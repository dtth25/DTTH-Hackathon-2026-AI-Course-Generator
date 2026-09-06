"""Pydantic schemas and quality scoring for HackaGen outputs."""

import re
from typing import Any, List, Literal, Mapping, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


# =====================================================================
# 0. Course Title Schema
# =====================================================================


class CourseTitleOutput(BaseModel):
    """A short, human-friendly title generated for a newly uploaded course."""

    title: str = Field(..., description="Concise course title (max ~8 words), no file extension")


# =====================================================================
# 1. Book (Study Guide) Schemas
# =====================================================================


class BookSection(BaseModel):
    """Section within a study guide chapter."""

    title: str = Field(..., description="Title of the section")
    content: str = Field(..., description="Detailed explanation and instructional content")


class BookChapter(BaseModel):
    """Chapter of the study guide."""

    chapter_title: str = Field(..., description="Title of the chapter")
    introduction: str = Field("", description="Opening paragraph introducing the chapter")
    objectives: List[str] = Field(default_factory=list, description="Learning objectives")
    sections: List[BookSection] = Field(default_factory=list, description="Sections in this chapter")
    key_points: List[str] = Field(default_factory=list, description="Key takeaways")
    review_questions: List[str] = Field(default_factory=list, description="Review/self-check questions")
    source_chunk_ids: List[str] = Field(
        default_factory=list, description="List of chunk IDs used for grounding this chapter"
    )


class BookOutput(BaseModel):
    """Complete generated Study Guide Book."""

    title: str = Field(..., description="Overall title of the study guide")
    summary: str = Field(..., description="Executive summary of the course content")
    preface: str = Field("", description="Foreword/preface introducing the book to the reader")
    chapters: List[BookChapter] = Field(default_factory=list, description="Chapters of the book")


# =====================================================================
# 1b. Book multi-pass pipeline (internal, never persisted as book.json)
# =====================================================================


class BookChapterPlan(BaseModel):
    """Outline entry for a single planned chapter."""

    chapter_number: int = Field(..., description="1-based chapter order")
    chapter_title: str = Field(..., description="Chapter title, without a 'Chương N' prefix")
    description: str = Field(..., description="2-3 sentence summary of what this chapter teaches")
    retrieval_query: str = Field(..., description="Vietnamese search query used to retrieve context for this chapter")
    planned_sections: List[str] = Field(default_factory=list, description="3-5 planned section headings")


class BookOutline(BaseModel):
    """High-level plan for the whole book, produced by the first LLM pass."""

    title: str = Field(..., description="Overall title of the study guide")
    summary: str = Field(..., description="Executive summary of the course content")
    preface: str = Field("", description="Optional concise orientation when it adds learning value")
    chapters: List[BookChapterPlan] = Field(default_factory=list, description="One entry per evidenced source-plan unit")


class BookObjectiveCoverage(BaseModel):
    """Internal structural link from a stable objective to teaching sections."""

    objective_id: str = Field(..., min_length=1, description="Assigned SourcePlan objective ID")
    objective: str = Field(..., min_length=1, description="Exact assigned objective text")
    section_indices: List[int] = Field(
        default_factory=list,
        description="Zero-based chapter section indices that teach this objective",
    )


class BookChapterContent(BaseModel):
    """Full content for a single chapter, produced by a per-chapter LLM pass."""

    chapter_title: str = Field(..., description="Title of the chapter")
    introduction: str = Field("", description="Opening paragraph introducing the chapter")
    objectives: List[str] = Field(default_factory=list, description="Learning objectives")
    sections: List[BookSection] = Field(default_factory=list, description="Sections in this chapter")
    objective_coverage: List[BookObjectiveCoverage] = Field(
        default_factory=list,
        description="Internal assignment of each objective ID to instructional sections",
    )
    key_points: List[str] = Field(default_factory=list, description="Key takeaways")
    review_questions: List[str] = Field(default_factory=list, description="Review/self-check questions")
    source_chunk_ids: List[str] = Field(
        default_factory=list, description="List of chunk IDs used for grounding this chapter"
    )


# =====================================================================
# 2. Slides Schemas
# =====================================================================


class SlideItem(BaseModel):
    """Single presentation slide."""

    slide_number: int = Field(..., description="Sequential slide number")
    title: str = Field(..., description="Slide title")
    layout_type: Optional[str] = Field("default", description="Slide layout: default, two_column, quote")
    bullet_points: List[str] = Field(default_factory=list, description="Concise bullet points on the slide")
    source_chunk_ids: List[str] = Field(
        default_factory=list, description="List of chunk IDs used for grounding this slide"
    )


