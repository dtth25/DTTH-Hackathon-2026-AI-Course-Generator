"""
Resource generation service: Quiz, Flashcard, Slide, Summary, Podcast, Study Guide.
Mapping: Features 6.4-6.9 [11, 13, 14]
"""
import os
import json
import time
import re
import shutil
import logging
from typing import List, Optional, Tuple, Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.core.config import (
    get_llm,
    format_docs,
    extract_json,
    sanitize_filename,
    get_course_path,
    QUESTIONS_DIR,
    AUDIO_DIR,
    GUIDES_DIR,
    FLASHCARDS_DIR,
    logger,
)
from backend.core.prompts import (
    COURSE_GENERATION_PROMPT,
    QUIZ_V2_PROMPT,
    SLIDES_V2_PROMPT,
    SUMMARY_V2_PROMPT, 
    FLASHCARDS_V2_PROMPT, 
    PODCAST_SCRIPT_PROMPT,
    STUDY_GUIDE_PROMPT,
    CONTINUE_GUIDE_PROMPT,
)
class ResourceGenerator:
    """
    Generates learning resources (Quiz, Flashcard, Slide, Summary, Podcast, Study Guide)
    from an initialized RAGChains instance.
    """

    def __init__(self, rag_chains):
        """
        Args:
            rag_chains: An initialized RAGChains instance with vectorstore.
        """
        self.rag = rag_chains
        self.course_id = rag_chains.course_id
        self.vectorstore = rag_chains.vectorstore
        
        """Tạo danh sách trích dẫn từ Metadata của tài liệu."""
    def _get_citations(self, docs):
        return [
            {
                "page": d.metadata.get("page", 1),
                "source": os.path.basename(d.metadata.get("source_file", d.metadata.get("source", "unknown"))),
                "chunk_id": d.metadata.get("chunk_id", f"chunk_{hash(d.page_content) % 1000}")
            } for d in docs[:3]
        ]

    def _clean_doc_text(self, doc, max_chars: int = 320) -> str:
        """Return compact text from a retrieved chunk for deterministic fallbacks."""
        text = doc.page_content
        text = re.sub(r"===\s*BẮT ĐẦU.*?===", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"===\s*KẾT THÚC.*?===", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\[MÃ ĐỊNH DANH TRANG:\s*\d+\]", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bNỘI DUNG:\s*", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bMã định danh trang\s+\d+\s+nội dung\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or len(text) < 3:
            return ""
        return text[:max_chars].strip()

    def _doc_points(self, docs, limit: int = 8, max_chars: int = 220):
        points = []
        for doc in docs:
            text = self._clean_doc_text(doc, max_chars)
            if len(text) < 30:
                continue
            points.append(
                {
                    "text": text,
                    "page": doc.metadata.get("page", "?"),
                    "source": os.path.basename(
                        doc.metadata.get("source_file", doc.metadata.get("source", "unknown"))
                    ),
                    "chunk_id": doc.metadata.get("chunk_id", ""),
                }
            )
            if len(points) >= limit:
                break
        return points or [
            {
                "text": "Tài liệu đã được xử lý thành công, nhưng hệ thống chưa trích xuất được đoạn nội dung đủ dài cho bản nháp.",
                "page": "?",
                "source": "unknown",
                "chunk_id": "",
            }
        ]

    def _short_title(self, text: str, fallback: str) -> str:
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        title = " ".join(words[:8]).strip()
        return title.capitalize() if title else fallback

    def _build_lesson_from_point(self, point, title: str, index_label: str):
        source_note = f"Trang {point['page']} - {point['source']}"
        text = point["text"]
        text_short = text[:180] if len(text) > 180 else text

        # Extract key terms from text for diverse generation (truncated to avoid excessive length)
        terms = [w.strip() for w in text.split()[:5] if len(w.strip()) > 3][:3]
        term_str = ", ".join(terms) if terms else "nội dung trọng tâm"

        return {
            "title": title,
            "duration": "20-30 phút",
            "objectives": [
                f"Nắm được khái niệm cốt lõi về {term_str} từ đoạn trích.",
                f"Phân tích được mối quan hệ giữa các ý trong phần {index_label}.",
            ],
            "lecture": (
                f"Phần {index_label} tập trung vào nội dung từ {source_note}.\n\n"
                f"{text}\n\n"
                "Khi học phần này, người học nên đọc kỹ đoạn gốc, xác định các khái niệm then chốt "
                "và liên hệ chúng với mục tiêu chung của tài liệu."
            ),
            "key_points": [
                f"Ý chính: {text_short}",
                f"Ví dụ/dẫn chứng từ nguồn: {source_note} cung cấp thông tin về {term_str}.",
                f"Liên hệ: Nội dung này có thể liên quan đến các khái niệm đã học trước đó về {term_str}.",
                f"Ứng dụng: Hãy tìm một tình huống thực tế để minh họa cho {term_str}.",
                f"Gợi mở: Nếu {term_str} thay đổi, hệ quả sẽ như thế nào theo tài liệu?",
            ],
            "activity": f"Yêu cầu người học tóm tắt phần {index_label} bằng 3 gạch đầu dòng, nêu 1 ví dụ cho {term_str}, và đặt 1 câu hỏi về nội dung chưa rõ.",
            "assessment": [
                f"Nhận biết: Thuật ngữ '{term_str}' được định nghĩa như thế nào trong tài liệu?",
                f"Thông hiểu: Hãy diễn giải lại bằng lời của bạn nội dung chính từ {source_note}.",
                f"Vận dụng: Áp dụng kiến thức về {term_str} để giải quyết tình huống: [tình huống từ nội dung tài liệu].",
            ],
            "citation": {
                "page": point["page"],
                "source": point["source"],
                "chunk_id": point["chunk_id"],
            },
        }

    def _normalize_course(self, course, docs, target_audience: str):
        points = self._doc_points(docs, limit=18, max_chars=620)
        if not isinstance(course, dict):
            return self._build_fallback_course(docs, target_audience)

        normalized = {
            "title": course.get("title") or "Khóa học từ tài liệu đã tải lên",
            "description": course.get("description")
            or f"Lộ trình học dành cho {target_audience or 'người học'}, bám sát nội dung tài liệu gốc.",
            "estimated_duration": course.get("estimated_duration") or "3-5 giờ",
            "chapters": [],
        }

        raw_chapters = course.get("chapters") or course.get("syllabus") or []
        if not isinstance(raw_chapters, list) or not raw_chapters:
            return self._build_fallback_course(docs, target_audience)

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
                enriched = self._build_lesson_from_point(
                    point,
                    title,
                    f"{chapter_index}.{lesson_index}",
                )

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
                    "title": chapter.get("title") or chapter.get("chapter") or f"Chương {chapter_index}",
                    "description": chapter.get("description")
                    or f"Chương này hệ thống hóa {len(lessons)} bài học chính từ tài liệu.",
                    "lessons": lessons,
                }
            )

        return normalized

    def _build_fallback_course(self, docs, target_audience: str):
        points = self._doc_points(docs, limit=6, max_chars=620)
        chapters = []
        for index, point in enumerate(points, 1):
            title = self._short_title(point["text"], f"Nội dung chính {index}")
            chapters.append(
                {
                    "title": f"Chương {index}: {title}",
                    "description": f"Hệ thống hóa nội dung trọng tâm từ trang {point['page']} của tài liệu.",
                    "lessons": [
                        self._build_lesson_from_point(
                            point,
                            f"Bài {index}.1: Đọc hiểu nội dung trang {point['page']}",
                            f"{index}.1",
                        ),
                        self._build_lesson_from_point(
                            point,
                            f"Bài {index}.2: Ghi nhớ và vận dụng ý chính",
                            f"{index}.2",
                        ),
                    ],
                }
            )
        return {
            "title": "Khóa học từ tài liệu đã tải lên",
            "description": f"Lộ trình học MVP dành cho {target_audience or 'người học'}, được dựng trực tiếp từ các đoạn nội dung đã index trong tài liệu.",
            "estimated_duration": "3-5 giờ",
            "chapters": chapters,
        }

    def _build_fallback_summary(self, docs, summary_type: str):
        points = self._doc_points(docs, limit=8, max_chars=260)
        bullets = "\n".join(
            f"- Trang {point['page']}: {point['text']}" for point in points
        )
        return (
            "# BẢN TÓM TẮT TÀI LIỆU\n\n"
            f"Loại tóm tắt: `{summary_type}`.\n\n"
            "Các ý chính được trích trực tiếp từ tài liệu:\n\n"
            f"{bullets}\n\n"
            "Bản này được tạo ở chế độ dự phòng để bảo đảm demo vẫn có nội dung khi LLM hoặc parser gặp lỗi."
        )

    def _build_fallback_quiz(self, docs, quantity: int, difficulty: str):
        points = self._doc_points(docs, limit=max(1, min(quantity, 10)), max_chars=220)
        questions = []
        for index in range(max(1, min(quantity, 10))):
            point = points[index % len(points)]
            questions.append(
                {
                    "question": f"Ý nào sau đây phản ánh đúng nội dung ở trang {point['page']}?",
                    "options": [
                        point["text"][:140],
                        "Một nhận định không được tài liệu cung cấp rõ ràng.",
                        "Một kết luận mở rộng ngoài phạm vi tài liệu.",
                        "Một phương án dùng để gây nhiễu trong câu hỏi.",
                    ],
                    "correct": 0,
                    "explanation": f"Đáp án đúng lấy trực tiếp từ chunk metadata page={point['page']}, source={point['source']}.",
                    "difficulty": difficulty,
                }
            )
        return questions

    def _build_fallback_slides(self, docs, num_slides: int):
        points = self._doc_points(docs, limit=max(1, min(num_slides, 10)), max_chars=220)
        slides = []
        for index in range(max(1, min(num_slides, 10))):
            point = points[index % len(points)]
            title = f"Trang {point['page']}: {self._short_title(point['text'], 'Nội dung trọng tâm')}"
            slides.append(
                {
                    "title": title,
                    "content": point["text"],
                    "layout_hint": "title-and-content",
                    "image_suggestion": "Nội dung được trích xuất trực tiếp từ tài liệu gốc.",
                    "citation": {
                        "page": point["page"],
                        "source": point["source"],
                        "chunk_id": point["chunk_id"],
                    },
                }
            )
        return slides
        
    def generate_course_structure(self, user_prompt: str, target_audience: str):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 10})
        docs = retriever.invoke(user_prompt or "tổng quan")
        citations = self._get_citations(docs)
        try:
            prompt = ChatPromptTemplate.from_template(COURSE_GENERATION_PROMPT)
            chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
            res = chain.invoke({
                "context": format_docs(docs),
                "user_prompt": user_prompt or "Không có",
                "target_audience": target_audience or "người học chung"
            })
            course = json.loads(extract_json(res))
            result = {
                "course": self._normalize_course(course, docs, target_audience),
                "citations": citations,
            }
            # Save to course JSON file for GET endpoint
            course_path = get_course_path(self.course_id)["course"]
            with open(course_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            return result
        except Exception as e:
            logger.warning("Course generation failed, using fallback: %s", e)
            result = {
                "course": self._build_fallback_course(docs, target_audience),
                "citations": citations,
            }
            # Save fallback too so GET can retrieve
            course_path = get_course_path(self.course_id)["course"]
            with open(course_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            return result

    # 4.2 Summary
    def generate_summary_v2(self, summary_type: str = "detailed"):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke("nội dung trọng tâm")
        citations = self._get_citations(docs)
        try:
            prompt = ChatPromptTemplate.from_template(SUMMARY_V2_PROMPT)
            chain = prompt | get_llm(temperature=0.2) | StrOutputParser()
            res = chain.invoke({
                "context": format_docs(docs),
                "type": summary_type
            })
            if not res or not res.strip():
                raise ValueError("LLM returned an empty summary.")
            return {"summary": res, "citations": citations}
        except Exception as e:
            logger.warning("Summary generation failed, using fallback: %s", e)
            return {
                "summary": self._build_fallback_summary(docs, summary_type),
                "citations": citations,
            }

    # 4.3 Flashcards
    def generate_flashcards_v2(self, count: int):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke("khái niệm định nghĩa")
        citations = self._get_citations(docs)

        try:
            prompt = ChatPromptTemplate.from_template(FLASHCARDS_V2_PROMPT)
            chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
            res = chain.invoke({"context": format_docs(docs), "count": count})
            flashcards = json.loads(extract_json(res))
            if not isinstance(flashcards, list) or not flashcards:
                raise ValueError("LLM did not return a non-empty flashcard array.")
            return {"flashcards": flashcards[:count], "citations": citations}
        except Exception as e:
            logger.warning("Flashcard LLM generation failed, using fallback: %s", e)
            return {
                "flashcards": self._build_fallback_flashcards(docs, count),
                "citations": citations,
            }

    def _build_fallback_flashcards(self, docs, count: int):
        """Build simple citation-backed flashcards when LLM output is unavailable."""
        cards = []
        for doc in docs:
            text = self._clean_doc_text(doc, 280)
            if not text:
                continue
            answer = text
            if len(answer) < 40:
                continue
            page = doc.metadata.get("page", "?")
            source = os.path.basename(
                doc.metadata.get("source_file", doc.metadata.get("source", "unknown"))
            )
            cards.append(
                {
                    "question": f"Ý chính cần ghi nhớ ở trang {page} là gì?",
                    "answer": answer,
                    "citation": {
                        "page": page,
                        "source": source,
                        "chunk_id": doc.metadata.get("chunk_id", ""),
                    },
                }
            )
            if len(cards) >= count:
                break

        if cards:
            return cards
        return [
            {
                "question": "Tài liệu này cần được ôn tập như thế nào?",
                "answer": "Hãy xem lại các phần chính trong tài liệu và tạo câu hỏi theo từng khái niệm quan trọng.",
                "citation": {"page": "?", "source": "unknown", "chunk_id": ""},
            }
        ]

    # 4.4 Quiz
    def generate_quiz_v2(self, topic: str, quantity: int, difficulty: str):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(topic)
        citations = self._get_citations(docs)
        try:
            prompt = ChatPromptTemplate.from_template(QUIZ_V2_PROMPT)
            chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
            res = chain.invoke({
                "context": format_docs(docs), "topic": topic,
                "quantity": quantity, "difficulty": difficulty
            })
            questions = json.loads(extract_json(res))
            if not isinstance(questions, list) or not questions:
                raise ValueError("LLM did not return a non-empty quiz array.")
            return {"questions": questions[:quantity], "citations": citations}
        except Exception as e:
            logger.warning("Quiz generation failed, using fallback: %s", e)
            return {
                "questions": self._build_fallback_quiz(docs, quantity, difficulty),
                "citations": citations,
            }

    # 4.5 Slides
    def generate_slides_v2(self, topic: str, num_slides: int):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(topic)
        citations = self._get_citations(docs)
        try:
            prompt = ChatPromptTemplate.from_template(SLIDES_V2_PROMPT)
            chain = prompt | get_llm(temperature=0.1) | StrOutputParser()
            res = chain.invoke({
                "context": format_docs(docs), "topic": topic, "num_slides": num_slides
            })
            slides = json.loads(extract_json(res))
            if not isinstance(slides, list) or not slides:
                raise ValueError("LLM did not return a non-empty slide array.")
            return {"slides": slides[:num_slides], "citations": citations}
        except Exception as e:
            logger.warning("Slides generation failed, using fallback: %s", e)
            return {
                "slides": self._build_fallback_slides(docs, num_slides),
                "citations": citations,
            }

    def _image_suggestion_to_keyword(self, suggestion: str) -> str:
        """
        Convert a Vietnamese image suggestion to an English Unsplash/Picsum keyword.
        Uses a simple keyword mapping for common educational/academic topics.
        Falls back to generic 'education learning' if no match found.
        """
        suggestion_lower = suggestion.lower()

        keyword_map = [
            # Sciences
            (["vật lí", "vật lý", "physics", "thí nghiệm", "experiment"], "physics laboratory experiment"),
            (["hóa học", "chemistry", "phân tử", "molecule"], "chemistry science"),
            (["sinh học", "biology", "tế bào", "cell", "sinh vật"], "biology nature"),
            (["toán", "math", "số học", "algebra", "geometry"], "mathematics chalkboard"),
            (["thiên văn", "vũ trụ", "astronomy", "space", "universe"], "astronomy space stars"),
            # Social/History
            (["lịch sử", "history", "chiến tranh", "war"], "history museum"),
            (["địa lý", "geography", "bản đồ", "map"], "world map geography"),
            (["kinh tế", "economy", "tài chính", "finance"], "business finance"),
            (["xã hội", "society", "con người", "people"], "people community"),
            # Technology
            (["công nghệ", "technology", "máy tính", "computer", "lập trình", "code"], "technology computer"),
            (["robot", "ai", "trí tuệ nhân tạo", "artificial intelligence"], "artificial intelligence robot"),
            (["điện", "electric", "mạch điện", "circuit"], "electronics circuit"),
            # Education generic
            (["học sinh", "student", "trường", "school", "lớp", "classroom"], "students classroom learning"),
            (["giáo viên", "teacher", "giảng dạy", "teaching"], "teacher classroom"),
            (["sách", "book", "đọc sách", "reading", "thư viện", "library"], "books library reading"),
            (["khóa học", "course", "bài học", "lesson"], "education study"),
            # Nature/Environment
            (["thiên nhiên", "nature", "môi trường", "environment"], "nature environment"),
            (["năng lượng", "energy", "mặt trời", "solar", "gió", "wind"], "renewable energy solar"),
            # Art/Literature
            (["văn học", "literature", "thơ", "poetry", "truyện"], "literature books"),
            (["nghệ thuật", "art", "hội họa", "painting"], "art museum painting"),
        ]

        for keywords, result in keyword_map:
            if any(kw in suggestion_lower for kw in keywords):
                return result

        return "education learning knowledge"

    def _get_slide_image_url(self, image_suggestion: str, slide_index: int, width: int = 800, height: int = 500) -> str:
        """
        Generate an image URL for a slide.

        Strategy:
        1. Extract a keyword from the image_suggestion text
        2. Use Picsum with a seeded ID derived from the keyword + index for consistency
           (Picsum doesn't support keyword search, but gives beautiful photos)
        3. Each slide gets a different but reproducible image
        """
        # Use picsum with a seed based on slide index for reproducible, varied images
        # Seeds 10-99 cover a wide range of beautiful photography
        seed = (slide_index * 17 + 43) % 1000  # Spread seeds for variety
        return f"https://picsum.photos/seed/{seed}/{width}/{height}"

    def generate_slides_html(self, topic: str = "", num_slides: int = 10) -> str:
        """
        Generate a self-contained Reveal.js HTML presentation.
        Features: modern 2-column layout, real images from Picsum, clean typography,
        bullet-by-bullet animations, citation footer.
        """
        try:
            generated = self.generate_slides_v2(topic=topic, num_slides=num_slides)
        except Exception as e:
            logger.warning("Slides HTML generation fallback: %s", e)
            try:
                retriever = self.vectorstore.as_retriever(search_kwargs={"k": num_slides})
                docs = retriever.invoke(topic or "tổng quan")
                generated = {"slides": self._build_fallback_slides(docs, num_slides)}
            except Exception as e2:
                logger.warning("Fallback also failed: %s", e2)
                generated = {
                    "slides": [
                        {
                            "title": "Nội dung trọng tâm",
                            "content": "Tài liệu đã được xử lý. Hệ thống đang chạy ở chế độ offline.",
                            "image_suggestion": "education learning",
                        }
                    ]
                }
        slides = generated.get("slides", [])

        def _clean_text(text: str) -> str:
            text = re.sub(r"\s+", " ", text).strip()
            text = text.replace("\\", " ")
            # Keep Vietnamese chars + common punctuation
            text = re.sub(
                r'[^\w\s,.\?!\-:;()àáảãạâấầẩẫậăắằẳẵặéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđĐA-Za-z0-9]+',
                ' ', text
            )
            return text.strip()

        def _escape(s: str) -> str:
            return (s.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace('"', "&quot;")
                     .replace("'", "&#039;"))

        def _content_to_bullets(content: str) -> str:
            """Split content into bullet points for animated reveal."""
            content = _clean_text(content)
            if not content:
                return ""
            # Split on newlines or sentences (naive but works for most LLM output)
            lines = [l.strip() for l in re.split(r'\n|(?<=[.!?])\s+', content) if l.strip() and len(l.strip()) > 10]
            if not lines:
                lines = [content[:300]]
            bullets = ""
            for line in lines[:6]:  # Max 6 bullets per slide
                bullets += f'<li class="fragment fade-in-then-semi-out">{_escape(line)}</li>\n'
            return f'<ul class="slide-bullets">{bullets}</ul>'

        sections = []
        for idx, item in enumerate(slides):
            slide_obj = item if isinstance(item, dict) else {}
            raw_title = slide_obj.get("title") or f"Slide {idx + 1}"
            raw_content = slide_obj.get("content", "") or ""
            raw_suggestion = slide_obj.get("image_suggestion", "") or ""
            citation = slide_obj.get("citation") or {}

            title = _escape(_clean_text(raw_title))
            bullets_html = _content_to_bullets(raw_content)
            img_url = self._get_slide_image_url(raw_suggestion, idx)
            keyword = _escape(self._image_suggestion_to_keyword(raw_suggestion))

            page = citation.get("page", "")
            source = _escape(str(citation.get("source", "")))
            cite_html = ""
            if page:
                cite_html = f'<div class="cite-bar">📄 {source} — Trang {page}</div>'

            # First slide gets a hero/title layout, rest get 2-column
            if idx == 0:
                section_html = f"""
<section class="slide-hero" data-background-image="{img_url}" data-background-opacity="0.25" data-background-size="cover">
  <div class="hero-content">
    <div class="hero-eyebrow">AI Course Generator</div>
    <h1 class="hero-title">{title}</h1>
    <div class="hero-divider"></div>
    {bullets_html}
  </div>
  {cite_html}
</section>"""
            else:
                section_html = f"""
<section class="slide-two-col">
  <div class="col-image">
    <img src="{img_url}" alt="{keyword}" loading="lazy" onerror="this.style.display='none'">
    <div class="img-caption">{_escape(raw_suggestion[:80]) if raw_suggestion else keyword}</div>
  </div>
  <div class="col-content">
    <h2 class="slide-title">{title}</h2>
    {bullets_html}
    {cite_html}
  </div>
</section>"""

            sections.append(section_html)

        slides_html = "\n".join(sections)

        html = f"""<!DOCTYPE html>
<html lang='vi'>
<head>
<meta charset='utf-8'>
<title>AI Course Generator — Slides</title>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Merriweather:wght@700;900&display=swap'>
<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css'>
<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/theme/white.css'>
<style>
  /* ── Design tokens ── */
  :root {{
    --accent: #4f46e5;
    --accent-light: #818cf8;
    --surface: #f8f9ff;
    --text-primary: #0f172a;
    --text-secondary: #475569;
    --text-muted: #94a3b8;
    --radius: 12px;
    --font-display: 'Merriweather', Georgia, serif;
    --font-body: 'Inter', system-ui, sans-serif;
  }}

  /* ── Reveal overrides ── */
  .reveal {{
    font-family: var(--font-body);
    font-size: 18px;
    color: var(--text-primary);
    background: var(--surface);
  }}

  .reveal .slides section {{
    text-align: left;
    padding: 0;
    height: 100%%;
    box-sizing: border-box;
  }}

  /* ── Hero slide (slide 1) ── */
  .slide-hero {{
    display: flex !important;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 60px 80px !important;
    background: linear-gradient(135deg, #0f172a 0%%, #1e1b4b 100%%) !important;
    color: #fff !important;
    min-height: 100%%;
  }}

  .hero-eyebrow {{
    font-size: 0.65em;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--accent-light);
    font-weight: 600;
    margin-bottom: 16px;
  }}

  .hero-title {{
    font-family: var(--font-display);
    font-size: 1.9em !important;
    font-weight: 900;
    color: #fff !important;
    line-height: 1.2;
    margin: 0 0 20px 0 !important;
    max-width: 80%%;
  }}

  .hero-divider {{
    width: 60px;
    height: 4px;
    background: var(--accent);
    border-radius: 2px;
    margin-bottom: 24px;
  }}

  .hero-content .slide-bullets {{
    color: rgba(255,255,255,0.85);
    font-size: 0.85em;
  }}

  /* ── Two-column slide ── */
  .slide-two-col {{
    display: flex !important;
    flex-direction: row;
    height: 100%%;
    overflow: hidden;
  }}

  .col-image {{
    flex: 0 0 42%%;
    position: relative;
    overflow: hidden;
    background: #1e1b4b;
  }}

  .col-image img {{
    width: 100%%;
    height: 100%%;
    object-fit: cover;
    display: block;
    opacity: 0.9;
  }}

  .img-caption {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 10px 14px;
    background: linear-gradient(transparent, rgba(0,0,0,0.7));
    color: rgba(255,255,255,0.75);
    font-size: 0.5em;
    line-height: 1.4;
    font-style: italic;
  }}

  .col-content {{
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 40px 48px;
    overflow-y: auto;
    background: #fff;
  }}

  /* ── Typography ── */
  .slide-title {{
    font-family: var(--font-display);
    font-size: 1.15em !important;
    font-weight: 700;
    color: var(--text-primary) !important;
    line-height: 1.3;
    margin: 0 0 20px 0 !important;
    padding-bottom: 14px;
    border-bottom: 3px solid var(--accent);
  }}

  /* ── Bullets ── */
  .slide-bullets {{
    list-style: none;
    padding: 0;
    margin: 0;
    flex: 1;
  }}

  .slide-bullets li {{
    position: relative;
    padding: 9px 0 9px 22px;
    font-size: 0.82em;
    line-height: 1.55;
    color: var(--text-secondary);
    border-bottom: 1px solid #f1f5f9;
  }}

  .slide-bullets li:last-child {{ border-bottom: none; }}

  .slide-bullets li::before {{
    content: '';
    position: absolute;
    left: 0;
    top: 18px;
    width: 8px;
    height: 8px;
    background: var(--accent);
    border-radius: 50%%;
    flex-shrink: 0;
  }}

  /* ── Citation bar ── */
  .cite-bar {{
    margin-top: 18px;
    padding: 8px 12px;
    background: #f1f5f9;
    border-left: 3px solid var(--accent-light);
    border-radius: 0 var(--radius) var(--radius) 0;
    font-size: 0.6em;
    color: var(--text-muted);
    font-style: italic;
  }}

  .slide-hero .cite-bar {{
    background: rgba(255,255,255,0.1);
    border-left-color: var(--accent-light);
    color: rgba(255,255,255,0.6);
    margin-top: 24px;
  }}

  /* ── Progress & controls ── */
  .reveal .progress {{ color: var(--accent); }}
  .reveal .controls button {{ color: var(--accent) !important; }}

  /* ── Fragment animations ── */
  .reveal .fragment.fade-in-then-semi-out.visible:not(.current-fragment) {{
    opacity: 0.45;
  }}
</style>
</head>
<body>
<div class='reveal'>
  <div class='slides'>
{slides_html}
  </div>
</div>
<script src='https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js'></script>
<script>
  Reveal.initialize({{
    hash: true,
    keyboard: true,
    touch: true,
    transition: 'slide',
    backgroundTransition: 'fade',
    progress: true,
    slideNumber: 'c/t',
    controls: true,
    center: false,
    width: '100%%',
    height: '100%%',
    margin: 0,
  }});
</script>
</body>
</html>"""
        return html
        
    

    

    # ═══════════════════════════════════════════════════════════════════════════
    # PODCAST — Feature 6.7 [14]
    # ═══════════════════════════════════════════════════════════════════════════
    
    

    def generate_podcast_script(self) -> dict:
        """Generate podcast dialogue script with citations."""
        self.rag._require_ready()
        try:
            logger.info(" -> Đang tạo kịch bản podcast (LLM)...")
            raw = self.rag.audio_chain.invoke({})
            clean = extract_json(raw)
            data = json.loads(clean, strict=False)

            script = []
            if isinstance(data, list):
                script = data
            elif isinstance(data, dict):
                for key in ["podcast", "script", "segments", "dialogue"]:
                    if key in data and isinstance(data[key], list):
                        script = data[key]
                        break
                if not script:
                    for val in data.values():
                        if isinstance(val, list):
                            script = val
                            break

            if not script:
                raise ValueError("Không tìm thấy mảng hội thoại trong JSON trả về.")

            audio_dir = get_course_path(self.course_id)["audio"]
            os.makedirs(audio_dir, exist_ok=True)
            script_path = os.path.join(audio_dir, "podcast_script.json")

            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script, f, indent=2, ensure_ascii=False)

            # Retrieve relevant docs for citations
            retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})
            docs = retriever.invoke("nội dung podcast tổng quan")
            citations = self._get_citations(docs)

            return {"script": script, "citations": citations}
        except Exception as e:
            logger.error(f"[PodcastScript] LỖI: {e}")
            raise

    def generate_podcast_audio(self) -> str:
        """Chuyển kịch bản thành MP3 - Bản sửa lỗi lọc ký tự đặc biệt và xử lý file rỗng."""
        import edge_tts
        import asyncio
        import shutil
        import threading
        import re
        from pydub import AudioSegment

        # Ép đường dẫn FFmpeg cho Mac
        possible_ffmpeg = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
        for path in possible_ffmpeg:
            if shutil.which(path):
                AudioSegment.converter = path
                break

        def clean_text_for_tts(text: str) -> str:
            """Loại bỏ các ký tự LaTeX và ký tự đặc biệt gây lỗi TTS."""
            # Xóa các ký hiệu toán học $...$
            text = re.sub(r'\$.*?\$', '', text)
            # Xóa các ký tự backslash và lệnh LaTeX
            text = text.replace('\\', ' ')
            # Chỉ giữ lại chữ cái, số, dấu câu tiếng Việt cơ bản
            text = re.sub(r'[^\w\s,.\?!\-áàảãạâấầẩẫậăắằẳẵặéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵĐđ]', ' ', text)
            # Xóa khoảng trắng thừa
            return re.sub(r'\s+', ' ', text).strip()

        self.rag._require_ready()
        try:
            audio_dir = get_course_path(self.course_id)["audio"]
            script_path = os.path.join(audio_dir, "podcast_script.json")
            final_audio_path = os.path.join(audio_dir, "podcast_full.mp3")

            with open(script_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # --- 1. CHUẨN HÓA & LÀM SẠCH VĂN BẢN ---
            script = []
            items = raw_data if isinstance(raw_data, list) else []
            if isinstance(raw_data, dict):
                for val in raw_data.values():
                    if isinstance(val, list): items = val; break
            
            for item in items:
                if isinstance(item, dict):
                    raw_text = str(item.get("text", ""))
                    cleaned_text = clean_text_for_tts(raw_text)
                    if len(cleaned_text) > 1:
                        script.append({
                            "speaker": str(item.get("speaker", "Alice")),
                            "text": cleaned_text
                        })

            temp_dir = os.path.join(audio_dir, "temp_chunks")
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            # --- 2. HÀM CHẠY TTS (Có bắt lỗi từng dòng) ---
            async def tts_worker():
                voices = {"Alice": "vi-VN-HoaiMyNeural", "Bob": "vi-VN-NamMinhNeural"}
                for i, line in enumerate(script):
                    voice = voices.get(line["speaker"], voices["Alice"])
                    chunk_path = os.path.join(temp_dir, f"line_{i:03d}.mp3")
                    try:
                        comm = edge_tts.Communicate(line["text"], voice)
                        await comm.save(chunk_path)
                    except Exception as e:
                        logger.error(f" -> Bỏ qua dòng {i+1} do lỗi TTS: {e}")
                        # Không tạo file rỗng, để tí nữa logic merge sẽ tự bỏ qua

            def start_loop():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(tts_worker())
                new_loop.close()

            logger.info(" -> Đang chuyển văn bản thành giọng nói...")
            thread = threading.Thread(target=start_loop)
            thread.start()
            thread.join()

            # --- 3. GỘP FILE (Thông minh: Bỏ qua file lỗi/rỗng) ---
            logger.info(" -> Đang ráp nối các đoạn âm thanh hợp lệ...")
            combined = AudioSegment.empty()
            chunks = sorted([f for f in os.listdir(temp_dir) if f.endswith(".mp3")])
            
            valid_count = 0
            for chunk_file in chunks:
                path = os.path.join(temp_dir, chunk_file)
                # Kiểm tra file có nội dung (không phải 0 byte)
                if os.path.getsize(path) > 100: 
                    try:
                        segment = AudioSegment.from_mp3(path)
                        combined += segment
                        combined += AudioSegment.silent(duration=600)
                        valid_count += 1
                    except Exception:
                        logger.warning(f" -> File {chunk_file} bị lỗi decode, bỏ qua.")

            if valid_count == 0:
                raise RuntimeError("Không có đoạn âm thanh nào hợp lệ để tạo Podcast.")

            combined.export(final_audio_path, format="mp3")
            shutil.rmtree(temp_dir)
            logger.info(f"✅ Podcast thành công với {valid_count} đoạn hội thoại!")
            return final_audio_path

        except Exception as e:
            logger.error(f"[PodcastAudio] LỖI: {str(e)}")
            raise RuntimeError(f"Lỗi hệ thống âm thanh: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # STUDY GUIDE — Feature 6.8 [14]
    # ═══════════════════════════════════════════════════════════════════════════

    def generate_study_guide(self) -> dict:
        """Generate structured study guide with auto-continue logic and citations."""
        self.rag._require_ready()

        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke("nội dung chi tiết hệ thống hóa kiến thức")
        full_context = "\n\n".join([doc.page_content for doc in docs])

        logger.info(" -> Đang tạo phần 1 của Study Guide...")
        guide_content = self.rag.guide_chain.invoke({"topic": "nội dung chi tiết"}).strip()

        max_parts = 2
        for i in range(max_parts):
            if any(marker in guide_content for marker in ["V. CÂU HỎI", "📌 V.", "TÓM TẮT BÀI HỌC"]):
                break

            logger.info(f" -> Phát hiện nội dung bị cắt cụt, đang viết tiếp phần {i+2}...")

            continue_llm = get_llm(temperature=0.2)
            continue_prompt = ChatPromptTemplate.from_messages([
                ("system", CONTINUE_GUIDE_PROMPT),
                ("human", "Hãy viết tiếp bản thảo."),
            ])
            continue_chain = continue_prompt | continue_llm | StrOutputParser()

            last_context = guide_content[-1000:]
            additional_content = continue_chain.invoke({
                "context": full_context,
                "existing_content": last_context
            }).strip()

            if guide_content[-1] in [".", "!", "?", "}", "]", "\n"]:
                guide_content += "\n\n" + additional_content
            else:
                guide_content += " " + additional_content

            time.sleep(2)

        guide_content = guide_content.replace("---", "").replace("---", "")

        guides_dir = get_course_path(self.course_id)["guides"]
        os.makedirs(guides_dir, exist_ok=True)
        guide_path = os.path.join(guides_dir, "study_guide.md")

        with open(guide_path, "w", encoding="utf-8") as f:
            f.write(guide_content)

        citations = self._get_citations(docs)
        return {"guide": guide_content, "citations": citations}

    # ═══════════════════════════════════════════════════════════════════════════
    # FLASHCARDS — Feature 6.9 [14]
    # ═══════════════════════════════════════════════════════════════════════════