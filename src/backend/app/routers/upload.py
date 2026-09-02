"""Upload router for receiving and validating course documents."""

import os
import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.course import Course
from app.models.user import User
from app.routers.courses import _enforce_course_limit
from app.routers.documents import _schedule_processing
from app.schemas.course import UploadResponse
from app.services.job_service import create_job

router = APIRouter(prefix="/api", tags=["upload"])

MAX_FILES_PER_UPLOAD = 5


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_files(
    background_tasks: BackgroundTasks,
    files: Optional[List[UploadFile]] = File(None, alias="files"),
    files_bracket: Optional[List[UploadFile]] = File(None, alias="files[]"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload course documents (PDF, DOCX, TXT - max 3 files, max 50MB each)."""
    upload_files_list = files or files_bracket
    if not upload_files_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng chọn ít nhất 1 file để tải lên.",
        )

    if len(upload_files_list) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chỉ được phép tải lên tối đa {MAX_FILES_PER_UPLOAD} file mỗi lần.",
        )

    _enforce_course_limit(db, current_user.id)

    allowed_exts = {".pdf", ".docx", ".txt"}
    max_size = 50 * 1024 * 1024  # 50 MB
    saved_filenames = []
    saved_file_paths = []
    file_contents = []

    # Validate all files before saving
    for f in upload_files_list:
        if not f.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tên file không hợp lệ.",
            )
        filename = os.path.basename(f.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Định dạng file {ext} không được hỗ trợ. Chỉ chấp nhận .pdf, .docx, .txt.",
            )

        content = await f.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {filename} là file rỗng (0 bytes).",
            )
        if len(content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {filename} vượt quá kích thước tối đa cho phép (50MB).",
            )
        file_contents.append((filename, content))

    # Generate IDs
    course_id = uuid.uuid4().hex[:12]
    document_id = uuid.uuid4().hex[:12]

    # Save to local filesystem
    upload_dir = os.path.join(settings.UPLOAD_DIR, course_id)
    os.makedirs(upload_dir, exist_ok=True)

    for filename, content in file_contents:
        timestamp_prefix = int(time.time())
        safe_filename = f"{timestamp_prefix}_{filename}"
        file_path = os.path.join(upload_dir, safe_filename)
        with open(file_path, "wb") as out_file:
            out_file.write(content)
        saved_filenames.append(filename)
        saved_file_paths.append(file_path)

    # Create Course record in database
    db_course = Course(
        id=course_id,
        user_id=current_user.id,
        filenames=saved_filenames,
        status="processing",
        stage="extracting",
        progress=30,
        chunk_count=0,
        embedding_status="pending",
        quality_score=0,
    )
    db.add(db_course)
    db.commit()
    db.refresh(db_course)

    job = create_job(
        db,
        course_id=course_id,
        user_id=current_user.id,
        job_type="preprocess",
    )
    _schedule_processing(background_tasks, course_id, saved_file_paths, job.id)

    return {
        "course_id": course_id,
        "document_id": document_id,
        "filenames": saved_filenames,
        "file_count": len(saved_filenames),
        "status": "processing",
        "message": f"Đã nhận {len(saved_filenames)} file và đang phân tích...",
        "job_id": job.id,
    }

