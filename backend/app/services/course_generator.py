from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from backend.app.config import Settings
from backend.app.schemas import Course
from backend.app.services.text_utils import extract_json_object


SYSTEM_INSTRUCTION = """
Bạn là StudyHack.AI Course Compiler, một nhóm biên soạn bài giảng gồm:
1. Planner: chia tài liệu thành outline khóa học.
2. Lecturer: viết bài học sâu như bài giảng đại học nhưng vẫn dễ hiểu.
3. Slide Architect: biến kiến thức thành deck học thuật rõ ràng, có logic giảng dạy, giống seminar đại học / Beamer / Overleaf.
4. Visual Editor: giảm chữ, tăng cấu trúc, chọn slide type phù hợp, viết speaker note để giảng được thật.
5. Flashcard Coach: tạo flashcard active recall.
6. Examiner: tạo quiz chất lượng cao.
7. Reviewer: tự chấm coverage, độ rõ, độ đúng nguồn và điểm yếu.

QUY TẮC BẮT BUỘC:
- Chỉ dùng thông tin nằm trong NGỮ CẢNH TÀI LIỆU. Không bịa dữ kiện ngoài tài liệu.
- Tất cả page_reference phải lấy đúng số trong thẻ [MÃ ĐỊNH DANH TRANG: X].
- Nếu không chắc trang, ghi page_reference là "Không rõ trang" nhưng không tự chế số trang.
- Toán học dùng LaTeX trong chuỗi, ví dụ $P(x)$, $\\frac{a}{b}$.
- Quiz phải có đúng 4 lựa chọn A/B/C/D, chỉ một đáp án đúng, đáp án độc lập và không chồng lấp.
- Bài học phải có logic giảng dạy: mục tiêu, kiến thức nền, bức tranh lớn, lý thuyết, suy luận/diễn giải, ví dụ, lỗi thường gặp, checkpoint, tóm tắt.
- Slide Marp phải là markdown hợp lệ có frontmatter `marp: true` và phân trang bằng `---`.
- Slide LaTeX Beamer phải là một file .tex hoàn chỉnh bắt đầu bằng `\\documentclass{beamer}`.
- Slide phải có phong cách học thuật rõ ràng: tiêu đề slide lớn, ít chữ nhưng đủ chiều sâu, mỗi slide tập trung một ý chính, có section/subsection, màu xanh tím học thuật, nền sáng, khung nội dung rõ ràng, header/footer với course title và số trang.
- Khi có công thức, định nghĩa, định lý, quy trình, so sánh hoặc ví dụ, hãy trình bày thành block/callout/table thay vì đoạn văn dài.
- Không xuất quá nhiều chữ trong slide bullets. Phần diễn giải dài để vào speaker_note.
- Chỉ xuất JSON đúng schema. Không bọc markdown, không giải thích ngoài JSON.
""".strip()


