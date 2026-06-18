from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.app.config import get_settings
from backend.app.schemas import CourseResponse, ErrorResponse
from backend.app.services.course_generator import GeminiCourseGenerator
from backend.app.services.demo_course_generator import build_demo_course
from backend.app.services.pdf_reader import build_model_context, extract_pages_from_pdf
from backend.app.services.storage import save_course_package, save_uploaded_file

settings = get_settings()

app = FastAPI(
    title="StudyHack.AI Course Compiler Backend",
    version="5.5.0",
    description="Backend Python: xử lý PDF, gọi Gemini, lưu course package maintainable.",
)

# Next.js dev server gọi backend từ server-side route.
# CORS vẫn mở cho dev/debug qua /docs, nhưng API key không nằm ở browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "backend",
        "model": settings.gemini_model,
        "ocr_enabled": settings.enable_ocr,
        "demo_mode": settings.demo_mode,
        "auto_demo_on_ai_error": settings.auto_demo_on_ai_error,
        "has_google_api_key": settings.has_google_api_key,
        "api_key_looks_like_google_key": settings.api_key_looks_like_google_key,
        "note": "Gemini API keys usually start with AIza. Do not expose your key publicly.",
    }


@app.post(
    "/api/course/upload",
    response_model=CourseResponse,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_course(file: UploadFile = File(...)) -> CourseResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Thiếu tên file.")

    suffix = Path(file.filename).suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Phiên bản local này đang hỗ trợ PDF trước.")

    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File vượt quá {settings.max_upload_mb}MB.")

    saved_pdf = save_uploaded_file(settings.uploads_dir, file.filename, content)

    try:
        pages = extract_pages_from_pdf(content, settings)
        extracted_chars = sum(len(page.text) for page in pages)
        if extracted_chars < settings.min_text_chars:
            raise HTTPException(
                status_code=422,
                detail=(
                    "PDF có quá ít text để tạo khóa học. Nếu là scan ảnh, bật ENABLE_OCR=true "
                    "và cài Tesseract OCR trên máy."
                ),
            )

        context = build_model_context(pages, settings.max_context_chars)

        generation_mode = "gemini"
        generation_error = ""

        if settings.demo_mode:
            generation_mode = "demo_mode"
            course = build_demo_course(context, file.filename, reason="DEMO_MODE=true trong file .env")
        else:
            try:
                generator = GeminiCourseGenerator(settings)
                course = generator.generate_course(context=context, source_file=file.filename)
            except Exception as exc:
                generation_error = str(exc)
                if settings.auto_demo_on_ai_error:
                    generation_mode = "demo_fallback_after_ai_error"
                    course = build_demo_course(context, file.filename, reason=generation_error)
                else:
                    lowered = generation_error.lower()
                    if "api key" in lowered or "apikey" in lowered or "permission" in lowered or "unauth" in lowered:
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "Gemini API key có vẻ không hợp lệ hoặc chưa có quyền dùng model. "
                                "Hãy kiểm tra GOOGLE_API_KEY trong .env. Gemini API key thường bắt đầu bằng AIza. "
                                f"Chi tiết kỹ thuật: {generation_error}"
                            ),
                        ) from exc
                    raise

        saved_course_dir = save_course_package(settings.courses_dir, course, file.filename)

        message = "Đã tạo khóa học từ PDF thành công."
        if generation_mode != "gemini":
            message = "Đã tạo course bằng chế độ dự phòng để frontend chạy được. Kiểm tra debug.generation_error để sửa Gemini key/quota nếu muốn dùng AI thật."

        return CourseResponse(
            status="success",
            message=message,
            course=course,
            debug={
                "saved_pdf": str(saved_pdf),
                "saved_course_dir": str(saved_course_dir),
                "pages_extracted": len(pages),
                "characters_extracted": extracted_chars,
                "context_characters_sent": len(context),
                "ocr_enabled": settings.enable_ocr,
                "generation_mode": generation_mode,
                "generation_error": generation_error,
                "has_google_api_key": settings.has_google_api_key,
                "api_key_looks_like_google_key": settings.api_key_looks_like_google_key,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/courses")
def list_courses() -> dict:
    course_dirs = sorted(
        [path for path in settings.courses_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return {"courses": [path.name for path in course_dirs]}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
