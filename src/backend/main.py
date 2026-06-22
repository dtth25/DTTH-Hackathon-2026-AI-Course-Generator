"""
FastAPI server for RAG Learning Assistant - Restructured (v3.0)
Uses modular structure: core/, services/, vector_db/, memory/
"""
import os
import shutil
import json
import time
import uuid
import re
from typing import Optional, Any, Dict
from collections import OrderedDict
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.core.config import (
    UPLOAD_DIR,
    INDEX_DIR,
    QUESTIONS_DIR,
    get_course_path,
    sanitize_input,
    _timestamp,
    logger,
)
from backend.services.course_gen import CourseManager

# ─── Configuration ─────────────────────────────────────────────────────────────

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30

# ─── Global instances ──────────────────────────────────────────────────────────

course_manager: Optional[CourseManager] = None
rate_limit_store: OrderedDict[str, list] = OrderedDict()


# ─── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global course_manager
    print(f"[{_timestamp()}] Khởi tạo CourseManager (scan FAISS indices)...")
    course_manager = CourseManager()
    courses = course_manager.list_courses()
    print(f"[{_timestamp()}] Đã phục hồi {len(courses)} khóa học: {courses}")
    print(f"[{_timestamp()}] Sẵn sàng!")
    yield
    print(f"[{_timestamp()}] Dọn dẹp tài nguyên...")


app = FastAPI(
    title="RAG Learning Assistant API v3.0",
    version="3.0.0",
    description="Modular RAG Learning Assistant with NotebookLM-style features",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Middleware: Rate Limiting ─────────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple in-memory rate limiter."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    if client_ip not in rate_limit_store:
        rate_limit_store[client_ip] = []

    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip]
        if now - t < RATE_LIMIT_WINDOW
    ]

    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Vui lòng thử lại sau."}
        )

    rate_limit_store[client_ip].append(now)

    if len(rate_limit_store) > 1000:
        old_clients = [
            ip for ip, times in rate_limit_store.items()
            if now - max(times) > RATE_LIMIT_WINDOW * 2
        ]
        for ip in old_clients:
            del rate_limit_store[ip]

    response = await call_next(request)
    return response


# ─── Pydantic Models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    course_id: str
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v):
        if not v or not v.strip():
            raise ValueError("Câu hỏi không được để trống.")
        if len(v) > 2000:
            raise ValueError("Câu hỏi quá dài (tối đa 2000 ký tự).")
        return sanitize_input(v)


class ChatResponse(BaseModel):
    answer: str
    course_id: str


class GenerateQuestionsRequest(BaseModel):
    course_id: str
    topic: str
    quantity: int = Field(default=20, ge=1, le=30)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v):
        if not v or not v.strip():
            raise ValueError("Chủ đề không được để trống.")
        if len(v) > 200:
            raise ValueError("Chủ đề quá dài (tối đa 200 ký tự).")
        return sanitize_input(v)


class GenerateQuestionsResponse(BaseModel):
    course_id: str
    topic: str
    questions: list
    total_questions: int


class GenerateSlidesRequest(BaseModel):
    course_id: str
    topic: str
    num_slides: Optional[int] = Field(default=None, ge=3, le=30)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v):
        if not v or not v.strip():
            raise ValueError("Chủ đề không được để trống.")
        return sanitize_input(v)


class GenerateSlidesResponse(BaseModel):
    course_id: str
    topic: str
    latex_code: str
    filename: str


class GenerateSyllabusResponse(BaseModel):
    course_id: str
    syllabus: list


class UploadResponse(BaseModel):
    course_id: str
    filename: str
    status: str
    message: str


class StatusResponse(BaseModel):
    status: str
    course_id: Optional[str] = None
    courses: Optional[list] = None


class PodcastScriptResponse(BaseModel):
    course_id: str
    script: list
    estimated_duration: str


class StudyGuideResponse(BaseModel):
    course_id: str
    guide: str
    filename: str


class SummaryResponse(BaseModel):
    course_id: str
    summary: str
    filename: str


class FlashcardsResponse(BaseModel):
    course_id: str
    flashcards: list
    total: int


