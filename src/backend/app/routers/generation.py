"""Generation Service router for HackaGen."""

import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.jobs.admission import enforce_job_admission
from app.models.course import Course
from app.models.user import User
from app.routers.jobs import dispatch_persisted_job
from app.schemas.generation import (
    BookGenerateRequest,
    GenerateRequest,
    GenerateResponse,
    QuizGenerateRequest,
    SlideGenerateRequest,
    StudyPackResponse,
    VidGenerateRequest,
)
from app.services.generator import Generator
from app.services.job_service import create_job
from app.services.llm import LLMService
from app.services.public_errors import public_error, sanitize_public_payload
from app.services.vector_store import get_vector_store
from app.services.versioning import (
    GenerationInFlightError,
    VersionCapReachedError,
    artifact_file_path,
    artifact_directory_path,
)

router = APIRouter(prefix="/api/courses", tags=["generation"])
router_single = APIRouter(prefix="/api/course", tags=["generation"])
router_generate = APIRouter(prefix="/api", tags=["generation"])
router_docs = APIRouter(tags=["generation"])

_generator_instance = None

ARTIFACT_FAILURE_CODES = {
    "book": "BOOK_GENERATION_FAILED",
    "slides": "SLIDE_GENERATION_FAILED",
    "quiz": "QUIZ_GENERATION_FAILED",
    "vid": "VIDEO_GENERATION_FAILED",
}


def public_artifact_error(info: Dict[str, Any], artifact: str) -> tuple[Optional[str], Optional[str]]:
    """Return only a closed code and fixed copy for failed artifact envelopes."""
    if info.get("status") != "error":
        return None, None
    code, message = public_error(info.get("error_code"), ARTIFACT_FAILURE_CODES[artifact])
    return code, message


def get_generator() -> Generator:
    """Singleton helper wiring per-feature OpenRouter models.

    Book/Vid use the default (Pro, long-form quality); Slide/Quiz default to the cheaper/
    faster Flash model — see OPENROUTER_{BOOK,SLIDE,QUIZ,VID}_MODEL in config.py. Each
    override gets its own LLMService (own OpenAI client), features left blank share the
    single default instance rather than each opening a redundant client.
    """
    global _generator_instance
    if _generator_instance is None:
        vs = get_vector_store()
        default_llm = LLMService()
        overrides = {
            "book": settings.OPENROUTER_BOOK_MODEL,
            "slides": settings.OPENROUTER_SLIDE_MODEL,
            "quiz": settings.OPENROUTER_QUIZ_MODEL,
            "vid": settings.OPENROUTER_VID_MODEL,
        }
        feature_llms = {
            feature: LLMService(model=model) if model else default_llm
            for feature, model in overrides.items()
        }
        _generator_instance = Generator(vs, default_llm, feature_llms)
    return _generator_instance


def get_valid_course(course_id: str, current_user: User, db: Session) -> Course:
    """Validate course existence and ownership."""
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.is_deleted == False)  # noqa: E712
        .first()
    )
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khóa học không tồn tại."
        )

    if course.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khóa học không tồn tại."
        )

    return course


def resolve_and_validate_course(
    req: Optional[GenerateRequest],
    query_course_id: Optional[str],
    current_user: User,
    db: Session,
) -> Course:
    """Resolve course_id from JSON body or query param and validate ownership."""
    cid = (req and req.course_id) or query_course_id
    if not cid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thiếu course_id trong yêu cầu.",
        )
    return get_valid_course(cid, current_user, db)


def version_fields(generator: Generator, course_id: str, artifact: str, requested: Optional[str]) -> tuple[Optional[str], Optional[str], list[Dict[str, Any]]]:
    active, versions = generator.artifact_versions(course_id, artifact)
    fallback = versions[-1]["version_id"] if versions else None
    return requested or active or fallback, active, versions


def versioned_file_path(generator: Generator, course_id: str, artifact: str, filename: str, requested: Optional[str]) -> Optional[str]:
    active, _ = generator.artifact_versions(course_id, artifact)
    version_id = requested or active
    return artifact_file_path(settings.UPLOAD_DIR, course_id, artifact, version_id, filename) if version_id else None


