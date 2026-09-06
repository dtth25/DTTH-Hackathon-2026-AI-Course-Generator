from datetime import datetime, timedelta

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.routers.jobs import job_response
from app.services import database
from app.services.job_service import claim_job, schedule_capacity_continuation


def test_capacity_continuation_preserves_progress_and_stage_through_reclaim():
    job_id = "capacity-job"
    with database.SessionLocal.begin() as db:
        db.add(Course(id="course", user_id="owner", filenames=["source.txt"], status="ready"))
        db.add(
            ProcessingJob(
                id=job_id,
                course_id="course",
                user_id="owner",
                job_type="book",
                status="running",
                product_stage="chapter",
                progress=57,
            attempts=1,
            failure_attempts=0,
            max_attempts=1,
                worker_id="worker-a",
                lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
                payload_json={"version_id": "v1"},
                queue_name="generation",
            )
        )

    retry_at = datetime.utcnow() - timedelta(seconds=1)
    with database.SessionLocal() as db:
        assert schedule_capacity_continuation(
            db,
            job_id,
            "worker-a",
            retry_at,
            expected_attempt=1,
        )
        retrying = db.get(ProcessingJob, job_id)
        assert retrying.status == "retry_scheduled"
        assert retrying.progress == 57
        assert retrying.failure_attempts == 0
        assert retrying.product_stage == "capacity_wait"
        assert job_response(db, retrying)["stage"] == "capacity_wait"

    with database.SessionLocal() as db:
        assert claim_job(db, job_id, "worker-b", 300)
        reclaimed = db.get(ProcessingJob, job_id)
        assert reclaimed.status == "running"
        assert reclaimed.attempts == 2
        assert reclaimed.failure_attempts == 0
        assert reclaimed.progress == 57
        assert reclaimed.product_stage == "generating"