class SlidesOutput(BaseModel):
    """Complete generated Presentation Slides."""

    title: str = Field(..., description="Title of the presentation deck")
    slides: List[SlideItem] = Field(default_factory=list, description="List of slides")


# =====================================================================
# 3. Quiz Schemas
# =====================================================================


class QuizOption(BaseModel):
    """Multiple choice option."""

    key: str = Field(..., description="Option letter: A, B, C, or D")
    text: str = Field(..., description="Text content of the option")


class QuizQuestion(BaseModel):
    """Single multiple choice question."""

    question_number: int = Field(..., description="Sequential question number")
    question_text: str = Field(..., description="The question text")
    difficulty: Optional[str] = Field("Medium", description="Bloom taxonomy difficulty: Easy, Medium, Hard")
    options: List[QuizOption] = Field(default_factory=list, description="List of 4 choices (A, B, C, D)")
    correct_answer: str = Field(..., description="The correct option letter (A, B, C, or D)")
    explanation: str = Field("", description="Detailed explanation of why the answer is correct")
    source_chunk_ids: List[str] = Field(
        default_factory=list, description="List of chunk IDs used for grounding this question"
    )


class QuizOutput(BaseModel):
    """Complete generated Multiple Choice Quiz."""

    title: str = Field(..., description="Title of the quiz assessment")
    questions: List[QuizQuestion] = Field(default_factory=list, description="List of quiz questions")


# =====================================================================
# 4. Video Script Schemas
# =====================================================================


class VidDiagramItem(BaseModel):
    """A compact label/detail pair rendered inside a video diagram."""

    label: str = Field(..., min_length=1, max_length=80, description="Short diagram label (<=6 words)")
    detail: Optional[str] = Field(None, max_length=120, description="Optional supporting detail (<=8 words)")

    @field_validator("label")
    @classmethod
    def label_word_limit(cls, value: str) -> str:
        if len(value.split()) > 6:
            raise ValueError("Diagram label must contain at most 6 words")
        return value

    @field_validator("detail")
    @classmethod
    def detail_word_limit(cls, value: Optional[str]) -> Optional[str]:
        if value and len(value.split()) > 8:
            raise ValueError("Diagram detail must contain at most 8 words")
        return value


class VidDiagram(BaseModel):
    """Flat diagram schema keeps structured output portable across routed models."""

    type: Literal["comparison", "flow", "timeline"] = Field(..., description="Diagram layout")
    title: Optional[str] = Field(None, max_length=80, description="Optional short diagram title")
    items: List[VidDiagramItem] = Field(..., min_length=2, max_length=4, description="2-4 diagram items")


class VidScene(BaseModel):
    """Single video scene. Frames stay text-light (heading + a few short keyword bullets) —
    the narration (spoken by TTS) still carries the actual content, matching the NotebookLM-
    style "voice-led, uncluttered frame" aesthetic rather than dense on-screen paragraphs."""

    scene_number: int = Field(..., description="Sequential scene number")
    title: str = Field(..., description="Short on-screen heading for the scene (<=6 words)")
    on_screen_text: Optional[str] = Field(
        "", description="Optional short keyword/phrase shown on screen (<=8 words), may be empty"
    )
    key_points: List[str] = Field(
        default_factory=list,
        description="2-3 short keyword bullets (<=6 words each) shown beneath the heading, "
        "reinforcing what the narration covers; empty list is fine for intro/outro scenes",
    )
    diagram: Optional[VidDiagram] = Field(
        None,
        description="Optional visual diagram; use only when comparison, sequence, or timeline clarifies the scene",
    )
    narration: str = Field(..., description="Voice-over script / narration text, spoken naturally")
    duration_seconds: int = Field(0, description="Actual scene duration in seconds, filled in from TTS audio length")
    source_chunk_ids: List[str] = Field(
        default_factory=list, description="List of chunk IDs used for grounding this scene"
    )


class VidOutput(BaseModel):
    """Complete generated Video Script."""

    title: str = Field(..., description="Title of the video script")
    total_duration_seconds: int = Field(..., description="Total estimated video duration in seconds")
    scenes: List[VidScene] = Field(default_factory=list, description="List of video scenes")




# =====================================================================
# 8. Quality Scoring and Validation
# =====================================================================


