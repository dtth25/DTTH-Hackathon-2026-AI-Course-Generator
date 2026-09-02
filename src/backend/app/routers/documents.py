"""Saved-document retries and ownership-protected processing-job status."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import exists, update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.course import Course
from app.models.processing_job import JobStatus, ProcessingJob
from app.models.user import User
from app.routers.generation import get_valid_course
from app.schemas.course import DocumentRetryResponse, JobResponse
from app.services import database
from app.services.document_processor import get_document_processor
from app.services.job_service import create_job
from app.services.public_errors import public_error

router = APIRouter(prefix="/api", tags=["documents"])

SCHEDULING_FAILURE_CODE = "DOCUMENT_SCHEDULING_FAILED"
SCHEDULING_FAILURE_MESSAGE = "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại."


def mark_inline_scheduling_failure(db: Session, course_id: str, job_id: str) -> None:
    """Atomically fail an inline job whose BackgroundTasks registration did not happen."""
    now = datetime.utcnow()
    course = db.get(Course, course_id)
    job = db.get(ProcessingJob, job_id)
    if course is None or job is None:
        raise RuntimeError("Scheduled document state disappeared before failure recovery.")
    course.status = "failed"
    course.stage = "failed"
    course.progress = 0
    course.embedding_status = "failed"
    course.error_message = SCHEDULING_FAILURE_MESSAGE
    course.failure_stage = "scheduling_failed"
    course.error_code = SCHEDULING_FAILURE_CODE
    course.can_retry = True
    course.recommended_action = "retry_later"
    course.technical_error = "Inline BackgroundTasks registration failed."
    job.status = JobStatus.FAILED.value
    job.error_code = SCHEDULING_FAILURE_CODE
    job.error_message = SCHEDULING_FAILURE_MESSAGE
    job.message = SCHEDULING_FAILURE_MESSAGE
    job.completed_at = now
    job.updated_at = now
    db.commit()


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
    file_paths = get_document_processor().list_saved_course_files(course.id)
    if not file_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SOURCE_FILE_MISSING", "message": "Không tìm thấy tệp nguồn đã tải lên."},
        )

    active_preprocess = exists().where(
        ProcessingJob.course_id == course.id,
        ProcessingJob.job_type == "preprocess",
        ProcessingJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
    )
    try:
        transitioned = db.execute(
            update(Course)
            .where(
                Course.id == course.id,
                Course.is_deleted == False,  # noqa: E712
                Course.status.in_(["failed", "paused_due_to_quota"]),
                ~active_preprocess,
            )
            .values(
                status="processing",
                stage="extracting",
                progress=0,
                embedding_status="pending",
                error_message=None,
                failure_stage=None,
                error_code=None,
                can_retry=False,
                recommended_action=None,
                technical_error=None,
            )
        )
        if transitioned.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "DOCUMENT_RETRY_NOT_ALLOWED", "message": "Tài liệu chưa ở trạng thái có thể thử lại."},
            )
        job = create_job(
            db,
            course_id=course.id,
            user_id=course.user_id,
            job_type="preprocess",
            commit=False,
        )
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DOCUMENT_RETRY_UNAVAILABLE", "message": "Không thể bắt đầu thử lại tài liệu."},
        ) from exc

    try:
        _schedule_processing(background_tasks, course.id, file_paths, job.id)
    except Exception as exc:
        try:
            mark_inline_scheduling_failure(db, course.id, job.id)
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "DOCUMENT_RETRY_UNAVAILABLE", "message": "Không thể bắt đầu thử lại tài liệu."},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": SCHEDULING_FAILURE_CODE, "message": SCHEDULING_FAILURE_MESSAGE},
        ) from exc

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

    public_code, public_message = public_error(
        job.error_code, "DOCUMENT_PROCESSING_FAILED"
    )
    failed = job.status == JobStatus.FAILED.value

    return {
        "id": job.id,
        "document_id": job.course_id,
        "user_id": job.user_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "message": public_message if failed else job.message,
        "error": public_message if failed else None,
        "error_code": public_code if failed else None,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }
