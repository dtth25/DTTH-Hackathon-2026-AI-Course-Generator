"""Document processing service for extracting, cleaning, chunking, and embedding documents."""

import hashlib
import logging
import os
import re
from collections import Counter
from typing import List, Optional, Tuple

import docx
import fitz  # PyMuPDF
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml.ns import qn
from pydantic import BaseModel

from app.models.course import Course
from app.services.vector_store import Document, VectorStore

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY_RE = re.compile(r"[.?!][ \n]")
_FRONT_MATTER_MARKERS = (
    "isbn", "nhà xuất bản", "nxb", "bản quyền", "tái bản", "ấn bản", "thẩm định",
    "được thẩm định", "approval", "approved by", "publisher", "copyright", "all rights reserved",
    "edition", "出版社", "出版", "审定", "批准", "版权", "isbn",
)


def _is_front_matter(text: str) -> bool:
    """Identify colophon/publishing pages so they cannot dominate RAG on thin scans."""
    normalized = " ".join(text.lower().split())
    matches = sum(marker in normalized for marker in _FRONT_MATTER_MARKERS)
    # A strong colophon marker is enough; a generic edition/publisher hint needs a second
    # signal to avoid discarding an academic discussion that happens to mention publishing.
    return matches >= 2 or any(marker in normalized for marker in ("isbn", "thẩm định", "审定", "出版社", "版权"))