class QualityReport(BaseModel):
    """Observable checks only; empirical answer faithfulness is optional by design."""

    structural_validity: int = Field(ge=0, le=100)
    citation_validity: int = Field(ge=0, le=100)
    source_coverage: Optional[int] = Field(default=None, ge=0, le=100)
    extraction_complete: Optional[bool] = None
    faithfulness: Optional[int] = Field(default=None, ge=0, le=100)
    indexed_chunk_count: Optional[int] = Field(default=None, ge=0)
    invalid_citation_count: int = Field(default=0, ge=0)
    missing_citation_count: int = Field(default=0, ge=0)
    labels: List[str] = Field(default_factory=lambda: ["structural checks", "source coverage"])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (int, float)):
            return self.structural_validity == other
        return super().__eq__(other)

    def __gt__(self, other: object) -> bool:
        if isinstance(other, (int, float)):
            return self.structural_validity > other
        return NotImplemented


_CHUNK_MENTION_RE = re.compile(r"\bchunk[_\s]*\d+\b", re.IGNORECASE)


def _strip_chunk_mentions(text: str, label: str, warnings: List[str]) -> str:
    """Defense-in-depth: the prompts forbid the model from naming internal chunk IDs in
    user-facing text (e.g. "Dựa vào chunk_3..."), but strip any that slip through anyway
    rather than leak an internal RAG concept the reader has no context for. Logs a warning
    so drift in prompt compliance shows up in quality_score warnings."""
    if not text or not _CHUNK_MENTION_RE.search(text):
        return text
    warnings.append(f"{label}: rò rỉ tham chiếu chunk nội bộ, đã tự động lọc.")
    return _CHUNK_MENTION_RE.sub("tài liệu", text)


def _check_grounding(
    cited_ids: List[str], valid_ids: set, label: str, warnings: List[str]
) -> Tuple[int, bool]:
    """Validate that cited chunk IDs were actually retrieved, not just present.
    Returns (score_penalty, is_grounded) — a citation pointing at a chunk ID that was
    never retrieved is a hallucinated reference, not grounding, so it costs points
    instead of counting toward the grounding boost."""
    if not cited_ids:
        warnings.append(f"{label} thiếu trích dẫn nguồn.")
        return 0, False
    invalid = [cid for cid in cited_ids if cid not in valid_ids]
    if invalid:
        warnings.append(f"{label} tham chiếu chunk không tồn tại: {invalid}")
        return 5 * len(invalid), False
    return 0, True


