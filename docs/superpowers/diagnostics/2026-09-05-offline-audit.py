"""Reproduce audited defects without credentials, network, or live database writes.

Run from src/backend:
  .venv/Scripts/python.exe ../../docs/superpowers/diagnostics/2026-09-05-offline-audit.py
These are observations of the pre-fix behavior, not acceptance tests for it.
"""

import json
import os
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src" / "backend"))
os.environ.update({
    "DATABASE_URL": "sqlite:///:memory:",
    "JWT_SECRET": "offline-audit-only-secret-with-32-characters",
    "OPENROUTER_API_KEY": "offline-audit-not-a-real-key",
    "ENVIRONMENT": "test",
    "JOB_QUEUE_PROVIDER": "inline",
    "CREATE_DEFAULT_ADMIN": "false",
})


def block_network(*args, **kwargs):
    raise AssertionError("Network is forbidden in this offline audit")


socket.socket.connect = block_network
socket.create_connection = block_network

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.course import Course
from app.models.user import User
from app.models.processing_job import ProcessingJob
from app.schemas.generator_output import SlideItem, SlidesOutput, validate_and_score_output
from app.services.database import Base
from app.services.generator import Generator

engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
Base.metadata.create_all(engine)
factory = sessionmaker(bind=engine)
with factory() as db:
    db.add(User(id="audit-user", email="audit@example.com", hashed_password="unused"))
    db.add(Course(id="audit-course", user_id="audit-user", status="ready", metadata_json="{}"))
    db.add(ProcessingJob(
        id="audit-job", course_id="audit-course", user_id="audit-user", job_type="book",
        status="running", progress=0, attempts=1, worker_id="audit-worker",
        lease_expires_at=datetime.utcnow() + timedelta(minutes=10),
        payload_json={"version_id": "audit-v1"},
    ))
    db.commit()

generator = Generator(None, None)
written = generator._set_artifact_status(
    "audit-course", "book", "processing", progress=52, version_id="audit-v1",
    job_id="audit-job", worker_id="audit-worker", attempt_number=1,
    db_session_factory=factory,
)
with factory() as db:
    metadata = json.loads(db.get(Course, "audit-course").metadata_json)
    artifact_progress = metadata["study_pack"]["artifacts"]["book"]["versions"]["audit-v1"]["progress"]
    job_progress = db.get(ProcessingJob, "audit-job").progress
    print(json.dumps({"check": "progress_boundary", "write_succeeded": written,
        "artifact_progress": artifact_progress, "job_progress": job_progress,
        "defect_confirmed": artifact_progress != job_progress}))

for valid_ids in ([], ["existing-id"]):
    deck = SlidesOutput(title="Audit", slides=[SlideItem(
        slide_number=1, title="Wrong arithmetic", bullet_points=["2 + 2 = 5"],
        source_chunk_ids=["existing-id"],
    )])
    _, score, warnings = validate_and_score_output(deck, "slides", valid_ids)
    print(json.dumps({"check": "quality_is_not_factual_accuracy", "valid_evidence_count": len(valid_ids),
        "deliberately_wrong_arithmetic": True, "score": score, "warning_count": len(warnings)}))

from openai import DEFAULT_TIMEOUT
print(json.dumps({"check": "installed_sdk_default_timeout", "read_seconds": DEFAULT_TIMEOUT.read}))
engine.dispose()
print(json.dumps({"openrouter_cost_usd": 0, "network_calls": 0}))
