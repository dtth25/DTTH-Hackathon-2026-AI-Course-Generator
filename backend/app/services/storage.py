import json
from datetime import datetime
from pathlib import Path

from backend.app.schemas import Course, Lesson
from backend.app.services.text_utils import safe_filename


def save_uploaded_file(upload_dir: Path, filename: str, content: bytes) -> Path:
    safe_name = safe_filename(filename) + Path(filename).suffix.lower()
    path = upload_dir / safe_name
    counter = 1
    while path.exists():
        path = upload_dir / f"{safe_filename(filename)}_{counter}{Path(filename).suffix.lower()}"
        counter += 1
    path.write_bytes(content)
    return path


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _lesson_to_markdown(lesson: Lesson, index: int) -> str:
    lines: list[str] = []
    lines.append(f"# Bài {index}: {lesson.title}")
    lines.append("")
    lines.append(f"Nguồn: {lesson.page_reference}")
    lines.append("")
    lines.append("## Mục tiêu học tập")
    lines.extend(f"- {item}" for item in lesson.learning_objectives)
    lines.append("")
    lines.append("## Kiến thức cần biết trước")
    lines.extend(f"- {item}" for item in lesson.prerequisites)
    lines.append("")
    lines.append("## Bức tranh lớn")
    lines.append(lesson.big_picture)
    lines.append("")
    lines.append("## Lý thuyết cốt lõi")
    lines.append(lesson.core_theory)
    lines.append("")
    lines.append("## Diễn giải / Suy luận")
    lines.append(lesson.derivation_or_reasoning)
    lines.append("")
    lines.append("## Ví dụ mẫu")
    for example in lesson.worked_examples:
        lines.append(f"### {example.title}")
        lines.append(f"**Bài toán:** {example.problem}")
        for step_no, step in enumerate(example.solution_steps, start=1):
            lines.append(f"{step_no}. {step}")
        lines.append(f"**Kết luận:** {example.final_answer}")
        lines.append(f"Nguồn: {example.page_reference}")
        lines.append("")
    lines.append("## Lỗi thường gặp")
    lines.extend(f"- {item}" for item in lesson.common_mistakes)
    lines.append("")
    lines.append("## Checkpoint")
    for cp in lesson.checkpoints:
        lines.append(f"- **Hỏi:** {cp.question}")
        lines.append(f"  **Đáp án kỳ vọng:** {cp.expected_answer}")
    lines.append("")
    lines.append("## Tóm tắt")
    lines.append(lesson.summary)
    lines.append("")
    lines.append("## Luyện tập thêm")
    lines.extend(f"- {item}" for item in lesson.further_practice)
    lines.append("")
    return "\n".join(lines)


def save_course_package(courses_dir: Path, course: Course, original_filename: str) -> Path:
    """Save a maintainable course package instead of one opaque JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    course_slug = f"{safe_filename(original_filename)}_{timestamp}"
    root = courses_dir / course_slug
    lessons_dir = root / "lessons"
    slides_dir = root / "slides"
    root.mkdir(parents=True, exist_ok=True)
    lessons_dir.mkdir(parents=True, exist_ok=True)
    slides_dir.mkdir(parents=True, exist_ok=True)

    data = course.model_dump()
    _write_json(root / "course.json", data)
    _write_json(root / "flashcards.json", data["flashcards"])
    _write_json(root / "quizzes.json", data["quizzes"])
    _write_json(root / "glossary.json", data["glossary"])
    _write_json(root / "quality_report.json", data["quality_report"])

    for index, lesson in enumerate(course.lessons, start=1):
        lesson_path = lessons_dir / f"lesson_{index:02d}.md"
        lesson_path.write_text(_lesson_to_markdown(lesson, index), encoding="utf-8")

    (slides_dir / "slides.md").write_text(course.slides_marp, encoding="utf-8")
    (slides_dir / "slides.tex").write_text(course.slides_latex_beamer, encoding="utf-8")
    (root / "teacher_notes.md").write_text(course.teacher_notes, encoding="utf-8")
    (root / "audio_script.md").write_text(course.audio_script, encoding="utf-8")

    return root


# Backward-compatible name for older code/tests.
def save_course_json(courses_dir: Path, course: Course, original_filename: str) -> Path:
    return save_course_package(courses_dir, course, original_filename) / "course.json"
