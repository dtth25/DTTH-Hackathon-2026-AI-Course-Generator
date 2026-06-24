"""FastAPI server for the AI Course Generator four-output API."""

import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from backend.core.config import INDEX_DIR, UPLOAD_DIR, _timestamp, get_course_path, logger, sanitize_input
from backend.services.course_gen import CourseManager


ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
ALLOW_ALL_ORIGINS = os.getenv("ALLOW_ALL_ORIGINS", "true").lower() in {"1", "true", "yes"}

MAX_UPLOAD_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "300"))

course_manager: Optional[CourseManager] = None
rate_limit_store: OrderedDict[str, list[float]] = OrderedDict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the course manager on startup."""
    global course_manager
    print(f"[{_timestamp()}] Khởi tạo CourseManager (scan FAISS indices)...")
    course_manager = CourseManager()
    courses = course_manager.list_courses()
    print(f"[{_timestamp()}] Đã phục hồi {len(courses)} tài liệu: {courses}")
    print(f"[{_timestamp()}] Sẵn sàng!")
    yield
    print(f"[{_timestamp()}] Dọn dẹp tài nguyên...")


app = FastAPI(
    title="AI Course Generator API",
    version="4.0.0",
    description="Generate exactly four grounded learning outputs: Book, Slide, Quiz, and Vid.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOW_ALL_ORIGINS else ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply a simple in-memory rate limit."""
    if request.method == "OPTIONS" or request.url.path.endswith("/status"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    rate_limit_store.setdefault(client_ip, [])
    rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < RATE_LIMIT_WINDOW]

    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Vui lòng thử lại sau."},
        )
        origin = request.headers.get("origin")
        if ALLOW_ALL_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    rate_limit_store[client_ip].append(now)

    if len(rate_limit_store) > 1000:
        old_clients = [
            ip for ip, times in rate_limit_store.items() if times and now - max(times) > RATE_LIMIT_WINDOW * 2
        ]
        for ip in old_clients:
            del rate_limit_store[ip]

    return await call_next(request)


class UploadResponse(BaseModel):
    course_id: str
    filename: str
    status: str
    message: str


class StatusResponse(BaseModel):
    status: str
    course_id: Optional[str] = None
    courses: Optional[list[str]] = None


class GenerateBookRequest(BaseModel):
    course_id: str
    user_prompt: str = ""
    target_audience: str = "sinh viên"

    @field_validator("user_prompt")
    @classmethod
    def validate_user_prompt(cls, value: str) -> str:
        value = sanitize_input(value or "")
        if len(value) > 2000:
            raise ValueError("Yêu cầu quá dài (tối đa 2000 ký tự).")
        return value

    @field_validator("target_audience")
    @classmethod
    def validate_target_audience(cls, value: str) -> str:
        value = sanitize_input(value or "sinh viên")
        if len(value) > 120:
            raise ValueError("Đối tượng học quá dài (tối đa 120 ký tự).")
        return value or "sinh viên"


class GenerateQuizRequest(BaseModel):
    course_id: str
    topic: str = "tổng quan"
    quantity: int = Field(default=10, ge=1, le=30)
    difficulty: str = "medium"

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = sanitize_input(value or "tổng quan")
        if len(value) > 200:
            raise ValueError("Chủ đề quá dài (tối đa 200 ký tự).")
        return value or "tổng quan"

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value: str) -> str:
        value = sanitize_input(value or "medium").lower()
        return value if value in {"easy", "medium", "hard"} else "medium"


class GenerateSlideRequest(BaseModel):
    course_id: str
    topic: str = "tổng quan"
    num_slides: int = Field(default=8, ge=1, le=30)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = sanitize_input(value or "tổng quan")
        if len(value) > 200:
            raise ValueError("Chủ đề quá dài (tối đa 200 ký tự).")
        return value or "tổng quan"


class GenerateVidRequest(BaseModel):
    course_id: str
    topic: str = "tổng quan"
    duration_minutes: int = Field(default=3, ge=1, le=5)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = sanitize_input(value or "tổng quan")
        if len(value) > 200:
            raise ValueError("Chủ đề quá dài (tối đa 200 ký tự).")
        return value or "tổng quan"