class TaskResponse(BaseModel):
    task_id: str
    status: str
    
class CustomPromptRequest(BaseModel):
    course_id: str
    prompt: str

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v):
        if not v or not v.strip():
            raise ValueError("Yêu cầu không được để trống.")
        if len(v) > 2000:
            raise ValueError("Yêu cầu quá dài (tối đa 2000 ký tự).")
        return sanitize_input(v)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def get_course(course_id: str):
    """Get a course or raise appropriate HTTP error."""
    if not course_manager:
        raise HTTPException(500, f"[{_timestamp()}] Hệ thống chưa sẵn sàng.")
    rag = course_manager.get_course(course_id)
    if not rag:
        raise HTTPException(404, f"[{_timestamp()}] Không tìm thấy khóa học '{course_id}'.")
    return rag


def _get_course_mgr() -> CourseManager:
    """Get or raise 503 if manager not initialized."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")
    return course_manager


def _validate_course_ready(mgr: CourseManager, course_id: str):
    """Validate course status before starting task."""
    status = mgr.get_course_status(course_id)
    if status not in ("ready", "pending"):
        raise HTTPException(
            400,
            f"Khóa học '{course_id}' chưa sẵn sàng (trạng thái: {status})."
        )


def run_background_task(task_id: str, course_id: str, task_type: str, **kwargs):
    """
    Generic background task runner.
    All async generation endpoints route here.
    Sử dụng ResourceGenerator cho các chức năng tạo resource.
    """
    task_dir = os.path.join("tasks", task_id)
    os.makedirs(task_dir, exist_ok=True)
    status_file = os.path.join(task_dir, "status.json")

    def write_status(status: str, result: Any = None, error: str = None):
        payload = {
            "status": status,
            "task_type": task_type,
            "course_id": course_id,
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
        if result is not None:
            payload["result"] = result
        if error:
            payload["error"] = str(error)
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    write_status("processing")

    try:
        if course_manager and course_manager.get_course_status(course_id) != "ready":
            raise ValueError(
                f"Khóa học '{course_id}' chưa sẵn sàng "
                f"(trạng thái: {course_manager.get_course_status(course_id)})."
            )

        rag = get_course(course_id)
        res_gen = rag.get_resource_generator()
        result = None

        def handle_podcast():
            script = res_gen.generate_podcast_script()
            print(f"[{_timestamp()}] Khởi động TTS cho podcast...")
            res_gen.generate_podcast_audio()
            return script

        task_handlers = {
            "syllabus": lambda: rag.generate_syllabus(),
            "questions": lambda: res_gen.generate_questions(kwargs["topic"], kwargs["quantity"]),
            "slides": lambda: {
                "latex_code": res_gen.generate_slides(kwargs["topic"], kwargs.get("num_slides"))[0],
                "filename": res_gen.generate_slides(kwargs["topic"], kwargs.get("num_slides"))[1],
            },
            "podcast": handle_podcast,
            "study_guide": lambda: res_gen.generate_study_guide(),
            "summary": lambda: res_gen.generate_summary(),
            "flashcards": lambda: res_gen.generate_flashcards(),
            "mindmap": lambda: rag.get_mindmap_generator().generate_mindmap(),
            "custom_prompt": lambda: rag.get_custom_processor().process(kwargs.get("prompt", "")),
        }

        if task_type not in task_handlers:
            raise ValueError(f"Unknown task type: {task_type}")

        result = task_handlers[task_type]()
        write_status("completed", result=result)
        print(f"[{_timestamp()}] Task {task_id} ({task_type}) completed successfully.")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        write_status("failed", error=error_msg)
        print(f"[{_timestamp()}] Task {task_id} ({task_type}) failed: {error_msg}")


def _build_course_info(course_id: str) -> dict:
    """Helper to build course info dict."""
    info = {"course_id": course_id}
    if course_manager:
        info["status"] = course_manager.get_course_status(course_id)
    else:
        info["status"] = "unknown"

    meta_path = get_course_path(course_id)["meta"]
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                info["pdf_path"] = meta.get("pdf_path", "")
                info["created_at"] = meta.get("created_at")
                if "error" in meta:
                    info["error"] = meta["error"]
        except Exception:
            pass
    return info


# ─── Health & Management ───────────────────────────────────────────────────────

@app.get("/health", response_model=StatusResponse)
async def health():
    """System health check."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")
    return StatusResponse(
        status="ok",
        course_id=None,
        courses=sorted(course_manager.list_courses()),
    )