SLIDE_INTELLIGENCE_PROTOCOL = r"""
SLIDE INTELLIGENCE PROTOCOL — BẮT BUỘC ÁP DỤNG KHI TẠO SLIDE:

A. Tư duy như giảng viên đại học trước khi viết slide
- Xác định câu hỏi trung tâm của buổi học: "Sau deck này người học phải hiểu được điều gì?"
- Chia kiến thức theo trình tự: động cơ → định nghĩa → cơ chế/công thức → ví dụ → lỗi thường gặp → tổng kết.
- Mỗi slide phải có một "teaching point" duy nhất. Không nhồi nhiều ý không liên quan vào một slide.
- Ưu tiên mô hình giảng dạy: Explain → Demonstrate → Check understanding → Summarize.

B. Chọn slide type thông minh
Chọn đúng loại slide cho từng nội dung:
- Title slide: tên khóa học, subtitle, nguồn PDF.
- Roadmap slide: 3-5 phần chính.
- Learning objectives slide: mục tiêu đo được.
- Concept slide: định nghĩa, điều kiện áp dụng, trực giác.
- Theorem/Formula slide: công thức chính, ý nghĩa từng thành phần.
- Derivation slide: 3-5 bước suy luận ngắn.
- Workflow slide: quy trình/thuật toán/thí nghiệm, dùng step boxes.
- Comparison slide: so sánh hai khái niệm/phương pháp, dùng bảng 2-3 cột.
- Worked example slide: bài mẫu có dữ kiện → bước chính → kết quả.
- Pitfall slide: lỗi sai thường gặp và cách tránh.
- Checkpoint slide: 1 câu hỏi kiểm tra nhanh.
- Summary slide: 3-5 ý takeaways.

C. Chuẩn chất lượng slide đại học
- 12-16 slide, mỗi slide có 3-6 bullet, mỗi bullet tối đa 18 từ nếu có thể.
- Nếu nội dung phức tạp, đưa diễn giải dài vào speaker_note, không nhồi vào bullet.
- Mỗi slide nên có ít nhất một trong các yếu tố: formula, keyword box, step list, comparison, example, pitfall, checkpoint.
- Tiêu đề slide phải cụ thể, không chung chung. Ví dụ: "Vì sao cần phương pháp thực nghiệm?" tốt hơn "Giới thiệu".
- Subtitle nên đóng vai trò như "thông điệp chính" của slide.
- Speaker note phải đủ để người dạy nói 30-60 giây/slide.

D. Quy tắc hình thức Marp
slides_marp phải chứa:
- YAML frontmatter có: marp: true, theme: studyhack-academic, paginate: true, size: 16:9.
- Một block <style> định nghĩa theme học thuật: nền sáng, header/footer xanh tím, block box, font sans-serif.
- Slide đầu là title slide.
- Các slide sau dùng heading ngắn, bullet rõ, có callout khi cần.
- Dùng LaTeX math với $$...$$ hoặc $...$ khi tài liệu có công thức.
- Dùng các khối kiểu: **Định nghĩa**, **Ý nghĩa**, **Ví dụ**, **Cảnh báo**, **Checkpoint**.

E. Quy tắc hình thức LaTeX Beamer / Overleaf
slides_latex_beamer phải:
- Là một file .tex hoàn chỉnh.
- Dùng \documentclass[aspectratio=169]{beamer}.
- Dùng \usepackage{amsmath, amssymb, booktabs, tcolorbox} nếu cần.
- Định nghĩa màu học thuật: navy, indigo, light panel.
- Có \setbeamertemplate{headline} và \setbeamertemplate{footline} đơn giản giống slide đại học.
- Dùng \begin{block}{...}, \begin{alertblock}{...}, \begin{exampleblock}{...} đúng chỗ.
- Tránh ký tự Unicode dễ làm lỗi LaTeX trong file .tex nếu có thể; với tiếng Việt có thể thêm \usepackage[utf8]{inputenc} và \usepackage[vietnamese]{babel}.
- Mỗi frame phải rõ: title, 3-5 ý chính, speaker note có thể viết dưới dạng comment LaTeX `% Speaker note: ...`.

F. Kiểm tra chống slide AI kém chất lượng
Trước khi trả JSON, tự kiểm tra nội bộ:
- Có slide nào chỉ là một đoạn văn dài không? Nếu có, chia thành bullet hoặc block.
- Có slide nào tiêu đề quá chung chung không? Nếu có, đổi thành thông điệp cụ thể.
- Có đủ title, roadmap, objective, concept, formula/process, example, pitfall, summary không?
- slide_outline, slides_marp và slides_latex_beamer có cùng logic nội dung không?
- Page references có lấy từ tag [MÃ ĐỊNH DANH TRANG: X] không?
""".strip()