def _evenly_spaced_indices(indices: List[int], limit: int) -> List[int]:
    """Choose up to ``limit`` source-page indices across the entire document."""
    if limit <= 0 or not indices:
        return []
    if len(indices) <= limit:
        return indices
    if limit == 1:
        return [indices[len(indices) // 2]]
    return [indices[round(i * (len(indices) - 1) / (limit - 1))] for i in range(limit)]


def _indices_with_optional_limit(indices: List[int], limit: int) -> List[int]:
    """Return all indices when ``limit`` is zero, otherwise preserve even coverage.

    OCR used to interpret zero as "do nothing" and the default hard cap silently left
    most long scanned documents unread. Zero now has the conventional configuration
    meaning of "unlimited"; a positive value remains available as an explicit cost cap.
    """
    return indices if limit == 0 else _evenly_spaced_indices(indices, limit)


def _text_signal_length(text: str) -> int:
    """Measure readable text rather than whitespace or decorative punctuation."""
    return sum(1 for char in text if char.isalnum())


def _decode_text_bytes(data: bytes) -> str:
    """Decode common TXT encodings without turning UTF-16 into NUL-filled garbage."""
    if not data:
        return ""

    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")

    # UTF-16 files without a BOM still have a strong alternating-NUL signature.
    nul_ratio = data.count(b"\x00") / len(data)
    if nul_ratio > 0.1:
        candidates = []
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                decoded = data.decode(encoding)
            except UnicodeDecodeError:
                continue
            control_count = sum(
                1 for char in decoded if ord(char) < 32 and char not in "\n\r\t"
            )
            candidates.append((control_count, -_text_signal_length(decoded), decoded))
        if candidates:
            return min(candidates, key=lambda item: (item[0], item[1]))[2]

    # UTF-8 covers the normal path; cp1258 covers legacy Vietnamese Windows text.
    for encoding in ("utf-8", "cp1258", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _is_probably_text(text: str) -> bool:
    if not text or "\x00" in text:
        return False
    control_count = sum(
        1 for char in text if ord(char) < 32 and char not in "\n\r\t\f"
    )
    return control_count / len(text) <= 0.02


def _extract_ooxml_text(root) -> List[str]:
    """Read paragraph text from an OOXML story, including tables and text boxes."""
    paragraph_tag = qn("w:p")
    text_tag = qn("w:t")
    tab_tag = qn("w:tab")
    break_tag = qn("w:br")
    lines: List[str] = []

    for paragraph in root.iter(paragraph_tag):
        pieces: List[str] = []
        for node in paragraph.iter():
            # A text box can contain a nested paragraph. Attribute each run only to its
            # nearest paragraph so it is not duplicated by the outer drawing paragraph.
            ancestor = node.getparent()
            belongs_to_paragraph = True
            while ancestor is not None and ancestor is not paragraph:
                if ancestor.tag == paragraph_tag:
                    belongs_to_paragraph = False
                    break
                ancestor = ancestor.getparent()
            if not belongs_to_paragraph:
                continue
            if node.tag == text_tag and node.text:
                pieces.append(node.text)
            elif node.tag == tab_tag:
                pieces.append("\t")
            elif node.tag == break_tag:
                pieces.append("\n")
        line = "".join(pieces).strip()
        if line:
            lines.append(line)
    return lines


def _find_split_position(text: str, start: int, end: int, chunk_size: int) -> int:
    """Find the best position to end a chunk at, preferring a sentence boundary, then a
    newline, then a plain space — only within the back half of the window so a chunk
    never ends up drastically shorter than requested. Returns -1 for a hard cut at `end`
    when no good boundary is found."""
    half = start + chunk_size // 2

    best = -1
    for m in _SENTENCE_BOUNDARY_RE.finditer(text, start, end):
        pos = m.start() + 1  # right after the punctuation, before the trailing whitespace
        if pos > half:
            best = pos
    if best != -1:
        return best

    split_pos = text.rfind("\n", start, end)
    if split_pos == -1 or split_pos <= half:
        split_pos = text.rfind(" ", start, end)
    if split_pos != -1 and split_pos > half:
        return split_pos

    return -1


class ProcessingResult(BaseModel):
    """Result of processing documents for a course."""

    course_id: str
    status: str
    chunk_count: int
    quality_score: int
    error: Optional[str] = None


class DocumentProcessor:
    """Processes course documents: extraction, cleaning, chunking, embedding, and vector storage."""

    def __init__(
        self,
        vector_store: VectorStore,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        from app.core.config import settings

        self.vector_store = vector_store
        self.chunk_size = chunk_size if chunk_size is not None else settings.DOCUMENT_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DOCUMENT_CHUNK_OVERLAP

    def _update_course_db(
        self,
        course_id: str,
        status: str,
        stage: str,
        progress: int,
        chunk_count: int = 0,
        quality_score: int = 0,
        embedding_status: str = "pending",
        name: Optional[str] = None,
        error_message: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        db_session_factory=None,
    ):
        """Helper to update course status in database."""
        if db_session_factory is None:
            from app.services.database import SessionLocal as factory
        else:
            factory = db_session_factory
        try:
            with factory() as db:
                course = (
                    db.query(Course)
                    .filter(Course.id == course_id, Course.is_deleted == False)  # noqa: E712
                    .first()
                )
                if course:
                    course.status = status
                    course.stage = stage
                    course.progress = progress
                    if chunk_count > 0:
                        course.chunk_count = chunk_count
                    if quality_score > 0:
                        course.quality_score = quality_score
                    if name:
                        course.name = name
                    if embedding_provider:
                        course.embedding_provider = embedding_provider
                    course.embedding_status = embedding_status
                    # Clears any stale error from a prior attempt on success, persists the
                    # real reason on failure — always set explicitly, not just on failure.
                    course.error_message = error_message
                    db.commit()
        except Exception as e:
            logger.error(f"Failed to update course {course_id} in DB: {e}")

    def _generate_course_title(self, all_documents: List[Document]) -> Optional[str]:
        """Best-effort AI-generated short course title from a sample of extracted text.
        Tried exactly once per course (from process_course) — on any failure the caller
        falls back to the document's own filename, like how chat UIs name a conversation
        once and leave the rest to manual rename."""
        try:
            from app.services.llm import LLMService

            sample = "\n\n".join(doc.content for doc in all_documents[:5])[:4000]
            if not sample.strip():
                return None
            result = LLMService().generate_course_title(sample)
            title = (result.title or "").strip()
            return title or None
        except Exception as e:
            logger.error(f"Course title generation failed, falling back to filename: {e}", exc_info=True)
            return None

    @staticmethod
    def _filename_fallback_title(file_path: str) -> str:
        """Clean a filename into a presentable course title: drop the upload-time timestamp
        prefix and the extension (e.g. '1730000000_Virtual Tree.pdf' -> 'Virtual Tree')."""
        filename = os.path.basename(file_path)
        parts = filename.split("_", 1)
        if len(parts) == 2 and parts[0].isdigit():
            filename = parts[1]
        return os.path.splitext(filename)[0].strip() or filename

    def purge_course_storage(self, course_id: str) -> None:
        """Remove on-disk uploads and vector store chunks for a course. Shared by
        single-course delete and full-account deletion so the cleanup logic lives in
        exactly one place."""
        import shutil
        from app.core.config import settings

        upload_dir = os.path.join(settings.UPLOAD_DIR, course_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir, ignore_errors=True)
        self.vector_store.delete_course(course_id)

    def extract_text_from_file(self, file_path: str) -> List[dict]:
        """Extract text from PDF/DOCX/TXT file. Returns list of dicts with content and page number."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        filename = os.path.basename(file_path)
        # Strip timestamp prefix if present (e.g. 1234567890_test.pdf -> test.pdf)
        parts = filename.split("_", 1)
        if len(parts) == 2 and parts[0].isdigit():
            clean_filename = parts[1]
        else:
            clean_filename = filename

        pages = []

        if ext == ".pdf":
            from app.core.config import settings

            try:
                pdf = fitz.open(file_path)
            except Exception as exc:
                return self._plain_text_fallback(file_path, clean_filename, "PDF", exc)

            with pdf:
                if pdf.needs_pass:
                    raise ValueError(
                        f"PDF {clean_filename} được bảo vệ bằng mật khẩu và không thể trích xuất nội dung."
                    )
                if pdf.page_count == 0:
                    raise ValueError(f"PDF {clean_filename} không có trang nào để xử lý.")

                page_texts = [(page.get_text() or "").strip() for page in pdf]
                visual_candidates = [
                    idx
                    for idx, text in enumerate(page_texts)
                    if _text_signal_length(text) < settings.PDF_TEXT_MIN_CHARS_PER_PAGE
                    and self._page_has_visual_content(pdf[idx])
                ]
                ocr_page_indices = set(
                    _indices_with_optional_limit(
                        visual_candidates, settings.PDF_OCR_MAX_PAGES
                    )
                    if settings.PDF_ENABLE_OCR
                    else []
                )
                ocr_attempted = 0
                ocr_succeeded = 0

                for idx, text in enumerate(page_texts):
                    if idx in ocr_page_indices:
                        ocr_attempted += 1
                        ocr_text = self._ocr_page(pdf, idx, settings.PDF_OCR_DPI)
                        if ocr_text and _text_signal_length(ocr_text) > _text_signal_length(text):
                            text = ocr_text.strip()
                            ocr_succeeded += 1
                    if text:
                        pages.append(
                            {
                                "content": text,
                                "page": idx + 1,
                                "source_file": clean_filename,
                            }
                        )

            if not pages:
                if visual_candidates and not settings.PDF_ENABLE_OCR:
                    raise ValueError(
                        f"PDF {clean_filename} chỉ chứa ảnh nhưng OCR đang bị tắt."
                    )
                if ocr_attempted and not ocr_succeeded:
                    raise ValueError(
                        f"Không thể OCR nội dung trong PDF {clean_filename}. "
                        "Hãy kiểm tra cấu hình OpenRouter hoặc chất lượng bản scan."
                    )
                raise ValueError(
                    f"PDF {clean_filename} không chứa văn bản hoặc hình ảnh có thể đọc được."
                )

        elif ext == ".docx":
            from app.core.config import settings

            try:
                word_doc = docx.Document(file_path)
            except Exception as exc:
                return self._plain_text_fallback(file_path, clean_filename, "DOCX", exc)

            full_text = _extract_ooxml_text(word_doc.element.body)
            story_parts = [word_doc.part]
            seen_story_parts = {id(word_doc.part)}
            for section in word_doc.sections:
                for story in (section.header, section.footer):
                    if id(story.part) not in seen_story_parts:
                        seen_story_parts.add(id(story.part))
                        story_parts.append(story.part)
                        full_text.extend(_extract_ooxml_text(story._element))

            image_blobs = []
            seen_images = set()
            for part in story_parts:
                for relationship in part.rels.values():
                    if relationship.reltype != RELATIONSHIP_TYPE.IMAGE:
                        continue
                    blob = relationship.target_part.blob
                    digest = hashlib.sha256(blob).digest()
                    if digest not in seen_images:
                        seen_images.add(digest)
                        image_blobs.append(blob)

            if settings.DOCX_ENABLE_OCR and image_blobs:
                image_indices = _indices_with_optional_limit(
                    list(range(len(image_blobs))), settings.DOCX_OCR_MAX_IMAGES
                )
                for image_index in image_indices:
                    ocr_text = self._ocr_image(image_blobs[image_index])
                    if ocr_text and ocr_text.strip():
                        full_text.append(ocr_text.strip())

            text = "\n".join(full_text).strip()
            if text:
                pages.append(
                    {
                        "content": text,
                        "page": 1,
                        "source_file": clean_filename,
                    }
                )
            elif image_blobs:
                if not settings.DOCX_ENABLE_OCR:
                    raise ValueError(
                        f"DOCX {clean_filename} chỉ chứa ảnh nhưng OCR đang bị tắt."
                    )
                raise ValueError(
                    f"Không thể OCR ảnh trong DOCX {clean_filename}. "
                    "Hãy kiểm tra cấu hình OpenRouter hoặc chất lượng hình ảnh."
                )
            else:
                raise ValueError(f"DOCX {clean_filename} không chứa nội dung có thể đọc được.")

        elif ext == ".txt":
            try:
                with open(file_path, "rb") as text_file:
                    text = _decode_text_bytes(text_file.read()).strip()
                if not _is_probably_text(text):
                    raise ValueError(f"TXT {clean_filename} không chứa văn bản hợp lệ.")
                pages.append(
                    {
                        "content": text,
                        "page": 1,
                        "source_file": clean_filename,
                    }
                )
            except Exception as exc:
                logger.error("Error reading TXT %s: %s", file_path, exc)
                raise

        else:
            raise ValueError(f"Unsupported file extension: {ext}")

        return pages

    @staticmethod
    def _plain_text_fallback(
        file_path: str, clean_filename: str, format_name: str, original_error: Exception
    ) -> List[dict]:
        """Keep compatibility with legacy plain-text test fixtures, but never mistake a
        corrupt real PDF/ZIP container for extracted document text."""
        with open(file_path, "rb") as source:
            raw = source.read()
        if raw.startswith((b"%PDF", b"PK\x03\x04")):
            logger.error("Error reading %s %s: %s", format_name, file_path, original_error)
            raise original_error
        text = _decode_text_bytes(raw).strip()
        if not _is_probably_text(text):
            raise original_error
        logger.warning(
            "%s open failed for %s; using legacy plain-text fallback.",
            format_name,
            file_path,
        )
        return [{"content": text, "page": 1, "source_file": clean_filename}]

    @staticmethod
    def _page_has_visual_content(page: "fitz.Page") -> bool:
        """Avoid paying for OCR on truly blank separator pages."""
        try:
            return bool(page.get_images(full=True) or page.get_drawings())
        except Exception:
            # If the structure cannot be inspected, attempting OCR is safer than silently
            # dropping a potentially scanned page.
            return True

    def _ocr_image(self, image_bytes: bytes) -> Optional[str]:
        """Normalize an embedded Word image to PNG and transcribe it with the OCR model."""
        try:
            pixmap = fitz.Pixmap(image_bytes)
            if pixmap.n - pixmap.alpha > 3:
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            png_bytes = pixmap.tobytes("png")

            from app.services.llm import LLMService

            return LLMService().ocr_page_image(png_bytes) or None
        except Exception as exc:
            logger.warning("OCR fallback failed for embedded DOCX image: %s", exc)
            return None

    def _ocr_page(self, doc: "fitz.Document", page_index: int, dpi: int) -> Optional[str]:
        """Render a PDF page to an image and ask OpenRouter vision to transcribe its text.
        Best-effort: returns None on any failure so the caller keeps whatever text
        extraction already produced (possibly empty/short)."""
        try:
            page = doc[page_index]
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            image_bytes = pix.tobytes("png")

            from app.services.llm import LLMService

            return LLMService().ocr_page_image(image_bytes) or None
        except Exception as e:
            logger.warning(f"OCR fallback failed for page {page_index + 1}: {e}")
            return None

    def clean_text(self, text: str) -> str:
        """Clean extracted text: remove repetitive noise, extra whitespace, Table of Contents leaders."""
        if not text:
            return ""

        # Remove TOC dot leaders (e.g. "Chapter 1 ................ 5")
        text = re.sub(r"\.{4,}\s*\d*", " ", text)
        # Remove repetitive dashes or underscores
        text = re.sub(r"[-_]{4,}", " ", text)
        # Normalize whitespace and newlines
        lines = [line.strip() for line in text.split("\n")]
        # Filter out very short noisy lines (like page numbers standing alone)
        cleaned_lines = [line for line in lines if len(line) > 1 or not line.isdigit()]

        return "\n".join(cleaned_lines).strip()

    def chunk_text(
        self,
        text: str,
        metadata: dict,
        course_id: str,
        page_offsets: Optional[List[Tuple[int, int, int]]] = None,
    ) -> List[Document]:
        """Chunk text with overlap and attach required metadata.

        When `page_offsets` (list of (start, end, page_number) covering `text`) is given —
        used when `text` is the concatenation of every page of one document, so ideas
        split across a page boundary don't get fragmented — each chunk's `page` is derived
        from the offset range it starts in instead of the single `metadata["page"]` value.
        Without it, behaves exactly as a single-page chunk call (`metadata["page"]` for all
        chunks), which is what direct single-page callers still rely on.
        """
        if not text:
            return []

        chunks = []
        source_file = metadata.get("source_file", "unknown")
        default_page = metadata.get("page", 1)

        def _page_for_offset(pos: int) -> int:
            if not page_offsets:
                return default_page
            for p_start, p_end, page_num in page_offsets:
                if p_start <= pos < p_end:
                    return page_num
            return page_offsets[-1][2]

        # Character-boundary chunking with overlap, preferring sentence/newline/space breaks
        start = 0
        text_len = len(text)
        idx = 0

        while start < text_len:
            end = start + self.chunk_size
            if end < text_len:
                split_pos = _find_split_position(text, start, end, self.chunk_size)
                if split_pos != -1:
                    end = split_pos

            chunk_content = text[start:end].strip()
            if chunk_content:
                page = _page_for_offset(start)
                chunk_id = f"{source_file}_p{page}_c{idx}"
                source_chunk_id = f"{course_id}_{chunk_id}"

                doc = Document(
                    content=chunk_content,
                    metadata={
                        "page": page,
                        "source_file": source_file,
                        "chunk_id": chunk_id,
                        "source_chunk_id": source_chunk_id,
                        "course_id": course_id,
                    },
                )
                chunks.append(doc)
                idx += 1

            if end >= text_len:
                break
            start = max(end - self.chunk_overlap, start + 1)

        return chunks

    def _strip_repeated_headers_footers(self, pages: List[dict]) -> List[dict]:
        """Detect lines that repeat identically across >=3 pages of the same document
        (running headers/footers) and strip them before chunking. Needs the full page
        list at once (unlike clean_text, which only ever sees one page)."""
        if len(pages) < 3:
            return pages

        line_counts: Counter = Counter()
        for p in pages:
            lines = {line.strip() for line in p["content"].split("\n") if line.strip()}
            for line in lines:
                if len(line) >= 3:
                    line_counts[line] += 1

        repeated = {line for line, count in line_counts.items() if count >= 3}
        if not repeated:
            return pages

        result = []
        for p in pages:
            kept = [line for line in p["content"].split("\n") if line.strip() not in repeated]
            result.append({**p, "content": "\n".join(kept)})
        return result

    def _is_low_information(self, text: str) -> bool:
        """A chunk is noise if it's too short or mostly non-alphanumeric (leftover
        table borders, decorative characters, stray symbols)."""
        stripped = text.strip()
        if len(stripped.split()) < 15:
            return True
        alnum_count = sum(1 for c in stripped if c.isalnum())
        return len(stripped) > 0 and (alnum_count / len(stripped)) < 0.5

    def extract_and_chunk_file(self, path: str, course_id: str) -> List[Document]:
        """Extract, clean, dedup headers/footers, cross-page chunk, and low-info-prune a
        single file. Shared by process_course() and the standalone re-embed migration
        script (scripts/reembed_courses.py) so both stay in sync with chunking changes."""
        extracted_pages = self.extract_text_from_file(path)
        cleaned_pages = []
        for page_data in extracted_pages:
            cleaned = self.clean_text(page_data["content"])
            if cleaned:
                cleaned_pages.append({**page_data, "content": cleaned})
        cleaned_pages = self._strip_repeated_headers_footers(cleaned_pages)

        # Concatenate every page of this document into one string with an
        # offset->page map, so a chunk never gets cut off just because it
        # happens to straddle a page boundary.
        combined_parts: List[str] = []
        page_offsets: List[Tuple[int, int, int]] = []
        offset = 0
        source_file = None
        for page_data in cleaned_pages:
            content = page_data["content"]
            if not content:
                continue
            source_file = page_data["source_file"]
            combined_parts.append(content)
            page_offsets.append((offset, offset + len(content), page_data["page"]))
            offset += len(content)
            combined_parts.append("\n\n")
            offset += 2

        if not combined_parts:
            return []

        combined_text = "".join(combined_parts)
        page_meta = {"page": page_offsets[0][2], "source_file": source_file}
        doc_chunks = self.chunk_text(combined_text, page_meta, course_id, page_offsets=page_offsets)
        front_matter_pages = {
            page_data["page"] for page_data in cleaned_pages if _is_front_matter(page_data["content"])
        }
        for chunk in doc_chunks:
            chunk.metadata["is_front_matter"] = chunk.metadata.get("page") in front_matter_pages
        filtered_chunks = [c for c in doc_chunks if not self._is_low_information(c.content)]
        # Pruning noise should never zero out a whole document's contribution —
        # a genuinely tiny document (or a chunk_size small enough to slice below
        # the word-count floor) should still upload, not silently disappear.
        return filtered_chunks or doc_chunks

    def process_course(
        self, course_id: str, file_paths: List[str], db_session_factory=None
    ) -> ProcessingResult:
        """
        1. Extract text từ files (PDF/DOCX/TXT)
        2. Clean text: remove headers, footers, TOC noise
        3. Chunk text với overlap
        4. Generate embeddings
        5. Store in Chroma
        """
        logger.info(f"Starting document processing pipeline for course {course_id}")
        self._update_course_db(
            course_id,
            status="processing",
            stage="extracting",
            progress=20,
            db_session_factory=db_session_factory,
        )

        all_documents: List[Document] = []
        try:
            # 1. Extract, 2. Clean, 3. Chunk
            for path in file_paths:
                all_documents.extend(self.extract_and_chunk_file(path, course_id))

            self._update_course_db(
                course_id,
                status="processing",
                stage="chunking",
                progress=50,
                db_session_factory=db_session_factory,
            )

            if not all_documents:
                raise ValueError(
                    "No valid text could be extracted from uploaded files."
                )

            self._update_course_db(
                course_id,
                status="processing",
                stage="embedding",
                progress=75,
                db_session_factory=db_session_factory,
            )

            # All newly indexed chunks use the single OpenRouter embedding space.
            embedding_provider = "openrouter"
            self.vector_store.add_documents(all_documents, course_id=course_id, provider=embedding_provider)
            indexed_count = self.vector_store.get_course_stats(
                course_id, provider=embedding_provider
            ).get("chunk_count", 0)
            if indexed_count < len(all_documents):
                raise RuntimeError(
                    "Không thể xác nhận đầy đủ nội dung sau khi lập chỉ mục "
                    f"({indexed_count}/{len(all_documents)} đoạn)."
                )

            # Calculate quality score (e.g., based on average chunk length and total chunks)
            quality_score = min(100, max(50, len(all_documents) * 5 + 60))

            # One AI-naming attempt per course, like a chat UI naming a new conversation —
            # no retries. Falls back to the (cleaned) uploaded filename so `name` is always
            # set once a course is ready; after this, naming is purely manual (rename).
            course_title = self._generate_course_title(all_documents) or self._filename_fallback_title(
                file_paths[0]
            )

            # Completed!
            self._update_course_db(
                course_id,
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=len(all_documents),
                quality_score=quality_score,
                embedding_status="completed",
                name=course_title,
                embedding_provider=embedding_provider,
                db_session_factory=db_session_factory,
            )

            logger.info(
                f"Successfully processed course {course_id}: {len(all_documents)} chunks created."
            )
            return ProcessingResult(
                course_id=course_id,
                status="ready",
                chunk_count=len(all_documents),
                quality_score=quality_score,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Document processing failed for course {course_id}: {error_msg}"
            )
            self._update_course_db(
                course_id,
                status="failed",
                stage="failed",
                progress=0,
                embedding_status="failed",
                error_message=error_msg[:500],
                db_session_factory=db_session_factory,
            )
            return ProcessingResult(
                course_id=course_id,
                status="failed",
                chunk_count=0,
                quality_score=0,
                error=error_msg,
            )


def get_document_processor() -> DocumentProcessor:
    """Get DocumentProcessor instance initialized with singleton VectorStore."""
    from app.services.vector_store import get_vector_store
    return DocumentProcessor(vector_store=get_vector_store())