def validate_and_score_output(
    data: Any,
    artifact_type: str,
    valid_chunk_ids: List[str] = None,
    unit_valid_chunk_ids: Optional[Mapping[int, List[str]]] = None,
    extraction_complete: Optional[bool] = None,
    indexed_chunk_count: Optional[int] = None,
) -> Tuple[Any, QualityReport, List[str]]:
    """Validate generated structure and citations without claiming factual accuracy.

    Returns:
        tuple[data, quality_report, warnings]
    """
    valid_chunk_ids_set = set(valid_chunk_ids or [])
    warnings: List[str] = []
    base_score = 80  # Start with high baseline for valid schema
    citation_results: List[bool] = []
    valid_cited_ids: set[str] = set()
    invalid_citation_count = 0
    missing_citation_count = 0

    def allowed_for(index: int) -> set[str]:
        if unit_valid_chunk_ids is None:
            return valid_chunk_ids_set
        return set(unit_valid_chunk_ids.get(index, []))

    def check(cited: List[str], index: int, label: str) -> Tuple[int, bool]:
        nonlocal invalid_citation_count, missing_citation_count
        allowed = allowed_for(index)
        if not cited:
            missing_citation_count += 1
        else:
            invalid_citation_count += sum(citation not in allowed for citation in cited)
        penalty, grounded = _check_grounding(cited, allowed, label, warnings)
        citation_results.append(grounded)
        if grounded:
            valid_cited_ids.update(cited)
        return penalty, grounded

    if artifact_type == "book":
        if not isinstance(data, BookOutput):
            data = BookOutput.model_validate(data)
        if not data.chapters:
            warnings.append("Sách không có chương nào.")
            base_score -= 20
        else:
            grounded_items = 0
            for index, ch in enumerate(data.chapters):
                if not ch.chapter_title or not ch.sections:
                    warnings.append(f"Chương '{ch.chapter_title}' thiếu nội dung chi tiết.")
                    base_score -= 5
                label = f"Chương '{ch.chapter_title}'"
                ch.introduction = _strip_chunk_mentions(ch.introduction, label, warnings)
                for sec in ch.sections:
                    sec.content = _strip_chunk_mentions(sec.content, label, warnings)
                ch.key_points = [_strip_chunk_mentions(kp, label, warnings) for kp in ch.key_points]
                ch.review_questions = [_strip_chunk_mentions(q, label, warnings) for q in ch.review_questions]
                penalty, grounded = check(ch.source_chunk_ids, index, f"Chương '{ch.chapter_title}'")
                base_score -= penalty
                if grounded:
                    grounded_items += 1
            # Boost score if well grounded
            if len(data.chapters) > 0 and (grounded_items / len(data.chapters)) >= 0.8:
                base_score += 10

    elif artifact_type == "slides":
        if not isinstance(data, SlidesOutput):
            data = SlidesOutput.model_validate(data)
        if not data.slides:
            warnings.append("Bài giảng không có slide nào.")
            base_score -= 20
        else:
            grounded_items = 0
            for index, sl in enumerate(data.slides):
                if not sl.bullet_points:
                    warnings.append(f"Slide {sl.slide_number} thiếu nội dung bullet points.")
                    base_score -= 5
                label = f"Slide {sl.slide_number}"
                sl.title = _strip_chunk_mentions(sl.title, label, warnings)
                sl.bullet_points = [_strip_chunk_mentions(b, label, warnings) for b in sl.bullet_points]
                penalty, grounded = check(sl.source_chunk_ids, index, f"Slide {sl.slide_number}")
                base_score -= penalty
                if grounded:
                    grounded_items += 1
            if len(data.slides) > 0 and (grounded_items / len(data.slides)) >= 0.8:
                base_score += 10

    elif artifact_type == "quiz":
        if not isinstance(data, QuizOutput):
            data = QuizOutput.model_validate(data)
        if not data.questions:
            warnings.append("Bộ đề trắc nghiệm không có câu hỏi nào.")
            base_score -= 20
        else:
            grounded_items = 0
            for index, q in enumerate(data.questions):
                if len(q.options) != 4:
                    warnings.append(f"Câu hỏi {q.question_number} không đủ 4 lựa chọn.")
                    base_score -= 10
                if q.correct_answer not in ["A", "B", "C", "D"]:
                    warnings.append(f"Câu hỏi {q.question_number} có đáp án đúng không hợp lệ: {q.correct_answer}")
                    base_score -= 10
                label = f"Câu hỏi {q.question_number}"
                q.question_text = _strip_chunk_mentions(q.question_text, label, warnings)
                q.explanation = _strip_chunk_mentions(q.explanation, label, warnings)
                for opt in q.options:
                    opt.text = _strip_chunk_mentions(opt.text, label, warnings)
                penalty, grounded = check(q.source_chunk_ids, index, f"Câu hỏi {q.question_number}")
                base_score -= penalty
                if grounded:
                    grounded_items += 1
            if len(data.questions) > 0 and (grounded_items / len(data.questions)) >= 0.8:
                base_score += 10

    elif artifact_type == "vid":
        if not isinstance(data, VidOutput):
            data = VidOutput.model_validate(data)
        if not data.scenes:
            warnings.append("Kịch bản video không có phân cảnh nào.")
            base_score -= 20
        else:
            grounded_items = 0
            for index, sc in enumerate(data.scenes):
                if not sc.narration or len(sc.narration.split()) < 5:
                    warnings.append(f"Phân cảnh {sc.scene_number} thiếu lời đọc hoặc quá ngắn.")
                    base_score -= 5
                label = f"Phân cảnh {sc.scene_number}"
                sc.title = _strip_chunk_mentions(sc.title, label, warnings)
                sc.on_screen_text = _strip_chunk_mentions(sc.on_screen_text or "", label, warnings)
                sc.key_points = [_strip_chunk_mentions(kp, label, warnings) for kp in sc.key_points]
                sc.narration = _strip_chunk_mentions(sc.narration, label, warnings)
                penalty, grounded = check(sc.source_chunk_ids, index, f"Phân cảnh {sc.scene_number}")
                base_score -= penalty
                if grounded:
                    grounded_items += 1
            if len(data.scenes) > 0 and (grounded_items / len(data.scenes)) >= 0.8:
                base_score += 10



    # Clamp score between 0 and 100
    structural_validity = max(0, min(100, base_score))
    citation_validity = (
        round(100 * sum(citation_results) / len(citation_results)) if citation_results else 0
    )
    source_coverage = (
        round(100 * len(valid_cited_ids) / len(valid_chunk_ids_set)) if valid_chunk_ids_set else None
    )
    report = QualityReport(
        structural_validity=structural_validity,
        citation_validity=citation_validity,
        source_coverage=source_coverage,
        extraction_complete=extraction_complete,
        faithfulness=None,
        indexed_chunk_count=indexed_chunk_count,
        invalid_citation_count=invalid_citation_count,
        missing_citation_count=missing_citation_count,
    )
    return data, report, warnings