@app.get("/courses", response_model=StatusResponse)
async def list_courses():
    """List all registered courses."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")
    return StatusResponse(
        status="ok",
        courses=sorted(course_manager.list_courses()),
    )


@app.get("/courses/all")
async def list_all_courses_with_meta():
    """List all courses with detailed metadata."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")

    courses = []
    seen_ids = set()

    if os.path.exists(INDEX_DIR):
        for name in os.listdir(INDEX_DIR):
            if name.startswith("course_") and os.path.isdir(os.path.join(INDEX_DIR, name)):
                cid = name.replace("course_", "", 1)
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                info = _build_course_info(cid)
                courses.append(info)

    for cid in course_manager.list_courses():
        if cid not in seen_ids:
            info = _build_course_info(cid)
            courses.append(info)

    return {"courses": courses, "total": len(courses)}


@app.delete("/courses/{course_id}", response_model=StatusResponse)
async def delete_course(course_id: str):
    """Delete a course and all its data."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")
    if not course_manager.contains(course_id):
        raise HTTPException(404, f"Không tìm thấy khóa học '{course_id}'.")
    course_manager.remove_course(course_id)
    return StatusResponse(status="deleted", course_id=course_id)


# ─── Upload ────────────────────────────────────────────────────────────────────

@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    """
    Yêu cầu 6.1: Upload tài liệu (PDF, DOCX, TXT) và xử lý background.
    """
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")

    if not file.filename:
        raise HTTPException(400, "Tên file không được để trống.")

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
    file_ext = os.path.splitext(file.filename.lower())[1]

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Định dạng file '{file_ext}' không hợp lệ. Hệ thống chỉ hỗ trợ: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "File bạn upload là file rỗng. Vui lòng kiểm tra lại.")

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            400,
            f"File quá lớn. Tối đa {MAX_UPLOAD_SIZE // (1024*1024)}MB."
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r"[^\w\-_\.]", "_", file.filename)
    file_path = os.path.join(UPLOAD_DIR, f"{int(time.time())}_{safe_name}")

    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, f"Lỗi trong quá trình lưu file: {str(e)}")

    course_id = uuid.uuid4().hex[:12]
    course_manager.register_course_id(course_id, file_path)

    import threading
    t = threading.Thread(
        target=course_manager.process_new_course,
        args=(course_id, file_path),
        daemon=True
    )
    t.start()

    return UploadResponse(
        course_id=course_id,
        filename=file.filename,
        status="processing",
        message=(
            f"File '{file.filename}' đã được nhận và đang được phân tích. "
            f"ID khóa học: {course_id}"
        ),
    )


@app.get("/course/{course_id}/status")
async def get_course_status(course_id: str):
    """Check processing status."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")

    status = course_manager.get_course_status(course_id)
    meta_path = get_course_path(course_id)["meta"]

    info = {"course_id": course_id, "status": status}

    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                info["pdf_path"] = meta.get("pdf_path", "")
                if meta.get("error"):
                    info["error"] = meta["error"]
        except Exception:
            pass

    return info


# ─── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Chat with course content."""
    rag = get_course(req.course_id)
    try:
        answer = rag.ask(req.question)
        return ChatResponse(answer=answer, course_id=req.course_id)
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi chat: {str(e)}")


# ─── Generation Endpoints (Sync) ───────────────────────────────────────────────

