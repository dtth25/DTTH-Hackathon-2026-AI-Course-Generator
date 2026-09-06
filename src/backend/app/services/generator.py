"""Generation Service responsible for RAG retrieval, LLM generation, scoring, and artifact storage."""

import json
import hashlib
import logging
import os
import re
import random
import inspect
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from sqlalchemy import case, text, update
from sqlalchemy.orm import Session
from billiard.exceptions import SoftTimeLimitExceeded
from app.services.provider_usage import BudgetLimitError, current_provider_context, stage_timer, book_usage, usage_context
from app.services.book_content_budget import (
    BookCoverageInfeasible,
    allocate_book_budget,
    outline_output_allowance,
)
from app.core.config import settings
from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob
from app.models.source_plan import SourcePlanRecord
from app.schemas.generation import (
    GroundingData,
    QualityScoresData,
    ReadinessData,
    StudyPackData,
    StudyPackResponse,
    StudyPackStats,
)
from app.schemas.generator_output import (
    BookChapter,
    BookChapterContent,
    BookChapterPlan,
    BookOutline,
    BookOutput,
    QuizOutput,
    QualityReport,
    SlidesOutput,
    VidOutput,
    validate_and_score_output,
)
from app.schemas.source_plan import SourceObjective, SourcePlan, SourcePlanUnit
from app.services.llm import (
    BookIncompleteError,
    LLMService,
    validate_book_chapter_completion,
)
from app.services.book_checkpoint import (
    BOOK_PROMPT_REVISION,
    BookCheckpointStore,
    CheckpointIdentity,
    canonical_digest,
    checkpoint_write_fence,
    options_digest as book_options_digest,
    plan_digest as checkpoint_plan_digest,
    remove_book_checkpoints,
)
from app.services.public_errors import sanitize_public_payload
from app.services.retrieval import retrieve_evidence
from app.services.source_plan import get_or_create_source_plan, source_plan_request_revision
from app.services.provider_guard import ProviderCircuitOpen
from app.services.pdf_book import build_book_pdf
from app.services.text_format import normalize_display_text, normalize_narration
from app.services.vector_store import VectorStore
from app.services.versioning import (
    AtomicArtifactDirectory,
    GenerationInFlightError,
    VERSION_CAPS,
    VersionCapReachedError,
    artifact_directory_path,
    migrate_legacy_artifact_metadata,
    remove_artifact_version,
    version_label,
    version_slug,
)

logger = logging.getLogger(__name__)

SOURCE_PLAN_PROMPT_REVISION = "source-plan-v1"

_PUBLIC_QUALITY_REPORT_FIELDS = {
    "structural_validity",
    "citation_validity",
    "source_coverage",
    "extraction_complete",
    "faithfulness",
    "indexed_chunk_count",
    "invalid_citation_count",
    "missing_citation_count",
    "labels",
}


