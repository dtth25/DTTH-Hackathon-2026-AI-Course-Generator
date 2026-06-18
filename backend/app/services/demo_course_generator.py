from __future__ import annotations

import re
from pathlib import Path

from backend.app.schemas import (
    AnswerOptions,
    CheckpointQuestion,
    Course,
    Flashcard,
    GlossaryItem,
    Lesson,
    QualityReport,
    QuizQuestion,
    SlideItem,
    WorkedExample,
)


def _clean(value: str, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def _extract_pages(context: str) -> list[tuple[int, str]]:
    pattern = re.compile(
        r"\[MÃ ĐỊNH DANH TRANG:\s*(\d+)\].*?NỘI DUNG:\s*(.*?)(?==== KẾT THÚC DỮ LIỆU TRANG|\Z)",
        re.S,
    )
    pages: list[tuple[int, str]] = []
    for match in pattern.finditer(context):
        page_no = int(match.group(1))
        text = _clean(match.group(2), 1200)
        if text:
            pages.append((page_no, text))
    return pages or [(1, _clean(context, 1200) or "Tài liệu đã được tải lên nhưng nội dung trích xuất còn hạn chế.")]


def _sentences(text: str, count: int = 6) -> list[str]:
    chunks = re.split(r"(?<=[.!?。])\s+|\n+", text)
    result = [_clean(chunk, 180) for chunk in chunks if len(_clean(chunk, 180)) > 25]
    return result[:count] or [_clean(text, 180)]


def build_demo_course(context: str, source_file: str, reason: str = "Demo fallback") -> Course:
    """Build a valid local course when Gemini is unavailable.

    The output is intentionally marked as fallback so the user knows it is not
    the full Gemini-generated course. It still lets the hackathon UI run end to end.
    """
    pages = _extract_pages(context)
    first_text = pages[0][1]
    title_base = Path(source_file).stem.replace("_", " ").replace("-", " ").strip() or "Tài liệu tải lên"
    key_sentences = _sentences(" ".join(text for _, text in pages[:3]), 8)

    topic = title_base.title()
    page_refs = [f"Trang {page_no}" for page_no, _ in pages[:4]]
    while len(page_refs) < 4:
        page_refs.append(page_refs[-1])

    lessons: list[Lesson] = []
    lesson_titles = [
        "Bức tranh tổng quan của tài liệu",
        "Khái niệm và luận điểm cốt lõi",
        "Cách đọc, phân tích và áp dụng nội dung",
        "Ôn tập, lỗi thường gặp và hướng học tiếp",
    ]
    for idx, lesson_title in enumerate(lesson_titles):
        page_ref = page_refs[min(idx, len(page_refs) - 1)]
        basis = key_sentences[idx % len(key_sentences)]
        lessons.append(
            Lesson(
                title=lesson_title,
                learning_objectives=[
                    f"Nắm được ý chính của phần: {lesson_title.lower()}.",
                    "Biết liên hệ nội dung với ngữ cảnh trong tài liệu gốc.",
                    "Tự trả lời được câu hỏi kiểm tra nhanh sau bài học.",
                ],
                prerequisites=[
                    "Đã đọc lướt tài liệu gốc một lần.",
                    "Biết ghi chú các từ khóa và luận điểm quan trọng.",
                ],
                big_picture=(
                    f"Phần này giúp người học định vị nội dung của '{topic}' trong toàn bộ tài liệu. "
                    "Thay vì học thuộc từng đoạn, người học cần hiểu vai trò của khái niệm, ví dụ và mối liên hệ giữa các ý."
                ),
                core_theory=(
                    f"Ý chính trích xuất từ tài liệu: {basis}\n\n"
                    "Khi biến tài liệu thành bài giảng, cần tách thông tin thành: khái niệm, điều kiện áp dụng, ví dụ minh họa và lỗi dễ gặp. "
                    "Đây là bản fallback local; khi Gemini API hoạt động, phần này sẽ được viết sâu hơn và bám sát tài liệu hơn."
                ),
                derivation_or_reasoning=(
                    "Cách đọc đề xuất: (1) xác định từ khóa, (2) tìm câu định nghĩa hoặc luận điểm chính, "
                    "(3) kiểm tra ví dụ hoặc bằng chứng đi kèm, (4) tự đặt câu hỏi vì sao nội dung đó quan trọng."
                ),
                worked_examples=[
                    WorkedExample(
                        title="Ví dụ phân tích một ý trong tài liệu",
                        problem=f"Từ đoạn: '{basis}', hãy rút ra ý chính cần nhớ.",
                        solution_steps=[
                            "Gạch chân danh từ hoặc thuật ngữ trung tâm.",
                            "Tìm động từ/mối quan hệ mô tả điều gì xảy ra với thuật ngữ đó.",
                            "Viết lại bằng một câu ngắn theo ngôn ngữ của mình.",
                        ],
                        final_answer=f"Ý cần nhớ: {basis}",
                        page_reference=page_ref,
                    )
                ],
                common_mistakes=[
                    "Chép lại nguyên đoạn dài mà không tách ý chính.",
                    "Nhầm ví dụ minh họa với định nghĩa cốt lõi.",
                    "Không ghi nguồn trang nên khó kiểm chứng lại.",
                ],
                checkpoints=[
                    CheckpointQuestion(
                        question="Ý chính nhất của phần này là gì?",
                        expected_answer="Nêu được khái niệm hoặc luận điểm trung tâm bằng một câu ngắn.",
                    ),
                    CheckpointQuestion(
                        question="Trang nguồn nào hỗ trợ cho phần này?",
                        expected_answer=page_ref,
                    ),
                ],
                summary=f"Bài này giúp hệ thống hóa một phần quan trọng của tài liệu '{topic}' và chuẩn bị cho flashcard/quiz.",
                further_practice=[
                    "Tự tạo thêm 3 câu hỏi vì sao từ phần này.",
                    "Tìm một ví dụ trong tài liệu gốc và giải thích lại bằng lời của mình.",
                ],
                page_reference=page_ref,
            )
        )

    flashcards = [
        Flashcard(
            id=i + 1,
            front=f"Ý chính #{i + 1} của tài liệu là gì?",
            back=key_sentences[i % len(key_sentences)],
            hint="Nhớ lại câu/đoạn được trích từ tài liệu.",
            topic=topic,
            difficulty="Dễ" if i < 4 else "Trung bình",
            tags=["fallback", "active-recall", "source-based"],
            page_reference=page_refs[i % len(page_refs)],
        )
        for i in range(12)
    ]

    quizzes = [
        QuizQuestion(
            id=i + 1,
            question=f"Theo tài liệu, ý nào sau đây gần nhất với nội dung cần nhớ #{i + 1}?",
            options=AnswerOptions(
                A=key_sentences[i % len(key_sentences)],
                B="Một nhận định không được chứng minh trong tài liệu.",
                C="Một ví dụ ngoài tài liệu không có nguồn trang.",
                D="Một kết luận quá rộng so với dữ liệu được trích xuất.",
            ),
            correct_answer="A",
            hint="Chọn phương án bám sát đoạn trích từ tài liệu nhất.",
            explanation="Phương án A bám sát nội dung trích xuất từ tài liệu. Các phương án còn lại hoặc không có nguồn, hoặc suy diễn quá rộng.",
            difficulty="Dễ" if i < 5 else "Trung bình",
            page_reference=page_refs[i % len(page_refs)],
        )
        for i in range(10)
    ]

    slide_outline = [
        SlideItem(
            title="Course overview",
            subtitle=f"Từ PDF '{source_file}' sang học phần có cấu trúc",
            bullets=[
                "Xác định mục tiêu học tập chính",
                "Tách nội dung thành bài học, flashcard và quiz",
                "Giữ nguồn trang để kiểm chứng",
            ],
            math_or_key_formula="",
            speaker_note="Mở đầu bằng lý do cần biến tài liệu thành cấu trúc học tập thay vì chỉ đọc PDF thụ động.",
            page_reference=page_refs[0],
        ),
        SlideItem(
            title="Key source ideas",
            subtitle="Các ý quan trọng được trích xuất tự động",
            bullets=key_sentences[:4],
            math_or_key_formula="",
            speaker_note="Giảng viên đi qua từng ý và yêu cầu người học tìm lại vị trí trong tài liệu gốc.",
            page_reference=page_refs[0],
        ),
        SlideItem(
            title="How to study this document",
            subtitle="Explain → Demonstrate → Check → Summarize",
            bullets=[
                "Đọc để tìm khái niệm trung tâm",
                "Chuyển ý chính thành câu hỏi active recall",
                "Dùng quiz để kiểm tra hiểu thật",
                "Quay lại trang nguồn khi trả lời sai",
            ],
            math_or_key_formula="Study loop = Read → Recall → Test → Review",
            speaker_note="Nhấn mạnh vòng lặp học chủ động và vai trò của page reference.",
            page_reference=page_refs[0],
        ),
        SlideItem(
            title="Summary and next steps",
            subtitle="Cách nâng cấp bản fallback thành course thật",
            bullets=[
                "Dùng Gemini API key hợp lệ để tạo bài giảng sâu hơn",
                "Dùng PDF có text copy được hoặc bật OCR cho scan",
                "Kiểm tra quality report sau khi tạo course",
            ],
            math_or_key_formula="",
            speaker_note="Kết thúc bằng checklist vận hành: key, PDF text, OCR và kiểm tra chất lượng.",
            page_reference=page_refs[0],
        ),
    ]

    slides_marp = f"""---
marp: true
theme: studyhack-academic
paginate: true
size: 16:9
---
<style>
section {{ font-family: Inter, Arial, sans-serif; background: #f7f8fb; color: #111827; }}
h1 {{ color: #1f2a60; }}
strong {{ color: #0f766e; }}
.callout {{ background: #eef2ff; border-left: 6px solid #1f2a60; padding: 16px; border-radius: 10px; }}
</style>

# {topic}

**Demo fallback course**  
Nguồn: `{source_file}`

---

# Key source ideas

""" + "\n".join(f"- {item}" for item in key_sentences[:5]) + "\n\n---\n\n# Study loop\n\n<div class=\"callout\">Read → Recall → Test → Review</div>\n\n- Tách ý chính\n- Tạo flashcard\n- Làm quiz\n- Quay lại trang nguồn\n"

    slides_latex_beamer = f"""\\documentclass[aspectratio=169]{{beamer}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath, amssymb, booktabs, tcolorbox}}
\\usetheme{{Madrid}}
\\definecolor{{studyhacknavy}}{{RGB}}{{31,42,96}}
\\setbeamercolor{{frametitle}}{{fg=white,bg=studyhacknavy}}
\\title{{{topic}}}
\\subtitle{{Demo fallback course from {source_file}}}
\\author{{StudyHack.AI}}
\\date{{}}
\\begin{{document}}
\\begin{{frame}}
  \\titlepage
\\end{{frame}}
\\begin{{frame}}{{Key source ideas}}
\\begin{{itemize}}
""" + "\n".join(f"  \\item {_clean(item, 110)}" for item in key_sentences[:5]) + "\n\\end{itemize}\n% Speaker note: Use this slide to ask students to locate the source page.\n\\end{frame}\n\\end{document}\n"

    return Course(
        title=f"{topic} — Course Package",
        subject="Tự động nhận diện từ PDF",
        source_file=source_file,
        summary=(
            f"Đây là course package fallback được tạo local từ PDF '{source_file}'. "
            "Nội dung dùng các đoạn text trích xuất được để dựng bài học, flashcard, quiz và slide. "
            f"Lý do dùng fallback: {reason}. Khi Gemini API hoạt động, hệ thống sẽ tạo bài giảng sâu và chính xác hơn."
        ),
        recommended_level="Tự học / lớp học phổ thông hoặc đại học nhập môn",
        course_goals=[
            "Nắm được các ý chính trong tài liệu gốc.",
            "Biết chuyển nội dung PDF thành câu hỏi active recall.",
            "Sử dụng page reference để kiểm chứng câu trả lời.",
            "Chuẩn bị dữ liệu để nâng cấp thành course AI đầy đủ.",
        ],
        lessons=lessons,
        flashcards=flashcards,
        quizzes=quizzes,
        slide_outline=slide_outline,
        slides_marp=slides_marp,
        slides_latex_beamer=slides_latex_beamer,
        glossary=[
            GlossaryItem(term="Course package", definition="Bộ dữ liệu gồm bài học, slide, quiz, flashcard và ghi chú giảng dạy.", page_reference=page_refs[0]),
            GlossaryItem(term="Active recall", definition="Cách học bằng việc tự gợi nhớ thay vì chỉ đọc lại.", page_reference=page_refs[0]),
            GlossaryItem(term="Page reference", definition="Nguồn trang giúp kiểm chứng nội dung với PDF gốc.", page_reference=page_refs[0]),
        ],
        teacher_notes=(
            "Bản fallback này dùng để kiểm tra luồng upload và giao diện. Khi dùng key Gemini hợp lệ, hãy chạy lại để có bài giảng sâu hơn. "
            "Nếu PDF là scan ảnh, bật OCR hoặc dùng PDF có thể copy text."
        ),
        audio_script=(
            f"Hôm nay chúng ta ôn nhanh tài liệu {topic}. Trọng tâm là xác định ý chính, biến chúng thành câu hỏi gợi nhớ, "
            "làm quiz kiểm tra và quay lại nguồn trang khi cần kiểm chứng."
        ),
        quality_report=QualityReport(
            coverage_score=55,
            strengths=[
                "Upload và trích xuất PDF đã hoạt động.",
                "Course package hợp lệ để frontend hiển thị đầy đủ tab.",
                "Có page reference và dữ liệu maintainable.",
            ],
            missing_or_weak_points=[
                "Đây là fallback local, chưa phải bài giảng Gemini đầy đủ.",
                "Slide và lesson chưa sâu bằng output AI thật.",
                f"Nguyên nhân fallback: {reason}",
            ],
            suggested_next_improvements=[
                "Dùng Gemini API key hợp lệ, thường bắt đầu bằng AIzaSy...",
                "Dùng PDF có text copy được hoặc bật OCR cho PDF scan.",
                "Chạy lại upload để tạo course AI hoàn chỉnh.",
            ],
        ),
    )
