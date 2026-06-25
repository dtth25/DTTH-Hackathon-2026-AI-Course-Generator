"""Generation service for the four public outputs: Book, Quiz, Vid, and Slide."""

import asyncio
import json
import os
import re
import shutil
import subprocess
import textwrap
import threading
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from backend.core.config import extract_json, get_course_path, get_llm, logger
from backend.core.prompts import (
    BOOK_OUTLINE_PROMPT,
    BOOK_LESSON_PROMPT,
    QUIZ_V2_PROMPT,
    SLIDE_GENERATION_PROMPT,
    VID_SCENES_PROMPT,
)


class ResourceGenerator:
    """Generate Book, Quiz, Vid, and Slide outputs from an initialized RAG course."""

    def __init__(self, rag_chains):
        self.rag = rag_chains
        self.course_id = rag_chains.course_id
        self.vectorstore = rag_chains.vectorstore

    def _save_json(self, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _clean_doc_text(self, doc, max_chars: int = 320) -> str:
        text = doc.page_content
        text = re.sub(r"===\s*BẮT ĐẦU.*?===", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"===\s*KẾT THÚC.*?===", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\[MÃ ĐỊNH DANH TRANG:\s*\d+\]", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bNỘI DUNG:\s*", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bMã định danh trang\s+\d+\s+nội dung\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars].strip()

    def _clean_generated_text(self, text: Any, compact: bool = True) -> str:
        """Remove internal extraction markers from generated/public text."""
        value = str(text or "")
        value = re.sub(r"===\s*BẮT ĐẦU.*?===", " ", value, flags=re.IGNORECASE | re.DOTALL)
        value = re.sub(r"===\s*KẾT THÚC.*?===", " ", value, flags=re.IGNORECASE | re.DOTALL)
        value = re.sub(r"\[MÃ ĐỊNH DANH TRANG:\s*\d+\]", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"\bNỘI DUNG:\s*", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"\b(page|source|chunk_id)\s*:\s*[^,\n]+", " ", value, flags=re.IGNORECASE)
        if compact:
            return re.sub(r"\s+", " ", value).strip()
        return re.sub(r"[ \t]+", " ", value).replace("\n\n\n", "\n\n").strip()

    def _replace_newlines_outside_math(self, content: str) -> str:
        """Safely replace literal \\n sequences with real newlines only outside of math blocks."""
        parts = re.split(r'(\$\$[\s\S]*?\$\$|\$[^\n$]*?\$)', content)
        result = []
        for part in parts:
            if not part:
                continue
            if part.startswith('$'):
                # Inside math blocks, replace literal \n only if it's NOT a LaTeX command starting with n
                result.append(re.sub(r'\\n(?![eauoisplgw])', '\n', part))
            else:
                result.append(part.replace('\\n', '\n'))
        return "".join(result)

    def _clean_text_for_pdf(self, text: Any) -> str:
        """Process and clean LaTeX and newline formatting specifically for PDF output."""
        value = str(text or "")
        # First clean extraction markers
        value = self._clean_generated_text(value, compact=False)
        
        # 1. Replace newlines safely using math-block aware logic
        value = self._replace_newlines_outside_math(value)
        
        # 2. Convert common LaTeX formulas and symbols to unicode/readable plain text (longest/most specific first)
        replacements = [
            (r'\\readonly', ''),
            (r'\\mathbb\{R\}', 'R'),
            (r'\\mathbb\{F\}', 'F'),
            (r'\\mathbb\{Q\}', 'Q'),
            (r'\\mathbb\{C\}', 'C'),
            (r'\\mathbb\{Z\}', 'Z'),
            (r'\\mathbb\{N\}', 'N'),
            (r'\\notin', ' không thuộc '),
            (r'\\infty', '∞'),
            (r'\\in', ' thuộc '),
            (r'\\neq', ' ≠ '),
            (r'\\ne', ' ≠ '),
            (r'\\cdots', '...'),
            (r'\\dots', '...'),
            (r'\\cdot', ' . '),
            (r'\\pm', '±'),
            (r'\\deg', 'deg'),
            (r'\\gcd', 'gcd'),
            (r'\\sum_\{([^{}]+)\}^\{([^{}]+)\}', r'Tổng từ \1 đến \2'),
            (r'\\sum', 'Tổng'),
            (r'\\prod', 'Tích'),
            (r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'(\1)/(\2)'),
            (r'\\sqrt\{([^{}]+)\}', r'sqrt(\1)'),
            (r'\\alpha', 'α'),
            (r'\\beta', 'β'),
            (r'\\gamma', 'γ'),
            (r'\\delta', 'δ'),
            (r'\\theta', 'θ'),
            (r'\\lambda', 'λ'),
            (r'\\sigma', 'σ'),
            (r'\\omega', 'ω'),
            (r'\\phi', 'φ'),
            (r'\\pi', 'π'),
            (r'\\([a-zA-Z]+)', r'\1'), # strip remaining command backslashes
        ]
        
        for pattern, repl in replacements:
            value = re.sub(pattern, repl, value)
            
        # 3. Format subscripts and superscripts using standard ASCII representation to avoid font box errors
        # Handle braced subscripts: a_{n-1} -> a_(n-1)
        value = re.sub(r'_\{([^{}]+)\}', r'_(\1)', value)
        # Handle single-char subscripts: a_n -> a_n, a_1 -> a_1
        value = re.sub(r'_([0-9a-zA-Z])', r'_\1', value)
        # Handle braced superscripts: x^{n-1} -> x^(n-1)
        value = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', value)
        # Handle single-char superscripts: x^2 -> x^2, x^n -> x^n
        value = re.sub(r'\^([0-9a-zA-Z])', r'^\1', value)
            
        # 4. Strip $ and $$ formula boundaries
        value = value.replace('$$', '')
        value = value.replace('$', '')
        
        # 5. Remove bold ** and inline code `
        value = re.sub(r'\*\*|`', '', value)
        
        return value.strip()

    def _sanitize_payload(self, value: Any) -> Any:
        """Recursively sanitize public payload strings."""
        if isinstance(value, dict):
            return {key: self._sanitize_payload(item) for key, item in value.items() if key not in {"page", "source", "chunk_id"}}
        if isinstance(value, list):
            return [self._sanitize_payload(item) for item in value]
        if isinstance(value, str):
            return self._clean_generated_text(value, compact=False)
        return value

    def _clean_docs_context(self, docs, max_docs: int = 24, max_chars: int = 900) -> str:
        """Build clean prompt context without internal page/chunk markers."""
        snippets: list[str] = []
        for doc in docs[:max_docs]:
            text = self._clean_doc_text(doc, max_chars=max_chars)
            if len(text) < 30:
                continue
            snippets.append(f"- {text}")
        if not snippets:
            return "Tài liệu đã được xử lý nhưng chưa trích xuất được đoạn nội dung đủ rõ."
        return "\n".join(snippets)

    def _doc_points(self, docs, limit: int = 8, max_chars: int = 220) -> list[dict[str, str]]:
        points = []
        for doc in docs:
            text = self._clean_doc_text(doc, max_chars)
            if len(text) < 30:
                continue
            points.append({"text": text})
            if len(points) >= limit:
                break
        return points or [
            {
                "text": (
                    "Tài liệu đã được xử lý thành công, nhưng hệ thống chưa trích xuất được đoạn nội dung "
                    "đủ dài cho bản nháp."
                )
            }
        ]

    def _short_title(self, text: str, fallback: str) -> str:
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        title = " ".join(words[:8]).strip()
        return title.capitalize() if title else fallback

    def _build_lesson_from_point(self, point: dict[str, str], title: str):
        return {
            "title": title,
            "duration": "20-30 phút",
            "objectives": [
                "Nắm được ý chính và thuật ngữ trọng tâm của phần này.",
                "Giải thích lại nội dung bằng ngôn ngữ của người học.",
            ],
            "lecture": (
                f"{point['text']}\n\n"
                "Khi học phần này, người học nên xác định các khái niệm then chốt, "
                "ghi chú ví dụ quan trọng và liên hệ chúng với mục tiêu chung của tài liệu."
            ),
            "key_points": [
                point["text"][:180],
                "Cần ghi nhớ mối liên hệ giữa ý chính, ví dụ và mục tiêu bài học.",
                "Người học nên tự diễn giải lại nội dung bằng một ví dụ ngắn.",
            ],
            "activity": "Tóm tắt phần này bằng 3 gạch đầu dòng và nêu 1 ví dụ minh họa.",
            "assessment": [
                "Ý chính của phần này là gì?",
                "Chi tiết nào trong tài liệu giúp củng cố ý chính đó?",
            ],
        }

    def _normalize_book(self, book, docs, target_audience: str):
        points = self._doc_points(docs, limit=18, max_chars=620)
        if not isinstance(book, dict):
            return self._build_fallback_book(docs, target_audience)

        normalized = {
            "title": book.get("title") or "Sách học tập từ tài liệu đã tải lên",
            "description": book.get("description")
            or f"Sách học tập dành cho {target_audience or 'người học'}, bám sát nội dung tài liệu gốc.",
            "estimated_duration": book.get("estimated_duration") or "3-5 giờ",
            "chapters": [],
        }

        raw_chapters = book.get("chapters") or []
        if not isinstance(raw_chapters, list) or not raw_chapters:
            return self._build_fallback_book(docs, target_audience)

        point_cursor = 0
        for chapter_index, raw_chapter in enumerate(raw_chapters[:6], 1):
            chapter = raw_chapter if isinstance(raw_chapter, dict) else {"title": str(raw_chapter)}
            raw_lessons = chapter.get("lessons") or []
            if not isinstance(raw_lessons, list) or not raw_lessons:
                raw_lessons = [{"title": f"Bài {chapter_index}.1: Nội dung trọng tâm"}]

            lessons = []
            for lesson_index, raw_lesson in enumerate(raw_lessons[:3], 1):
                lesson = raw_lesson if isinstance(raw_lesson, dict) else {"title": str(raw_lesson)}
                point = points[point_cursor % len(points)]
                point_cursor += 1
                title = lesson.get("title") or f"Bài {chapter_index}.{lesson_index}: Nội dung trọng tâm"
                enriched = self._build_lesson_from_point(point, title)

                for field in ["duration", "activity"]:
                    if lesson.get(field):
                        enriched[field] = lesson[field]

                for field in ["objectives", "key_points", "assessment"]:
                    if isinstance(lesson.get(field), list) and lesson[field]:
                        enriched[field] = lesson[field]

                if isinstance(lesson.get("lecture"), str) and lesson["lecture"].strip():
                    enriched["lecture"] = lesson["lecture"].strip()

                lessons.append(enriched)

            normalized["chapters"].append(
                {
                    "title": chapter.get("title") or f"Chương {chapter_index}",
                    "description": chapter.get("description")
                    or f"Chương này hệ thống hóa {len(lessons)} bài học chính từ tài liệu.",
                    "lessons": lessons,
                }
            )

        return normalized

    def _build_fallback_book(self, docs, target_audience: str):
        points = self._doc_points(docs, limit=6, max_chars=620)
        chapters = []
        for index, point in enumerate(points, 1):
            title = self._short_title(point["text"], f"Nội dung chính {index}")
            chapters.append(
                {
                    "title": f"Chương {index}: {title}",
                    "description": "Hệ thống hóa một nhóm nội dung trọng tâm trong tài liệu.",
                    "lessons": [
                        self._build_lesson_from_point(point, f"Bài {index}.1: Đọc hiểu nội dung chính"),
                        self._build_lesson_from_point(point, f"Bài {index}.2: Ghi nhớ và vận dụng ý chính"),
                    ],
                }
            )
        return {
            "title": "Sách học tập từ tài liệu đã tải lên",
            "description": (
                f"Bản sách MVP dành cho {target_audience or 'người học'}, được dựng trực tiếp từ các đoạn "
                "nội dung đã index trong tài liệu."
            ),
            "estimated_duration": "3-5 giờ",
            "chapters": chapters,
        }

    def _book_pdf_elements(self, book: dict[str, Any]) -> list[tuple[str, str]]:
        elements: list[tuple[str, str]] = []

        def add(text: Any, style: str = "body") -> None:
            clean = str(text or "").strip()
            if clean:
                elements.append((clean, style))

        add(book.get("title") or "Sách học tập", "title")
        add(book.get("description"), "body")
        add(f"Thời lượng ước tính: {book.get('estimated_duration')}", "small")
        elements.append(("", "gap"))

        for chapter_index, chapter in enumerate(book.get("chapters") or [], 1):
            if not isinstance(chapter, dict):
                continue
            add(chapter.get("title") or f"Chương {chapter_index}", "chapter")
            add(chapter.get("description"), "body")

            for lesson_index, lesson in enumerate(chapter.get("lessons") or [], 1):
                if not isinstance(lesson, dict):
                    continue
                add(lesson.get("title") or f"Bài {chapter_index}.{lesson_index}", "lesson")
                add(f"Thời lượng: {lesson.get('duration')}", "small")

                for label, key in [
                    ("Mục tiêu", "objectives"),
                    ("Nội dung bài giảng", "lecture"),
                    ("Ý chính cần nhớ", "key_points"),
                    ("Hoạt động học tập", "activity"),
                    ("Kiểm tra nhanh", "assessment"),
                ]:
                    value = lesson.get(key)
                    if not value:
                        continue
                    add(label, "section")
                    if isinstance(value, list):
                        for item in value:
                            add(f"- {item}", "body")
                    else:
                        add(value, "body")
                elements.append(("", "gap"))

        return elements

    def _render_book_pdf(self, book: dict[str, Any], pdf_path: str) -> str:
        from PIL import Image, ImageDraw

        page_width, page_height = 1240, 1754
        margin = 86
        content_width = page_width - margin * 2
        styles = {
            "title": {"font": self._font(44, bold=True), "fill": (17, 24, 39), "line_height": 58, "width": 38},
            "chapter": {"font": self._font(34, bold=True), "fill": (30, 64, 175), "line_height": 46, "width": 48},
            "lesson": {"font": self._font(29, bold=True), "fill": (15, 23, 42), "line_height": 40, "width": 58},
            "section": {"font": self._font(25, bold=True), "fill": (51, 65, 85), "line_height": 34, "width": 66},
            "body": {"font": self._font(24), "fill": (51, 65, 85), "line_height": 34, "width": 78},
            "small": {"font": self._font(21), "fill": (100, 116, 139), "line_height": 30, "width": 88},
        }

        pages: list[Image.Image] = []
        image = Image.new("RGB", (page_width, page_height), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        y = margin

        def finish_page() -> None:
            pages.append(image.copy())

        def reset_page() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
            next_image = Image.new("RGB", (page_width, page_height), (255, 255, 255))
            next_draw = ImageDraw.Draw(next_image)
            return next_image, next_draw, margin

        for text, style_name in self._book_pdf_elements(book):
            if style_name == "gap":
                y += 24
                continue

            style = styles.get(style_name, styles["body"])
            clean_text = self._clean_text_for_pdf(text)
            lines = self._wrap_lines(clean_text, width=style["width"]) or [clean_text]
            block_height = len(lines) * style["line_height"] + 12
            if y + block_height > page_height - margin:
                finish_page()
                image, draw, y = reset_page()

            if style_name in {"chapter", "lesson"}:
                draw.rounded_rectangle(
                    (margin - 18, y - 10, margin + content_width + 18, y + block_height - 8),
                    radius=10,
                    fill=(248, 250, 252),
                )

            for line in lines:
                draw.text((margin, y), line, font=style["font"], fill=style["fill"])
                y += style["line_height"]
            y += 12

        finish_page()
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        pages[0].save(pdf_path, "PDF", resolution=120.0, save_all=True, append_images=pages[1:])
        return pdf_path

    def export_book_pdf(self) -> str:
        paths = get_course_path(self.course_id)
        if not os.path.exists(paths["book"]):
            raise FileNotFoundError("Book has not been generated yet.")
        with open(paths["book"], "r", encoding="utf-8") as f:
            book = json.load(f)
        return self._render_book_pdf(book, paths["book_pdf"])

    def _render_artifact_pdf(self, title: str, elements: list[tuple[str, str]], pdf_path: str) -> str:
        from PIL import Image, ImageDraw

        page_width, page_height = 1240, 1754
        margin = 86
        content_width = page_width - margin * 2
        styles = {
            "title": {"font": self._font(44, bold=True), "fill": (17, 24, 39), "line_height": 58, "width": 38},
            "heading": {"font": self._font(32, bold=True), "fill": (15, 23, 42), "line_height": 44, "width": 52},
            "section": {"font": self._font(24, bold=True), "fill": (51, 65, 85), "line_height": 34, "width": 72},
            "body": {"font": self._font(23), "fill": (51, 65, 85), "line_height": 33, "width": 82},
            "small": {"font": self._font(20), "fill": (100, 116, 139), "line_height": 29, "width": 92},
        }

        pages: list[Image.Image] = []
        image = Image.new("RGB", (page_width, page_height), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        y = margin

        def finish_page() -> None:
            pages.append(image.copy())

        def reset_page() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
            next_image = Image.new("RGB", (page_width, page_height), (255, 255, 255))
            next_draw = ImageDraw.Draw(next_image)
            return next_image, next_draw, margin

        full_elements = [(title, "title"), ("", "gap"), *elements]
        for text, style_name in full_elements:
            if style_name == "gap":
                y += 24
                continue

            style = styles.get(style_name, styles["body"])
            clean_text = self._clean_text_for_pdf(text)
            lines = self._wrap_lines(clean_text, width=style["width"]) or [clean_text]
            block_height = len(lines) * style["line_height"] + 16
            if y + block_height > page_height - margin:
                finish_page()
                image, draw, y = reset_page()

            if style_name == "heading":
                draw.rounded_rectangle(
                    (margin - 18, y - 10, margin + content_width + 18, y + block_height - 8),
                    radius=10,
                    fill=(248, 250, 252),
                )

            for line in lines:
                draw.text((margin, y), line, font=style["font"], fill=style["fill"])
                y += style["line_height"]
            y += 12

        finish_page()
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        pages[0].save(pdf_path, "PDF", resolution=120.0, save_all=True, append_images=pages[1:])
        return pdf_path

    def export_slides_pdf(self) -> str:
        paths = get_course_path(self.course_id)
        if not os.path.exists(paths["slides"]):
            raise FileNotFoundError("Slide has not been generated yet.")
        with open(paths["slides"], "r", encoding="utf-8") as f:
            slides = json.load(f)

        elements: list[tuple[str, str]] = []
        for index, slide in enumerate(slides if isinstance(slides, list) else [], 1):
            item = slide if isinstance(slide, dict) else {"content": str(slide)}
            elements.append((f"Slide {index}: {item.get('title') or 'Nội dung'}", "heading"))
            if item.get("content"):
                elements.append((item["content"], "body"))
            if item.get("image_suggestion"):
                elements.append((f"Gợi ý hình ảnh: {item['image_suggestion']}", "small"))
            elements.append(("", "gap"))

        return self._render_artifact_pdf("Slide học tập", elements, paths["slides_pdf"])

    def export_quiz_pdf(self) -> str:
        paths = get_course_path(self.course_id)
        if not os.path.exists(paths["questions"]):
            raise FileNotFoundError("Quiz has not been generated yet.")
        with open(paths["questions"], "r", encoding="utf-8") as f:
            questions = json.load(f)

        elements: list[tuple[str, str]] = []
        labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for index, question in enumerate(questions if isinstance(questions, list) else [], 1):
            item = question if isinstance(question, dict) else {"question": str(question)}
            elements.append((f"Câu {index}: {item.get('question') or 'Câu hỏi'}", "heading"))
            options = item.get("options") if isinstance(item.get("options"), list) else []
            for option_index, option in enumerate(options):
                elements.append((f"{labels[option_index]}. {option}", "body"))
            try:
                correct = int(item.get("correct", 0))
            except (TypeError, ValueError):
                correct = 0
            if 0 <= correct < len(options):
                elements.append((f"Đáp án: {labels[correct]}", "section"))
            if item.get("explanation"):
                elements.append((f"Giải thích: {item['explanation']}", "small"))
            elements.append(("", "gap"))

        return self._render_artifact_pdf("Quiz học tập", elements, paths["questions_pdf"])

    async def _generate_lesson_content(
        self,
        book_title: str,
        chapter_title: str,
        lesson_title: str,
        objectives: list,
        user_prompt: str
    ) -> dict:
        query = f"{chapter_title} - {lesson_title} {user_prompt}".strip()
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})
        docs = await retriever.ainvoke(query)
        context = self._clean_docs_context(docs, max_docs=3, max_chars=1200)

        max_attempts = 5
        backoff = 2.0
        last_error = None
        for attempt in range(max_attempts):
            try:
                prompt = ChatPromptTemplate.from_template(BOOK_LESSON_PROMPT)
                chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
                res = await chain.ainvoke(
                    {
                        "context": context,
                        "book_title": book_title,
                        "chapter_title": chapter_title,
                        "lesson_title": lesson_title,
                        "lesson_objectives": ", ".join(objectives) if objectives else "Tự động trích xuất ý chính",
                    }
                )
                lesson_data = json.loads(extract_json(res), strict=False)
                return {
                    "lecture": lesson_data.get("lecture") or "Không có nội dung giảng bài.",
                    "key_points": lesson_data.get("key_points") or [],
                    "activity": lesson_data.get("activity") or "Hoạt động thực hành ngắn",
                    "assessment": lesson_data.get("assessment") or []
                }
            except Exception as e:
                last_error = e
                error_str = str(e)
                if "429" in error_str and attempt < max_attempts - 1:
                    sleep_time = backoff * (2 ** attempt)
                    logger.warning("NIM API 429 rate limit hit for %s. Retrying in %.1fs... (Attempt %d/%d)", 
                                   lesson_title, sleep_time, attempt + 1, max_attempts)
                    await asyncio.sleep(sleep_time)
                    continue
                break

        logger.warning("Failed generating lesson content for %s: %s", lesson_title, last_error)
        points = self._doc_points(docs, limit=1, max_chars=620)
        point = points[0] if points else {"text": "Tài liệu học tập."}
        fallback_lesson = self._build_lesson_from_point(point, lesson_title)
        return {
            "lecture": fallback_lesson["lecture"],
            "key_points": fallback_lesson["key_points"],
            "activity": fallback_lesson["activity"],
            "assessment": fallback_lesson["assessment"]
        }

    async def generate_book(self, user_prompt: str = "", target_audience: str = "sinh viên"):
        total_chunks = 10
        if hasattr(self.vectorstore, "index") and hasattr(self.vectorstore.index, "ntotal"):
            total_chunks = self.vectorstore.index.ntotal

        # Lấy số lượng chunk đa dạng hơn để bao quát tất cả chủ đề/khái niệm của tài liệu
        if total_chunks <= 5:
            max_docs = total_chunks
        elif total_chunks <= 15:
            max_docs = total_chunks
        else:
            max_docs = min(20, total_chunks)

        retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": max_docs, "fetch_k": min(50, total_chunks)}
        )
        query = user_prompt or "mục lục chương bài học định lý định nghĩa công thức ví dụ bài tập lý thuyết khái niệm"
        docs = await retriever.ainvoke(query)
        # Sử dụng max_chars lớn hơn (1200) để không làm mất hoặc cụt các công thức toán học/khái niệm chi tiết
        context = self._clean_docs_context(docs, max_docs=max_docs, max_chars=1200)
        try:
            prompt = ChatPromptTemplate.from_template(BOOK_OUTLINE_PROMPT)
            chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
            res = await chain.ainvoke(
                {
                    "context": context,
                    "user_prompt": user_prompt or "Không có",
                    "target_audience": target_audience or "người học chung",
                }
            )
            raw_outline = json.loads(extract_json(res), strict=False)
            
            book = {
                "title": raw_outline.get("title") or "Sách học tập từ tài liệu đã tải lên",
                "description": raw_outline.get("description") or f"Sách học tập dành cho {target_audience or 'người học'}.",
                "estimated_duration": raw_outline.get("estimated_duration") or "3-5 giờ",
                "chapters": []
            }
            
            raw_chapters = raw_outline.get("chapters") or []
            tasks = []
            task_indices = []

            # Cho phép tối đa 8 chương và tối đa 5 bài học mỗi chương để bao phủ đầy đủ tất cả các chủ đề/khái niệm
            for ch_idx, raw_chapter in enumerate(raw_chapters[:8]):
                chapter_title = raw_chapter.get("title") or f"Chương {ch_idx + 1}"
                chapter_desc = raw_chapter.get("description") or ""
                book_chapter = {
                    "title": chapter_title,
                    "description": chapter_desc,
                    "lessons": []
                }
                book["chapters"].append(book_chapter)

                raw_lessons = raw_chapter.get("lessons") or []
                for les_idx, raw_lesson in enumerate(raw_lessons[:5]):
                    lesson_title = raw_lesson.get("title") or f"Bài {ch_idx + 1}.{les_idx + 1}"
                    lesson_duration = raw_lesson.get("duration") or "20-30 phút"
                    lesson_objectives = raw_lesson.get("objectives") or []

                    book_lesson = {
                        "title": lesson_title,
                        "duration": lesson_duration,
                        "objectives": lesson_objectives,
                        "lecture": "",
                        "key_points": [],
                        "activity": "",
                        "assessment": []
                    }
                    book_chapter["lessons"].append(book_lesson)

                    task = self._generate_lesson_content(
                        book_title=book["title"],
                        chapter_title=chapter_title,
                        lesson_title=lesson_title,
                        objectives=lesson_objectives,
                        user_prompt=user_prompt
                    )
                    tasks.append(task)
                    task_indices.append((ch_idx, les_idx))

            if tasks:
                sem = asyncio.Semaphore(2)

                async def sem_worker(idx, task):
                    await asyncio.sleep(idx * 0.5)  # Tránh gửi request đồng thời (stagger nhẹ)
                    async with sem:
                        return await task

                results = await asyncio.gather(*(sem_worker(i, t) for i, t in enumerate(tasks)))
                for (ch_idx, les_idx), lesson_content in zip(task_indices, results):
                    book["chapters"][ch_idx]["lessons"][les_idx].update(lesson_content)

        except Exception as e:
            logger.warning("Book outline generation failed, using fallback: %s", e)
            book = self._build_fallback_book(docs, target_audience)

        book = self._sanitize_payload(book)

        paths = get_course_path(self.course_id)
        self._save_json(paths["book"], book)
        self._render_book_pdf(book, paths["book_pdf"])
        return {"book": book, "pdf_url": f"/api/course/{self.course_id}/book.pdf"}


    def _build_fallback_quiz(self, docs, quantity: int, difficulty: str):
        points = self._doc_points(docs, limit=max(1, min(quantity, 10)), max_chars=220)
        questions = []
        for index in range(max(1, min(quantity, 10))):
            point = points[index % len(points)]
            questions.append(
                {
                    "question": "Ý nào sau đây phản ánh đúng nội dung trong tài liệu?",
                    "options": [
                        point["text"][:140],
                        "Một nhận định không được tài liệu cung cấp rõ ràng.",
                        "Một kết luận mở rộng ngoài phạm vi tài liệu.",
                        "Một phương án dùng để gây nhiễu trong câu hỏi.",
                    ],
                    "correct": 0,
                    "explanation": "Đáp án đúng bám sát đoạn nội dung được hệ thống truy xuất từ tài liệu.",
                    "difficulty": difficulty,
                }
            )
        return questions

    def _normalize_quiz(self, raw_questions, quantity: int, docs, difficulty: str):
        if not isinstance(raw_questions, list) or not raw_questions:
            return self._build_fallback_quiz(docs, quantity, difficulty)

        normalized = []
        for item in raw_questions:
            if not isinstance(item, dict):
                continue
            options = item.get("options")
            correct = item.get("correct", item.get("correct_answer"))

            if isinstance(options, dict):
                entries = list(options.items())
                labels = [key for key, _ in entries]
                options = [str(value) for _, value in entries]
                if isinstance(correct, str) and correct in labels:
                    correct = labels.index(correct)

            if not isinstance(options, list):
                continue
            options = [str(option) for option in options[:4]]
            if len(options) < 2:
                continue

            try:
                correct_index = int(correct)
            except (TypeError, ValueError):
                correct_index = 0
            if correct_index < 0 or correct_index >= len(options):
                correct_index = 0

            normalized.append(
                {
                    "question": str(item.get("question") or "Câu hỏi"),
                    "options": options,
                    "correct": correct_index,
                    "explanation": str(item.get("explanation") or "Đáp án đúng dựa trên nội dung tài liệu."),
                    "difficulty": item.get("difficulty") or difficulty,
                }
            )
            if len(normalized) >= quantity:
                break

        return normalized or self._build_fallback_quiz(docs, quantity, difficulty)

    def generate_quiz_v2(self, topic: str, quantity: int, difficulty: str):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(topic)
        context = self._clean_docs_context(docs, max_docs=15, max_chars=800)
        try:
            prompt = ChatPromptTemplate.from_template(QUIZ_V2_PROMPT)
            chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
            res = chain.invoke(
                {
                    "context": context,
                    "topic": topic,
                    "quantity": quantity,
                    "difficulty": difficulty,
                }
            )
            questions = self._normalize_quiz(json.loads(extract_json(res), strict=False), quantity, docs, difficulty)
        except Exception as e:
            logger.warning("Quiz generation failed, using fallback: %s", e)
            questions = self._build_fallback_quiz(docs, quantity, difficulty)

        questions = self._sanitize_payload(questions)
        self._save_json(get_course_path(self.course_id)["questions"], questions)
        try:
            self.export_quiz_pdf()
        except Exception as exc:
            logger.warning("Quiz PDF export failed: %s", exc)
        return {
            "questions": questions,
            "json_url": f"/api/course/{self.course_id}/quiz.json",
            "pdf_url": f"/api/course/{self.course_id}/quiz.pdf",
        }

    def _build_fallback_slides(self, docs, num_slides: int):
        points = self._doc_points(docs, limit=max(1, min(num_slides, 10)), max_chars=220)
        slides = []
        for index in range(max(1, min(num_slides, 10))):
            point = points[index % len(points)]
            slides.append(
                {
                    "title": f"Slide {index + 1}: Ý chính",
                    "content": f"- {point['text']}\n- Ghi nhớ ý chính và liên hệ với nội dung trước đó.",
                    "layout_hint": "title-and-content",
                    "image_suggestion": "Sơ đồ hoặc minh họa đơn giản cho ý chính của slide.",
                }
            )
        return slides

    def _normalize_slides(self, raw_slides, num_slides: int, docs):
        if not isinstance(raw_slides, list) or not raw_slides:
            return self._build_fallback_slides(docs, num_slides)

        slides = []
        for index, item in enumerate(raw_slides[:num_slides], 1):
            slide = item if isinstance(item, dict) else {"content": str(item)}
            slides.append(
                {
                    "title": str(slide.get("title") or f"Slide {index}"),
                    "content": str(slide.get("content") or ""),
                    "layout_hint": str(slide.get("layout_hint") or "title-and-content"),
                    "image_suggestion": str(slide.get("image_suggestion") or ""),
                }
            )
        return slides or self._build_fallback_slides(docs, num_slides)

    def generate_slides_v2(self, topic: str, num_slides: int):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(topic)
        context = self._clean_docs_context(docs, max_docs=15, max_chars=800)
        try:
            prompt = ChatPromptTemplate.from_template(SLIDE_GENERATION_PROMPT)
            chain = prompt | get_llm(temperature=0.1) | StrOutputParser()
            res = chain.invoke({"context": context, "topic": topic, "num_slides": num_slides})
            slides = self._normalize_slides(json.loads(extract_json(res), strict=False), num_slides, docs)
        except Exception as e:
            logger.warning("Slide generation failed, using fallback: %s", e)
            slides = self._build_fallback_slides(docs, num_slides)

        slides = self._sanitize_payload(slides)
        self._save_json(get_course_path(self.course_id)["slides"], slides)
        try:
            self.export_slides_pdf()
        except Exception as exc:
            logger.warning("Slide PDF export failed: %s", exc)
        return {
            "slides": slides,
            "json_url": f"/api/course/{self.course_id}/slide.json",
            "pdf_url": f"/api/course/{self.course_id}/slide.pdf",
        }

    def _build_fallback_scenes(self, docs, scene_count: int):
        points = self._doc_points(docs, limit=scene_count, max_chars=260)
        scenes = []
        for index in range(scene_count):
            point = points[index % len(points)]
            scenes.append(
                {
                    "title": f"Cảnh {index + 1}: Ý chính",
                    "visual_text": f"- {point['text']}\n- Ghi nhớ ý chính\n- Liên hệ với nội dung tài liệu",
                    "voiceover": (
                        f"Ở phần này, chúng ta tập trung vào ý chính sau: {point['text']} "
                        "Hãy ghi nhớ nội dung cốt lõi và liên hệ nó với các phần trước của tài liệu."
                    ),
                }
            )
        return scenes

    def _normalize_scenes(self, raw_scenes, scene_count: int, docs):
        if not isinstance(raw_scenes, list) or not raw_scenes:
            return self._build_fallback_scenes(docs, scene_count)

        scenes = []
        for index, item in enumerate(raw_scenes[:scene_count], 1):
            scene = item if isinstance(item, dict) else {"voiceover": str(item)}
            title = str(scene.get("title") or f"Cảnh {index}")
            visual_text = str(scene.get("visual_text") or scene.get("content") or title)
            voiceover = str(scene.get("voiceover") or visual_text.replace("-", ""))
            scenes.append({"title": title, "visual_text": visual_text, "voiceover": voiceover})
        return scenes or self._build_fallback_scenes(docs, scene_count)

    def _font(self, size: int, bold: bool = False):
        from PIL import ImageFont

        candidates = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return ImageFont.truetype(candidate, size)
        return ImageFont.load_default()

    def _wrap_lines(self, text: str, width: int) -> list[str]:
        lines: list[str] = []
        for raw_line in text.replace("\r", "").split("\n"):
            line = raw_line.strip().lstrip("-*• ").strip()
            if not line:
                continue
            lines.extend(textwrap.wrap(line, width=width) or [line])
        return lines

    def _draw_text_block(self, draw, position: tuple[int, int], lines: list[str], font, fill, line_height: int):
        x, y = position
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height
        return y

    def _render_scene_image(self, scene: dict[str, str], index: int, path: str) -> None:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (1280, 720), (247, 249, 252))
        draw = ImageDraw.Draw(image)
        title_font = self._font(48, bold=True)
        body_font = self._font(32)
        small_font = self._font(22)

        draw.rectangle((0, 0, 1280, 92), fill=(24, 39, 75))
        draw.text((56, 26), f"Vid học tập · Cảnh {index}", font=small_font, fill=(225, 232, 245))
        draw.rounded_rectangle((56, 128, 1224, 628), radius=28, fill=(255, 255, 255), outline=(224, 229, 238), width=2)

        title_lines = self._wrap_lines(scene["title"], width=38)[:2]
        y = self._draw_text_block(draw, (96, 168), title_lines, title_font, (16, 24, 39), 58)

        visual_lines = self._wrap_lines(scene["visual_text"], width=58)[:10]
        y += 24
        for line in visual_lines:
            draw.ellipse((102, y + 11, 114, y + 23), fill=(34, 116, 165))
            draw.text((132, y), line, font=body_font, fill=(45, 55, 72))
            y += 44

        image.save(path, quality=95)

    def _clean_tts_text(self, text: str) -> str:
        text = re.sub(r"\$.*?\$", "", text)
        text = text.replace("\\", " ")
        text = re.sub(
            r"[^\w\s,.\?!\-áàảãạâấầẩẫậăắằẳẵặéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợ"
            r"úùủũụưứừửữựýỳỷỹỵĐđ]",
            " ",
            text,
        )
        return re.sub(r"\s+", " ", text).strip()

    def _run_async_in_thread(self, coro):
        result: dict[str, Any] = {}

        def runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:  # pragma: no cover - threaded propagation
                result["error"] = exc

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _synthesize_voiceover(self, text: str, path: str) -> None:
        import edge_tts

        cleaned = self._clean_tts_text(text)
        if not cleaned:
            raise ValueError("Voiceover text is empty after cleaning.")
        communicate = edge_tts.Communicate(cleaned, "vi-VN-HoaiMyNeural")
        self._run_async_in_thread(communicate.save(path))

    def _run_ffmpeg(self, command: list[str]) -> None:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-1200:])

    def _estimate_scene_seconds(self, voiceover: str) -> int:
        word_count = max(12, len(voiceover.split()))
        return max(8, min(45, round(word_count / 2.2)))

    def _render_scene_clip(self, ffmpeg: str, image_path: str, audio_path: str | None, clip_path: str, seconds: int) -> None:
        if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 100:
            command = [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                image_path,
                "-i",
                audio_path,
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-shortest",
                clip_path,
            ]
        else:
            command = [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                image_path,
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t",
                str(seconds),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-pix_fmt",
                "yuv420p",
                "-shortest",
                clip_path,
            ]
        self._run_ffmpeg(command)

    def _render_vid(self, scenes: list[dict[str, str]], duration_minutes: int):
        import imageio_ffmpeg

        video_dir = get_course_path(self.course_id)["videos"]
        assets_dir = os.path.join(video_dir, "assets")
        if os.path.exists(assets_dir):
            shutil.rmtree(assets_dir)
        os.makedirs(assets_dir, exist_ok=True)
        os.makedirs(video_dir, exist_ok=True)

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        scene_clips: list[str] = []
        total_seconds = 0
        voiceover_count = 0

        for index, scene in enumerate(scenes, 1):
            image_path = os.path.join(assets_dir, f"scene_{index:02d}.png")
            audio_path = os.path.join(assets_dir, f"scene_{index:02d}.mp3")
            clip_path = os.path.join(assets_dir, f"scene_{index:02d}.mp4")
            seconds = self._estimate_scene_seconds(scene["voiceover"])
            total_seconds += seconds

            self._render_scene_image(scene, index, image_path)
            try:
                self._synthesize_voiceover(scene["voiceover"], audio_path)
                voiceover_count += 1
            except Exception as exc:
                logger.warning("Voiceover generation failed for scene %s: %s", index, exc)
                audio_path = None

            self._render_scene_clip(ffmpeg, image_path, audio_path, clip_path, seconds)
            scene_clips.append(clip_path)

        concat_path = os.path.join(assets_dir, "concat.txt")
        if not scene_clips:
            raise RuntimeError("No video scenes were rendered.")

        with open(concat_path, "w", encoding="utf-8") as f:
            for clip in scene_clips:
                escaped = clip.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        final_path = os.path.join(video_dir, "vid.mp4")
        self._run_ffmpeg([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_path, "-c", "copy", final_path])

        metadata = {
            "filename": "vid.mp4",
            "url": f"/api/course/{self.course_id}/vid/file",
            "status": "ready",
            "duration_minutes": duration_minutes,
            "estimated_duration_seconds": total_seconds,
            "voiceover_status": "ready" if voiceover_count == len(scenes) else "partial_or_silent",
            "scenes": scenes,
        }
        self._save_json(os.path.join(video_dir, "vid.json"), metadata)
        shutil.rmtree(assets_dir, ignore_errors=True)
        return metadata

    def generate_vid(self, topic: str = "tổng quan", duration_minutes: int = 3):
        duration_minutes = max(1, min(int(duration_minutes or 3), 5))
        scene_count = max(4, min(duration_minutes * 2, 10))
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 12})
        docs = retriever.invoke(topic or "tổng quan")
        context = self._clean_docs_context(docs, max_docs=12, max_chars=760)

        try:
            prompt = ChatPromptTemplate.from_template(VID_SCENES_PROMPT)
            chain = prompt | get_llm(temperature=0.25) | StrOutputParser()
            res = chain.invoke(
                {
                    "context": context,
                    "topic": topic or "tổng quan",
                    "duration_minutes": duration_minutes,
                    "scene_count": scene_count,
                }
            )
            scenes = self._normalize_scenes(json.loads(extract_json(res), strict=False), scene_count, docs)
        except Exception as e:
            logger.warning("Vid script generation failed, using fallback: %s", e)
            scenes = self._build_fallback_scenes(docs, scene_count)

        scenes = self._sanitize_payload(scenes)
        try:
            vid = self._render_vid(scenes, duration_minutes)
        except Exception as exc:
            logger.error("Vid rendering failed for course '%s': %s", self.course_id, exc)
            video_dir = get_course_path(self.course_id)["videos"]
            os.makedirs(video_dir, exist_ok=True)
            vid = {
                "filename": None,
                "url": None,
                "status": "failed",
                "error": str(exc),
                "duration_minutes": duration_minutes,
                "scenes": scenes,
            }
            self._save_json(os.path.join(video_dir, "vid.json"), vid)
        return {"vid": vid}
