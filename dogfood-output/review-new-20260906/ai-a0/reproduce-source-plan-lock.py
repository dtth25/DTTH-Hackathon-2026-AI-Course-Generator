"""Offline audit probe; writes only disposable SQLite and evidence beside itself."""
from pathlib import Path
import json
import os
import socket
import sys
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DB_PATH = HERE / "source-plan-lock-probe.db"
assert not DB_PATH.exists(), "Use a fresh diagnostic database; never overwrite one."
os.environ.update(
    DATABASE_URL="sqlite:///" + DB_PATH.as_posix(),
    JWT_SECRET="offline-diagnostic-secret-not-used-for-auth-20260906",
    OPENROUTER_API_KEY="offline-diagnostic-not-a-real-key",
)
sys.path.insert(0, str(ROOT / "src" / "backend"))
# Do not read the repository .env or any saved credentials.
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}

class OfflineSocket(socket.socket):
    def connect(self, *args, **kwargs):
        raise AssertionError("Network access forbidden in offline probe")
    def connect_ex(self, *args, **kwargs):
        raise AssertionError("Network access forbidden in offline probe")
socket.socket = OfflineSocket

from app.services import database
from app.models.user import User
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.source_plan import SourcePlanRecord
from app.models.provider_call import ProviderCall
from app.schemas.source_plan import SourcePlan, SourceObjective, SourcePlanUnit
from app.services.source_plan import get_or_create_source_plan
from app.services.provider_usage import dispatch_provider, ProviderCallContext, usage_context

database.Base.metadata.create_all(database.engine)
factory = database.SessionLocal
with factory.begin() as db:
    db.add(User(id="probe-user", email="offline@example.invalid", hashed_password="fake"))
    db.add(Course(id="probe-course", user_id="probe-user", status="ready"))
    db.add(ProcessingJob(
        id="probe-job", course_id="probe-course", user_id="probe-user", job_type="slide",
        status="running", worker_id="probe-worker", attempts=1,
        lease_expires_at=datetime.utcnow() + timedelta(minutes=10),
    ))

fake_calls = 0
builder_calls = 0
def fake_provider(**kwargs):
    global fake_calls
    fake_calls += 1
    return SimpleNamespace(id=f"offline-response-{fake_calls}", usage={
        "cost": 0, "prompt_tokens": 1, "completion_tokens": 1,
    })

def dispatch():
    with usage_context(ProviderCallContext(
        job_id="probe-job", worker_id="probe-worker", job_attempt=1,
        course_id="probe-course", user_id="probe-user", feature="slide", stage="generating",
    )):
        return dispatch_provider(fake_provider, model="offline-fake-model", request={}, feature="generation", attempt=1)

def plan(revision):
    return SourcePlan(revision=revision, source_digest="d" * 64,
        objectives=[SourceObjective(id="o1", text="Offline probe", evidence_ids=["e1"])],
        units=[SourcePlanUnit(id="u1", title="Probe", objective_ids=["o1"], evidence_ids=["e1"])])

def builder(revision):
    global builder_calls
    builder_calls += 1
    dispatch()
    return plan(revision)

def counts():
    with factory() as db:
        return {"provider_calls": db.query(ProviderCall).count(), "source_plans": db.query(SourcePlanRecord).count()}

evidence = {"network": "socket connect disabled; fake provider only", "database": str(DB_PATH),
    "engine": "real create_database_engine(settings), default file-SQLite timeout and pool"}
dispatch()
evidence["outside_transaction_control"] = {"fake_calls": fake_calls, **counts()}
started = time.monotonic()
try:
    get_or_create_source_plan("probe-course", "d" * 64, "offline-fake-model", "probe-v1",
        db_session_factory=factory, create=builder)
    evidence["cold_plan"] = {"unexpected": "succeeded"}
except Exception as exc:
    chain = []
    current = exc
    while current:
        chain.append({"type": type(current).__name__, "message": str(current)})
        current = current.__cause__
    evidence["cold_plan"] = {"elapsed_seconds": round(time.monotonic() - started, 3),
        "exception_chain": chain, "fake_calls": fake_calls, "builder_calls": builder_calls, **counts()}

# After rollback, the same production dispatch succeeds; the fake itself is healthy.
dispatch()
evidence["after_rollback_control"] = {"fake_calls": fake_calls, **counts()}

# A purely local builder populates the cache; a hit never enters the paid builder.
get_or_create_source_plan("probe-course", "d" * 64, "offline-fake-model", "probe-v1",
    db_session_factory=factory, create=plan)
cached = get_or_create_source_plan("probe-course", "d" * 64, "offline-fake-model", "probe-v1",
    db_session_factory=factory, create=builder)
evidence["warm_plan_control"] = {"revision": cached.revision, "fake_calls": fake_calls,
    "builder_calls": builder_calls, **counts()}

assert evidence["outside_transaction_control"]["fake_calls"] == 1
assert evidence["cold_plan"]["fake_calls"] == 1
assert evidence["cold_plan"]["source_plans"] == 0
assert evidence["cold_plan"]["exception_chain"][0]["type"] == "AccountingError"
assert "database is locked" in str(evidence["cold_plan"]["exception_chain"])
assert evidence["after_rollback_control"]["fake_calls"] == 2
assert evidence["warm_plan_control"]["builder_calls"] == 1
assert evidence["warm_plan_control"]["source_plans"] == 1
database.engine.dispose()
(HERE / "source-plan-lock-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