@app.post("/generate-podcast/{course_id}", response_model=PodcastScriptResponse)
async def generate_podcast_endpoint(course_id: str):
    """Generate podcast script."""
    rag = get_course(course_id)
    res_gen = rag.get_resource_generator()
    try:
        script = res_gen.generate_podcast_script()
        res_gen.generate_podcast_audio()
        total_words = sum(len(entry.get("text", "").split()) for entry in script)
        duration = max(3, total_words // 150)
        return PodcastScriptResponse(
            course_id=course_id,
            script=script,
            estimated_duration=f"{duration} phút",
        )
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi tạo podcast: {str(e)}")


@app.post("/generate-study-guide/{course_id}", response_model=StudyGuideResponse)
async def generate_study_guide_endpoint(course_id: str):
    """Generate comprehensive study guide."""
    rag = get_course(course_id)
    res_gen = rag.get_resource_generator()
    try:
        guide = res_gen.generate_study_guide()
        filename = f"study_guide_{course_id}.md"
        return StudyGuideResponse(
            course_id=course_id,
            guide=guide,
            filename=filename,
        )
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi tạo study guide: {str(e)}")


@app.post("/generate-summary/{course_id}", response_model=SummaryResponse)
async def generate_summary_endpoint(course_id: str):
    """
    Yêu cầu 6.4: Tạo bản tóm tắt (Ngắn, Chi tiết, Ý chính, Kết luận).
    """
    rag = get_course(course_id)
    res_gen = rag.get_resource_generator()
    try:
        summary = res_gen.generate_summary()
        return SummaryResponse(
            course_id=course_id,
            summary=summary,
            filename="summary.md"
        )
    except Exception as e:
        raise HTTPException(500, f"Lỗi tạo tóm tắt: {str(e)}")


@app.post("/generate-flashcards/{course_id}", response_model=FlashcardsResponse)
async def generate_flashcards_endpoint(course_id: str):
    """Generate flashcards for spaced repetition."""
    rag = get_course(course_id)
    res_gen = rag.get_resource_generator()
    try:
        cards = res_gen.generate_flashcards()
        return FlashcardsResponse(
            course_id=course_id,
            flashcards=cards,
            total=len(cards),
        )
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi tạo flashcards: {str(e)}")


@app.post("/generate-syllabus/{course_id}", response_model=GenerateSyllabusResponse)
async def generate_syllabus_endpoint(course_id: str):
    """Generate course syllabus."""
    rag = get_course(course_id)
    try:
        syllabus = rag.generate_syllabus()
        return GenerateSyllabusResponse(
            course_id=course_id,
            syllabus=syllabus,
        )
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi tạo syllabus: {str(e)}")


@app.post("/generate-questions", response_model=GenerateQuestionsResponse)
async def generate_questions(req: GenerateQuestionsRequest):
    """Generate MCQ questions."""
    rag = get_course(req.course_id)
    res_gen = rag.get_resource_generator()
    try:
        questions = res_gen.generate_questions(req.topic, req.quantity)
        q_path = get_course_path(req.course_id)["questions"]
        total = 0
        if os.path.exists(q_path):
            try:
                with open(q_path, "r", encoding="utf-8") as f:
                    total = len(json.load(f))
            except Exception:
                total = len(questions)
        return GenerateQuestionsResponse(
            course_id=req.course_id,
            topic=req.topic,
            questions=questions,
            total_questions=total,
        )
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi tạo câu hỏi: {str(e)}")


@app.post("/generate-slides", response_model=GenerateSlidesResponse)
async def generate_slides(req: GenerateSlidesRequest):
    """Generate LaTeX slides."""
    rag = get_course(req.course_id)
    res_gen = rag.get_resource_generator()
    try:
        latex_code, filename = res_gen.generate_slides(req.topic, req.num_slides)
        return GenerateSlidesResponse(
            course_id=req.course_id,
            topic=req.topic,
            latex_code=latex_code,
            filename=filename,
        )
    except Exception as e:
        raise HTTPException(500, f"[{_timestamp()}] Lỗi tạo slides: {str(e)}")
    
@app.post("/generate-mindmap/{course_id}")
async def generate_mindmap_sync(course_id: str):
    """
    Tạo bản đồ tư duy và trả về kết quả ngay lập tức (Sync).
    Sử dụng cho tài liệu ngắn hoặc khi muốn lấy data nhanh.
    """
    rag = get_course(course_id)
    try:
        # Gọi trực tiếp hàm tạo từ MindmapGenerator
        mindmap_data = rag.get_mindmap_generator().generate_mindmap()
        return mindmap_data
    except Exception as e:
        raise HTTPException(500, f"Lỗi tạo bản đồ tư duy: {str(e)}")
    
@app.post("/custom-prompt")
async def custom_prompt_sync(req: CustomPromptRequest):
    """
    Xử lý prompt tùy chỉnh (Sync).
    Phân loại prompt → retrieve context → inject format instruction → gọi LLM → trả kết quả + citations.
    
    Hỗ trợ 5 loại prompt: TABLE, LIST, EXPLAIN (default), JSON, CODE.
    """
    rag = get_course(req.course_id)
    processor = rag.get_custom_processor()
    
    try:
        result = processor.process(req.prompt)
        return {
            "course_id": req.course_id,
            "prompt": req.prompt,
            "prompt_type": result["prompt_type"],
            "result": result["result"],
            "citations": result["citations"],
        }
    except Exception as e:
        raise HTTPException(500, f"Lỗi xử lý prompt tùy chỉnh: {str(e)}")


# ─── Generation Endpoints (Async) ─────────────────────────────────────────────

@app.post("/custom-prompt-async/{course_id}", response_model=TaskResponse)
async def custom_prompt_async(
    course_id: str,
    prompt: str = "Phân tích nội dung tài liệu",
    background_tasks: BackgroundTasks = None,
):
    """Xử lý prompt tùy chỉnh trong background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)

    prompt = sanitize_input(prompt)
    if not prompt:
        prompt = "Phân tích nội dung tài liệu"
    if len(prompt) > 2000:
        raise HTTPException(400, "Yêu cầu quá dài (tối đa 2000 ký tự).")

    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(
        run_background_task,
        task_id, course_id, "custom_prompt",
        prompt=prompt,
    )
    return TaskResponse(task_id=task_id, status="processing")

@app.post("/generate-podcast-async/{course_id}", response_model=TaskResponse)
async def generate_podcast_async(course_id: str, background_tasks: BackgroundTasks):
    """Generate podcast in background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)
    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_background_task, task_id, course_id, "podcast")
    return TaskResponse(task_id=task_id, status="processing")