def prepare_version_or_raise(generator: Generator, course_id: str, artifact: str, options: Dict[str, Any], **kwargs) -> str:
    try:
        return generator.prepare_artifact_version(course_id, artifact, options, **kwargs)
    except GenerationInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "generation_in_flight"}) from exc
    except VersionCapReachedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "version_cap_reached", "versions": exc.versions}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_GENERATION_REQUEST",
                "message": "Yêu cầu tạo học liệu không hợp lệ.",
            },
        ) from exc


def reserve_version_or_raise(generator: Generator, course_id: str, artifact: str, options: Dict[str, Any], **kwargs) -> str:
    return prepare_version_or_raise(generator, course_id, artifact, options, **kwargs)


def enqueue_generation_job(
    *,
    background_tasks: BackgroundTasks,
    db: Session,
    course: Course,
    generator: Generator,
    job_type: str,
    artifact: str,
    options: Dict[str, Any],
    payload_options: Dict[str, Any],
    **reservation_options: Any,
):
    """Admit, reserve, persist, then dispatch one durable artifact job."""
    enforce_job_admission(db, course.user_id)
    try:
        version_id = reserve_version_or_raise(
            generator,
            course.id,
            artifact,
            options,
            db_session=db,
            **reservation_options,
        )
        job = create_job(
            db,
            course_id=course.id,
            user_id=course.user_id,
            job_type=job_type,
            payload_json={
                "course_id": course.id,
                "artifact": artifact,
                "version_id": version_id,
                **payload_options,
            },
            queue_name="video" if job_type == "video" else "generation",
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    dispatch_persisted_job(background_tasks, db, job)
    return job, version_id


# =====================================================================
# 1. Study Pack Endpoint
# =====================================================================


@router_single.get("/{course_id}/study-pack", response_model=StudyPackResponse)
@router.get("/{course_id}/study-pack", response_model=StudyPackResponse)
def get_study_pack(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Return actual study pack data for the specified course."""
    get_valid_course(course_id, current_user, db)
    generator = get_generator()
    return generator.get_study_pack(course_id)


# =====================================================================
# 2. Generate Endpoints (trigger background AI generation)
# =====================================================================


@router_generate.post("/generate-book", response_model=GenerateResponse)
def generate_book(
    background_tasks: BackgroundTasks,
    req: Optional[BookGenerateRequest] = None,
    course_id: Optional[str] = Query(None),
    user_prompt: Optional[str] = Query(None),
    detail_level: Optional[str] = Query(None),
    retry_version_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Trigger background generation for Book artifact."""
    course = resolve_and_validate_course(req, course_id, current_user, db)
    prompt = (req and req.user_prompt) or user_prompt or ""
    detail = (req and req.detail_level) or detail_level or "Tiêu chuẩn"
    generator = get_generator()
    job, version_id = enqueue_generation_job(
        background_tasks=background_tasks,
        db=db,
        course=course,
        generator=generator,
        job_type="book",
        artifact="book",
        options={"detail_level": detail},
        payload_options={"detail_level": detail, "user_prompt": prompt},
        user_prompt=prompt,
        retry_version_id=(req and req.retry_version_id) or retry_version_id,
    )
    return GenerateResponse(course_id=course.id, version_id=version_id, job_id=job.id)


@router_generate.post("/generate-slide", response_model=GenerateResponse)
def generate_slide(
    background_tasks: BackgroundTasks,
    req: Optional[SlideGenerateRequest] = None,
    course_id: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    focus_prompt: Optional[str] = Query(None),
    retry_version_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Trigger background generation for Slide artifact."""
    course = resolve_and_validate_course(req, course_id, current_user, db)
    t = (req and req.topic) or topic
    slide_mode = (req and req.mode) or mode or "lesson"
    n = {"summary": 8, "lesson": 15, "deep_dive": 22}.get(slide_mode, 15)
    focus = (req and req.focus_prompt) or focus_prompt or ""
    generator = get_generator()
    job, version_id = enqueue_generation_job(
        background_tasks=background_tasks,
        db=db,
        course=course,
        generator=generator,
        job_type="slides",
        artifact="slides",
        options={"mode": slide_mode, "num_slides": n, "focus_prompt": focus},
        payload_options={"topic": t, "num_slides": n, "focus_prompt": focus},
        topic=t,
        retry_version_id=(req and req.retry_version_id) or retry_version_id,
    )
    return GenerateResponse(course_id=course.id, version_id=version_id, job_id=job.id)


@router_generate.post("/generate-quiz", response_model=GenerateResponse)
def generate_quiz(
    background_tasks: BackgroundTasks,
    req: Optional[QuizGenerateRequest] = None,
    course_id: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    quantity: Optional[int] = Query(None),
    difficulty: Optional[str] = Query(None),
    retry_version_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Trigger background generation for Quiz artifact."""
    course = resolve_and_validate_course(req, course_id, current_user, db)
    t = (req and req.topic) or topic
    q = (req and req.quantity) or quantity or 5
    d = (req and req.difficulty) or difficulty or "medium"
    generator = get_generator()
    job, version_id = enqueue_generation_job(
        background_tasks=background_tasks,
        db=db,
        course=course,
        generator=generator,
        job_type="quiz",
        artifact="quiz",
        options={"quantity": q, "difficulty": d},
        payload_options={"topic": t, "quantity": q, "difficulty": d},
        topic=t,
        retry_version_id=(req and req.retry_version_id) or retry_version_id,
    )
    return GenerateResponse(course_id=course.id, version_id=version_id, job_id=job.id)


@router_generate.post("/generate-vid", response_model=GenerateResponse)
def generate_vid(
    background_tasks: BackgroundTasks,
    req: Optional[VidGenerateRequest] = None,
    course_id: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    voice: Optional[str] = Query(None),
    user_prompt: Optional[str] = Query(None),
    retry_version_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Trigger background generation for the narrated Video artifact."""
    course = resolve_and_validate_course(req, course_id, current_user, db)
    t = (req and req.topic) or topic
    fmt = (req and req.format) or format or "standard"
    v = (req and req.voice) or voice or "female"
    up = (req and req.user_prompt) or user_prompt or ""
    generator = get_generator()
    job, version_id = enqueue_generation_job(
        background_tasks=background_tasks,
        db=db,
        course=course,
        generator=generator,
        job_type="video",
        artifact="vid",
        options={"format": fmt, "voice": v},
        payload_options={
            "topic": t,
            "format": fmt,
            "voice": v,
            "user_prompt": up,
        },
        topic=t,
        user_prompt=up,
        retry_version_id=(req and req.retry_version_id) or retry_version_id,
    )
    return GenerateResponse(
        course_id=course.id,
        estimated_time="3-5 minutes",
        version_id=version_id,
        job_id=job.id,
    )


# =====================================================================
# 3. Artifact Retrieval Endpoints
# =====================================================================


@router_single.patch("/{course_id}/artifacts/{artifact}/versions/{version_id}")
def rename_artifact_version(
    course_id: str,
    artifact: str,
    version_id: str,
    payload: Dict[str, str],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    get_valid_course(course_id, current_user, db)
    try:
        return get_generator().rename_artifact_version(course_id, artifact, version_id, payload.get("label", ""))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_ARTIFACT_VERSION_NAME",
                "message": "Tên phiên bản học liệu không hợp lệ.",
            },
        ) from exc


@router_single.delete("/{course_id}/artifacts/{artifact}/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artifact_version(
    course_id: str,
    artifact: str,
    version_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    get_valid_course(course_id, current_user, db)
    try:
        get_generator().delete_artifact_version(course_id, artifact, version_id)
    except GenerationInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "generation_in_flight"}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "ARTIFACT_VERSION_NOT_FOUND",
                "message": "Không tìm thấy phiên bản học liệu.",
            },
        ) from exc


@router_single.get("/{course_id}/book", response_model=Any)
@router.get("/{course_id}/book", response_model=Any)
def get_book(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve Book artifact status envelope: {status, error, progress, data}.

    status is one of "empty" | "processing" | "ready" | "error". `data` never leaks
    raw source_chunk_ids (grounding metadata), matching the no-raw-metadata invariant.
    """
    get_valid_course(course_id, current_user, db)
    generator = get_generator()
    version_id, active_version, versions = version_fields(generator, course_id, "book", version)
    data = sanitize_public_payload(generator._load_artifact_json(course_id, "book.json", artifact_directory_path(settings.UPLOAD_DIR, course_id, "book", version_id))) if version_id else None
    info = generator.get_artifact_status(course_id, "book", version_id)
    error_code, error_message = public_artifact_error(info, "book")
    status_val = info.get("status") or ("ready" if data else "empty")
    if status_val == "ready" and data is None:
        status_val = "empty"
    return {
        "status": status_val,
        "error": error_message,
        "error_code": error_code,
        "progress": info.get("progress"),
        "data": data,
        "version_id": version_id,
        "active_version": active_version,
        "versions": versions,
    }


@router_single.get("/{course_id}/slide", response_model=Any)
@router.get("/{course_id}/slide", response_model=Any)
def get_slide(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve Slide artifact status envelope: {status, error, progress, data}.

    status is one of "empty" | "processing" | "ready" | "error". `data` never leaks
    raw source_chunk_ids (grounding metadata), matching the no-raw-metadata invariant.
    """
    get_valid_course(course_id, current_user, db)
    generator = get_generator()
    version_id, active_version, versions = version_fields(generator, course_id, "slides", version)
    data = sanitize_public_payload(generator._load_artifact_json(course_id, "slides.json", artifact_directory_path(settings.UPLOAD_DIR, course_id, "slides", version_id))) if version_id else None
    info = generator.get_artifact_status(course_id, "slides", version_id)
    error_code, error_message = public_artifact_error(info, "slides")
    status_val = info.get("status") or ("ready" if data else "empty")
    if status_val == "ready" and data is None:
        status_val = "empty"
    return {
        "status": status_val,
        "error": error_message,
        "error_code": error_code,
        "progress": info.get("progress"),
        "data": data,
        "version_id": version_id,
        "active_version": active_version,
        "versions": versions,
    }


@router_single.get("/{course_id}/quiz", response_model=Any)
@router.get("/{course_id}/quiz", response_model=Any)
def get_quiz(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve Quiz artifact status envelope: {status, error, progress, data}.

    status is one of "empty" | "processing" | "ready" | "error". `data` is the list of
    questions (or null) and never leaks raw source_chunk_ids (grounding metadata).
    """
    get_valid_course(course_id, current_user, db)
    generator = get_generator()
    version_id, active_version, versions = version_fields(generator, course_id, "quiz", version)
    raw = sanitize_public_payload(generator._load_artifact_json(course_id, "quiz.json", artifact_directory_path(settings.UPLOAD_DIR, course_id, "quiz", version_id))) if version_id else None
    questions = raw.get("questions", []) if raw else None
    info = generator.get_artifact_status(course_id, "quiz", version_id)
    error_code, error_message = public_artifact_error(info, "quiz")
    status_val = info.get("status") or ("ready" if questions else "empty")
    if status_val == "ready" and not questions:
        status_val = "empty"
    return {
        "status": status_val,
        "error": error_message,
        "error_code": error_code,
        "progress": info.get("progress"),
        "data": questions,
        "version_id": version_id,
        "active_version": active_version,
        "versions": versions,
    }


@router_single.get("/{course_id}/vid", response_model=Any)
@router.get("/{course_id}/vid", response_model=Any)
def get_vid(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve Video artifact status envelope: {status, error, progress, data}.

    status is one of "empty" | "processing" | "ready" | "error". `data` never leaks
    raw source_chunk_ids (grounding metadata), matching the no-raw-metadata invariant.
    """
    get_valid_course(course_id, current_user, db)
    generator = get_generator()
    version_id, active_version, versions = version_fields(generator, course_id, "vid", version)
    data = sanitize_public_payload(generator._load_artifact_json(course_id, "vid.json", artifact_directory_path(settings.UPLOAD_DIR, course_id, "vid", version_id))) if version_id else None
    info = generator.get_artifact_status(course_id, "vid", version_id)
    error_code, error_message = public_artifact_error(info, "vid")
    status_val = info.get("status") or ("ready" if data else "empty")
    if status_val == "ready" and data is None:
        status_val = "empty"
    return {
        "status": status_val,
        "error": error_message,
        "error_code": error_code,
        "progress": info.get("progress"),
        "data": data,
        "version_id": version_id,
        "active_version": active_version,
        "versions": versions,
    }


# =====================================================================
# 4. Download Endpoints (serve generated files or 404)
# =====================================================================


@router_single.get("/{course_id}/book.pdf")
@router.get("/{course_id}/book.pdf")
def download_book_pdf(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Download Book Study Guide PDF."""
    get_valid_course(course_id, current_user, db)
    file_path = versioned_file_path(get_generator(), course_id, "book", "book.pdf", version)
    if file_path and os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="application/pdf",
            filename=f"study_guide_{course_id}.pdf",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Chưa có file PDF cho tài liệu này.",
    )


@router_single.get("/{course_id}/slide.pptx")
@router.get("/{course_id}/slide.pptx")
def download_slide_pptx(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Download Slide PPTX presentation."""
    get_valid_course(course_id, current_user, db)
    file_path = versioned_file_path(get_generator(), course_id, "slides", "slide.pptx", version)
    if file_path and os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"slides_{course_id}.pptx",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Chưa có file bài giảng PPTX cho tài liệu này.",
    )


@router_single.get("/{course_id}/slide.pdf")
@router.get("/{course_id}/slide.pdf")
def download_slide_pdf(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Download Slide presentation as a 16:9 PDF."""
    get_valid_course(course_id, current_user, db)
    file_path = versioned_file_path(get_generator(), course_id, "slides", "slide.pdf", version)
    if file_path and os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="application/pdf",
            filename=f"slides_{course_id}.pdf",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Chưa có file bài giảng PDF cho tài liệu này.",
    )


@router_single.get("/{course_id}/slide-images/{slide_num}")
@router.get("/{course_id}/slide-images/{slide_num}")
def get_slide_image(
    course_id: str,
    slide_num: int,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Get slide image by slide number."""
    get_valid_course(course_id, current_user, db)
    file_path = versioned_file_path(get_generator(), course_id, "slides", f"slide_{slide_num}.png", version)
    if file_path and os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/png")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy ảnh slide tương ứng.",
    )


@router_single.get("/{course_id}/quiz-key.pdf")
@router.get("/{course_id}/quiz-key.pdf")
def download_quiz_key_pdf(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Download Quiz Answer Key PDF."""
    get_valid_course(course_id, current_user, db)
    file_path = versioned_file_path(get_generator(), course_id, "quiz", "quiz-key.pdf", version)
    if file_path and os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="application/pdf",
            filename=f"quiz_key_{course_id}.pdf",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Chưa có file đáp án trắc nghiệm PDF cho tài liệu này.",
    )


@router_single.get("/{course_id}/vid.mp4")
@router.get("/{course_id}/vid.mp4")
def download_vid_mp4(
    course_id: str,
    version: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Download/stream the narrated Video MP4 (FileResponse supports Range for <video> seeking)."""
    get_valid_course(course_id, current_user, db)
    file_path = versioned_file_path(get_generator(), course_id, "vid", "vid.mp4", version)
    if file_path and os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="video/mp4",
            filename=f"video_{course_id}.mp4",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Chưa có file video cho tài liệu này.",
    )


@router_docs.get("/documents/{document_id}/sources")
@router_docs.get("/api/documents/{document_id}/sources")
def get_sources(
    document_id: str,
    ids: Optional[str] = Query(None),
    developer: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Stable source-grounding endpoint for UI panels."""
    get_valid_course(document_id, current_user, db)
    provider = get_generator()._get_embedding_provider(document_id)
    vs = get_vector_store()
    stats = vs.get_course_stats(document_id, provider=provider)
    total_chunks = stats.get("chunk_count", 0)

    target_ids = [cid.strip() for cid in ids.split(",") if cid.strip()] if ids else None
    docs = vs.get_course_chunks(document_id, target_ids, provider=provider)

    sources = []
    for doc in docs:
        page_val = doc.metadata.get("page", 1)
        try:
            page_num = int(page_val)
        except (ValueError, TypeError):
            page_num = 1

        excerpt = doc.content
        if len(excerpt) > 300:
            excerpt = excerpt[:300] + "..."

        item = {
            "page": page_num,
            "excerpt": excerpt,
        }
        if developer and current_user.role == "admin":
            item["source_chunk_id"] = doc.metadata.get("chunk_id", "")
        sources.append(item)

    return {
        "document_id": document_id,
        "total_source_chunks": total_chunks,
        "matched_source_chunks": len(sources),
        "sources": sources,
    }