def _quality_report_payload(report: QualityReport | Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
    """Return only aggregate quality fields; never persist or expose raw evidence IDs."""

    if report is None:
        return None
    raw = report.model_dump() if isinstance(report, QualityReport) else report
    if not isinstance(raw, dict):
        return None
    return {key: raw[key] for key in _PUBLIC_QUALITY_REPORT_FIELDS if key in raw}


def _quality_report_key(artifact: str) -> str:
    return "study_guide_pdf" if artifact == "book" else artifact


def _active_quality_report_payloads(study_pack: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Derive report caches from active versions so removed artifacts cannot leak stale checks."""

    reports: Dict[str, Dict[str, Any]] = {}
    artifacts = study_pack.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return reports
    for artifact, entry in artifacts.items():
        if not isinstance(entry, dict):
            continue
        versions = entry.get("versions", {})
        active = entry.get("active")
        if not isinstance(versions, dict) or active not in versions:
            continue
        version = versions.get(active)
        if not isinstance(version, dict):
            continue
        payload = _quality_report_payload(version.get("quality_report"))
        if payload is not None:
            reports[_quality_report_key(artifact)] = payload
    return reports


class _GenerationInterrupted(Exception):
    """The durable worker lost its lease or observed cancellation."""


@dataclass(frozen=True)
class _BookChapterTask:
    index: int
    book_title: str
    plan: BookChapterPlan
    total: int
    context: str
    valid_chunk_ids: tuple[str, ...]
    detail_level: str
    max_output_tokens: int | None
    reasoning_tokens: int | None
    required_objectives: dict[str, str]


_LEADING_ID_TOKEN_RE = re.compile(r"^([A-Za-z0-9-]+)[_\s]+")
_ARRAY_INDEX_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9]*)(\[[A-Za-z0-9, ]+\](?:\[[A-Za-z0-9, ]+\])*)")


def _strip_leading_id_token(text: str) -> str:
    """Strip a leading filename-style identifier code (e.g. "NLC416-14jh005357-58048_Title"
    -> "Title") from a topic-fallback string, so a generated title/topic never leaks an
    internal document ID. Only strips when the leading token has >=4 digits, so a real title
    that happens to start with a short number (e.g. "3D Printing Basics") survives untouched."""
    m = _LEADING_ID_TOKEN_RE.match(text)
    if not m:
        return text
    token = m.group(1)
    if sum(c.isdigit() for c in token) >= 4:
        return text[m.end():].strip()
    return text


def _clean_slides_output(deck: SlidesOutput) -> SlidesOutput:
    """Apply only safe display normalization before persisting a slide deck."""
    deck.title = normalize_display_text(deck.title)
    for sl in deck.slides:
        sl.title = normalize_display_text(sl.title)
        sl.bullet_points = [normalize_display_text(b) for b in sl.bullet_points]
    return deck


def _repair_flattened_array_indices(data: Any, source_context: str, artifact_type: str) -> Any:
    """Restore bracketed array indices that Flash occasionally flattens (``P[i]`` ->
    ``Pi``). Replacements are deliberately limited to canonical forms observed in the
    retrieved source context, so prose from an unrelated document is never guessed at."""
    replacements = {}
    for match in _ARRAY_INDEX_RE.finditer(source_context):
        canonical = match.group(0)
        flattened = match.group(1) + re.sub(r"[\[\], ]", "", match.group(2))
        if flattened != canonical:
            replacements[flattened] = canonical

    def repair(text: str) -> str:
        for flattened, canonical in replacements.items():
            text = re.sub(
                rf"(?<![A-Za-z0-9]){re.escape(flattened)}(?![A-Za-z0-9])",
                canonical,
                text,
            )
        return text

    if artifact_type == "slides":
        data.title = repair(data.title)
        for slide in data.slides:
            slide.title = repair(slide.title)
            slide.bullet_points = [repair(point) for point in slide.bullet_points]
    elif artifact_type == "quiz":
        data.title = repair(data.title)
        for question in data.questions:
            question.question_text = repair(question.question_text)
            question.options = [option.model_copy(update={"text": repair(option.text)}) for option in question.options]
            question.explanation = repair(question.explanation)
    return data


def _clean_vid_output(vid: VidOutput) -> VidOutput:
    """Keep screen text canonical; normalize only narration for the TTS boundary."""
    vid.title = normalize_display_text(vid.title)
    for sc in vid.scenes:
        sc.title = normalize_display_text(sc.title)
        sc.on_screen_text = normalize_display_text(sc.on_screen_text)
        sc.key_points = [normalize_display_text(kp) for kp in sc.key_points]
        if sc.diagram:
            sc.diagram.title = normalize_display_text(sc.diagram.title) or None
            for item in sc.diagram.items:
                item.label = normalize_display_text(item.label)
                item.detail = normalize_display_text(item.detail) or None
        sc.narration = normalize_narration(sc.narration)
    return vid


def _balance_quiz_answers(quiz: QuizOutput, version_id: str) -> QuizOutput:
    """Deterministically spread correct answers across A-D before every persistence path."""
    letters = ["A", "B", "C", "D"]
    targets = [letters[index % len(letters)] for index in range(len(quiz.questions))]
    rng = random.Random(version_id)
    for _ in range(32):
        rng.shuffle(targets)
        if all(targets[i] != targets[i - 1] or targets[i] != targets[i - 2] for i in range(2, len(targets))):
            break
    for question, target in zip(quiz.questions, targets):
        by_key = {option.key.upper(): option for option in question.options}
        correct = by_key.get(question.correct_answer.upper())
        others = [option for option in question.options if option is not correct]
        rng.shuffle(others)
        target_index = letters.index(target)
        arranged = others[:target_index] + ([correct] if correct else []) + others[target_index:]
        if len(arranged) != 4:
            continue
        for key, option in zip(letters, arranged):
            option.key = key
        question.options = arranged
        question.correct_answer = target
    return quiz


class Generator:
    """Orchestrates RAG retrieval, AI generation, validation, and file storage."""

    def __init__(self, vector_store: VectorStore | None, llm: LLMService, feature_llms: Optional[Dict[str, LLMService]] = None):
        self._vector_store = vector_store
        self.llm = llm
        # Kept injectable for tests; production uses a single OpenRouter service.
        self.feature_llms = feature_llms or {}
        self._generation_versions: Dict[tuple[str, str], str] = {}
        self._source_plan_contexts: Dict[tuple[str, str], Tuple[str, List[str]]] = {}
        self._source_plan_models: Dict[tuple[str, str, int], str] = {}

    @property
    def vector_store(self) -> VectorStore:
        """Initialize retrieval storage only when a retrieval operation needs it."""
        if self._vector_store is None:
            from app.services.vector_store import get_vector_store

            self._vector_store = get_vector_store()
        return self._vector_store

    @vector_store.setter
    def vector_store(self, value: VectorStore | None) -> None:
        self._vector_store = value

    def _llm_for(self, feature: str) -> LLMService:
        return self.feature_llms.get(feature, self.llm)

    def _source_plan_inputs(self, course_id: str, db_session_factory=None):
        """Read only this course's indexed content and derive a stable source digest."""
        provider = self._get_embedding_provider(course_id, db_session_factory)
        source_names = self._get_doc_name_list(course_id, db_session_factory)
        context, evidence_ids = self._retrieve_context(
            course_id,
            k=80,
            db_session_factory=db_session_factory,
            coverage_sources=source_names,
        )
        self._require_context(context)
        chunks = (
            self.vector_store.get_course_chunks(course_id, provider=provider)
            if isinstance(self.vector_store, VectorStore)
            else []
        )
        ordered = sorted(chunks, key=lambda item: str(item.metadata.get("chunk_id", "")))
        digest = hashlib.sha256()
        if ordered:
            for chunk in ordered:
                digest.update(str(chunk.metadata.get("chunk_id", "")).encode("utf-8"))
                digest.update(b"\0")
                digest.update(chunk.content.encode("utf-8"))
                digest.update(b"\0")
        else:
            # Compatibility for bounded/fake stores that expose only the retrieval API.
            digest.update(context.encode("utf-8"))
        return digest.hexdigest(), context, evidence_ids

    @staticmethod
    def _validated_source_plan(
        plan: SourcePlan, revision: int, source_digest: str, valid_ids: List[str]
    ) -> SourcePlan:
        """Reject invented evidence and normalize stable internal unit/objective IDs."""
        allowed = set(valid_ids)
        plan = plan.model_copy(
            update={"revision": revision, "source_digest": source_digest}, deep=True
        )
        objective_id_map = {
            objective.id: f"objective-{index + 1}"
            for index, objective in enumerate(plan.objectives)
        }
        for objective in plan.objectives:
            objective.id = objective_id_map[objective.id]
        objective_ids = {objective.id for objective in plan.objectives}
        for index, unit in enumerate(plan.units):
            unit.id = f"unit-{index + 1}"
            unit.objective_ids = [
                objective_id_map[value]
                for value in unit.objective_ids
                if objective_id_map.get(value) in objective_ids
            ]
        evidenced = [*plan.objectives, *plan.glossary, *plan.equations, *plan.units]
        if any(not set(item.evidence_ids) or not set(item.evidence_ids).issubset(allowed) for item in evidenced):
            raise ValueError("Source plan cited evidence outside the owned retrieved source")
        return SourcePlan.model_validate(plan.model_dump())

    def _get_source_plan(
        self,
        course_id: str,
        feature: Optional[str] = None,
        db_session_factory=None,
        *,
        selected_llm=None,
    ) -> SourcePlan:
        source_digest, context, evidence_ids = self._source_plan_inputs(
            course_id, db_session_factory
        )
        self._source_plan_contexts[(course_id, source_digest)] = (context, evidence_ids)
        selected_llm = selected_llm or (self._llm_for(feature) if feature else self.llm)
        model = getattr(selected_llm, "model", settings.OPENROUTER_MODEL)

        def build(revision: int) -> SourcePlan:
            generate = getattr(selected_llm, "generate_source_plan", None)
            if generate is None:
                raw = self._fallback_source_plan(revision, source_digest, evidence_ids)
            elif isinstance(selected_llm, LLMService) and getattr(
                selected_llm, "book_policy", None
            ) is not None:
                source_plan_output = min(4_000, 1_800 + 200 * len(evidence_ids))
                parameters = inspect.signature(generate).parameters.values()
                supports_budget = any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    or parameter.name == "max_output_tokens"
                    for parameter in parameters
                )
                if supports_budget:
                    raw = generate(
                        context,
                        source_digest,
                        revision,
                        evidence_ids,
                        max_output_tokens=source_plan_output,
                        reasoning_tokens=selected_llm.book_policy.reasoning_budget,
                    )
                else:
                    raw = generate(context, source_digest, revision, evidence_ids)
            else:
                raw = generate(context, source_digest, revision, evidence_ids)
            return self._validated_source_plan(raw, revision, source_digest, evidence_ids)

        plan = get_or_create_source_plan(
            course_id,
            source_digest,
            model,
            SOURCE_PLAN_PROMPT_REVISION,
            db_session_factory=(db_session_factory or None),
            create=build,
        )
        provenance_db = self._get_db(db_session_factory)
        try:
            record = provenance_db.query(SourcePlanRecord).filter_by(
                course_id=course_id, revision=plan.revision
            ).one()
            self._source_plan_models[
                (course_id, plan.source_digest, plan.revision)
            ] = record.model
        finally:
            provenance_db.close()
        return plan

    @staticmethod
    def _fallback_source_plan(
        revision: int, source_digest: str, evidence_ids: List[str]
    ) -> SourcePlan:
        """Compatibility plan for injected legacy test doubles without a plan method."""
        # The compatibility plan must preserve the same targeted-context invariant
        # as a generated plan. Repeating every source block in all four units would
        # make the uncached Book input grow fourfold.
        buckets = [[] for _ in range(4)]
        for index, evidence_id in enumerate(evidence_ids):
            buckets[index % len(buckets)].append(evidence_id)
        fallback_id = evidence_ids[0] if evidence_ids else "chunk_1"
        buckets = [bucket or [fallback_id] for bucket in buckets]
        objectives = [
            SourceObjective(
                id=f"objective-{index}",
                text=f"Giải thích nội dung học tập {index}",
                evidence_ids=buckets[index - 1],
            )
            for index in range(1, 5)
        ]
        return SourcePlan(
            revision=revision,
            source_digest=source_digest,
            objectives=objectives,
            glossary=[],
            equations=[],
            units=[
                SourcePlanUnit(
                    id=f"unit-{index}",
                    title=f"Nội dung học tập {index}",
                    objective_ids=[f"objective-{index}"],
                    evidence_ids=buckets[index - 1],
                )
                for index in range(1, 5)
            ],
        )

    def _plan_context(
        self,
        course_id: str,
        plan: SourcePlan,
        topic: str = "",
        *,
        all_units: bool = False,
        unit_ids: Optional[List[str]] = None,
        evidence_ids_override: Optional[List[str]] = None,
    ) -> Tuple[str, List[str], List[Any]]:
        """Provide prompts only the plan units and owned evidence relevant to this request."""
        terms = {token for token in re.findall(r"\w+", topic.casefold()) if len(token) > 2}
        if unit_ids is not None:
            wanted = set(unit_ids)
            selected = [unit for unit in plan.units if unit.id in wanted]
            if len(selected) != len(wanted):
                raise ValueError("Unknown source-plan unit assignment")
        else:
            selected = list(plan.units) if all_units else [
                unit for unit in plan.units if terms & set(re.findall(r"\w+", unit.title.casefold()))
            ]
        if not selected:
            selected = list(plan.units[: min(4, len(plan.units))])
        evidence_ids = list(dict.fromkeys(cid for unit in selected for cid in unit.evidence_ids))
        if evidence_ids_override is not None:
            known_evidence = {
                evidence_id
                for item in [*plan.objectives, *plan.glossary, *plan.equations, *plan.units]
                for evidence_id in item.evidence_ids
            }
            requested = list(dict.fromkeys(evidence_ids_override))
            if not set(requested).issubset(known_evidence):
                raise ValueError("Chapter allocation requested evidence outside the source plan")
            evidence_ids = requested
        cached = self._source_plan_contexts.get((course_id, plan.source_digest))
        if cached and set(evidence_ids) == set(cached[1]):
            chunks = []
            fallback_context = cached[0]
        else:
            try:
                chunks = self.vector_store.get_course_chunks(course_id, evidence_ids)
            except (KeyError, TypeError):
                fallback_context, fallback_ids = self._retrieve_context(
                    course_id,
                    query=topic,
                    k=80,
                    coverage_sources=self._get_doc_name_list(course_id),
                )
                chunks = []
                evidence_ids = fallback_ids
            else:
                fallback_context = ""
        by_id = {str(chunk.metadata.get("chunk_id")): chunk for chunk in chunks}
        evidence = "\n\n".join(
            f"[Chunk ID: {cid}]:\n{by_id[cid].content}" for cid in evidence_ids if cid in by_id
        ) or fallback_context
        selected_ids = {unit.id for unit in selected}
        selected_objectives = [
            item.model_dump() for item in plan.objectives
            if any(item.id in unit.objective_ids for unit in selected)
        ]
        relevant_evidence = set(evidence_ids)
        plan_payload = {
            "revision": plan.revision,
            "objectives": selected_objectives,
            "glossary": [item.model_dump() for item in plan.glossary if relevant_evidence & set(item.evidence_ids)],
            "equations": [item.model_dump() for item in plan.equations if relevant_evidence & set(item.evidence_ids)],
            "units": [item.model_dump() for item in plan.units if item.id in selected_ids],
        }
        return (
            "SOURCE PLAN (ràng buộc dùng chung; giữ nguyên định nghĩa và LaTeX):\n"
            + json.dumps(plan_payload, ensure_ascii=False)
            + "\nOUTPUT ASSIGNMENT: output item N must cite only the evidence of unit "
            + "((N-1) modulo selected unit count)."
            + "\n\nOWNED UNIT EVIDENCE:\n"
            + evidence,
            evidence_ids,
            selected,
        )

    def _bind_version_to_plan(
        self, course_id: str, artifact: str, version_id: Optional[str], plan: SourcePlan,
        db_session_factory=None, selected_model: Optional[str] = None,
    ) -> None:
        if not version_id:
            return
        db = self._get_db(db_session_factory)
        try:
            course = db.get(Course, course_id)
            if course is None:
                raise ValueError("Course not found")
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            version = meta["study_pack"]["artifacts"][artifact]["versions"][version_id]
            version["source_plan_revision"] = plan.revision
            version["source_plan_digest"] = plan.source_digest
            version["source_plan_model"] = self._source_plan_models.get(
                (course_id, plan.source_digest, plan.revision),
                selected_model or settings.OPENROUTER_MODEL,
            )
            version["source_plan_prompt_revision"] = SOURCE_PLAN_PROMPT_REVISION
            course.metadata_json = json.dumps(meta, ensure_ascii=False)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _artifact_with_plan(data: Any, plan: SourcePlan, unit_ids: List[str]) -> Dict[str, Any]:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        payload["source_plan"] = {
            "revision": plan.revision,
            "source_digest": plan.source_digest,
            "unit_ids": unit_ids,
            "canonical_equations": [item.model_dump() for item in plan.equations],
            "glossary": [item.model_dump() for item in plan.glossary],
        }
        return payload

    @staticmethod
    def _top_level_visible_fields(data: Any, artifact: str) -> List[str]:
        values = [data.title]
        if artifact == "book":
            values.extend([data.summary, data.preface])
        return [str(value) for value in values if value]

    @staticmethod
    def _visible_item_fields(data: Any, artifact: str, index: int) -> List[str]:
        """Return learner-visible text fields without merging their claim boundaries."""
        values: List[Any] = []
        if artifact == "book":
            chapter = data.chapters[index]
            values.extend([chapter.chapter_title, chapter.introduction, *chapter.objectives])
            for section in chapter.sections:
                values.extend([section.title, section.content])
            values.extend(chapter.key_points + chapter.review_questions)
        elif artifact == "slides":
            slide = data.slides[index]
            values.extend([slide.title, *slide.bullet_points])
        elif artifact == "quiz":
            question = data.questions[index]
            selected = next(
                (option.text for option in question.options if option.key == question.correct_answer),
                "",
            )
            # Distractors are intentionally false. Only the selected answer participates
            # in the truth-bearing canonical contract.
            values.extend([question.question_text, selected, question.explanation])
        else:
            scene = data.scenes[index]
            values.extend([scene.title, scene.on_screen_text or "", scene.narration, *scene.key_points])
            if scene.diagram:
                values.append(scene.diagram.title or "")
                for item in scene.diagram.items:
                    values.extend([item.label, item.detail or ""])
        return [str(value) for value in values if value]

    @classmethod
    def _visible_item_text(cls, data: Any, artifact: str, index: int) -> str:
        fields = cls._visible_item_fields(data, artifact, index)
        if index == 0:
            fields = [*cls._top_level_visible_fields(data, artifact), *fields]
        return "\n".join(fields)

    @staticmethod
    def _normalized_canonical_text(value: str) -> str:
        """Normalize presentation whitespace while preserving semantic punctuation."""
        # An exclamation mark may be factorial (including repeated factorials).
        # Never discard it, even when it occurs at the end of an answer.
        return re.sub(r"\s+", " ", value.casefold()).strip().rstrip(".?;").strip()

    @classmethod
    def _named_claim_values(
        cls, fields: List[str], name: str, *, equation_only: bool = False
    ) -> List[str]:
        """Extract every explicit value asserted for a named definition/equation."""
        escaped_name = re.escape(name)
        connectors = r"=" if equation_only else (
            r":|=|means?|is(?:\s+defined\s+as)?|has\s+the\s+meaning|"
            r"là|có\s+nghĩa\s+là|được\s+định\s+nghĩa\s+là"
        )
        prefix = rf"(?<!\w){escaped_name}(?!\w)\s*(?:{connectors})\s*"
        next_claim = (
            rf"(?:(?:,\s*|\s+)(?:but|and|nhưng|và)\s+)?"
            rf"(?<!\w){escaped_name}(?!\w)\s*(?:{connectors})"
        )
        # A period followed by a digit belongs to a number (0.5 or .5),
        # while factorial must remain part of the asserted mathematical value.
        sentence_end = r"\.(?=\s|$)|[?;\n]"
        pattern = re.compile(
            rf"{prefix}(.*?)(?={next_claim}|{sentence_end}|$)",
            flags=re.IGNORECASE,
        )
        return [match.group(1).strip(" ,") for field in fields for match in pattern.finditer(field)]

    @classmethod
    def _reject_conflicting_named_claims(
        cls,
        fields: List[str],
        name: str,
        allowed_values: List[str],
        *,
        equation_only: bool = False,
    ) -> None:
        """Reject explicit claims about a named plan item that disagree with its canon.

        This deliberately recognizes only explicit definition/equation syntax. It does
        not attempt general factual verification, which remains outside CP6 scoring.
        """
        normalized_allowed = {
            cls._normalized_canonical_text(value) for value in allowed_values if value
        }
        for value in cls._named_claim_values(fields, name, equation_only=equation_only):
            claim = cls._normalized_canonical_text(value)
            if claim and claim not in normalized_allowed:
                raise ValueError("Visible output contains a conflicting canonical claim")

    @classmethod
    def _reject_incorrect_quiz_answer(
        cls, data: Any, index: int, name: str, canonical: str, *, equation: bool
    ) -> None:
        question = data.questions[index]
        prompt = question.question_text.casefold()
        if name.casefold() not in prompt:
            return
        if equation:
            asks_for_canonical = bool(re.search(r"formula|equation|công\s*thức|phương\s*trình", prompt))
        else:
            asks_for_canonical = bool(re.search(
                r"what\s+is|what\s+does|meaning|means|definition|là\s+gì|định\s+nghĩa|nghĩa\s+là\s+gì",
                prompt,
            ))
        if not asks_for_canonical:
            return
        selected = next(
            (option.text for option in question.options if option.key == question.correct_answer),
            "",
        )
        expected = cls._normalized_canonical_text(canonical)
        if cls._normalized_canonical_text(selected) == expected:
            return
        selected_claims = cls._named_claim_values([selected], name, equation_only=equation)
        if selected_claims and all(
            cls._normalized_canonical_text(claim) == expected for claim in selected_claims
        ):
            return
        raise ValueError("Quiz correct answer conflicts with the canonical plan")

    @staticmethod
    def _append_visible_canonical(data: Any, artifact: str, index: int, statement: str) -> None:
        if artifact == "book" and data.chapters[index].sections:
            data.chapters[index].sections[0].content += f"\n\n{statement}"
        elif artifact == "slides":
            data.slides[index].bullet_points.append(statement)
        elif artifact == "quiz":
            data.questions[index].explanation += f" {statement}"
        elif artifact == "vid":
            data.scenes[index].narration += f" {statement}"
        else:
            raise ValueError("Generated artifact has no visible canonical-content target")

    def _enforce_canonical_consistency(
        self, data: Any, artifact: str, plan: SourcePlan, assigned_units: List[Any]
    ) -> None:
        """Reject visible contradictions and add omitted assigned canonical facts.

        This checks cross-artifact wording only. It deliberately does not claim source
        faithfulness; CP6's factual evaluation remains unevaluated.
        """
        initial_visible = [
            self._visible_item_text(data, artifact, index)
            for index in range(len(assigned_units))
        ]
        visible_fields = [
            self._visible_item_fields(data, artifact, index)
            for index in range(len(assigned_units))
        ]
        top_level_fields = self._top_level_visible_fields(data, artifact)
        for entry in plan.glossary:
            indexes = [
                index for index, unit in enumerate(assigned_units)
                if set(unit.evidence_ids).intersection(entry.evidence_ids)
            ]
            if not indexes:
                continue
            same_name_equations = [
                equation.latex for equation in plan.equations
                if equation.name.casefold() == entry.term.casefold()
            ]
            for index in indexes:
                self._reject_conflicting_named_claims(
                    [*top_level_fields, *visible_fields[index]],
                    entry.term,
                    [entry.definition, *same_name_equations],
                )
                if artifact == "quiz":
                    self._reject_incorrect_quiz_answer(
                        data, index, entry.term, entry.definition, equation=False
                    )
            mentions = [
                index for index in indexes
                if entry.term.casefold() in initial_visible[index].casefold()
            ]
            if mentions:
                if any(entry.definition not in initial_visible[index] for index in mentions):
                    raise ValueError("Visible output contradicts or omits a canonical definition")
            else:
                self._append_visible_canonical(
                    data, artifact, indexes[0], f"{entry.term}: {entry.definition}"
                )
        for equation in plan.equations:
            indexes = [
                index for index, unit in enumerate(assigned_units)
                if set(unit.evidence_ids).intersection(equation.evidence_ids)
            ]
            if not indexes:
                continue
            for index in indexes:
                self._reject_conflicting_named_claims(
                    [*top_level_fields, *visible_fields[index]],
                    equation.name,
                    [equation.latex],
                    equation_only=True,
                )
                if artifact == "quiz":
                    self._reject_incorrect_quiz_answer(
                        data, index, equation.name, equation.latex, equation=True
                    )
            mentions = [
                index for index in indexes
                if equation.name.casefold() in initial_visible[index].casefold()
            ]
            if mentions:
                if any(equation.latex not in initial_visible[index] for index in mentions):
                    raise ValueError("Visible output contradicts or omits a canonical equation")
            else:
                self._append_visible_canonical(
                    data, artifact, indexes[0], f"{equation.name}: {equation.latex}"
                )

    def _get_db(self, db_session_factory=None):
        if db_session_factory is None:
            from app.services.database import SessionLocal
            return SessionLocal()
        return db_session_factory()

    def _get_embedding_provider(self, course_id: str, db_session_factory=None) -> str:
        """Lazy-migrate legacy embeddings before a retrieval operation."""
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            provider = course.embedding_provider if course else "openrouter"
            if provider != "gemini":
                return "openrouter"

            legacy_chunks = self.vector_store.get_legacy_course_chunks(course_id)
            if not legacy_chunks:
                raise ValueError("Không tìm thấy dữ liệu lập chỉ mục cũ để nâng cấp khóa học này.")
            self.vector_store.add_documents(legacy_chunks, course_id=course_id, provider="openrouter")
            migrated_count = self.vector_store.get_course_stats(course_id, provider="openrouter").get("chunk_count", 0)
            if migrated_count < len(legacy_chunks):
                raise RuntimeError("Không thể xác nhận đầy đủ dữ liệu lập chỉ mục sau khi nâng cấp.")
            course.embedding_provider = "openrouter"
            db.commit()
            logger.info("Migrated %s legacy embeddings to OpenRouter", course_id)
            return "openrouter"
        finally:
            db.close()

    def _retrieve_context(
        self,
        course_id: str,
        query: str = "",
        k: int = 20,
        db_session_factory=None,
        coverage_sources: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        """Retrieve usable owned evidence, then present it in coherent source order."""
        search_query = query or "tổng quan kiến thức khóa học các chương quan trọng"
        provider = self._get_embedding_provider(course_id, db_session_factory)
        chunks = retrieve_evidence(
            course_id,
            search_query,
            k,
            vector_store=self.vector_store,
            provider=provider,
            coverage_sources=coverage_sources,
        )
        if not chunks:
            logger.warning("No usable source evidence found for course %s.", course_id)
            return "", []

        context_lines = []
        valid_chunk_ids = []
        for i, doc in enumerate(chunks):
            cid = doc.metadata.get("chunk_id") or f"chunk_{i+1}"
            valid_chunk_ids.append(cid)
            file_name = doc.metadata.get("source_file", "unknown")
            page_num = doc.metadata.get("page", 1)
            context_lines.append(
                f"[Chunk ID: {cid}] (Tài liệu: {file_name}, Trang: {page_num}):\n{doc.content}"
            )

        return "\n\n".join(context_lines), valid_chunk_ids

    _NO_CONTEXT_MSG = (
        "Không tìm thấy nội dung nào từ tài liệu để tạo học liệu. Tài liệu có thể là bản "
        "scan/ảnh chưa trích xuất được chữ, hoặc chưa lập chỉ mục thành công. Hãy thử xoá "
        "và tải lại tài liệu (ưu tiên PDF có lớp văn bản thật, không phải ảnh chụp)."
    )
    _PROCESSING_MSG = (
        "Tài liệu vẫn đang được xử lý (trích xuất và lập chỉ mục nội dung). Việc này có thể "
        "mất khoảng nửa phút với tài liệu dài. Vui lòng đợi giây lát rồi thử lại."
    )

    def _require_course_not_processing(self, course_id: str, db_session_factory=None) -> None:
        """Guard: refuse to run a generator while the course's document ingestion is still
        running. Without this, a generate call fired right after upload — before chunking/
        embedding finishes writing chunk_count — hits the exact same "no chunks found" path
        as a genuinely broken document, and `_require_context`'s scan/OCR-focused message is
        actively misleading here since the document is fine, just not indexed yet. Ingestion
        legitimately takes 10-30+s for large real documents, long enough for a
        user clicking into a tab right after upload to reliably hit this race."""
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if course and course.status == "processing":
                raise ValueError(self._PROCESSING_MSG)
        finally:
            db.close()

    def _require_context(self, context: str) -> None:
        """Guard: refuse to run a generator on empty RAG context. Without this, the LLM
        dutifully writes a 'no context was provided' apology that gets saved and marked
        ready — the Study Guide shows an abstention essay, Quiz yields 0 questions (the
        frontend then sticks at 100% because its data never passes isReady), and Video
        narrates generic filler. Failing loud turns all of those into one clear error."""
        if not context or not context.strip():
            raise ValueError(self._NO_CONTEXT_MSG)

    def _get_artifact_dir(self, course_id: str) -> str:
        """Get or create local filesystem artifact storage directory."""
        dir_path = os.path.join(settings.UPLOAD_DIR, course_id, "artifacts")
        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    def _start_version_write(
        self,
        course_id: str,
        artifact: str,
        version_id: Optional[str],
        execution_token: Optional[str] = None,
    ):
        if not version_id:
            return None, None
        self._generation_versions[(course_id, artifact)] = version_id
        transaction = AtomicArtifactDirectory(
            artifact_directory_path(settings.UPLOAD_DIR, course_id, artifact, version_id)
        )
        if execution_token:
            safe_token = re.sub(r"[^A-Za-z0-9_-]", "-", execution_token)
            transaction.temp_dir = Path(f"{transaction.target_dir}.tmp.{safe_token}")
        return transaction, transaction.prepare()

    def _ready_version_output(
        self,
        course_id: str,
        artifact: str,
        filename: str,
        version_id: Optional[str],
        output_type,
        db_session_factory=None,
    ):
        """Return an already-published version without touching its files."""
        if not version_id:
            return False, None
        status = self.get_artifact_status(
            course_id,
            artifact,
            version_id=version_id,
            db_session_factory=db_session_factory,
        )
        if status.get("status") != "ready":
            return False, None
        artifact_dir = artifact_directory_path(
            settings.UPLOAD_DIR, course_id, artifact, version_id
        )
        payload = self._load_artifact_json(course_id, filename, artifact_dir)
        return True, output_type.model_validate(payload) if payload else None

    @staticmethod
    def _report_progress(progress_callback: Optional[Callable[[], bool]]) -> None:
        if progress_callback and not progress_callback():
            raise _GenerationInterrupted

    def _finish_version_write(self, transaction, success: bool) -> None:
        if transaction:
            transaction.commit() if success else transaction.abort()

    def _publish_ready_version(
        self,
        transaction,
        *,
        course_id: str,
        artifact: str,
        version_id: str,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
        score: Optional[int] = None,
        quality_report: QualityReport | Dict[str, Any] | None = None,
        db_session_factory=None,
    ) -> bool:
        """Atomically fence job ownership, publish files, and mark both records ready."""
        if not job_id:
            self._finish_version_write(transaction, True)
            self._set_artifact_status(
                course_id,
                artifact,
                "ready",
                progress=100,
                version_id=version_id,
                quality_report=quality_report,
                db_session_factory=db_session_factory,
            )
            return True

        db = self._get_db(db_session_factory)
        try:
            now = datetime.utcnow()
            guard = db.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.course_id == course_id,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.worker_id == worker_id,
                    ProcessingJob.attempts == attempt_number,
                    ProcessingJob.cancel_requested.is_(False),
                    ProcessingJob.lease_expires_at > now,
                )
                .values(updated_at=ProcessingJob.updated_at)
            )
            if guard.rowcount != 1:
                db.rollback()
                return False
            course_query = db.query(Course).filter(Course.id == course_id)
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                course_query = course_query.with_for_update()
            course = course_query.first()
            if course is None or course.is_deleted:
                db.rollback()
                return False
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            study_pack = dict(meta.get("study_pack", {}))
            artifacts = dict(study_pack.get("artifacts", {}))
            entry = dict(artifacts.get(artifact, {}))
            versions = dict(entry.get("versions", {}))
            if version_id not in versions:
                db.rollback()
                return False
            current = dict(versions.get(version_id, {}))
            if current.get("status") != "processing":
                db.rollback()
                return False
            job = db.get(ProcessingJob, job_id)
            payload = job.payload_json if job and isinstance(job.payload_json, dict) else {}
            if payload.get("version_id") != version_id:
                db.rollback()
                return False
            if artifact == "book":
                from app.models.provider_call import BookBudget

                budget_id = payload.get("budget_id")
                budget = db.get(BookBudget, budget_id) if budget_id else None
                if (
                    budget is None
                    or budget.course_id != course_id
                    or budget.version_id != version_id
                    or budget.user_id != course.user_id
                ):
                    db.rollback()
                    return False
            timestamp = now.isoformat()
            current.update(
                {
                    "status": "ready",
                    "error": None,
                    "error_code": None,
                    "technical_error": None,
                    "progress": 100,
                    "finished_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            if score is not None:
                current["quality_score"] = score
            report_payload = _quality_report_payload(quality_report)
            if report_payload is not None:
                current["quality_report"] = report_payload
            versions[version_id] = current
            entry.update({"active": version_id, "versions": versions})
            artifacts[artifact] = entry
            study_pack["artifacts"] = artifacts
            readiness = dict(study_pack.get("readiness", {}))
            quality_scores = dict(study_pack.get("quality_scores", {}))
            readiness_key = {
                "book": "study_guide_pdf",
                "slides": "slides",
                "quiz": "quiz",
                "vid": "vid",
            }[artifact]
            readiness[readiness_key] = True
            if score is not None:
                quality_scores[readiness_key] = score
            quality_reports = dict(study_pack.get("quality_reports", {}))
            if report_payload is not None:
                quality_reports[readiness_key] = report_payload
            grounding = dict(
                study_pack.get(
                    "grounding",
                    {
                        "num_chunks": course.chunk_count,
                        "quality_score": 0,
                        "warnings": [],
                    },
                )
            )
            scores = [value for value in quality_scores.values() if value > 0]
            if scores:
                grounding["quality_score"] = sum(scores) // len(scores)
                course.quality_score = grounding["quality_score"]
            study_pack["readiness"] = readiness
            study_pack["quality_scores"] = quality_scores
            study_pack["quality_reports"] = quality_reports
            study_pack["grounding"] = grounding
            meta["study_pack"] = study_pack

            transaction.commit()
            course.metadata_json = json.dumps(meta, ensure_ascii=False)
            completed = db.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.worker_id == worker_id,
                    ProcessingJob.attempts == attempt_number,
                    ProcessingJob.status == JobStatus.RUNNING.value,
                    ProcessingJob.cancel_requested.is_(False),
                )
                .values(
                    status=JobStatus.SUCCEEDED.value,
                    active_key=None,
                    worker_id=None,
                    lease_expires_at=None,
                    next_attempt_at=None,
                    progress=100,
                    message="Hoàn thành",
                    error_code=None,
                    error_message=None,
                    updated_at=now,
                    completed_at=now,
                )
            )
            if completed.rowcount != 1:
                db.rollback()
                return False
            db.commit()
            self._generation_versions.pop((course_id, artifact), None)
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _save_artifact_json(self, course_id: str, filename: str, data: Any, artifact_dir: Optional[str] = None) -> str:
        """Save generated Pydantic model or dict as JSON file."""
        dir_path = artifact_dir or self._get_artifact_dir(course_id)
        file_path = os.path.join(dir_path, filename)
        try:
            if hasattr(data, "model_dump"):
                content_dict = data.model_dump()
            elif hasattr(data, "dict"):
                content_dict = data.dict()
            else:
                content_dict = data
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(content_dict, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved artifact JSON to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error saving artifact JSON {filename}: {e}")
            raise

    def _load_artifact_json(self, course_id: str, filename: str, artifact_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load artifact JSON from disk if exists."""
        file_path = os.path.join(artifact_dir or self._get_artifact_dir(course_id), filename)
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading artifact JSON {filename}: {e}")
            return None

    def _generate_pdf_book(self, course_id: str, book_data: BookOutput, artifact_dir: Optional[str] = None) -> str:
        """Generate the Study Guide PDF (cover, preface, page-numbered TOC, chapters).

        Raises on failure — callers must treat that as a hard generation error, not write a
        placeholder file in its place.
        """
        file_path = os.path.join(artifact_dir or self._get_artifact_dir(course_id), "book.pdf")
        build_book_pdf(file_path, book_data)
        return file_path

    def _generate_pdf_slides(self, course_id: str, slides_data: SlidesOutput, artifact_dir: Optional[str] = None) -> str:
        """Generate a 16:9 Widescreen PDF presentation using ReportLab."""
        file_path = os.path.join(artifact_dir or self._get_artifact_dir(course_id), "slide.pdf")
        try:
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib import colors
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak, Table, TableStyle
            from app.services.pdf_utils import prepare_pdf_text, register_vietnamese_fonts

            font_name, font_bold = register_vietnamese_fonts()

            # Widescreen 16:9 is 960 width by 540 height
            doc = SimpleDocTemplate(
                file_path,
                pagesize=(960, 540),
                leftMargin=50,
                rightMargin=50,
                topMargin=50,
                bottomMargin=50
            )

            styles = getSampleStyleSheet()

            # Styles for Slide contents
            slide_title_style = ParagraphStyle(
                "SlideTitle",
                parent=styles["Title"],
                fontName=font_bold,
                fontSize=28,
                leading=34,
                textColor=colors.HexColor("#06b6d4"), # Cyan-500
                alignment=0,
                spaceAfter=20
            )

            slide_body_style = ParagraphStyle(
                "SlideBody",
                parent=styles["BodyText"],
                fontName=font_name,
                fontSize=16,
                leading=22,
                textColor=colors.HexColor("#f8fafc"), # slate-50
                spaceAfter=12
            )

            slide_quote_style = ParagraphStyle(
                "SlideQuote",
                parent=styles["Normal"],
                fontName=font_name,
                fontSize=22,
                leading=30,
                textColor=colors.HexColor("#38bdf8"), # light-blue-400
                alignment=1,
                spaceAfter=20
            )

            story = []

            # Page Templates: background & footer drawing
            def draw_title_slide_bg(canvas, doc):
                canvas.saveState()
                canvas.setFillColor(colors.HexColor("#020617"))
                canvas.rect(0, 0, 960, 540, fill=True, stroke=False)
                
                canvas.setFillColor(colors.HexColor("#0f172a"))
                canvas.rect(0, 0, 960, 80, fill=True, stroke=False)
                
                canvas.setFillColor(colors.HexColor("#06b6d4"))
                canvas.rect(50, 150, 8, 260, fill=True, stroke=False)
                canvas.restoreState()

            def draw_content_slide_bg(canvas, doc):
                canvas.saveState()
                canvas.setFillColor(colors.HexColor("#0f172a"))
                canvas.rect(0, 0, 960, 540, fill=True, stroke=False)

                canvas.setFillColor(colors.HexColor("#1e293b"))
                canvas.rect(0, 480, 960, 60, fill=True, stroke=False)

                canvas.setStrokeColor(colors.HexColor("#06b6d4"))
                canvas.setLineWidth(2)
                canvas.line(0, 480, 960, 480)

                canvas.setFillColor(colors.HexColor("#64748b"))
                canvas.setFont(font_name, 10)
                canvas.drawRightString(910, 20, f"Slide {canvas._pageNumber}")
                canvas.restoreState()

            # Slide 1: Cover Page
            story.append(Spacer(1, 100))
            title_p = Paragraph(f"<font color='#06b6d4'>{prepare_pdf_text(slides_data.title)}</font>", ParagraphStyle("CoverTitle", parent=slide_title_style, fontSize=36, leading=44, leftIndent=30))
            story.append(title_p)
            story.append(PageBreak())

            # Slide content pages
            for idx, item in enumerate(slides_data.slides):
                story.append(Spacer(1, 10))
                story.append(Paragraph(prepare_pdf_text(item.title), slide_title_style))
                story.append(Spacer(1, 10))

                layout_type = getattr(item, "layout_type", "default") or "default"
                if layout_type == "two_column":
                    mid = (len(item.bullet_points) + 1) // 2
                    left_bps = [f"• {prepare_pdf_text(bp)}" for bp in item.bullet_points[:mid]]
                    right_bps = [f"• {prepare_pdf_text(bp)}" for bp in item.bullet_points[mid:]]

                    left_text = "<br/><br/>".join(left_bps)
                    right_text = "<br/><br/>".join(right_bps)

                    left_p = Paragraph(left_text, slide_body_style)
                    right_p = Paragraph(right_text, slide_body_style)

                    t = Table([[left_p, right_p]], colWidths=[420, 420])
                    t.setStyle(TableStyle([
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                        ('LEFTPADDING', (0,0), (-1,-1), 0),
                        ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ]))
                    story.append(t)
                elif layout_type == "quote":
                    quote_text = "<br/><br/>".join(prepare_pdf_text(bp) for bp in item.bullet_points)
                    story.append(Spacer(1, 40))
                    story.append(Paragraph(f"<i>“{quote_text}”</i>", slide_quote_style))
                else:
                    bullets_html = []
                    for bp in item.bullet_points:
                        bullets_html.append(f"• {prepare_pdf_text(bp)}")
                    content_text = "<br/><br/>".join(bullets_html)
                    story.append(Paragraph(content_text, slide_body_style))

                if idx < len(slides_data.slides) - 1:
                    story.append(PageBreak())

            doc.build(
                story,
                onFirstPage=draw_title_slide_bg,
                onLaterPages=draw_content_slide_bg
            )
            logger.info(f"Generated 16:9 PDF Slides at {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error generating PDF slides: {e}", exc_info=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"PDF Slides Placeholder for {slides_data.title}")
            return file_path

    def _convert_pdf_to_images(self, pdf_path: str, course_id: str, artifact_dir: Optional[str] = None) -> list[str]:
        """Convert a PDF file into PNG slide images using PyMuPDF (fitz)."""
        import fitz
        artifact_dir = artifact_dir or self._get_artifact_dir(course_id)
        image_paths = []
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=150)
                img_name = f"slide_{i+1}.png"
                img_path = os.path.join(artifact_dir, img_name)
                pix.save(img_path)
                image_paths.append(img_path)
            logger.info(f"Converted {len(image_paths)} pages to PNG slide images for course {course_id}")
            return image_paths
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}", exc_info=True)
            return []

    def _generate_pptx_slides(self, course_id: str, slides_data: SlidesOutput, artifact_dir: Optional[str] = None) -> str:
        """Generate PowerPoint presentation by inserting ReportLab slide PNGs full screen."""
        artifact_dir = artifact_dir or self._get_artifact_dir(course_id)
        file_path = os.path.join(artifact_dir, "slide.pptx")
        try:
            from pptx import Presentation
            from pptx.util import Inches

            pdf_path = self._generate_pdf_slides(course_id, slides_data, artifact_dir)
            image_paths = self._convert_pdf_to_images(pdf_path, course_id, artifact_dir)

            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            
            blank_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
            
            for img_path in image_paths:
                slide = prs.slides.add_slide(blank_layout)
                slide.shapes.add_picture(img_path, 0, 0, width=prs.slide_width, height=prs.slide_height)

            prs.save(file_path)
            logger.info(f"Generated Slide PPTX at {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error generating Slide PPTX: {e}", exc_info=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"PPTX Placeholder for {slides_data.title}")
            return file_path

    def _generate_pdf_quiz_key(self, course_id: str, quiz_data: QuizOutput, artifact_dir: Optional[str] = None) -> str:
        """Generate Quiz PDF in two sections: Student Quiz Sheet and Answer Key & Explanations."""
        file_path = os.path.join(artifact_dir or self._get_artifact_dir(course_id), "quiz-key.pdf")
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib import colors
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
            from app.services.pdf_utils import prepare_pdf_text, register_vietnamese_fonts

            font_name, font_bold = register_vietnamese_fonts()

            doc = SimpleDocTemplate(file_path, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle("QTitle", parent=styles["Title"], fontName=font_bold, fontSize=20, leading=24, textColor=colors.HexColor("#1e3a8a"), spaceAfter=15)
            part_style = ParagraphStyle("QPart", parent=styles["Heading1"], fontName=font_bold, fontSize=15, leading=18, textColor=colors.HexColor("#4f46e5"), spaceBefore=10, spaceAfter=15)
            q_style = ParagraphStyle("QQ", parent=styles["Heading2"], fontName=font_bold, fontSize=12, leading=16, textColor=colors.HexColor("#1e293b"), spaceBefore=10, spaceAfter=6)
            body_style = ParagraphStyle("QBody", parent=styles["BodyText"], fontName=font_name, fontSize=11, leading=15, textColor=colors.HexColor("#0f172a"), spaceAfter=5)

            story = [Paragraph(f"BỘ ĐỀ KIỂM TRA & ĐÁNH GIÁ: {prepare_pdf_text(quiz_data.title)}", title_style), Spacer(1, 10)]

            # --- Part 1: Student Quiz Sheet ---
            story.append(Paragraph("PHẦN 1: ĐỀ THI TRẮC NGHIỆM (STUDENT QUIZ SHEET)", part_style))
            for q in quiz_data.questions:
                story.append(Paragraph(f"<b>Câu {q.question_number}:</b> {prepare_pdf_text(q.question_text)}", q_style))
                for opt in q.options:
                    story.append(Paragraph(f"<b>{opt.key}.</b> {prepare_pdf_text(opt.text)}", body_style))
                story.append(Spacer(1, 10))
            story.append(PageBreak())

            # --- Part 2: Answer Key & Explanations ---
            # Same Dễ/Vừa/Khó label the web quiz badge shows — no internal "Bloom" jargon.
            difficulty_vn = {"easy": "Dễ", "medium": "Vừa", "hard": "Khó"}
            story.append(Paragraph("PHẦN 2: ĐÁP ÁN & GIẢI THÍCH CHI TIẾT (ANSWER KEY & EXPLANATIONS)", part_style))
            for q in quiz_data.questions:
                diff_str = getattr(q, "difficulty", "Medium") or "Medium"
                diff_label = difficulty_vn.get(diff_str.strip().lower(), diff_str)
                story.append(Paragraph(f"<b>Câu {q.question_number} ({diff_label}):</b> {prepare_pdf_text(q.question_text)}", q_style))
                story.append(Paragraph(f"<b>Đáp án đúng:</b> <font color='#16a34a'><b>{q.correct_answer}</b></font>", body_style))
                if q.explanation:
                    story.append(Paragraph(f"<b>Giải thích chi tiết:</b> {prepare_pdf_text(q.explanation)}", body_style))
                story.append(Spacer(1, 10))

            doc.build(story)
            logger.info(f"Generated Quiz Key PDF at {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error generating Quiz Key PDF: {e}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"Quiz Key Placeholder for {quiz_data.title}")
            return file_path

    def _generate_video_mp4(
        self,
        course_id: str,
        vid_data: VidOutput,
        fmt: str,
        voice: str,
        progress_cb=None,
        artifact_dir: Optional[str] = None,
        scene_visual_map: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> str:
        """Render the narrated MP4 (TTS + still frames + ffmpeg concat). Raises on failure — callers must treat that as a hard generation error, not
        write a placeholder file in its place (matches the strict invariant used by Book's PDF)."""
        from app.services.video_render import assemble_video

        artifact_dir = artifact_dir or self._get_artifact_dir(course_id)
        return assemble_video(
            vid_data,
            fmt,
            voice,
            artifact_dir,
            progress_cb=progress_cb,
            scene_visual_map=scene_visual_map,
        )

    def _resolve_course_pdf_path(self, course_id: str, source_file: str) -> Optional[str]:
        """Resolve a chunk's original filename to its timestamp-prefixed uploaded PDF."""
        safe_name = os.path.basename(source_file or "")
        if not safe_name.lower().endswith(".pdf"):
            return None
        course_dir = os.path.join(settings.UPLOAD_DIR, course_id)
        direct_path = os.path.join(course_dir, safe_name)
        if os.path.isfile(direct_path):
            return direct_path
        try:
            for name in os.listdir(course_dir):
                prefix, separator, original_name = name.partition("_")
                if separator and prefix.isdigit() and original_name == safe_name:
                    path = os.path.join(course_dir, name)
                    if os.path.isfile(path):
                        return path
        except OSError:
            return None
        return None

    def _build_scene_visual_map(self, course_id: str, vid_data: VidOutput) -> Dict[int, Dict[str, Any]]:
        """Select grounded PDF-page visuals for every other eligible middle video scene."""
        chunk_ids = [chunk_id for scene in vid_data.scenes for chunk_id in scene.source_chunk_ids]
        if not chunk_ids:
            return {}
        chunks = self.vector_store.get_course_chunks(course_id, list(dict.fromkeys(chunk_ids)))
        chunks_by_id = {str(chunk.metadata.get("chunk_id", "")): chunk for chunk in chunks}
        candidates: List[Dict[str, Any]] = []
        total_scenes = len(vid_data.scenes)
        for index, scene in enumerate(vid_data.scenes):
            if index == 0 or index == total_scenes - 1 or scene.diagram:
                continue
            for chunk_id in scene.source_chunk_ids:
                chunk = chunks_by_id.get(chunk_id)
                if not chunk:
                    continue
                pdf_path = self._resolve_course_pdf_path(course_id, str(chunk.metadata.get("source_file", "")))
                if not pdf_path:
                    continue
                try:
                    page = max(1, int(chunk.metadata.get("page", 1)))
                except (TypeError, ValueError):
                    page = 1
                candidates.append({"scene_number": scene.scene_number, "pdf_path": pdf_path, "page": page})
                break

        visual_map: Dict[int, Dict[str, Any]] = {}
        for visual_index, candidate in enumerate(candidates[::2]):
            visual_map[candidate["scene_number"]] = {
                "pdf_path": candidate["pdf_path"],
                "page": candidate["page"],
                "side": "left" if visual_index % 2 == 0 else "right",
            }
        return visual_map

    def _update_course_metadata(
        self,
        course_id: str,
        artifact_type: str,
        score: int,
        db_session_factory=None,
        quality_report: QualityReport | Dict[str, Any] | None = None,
    ):
        """Update course metadata_json and readiness flags in database."""
        version_id = self._generation_versions.get((course_id, artifact_type))
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                return

            meta = course.metadata_json or "{}"
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            study_pack = meta.get("study_pack", {})
            if version_id:
                artifacts = dict(study_pack.get("artifacts", {}))
                entry = dict(artifacts.get(artifact_type, {}))
                versions = dict(entry.get("versions", {}))
                if version_id in versions:
                    version = dict(versions[version_id])
                    version["quality_score"] = score
                    report_payload = _quality_report_payload(quality_report)
                    if report_payload is not None:
                        version["quality_report"] = report_payload
                    versions[version_id] = version
                    entry["versions"] = versions
                    artifacts[artifact_type] = entry
                    study_pack["artifacts"] = artifacts
            readiness = study_pack.get("readiness", {})
            quality_scores = study_pack.get("quality_scores", {})
            quality_reports = study_pack.get("quality_reports", {})
            grounding = study_pack.get("grounding", {"num_chunks": course.chunk_count, "quality_score": 0, "warnings": []})

            if artifact_type == "book":
                readiness["study_guide_pdf"] = True
                quality_scores["study_guide_pdf"] = score
                readiness_key = "study_guide_pdf"
            elif artifact_type == "slides":
                readiness["slides"] = True
                quality_scores["slides"] = score
                readiness_key = "slides"
            elif artifact_type == "quiz":
                readiness["quiz"] = True
                quality_scores["quiz"] = score
                readiness_key = "quiz"
            elif artifact_type == "vid":
                readiness["vid"] = True
                quality_scores["vid"] = score
                readiness_key = "vid"

            report_payload = _quality_report_payload(quality_report)
            if report_payload is not None:
                quality_reports[readiness_key] = report_payload


            # Update overall average score
            scores_list = [v for v in quality_scores.values() if v > 0]
            if scores_list:
                grounding["quality_score"] = sum(scores_list) // len(scores_list)
                course.quality_score = grounding["quality_score"]

            study_pack["readiness"] = readiness
            study_pack["quality_scores"] = quality_scores
            study_pack["quality_reports"] = quality_reports
            study_pack["grounding"] = grounding
            meta["study_pack"] = study_pack
            course.metadata_json = json.dumps(meta, ensure_ascii=False)
            db.commit()
            logger.info(f"Updated course {course_id} metadata for {artifact_type} with score {score}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating course metadata: {e}")
        finally:
            db.close()

    @staticmethod
    def _metadata_dict(course: Course) -> Dict[str, Any]:
        raw = course.metadata_json or "{}"
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    def prepare_artifact_version(
        self, course_id: str, artifact: str, options: Dict[str, Any], topic: Optional[str] = None,
        user_prompt: str = "", retry_version_id: Optional[str] = None, reserve: bool = True,
        db_session_factory=None, db_session: Optional[Session] = None,
    ) -> str:
        """Reserve a version slot and enforce per-artifact concurrency/caps."""
        owns_session = db_session is None
        db = db_session or self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                raise ValueError("Course not found")
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            study_pack = dict(meta.get("study_pack", {}))
            artifacts = dict(study_pack.get("artifacts", {}))
            entry = dict(artifacts.get(artifact, {}))
            versions = dict(entry.get("versions", {}))
            now = datetime.utcnow().isoformat()
            stale_minutes = {"book": 10, "vid": 20, "slides": 8, "quiz": 8}[artifact]
            for value in versions.values():
                if not isinstance(value, dict) or value.get("status") != "processing":
                    continue
                try:
                    age = datetime.utcnow() - datetime.fromisoformat(value.get("updated_at", ""))
                except (TypeError, ValueError):
                    age = None
                if age is None or age.total_seconds() <= stale_minutes * 60:
                    raise GenerationInFlightError()
                value.update({"status": "error", "error": "Tác vụ tạo đã hết thời gian chờ.", "finished_at": now, "updated_at": now})

            if retry_version_id:
                version_id = retry_version_id
                current = dict(versions.get(version_id, {}))
                if not current or current.get("status") != "error":
                    raise ValueError("Only an error version can be retried")
                options = dict(current.get("options", options))
                topic = current.get("topic", topic)
                user_prompt = current.get("user_prompt", user_prompt)
            else:
                version_id = version_slug(artifact, options)
                current = {}
            is_new = version_id not in versions
            if is_new and len(versions) >= VERSION_CAPS[artifact]:
                raise VersionCapReachedError(self._version_summaries(versions))
            label = current.get("label") or version_label(artifact, options)
            if is_new:
                existing_labels = {str(value.get("label", "")).casefold() for value in versions.values() if isinstance(value, dict)}
                base_label = label
                suffix = 2
                while label.casefold() in existing_labels:
                    label = f"{base_label} ({suffix})"
                    suffix += 1
            current.update({
                "options": dict(options), "label": label, "topic": topic,
                "user_prompt": user_prompt, "path": version_id, "status": "processing", "error": None,
                "progress": 0, "created_at": current.get("created_at", now), "started_at": now, "updated_at": now,
            })
            versions[version_id] = current
            artifacts[artifact] = {"active": entry.get("active"), "versions": versions}
            study_pack["artifacts"] = artifacts
            meta["study_pack"] = study_pack
            if reserve:
                if artifact == "book":
                    from app.services.provider_usage import ensure_book_budget
                    ensure_book_budget(db, course, version_id, retry=bool(retry_version_id))
                course.metadata_json = json.dumps(meta, ensure_ascii=False)
                if owns_session:
                    db.commit()
                else:
                    db.flush()
            return version_id
        except Exception:
            if owns_session:
                db.rollback()
            raise
        finally:
            if owns_session:
                db.close()

    def find_ready_book_version(
        self,
        course_id: str,
        options: Dict[str, Any],
        user_prompt: str = "",
        *,
        db_session: Optional[Session] = None,
        db_session_factory=None,
    ) -> Optional[str]:
        """Return an identical owned ready Book before admitting paid work."""

        from app.models.provider_call import BookBudget
        from app.services.book_model_policy import BookModelPolicy

        owns_session = db_session is None
        db = db_session or self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(
                Course.id == course_id, Course.is_deleted.is_(False)
            ).first()
            if course is None:
                return None
            owner_id = course.user_id
            try:
                source_digest, _context, evidence_ids = self._source_plan_inputs(
                    course_id, db_session_factory
                )
            except ValueError:
                return None
            expected_options_digest = book_options_digest(
                {"detail_level": options.get("detail_level"), "user_prompt": user_prompt}
            )
            expected_policy = BookModelPolicy.default()
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            versions = (
                meta.get("study_pack", {})
                .get("artifacts", {})
                .get("book", {})
                .get("versions", {})
            )
            for version_id, version in sorted(
                versions.items(),
                key=lambda item: str(item[1].get("created_at", "")),
                reverse=True,
            ):
                if (
                    not isinstance(version, dict)
                    or version.get("status") != "ready"
                    or version.get("options") != options
                    or str(version.get("user_prompt") or "") != user_prompt
                    or version.get("source_plan_digest") != source_digest
                ):
                    continue
                budget = db.query(BookBudget).filter_by(
                    course_id=course_id, version_id=version_id
                ).one_or_none()
                if (
                    budget is None
                    or budget.state != "active"
                    or not budget.allocation_digest
                ):
                    continue
                candidate_allocation_digest = budget.allocation_digest
                try:
                    policy = BookModelPolicy.model_validate(budget.model_policy)
                    if policy != expected_policy:
                        continue
                    identity = CheckpointIdentity(
                        course_id=course_id,
                        version_id=version_id,
                        source_digest=source_digest,
                        source_plan_revision=int(version.get("source_plan_revision")),
                        model=policy.model,
                        options_digest=expected_options_digest,
                        prompt_revision=BOOK_PROMPT_REVISION,
                        policy_revision=policy.revision,
                        budget_id=budget.id,
                    )
                except (TypeError, ValueError):
                    continue
                store = BookCheckpointStore(settings.UPLOAD_DIR, identity)
                ready_manifest = store.ready_manifest(
                    budget.allocation_digest, evidence_ids
                )
                if ready_manifest is None:
                    continue
                artifact_dir = Path(
                    artifact_directory_path(
                        settings.UPLOAD_DIR, course_id, "book", version_id
                    )
                )
                json_path = artifact_dir / "book.json"
                pdf_path = artifact_dir / "book.pdf"
                try:
                    cached_output = BookOutput.model_validate_json(
                        json_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError):
                    continue
                if (
                    len(cached_output.chapters) == len(ready_manifest.plan_digests)
                    and pdf_path.is_file()
                    and pdf_path.stat().st_size > 0
                ):
                    self._ready_cache_before_final_lock(course_id, version_id)
                    owner_query = db.query(Course).filter(
                        Course.id == course_id,
                        Course.user_id == owner_id,
                        Course.is_deleted.is_(False),
                    ).populate_existing()
                    if db.bind is not None and db.bind.dialect.name == "postgresql":
                        owner_query = owner_query.with_for_update()
                    fresh_course = owner_query.first()
                    if fresh_course is None:
                        continue
                    fresh_meta, _ = migrate_legacy_artifact_metadata(
                        self._metadata_dict(fresh_course)
                    )
                    fresh_version = (
                        fresh_meta.get("study_pack", {})
                        .get("artifacts", {})
                        .get("book", {})
                        .get("versions", {})
                        .get(version_id)
                    )
                    fresh_budget = (
                        db.query(BookBudget)
                        .populate_existing()
                        .filter_by(
                            id=budget.id,
                            course_id=course_id,
                            user_id=owner_id,
                            version_id=version_id,
                        )
                        .one_or_none()
                    )
                    if (
                        not isinstance(fresh_version, dict)
                        or fresh_version.get("status") != "ready"
                        or fresh_version.get("options") != options
                        or str(fresh_version.get("user_prompt") or "") != user_prompt
                        or fresh_version.get("source_plan_digest") != source_digest
                        or fresh_budget is None
                        or fresh_budget.state != "active"
                        or fresh_budget.allocation_digest != candidate_allocation_digest
                    ):
                        continue
                    try:
                        fresh_policy = BookModelPolicy.model_validate(
                            fresh_budget.model_policy
                        )
                        fresh_identity = CheckpointIdentity(
                            course_id=course_id,
                            version_id=version_id,
                            source_digest=source_digest,
                            source_plan_revision=int(
                                fresh_version.get("source_plan_revision")
                            ),
                            model=fresh_policy.model,
                            options_digest=expected_options_digest,
                            prompt_revision=BOOK_PROMPT_REVISION,
                            policy_revision=fresh_policy.revision,
                            budget_id=fresh_budget.id,
                        )
                    except (TypeError, ValueError):
                        continue
                    if fresh_policy == expected_policy and fresh_identity == identity:
                        return version_id
            return None
        finally:
            if owns_session:
                db.close()

    @staticmethod
    def _ready_cache_before_final_lock(_course_id: str, _version_id: str) -> None:
        """Test seam for races between private file validation and ownership lock."""

    @staticmethod
    def _version_summaries(versions: Dict[str, Any]) -> list[Dict[str, Any]]:
        summaries = []
        for key, value in versions.items():
            if not isinstance(value, dict):
                continue
            summary = {
                "version_id": key,
                "label": value.get("label", key),
                "options": value.get("options", {}),
                "status": value.get("status", "empty"),
                "created_at": value.get("created_at"),
            }
            quality_report = _quality_report_payload(value.get("quality_report"))
            if quality_report is not None:
                summary["quality_report"] = quality_report
            summaries.append(summary)
        return summaries

    def artifact_versions(self, course_id: str, artifact: str, db_session_factory=None) -> tuple[Optional[str], list[Dict[str, Any]]]:
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                return None, []
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            entry = meta.get("study_pack", {}).get("artifacts", {}).get(artifact, {})
            return entry.get("active"), self._version_summaries(entry.get("versions", {}))
        finally:
            db.close()

    def _set_artifact_status(
        self,
        course_id: str,
        artifact: str,
        status: str,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        technical_error: Optional[str] = None,
        progress: Optional[int] = None,
        quality_report: QualityReport | Dict[str, Any] | None = None,
        version_id: Optional[str] = None,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
        db_session_factory=None,
    ) -> bool:
        """Persist per-artifact generation status (processing/ready/error) into Course.metadata_json."""
        version_id = version_id or self._generation_versions.get((course_id, artifact))
        replacement_to_remove: Optional[str] = None
        db = self._get_db(db_session_factory)
        try:
            # SQLite ignores SELECT FOR UPDATE. Acquire its database write lock before
            # either representation is read so concurrent artifact updates cannot lose
            # one another's metadata entry.
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            effective_progress = progress
            if job_id:
                values = {"updated_at": datetime.utcnow()}
                if progress is not None:
                    bounded = max(0, min(99 if status == "processing" else 100, progress))
                    values["progress"] = case(
                        (ProcessingJob.progress > bounded, ProcessingJob.progress),
                        else_=bounded,
                    )
                guard = db.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.course_id == course_id,
                        ProcessingJob.status == JobStatus.RUNNING.value,
                        ProcessingJob.worker_id == worker_id,
                        ProcessingJob.attempts == attempt_number,
                        ProcessingJob.cancel_requested.is_(False),
                        ProcessingJob.lease_expires_at > datetime.utcnow(),
                    )
                    .values(**values)
                    .returning(ProcessingJob.progress)
                )
                guarded_progress = guard.scalar_one_or_none()
                if guarded_progress is None:
                    db.rollback()
                    return False
                if progress is not None:
                    effective_progress = guarded_progress
            course_query = db.query(Course).filter(Course.id == course_id)
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                course_query = course_query.with_for_update()
            course = course_query.first()
            if not course:
                return False

            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            study_pack = dict(meta.get("study_pack", {}))
            artifacts = dict(study_pack.get("artifacts", {}))
            entry = dict(artifacts.get(artifact, {}))
            if not version_id and entry.get("active") and isinstance(entry.get("versions"), dict):
                version_id = entry["active"]
            versions = dict(entry.get("versions", {})) if version_id else {}
            current = dict(versions.get(version_id, {})) if version_id else entry

            now = datetime.utcnow().isoformat()
            current["status"] = status
            current["error"] = error
            current["error_code"] = error_code
            current["technical_error"] = technical_error
            report_payload = _quality_report_payload(quality_report)
            if report_payload is not None:
                current["quality_report"] = report_payload
            if effective_progress is not None:
                current["progress"] = effective_progress
            if status == "processing" and "started_at" not in current:
                current["started_at"] = now
            if status in ("ready", "error"):
                current["finished_at"] = now
            current["updated_at"] = now
            if version_id:
                versions[version_id] = current
                if status == "ready":
                    entry["active"] = version_id
                entry["versions"] = versions
            else:
                entry = current

            artifacts[artifact] = entry
            study_pack["artifacts"] = artifacts
            meta["study_pack"] = study_pack
            course.metadata_json = json.dumps(meta, ensure_ascii=False)
            db.commit()
            if replacement_to_remove:
                try:
                    remove_artifact_version(settings.UPLOAD_DIR, course_id, artifact, replacement_to_remove)
                except OSError as exc:
                    logger.warning(
                        "Could not remove replaced %s artifact %s for course %s: %s",
                        artifact,
                        replacement_to_remove,
                        course_id,
                        exc,
                    )
            if version_id and status in ("ready", "error"):
                self._generation_versions.pop((course_id, artifact), None)
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error setting artifact status for {artifact}: {e}")
            return False
        finally:
            db.close()

    def rename_artifact_version(self, course_id: str, artifact: str, version_id: str, label: str, db_session_factory=None) -> Dict[str, Any]:
        label = label.strip()
        if not 1 <= len(label) <= 40:
            raise ValueError("Tên phiên bản phải dài từ 1 đến 40 ký tự")
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                raise ValueError("Course not found")
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            entry = meta.get("study_pack", {}).get("artifacts", {}).get(artifact, {})
            versions = dict(entry.get("versions", {}))
            current = dict(versions.get(version_id, {}))
            if not current:
                raise ValueError("Version not found")
            if any(v.get("label", "").casefold() == label.casefold() for key, v in versions.items() if key != version_id):
                raise ValueError("Tên phiên bản đã tồn tại")
            current["label"] = label
            current["updated_at"] = datetime.utcnow().isoformat()
            versions[version_id] = current
            entry["versions"] = versions
            study_pack = meta["study_pack"]
            study_pack["artifacts"][artifact] = entry
            study_pack["quality_reports"] = _active_quality_report_payloads(study_pack)
            course.metadata_json = json.dumps(meta, ensure_ascii=False)
            db.commit()
            return {"version_id": version_id, "label": label}
        finally:
            db.close()

    def delete_artifact_version(self, course_id: str, artifact: str, version_id: str, db_session_factory=None) -> None:
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                raise ValueError("Course not found")
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            entry = dict(meta.get("study_pack", {}).get("artifacts", {}).get(artifact, {}))
            versions = dict(entry.get("versions", {}))
            current = versions.get(version_id)
            if not current:
                raise ValueError("Version not found")
            if current.get("status") == "processing":
                raise GenerationInFlightError()
            versions.pop(version_id)
            if entry.get("active") == version_id:
                candidates = sorted(versions.items(), key=lambda item: item[1].get("created_at", ""), reverse=True)
                ready = next((key for key, value in candidates if value.get("status") == "ready"), None)
                error = next((key for key, value in candidates if value.get("status") == "error"), None)
                entry["active"] = ready or error
            entry["versions"] = versions
            meta["study_pack"]["artifacts"][artifact] = entry
            course.metadata_json = json.dumps(meta, ensure_ascii=False)
            if artifact == "book":
                from app.models.provider_call import BookBudget
                db.query(BookBudget).filter(BookBudget.course_id == course_id, BookBudget.version_id == version_id).update({"state": "closed"})
            db.commit()
        finally:
            db.close()
        remove_artifact_version(settings.UPLOAD_DIR, course_id, artifact, version_id)
        if artifact == "book":
            remove_book_checkpoints(settings.UPLOAD_DIR, course_id, version_id)

    def get_artifact_status(self, course_id: str, artifact: str, version_id: Optional[str] = None, db_session_factory=None) -> Dict[str, Any]:
        """Read per-artifact generation status from Course.metadata_json."""
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                return {}
            meta, _ = migrate_legacy_artifact_metadata(self._metadata_dict(course))
            entry = meta.get("study_pack", {}).get("artifacts", {}).get(artifact, {})
            if not isinstance(entry, dict) or "versions" not in entry:
                return entry if isinstance(entry, dict) else {}
            return dict(entry.get("versions", {}).get(version_id or entry.get("active"), {}))
        finally:
            db.close()

    def _resolve_topic(self, course_id: str, topic: Optional[str] = None, db_session_factory=None) -> str:
        """Resolve actual course/document topic if topic is missing or hardcoded generic AI string."""
        ignore_list = ["AI Quiz", "AI Overview", "AI Video", "AI Course", "General Students", ""]
        if topic and str(topic).strip() and str(topic).strip() not in ignore_list:
            return str(topic).strip()

        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if course and course.name and course.name.strip():
                return course.name.strip()
            if course and course.filenames and len(course.filenames) > 0:
                fn = str(course.filenames[0])
                for ext in [".pdf", ".docx", ".txt", ".PPTX", ".PDF", ".DOCX", ".TXT"]:
                    if fn.lower().endswith(ext.lower()):
                        fn = fn[:-len(ext)]
                fn = _strip_leading_id_token(fn.strip())
                if fn.strip():
                    return fn.strip()
            if course and course.metadata_json:
                try:
                    meta = json.loads(course.metadata_json) if isinstance(course.metadata_json, str) else course.metadata_json
                    if isinstance(meta, dict) and meta.get("title"):
                        return str(meta["title"]).strip()
                except Exception:
                    pass
        finally:
            db.close()
        return "Nội dung tài liệu chính"

    def _get_doc_names(self, course_id: str, db_session_factory=None) -> str:
        """Fetch the course's source document filenames as a comma-separated string."""
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            if course and course.filenames:
                return ", ".join(str(fn) for fn in course.filenames)
            return ""
        finally:
            db.close()

    @staticmethod
    def _chapter_content_to_book_chapter(
        content: BookChapterContent, plan: BookChapterPlan
    ) -> BookChapter:
        return BookChapter(
            chapter_title=content.chapter_title or plan.chapter_title,
            introduction=content.introduction,
            objectives=content.objectives,
            sections=content.sections,
            key_points=content.key_points,
            review_questions=content.review_questions,
            source_chunk_ids=content.source_chunk_ids,
        )

    def _run_book_chapter_task(
        self,
        book_llm,
        task: _BookChapterTask,
        provider_context,
    ) -> tuple[int, BookChapterContent]:
        with usage_context(
            dataclass_replace(
                provider_context,
                stage="chapter",
                chapter=task.index + 1,
            )
        ), stage_timer("chapter", task.index + 1):
            chapter_args = (
                task.book_title,
                task.plan,
                task.total,
                task.context,
                task.detail_level,
                list(task.valid_chunk_ids),
            )
            if isinstance(book_llm, LLMService) and getattr(
                book_llm, "book_policy", None
            ) is not None:
                content = book_llm.generate_book_chapter(
                    *chapter_args,
                    max_output_tokens=task.max_output_tokens,
                    reasoning_tokens=task.reasoning_tokens,
                    required_objectives=task.required_objectives,
                )
            else:
                content = book_llm.generate_book_chapter(
                    *chapter_args,
                    required_objectives=task.required_objectives,
                )
        return task.index, content

    def _generate_book_chapters_bounded(
        self,
        *,
        book_llm,
        outline: BookOutline,
        plans: list[BookChapterPlan],
        source_plan: SourcePlan,
        chapter_budgets,
        chapter_contexts,
        cached_chapter_contents: list[BookChapterContent | None],
        chapter_request_estimates,
        checkpoint_store,
        checkpoint_fence,
        outline_digest: str,
        allocation_digest: str,
        checkpoint_plan_digests: list[str],
        detail_level: str,
        progress_callback: Optional[Callable[[], bool]],
        set_progress: Callable[[int], bool],
        capacity_check: Callable[[list[Any], Any], None],
    ) -> tuple[list[BookChapter], set[str], dict[int, list[str]]]:
        total = len(plans)
        provider_context = current_provider_context()
        completed: list[BookChapterContent | None] = list(cached_chapter_contents)
        all_ids: set[str] = set()
        chapter_evidence: dict[int, list[str]] = {}
        for index, (_context, evidence_ids) in enumerate(chapter_contexts):
            all_ids.update(evidence_ids)
            chapter_evidence[index] = list(evidence_ids)

        missing = [index for index, item in enumerate(completed) if item is None]
        if not missing:
            return (
                [
                    self._chapter_content_to_book_chapter(content, plan)
                    for content, plan in zip(completed, plans)
                    if content is not None
                ],
                all_ids,
                chapter_evidence,
            )

        cap = max(1, min(settings.BOOK_CHAPTER_CONCURRENCY, total))
        if provider_context.job_id:
            try:
                from app.services import database as database_service

                bind = database_service.SessionLocal.kw.get("bind")
                if bind is not None and bind.dialect.name == "sqlite":
                    cap = 1
            except Exception:
                pass
        executor = ThreadPoolExecutor(max_workers=cap, thread_name_prefix="book-chapter")
        active = {}
        next_missing = 0
        completed_count = total - len(missing)
        aborted = False

        def submit_available() -> None:
            nonlocal next_missing
            while len(active) < cap and next_missing < len(missing):
                index = missing[next_missing]
                if chapter_request_estimates:
                    remaining = [
                        chapter_request_estimates[pending]
                        for pending in missing[next_missing:]
                    ]
                    capacity_check(remaining, chapter_request_estimates[index])
                self._report_progress(progress_callback)
                unit = source_plan.units[index]
                chapter_budget = chapter_budgets[index]
                if unit.id != chapter_budget.unit_id:
                    raise BookCoverageInfeasible(
                        "Chapter allocation no longer matches the source plan"
                    )
                ch_context, ch_ids = chapter_contexts[index]
                required_objectives = dict(
                    zip(
                        chapter_budget.objective_ids,
                        chapter_budget.expected_learning_objectives,
                    )
                )
                task = _BookChapterTask(
                    index=index,
                    book_title=outline.title,
                    plan=plans[index],
                    total=total,
                    context=ch_context,
                    valid_chunk_ids=tuple(ch_ids),
                    detail_level=detail_level,
                    max_output_tokens=(
                        chapter_budget.max_tokens
                        if isinstance(book_llm, LLMService)
                        and getattr(book_llm, "book_policy", None) is not None
                        else None
                    ),
                    reasoning_tokens=(
                        chapter_budget.reasoning_allowance
                        if isinstance(book_llm, LLMService)
                        and getattr(book_llm, "book_policy", None) is not None
                        else None
                    ),
                    required_objectives=required_objectives,
                )
                future = executor.submit(self._run_book_chapter_task, book_llm, task, provider_context)
                active[future] = index
                next_missing += 1

        try:
            submit_available()
            while active:
                done, _pending = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    index = active.pop(future)
                    try:
                        result_index, content = future.result()
                    except Exception:
                        aborted = True
                        for pending in active:
                            pending.cancel()
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise
                    if result_index != index:
                        raise RuntimeError("Book chapter worker returned the wrong index")
                    ch_ids = list(chapter_contexts[index][1])
                    required_objectives = dict(
                        zip(
                            chapter_budgets[index].objective_ids,
                            chapter_budgets[index].expected_learning_objectives,
                        )
                    )
                    validate_book_chapter_completion(
                        content,
                        valid_chunk_ids=ch_ids,
                        required_objectives=required_objectives,
                    )
                    if checkpoint_store and not checkpoint_store.save_chapter(
                        index,
                        content,
                        outline_digest=outline_digest,
                        allocation_digest=allocation_digest,
                        expected_plan_digest=checkpoint_plan_digests[index],
                        evidence_ids=ch_ids,
                        fence=checkpoint_fence,
                    ):
                        raise _GenerationInterrupted
                    completed[index] = content
                    completed_count += 1
                    progress = 15 + int(75 * completed_count / total)
                    self._report_progress(progress_callback)
                    if not set_progress(progress):
                        raise _GenerationInterrupted
                submit_available()
        finally:
            if not aborted:
                executor.shutdown(wait=True, cancel_futures=True)

        if any(item is None for item in completed):
            raise _GenerationInterrupted
        return (
            [
                self._chapter_content_to_book_chapter(content, plan)
                for content, plan in zip(completed, plans)
                if content is not None
            ],
            all_ids,
            chapter_evidence,
        )

    def _get_doc_name_list(self, course_id: str, db_session_factory=None) -> List[str]:
        """Fetch ordered source filenames for bounded Book-outline coverage retrieval."""

        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            return [str(name) for name in (course.filenames or [])] if course else []
        finally:
            db.close()

    @book_usage
    def generate_book(
        self,
        course_id: str,
        detail_level: str = "Tiêu chuẩn",
        user_prompt: str = "",
        db_session_factory=None,
        progress_callback: Optional[Callable[[], bool]] = None,
        **kwargs,
    ) -> Optional[BookOutput]:
        """Execute the multi-pass generation pipeline for the Study Guide Book:
        outline pass -> one LLM call per chapter (with per-chapter retrieval) -> assemble -> validate -> PDF.

        On any failure, records an "error" artifact status and returns None instead of writing a
        partial/placeholder artifact.
        """
        logger.info(f"Starting Book generation for course {course_id}")
        version_id = kwargs.get("version_id")
        ready, output = self._ready_version_output(
            course_id, "book", "book.json", version_id, BookOutput, db_session_factory
        )
        if ready:
            return output
        execution_token = kwargs.get("execution_token")
        job_id = kwargs.get("job_id")
        worker_id = kwargs.get("worker_id")
        attempt_number = kwargs.get("attempt_number")
        status_fence = {
            "job_id": job_id,
            "worker_id": worker_id,
            "attempt_number": attempt_number,
        }
        transaction, artifact_dir = self._start_version_write(
            course_id, "book", version_id, execution_token=execution_token
        )
        try:
            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "book", "processing", progress=5, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._require_course_not_processing(course_id, db_session_factory)

            book_llm = self._llm_for("book")
            if version_id:
                from app.services.provider_usage import (
                    get_book_model_policy,
                    require_estimated_book_capacity,
                )

                policy_db = self._get_db(db_session_factory)
                try:
                    policy = get_book_model_policy(policy_db, course_id, version_id)
                finally:
                    policy_db.close()
                binder = getattr(book_llm, "with_book_policy", None)
                if binder is None:
                    raise BudgetLimitError("Book LLM cannot honor the saved model policy")
                book_llm = binder(policy)

            total_output = {
                "tóm tắt": 14_000,
                "tiêu chuẩn": 20_000,
                "chuyên sâu": 24_000,
            }.get(detail_level.strip().casefold(), 20_000)
            total_input = {
                "tóm tắt": 60_000,
                "tiêu chuẩn": 40_000,
                "chuyên sâu": 30_000,
            }.get(detail_level.strip().casefold(), 40_000)
            outline_tokens = outline_output_allowance(detail_level, total_output)
            outline_reasoning = getattr(
                getattr(book_llm, "book_policy", None), "reasoning_budget", 512
            )

            def require_capacity(requests, *, retry_request=None, residual_usd=Decimal("0")):
                if not version_id:
                    return
                capacity_db = self._get_db(db_session_factory)
                try:
                    require_estimated_book_capacity(
                        capacity_db,
                        course_id,
                        version_id,
                        requests,
                        retry_request=retry_request,
                        residual_usd=residual_usd,
                    )
                finally:
                    capacity_db.close()

            source_plan_estimate = None
            if isinstance(book_llm, LLMService) and getattr(
                book_llm, "book_policy", None
            ) is not None:
                from app.services.provider_usage import estimate_call_usd

                source_digest, source_context, source_ids = self._source_plan_inputs(
                    course_id, db_session_factory
                )
                self._source_plan_contexts[(course_id, source_digest)] = (
                    source_context,
                    source_ids,
                )
                source_plan_output = min(4_000, 1_800 + 200 * len(source_ids))
                source_plan_revision = source_plan_request_revision(
                    course_id,
                    source_digest,
                    book_llm.book_policy.model,
                    SOURCE_PLAN_PROMPT_REVISION,
                    db_session_factory=db_session_factory,
                )
                source_plan_estimate = book_llm.estimate_source_plan_request(
                    source_context,
                    source_digest,
                    source_plan_revision,
                    source_plan_output,
                    outline_reasoning,
                )
                residual_usd = estimate_call_usd(
                    total_input,
                    total_output,
                    book_llm.book_policy.input_price_ceiling,
                    book_llm.book_policy.output_price_ceiling,
                )
                plan_db = self._get_db(db_session_factory)
                try:
                    source_plan_is_cached = plan_db.query(SourcePlanRecord.id).filter_by(
                        course_id=course_id,
                        source_digest=source_digest,
                        model=book_llm.book_policy.model,
                        prompt_revision=SOURCE_PLAN_PROMPT_REVISION,
                    ).first() is not None
                finally:
                    plan_db.close()
                if not source_plan_is_cached:
                    require_capacity(
                        [source_plan_estimate],
                        retry_request=source_plan_estimate,
                        residual_usd=residual_usd,
                    )
            with stage_timer("retrieving"):
                source_plan = self._get_source_plan(
                    course_id,
                    "book",
                    db_session_factory,
                    selected_llm=book_llm,
                )
                context, base_ids, plan_units = self._plan_context(
                    course_id, source_plan, all_units=True
                )
                provisional_budgets = allocate_book_budget(
                    source_plan,
                    available_input_tokens=10_000_000,
                    available_output_tokens=(
                        total_output - outline_tokens - outline_reasoning
                    ),
                    detail_level=detail_level,
                )
                objectives = {item.id: item.text for item in source_plan.objectives}
                provisional_plans = [
                    BookChapterPlan(
                        chapter_number=index + 1,
                        chapter_title=unit.title,
                        description="; ".join(
                            objectives[item] for item in unit.objective_ids
                        ),
                        retrieval_query=unit.title,
                        planned_sections=[objectives[item] for item in unit.objective_ids],
                    )
                    for index, unit in enumerate(source_plan.units)
                ]
                chapter_contexts = []
                for unit, budget in zip(source_plan.units, provisional_budgets):
                    chapter_contexts.append(
                        self._plan_context(
                            course_id,
                            source_plan,
                            unit_ids=[unit.id],
                            evidence_ids_override=list(budget.evidence_ids),
                        )[:2]
                    )
                if isinstance(book_llm, LLMService) and getattr(
                    book_llm, "book_policy", None
                ) is not None:
                    raw_source_context, raw_source_ids = self._source_plan_contexts[
                        (course_id, source_plan.source_digest)
                    ]
                    source_plan_output = min(
                        4_000, 1_800 + 200 * len(raw_source_ids)
                    )
                    source_plan_estimate = book_llm.estimate_source_plan_request(
                        raw_source_context,
                        source_plan.source_digest,
                        source_plan.revision,
                        source_plan_output,
                        outline_reasoning,
                    )
                    outline_estimate = book_llm.estimate_book_outline_request(
                        context,
                        detail_level,
                        user_prompt,
                        self._get_doc_names(course_id, db_session_factory),
                        outline_tokens,
                        outline_reasoning,
                    )
                    measured_inputs = {}
                    chapter_estimates = []
                    for plan, budget, (unit_context, _ids) in zip(
                        provisional_plans, provisional_budgets, chapter_contexts
                    ):
                        estimate = book_llm.estimate_book_chapter_request(
                            "Sách ôn tập theo Source Plan",
                            plan,
                            len(provisional_plans),
                            unit_context,
                            detail_level,
                            budget.visible_output_allowance,
                            budget.reasoning_allowance,
                            dict(
                                zip(
                                    budget.objective_ids,
                                    budget.expected_learning_objectives,
                                )
                            ),
                        )
                        if estimate.output_bound != budget.output_bound:
                            raise BookCoverageInfeasible(
                                "Provider output reservation disagrees with chapter allocation"
                            )
                        measured_inputs[budget.unit_id] = estimate.input_bound + 512
                        chapter_estimates.append(estimate)
                    remaining_input = (
                        total_input
                        - source_plan_estimate.input_bound
                        - outline_estimate.input_bound
                    )
                    chapter_budgets = allocate_book_budget(
                        source_plan,
                        available_input_tokens=remaining_input,
                        available_output_tokens=(
                            total_output - outline_tokens - outline_reasoning
                        ),
                        detail_level=detail_level,
                        measured_input_bounds=measured_inputs,
                    )
                    from app.services.provider_usage import CEILING

                    planned_upper = (
                        source_plan_estimate.upper_bound_usd
                        + outline_estimate.upper_bound_usd
                        + sum(item.upper_bound_usd for item in chapter_estimates)
                        + outline_estimate.upper_bound_usd
                    )
                    if planned_upper > CEILING:
                        raise BookCoverageInfeasible(
                            "Estimated complete Book plan exceeds the financial envelope"
                        )
                else:
                    chapter_budgets = provisional_budgets
                allocation_payload = [item.model_dump(mode="json") for item in chapter_budgets]
                allocation_digest = hashlib.sha256(
                    json.dumps(allocation_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                if version_id:
                    from app.services.provider_usage import save_book_allocation_digest

                    allocation_db = self._get_db(db_session_factory)
                    try:
                        save_book_allocation_digest(
                            allocation_db, course_id, version_id, allocation_digest
                        )
                        allocation_db.commit()
                    finally:
                        allocation_db.close()
                self._bind_version_to_plan(
                    course_id, "book", version_id, source_plan, db_session_factory,
                    selected_model=getattr(book_llm, "model", settings.OPENROUTER_MODEL),
                )
            self._require_context(context)
            checkpoint_store = None
            checkpoint_fence = None
            if version_id:
                from app.models.provider_call import BookBudget
                from app.services import database as database_service

                identity_db = self._get_db(db_session_factory)
                try:
                    budget = identity_db.query(BookBudget).filter_by(
                        course_id=course_id, version_id=version_id
                    ).one_or_none()
                    if budget is None or budget.allocation_digest != allocation_digest:
                        raise BudgetLimitError("Book checkpoint budget identity is unavailable")
                    checkpoint_identity = CheckpointIdentity(
                        course_id=course_id,
                        version_id=version_id,
                        source_digest=source_plan.source_digest,
                        source_plan_revision=source_plan.revision,
                        model=getattr(book_llm, "model", settings.OPENROUTER_MODEL),
                        options_digest=book_options_digest(
                            {"detail_level": detail_level, "user_prompt": user_prompt}
                        ),
                        prompt_revision=BOOK_PROMPT_REVISION,
                        policy_revision=getattr(
                            getattr(book_llm, "book_policy", None), "revision", "legacy"
                        ),
                        budget_id=budget.id,
                    )
                finally:
                    identity_db.close()
                checkpoint_store = BookCheckpointStore(settings.UPLOAD_DIR, checkpoint_identity)
                checkpoint_fence = checkpoint_write_fence(
                    db_session_factory or database_service.SessionLocal,
                    checkpoint_identity,
                    job_id=job_id,
                    worker_id=worker_id,
                    attempt_number=attempt_number,
                )

            proposed_outline = (
                checkpoint_store.load_outline(base_ids) if checkpoint_store else None
            )
            if proposed_outline is None:
                if (
                    isinstance(book_llm, LLMService)
                    and getattr(book_llm, "book_policy", None) is not None
                ):
                    require_capacity(
                        [outline_estimate, *chapter_estimates],
                        retry_request=outline_estimate,
                    )
                with stage_timer("outline"):
                    outline_args = (
                        context,
                        detail_level,
                        user_prompt,
                        self._get_doc_names(course_id, db_session_factory),
                    )
                    if isinstance(book_llm, LLMService):
                        proposed_outline = book_llm.generate_book_outline(
                            *outline_args,
                            max_output_tokens=outline_tokens,
                            reasoning_tokens=outline_reasoning,
                        )
                    else:
                        proposed_outline = book_llm.generate_book_outline(*outline_args)
                if (
                    len(proposed_outline.chapters) != len(source_plan.units)
                    and not getattr(book_llm, "_test_mode", False)
                ):
                    raise BookCoverageInfeasible("Outline omitted a planned source unit")
                proposed_outline = BookOutline(
                    title=proposed_outline.title,
                    summary=proposed_outline.summary,
                    preface=proposed_outline.preface,
                    chapters=[
                        BookChapterPlan(
                            chapter_number=index + 1,
                            chapter_title=unit.title,
                            description=(
                                proposed_outline.chapters[index].description
                                if index < len(proposed_outline.chapters)
                                else objectives.get(unit.objective_ids[0], unit.title)
                            ),
                            retrieval_query=unit.title,
                            planned_sections=(
                                proposed_outline.chapters[index].planned_sections
                                if index < len(proposed_outline.chapters)
                                else [objectives.get(unit.objective_ids[0], unit.title)]
                            ),
                        )
                        for index, unit in enumerate(source_plan.units)
                    ],
                )
                if checkpoint_store and not checkpoint_store.save_outline(
                    proposed_outline, list(base_ids), checkpoint_fence
                ):
                    raise _GenerationInterrupted
            if len(proposed_outline.chapters) != len(source_plan.units):
                raise BookCoverageInfeasible("Checkpointed outline omitted a planned source unit")
            outline = proposed_outline
            plans = outline.chapters
            if len(plans) != len(chapter_budgets):
                raise BookCoverageInfeasible("Outline omitted a planned source unit")

            outline_digest = canonical_digest(outline.model_dump(mode="json"))
            checkpoint_plan_digests = [checkpoint_plan_digest(plan) for plan in plans]
            manifest = None
            if checkpoint_store:
                manifest = checkpoint_store.load_manifest(
                    outline_digest=outline_digest,
                    allocation_digest=allocation_digest,
                    plan_digests=checkpoint_plan_digests,
                    valid_evidence_ids=base_ids,
                )
                if manifest is None and not checkpoint_store.save_manifest(
                    outline_digest=outline_digest,
                    allocation_digest=allocation_digest,
                    plans=plans,
                    evidence_ids=list(base_ids),
                    fence=checkpoint_fence,
                ):
                    raise _GenerationInterrupted

            chapter_request_estimates = []
            if isinstance(book_llm, LLMService) and getattr(
                book_llm, "book_policy", None
            ) is not None:
                for plan, chapter_budget, (chapter_context, _ids) in zip(
                    plans, chapter_budgets, chapter_contexts
                ):
                    estimate = book_llm.estimate_book_chapter_request(
                        outline.title,
                        plan,
                        len(plans),
                        chapter_context,
                        detail_level,
                        chapter_budget.visible_output_allowance,
                        chapter_budget.reasoning_allowance,
                        dict(
                            zip(
                                chapter_budget.objective_ids,
                                chapter_budget.expected_learning_objectives,
                            )
                        ),
                    )
                    if (
                        estimate.input_bound > chapter_budget.input_bound
                        or estimate.output_bound != chapter_budget.output_bound
                    ):
                        raise BookCoverageInfeasible(
                            "Final chapter request exceeds its measured allocation"
                        )
                    chapter_request_estimates.append(estimate)
            cached_chapter_contents: list[BookChapterContent | None] = [
                None for _ in plans
            ]
            if checkpoint_store:
                for index, (chapter_budget, (_context, evidence_ids)) in enumerate(
                    zip(chapter_budgets, chapter_contexts)
                ):
                    assigned_objectives = dict(
                        zip(
                            chapter_budget.objective_ids,
                            chapter_budget.expected_learning_objectives,
                        )
                    )

                    def validate_saved(
                        value: BookChapterContent,
                        *,
                        valid_ids=evidence_ids,
                        required=assigned_objectives,
                    ) -> None:
                        validate_book_chapter_completion(
                            value,
                            valid_chunk_ids=valid_ids,
                            required_objectives=required,
                        )

                    cached_chapter_contents[index] = checkpoint_store.load_chapter(
                        index,
                        outline_digest=outline_digest,
                        allocation_digest=allocation_digest,
                        expected_plan_digest=checkpoint_plan_digests[index],
                        valid_evidence_ids=evidence_ids,
                        validator=validate_saved,
                    )
            if chapter_request_estimates:
                missing_estimates = [
                    estimate
                    for estimate, cached in zip(
                        chapter_request_estimates, cached_chapter_contents
                    )
                    if cached is None
                ]
                if missing_estimates:
                    require_capacity(
                        missing_estimates,
                        retry_request=missing_estimates[0],
                    )

            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "book", "processing", progress=15, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted

            chapters, chapter_ids, chapter_evidence = self._generate_book_chapters_bounded(
                book_llm=book_llm,
                outline=outline,
                plans=plans,
                source_plan=source_plan,
                chapter_budgets=chapter_budgets,
                chapter_contexts=chapter_contexts,
                cached_chapter_contents=cached_chapter_contents,
                chapter_request_estimates=chapter_request_estimates,
                checkpoint_store=checkpoint_store,
                checkpoint_fence=checkpoint_fence,
                outline_digest=outline_digest,
                allocation_digest=allocation_digest,
                checkpoint_plan_digests=checkpoint_plan_digests,
                detail_level=detail_level,
                progress_callback=progress_callback,
                set_progress=lambda progress: self._set_artifact_status(
                    course_id,
                    "book",
                    "processing",
                    progress=progress,
                    db_session_factory=db_session_factory,
                    **status_fence,
                ),
                capacity_check=lambda requests, retry_request: require_capacity(
                    requests,
                    retry_request=retry_request,
                ),
            )
            all_ids = set(base_ids)
            all_ids.update(chapter_ids)

            book = BookOutput(title=outline.title, summary=outline.summary, preface=outline.preface, chapters=chapters)
            self._enforce_canonical_consistency(book, "book", source_plan, plan_units)
            validated_output, report, warnings = validate_and_score_output(
                book,
                "book",
                list(all_ids),
                unit_valid_chunk_ids=chapter_evidence,
            )
            score = report.structural_validity
            if warnings:
                logger.warning(f"Book generation warnings for {course_id}: {warnings}")

            with stage_timer("exporting"):
                self._save_artifact_json(
                    course_id, "book.json",
                    self._artifact_with_plan(
                        validated_output, source_plan, [unit.id for unit in plan_units]
                    ),
                    artifact_dir,
                )
                self._generate_pdf_book(course_id, validated_output, artifact_dir)
            if not job_id:
                self._update_course_metadata(
                    course_id, "book", score, db_session_factory, quality_report=report
                )
            self._report_progress(progress_callback)
            if not self._publish_ready_version(
                transaction,
                course_id=course_id,
                artifact="book",
                version_id=version_id,
                job_id=job_id,
                worker_id=worker_id,
                attempt_number=attempt_number,
                score=score,
                quality_report=report,
                db_session_factory=db_session_factory,
            ):
                raise _GenerationInterrupted
            return validated_output
        except _GenerationInterrupted:
            self._finish_version_write(transaction, False)
            return None
        except SoftTimeLimitExceeded:
            self._finish_version_write(transaction, False)
            raise
        except BudgetLimitError:
            self._finish_version_write(transaction, False)
            self._set_artifact_status(course_id, "book", "error",
                error="Tác vụ đã dừng ở giới hạn chi phí an toàn.", error_code="BOOK_BUDGET_LIMIT",
                db_session_factory=db_session_factory, **status_fence)
            raise
        except BookCoverageInfeasible as exc:
            self._finish_version_write(transaction, False)
            self._set_artifact_status(
                course_id,
                "book",
                "error",
                error="Phạm vi sách đã chọn không thể bao quát đầy đủ trong giới hạn chi phí.",
                error_code="BOOK_SCOPE_INFEASIBLE",
                technical_error=str(exc)[:1000],
                db_session_factory=db_session_factory,
                **status_fence,
            )
            return None
        except BookIncompleteError as exc:
            self._finish_version_write(transaction, False)
            self._set_artifact_status(
                course_id,
                "book",
                "error",
                error="Chương sách chưa hoàn chỉnh và không được công bố.",
                error_code="BOOK_INCOMPLETE_BUDGET",
                technical_error=str(exc)[:1000],
                db_session_factory=db_session_factory,
                **status_fence,
            )
            return None
        except ProviderCircuitOpen:
            self._finish_version_write(transaction, False)
            raise
        except Exception as e:
            self._finish_version_write(transaction, False)
            logger.error(f"Book generation failed for course {course_id}: {e}", exc_info=True)
            self._set_artifact_status(
                course_id,
                "book",
                "error",
                error=(self._NO_CONTEXT_MSG if str(e) == self._NO_CONTEXT_MSG else "Không thể tạo sách ôn tập. Vui lòng thử lại."),
                error_code=("ARTIFACT_SOURCE_UNAVAILABLE" if str(e) == self._NO_CONTEXT_MSG else "BOOK_GENERATION_FAILED"),
                technical_error=str(e)[:1000],
                db_session_factory=db_session_factory,
                **status_fence,
            )
            return None

    def generate_slides(self, course_id: str, topic: str = "AI Overview", num_slides: int = 15, focus_prompt: str = "", db_session_factory=None, progress_callback: Optional[Callable[[], bool]] = None, **kwargs) -> Optional[SlidesOutput]:
        """Execute full generation pipeline for Presentation Slides.

        On any failure, records an "error" artifact status and returns None instead of
        letting a background-task exception vanish silently.
        """
        logger.info(f"Starting Slides generation for course {course_id}")
        version_id = kwargs.get("version_id")
        ready, output = self._ready_version_output(
            course_id, "slides", "slides.json", version_id, SlidesOutput, db_session_factory
        )
        if ready:
            return output
        execution_token = kwargs.get("execution_token")
        job_id = kwargs.get("job_id")
        worker_id = kwargs.get("worker_id")
        attempt_number = kwargs.get("attempt_number")
        status_fence = {
            "job_id": job_id,
            "worker_id": worker_id,
            "attempt_number": attempt_number,
        }
        transaction, artifact_dir = self._start_version_write(
            course_id, "slides", version_id, execution_token=execution_token
        )
        try:
            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "slides", "processing", progress=10, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._require_course_not_processing(course_id, db_session_factory)
            resolved_topic = self._resolve_topic(course_id, topic, db_session_factory=db_session_factory)
            slides_llm = self._llm_for("slides")
            source_plan = self._get_source_plan(
                course_id,
                "slides",
                db_session_factory,
                selected_llm=slides_llm,
            )
            context, valid_chunk_ids, plan_units = self._plan_context(
                course_id, source_plan, topic=resolved_topic
            )
            self._bind_version_to_plan(
                course_id, "slides", version_id, source_plan, db_session_factory,
                selected_model=getattr(slides_llm, "model", settings.OPENROUTER_MODEL),
            )
            self._require_context(context)
            focus = f"\nTrọng tâm mong muốn: {focus_prompt}" if focus_prompt.strip() else ""
            raw_output = slides_llm.generate_slides(context + focus, resolved_topic, num_slides, valid_chunk_ids)
            raw_output = _repair_flattened_array_indices(raw_output, context, "slides")
            raw_output = _clean_slides_output(raw_output)
            assigned_units = [
                plan_units[i % len(plan_units)] for i in range(len(raw_output.slides))
            ]
            self._enforce_canonical_consistency(raw_output, "slides", source_plan, assigned_units)
            item_evidence = {
                i: unit.evidence_ids for i, unit in enumerate(assigned_units)
            }
            validated_output, report, warnings = validate_and_score_output(
                raw_output, "slides", valid_chunk_ids, unit_valid_chunk_ids=item_evidence
            )
            score = report.structural_validity
            if warnings:
                logger.warning(f"Slides generation warnings for {course_id}: {warnings}")

            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "slides", "processing", progress=70, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._save_artifact_json(
                course_id, "slides.json",
                self._artifact_with_plan(
                    validated_output, source_plan, [unit.id for unit in plan_units]
                ), artifact_dir,
            )
            self._generate_pptx_slides(course_id, validated_output, artifact_dir)
            if not job_id:
                self._update_course_metadata(
                    course_id, "slides", score, db_session_factory, quality_report=report
                )
            self._report_progress(progress_callback)
            if not self._publish_ready_version(
                transaction,
                course_id=course_id,
                artifact="slides",
                version_id=version_id,
                job_id=job_id,
                worker_id=worker_id,
                attempt_number=attempt_number,
                score=score,
                quality_report=report,
                db_session_factory=db_session_factory,
            ):
                raise _GenerationInterrupted
            return validated_output
        except _GenerationInterrupted:
            self._finish_version_write(transaction, False)
            return None
        except ProviderCircuitOpen:
            self._finish_version_write(transaction, False)
            raise
        except Exception as e:
            self._finish_version_write(transaction, False)
            logger.error(f"Slides generation failed for course {course_id}: {e}", exc_info=True)
            self._set_artifact_status(
                course_id,
                "slides",
                "error",
                error=(self._NO_CONTEXT_MSG if str(e) == self._NO_CONTEXT_MSG else "Không thể tạo bài trình chiếu. Vui lòng thử lại."),
                error_code=("ARTIFACT_SOURCE_UNAVAILABLE" if str(e) == self._NO_CONTEXT_MSG else "SLIDE_GENERATION_FAILED"),
                technical_error=str(e)[:1000],
                db_session_factory=db_session_factory,
                **status_fence,
            )
            return None

    def generate_quiz(self, course_id: str, topic: str = "AI Quiz", quantity: int = 5, difficulty: str = "mixed", db_session_factory=None, progress_callback: Optional[Callable[[], bool]] = None, **kwargs) -> Optional[QuizOutput]:
        """Execute full generation pipeline for Multiple Choice Quiz.

        On any failure, records an "error" artifact status and returns None instead of
        letting a background-task exception vanish silently.
        """
        logger.info(f"Starting Quiz generation for course {course_id} (quantity={quantity}, difficulty={difficulty})")
        version_id = kwargs.get("version_id")
        ready, output = self._ready_version_output(
            course_id, "quiz", "quiz.json", version_id, QuizOutput, db_session_factory
        )
        if ready:
            return output
        execution_token = kwargs.get("execution_token")
        job_id = kwargs.get("job_id")
        worker_id = kwargs.get("worker_id")
        attempt_number = kwargs.get("attempt_number")
        status_fence = {
            "job_id": job_id,
            "worker_id": worker_id,
            "attempt_number": attempt_number,
        }
        transaction, artifact_dir = self._start_version_write(
            course_id, "quiz", version_id, execution_token=execution_token
        )
        try:
            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "quiz", "processing", progress=10, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._require_course_not_processing(course_id, db_session_factory)
            resolved_topic = self._resolve_topic(course_id, topic, db_session_factory=db_session_factory)
            quiz_llm = self._llm_for("quiz")
            source_plan = self._get_source_plan(
                course_id,
                "quiz",
                db_session_factory,
                selected_llm=quiz_llm,
            )
            context, valid_chunk_ids, plan_units = self._plan_context(
                course_id, source_plan, topic=resolved_topic
            )
            self._bind_version_to_plan(
                course_id, "quiz", version_id, source_plan, db_session_factory,
                selected_model=getattr(quiz_llm, "model", settings.OPENROUTER_MODEL),
            )
            self._require_context(context)
            raw_output = quiz_llm.generate_quiz(context, resolved_topic, quantity, valid_chunk_ids, difficulty=difficulty)
            raw_output = _balance_quiz_answers(raw_output, kwargs.get("version_id", "legacy"))
            raw_output = _repair_flattened_array_indices(raw_output, context, "quiz")
            assigned_units = [
                plan_units[i % len(plan_units)] for i in range(len(raw_output.questions))
            ]
            self._enforce_canonical_consistency(raw_output, "quiz", source_plan, assigned_units)
            item_evidence = {
                i: unit.evidence_ids for i, unit in enumerate(assigned_units)
            }
            validated_output, report, warnings = validate_and_score_output(
                raw_output, "quiz", valid_chunk_ids, unit_valid_chunk_ids=item_evidence
            )
            score = report.structural_validity
            if warnings:
                logger.warning(f"Quiz generation warnings for {course_id}: {warnings}")

            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "quiz", "processing", progress=70, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._save_artifact_json(
                course_id, "quiz.json",
                self._artifact_with_plan(
                    validated_output, source_plan, [unit.id for unit in plan_units]
                ), artifact_dir,
            )
            self._generate_pdf_quiz_key(course_id, validated_output, artifact_dir)
            if not job_id:
                self._update_course_metadata(
                    course_id, "quiz", score, db_session_factory, quality_report=report
                )
            self._report_progress(progress_callback)
            if not self._publish_ready_version(
                transaction,
                course_id=course_id,
                artifact="quiz",
                version_id=version_id,
                job_id=job_id,
                worker_id=worker_id,
                attempt_number=attempt_number,
                score=score,
                quality_report=report,
                db_session_factory=db_session_factory,
            ):
                raise _GenerationInterrupted
            return validated_output
        except _GenerationInterrupted:
            self._finish_version_write(transaction, False)
            return None
        except ProviderCircuitOpen:
            self._finish_version_write(transaction, False)
            raise
        except Exception as e:
            self._finish_version_write(transaction, False)
            logger.error(f"Quiz generation failed for course {course_id}: {e}", exc_info=True)
            self._set_artifact_status(
                course_id,
                "quiz",
                "error",
                error=(self._NO_CONTEXT_MSG if str(e) == self._NO_CONTEXT_MSG else "Không thể tạo bài trắc nghiệm. Vui lòng thử lại."),
                error_code=("ARTIFACT_SOURCE_UNAVAILABLE" if str(e) == self._NO_CONTEXT_MSG else "QUIZ_GENERATION_FAILED"),
                technical_error=str(e)[:1000],
                db_session_factory=db_session_factory,
                **status_fence,
            )
            return None

    def generate_vid(
        self,
        course_id: str,
        topic: str = "AI Video",
        fmt: str = "standard",
        voice: str = "female",
        user_prompt: str = "",
        db_session_factory=None,
        progress_callback: Optional[Callable[[], bool]] = None,
        **kwargs,
    ) -> Optional[VidOutput]:
        """Execute full generation pipeline for the narrated Video: LLM script (1 call) ->
        per-scene TTS narration + still frame -> ffmpeg mux/concat into vid.mp4.

        On any failure, records an "error" artifact status and returns None instead of
        letting a background-task exception vanish silently.
        """
        logger.info(f"Starting Video generation for course {course_id} (format={fmt}, voice={voice})")
        version_id = kwargs.get("version_id")
        ready, output = self._ready_version_output(
            course_id, "vid", "vid.json", version_id, VidOutput, db_session_factory
        )
        if ready:
            return output
        execution_token = kwargs.get("execution_token")
        job_id = kwargs.get("job_id")
        worker_id = kwargs.get("worker_id")
        attempt_number = kwargs.get("attempt_number")
        status_fence = {
            "job_id": job_id,
            "worker_id": worker_id,
            "attempt_number": attempt_number,
        }
        transaction, artifact_dir = self._start_version_write(
            course_id, "vid", version_id, execution_token=execution_token
        )
        try:
            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "vid", "processing", progress=10, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._require_course_not_processing(course_id, db_session_factory)
            resolved_topic = self._resolve_topic(course_id, topic, db_session_factory=db_session_factory)
            vid_llm = self._llm_for("vid")
            source_plan = self._get_source_plan(
                course_id,
                "vid",
                db_session_factory,
                selected_llm=vid_llm,
            )
            context, valid_chunk_ids, plan_units = self._plan_context(
                course_id, source_plan, topic=resolved_topic
            )
            self._bind_version_to_plan(
                course_id, "vid", version_id, source_plan, db_session_factory,
                selected_model=getattr(vid_llm, "model", settings.OPENROUTER_MODEL),
            )
            self._require_context(context)
            raw_output = vid_llm.generate_vid(
                context, resolved_topic, fmt, user_prompt, valid_chunk_ids
            )
            raw_output = _clean_vid_output(raw_output)
            assigned_units = [
                plan_units[i % len(plan_units)] for i in range(len(raw_output.scenes))
            ]
            self._enforce_canonical_consistency(raw_output, "vid", source_plan, assigned_units)
            item_evidence = {
                i: unit.evidence_ids for i, unit in enumerate(assigned_units)
            }
            validated_output, report, warnings = validate_and_score_output(
                raw_output, "vid", valid_chunk_ids, unit_valid_chunk_ids=item_evidence
            )
            score = report.structural_validity
            if warnings:
                logger.warning(f"Vid generation warnings for {course_id}: {warnings}")
            scene_visual_map = self._build_scene_visual_map(course_id, validated_output)

            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "vid", "processing", progress=25, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted

            def _progress_cb(fraction: float) -> None:
                self._report_progress(progress_callback)
                if not self._set_artifact_status(
                    course_id, "vid", "processing", progress=25 + int(60 * fraction),
                    db_session_factory=db_session_factory,
                    **status_fence,
                ):
                    raise _GenerationInterrupted

            self._generate_video_mp4(
                course_id,
                validated_output,
                fmt,
                voice,
                progress_cb=_progress_cb,
                artifact_dir=artifact_dir,
                scene_visual_map=scene_visual_map,
            )

            self._report_progress(progress_callback)
            if not self._set_artifact_status(course_id, "vid", "processing", progress=90, db_session_factory=db_session_factory, **status_fence):
                raise _GenerationInterrupted
            self._save_artifact_json(
                course_id, "vid.json",
                self._artifact_with_plan(
                    validated_output, source_plan, [unit.id for unit in plan_units]
                ), artifact_dir,
            )
            if not job_id:
                self._update_course_metadata(
                    course_id, "vid", score, db_session_factory, quality_report=report
                )
            self._report_progress(progress_callback)
            if not self._publish_ready_version(
                transaction,
                course_id=course_id,
                artifact="vid",
                version_id=version_id,
                job_id=job_id,
                worker_id=worker_id,
                attempt_number=attempt_number,
                score=score,
                quality_report=report,
                db_session_factory=db_session_factory,
            ):
                raise _GenerationInterrupted
            return validated_output
        except _GenerationInterrupted:
            self._finish_version_write(transaction, False)
            return None
        except ProviderCircuitOpen:
            self._finish_version_write(transaction, False)
            raise
        except Exception as e:
            self._finish_version_write(transaction, False)
            logger.error(f"Vid generation failed for course {course_id}: {e}", exc_info=True)
            self._set_artifact_status(
                course_id,
                "vid",
                "error",
                error=(self._NO_CONTEXT_MSG if str(e) == self._NO_CONTEXT_MSG else "Không thể tạo video. Vui lòng thử lại."),
                error_code=("ARTIFACT_SOURCE_UNAVAILABLE" if str(e) == self._NO_CONTEXT_MSG else "VIDEO_GENERATION_FAILED"),
                technical_error=str(e)[:1000],
                db_session_factory=db_session_factory,
                **status_fence,
            )
            return None

    def get_study_pack(self, course_id: str, db_session_factory=None) -> StudyPackResponse:
        """Build and return full StudyPackResponse from filesystem artifacts and DB state."""
        db = self._get_db(db_session_factory)
        try:
            course = db.query(Course).filter(Course.id == course_id).first()
            status_val = course.status if course else "ready"
            chunk_cnt = course.chunk_count if course else 0
            q_score = course.quality_score if course else 0
            meta = course.metadata_json if course and course.metadata_json else "{}"
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            sp_meta = meta.get("study_pack", {})
        finally:
            db.close()

        def active_artifact_dir(artifact: str) -> str:
            entry = sp_meta.get("artifacts", {}).get(artifact, {})
            if isinstance(entry, dict) and entry.get("active"):
                return artifact_directory_path(settings.UPLOAD_DIR, course_id, artifact, entry["active"])
            return self._get_artifact_dir(course_id)

        book_dir = active_artifact_dir("book")
        slides_dir = active_artifact_dir("slides")
        quiz_dir = active_artifact_dir("quiz")
        vid_dir = active_artifact_dir("vid")
        book_json = self._load_artifact_json(course_id, "book.json", book_dir)
        slides_json = self._load_artifact_json(course_id, "slides.json", slides_dir)
        quiz_json = self._load_artifact_json(course_id, "quiz.json", quiz_dir)
        vid_json = self._load_artifact_json(course_id, "vid.json", vid_dir)
        has_book = book_json is not None
        has_book_pdf = os.path.exists(os.path.join(book_dir, "book.pdf"))
        has_slide = slides_json is not None
        has_slide_pptx = os.path.exists(os.path.join(slides_dir, "slide.pptx"))
        has_quiz = quiz_json is not None
        has_quiz_key = os.path.exists(os.path.join(quiz_dir, "quiz-key.pdf"))
        has_vid = vid_json is not None

        readiness_meta = sp_meta.get("readiness", {})
        readiness = ReadinessData(
            study_guide_pdf=has_book or readiness_meta.get("study_guide_pdf", False),
            slides=has_slide or readiness_meta.get("slides", False),
            quiz=has_quiz or readiness_meta.get("quiz", False),
            vid=has_vid or readiness_meta.get("vid", False),
        )

        quality_scores_meta = sp_meta.get("quality_scores", {})
        quality_scores = QualityScoresData(
            study_guide_pdf=quality_scores_meta.get("study_guide_pdf", 0),
            slides=quality_scores_meta.get("slides", 0),
            quiz=quality_scores_meta.get("quiz", 0),
            vid=quality_scores_meta.get("vid", 0),
        )
        quality_reports = {}
        for key, value in _active_quality_report_payloads(sp_meta).items():
            payload = _quality_report_payload(value)
            if payload is None:
                continue
            try:
                quality_reports[key] = QualityReport.model_validate(payload)
            except Exception:
                continue

        grounding_meta = sp_meta.get("grounding", {})
        grounding = GroundingData(
            num_chunks=grounding_meta.get("num_chunks", chunk_cnt if (has_book or has_slide or has_quiz or has_vid) else 0),
            quality_score=grounding_meta.get("quality_score", q_score if (has_book or has_slide or has_quiz or has_vid) else 0),
            warnings=grounding_meta.get("warnings", []),
        )

        return StudyPackResponse(
            course_id=course_id,
            stats=StudyPackStats(
                course_id=course_id,
                status=status_val,
                has_book=has_book,
                has_book_pdf=has_book_pdf,
                has_slide=has_slide,
                has_slide_pptx=has_slide_pptx,
                has_quiz=has_quiz,
                has_quiz_answer_key=has_quiz_key,
                has_vid=has_vid,
                quality_score=q_score,
                num_chunks=chunk_cnt,
            ),
            study_pack=StudyPackData(
                title=book_json.get("title", "Course Title") if book_json else "Course Title",
                book=sanitize_public_payload(book_json),
                slides=sanitize_public_payload(slides_json),
                quiz=sanitize_public_payload(quiz_json.get("questions", [])) if quiz_json else [],
                vid=sanitize_public_payload(vid_json),
                readiness=readiness,
                quality_scores=quality_scores,
                quality_reports=quality_reports,
                grounding=grounding,
            ),
        )