def _get_course_manager() -> CourseManager:
    """Return the course manager or fail if startup has not completed."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")
    return course_manager


def _get_ready_course(course_id: str):
    """Return a ready course or raise a public API error."""
    mgr = _get_course_manager()
    status = mgr.get_course_status(course_id)
    if status != "ready":
        raise HTTPException(400, f"Tài liệu '{course_id}' chưa sẵn sàng (trạng thái: {status}).")

    rag = mgr.get_course(course_id)
    if not rag:
        raise HTTPException(404, f"Không tìm thấy tài liệu '{course_id}'.")
    return rag


def _read_json(path: str, missing_message: str):
    """Read a JSON artifact from disk."""
    if not os.path.exists(path):
        raise HTTPException(404, missing_message)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_course_info(course_id: str) -> dict:
    """Build course metadata for list endpoints."""
    info = {"course_id": course_id, "status": "unknown"}
    if course_manager:
        info["status"] = course_manager.get_course_status(course_id)

    meta_path = get_course_path(course_id)["meta"]
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            info["created_at"] = meta.get("created_at")
            if "error" in meta:
                info["error"] = meta["error"]
        except Exception:
            pass
    return info


@app.get("/api/health", response_model=StatusResponse)
async def health():
    """Return backend health and registered course IDs."""
    mgr = _get_course_manager()
    return StatusResponse(status="ok", course_id=None, courses=sorted(mgr.list_courses()))


@app.get("/api/courses", response_model=StatusResponse)
async def list_courses():
    """Return registered course IDs."""
    mgr = _get_course_manager()
    return StatusResponse(status="ok", courses=sorted(mgr.list_courses()))


@app.get("/api/courses/all")
async def list_all_courses_with_meta():
    """Return all known courses with local metadata."""
    mgr = _get_course_manager()
    courses = []
    seen_ids = set()

    if os.path.exists(INDEX_DIR):
        import glob

        for faiss_meta in glob.glob(os.path.join(INDEX_DIR, "faiss_*.json")):
            try:
                with open(faiss_meta, "r", encoding="utf-8") as f:
                    course_id = json.load(f).get("course_id", "")
                if course_id and course_id not in seen_ids:
                    seen_ids.add(course_id)
                    courses.append(_build_course_info(course_id))
            except Exception:
                pass

    for course_id in mgr.list_courses():
        if course_id not in seen_ids:
            courses.append(_build_course_info(course_id))

    return {"courses": courses, "total": len(courses)}


@app.delete("/api/courses/{course_id}", response_model=StatusResponse)
async def delete_course(course_id: str):
    """Delete a course and generated public artifacts."""
    mgr = _get_course_manager()
    if not mgr.contains(course_id):
        raise HTTPException(404, f"Không tìm thấy tài liệu '{course_id}'.")
    mgr.remove_course(course_id)
    return StatusResponse(status="deleted", course_id=course_id)


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    """Upload one PDF, DOCX, or TXT document and process it in the background."""
    mgr = _get_course_manager()

    if not file.filename:
        raise HTTPException(400, "Tên file không được để trống.")

    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(400, f"Định dạng file '{file_ext}' không hợp lệ. Hệ thống chỉ hỗ trợ: {allowed}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "File bạn upload là file rỗng. Vui lòng kiểm tra lại.")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File quá lớn. Tối đa {MAX_UPLOAD_SIZE // (1024 * 1024)}MB.")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r"[^\w\-_\.]", "_", file.filename)
    file_path = os.path.join(UPLOAD_DIR, f"{int(time.time())}_{safe_name}")

    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        raise HTTPException(500, f"Lỗi trong quá trình lưu file: {exc}")

    course_id = uuid.uuid4().hex[:12]
    mgr.register_course_id(course_id, file_path)

    thread = threading.Thread(target=mgr.process_new_course, args=(course_id, file_path), daemon=True)
    thread.start()

    return UploadResponse(
        course_id=course_id,
        filename=file.filename,
        status="processing",
        message=f"File '{file.filename}' đã được nhận và đang được phân tích. ID tài liệu: {course_id}",
    )


@app.get("/api/course/{course_id}/status")
async def get_course_status(course_id: str):
    """Return document processing status."""
    mgr = _get_course_manager()
    status = mgr.get_course_status(course_id)
    info = {"course_id": course_id, "status": status}

    meta_path = get_course_path(course_id)["meta"]
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("error"):
                info["error"] = meta["error"]
        except Exception:
            pass

    return info


@app.post("/api/generate-book")
async def generate_book(req: GenerateBookRequest):
    """Generate the Book output and its downloadable PDF."""
    rag = _get_ready_course(req.course_id)
    result = rag.get_resource_generator().generate_book(req.user_prompt, req.target_audience)
    return {
        "course_id": req.course_id,
        "book": result.get("book", {}),
        "pdf_url": result.get("pdf_url", f"/api/course/{req.course_id}/book.pdf"),
    }


@app.post("/api/generate-slide")
async def generate_slide(req: GenerateSlideRequest):
    """Generate the Slide output."""
    rag = _get_ready_course(req.course_id)
    result = rag.get_resource_generator().generate_slides_v2(req.topic, req.num_slides)
    slides = result.get("slides", [])
    return {
        "course_id": req.course_id,
        "topic": req.topic,
        "total_slides": len(slides),
        "slides": slides,
    }


@app.post("/api/generate-quiz")
async def generate_quiz(req: GenerateQuizRequest):
    """Generate the Quiz output."""
    rag = _get_ready_course(req.course_id)
    result = rag.get_resource_generator().generate_quiz_v2(req.topic, req.quantity, req.difficulty)
    questions = result.get("questions", [])
    return {
        "course_id": req.course_id,
        "topic": req.topic,
        "difficulty": req.difficulty,
        "total_questions": len(questions),
        "questions": questions,
    }


@app.post("/api/generate-vid")
async def generate_vid(req: GenerateVidRequest):
    """Generate the Vid output."""
    rag = _get_ready_course(req.course_id)
    result = rag.get_resource_generator().generate_vid(req.topic, req.duration_minutes)
    return {"course_id": req.course_id, "vid": result.get("vid", {})}


@app.get("/api/course/{course_id}/book")
async def get_saved_book(course_id: str):
    """Return the generated Book JSON."""
    paths = get_course_path(course_id)
    book = _read_json(paths["book"], "Chưa có Book cho tài liệu này.")
    return {
        "course_id": course_id,
        "book": book,
        "pdf_url": f"/api/course/{course_id}/book.pdf" if os.path.exists(paths["book_pdf"]) else None,
    }


@app.get("/api/course/{course_id}/book.pdf")
async def get_saved_book_pdf(course_id: str):
    """Return the generated Book PDF."""
    paths = get_course_path(course_id)
    if not os.path.exists(paths["book_pdf"]):
        if not os.path.exists(paths["book"]):
            raise HTTPException(404, "Chưa có Book PDF cho tài liệu này.")
        rag = _get_ready_course(course_id)
        rag.get_resource_generator().export_book_pdf()

    return FileResponse(
        paths["book_pdf"],
        media_type="application/pdf",
        filename=f"book_{course_id}.pdf",
    )


@app.get("/api/course/{course_id}/slide")
async def get_saved_slide(course_id: str):
    """Return the generated Slide JSON."""
    slides = _read_json(get_course_path(course_id)["slides"], "Chưa có Slide cho tài liệu này.")
    return {"course_id": course_id, "slides": slides, "total_slides": len(slides)}


@app.get("/api/course/{course_id}/quiz")
async def get_saved_quiz(course_id: str):
    """Return the generated Quiz JSON."""
    questions = _read_json(get_course_path(course_id)["questions"], "Chưa có Quiz cho tài liệu này.")
    return {"course_id": course_id, "questions": questions, "total_questions": len(questions)}


@app.get("/api/course/{course_id}/vid")
async def get_saved_vid(course_id: str):
    """Return the generated Vid metadata."""
    vid_path = os.path.join(get_course_path(course_id)["videos"], "vid.json")
    return {"course_id": course_id, "vid": _read_json(vid_path, "Chưa có Vid cho tài liệu này.")}


@app.get("/api/course/{course_id}/vid/file")
async def get_saved_vid_file(course_id: str):
    """Return the generated Vid MP4 file."""
    video_path = os.path.join(get_course_path(course_id)["videos"], "vid.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(404, "Chưa có file Vid cho tài liệu này.")
    return FileResponse(video_path, media_type="video/mp4", filename=f"vid_{course_id}.mp4")


@app.get("/api/course/{course_id}/files")
async def get_course_files(course_id: str):
    """List generated public artifacts for a course."""
    paths = get_course_path(course_id)
    files = {}

    for key in ["book", "book_pdf", "questions", "slides"]:
        if os.path.exists(paths[key]):
            files[key] = paths[key]

    video_dir = paths["videos"]
    if os.path.exists(video_dir):
        files["vid"] = sorted(os.listdir(video_dir))

    return {"course_id": course_id, "files": files}


@app.get("/api/course/{course_id}/stats")
async def get_course_stats(course_id: str):
    """Return basic artifact availability stats."""
    mgr = _get_course_manager()
    if not mgr.contains(course_id):
        raise HTTPException(404, f"Không tìm thấy tài liệu '{course_id}'.")

    paths = get_course_path(course_id)
    stats = {
        "course_id": course_id,
        "status": mgr.get_course_status(course_id),
        "generated_at": _timestamp(),
        "has_book": os.path.exists(paths["book"]),
        "has_book_pdf": os.path.exists(paths["book_pdf"]),
        "has_slide": os.path.exists(paths["slides"]),
        "has_quiz": os.path.exists(paths["questions"]),
        "has_vid": os.path.exists(os.path.join(paths["videos"], "vid.mp4")),
    }

    if stats["has_quiz"]:
        try:
            with open(paths["questions"], "r", encoding="utf-8") as f:
                stats["total_questions"] = len(json.load(f))
        except Exception:
            stats["total_questions"] = 0

    if stats["has_slide"]:
        try:
            with open(paths["slides"], "r", encoding="utf-8") as f:
                stats["total_slides"] = len(json.load(f))
        except Exception:
            stats["total_slides"] = 0

    return stats


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
