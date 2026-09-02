"""Saved-document retries and ownership-protected processing-job status."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.processing_job import JobStatus, ProcessingJob
from app.models.user import User
from app.routers.generation import get_valid_course
from app.schemas.course import DocumentRetryResponse, JobResponse
from app.services import database
from app.services.document_processor import get_document_processor
from app.services.job_service import create_job

router = APIRouter(prefix="/api", tags=["documents"])


def _schedule_processing(
    background_tasks: BackgroundTasks,
    course_id: str,
    file_paths: list[str],
    job_id: str,
) -> None:
    """Queue the one document-processing task used by uploads and retries.

    The session factory is resolved when scheduling so test session overrides and the
    production factory both reach the worker; the task itself owns its session.
    """
    processor = get_document_processor()
    background_tasks.add_task(
        processor.process_course,
        course_id,
        file_paths,
        database.SessionLocal,
        job_id,
    )


@router.post(
    "/documents/{course_id}/retry",
    response_model=DocumentRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_document_processing(
    course_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retry indexing from the original saved uploads without accepting new files."""
    course = get_valid_course(course_id, current_user, db)
    if course.status not in {"failed", "paused_due_to_quota"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DOCUMENT_RETRY_NOT_ALLOWED", "message": "Tài liệu chưa ở trạng thái có thể thử lại."},
        )

    in_flight = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.course_id == course.id,
            ProcessingJob.job_type == "preprocess",
            ProcessingJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        )
        .first()
    )
    if in_flight:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "PROCESSING_IN_PROGRESS", "message": "Tài liệu đang được xử lý."},
        )

    file_paths = get_document_processor().list_saved_course_files(course.id)
    if not file_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SOURCE_FILE_MISSING", "message": "Không tìm thấy tệp nguồn đã tải lên."},
        )

    course.status = "processing"
    course.stage = "extracting"
    course.progress = 0
    course.embedding_status = "pending"
    course.error_message = None
    course.failure_stage = None
    course.error_code = None
    course.can_retry = False
    course.recommended_action = None
    course.technical_error = None
    db.commit()

    job = create_job(
        db,
        course_id=course.id,
        user_id=current_user.id,
        job_type="preprocess",
    )
    _schedule_processing(background_tasks, course.id, file_paths, job.id)

    return {
        "document_id": course.id,
        "status": "processing",
        "stage": "extracting",
        "progress": 0,
        "message": "Đang thử lại xử lý tài liệu từ tệp đã tải lên.",
        "job_id": job.id,
    }


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_processing_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a safe job envelope only to its owner or an administrator."""
    job = db.get(ProcessingJob, job_id)
    if not job or (job.user_id != current_user.id and current_user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tác vụ không tồn tại.")

    return {
        "id": job.id,
        "document_id": job.course_id,
        "user_id": job.user_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error_message,
        "error_code": job.error_code,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }
