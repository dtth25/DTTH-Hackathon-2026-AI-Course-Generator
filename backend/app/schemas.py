from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class WorkedExample(BaseModel):
    title: str = Field(..., description="Tên ví dụ ngắn")
    problem: str = Field(..., description="Đề bài hoặc tình huống")
    solution_steps: List[str] = Field(default_factory=list, description="Các bước giải thích")
    final_answer: str = Field(..., description="Kết luận cuối")
    page_reference: str = Field(..., description="Ví dụ: Trang 3")


class CheckpointQuestion(BaseModel):
    question: str = Field(..., description="Câu hỏi kiểm tra nhanh trong bài học")
    expected_answer: str = Field(..., description="Đáp án kỳ vọng ngắn")


class Lesson(BaseModel):
    title: str = Field(..., description="Tên bài học ngắn gọn")
    learning_objectives: List[str] = Field(default_factory=list, description="Mục tiêu học tập đo được")
    prerequisites: List[str] = Field(default_factory=list, description="Kiến thức cần biết trước")
    big_picture: str = Field(..., description="Bức tranh tổng quan/tại sao cần học")
    core_theory: str = Field(..., description="Lý thuyết chính, viết như bài giảng đại học")
    derivation_or_reasoning: str = Field(..., description="Diễn giải logic, chứng minh, hoặc cách suy ra")
    worked_examples: List[WorkedExample] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list, description="Lỗi sai thường gặp")
    checkpoints: List[CheckpointQuestion] = Field(default_factory=list)
    summary: str = Field(..., description="Tóm tắt cuối bài")
    further_practice: List[str] = Field(default_factory=list, description="Gợi ý bài tập/luyện tập tiếp")
    page_reference: str = Field(..., description="Ví dụ: Trang 3, Trang 4")


class Flashcard(BaseModel):
    id: int
    front: str
    back: str
    hint: str
    topic: str
    difficulty: Literal["Dễ", "Trung bình", "Khó"]
    tags: List[str] = Field(default_factory=list)
    page_reference: str

    @field_validator("id")
    @classmethod
    def positive_flashcard_id(cls, value: int) -> int:
        if value < 1:
            raise ValueError("flashcard id phải bắt đầu từ 1")
        return value


class AnswerOptions(BaseModel):
    """Fixed A/B/C/D object to avoid JSON Schema additionalProperties."""

    A: str
    B: str
    C: str
    D: str


class QuizQuestion(BaseModel):
    id: int
    question: str
    options: AnswerOptions
    correct_answer: Literal["A", "B", "C", "D"]
    hint: str
    explanation: str
    difficulty: Literal["Dễ", "Trung bình", "Khó"]
    page_reference: str

    @field_validator("id")
    @classmethod
    def positive_id(cls, value: int) -> int:
        if value < 1:
            raise ValueError("quiz id phải bắt đầu từ 1")
        return value


class SlideItem(BaseModel):
    title: str
    subtitle: str
    bullets: List[str]
    math_or_key_formula: str = Field(..., description="Công thức/ký hiệu quan trọng, nếu không có ghi chuỗi rỗng")
    speaker_note: str
    page_reference: str


class GlossaryItem(BaseModel):
    term: str
    definition: str
    page_reference: str


class QualityReport(BaseModel):
    coverage_score: int = Field(..., ge=0, le=100)
    strengths: List[str] = Field(default_factory=list)
    missing_or_weak_points: List[str] = Field(default_factory=list)
    suggested_next_improvements: List[str] = Field(default_factory=list)


class Course(BaseModel):
    title: str
    subject: str
    source_file: str
    summary: str
    recommended_level: str
    course_goals: List[str]
    lessons: List[Lesson]
    flashcards: List[Flashcard]
    quizzes: List[QuizQuestion]
    slide_outline: List[SlideItem]
    slides_marp: str = Field(..., description="Marp markdown source for academic slides")
    slides_latex_beamer: str = Field(..., description="LaTeX Beamer source, Overleaf-like")
    glossary: List[GlossaryItem]
    teacher_notes: str
    audio_script: str
    quality_report: QualityReport


class CourseResponse(BaseModel):
    status: Literal["success"]
    message: str
    course: Course
    # This response model is for FastAPI only, not sent to Gemini.
    debug: dict


class ErrorResponse(BaseModel):
    status: Literal["error"]
    message: str
    detail: Optional[dict] = None
