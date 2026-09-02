"""Courses router for CRUD operations and status tracking."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.routers.generation import get_valid_course
from app.schemas.course import (
    CourseCreate,
    CourseListItem,
    CourseListResponse,
    CourseRenameRequest,
    CourseResponse,
    CourseStatusResponse,
)
from app.services.public_errors import public_error

router = APIRouter(prefix="/api/courses", tags=["courses"])
# Map /api/course per frontend expectations
router_single = APIRouter(prefix="/api/course", tags=["courses"])

MAX_COURSES_PER_USER = 10


def _enforce_course_limit(db: Session, user_id: str) -> None:
    count = (
        db.query(Course)
        .filter(Course.user_id == user_id, Course.is_deleted == False)  # noqa: E712
        .count()
    )
    if count >= MAX_COURSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bạn đã đạt giới hạn tối đa {MAX_COURSES_PER_USER} khóa học. Vui lòng xóa bớt khóa học cũ để tạo mới.",
        )


@router.get("/all", response_model=CourseListResponse)
def get_user_courses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all courses for current user (or all courses if admin)."""
    query = db.query(Course).filter(Course.is_deleted == False)  # noqa: E712
    if current_user.role != "admin":
        query = query.filter(Course.user_id == current_user.id)

    courses = query.order_by(Course.created_at.desc()).all()

    items = []
    for c in courses:
        filenames = c.filenames if isinstance(c.filenames, list) else []
        error_code, error_message = public_error(
            c.error_code, "DOCUMENT_PROCESSING_FAILED"
        )
        items.append(
            CourseListItem(
                course_id=c.id,
                name=c.name,
                status=c.status,
                filenames=filenames,
                file_count=len(filenames),
                created_at=c.created_at,
                error=error_message if c.status in {"failed", "paused_due_to_quota"} else None,
                error_code=error_code if c.status in {"failed", "paused_due_to_quota"} else None,
            )
        )
    return {"courses": items, "total": len(items)}


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    course_in: CourseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new course entry manually without files."""
    _enforce_course_limit(db, current_user.id)
    db_course = Course(
        user_id=current_user.id,
        filenames=course_in.filenames if course_in.filenames else [],
        metadata_json=course_in.metadata_json,
        status="processing",
        stage="extracting",
        progress=30,
    )
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    return db_course


@router.patch("/{course_id}", response_model=CourseResponse)
def rename_course(
    course_id: str,
    body: CourseRenameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a course."""
    course = get_valid_course(course_id, current_user, db)

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tên khóa học không được để trống.")

    course.name = name[:200]
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}")
def delete_course(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft delete a course and remove its local uploaded files."""
    course = get_valid_course(course_id, current_user, db)

    now = datetime.utcnow()
    db.query(ProcessingJob).filter(
        ProcessingJob.course_id == course.id,
        ProcessingJob.job_type == "preprocess",
        ProcessingJob.status.in_(["queued", "running"]),
    ).update(
        {
            ProcessingJob.status: "failed",
            ProcessingJob.error_code: "DOCUMENT_PROCESSING_CANCELLED",
            ProcessingJob.error_message: "Tài liệu đã bị xóa trước khi xử lý hoàn tất.",
            ProcessingJob.message: "Tài liệu đã bị xóa trước khi xử lý hoàn tất.",
            ProcessingJob.completed_at: now,
            ProcessingJob.updated_at: now,
        },
        synchronize_session=False,
    )
    # Soft delete and cancel active preprocessing in the same transaction.
    course.is_deleted = True
    course.status = "deleted"
    db.commit()

    from app.services.document_processor import get_document_processor

    get_document_processor().purge_course_storage(course.id)

    return {"status": "deleted"}


@router_single.get("/{course_id}/status", response_model=CourseStatusResponse)
@router.get("/{course_id}/status", response_model=CourseStatusResponse)
def get_course_status(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get real course processing status."""
    course = get_valid_course(course_id, current_user, db)

    filenames = course.filenames if isinstance(course.filenames, list) else []
    latest_job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.course_id == course.id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )
    public_code, public_message = public_error(
        course.error_code, "DOCUMENT_PROCESSING_FAILED"
    )
    if course.status == "ready":
        message = "Tài liệu đã sẵn sàng."
    elif course.status in {"failed", "paused_due_to_quota"}:
        message = public_message
    else:
        message = "Đang phân tích và xử lý tài liệu..."

    return {
        "course_id": course.id,
        "name": course.name,
        "status": course.status,
        "stage": course.stage,
        "progress": course.progress,
        "chunk_count": course.chunk_count,
        "embedding_status": course.embedding_status,
        "quality_score": course.quality_score,
        "message": message,
        "filenames": filenames,
        "file_count": len(filenames),
        "error": public_message if course.status in {"failed", "paused_due_to_quota"} else None,
        "failure_stage": course.failure_stage,
        "error_code": public_code if course.status in {"failed", "paused_due_to_quota"} else None,
        "can_retry": course.can_retry,
        "recommended_action": course.recommended_action,
        "job_id": latest_job.id if latest_job else None,
        "document_quality_report": {
            "score": course.quality_score,
            "summary": "Tài liệu rõ ràng, cấu trúc tốt." if course.quality_score >= 70 else "Chất lượng tài liệu trung bình, có thể ảnh hưởng đến nội dung sinh ra.",
        }
        if course.status == "ready" and course.quality_score > 0
        else None,
    }

