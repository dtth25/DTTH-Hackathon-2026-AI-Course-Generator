"""Create verified deterministic users for the guarded load-test environment."""
import argparse
import os

from app.core.config import settings
from app.models.user import User
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.core.security import get_password_hash
from app.services.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if settings.ENVIRONMENT != "loadtest" or args.confirm != "LOADTEST":
        raise SystemExit("refusing outside confirmed loadtest environment")
    if not 1 <= args.count <= 1000:
        raise SystemExit("count must be between 1 and 1000")
    password = os.environ.get("LOAD_TEST_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("LOAD_TEST_PASSWORD must contain at least 12 characters")
    password_hash = get_password_hash(password)
    created = existing = courses_created = 0
    with SessionLocal() as db:
        for number in range(1, args.count + 1):
            # EmailStr deliberately rejects RFC-reserved `.invalid`; this public
            # example domain is used only inside the disposable load-test database.
            email = f"loadtest-{number:03d}@example.com"
            user = db.query(User).filter(User.email == email).first()
            if user:
                existing += 1
            else:
                user = User(
                    email=email,
                    hashed_password=password_hash,
                    full_name=f"Load User {number:03d}",
                    is_verified=True,
                    is_active=True,
                    role="user",
                )
                db.add(user)
                db.flush()
                created += 1
            course_id = f"load-course-{number:03d}"
            if not db.get(Course, course_id):
                db.add(
                    Course(
                        id=course_id,
                        user_id=user.id,
                        filenames=["load-document.txt"],
                        name="Load baseline",
                        status="ready",
                        stage="completed",
                        progress=100,
                        chunk_count=1,
                        embedding_status="completed",
                        quality_score=100,
                    )
                )
                db.add(
                    ProcessingJob(
                        id=f"load-job-{number:03d}",
                        course_id=course_id,
                        user_id=user.id,
                        job_type="preprocess",
                        status="succeeded",
                        progress=100,
                        message="Hoàn tất",
                        payload_json={},
                        queue_name="ingestion",
                    )
                )
                courses_created += 1
        admin_email = "loadtest-admin@example.com"
        if not db.query(User).filter(User.email == admin_email).first():
            db.add(
                User(
                    email=admin_email,
                    hashed_password=password_hash,
                    full_name="Load Test Admin",
                    is_verified=True,
                    is_active=True,
                    role="admin",
                )
            )
        db.commit()
    print(f"requested={args.count} created={created} existing={existing} baseline_courses_created={courses_created}")


if __name__ == "__main__":
    main()