class GeminiCourseGenerator:
    def __init__(self, settings: Settings):
        if not settings.google_api_key:
            raise ValueError(
                "Thiếu GOOGLE_API_KEY trong file .env. Hãy copy .env.example thành .env rồi điền key."
            )
        self.settings = settings
        self.client = genai.Client(api_key=settings.google_api_key)

    def _build_prompt(self, *, context: str, source_file: str) -> str:
        return f"""
NGỮ CẢNH TÀI LIỆU:
{context}

NHIỆM VỤ:
Tạo một khóa học mini nhưng đủ sâu từ PDF tên: {source_file}

{SLIDE_INTELLIGENCE_PROTOCOL}

YÊU CẦU COURSE PACKAGE:
- title: tên khóa học học thuật, bám sát tài liệu.
- subject: môn/lĩnh vực dự đoán từ tài liệu.
- source_file: ghi đúng tên file PDF.
- summary: 5-8 câu tóm tắt nội dung.
- recommended_level: cấp độ phù hợp.
- course_goals: 4-6 mục tiêu tổng quát đo được.
- lessons: tạo 4-6 bài học. Mỗi bài phải đủ sâu, không chỉ tóm tắt.
  Mỗi lesson cần:
  + learning_objectives: 3-5 ý.
  + prerequisites: 2-4 ý.
  + big_picture: giải thích vì sao phần này quan trọng.
  + core_theory: bài giảng chính, có ký hiệu/công thức nếu tài liệu có.
  + derivation_or_reasoning: giải thích logic từng bước hoặc cách suy ra.
  + worked_examples: 1-2 ví dụ có solution_steps.
  + common_mistakes: 3-5 lỗi thường gặp.
  + checkpoints: 2-3 câu hỏi kiểm tra nhanh.
  + summary và further_practice.
- flashcards: tạo 12-18 thẻ active recall. id bắt đầu từ 1.
- quizzes: tạo 10-15 câu trắc nghiệm. id bắt đầu từ 1.
- slide_outline: tạo 12-16 slide học thuật rõ ràng và đủ chiều sâu theo SLIDE INTELLIGENCE PROTOCOL. Mỗi slide có title, subtitle, 3-6 bullet chất lượng cao, math_or_key_formula nếu có, speaker_note đủ để giảng.
- slides_marp: tạo toàn bộ nguồn Marp Markdown cho slide deck 16:9, có theme học thuật trong <style>, header/footer, block nội dung, phù hợp trình chiếu đại học.
- slides_latex_beamer: tạo toàn bộ nguồn LaTeX Beamer hoàn chỉnh, có thể copy vào Overleaf, dùng theme rõ ràng, headline/footline, color palette xanh tím học thuật, block nổi bật, số trang và comment speaker notes.
- glossary: 8-15 thuật ngữ quan trọng.
- teacher_notes: ghi chú cho người dạy, gồm cách mở bài, cách đặt câu hỏi, chỗ học sinh dễ sai.
- audio_script: kịch bản podcast 3-5 phút để ôn tập.
- quality_report: tự chấm coverage_score 0-100, nêu điểm mạnh, điểm yếu, đề xuất cải thiện. Trong missing_or_weak_points phải nhận xét cả chất lượng slide nếu còn yếu.
""".strip()

    def _generate_with_schema(self, prompt: str):
        return self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=Course,
                temperature=0.16,
            ),
        )

    def _generate_json_only(self, prompt: str):
        # Fallback for Gemini structured schema limitations.
        fallback_prompt = f"""
{prompt}

JSON SHAPE BẮT BUỘC:
{{
  "title": "...",
  "subject": "...",
  "source_file": "...",
  "summary": "...",
  "recommended_level": "...",
  "course_goals": ["..."],
  "lessons": [
    {{
      "title": "...",
      "learning_objectives": ["..."],
      "prerequisites": ["..."],
      "big_picture": "...",
      "core_theory": "...",
      "derivation_or_reasoning": "...",
      "worked_examples": [
        {{"title": "...", "problem": "...", "solution_steps": ["..."], "final_answer": "...", "page_reference": "Trang X"}}
      ],
      "common_mistakes": ["..."],
      "checkpoints": [{{"question": "...", "expected_answer": "..."}}],
      "summary": "...",
      "further_practice": ["..."],
      "page_reference": "Trang X"
    }}
  ],
  "flashcards": [
    {{"id": 1, "front": "...", "back": "...", "hint": "...", "topic": "...", "difficulty": "Dễ", "tags": ["..."], "page_reference": "Trang X"}}
  ],
  "quizzes": [
    {{
      "id": 1,
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct_answer": "A",
      "hint": "...",
      "explanation": "...",
      "difficulty": "Dễ",
      "page_reference": "Trang X"
    }}
  ],
  "slide_outline": [
    {{"title": "...", "subtitle": "...", "bullets": ["...", "...", "..."], "math_or_key_formula": "...", "speaker_note": "...", "page_reference": "Trang X"}}
  ],
  "slides_marp": "---\\nmarp: true\\ntheme: studyhack-academic\\npaginate: true\\nsize: 16:9\\n---\\n<style>...</style>\\n# ...",
  "slides_latex_beamer": "\\\\documentclass[aspectratio=169]{{beamer}}\\n...",
  "glossary": [{{"term": "...", "definition": "...", "page_reference": "Trang X"}}],
  "teacher_notes": "...",
  "audio_script": "...",
  "quality_report": {{
    "coverage_score": 85,
    "strengths": ["..."],
    "missing_or_weak_points": ["..."],
    "suggested_next_improvements": ["..."]
  }}
}}

CHỈ TRẢ VỀ JSON OBJECT, KHÔNG MARKDOWN.
""".strip()
        return self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=fallback_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.16,
            ),
        )

    def generate_course(self, *, context: str, source_file: str) -> Course:
        prompt = self._build_prompt(context=context, source_file=source_file)

        try:
            response = self._generate_with_schema(prompt)
        except Exception as exc:
            message = str(exc)
            # Covers: "additionalProperties is not supported in the Gemini API."
            # Also useful when the SDK rejects one nested schema detail.
            if "additionalProperties" not in message and "schema" not in message.lower():
                raise
            response = self._generate_json_only(prompt)

        parsed: Any = getattr(response, "parsed", None)
        if isinstance(parsed, Course):
            course = parsed
        elif hasattr(parsed, "model_dump"):
            course = Course.model_validate(parsed.model_dump())
        elif parsed is not None:
            course = Course.model_validate(parsed)
        else:
            course = Course.model_validate(extract_json_object(response.text))

        # Force source_file from trusted backend input, not from model hallucination.
        data = course.model_dump()
        data["source_file"] = source_file
        return Course.model_validate(data)
