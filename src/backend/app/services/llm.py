"""Paid-only OpenRouter LLM service with strict structured-output validation."""

import base64
import logging
import os
from typing import Any, Callable, List, Optional

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.generator_output import (
    BookChapterContent,
    BookChapterPlan,
    BookOutline,
    BookSection,
    CourseTitleOutput,
    QuizOption,
    QuizOutput,
    QuizQuestion,
    SlideItem,
    SlidesOutput,
    VidOutput,
    VidScene,
)
from app.services.provider_errors import (
    ProviderRequestError,
    classify_openrouter_error,
)

logger = logging.getLogger(__name__)

COURSE_TITLE_MAX_TOKENS = 512
BOOK_OUTLINE_MAX_TOKENS = 8192
BOOK_CHAPTER_MAX_TOKENS = 16384
SLIDES_MAX_TOKENS = 8192
QUIZ_MAX_TOKENS = 8192
VID_MAX_TOKENS = 8192


def _quiz_max_tokens(quantity: int) -> int:
    """Scale the JSON output budget with question count so large quizzes don't get
    truncated mid-response (each MCQ + 4 options + VN explanation is ~600-900 tokens)."""
    return max(QUIZ_MAX_TOKENS, min(4096 + quantity * 900, 32768))


def _slides_max_tokens(num_slides: int) -> int:
    """Scale the JSON output budget with slide count so long decks don't get truncated."""
    return max(SLIDES_MAX_TOKENS, min(2048 + num_slides * 500, 24576))

class LLMGenerationError(Exception):
    """Raised when both attempts with the configured OpenRouter model fail."""


def _friendly_openrouter_error(exc: Exception) -> str:
    """Map provider failures to a clean Vietnamese message safe to show in the UI."""
    text = str(exc)
    if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in text or "UNAUTHENTICATED" in text or "401" in text:
        return (
            "OpenRouter API key không hợp lệ hoặc đã hết hạn."
        )
    if "PERMISSION_DENIED" in text or "403" in text:
        return "OpenRouter API key không có quyền truy cập mô hình này."
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return "Các mô hình AI hiện đang hết hạn mức hoặc quá tải. Vui lòng thử lại sau."
    if "UNAVAILABLE" in text or "503" in text:
        return "Dịch vụ AI đang quá tải tạm thời. Vui lòng thử lại sau ít phút."
    if "json_invalid" in text or "EOF while parsing" in text or "Invalid JSON" in text:
        return "Nội dung sinh ra bị cắt do quá dài. Vui lòng thử tạo lại (hoặc giảm số lượng yêu cầu)."
    return f"Dịch vụ AI gặp lỗi: {text[:300]}"