@app.post("/generate-study-guide-async/{course_id}", response_model=TaskResponse)
async def generate_study_guide_async(course_id: str, background_tasks: BackgroundTasks):
    """Generate study guide in background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)
    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_background_task, task_id, course_id, "study_guide")
    return TaskResponse(task_id=task_id, status="processing")


@app.post("/generate-summary-async/{course_id}", response_model=TaskResponse)
async def generate_summary_async(course_id: str, background_tasks: BackgroundTasks):
    """
    Yêu cầu 6.4: Tạo bản tóm tắt trong background (tránh Timeout).
    """
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)
    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_background_task, task_id, course_id, "summary")
    return TaskResponse(task_id=task_id, status="processing")


@app.post("/generate-flashcards-async/{course_id}", response_model=TaskResponse)
async def generate_flashcards_async(course_id: str, background_tasks: BackgroundTasks):
    """Generate flashcards in background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)
    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_background_task, task_id, course_id, "flashcards")
    return TaskResponse(task_id=task_id, status="processing")


@app.post("/generate-syllabus-async/{course_id}", response_model=TaskResponse)
async def generate_syllabus_async(course_id: str, background_tasks: BackgroundTasks):
    """Generate syllabus in background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)
    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_background_task, task_id, course_id, "syllabus")
    return TaskResponse(task_id=task_id, status="processing")


@app.post("/generate-questions-async/{course_id}", response_model=TaskResponse)
async def generate_questions_async(
    course_id: str,
    topic: str = "Kiến thức tổng quát",
    quantity: int = 5,
    background_tasks: BackgroundTasks = None,  # type: ignore[arg-type]
):
    """Generate questions in background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)

    topic = sanitize_input(topic)
    if not topic:
        topic = "Kiến thức tổng quát"
    if quantity < 1 or quantity > 20:
        raise HTTPException(400, "Số lượng câu hỏi phải từ 1 đến 20.")

    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(
        run_background_task,
        task_id, course_id, "questions",
        topic=topic,
        quantity=quantity,
    )
    return TaskResponse(task_id=task_id, status="processing")


