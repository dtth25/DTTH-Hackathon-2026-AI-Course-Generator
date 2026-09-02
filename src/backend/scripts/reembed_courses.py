"""One-off migration: re-embed existing courses' chunks through the currently configured
embedding function (and the reworked chunking) — needed after switching CHROMA_COLLECTION_NAME
to a new value or wiping data/chroma/, since Chroma binds an embedding function to a collection
at creation time and old chunks embedded with the previous function are not compatible.

Skips AI course-title regeneration on purpose (a real provider call) — courses already have a
name, so re-running it here would just burn quota for no visible change.

Usage (from src/backend):
    uv run python scripts/reembed_courses.py [--course-id ID ...]
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.services.database import SessionLocal  # noqa: E402
from app.services.document_processor import DocumentProcessor  # noqa: E402
from app.services.vector_store import get_vector_store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("reembed_courses")


def _reembed_course(processor: DocumentProcessor, course: Course) -> int:
    """Re-extract, re-clean, re-chunk, and re-store one course's original files.

    Files on disk are saved as "{unix_timestamp}_{original_filename}" (see
    routers/upload.py), while Course.filenames only stores the clean original name —
    so we glob the course's upload directory instead of reconstructing the on-disk name.
    """
    file_paths = processor.list_saved_course_files(course.id)
    if not file_paths:
        logger.warning(f"Course {course.id} ({course.name}): no source files found on disk, skipping.")
        return 0

    all_documents = []
    for path in file_paths:
        all_documents.extend(processor.extract_and_chunk_file(path, course.id))

    if not all_documents:
        logger.warning(f"Course {course.id} ({course.name}): produced 0 chunks, skipping store.")
        return 0

    processor.vector_store.add_documents(all_documents, course_id=course.id)

    db = SessionLocal()
    try:
        db_course = db.query(Course).filter(Course.id == course.id).first()
        if db_course:
            db_course.chunk_count = len(all_documents)
            db.commit()
    finally:
        db.close()

    return len(all_documents)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--course-id", action="append", dest="course_ids",
        help="Limit to specific course ID(s); repeatable. Default: all non-deleted courses.",
    )
    args = parser.parse_args()

    vector_store = get_vector_store()
    processor = DocumentProcessor(vector_store=vector_store)

    db = SessionLocal()
    try:
        query = db.query(Course).filter(Course.is_deleted == False)  # noqa: E712
        if args.course_ids:
            query = query.filter(Course.id.in_(args.course_ids))
        courses = query.all()
        # Detach from session before closing so attribute access below doesn't error.
        for c in courses:
            db.expunge(c)
    finally:
        db.close()

    logger.info(
        f"Re-embedding {len(courses)} course(s) into collection "
        f"'{settings.CHROMA_COLLECTION_NAME}' "
        f"(provider=openrouter, model={settings.OPENROUTER_EMBEDDING_MODEL})..."
    )
    total = 0
    failed = []
    for course in courses:
        try:
            count = _reembed_course(processor, course)
            logger.info(f"  {course.id} ({course.name}): {count} chunks")
            total += count
        except Exception as e:
            # A single course hitting a rate-limit or provider error must not lose
            # progress already made on the other courses in this run.
            logger.error(f"  {course.id} ({course.name}): FAILED - {e}")
            failed.append(course.id)
    logger.info(f"Done. {total} chunks written across {len(courses) - len(failed)}/{len(courses)} course(s).")
    if failed:
        logger.warning(f"Failed course(s), re-run with --course-id for these once quota resets: {failed}")


if __name__ == "__main__":
    main()