class LLMService:
    """Service wrapper for one paid OpenRouter model with one same-model retry."""

    def __init__(self, model: Optional[str] = None):
        self.client = None
        self.model = model or settings.OPENROUTER_MODEL
        self._test_mode = "PYTEST_CURRENT_TEST" in os.environ
        self._init_client()
        self.prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

    def _init_client(self):
        """Initialize the OpenRouter client, allowing mock mode only under pytest."""
        if self._test_mode:
            logger.info("PYTEST_CURRENT_TEST detected: using mock mode for LLMService.")
            return
        try:
            from openai import OpenAI

            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
                max_retries=0,
            )
            logger.info("Initialized OpenRouter client with model %s", self.model)
        except Exception as exc:
            logger.exception("Failed to initialize OpenRouter client")
            raise LLMGenerationError("Không thể khởi tạo dịch vụ AI OpenRouter.") from exc

    def _load_prompt(self, template_name: str, **kwargs) -> str:
        """Load and format prompt template from app/prompts directory."""
        file_path = os.path.join(self.prompts_dir, template_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                template = f.read()
            return template.format(**kwargs)
        except Exception as e:
            logger.error(f"Error loading prompt template {template_name}: {e}")
            return f"Generate {template_name} with context: {kwargs.get('context', '')}"

    def _call_openrouter_strict(
        self,
        prompt: str,
        schema_model: Any,
        fallback_fn: Callable[[], Any],
        max_output_tokens: int,
    ) -> Any:
        """Call the configured paid model and retry it once if validation or delivery fails.

        Local Pydantic parsing deliberately remains part of the retry condition: a provider
        can return HTTP 200 while still emitting an incomplete or schema-invalid payload.
        """
        if not self.client:
            if self._test_mode:
                return fallback_fn()
            raise LLMGenerationError("Dịch vụ AI OpenRouter chưa được khởi tạo.")

        last_error: Optional[Exception] = None
        model = self.model
        for attempt in range(1, 3):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_output_tokens,
                    temperature=0.2,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_model.__name__,
                            "schema": schema_model.model_json_schema(),
                            "strict": True,
                        },
                    },
                    extra_body={"provider": {"require_parameters": True}},
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    raise LLMGenerationError("OpenRouter returned an empty response")
                return schema_model.model_validate_json(content)
            except (ValidationError, LLMGenerationError) as e:
                last_error = e
                logger.warning(
                    "OpenRouter model %s produced invalid output on attempt %s/2: %s",
                    model,
                    attempt,
                    e,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "OpenRouter model %s failed on attempt %s/2: %s",
                    model,
                    attempt,
                    e,
                )

        raise LLMGenerationError(
            _friendly_openrouter_error(last_error) if last_error else "AI generation failed."
        )

    def ocr_page_image(self, image_bytes: bytes) -> str:
        """Transcribe one rendered PDF page through the configured OpenRouter model.

        A valid empty provider response means that the page genuinely has no readable
        text. Request failures use the shared provider classifier: permanent failures stop
        after one call, while transient failures get the single same-model retry allowed by
        the OCR contract. Typed failures must reach the document pipeline for persistence.
        """
        if not self.client:
            return ""
        content = [{"type": "text", "text": "Trích xuất toàn bộ văn bản có thể đọc được trong ảnh này, giữ nguyên thứ tự đọc tự nhiên. Chỉ trả về văn bản thuần, không thêm giải thích hay định dạng markdown."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"}}]
        model = self.model
        for attempt in range(1, 3):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    max_tokens=4096,
                    temperature=0.0,
                    extra_body={"provider": {"require_parameters": True}},
                )
                text = response.choices[0].message.content if response.choices else None
                if text and text.strip():
                    return text.strip()
                return ""
            except Exception as exc:
                failure = (
                    exc.failure
                    if isinstance(exc, ProviderRequestError)
                    else classify_openrouter_error(exc)
                )
                logger.warning(
                    "OCR via OpenRouter model %s failed on attempt %s/2 with %s",
                    model,
                    attempt,
                    failure.code,
                )
                if not failure.automatic_retry or attempt == 2:
                    if isinstance(exc, ProviderRequestError):
                        raise
                    raise ProviderRequestError(failure) from exc
        raise AssertionError("unreachable OCR retry state")

    def generate_course_title(self, context: str) -> CourseTitleOutput:
        """Generate a short, human-friendly course title from a sample of extracted document text."""
        prompt = self._load_prompt("course_title.txt", context=context)

        def _fallback():
            return CourseTitleOutput(title="")

        return self._call_openrouter_strict(prompt, CourseTitleOutput, _fallback, COURSE_TITLE_MAX_TOKENS)

    def generate_book_outline(
        self,
        context: str,
        detail_level: str = "Tiêu chuẩn",
        user_prompt: str = "",
        doc_names: str = "",
    ) -> BookOutline:
        """Generate the whole-book outline (title, preface, chapter plans) from RAG context."""
        prompt = self._load_prompt(
            "book_outline.txt",
            detail_level=detail_level,
            user_prompt=user_prompt or "(không có)",
            doc_names=doc_names or "(không rõ)",
            context=context,
        )

        def _fallback():
            chapter_specs = [
                ("Tổng quan về Trí tuệ Nhân tạo", "Giới thiệu khái niệm AI, lịch sử phát triển và các nhánh chính.", "khái niệm cơ bản trí tuệ nhân tạo"),
                ("Học Máy và Các Thuật Toán Nền Tảng", "Trình bày nguyên lý học máy, các loại học có giám sát/không giám sát.", "học máy thuật toán nền tảng"),
                ("Mạng Thần Kinh và Học Sâu", "Đi sâu vào cấu trúc mạng thần kinh nhân tạo và học sâu.", "mạng thần kinh học sâu"),
                ("Ứng Dụng Thực Tiễn", "Khảo sát các ứng dụng AI trong đời sống và công nghiệp.", "ứng dụng trí tuệ nhân tạo thực tiễn"),
                ("Xu Hướng và Thách Thức", "Bàn về xu hướng phát triển và các thách thức đạo đức, kỹ thuật.", "xu hướng thách thức trí tuệ nhân tạo"),
            ]
            chapters = [
                BookChapterPlan(
                    chapter_number=i + 1,
                    chapter_title=title,
                    description=desc,
                    retrieval_query=query,
                    planned_sections=[f"{title} — Phần 1", f"{title} — Phần 2", f"{title} — Phần 3"],
                )
                for i, (title, desc, query) in enumerate(chapter_specs)
            ]
            return BookOutline(
                title="Sách Ôn Tập: Trí Tuệ Nhân Tạo Căn Bản",
                summary="Tổng hợp kiến thức cốt lõi về Trí tuệ Nhân tạo và Học máy từ tài liệu của bạn, trình bày theo trình tự từ nền tảng đến ứng dụng.",
                preface=(
                    "Cuốn sách này được biên soạn nhằm giúp bạn ôn tập lại những kiến thức cốt lõi đã có trong tài liệu gốc "
                    "một cách nhanh chóng và dễ hiểu. Mỗi chương được thiết kế để đứng độc lập, giúp bạn tra cứu theo đúng "
                    "chủ đề mình cần mà không phải đọc lại toàn bộ tài liệu dài. Chúng tôi khuyến khích bạn đọc tuần tự từ "
                    "chương đầu để nắm vững nền tảng trước khi chuyển sang các chương ứng dụng nâng cao hơn. Sau mỗi chương "
                    "đều có phần câu hỏi ôn tập — hãy thử tự trả lời trước khi xem lại nội dung để kiểm tra mức độ ghi nhớ "
                    "của bản thân. Chúc bạn học tập hiệu quả."
                ),
                chapters=chapters,
            )

        return self._call_openrouter_strict(prompt, BookOutline, _fallback, BOOK_OUTLINE_MAX_TOKENS)

    def generate_book_chapter(
        self,
        book_title: str,
        chapter_plan: BookChapterPlan,
        total_chapters: int,
        context: str,
        detail_level: str = "Tiêu chuẩn",
        valid_chunk_ids: List[str] = None,
    ) -> BookChapterContent:
        """Generate the full content for a single chapter from chapter-specific RAG context."""
        prompt = self._load_prompt(
            "book_chapter.txt",
            book_title=book_title,
            chapter_number=chapter_plan.chapter_number,
            total_chapters=total_chapters,
            chapter_title=chapter_plan.chapter_title,
            chapter_description=chapter_plan.description,
            planned_sections=", ".join(chapter_plan.planned_sections) or "(do bạn tự đề xuất)",
            detail_level=detail_level,
            context=context,
        )
        cids = valid_chunk_ids or ["chunk_1", "chunk_2"]

        def _fallback():
            sections = [
                BookSection(
                    title=title,
                    content=(
                        f"{title} là một phần quan trọng trong chương này, liên quan trực tiếp đến {chapter_plan.chapter_title.lower()}. "
                        "Nội dung được trình bày dựa trên các khái niệm nền tảng đã đề cập trong tài liệu gốc, giúp người đọc "
                        "hình dung rõ bản chất vấn đề trước khi đi vào chi tiết kỹ thuật.\n\n"
                        "Để dễ hình dung hơn, hãy tưởng tượng quá trình này giống như việc một người học nghề quan sát và "
                        "thực hành nhiều lần trước khi thành thạo — hệ thống cũng dần cải thiện thông qua quá trình lặp lại "
                        "và điều chỉnh dựa trên phản hồi thu được."
                    ),
                )
                for title in (chapter_plan.planned_sections[:3] or [f"{chapter_plan.chapter_title} — Nội dung chính"])
            ]
            return BookChapterContent(
                chapter_title=chapter_plan.chapter_title,
                introduction=(
                    f"Chương này tập trung vào {chapter_plan.chapter_title.lower()}, một nội dung then chốt giúp bạn xây dựng "
                    "nền tảng vững chắc trước khi tiếp cận các chương tiếp theo. Chúng ta sẽ đi từ khái niệm cơ bản đến các "
                    "ví dụ minh họa cụ thể, giúp việc ôn tập trở nên trực quan và dễ nhớ hơn."
                ),
                objectives=[
                    f"Giải thích được các khái niệm cốt lõi của {chapter_plan.chapter_title.lower()}",
                    "Phân biệt được các thành phần chính đã trình bày trong chương",
                ],
                sections=sections,
                key_points=[
                    f"{chapter_plan.chapter_title} xây dựng nền tảng cho các chương sau",
                    "Kiến thức cần được liên hệ với ví dụ thực tế để ghi nhớ lâu dài",
                ],
                review_questions=[
                    f"Hãy tóm tắt lại nội dung chính của {chapter_plan.chapter_title.lower()} bằng lời của bạn.",
                    "Bạn có thể liên hệ nội dung chương này với một tình huống thực tế nào?",
                ],
                source_chunk_ids=cids[:2],
            )

        return self._call_openrouter_strict(prompt, BookChapterContent, _fallback, BOOK_CHAPTER_MAX_TOKENS)

    def generate_slides(
        self, context: str, topic: str = "AI Overview", num_slides: int = 15, valid_chunk_ids: List[str] = None
    ) -> SlidesOutput:
        """Generate Presentation Slides from RAG context."""
        prompt = self._load_prompt("slides.txt", topic=topic, num_slides=num_slides, context=context)
        cids = valid_chunk_ids or ["chunk_1"]

        def _fallback():
            slides = []
            for i in range(1, num_slides + 1):
                slides.append(
                    SlideItem(
                        slide_number=i,
                        title=f"Slide {i}: {topic} - Phần {i}",
                        layout_type="two_column" if i % 2 == 0 else ("quote" if i == 3 else "default"),
                        bullet_points=[
                            "Khái niệm cốt lõi từ tài liệu học tập",
                            "Nguyên lý hoạt động và phân tích hệ thống",
                            "Ứng dụng thực tiễn trong ngành công nghệ",
                        ],
                        source_chunk_ids=cids,
                    )
                )
            return SlidesOutput(
                title=f"Bài Giảng Trình Chiếu: {topic}",
                slides=slides,
            )

        return self._call_openrouter_strict(prompt, SlidesOutput, _fallback, _slides_max_tokens(num_slides))

    _QUIZ_DIFFICULTY_DIRECTIVES = {
        "easy": "Tất cả câu hỏi ở mức DỄ (Bloom: Easy) — kiểm tra ghi nhớ và nhận biết khái niệm cơ bản.",
        "medium": "Tất cả câu hỏi ở mức TRUNG BÌNH (Bloom: Medium) — yêu cầu hiểu và vận dụng kiến thức.",
        "hard": "Tất cả câu hỏi ở mức KHÓ (Bloom: Hard) — yêu cầu phân tích, so sánh, đánh giá và suy luận sâu.",
        "mixed": "Phân bổ đa dạng các mức độ theo thang Bloom (Easy / Medium / Hard), tăng dần độ khó từ đầu đến cuối bộ đề.",
    }

    def generate_quiz(
        self,
        context: str,
        topic: str = "AI Quiz",
        quantity: int = 5,
        valid_chunk_ids: List[str] = None,
        difficulty: str = "mixed",
    ) -> QuizOutput:
        """Generate Multiple Choice Quiz from RAG context."""
        directive = self._QUIZ_DIFFICULTY_DIRECTIVES.get(
            str(difficulty or "mixed").strip().lower(),
            self._QUIZ_DIFFICULTY_DIRECTIVES["mixed"],
        )
        prompt = self._load_prompt(
            "quiz.txt", topic=topic, quantity=quantity, context=context, difficulty=directive
        )
        cids = valid_chunk_ids or ["chunk_1"]

        def _fallback():
            questions = []
            for i in range(1, quantity + 1):
                questions.append(
                    QuizQuestion(
                        question_number=i,
                        question_text=f"Câu hỏi {i}: Theo tài liệu, đặc điểm chính của {topic} là gì?",
                        difficulty="Easy" if i == 1 else ("Hard" if i == quantity else "Medium"),
                        options=[
                            QuizOption(key="A", text="Khả năng tự động hóa và học hỏi từ dữ liệu"),
                            QuizOption(key="B", text="Chỉ xử lý được dữ liệu văn bản tĩnh không cấu trúc"),
                            QuizOption(key="C", text="Không cần sự can thiệp hay lập trình của con người từ ban đầu"),
                            QuizOption(key="D", text="Hoạt động hoàn toàn độc lập không cần phần cứng máy tính"),
                        ],
                        correct_answer="A",
                        explanation="Theo phần tổng quan trong tài liệu, hệ thống thông minh có khả năng học hỏi từ dữ liệu và tự động hóa quy trình.",
                        source_chunk_ids=cids,
                    )
                )
            return QuizOutput(
                title=f"Bộ Đề Đánh Giá Năng Lực: {topic}",
                questions=questions,
            )

        return self._call_openrouter_strict(prompt, QuizOutput, _fallback, _quiz_max_tokens(quantity))

    def generate_vid(
        self,
        context: str,
        topic: str = "AI Video",
        fmt: str = "standard",
        user_prompt: str = "",
        valid_chunk_ids: List[str] = None,
    ) -> VidOutput:
        """Generate a narrated Video script (minimal on-frame text, voice-led) from RAG context."""
        from app.services.video_render import format_guidance, narration_hint, scene_count_hint

        prompt = self._load_prompt(
            "vid.txt",
            topic=topic,
            user_prompt=user_prompt or "(không có)",
            scene_hint=scene_count_hint(fmt),
            narration_hint=narration_hint(fmt),
            format_guidance=format_guidance(fmt),
            context=context,
        )
        cids = valid_chunk_ids or ["chunk_1"]

        def _fallback():
            return VidOutput(
                title=f"Video: {topic}",
                total_duration_seconds=0,
                scenes=[
                    VidScene(
                        scene_number=1,
                        title="Điều gì đang xảy ra?",
                        on_screen_text="Một câu hỏi cần lời giải",
                        duration_seconds=0,
                        narration=f"Điều gì khiến {topic} trở thành vấn đề đáng chú ý? Câu trả lời nằm ở cách các ý chính trong tài liệu kết nối với nhau.",
                        source_chunk_ids=cids,
                    ),
                    VidScene(
                        scene_number=2,
                        title="Nội dung cốt lõi",
                        on_screen_text="",
                        duration_seconds=0,
                        narration="Như tài liệu đã chỉ ra, cấu trúc của hệ thống dựa trên việc thu thập dữ liệu và huấn luyện mô hình theo từng bước rõ ràng.",
                        source_chunk_ids=cids,
                    ),
                    VidScene(
                        scene_number=3,
                        title="Tổng kết",
                        on_screen_text="",
                        duration_seconds=0,
                        narration="Tóm lại, chúng ta vừa tìm hiểu nguyên lý cơ bản và ứng dụng thực tế. Hãy ôn lại phần Quiz để củng cố kiến thức nhé.",
                        source_chunk_ids=cids,
                    ),
                ],
            )

        return self._call_openrouter_strict(prompt, VidOutput, _fallback, VID_MAX_TOKENS)