@app.post("/generate-slides-async/{course_id}", response_model=TaskResponse)
async def generate_slides_async(
    course_id: str,
    topic: str = "Kiến thức tổng quát",
    num_slides: Optional[int] = None,
    background_tasks: BackgroundTasks = None,  # type: ignore[arg-type]
):
    """Generate slides in background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)

    topic = sanitize_input(topic)
    if not topic:
        topic = "Kiến thức tổng quát"

    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(
        run_background_task,
        task_id, course_id, "slides",
        topic=topic,
        num_slides=num_slides,
    )
    return TaskResponse(task_id=task_id, status="processing")

@app.post("/generate-mindmap-async/{course_id}", response_model=TaskResponse)
async def generate_mindmap_async(course_id: str, background_tasks: BackgroundTasks):
    """Tạo bản đồ tư duy trong background."""
    course_mgr = _get_course_mgr()
    _validate_course_ready(course_mgr, course_id)
    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_background_task, task_id, course_id, "mindmap")
    return TaskResponse(task_id=task_id, status="processing")

# ─── Task Polling ──────────────────────────────────────────────────────────────

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll background task status."""
    task_dir = os.path.join("tasks", task_id)
    status_file = os.path.join(task_dir, "status.json")
    if not os.path.exists(status_file):
        raise HTTPException(404, f"Không tìm thấy task '{task_id}'.")
    with open(status_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("status") == "processing" and data.get("created_at"):
        try:
            created = datetime.strptime(data["created_at"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - created).total_seconds()
            data["elapsed_seconds"] = int(elapsed)
        except Exception:
            pass
    return data


# ─── Get Saved Content ─────────────────────────────────────────────────────────

@app.get("/course/{course_id}/questions")
async def get_saved_questions(course_id: str):
    """Get all saved questions."""
    q_path = get_course_path(course_id)["questions"]
    if not os.path.exists(q_path):
        return {"course_id": course_id, "questions": [], "total": 0}
    with open(q_path, "r", encoding="utf-8") as f:
        questions = json.load(f)
    return {"course_id": course_id, "questions": questions, "total": len(questions)}


@app.get("/course/{course_id}/syllabus")
async def get_saved_syllabus(course_id: str):
    """Get saved syllabus."""
    s_path = get_course_path(course_id)["syllabus"]
    if not os.path.exists(s_path):
        return {"course_id": course_id, "syllabus": None}
    with open(s_path, "r", encoding="utf-8") as f:
        syllabus = json.load(f)
    return {"course_id": course_id, "syllabus": syllabus}


@app.get("/course/{course_id}/slides")
async def get_saved_slides(course_id: str):
    """List all saved slides."""
    slides_dir = os.path.join(QUESTIONS_DIR, f"course_{course_id}_slides")
    if not os.path.exists(slides_dir):
        return {"course_id": course_id, "slides": [], "total": 0}

    slides = []
    for fname in sorted(os.listdir(slides_dir)):
        if fname.endswith(".tex"):
            fpath = os.path.join(slides_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            slides.append({
                "filename": fname,
                "preview": content[:500] if len(content) > 500 else content,
                "size": len(content),
            })

    return {"course_id": course_id, "slides": slides, "total": len(slides)}


@app.get("/course/{course_id}/audio")
async def get_saved_audio_script(course_id: str):
    """Get saved podcast script."""
    audio_dir = get_course_path(course_id)["audio"]
    script_path = os.path.join(audio_dir, "podcast_script.json")
    if not os.path.exists(script_path):
        raise HTTPException(404, "Chưa có podcast script.")
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)
    return {"course_id": course_id, "script": script}


@app.get("/course/{course_id}/study-guide")
async def get_saved_study_guide(course_id: str):
    """Get saved study guide."""
    guide_path = os.path.join(get_course_path(course_id)["guides"], "study_guide.md")
    if not os.path.exists(guide_path):
        raise HTTPException(404, "Chưa có study guide.")
    with open(guide_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"course_id": course_id, "guide": content, "filename": "study_guide.md"}


@app.get("/course/{course_id}/summary")
async def get_saved_summary(course_id: str):
    """Lấy bản tóm tắt đã lưu."""
    summary_path = os.path.join(get_course_path(course_id)["guides"], "summary.md")
    if not os.path.exists(summary_path):
        raise HTTPException(
            404,
            "Chưa có bản tóm tắt cho khóa học này. Hãy gọi POST /generate-summary trước."
        )
    with open(summary_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"course_id": course_id, "summary": content}


@app.get("/course/{course_id}/flashcards")
async def get_saved_flashcards(course_id: str):
    """Get saved flashcards."""
    cards_path = get_course_path(course_id)["flashcards"]
    if not os.path.exists(cards_path):
        return {"course_id": course_id, "flashcards": [], "total": 0}
    with open(cards_path, "r", encoding="utf-8") as f:
        cards = json.load(f)
    return {"course_id": course_id, "flashcards": cards, "total": len(cards)}

@app.get("/course/{course_id}/mindmap")
async def get_saved_mindmap(course_id: str):
    """Lấy dữ liệu bản đồ tư duy từ folder mindmaps."""
    # Lấy đường dẫn chuẩn từ config
    paths = get_course_path(course_id)
    path = os.path.join(paths["mindmaps"], "mindmap.json")
    
    if not os.path.exists(path):
        raise HTTPException(404, "Chưa có bản đồ tư duy cho khóa học này.")
        
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/course/{course_id}/files")
async def get_course_files(course_id: str):
    """List all generated files for a course."""
    paths = get_course_path(course_id)
    files = {}

    if os.path.exists(paths["syllabus"]):
        files["syllabus"] = paths["syllabus"]
    if os.path.exists(paths["questions"]):
        files["questions"] = paths["questions"]
    if os.path.exists(paths["flashcards"]):
        files["flashcards"] = paths["flashcards"]

    slides_dir = os.path.join(QUESTIONS_DIR, f"course_{course_id}_slides")
    if os.path.exists(slides_dir):
        files["slides"] = sorted(os.listdir(slides_dir))

    guides_dir = paths["guides"]
    if os.path.exists(guides_dir):
        files["guides"] = sorted(os.listdir(guides_dir))

    audio_dir = paths["audio"]
    if os.path.exists(audio_dir):
        files["audio"] = sorted(os.listdir(audio_dir))

    return {"course_id": course_id, "files": files}


@app.get("/course/{course_id}/stats")
async def get_course_stats(course_id: str):
    """Get detailed course statistics."""
    if not course_manager:
        raise HTTPException(503, "Hệ thống chưa khởi tạo.")

    rag = get_course(course_id)
    stats = {
        "course_id": course_id,
        "status": course_manager.get_course_status(course_id),
        "generated_at": _timestamp(),
    }

    q_path = get_course_path(course_id)["questions"]
    if os.path.exists(q_path):
        try:
            with open(q_path, "r", encoding="utf-8") as f:
                stats["total_questions"] = len(json.load(f))
        except Exception:
            stats["total_questions"] = 0

    cards_path = get_course_path(course_id)["flashcards"]
    if os.path.exists(cards_path):
        try:
            with open(cards_path, "r", encoding="utf-8") as f:
                stats["total_flashcards"] = len(json.load(f))
        except Exception:
            stats["total_flashcards"] = 0

    slides_dir = os.path.join(QUESTIONS_DIR, f"course_{course_id}_slides")
    if os.path.exists(slides_dir):
        stats["total_slides"] = len([
            f for f in os.listdir(slides_dir) if f.endswith(".tex")
        ])

    guide_path = os.path.join(get_course_path(course_id)["guides"], "study_guide.md")
    stats["has_study_guide"] = os.path.exists(guide_path)

    script_path = os.path.join(get_course_path(course_id)["audio"], "podcast_script.json")
    stats["has_podcast"] = os.path.exists(script_path)

    return stats


# ─── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info",
    )