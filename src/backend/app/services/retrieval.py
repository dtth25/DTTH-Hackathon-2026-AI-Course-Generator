"""Source-faithful evidence selection for generation and offline evaluation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from app.services.vector_store import Document, VectorStore


@dataclass(frozen=True)
class RetrievalCalibration:
    """Measured retrieval settings. ``None`` means no calibrated cutoff exists."""

    max_distance: Optional[float] = None
    metric: Optional[str] = None
    corpus_version: Optional[str] = None


_PAGE_NOISE_RE = re.compile(r"^(?:page|trang)\s+\d+(?:\s+(?:of|/|trên)\s+\d+)?$", re.IGNORECASE)


def _is_usable(doc: Document) -> bool:
    text = doc.content.strip()
    if not text or doc.metadata.get("is_front_matter") or doc.metadata.get("is_noise"):
        return False
    return not _PAGE_NOISE_RE.fullmatch(" ".join(text.split()))


def content_digest(content: str) -> str:
    """Hash complete NFC text while preserving case and meaningful internal whitespace."""

    normalized = unicodedata.normalize("NFC", content).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _int_metadata(doc: Document, *names: str) -> Optional[int]:
    for name in names:
        value = doc.metadata.get(name)
        try:
            if value is not None and value != "":
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


_LOCATION_ORDER_RE = re.compile(r"(?:^|/)(?:block|body|paragraph|table)\[(\d+)\]")


def _location_order(doc: Document) -> Optional[int]:
    location = doc.metadata.get("document_location")
    if not isinstance(location, str):
        return None
    match = _LOCATION_ORDER_RE.search(location)
    return int(match.group(1)) if match else None


def _source_key(doc: Document) -> tuple[str, int, int, int, int, int]:
    try:
        page = int(doc.metadata.get("page", 0))
    except (TypeError, ValueError):
        page = 0
    block_order = _int_metadata(doc, "block_order", "source_offset")
    if block_order is None:
        block_order = _location_order(doc)
    within_block = _int_metadata(
        doc,
        "within_block_order",
        "within_block_offset",
        "char_start",
        "offset",
    )
    rank = int(doc.metadata.get("similarity_rank", 0))
    return (
        str(doc.metadata.get("source_file", "")),
        page,
        1 if block_order is None else 0,
        block_order if block_order is not None else rank,
        within_block if within_block is not None else rank,
        rank,
    )


def select_evidence(candidates: list[Document], k: int) -> list[Document]:
    """Filter and deduplicate ranked candidates, then source-sort selected evidence."""

    selected: list[Document] = []
    seen: set[str] = set()
    for rank, candidate in enumerate(candidates):
        if not _is_usable(candidate):
            continue
        digest = content_digest(candidate.content)
        if digest in seen:
            continue
        seen.add(digest)
        candidate.metadata = {
            **candidate.metadata,
            "similarity_rank": candidate.metadata.get("similarity_rank", rank),
        }
        selected.append(candidate)
        if len(selected) >= k:
            break
    selected.sort(key=_source_key)
    return selected


def retrieve_evidence(
    course_id: str,
    query: str,
    k: int,
    calibration: RetrievalCalibration | None = None,
    *,
    vector_store: VectorStore | None = None,
    provider: str = "openrouter",
    coverage_sources: list[str] | None = None,
) -> list[Document]:
    """Retrieve owned course evidence without inventing an uncalibrated distance cutoff."""

    if vector_store is None:
        from app.services.vector_store import get_vector_store

        vector_store = get_vector_store()
    measured = calibration or RetrievalCalibration()
    candidates = vector_store.search(
        query=query,
        course_id=course_id,
        k=k + 5,
        max_distance=measured.max_distance,
        provider=provider,
    )
    if not coverage_sources:
        return select_evidence(candidates, k)

    ranked: list[Document] = []
    for rank, candidate in enumerate(candidates):
        candidate.metadata = {**candidate.metadata, "similarity_rank": rank}
        ranked.append(candidate)

    # Cover at most k sources and scan a finite k-derived number of stored rows per source.
    # The bound applies before storage access, while selection stops as soon as one usable
    # representative is found. Front matter/noise therefore does not consume the usable
    # representative budget.
    sources = list(dict.fromkeys(str(source) for source in coverage_sources if source))[:k]
    representatives: list[Document] = []
    next_rank = len(ranked)
    for source in sources:
        representative = next(
            (
                doc
                for doc in ranked
                if doc.metadata.get("source_file") == source and _is_usable(doc)
            ),
            None,
        )
        offset = 0
        scan_budget = min(50, max(2, k + 5))
        while representative is None and offset < scan_budget:
            page_size = min(2, scan_budget - offset)
            local = vector_store.get_course_chunks(
                course_id,
                provider=provider,
                source_file=source,
                limit=page_size,
                offset=offset,
            )
            if not local:
                break
            for document in local:
                document.metadata = {**document.metadata, "similarity_rank": next_rank}
                next_rank += 1
                if representative is None and _is_usable(document):
                    representative = document
            offset += len(local)
            if len(local) < page_size:
                break
        if representative is not None:
            representatives.append(representative)
    return select_evidence(representatives + ranked, k)
