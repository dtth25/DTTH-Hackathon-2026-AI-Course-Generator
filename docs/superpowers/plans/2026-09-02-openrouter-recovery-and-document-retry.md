# OpenRouter Recovery and Document Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make document ingestion recover cleanly from OpenRouter key, credit, quota, rate-limit, and transient provider failures without misdiagnosing the PDF or requiring a second upload.

**Architecture:** Add one provider-error boundary that turns SDK exceptions into stable internal codes and safe Vietnamese user messages. Persist structured failure and job state in SQL, expose ownership-protected retry/status APIs, and let the existing inline `BackgroundTasks` execution reprocess the original saved files; the separate 50–100-user plan later swaps only the dispatcher for Celery.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, OpenAI Python client pointed at OpenRouter, Chroma, pytest, Next.js 16, React 19, TypeScript, Vitest, Playwright.

**Spec:** `docs/api_contract.md` sections 1–2 and `docs/PRD.md` sections 3–5.

## Global Constraints

- OpenRouter remains the only AI and embedding gateway; do not add a silent provider or model fallback.
- The browser never receives API keys, key labels, key hashes, raw SDK payloads, model-routing metadata, stack traces, or `technical_error`.
- Do not retry permanent `401`, `402`, or quota/key-limit `403` responses automatically.
- Keep automatic retries for `429`, timeouts, connection failures, and `5xx`, with bounded exponential backoff.
- Preserve uploaded `.pdf`, `.docx`, and `.txt` files after processing failure so manual retry can reuse them.
- Retry, job, course, and admin-provider endpoints must enforce active-user ownership; only admins may see provider capacity metadata.
- Keep the four public generation endpoints unchanged: `/api/generate-book`, `/api/generate-slide`, `/api/generate-quiz`, `/api/generate-vid`.
- `/health` must remain local and fast; it must not call OpenRouter.
- Local/dev remains SQLite + embedded Chroma + FastAPI `BackgroundTasks` in this plan.
- Public generation stays grounded only in successfully indexed chunks from the uploaded documents.

## File Map

- Create `src/backend/app/services/provider_errors.py`: provider exception classification and safe failure contract.
- Create `src/backend/app/services/provider_health.py`: cached current-key/model preflight for workers and admins.
- Create `src/backend/app/models/processing_job.py`: durable queue-neutral job metadata.
- Create `src/backend/app/services/job_service.py`: create/update/query processing jobs.
- Create `src/backend/app/routers/documents.py`: retry and job-status endpoints with ownership checks.
- Create `src/backend/alembic/versions/b8c9d0e1f2a3_add_processing_failures_and_jobs.py`: course failure fields and processing-jobs table.
- Create `src/backend/tests/test_provider_errors.py`: permanent/transient error classification and retry policy tests.
- Create `src/backend/tests/test_provider_health.py`: safe preflight and TTL-cache tests.
- Create `src/backend/tests/test_document_retry.py`: retry, ownership, deduplication, and saved-file tests.
- Modify `src/backend/app/services/vector_store.py`: fail fast on permanent embedding errors.
- Modify `src/backend/app/services/document_processor.py`: provider preflight, structured status, job updates, and reusable saved-file discovery.
- Modify `src/backend/app/models/course.py`: structured failure columns.
- Modify `src/backend/app/models/__init__.py`: export `ProcessingJob`.
- Modify `src/backend/app/schemas/course.py`: structured course/job/retry response fields.
- Modify `src/backend/app/schemas/__init__.py`: export new schemas.
- Modify `src/backend/app/routers/upload.py`: create and return a processing job.
- Modify `src/backend/app/routers/courses.py`: safe structured failure fields in list/status responses.
- Modify `src/backend/app/routers/auth.py`: explicitly remove processing jobs during SQLite account deletion.
- Modify `src/backend/app/routers/admin.py`: admin-only provider status endpoint.
- Modify `src/backend/main.py`: register the documents router.
- Modify `src/backend/app/core/config.py`: provider preflight cache and retry timing settings.
- Modify `src/frontend/src/lib/types.ts`: job and structured failure types.
- Modify `src/frontend/src/lib/api.ts`: retry/job-status clients and centralized network-error normalization.
- Create `src/frontend/src/lib/api.test.ts`: prove raw browser fetch errors never reach UI callers.
- Modify `src/frontend/src/app/course/[id]/page.tsx`: actionable error panel and retry polling.
- Modify `src/frontend/src/app/course/[id]/page.test.tsx`: failed-course and retry UI tests.
- Modify `src/frontend/e2e/visual-brand.spec.ts`: mocked quota failure and retry journey.
- Modify `.env.example`, `README.md`, and `docs/api_contract.md`: operator settings and exact recovery runbook.

---

### Task 1: Stable OpenRouter Failure Contract

**Files:**
- Create: `src/backend/app/services/provider_errors.py`
- Create: `src/backend/tests/test_provider_errors.py`

**Interfaces:**
- Consumes: arbitrary exceptions raised by the OpenAI client, `httpx`, or a wrapper.
- Produces: `ProviderErrorCode`, `ProviderFailure`, `ProviderRequestError`, and `classify_openrouter_error(exc: Exception) -> ProviderFailure`.

- [ ] **Step 1: Write the failing classification tests**

```python
from app.services.provider_errors import (
    ProviderErrorCode,
    classify_openrouter_error,
)


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def test_key_limit_403_is_manual_retry_only():
    failure = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    assert failure.code == ProviderErrorCode.KEY_LIMIT_EXCEEDED
    assert failure.can_retry is True
    assert failure.automatic_retry is False
    assert failure.recommended_action == "restore_provider_quota"
    assert "Key limit" not in failure.user_message


def test_rate_limit_429_is_automatic_retry():
    failure = classify_openrouter_error(FakeStatusError(429, "rate limited"))
    assert failure.code == ProviderErrorCode.RATE_LIMITED
    assert failure.automatic_retry is True


def test_invalid_key_and_payment_are_not_automatically_retried():
    invalid = classify_openrouter_error(FakeStatusError(401, "invalid api key"))
    payment = classify_openrouter_error(FakeStatusError(402, "payment required"))
    assert invalid.code == ProviderErrorCode.KEY_INVALID
    assert payment.code == ProviderErrorCode.CREDITS_EXHAUSTED
    assert invalid.automatic_retry is False
    assert payment.automatic_retry is False
```

- [ ] **Step 2: Run the new tests and verify the missing module failure**

Run:

```powershell
Set-Location src/backend
uv run --project . pytest tests/test_provider_errors.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: app.services.provider_errors`.

- [ ] **Step 3: Implement the provider failure contract**

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class ProviderErrorCode(StrEnum):
    KEY_INVALID = "OPENROUTER_KEY_INVALID"
    KEY_LIMIT_EXCEEDED = "OPENROUTER_KEY_LIMIT_EXCEEDED"
    CREDITS_EXHAUSTED = "OPENROUTER_CREDITS_EXHAUSTED"
    ACCESS_DENIED = "OPENROUTER_ACCESS_DENIED"
    RATE_LIMITED = "OPENROUTER_RATE_LIMITED"
    UNAVAILABLE = "OPENROUTER_UNAVAILABLE"
    TIMEOUT = "OPENROUTER_TIMEOUT"
    REQUEST_FAILED = "OPENROUTER_REQUEST_FAILED"


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    code: ProviderErrorCode
    user_message: str
    can_retry: bool
    automatic_retry: bool
    recommended_action: str
    http_status: Optional[int]
    technical_message: str


class ProviderRequestError(RuntimeError):
    def __init__(self, failure: ProviderFailure):
        super().__init__(failure.user_message)
        self.failure = failure


def _status_code(exc: Exception) -> Optional[int]:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_openrouter_error(exc: Exception) -> ProviderFailure:
    status = _status_code(exc)
    technical = str(exc)[:1000]
    folded = technical.casefold()
    if status == 401:
        return ProviderFailure(ProviderErrorCode.KEY_INVALID, "Dịch vụ AI chưa được cấu hình hợp lệ.", True, False, "contact_admin", status, technical)
    if status == 402 or "insufficient credit" in folded or "payment required" in folded:
        return ProviderFailure(ProviderErrorCode.CREDITS_EXHAUSTED, "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.", True, False, "restore_provider_quota", status, technical)
    if status == 403 and "key limit exceeded" in folded:
        return ProviderFailure(ProviderErrorCode.KEY_LIMIT_EXCEEDED, "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.", True, False, "restore_provider_quota", status, technical)
    if status == 403:
        return ProviderFailure(ProviderErrorCode.ACCESS_DENIED, "Dịch vụ AI không có quyền thực hiện yêu cầu này.", True, False, "contact_admin", status, technical)
    if status == 429:
        return ProviderFailure(ProviderErrorCode.RATE_LIMITED, "Dịch vụ AI đang bận. Tác vụ có thể thử lại sau.", True, True, "retry_later", status, technical)
    if status is not None and status >= 500:
        return ProviderFailure(ProviderErrorCode.UNAVAILABLE, "Dịch vụ AI tạm thời không khả dụng.", True, True, "retry_later", status, technical)
    if "timeout" in folded or "timed out" in folded:
        return ProviderFailure(ProviderErrorCode.TIMEOUT, "Kết nối dịch vụ AI quá thời gian chờ.", True, True, "retry_later", status, technical)
    return ProviderFailure(ProviderErrorCode.REQUEST_FAILED, "Không thể hoàn tất yêu cầu AI.", True, False, "retry_later", status, technical)
```

- [ ] **Step 4: Run the tests and verify all classifications pass**

Run: `uv run --project . pytest tests/test_provider_errors.py -q`

Expected: PASS with no provider key or raw payload printed.

- [ ] **Step 5: Commit the provider error boundary**

```powershell
git add src/backend/app/services/provider_errors.py src/backend/tests/test_provider_errors.py
git commit -m "feat: classify OpenRouter failures safely"
```

---

### Task 2: Fail Fast for Permanent Embedding Errors

**Files:**
- Modify: `src/backend/app/services/vector_store.py:17-44`
- Modify: `src/backend/tests/test_provider_errors.py`

**Interfaces:**
- Consumes: `classify_openrouter_error()` and `ProviderRequestError` from Task 1.
- Produces: `OpenRouterEmbeddingFunction._embed()` that retries only transient failures and raises a structured terminal error.

- [ ] **Step 1: Add failing retry-count tests**

```python
from app.services.provider_errors import ProviderErrorCode, ProviderRequestError
from app.services.vector_store import OpenRouterEmbeddingFunction


class AlwaysFailsEmbeddings:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise self.error


class FakeClient:
    def __init__(self, embeddings):
        self.embeddings = embeddings


def build_embedding_function(error):
    function = OpenRouterEmbeddingFunction.__new__(OpenRouterEmbeddingFunction)
    embeddings = AlwaysFailsEmbeddings(error)
    function._client = FakeClient(embeddings)
    function._model = "openai/text-embedding-3-small"
    function._max_retries = 3
    function._max_retry_delay = 0
    return function, embeddings


def test_embedding_key_limit_stops_after_one_attempt():
    function, embeddings = build_embedding_function(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    try:
        function._embed(["document text"])
    except ProviderRequestError as exc:
        assert exc.failure.code == ProviderErrorCode.KEY_LIMIT_EXCEEDED
    else:
        raise AssertionError("ProviderRequestError was not raised")
    assert embeddings.calls == 1


def test_embedding_503_uses_all_three_attempts(monkeypatch):
    monkeypatch.setattr("app.services.vector_store.time.sleep", lambda _: None)
    function, embeddings = build_embedding_function(FakeStatusError(503, "unavailable"))
    try:
        function._embed(["document text"])
    except ProviderRequestError as exc:
        assert exc.failure.code == ProviderErrorCode.UNAVAILABLE
    else:
        raise AssertionError("ProviderRequestError was not raised")
    assert embeddings.calls == 3
```

- [ ] **Step 2: Run the focused tests and verify the permanent error is retried three times**

Run: `uv run --project . pytest tests/test_provider_errors.py -q`

Expected: FAIL because the current embedding function retries the `403` three times and raises plain `RuntimeError`.

- [ ] **Step 3: Implement selective retry and bounded delay**

Change the constructor to accept `max_retry_delay`, then replace `_embed` with:

```python
def _embed(self, texts: List[str]) -> List[List[float]]:
    delay = 1.0
    last_failure = None
    for attempt in range(1, self._max_retries + 1):
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
            return [item.embedding for item in response.data]
        except Exception as exc:
            failure = classify_openrouter_error(exc)
            last_failure = failure
            logger.warning(
                "OpenRouter embedding attempt %s/%s failed with %s",
                attempt,
                self._max_retries,
                failure.code,
            )
            if not failure.automatic_retry or attempt == self._max_retries:
                raise ProviderRequestError(failure) from exc
            time.sleep(min(delay, self._max_retry_delay))
            delay *= 2
    raise ProviderRequestError(last_failure)
```

Wire `settings.EMBEDDING_MAX_RETRIES` and `settings.EMBEDDING_MAX_RETRY_DELAY` through `_build_embedding_function()`.

- [ ] **Step 4: Run provider and vector-store tests**

Run:

```powershell
uv run --project . pytest tests/test_provider_errors.py tests/test_vector_store_and_processor.py -q
```

Expected: PASS; the `403 key limit` fixture records one client call and the `503` fixture records three.

- [ ] **Step 5: Commit selective embedding retry**

```powershell
git add src/backend/app/services/vector_store.py src/backend/tests/test_provider_errors.py
git commit -m "fix: stop retrying permanent embedding failures"
```

---

### Task 3: Persist Structured Course Failures and Processing Jobs

**Files:**
- Create: `src/backend/app/models/processing_job.py`
- Create: `src/backend/app/services/job_service.py`
- Create: `src/backend/alembic/versions/b8c9d0e1f2a3_add_processing_failures_and_jobs.py`
- Modify: `src/backend/app/models/course.py`
- Modify: `src/backend/app/models/__init__.py`
- Modify: `src/backend/app/schemas/course.py`
- Modify: `src/backend/app/schemas/__init__.py`
- Modify: `src/backend/app/routers/auth.py`
- Create: `src/backend/tests/test_document_retry.py`

**Interfaces:**
- Produces: `ProcessingJob`, `JobStatus`, `JobType`, `create_job()`, `mark_job_running()`, `mark_job_succeeded()`, `mark_job_failed()`, and `JobResponse`.
- Produces course failure fields: `failure_stage`, `error_code`, `can_retry`, `recommended_action`, and private `technical_error`.

- [ ] **Step 1: Write failing model/service tests**

```python
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.job_service import create_job, mark_job_failed, mark_job_running
from app.services.database import SessionLocal


def _auth_headers(client, email: str) -> dict[str, str]:
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "full_name": "Retry Test"},
    )
    assert register.status_code == 201
    verified = client.post(
        "/api/auth/verify-email",
        json={"email": email, "code": "000000"},
    )
    assert verified.status_code == 200
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_processing_job_lifecycle():
    db = SessionLocal()
    try:
        user = User(
            email="job-owner@example.com",
            hashed_password="not-used-by-this-test",
            is_verified=True,
        )
        db.add(user)
        db.flush()
        course = Course(user_id=user.id, filenames=["source.txt"])
        db.add(course)
        db.commit()
        job = create_job(
            db,
            course_id=course.id,
            user_id=user.id,
            job_type="preprocess",
        )
        assert job.status == "queued"
        mark_job_running(db, job.id, "Đang phân tích tài liệu")
        db.refresh(job)
        assert job.status == "running"
        mark_job_failed(db, job.id, error_code="OPENROUTER_KEY_LIMIT_EXCEEDED", message="Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.")
        db.refresh(job)
        assert job.status == "failed"
        assert job.completed_at is not None
    finally:
        db.close()


def test_account_cleanup_deletes_processing_jobs(client):
    headers = _auth_headers(client, "delete-job-owner@example.com")
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        course = Course(user_id=user_id, filenames=["source.txt"])
        db.add(course)
        db.commit()
        create_job(db, course_id=course.id, user_id=user_id, job_type="preprocess")
    deleted = client.request(
        "DELETE",
        "/api/auth/me",
        headers=headers,
        json={"password": "password123"},
    )
    assert deleted.status_code == 204
    with SessionLocal() as db:
        assert db.query(ProcessingJob).filter_by(user_id=user_id).count() == 0
```

- [ ] **Step 2: Run the test and verify the model/service imports fail**

Run: `uv run --project . pytest tests/test_document_retry.py::test_processing_job_lifecycle -q`

Expected: FAIL with missing `processing_job` or `job_service`.

- [ ] **Step 3: Add the SQLAlchemy model and course fields**

Define `ProcessingJob` with these columns:

```python
class JobType(StrEnum):
    PREPROCESS = "preprocess"
    BOOK = "book"
    SLIDES = "slides"
    QUIZ = "quiz"
    VIDEO = "video"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default=JobStatus.QUEUED.value, index=True)
    progress = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=False, default="Đang chờ xử lý")
    error_code = Column(String(80), nullable=True)
    error_message = Column(Text, nullable=True)
    external_task_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

Add nullable/defaulted fields to `Course` so existing rows migrate safely:

```python
failure_stage = Column(String(50), nullable=True)
error_code = Column(String(80), nullable=True)
can_retry = Column(Boolean, nullable=False, default=False)
recommended_action = Column(String(80), nullable=True)
technical_error = Column(Text, nullable=True)
```

Because the test SQLite engine does not enforce `ON DELETE CASCADE`, update the existing account-deletion transaction in `routers/auth.py` to delete `ProcessingJob` rows for the user before deleting courses and the user. Keep soft-deleted course job history until account deletion; ownership rules make it inaccessible to other users.

- [ ] **Step 4: Add the Alembic upgrade/downgrade**

Use revision `b8c9d0e1f2a3` with `down_revision = "a7b8c9d0e1f2"`. The upgrade must add the five course columns, create `processing_jobs`, create indexes on `course_id`, `user_id`, `status`, and `external_task_id`; downgrade must remove those indexes/table before removing course columns.

- [ ] **Step 5: Implement explicit job lifecycle functions**

```python
def create_job(db: Session, *, course_id: str, user_id: str, job_type: str) -> ProcessingJob:
    job = ProcessingJob(course_id=course_id, user_id=user_id, job_type=job_type)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_running(db: Session, job_id: str, message: str) -> None:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = "running"
    job.message = message
    job.updated_at = datetime.utcnow()
    db.commit()


def mark_job_failed(db: Session, job_id: str, *, error_code: str, message: str) -> None:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = "failed"
    job.error_code = error_code
    job.error_message = message
    job.message = message
    job.completed_at = datetime.utcnow()
    db.commit()


def mark_job_succeeded(db: Session, job_id: str) -> None:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = "succeeded"
    job.progress = 100
    job.message = "Hoàn thành"
    job.error_code = None
    job.error_message = None
    job.completed_at = datetime.utcnow()
    db.commit()
```

- [ ] **Step 6: Extend Pydantic schemas without exposing technical errors**

Add `failure_stage`, `error_code`, `can_retry`, `recommended_action`, and `job_id` to `CourseStatusResponse`; add `job_id` to `UploadResponse`; define `JobResponse` and `DocumentRetryResponse`. Do not add `technical_error` to any public schema.

- [ ] **Step 7: Run migrations and tests on a disposable SQLite database**

Run:

```powershell
$env:DATABASE_URL='sqlite:///./data/plan-a-migration-test.db'
uv run --project . alembic upgrade head
uv run --project . alembic downgrade a7b8c9d0e1f2
Remove-Item -LiteralPath '.\data\plan-a-migration-test.db' -Force
uv run --project . pytest tests/test_document_retry.py::test_processing_job_lifecycle tests/test_document_retry.py::test_account_cleanup_deletes_processing_jobs -q
```

Expected: migration upgrade/downgrade and lifecycle test PASS.

- [ ] **Step 8: Commit durable failure/job state**

```powershell
git add src/backend/app/models src/backend/app/services/job_service.py src/backend/app/schemas src/backend/app/routers/auth.py src/backend/alembic/versions/b8c9d0e1f2a3_add_processing_failures_and_jobs.py src/backend/tests/test_document_retry.py
git commit -m "feat: persist document processing failures and jobs"
```

---

### Task 4: Cached Provider Preflight and Safe Admin Status

**Files:**
- Create: `src/backend/app/services/provider_health.py`
- Create: `src/backend/tests/test_provider_health.py`
- Modify: `src/backend/app/core/config.py`
- Modify: `src/backend/app/routers/admin.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `OPENROUTER_API_KEY`, content model, embedding model, and Task 1 failure classifier.
- Produces: `ProviderHealth`, `get_openrouter_health(force: bool = False) -> ProviderHealth`, and `GET /api/admin/provider-health`.

- [ ] **Step 1: Write failing TTL, redaction, and quota tests**

```python
def test_provider_health_reports_zero_remaining_without_secret(fake_httpx, monkeypatch):
    fake_httpx.respond_json(200, {"data": {"limit": 10, "limit_remaining": 0, "usage": 10.05, "limit_reset": None}})
    health = get_openrouter_health(force=True)
    assert health.available is False
    assert health.error_code == "OPENROUTER_KEY_LIMIT_EXCEEDED"
    assert health.limit_remaining == 0
    assert "sk-or" not in health.model_dump_json()


def test_provider_health_uses_ttl_cache(fake_httpx):
    get_openrouter_health(force=True)
    get_openrouter_health()
    assert fake_httpx.call_count == 1
```

Add an API test proving a normal user receives `403` and an admin receives the safe shape without key/hash/technical payload.

- [ ] **Step 2: Run the tests and verify missing service/route failures**

Run: `uv run --project . pytest tests/test_provider_health.py -q`

Expected: FAIL because `provider_health.py` and `/api/admin/provider-health` do not exist.

- [ ] **Step 3: Add preflight settings**

```python
OPENROUTER_PREFLIGHT_TTL_SECONDS: int = Field(default=30, ge=5, le=300)
OPENROUTER_PREFLIGHT_TIMEOUT_SECONDS: float = Field(default=5.0, ge=1.0, le=20.0)
```

Add the same values to `.env.example` with comments that preflight reads `/api/v1/key` and never logs the bearer token.

- [ ] **Step 4: Implement cached current-key/model checks**

`get_openrouter_health()` must:

1. Return the in-process cached result until `time.monotonic()` exceeds the TTL.
2. Call `GET https://openrouter.ai/api/v1/key` with bearer auth and the configured timeout.
3. Treat `limit_remaining <= 0` as unavailable with `OPENROUTER_KEY_LIMIT_EXCEEDED`.
4. Check configured model IDs against `GET /api/v1/models` and `GET /api/v1/embeddings/models` only when the key response is usable.
5. Return only `available`, `error_code`, `checked_at`, `limit`, `limit_remaining`, `limit_reset`, `content_model_available`, and `embedding_model_available`.
6. Pass request failures through `classify_openrouter_error()`; never store or return the bearer token or raw response.

- [ ] **Step 5: Add the admin-only endpoint**

```python
@router.get("/provider-health")
def provider_health(
    force: bool = False,
    _: User = Depends(require_admin),
) -> dict:
    return get_openrouter_health(force=force).model_dump()
```

Do not add provider preflight to `/health`; container readiness must not depend on internet or paid-provider state.

- [ ] **Step 6: Run provider-health and auth tests**

Run:

```powershell
uv run --project . pytest tests/test_provider_health.py tests/test_auth_and_core.py -q
```

Expected: PASS; normal-user access is forbidden and all serialized fixtures are secret-free.

- [ ] **Step 7: Commit provider preflight**

```powershell
git add src/backend/app/services/provider_health.py src/backend/app/core/config.py src/backend/app/routers/admin.py src/backend/tests/test_provider_health.py .env.example
git commit -m "feat: expose safe OpenRouter capacity status to admins"
```

---

### Task 5: Retry Saved Documents Without Re-uploading

**Files:**
- Create: `src/backend/app/routers/documents.py`
- Modify: `src/backend/app/services/document_processor.py:93-141,448-600`
- Modify: `src/backend/app/routers/upload.py:23-127`
- Modify: `src/backend/app/routers/courses.py:131-167`
- Modify: `src/backend/main.py:12-48`
- Modify: `src/backend/tests/test_document_retry.py`

**Interfaces:**
- Consumes: `ProviderRequestError`, provider preflight, `ProcessingJob`, saved uploads under `UPLOAD_DIR/{course_id}`.
- Produces: `list_saved_course_files(course_id: str) -> list[str]`, `_schedule_processing(...)`, `POST /api/documents/{course_id}/retry`, and `GET /api/jobs/{job_id}`.

- [ ] **Step 1: Write failing ownership and retry-state tests**

Reuse `_auth_headers()` from Task 3 and add these fixtures before the route tests so the module remains self-contained:

```python
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.course import Course
from app.services.database import SessionLocal


@pytest.fixture
def owner_headers(client):
    return _auth_headers(client, "retry-owner@example.com")


@pytest.fixture
def other_headers(client):
    return _auth_headers(client, "retry-other@example.com")


def _course_for(client, headers, *, status: str, with_file: bool) -> Course:
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        course = Course(
            user_id=user_id,
            filenames=["source.txt"],
            status=status,
            stage="failed" if status == "failed" else "ready",
            error_message="Dịch vụ AI đang tạm dừng vì hạn mức sử dụng."
            if status == "failed"
            else None,
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        db.expunge(course)
    if with_file:
        course_dir = Path(settings.UPLOAD_DIR) / course.id
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / "source.txt").write_text("Grounded retry fixture", encoding="utf-8")
    return course


@pytest.fixture
def failed_course_with_file(client, owner_headers):
    return _course_for(client, owner_headers, status="failed", with_file=True)


@pytest.fixture
def failed_course_without_file(client, owner_headers):
    return _course_for(client, owner_headers, status="failed", with_file=False)


@pytest.fixture
def ready_course(client, owner_headers):
    return _course_for(client, owner_headers, status="ready", with_file=True)
```

```python
def test_owner_can_retry_failed_course_from_saved_file(client, failed_course_with_file, owner_headers, monkeypatch):
    scheduled = []
    monkeypatch.setattr("app.routers.documents._schedule_processing", lambda *args: scheduled.append(args))
    response = client.post(f"/api/documents/{failed_course_with_file.id}/retry", headers=owner_headers)
    assert response.status_code == 202
    body = response.json()
    assert body["document_id"] == failed_course_with_file.id
    assert body["status"] == "processing"
    assert body["job_id"]
    assert len(scheduled) == 1


def test_other_user_cannot_retry_course(client, failed_course_with_file, other_headers):
    response = client.post(f"/api/documents/{failed_course_with_file.id}/retry", headers=other_headers)
    assert response.status_code == 404


def test_processing_or_ready_course_rejects_retry(client, ready_course, owner_headers):
    response = client.post(f"/api/documents/{ready_course.id}/retry", headers=owner_headers)
    assert response.status_code == 409


def test_retry_requires_saved_source_file(client, failed_course_without_file, owner_headers):
    response = client.post(f"/api/documents/{failed_course_without_file.id}/retry", headers=owner_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SOURCE_FILE_MISSING"
```

- [ ] **Step 2: Run the retry tests and verify route failures**

Run: `uv run --project . pytest tests/test_document_retry.py -q`

Expected: FAIL with `404` for the new retry/job routes.

- [ ] **Step 3: Extract saved-file discovery into the document processor**

```python
def list_saved_course_files(self, course_id: str) -> List[str]:
    course_dir = os.path.join(settings.UPLOAD_DIR, course_id)
    if not os.path.isdir(course_dir):
        return []
    return [
        os.path.join(course_dir, entry)
        for entry in sorted(os.listdir(course_dir))
        if os.path.isfile(os.path.join(course_dir, entry))
    ]
```

Use the same method from `scripts/reembed_courses.py` to remove its duplicate directory walk.

- [ ] **Step 4: Make `process_course()` update structured course/job state**

Change the signature to:

```python
def process_course(
    self,
    course_id: str,
    file_paths: List[str],
    db_session_factory=None,
    job_id: Optional[str] = None,
) -> ProcessingResult:
```

At start, mark the job running. Before extraction, call cached provider preflight; if unavailable, raise `ProviderRequestError` using its failure. On success, clear every failure field and mark the job succeeded. On `ProviderRequestError`, store `paused_due_to_quota` for key-limit/credit errors or `failed` for other failures, set `failure_stage="embedding_failed"`, persist only `failure.user_message` publicly, persist `technical_message` privately, and mark the job failed. Extraction exceptions must use `DOCUMENT_TEXT_EXTRACTION_FAILED`, `failure_stage="extraction_failed"`, and `recommended_action="upload_clearer_pdf"`.

- [ ] **Step 5: Create a processing job during upload**

After committing the new course:

```python
job = create_job(
    db,
    course_id=course_id,
    user_id=current_user.id,
    job_type="preprocess",
)
background_tasks.add_task(
    processor.process_course,
    course_id,
    saved_file_paths,
    SessionLocal,
    job.id,
)
```

Return `job_id=job.id` in the upload response.

- [ ] **Step 6: Implement retry and job-status routes**

The retry route must load the course using existing ownership helpers, accept only `failed` or `paused_due_to_quota`, ensure no queued/running preprocess job exists for that course, discover saved files, reset course status to `processing`, create a new job, and schedule `process_course()` through `BackgroundTasks`. Put the single `background_tasks.add_task(processor.process_course, course_id, file_paths, SessionLocal, job_id)` call inside `_schedule_processing()` and use that helper from both upload and retry, matching the test seam in Step 1. The job endpoint must return `404` unless `job.user_id == current_user.id` or the requester is admin.

- [ ] **Step 7: Register the documents router and expose safe fields**

Add `documents` to `app.routers`, register it in `main.py`, and return `failure_stage`, `error_code`, `can_retry`, `recommended_action`, and latest `job_id` from course status. Never return `technical_error` from course or job routes.

- [ ] **Step 8: Run the complete document path tests**

Run:

```powershell
uv run --project . pytest tests/test_document_retry.py tests/test_course_and_upload.py tests/test_vector_store_and_processor.py -q
```

Expected: PASS; duplicate retry is `409`, ownership is enforced, and the saved file is reused.

- [ ] **Step 9: Commit document retry**

```powershell
git add src/backend/app/routers/documents.py src/backend/app/routers/upload.py src/backend/app/routers/courses.py src/backend/app/services/document_processor.py src/backend/main.py src/backend/tests/test_document_retry.py
git commit -m "feat: retry failed document indexing without re-upload"
```

---

### Task 6: Actionable Failed-Course UI and Retry Polling

**Files:**
- Modify: `src/frontend/src/lib/types.ts:31-58`
- Modify: `src/frontend/src/lib/api.ts:180-330`
- Create: `src/frontend/src/lib/api.test.ts`
- Modify: `src/frontend/src/app/course/[id]/page.tsx:1-240`
- Modify: `src/frontend/src/app/course/[id]/page.test.tsx`
- Modify: `src/frontend/e2e/visual-brand.spec.ts`

**Interfaces:**
- Consumes: structured status from Task 5 and `POST /api/documents/{course_id}/retry`.
- Produces: `apiRetryDocument(courseId)`, `apiGetJob(jobId)`, and a retryable error panel that resumes existing course polling.

- [ ] **Step 1: Write failing UI tests for quota and retry**

Extend the API mock with `apiRetryDocument` and add:

```tsx
it("explains provider quota failure without blaming the PDF", async () => {
  vi.mocked(apiGetCourseStatus).mockResolvedValue({
    course_id: "course-1",
    status: "paused_due_to_quota",
    error: "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
    error_code: "OPENROUTER_KEY_LIMIT_EXCEEDED",
    can_retry: true,
    recommended_action: "restore_provider_quota",
  });
  render(<CourseDashboardPage />);
  expect(await screen.findByText("Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.")).toBeVisible();
  expect(screen.queryByText(/PDF.*scan/u)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Thử lập chỉ mục lại" })).toBeEnabled();
});
```

Add a user-event test that clicks the button, expects `apiRetryDocument("course-1")`, shows `Đang xử lý`, and resumes the existing 3–5 second course-status polling.

In `src/frontend/src/lib/api.test.ts`, mock `global.fetch` to reject with `TypeError("Failed to fetch")` and assert every `apiFetch` caller receives the stable public message `Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.` with code `NETWORK_UNAVAILABLE`; assert neither the returned error nor rendered course page contains `Failed to fetch`. Add a second test showing an `AbortError` from component unmount stays silent and is not converted into a visible error banner.

- [ ] **Step 2: Run the page test and verify missing types/API/UI failures**

Run: `npm test -- --run 'src/app/course/[id]/page.test.tsx'`

Expected: FAIL because the response type and retry function do not exist.

- [ ] **Step 3: Add frontend contracts and API clients**

```typescript
export type DocumentFailureCode =
  | "OPENROUTER_KEY_INVALID"
  | "OPENROUTER_KEY_LIMIT_EXCEEDED"
  | "OPENROUTER_CREDITS_EXHAUSTED"
  | "OPENROUTER_ACCESS_DENIED"
  | "OPENROUTER_RATE_LIMITED"
  | "OPENROUTER_UNAVAILABLE"
  | "OPENROUTER_TIMEOUT"
  | "DOCUMENT_TEXT_EXTRACTION_FAILED"
  | "OPENROUTER_REQUEST_FAILED";

export interface DocumentRetryResponse {
  document_id: string;
  status: "processing";
  stage: "extracting";
  progress: number;
  message: string;
  job_id: string;
}
```

Add the structured optional fields to `CourseStatusResponse`, then implement:

```typescript
export function apiRetryDocument(courseId: string): Promise<DocumentRetryResponse> {
  return apiFetch(`/api/documents/${encodeURIComponent(courseId)}/retry`, {
    method: "POST",
  });
}
```

Wrap the single shared `fetch()` call in `apiFetch`: preserve structured HTTP errors, rethrow `AbortError`, and convert network `TypeError` into an exported `ApiNetworkError` with code `NETWORK_UNAVAILABLE` and the Vietnamese public message from Step 1. Do not match only the English browser string; classification must use the error type so Chromium, Firefox, proxies, and CORS failures behave consistently.

- [ ] **Step 4: Render the retryable error state**

When normalized status is `error`, render the backend `error` text and choose the action from `recommended_action`. `restore_provider_quota` copy must say the uploaded file is preserved and an administrator must restore AI capacity before retrying. A `NETWORK_UNAVAILABLE` error must render the stable connection message and a retry button, never `Failed to fetch`. The retry button must disable while the request is in flight and call existing `handleRefetch()` after success.

- [ ] **Step 5: Add a Playwright mocked recovery journey**

Mock first status as `paused_due_to_quota`, mock retry as `202` with a job id, then return `processing` followed by `ready`. Assert the UI never shows scan/PDF corruption copy, the retry request fires once, and the ready Study Pack tabs appear without upload navigation. Add a separate browser journey that aborts the `/api/course/{id}/status` request; assert the stable Vietnamese connection message and retry control appear and the literal `Failed to fetch` is absent from the page.

- [ ] **Step 6: Run frontend unit and focused browser tests**

Run:

```powershell
npm test -- --run 'src/app/course/[id]/page.test.tsx'
npm test -- --run src/lib/api.test.ts
npx playwright test --project=chromium --grep "document retry"
```

Expected: PASS with one retry request and a final ready state.

- [ ] **Step 7: Commit retry UX**

```powershell
git add src/frontend/src/lib/types.ts src/frontend/src/lib/api.ts src/frontend/src/lib/api.test.ts 'src/frontend/src/app/course/[id]/page.tsx' 'src/frontend/src/app/course/[id]/page.test.tsx' src/frontend/e2e/visual-brand.spec.ts
git commit -m "feat: add actionable document retry experience"
```

---

### Task 7: Recovery Runbook and Release Gates

**Files:**
- Modify: `README.md`
- Modify: `docs/api_contract.md`
- Modify: `.env.example`

**Interfaces:**
- Documents the exact operator and user recovery flow delivered by Tasks 1–6.

- [ ] **Step 1: Update the API contract to match code exactly**

Document `paused_due_to_quota`, all public `error_code` values, `can_retry`, `recommended_action`, upload `job_id`, `GET /api/jobs/{job_id}`, `POST /api/documents/{course_id}/retry`, and admin-only `GET /api/admin/provider-health`. State that `technical_error` is stored server-side and never returned to regular users.

- [ ] **Step 2: Add the OpenRouter recovery runbook**

Include these commands without printing the key:

```powershell
docker compose exec backend python3 -c "import os,httpx,json; d=httpx.get('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},timeout=20).json()['data']; print(json.dumps({k:d.get(k) for k in ['limit','limit_remaining','usage','limit_reset','expires_at']},indent=2))"
docker compose up -d --no-deps --force-recreate backend
docker compose up -d --wait
```

Explain that `limit_remaining=0` plus `limit_reset=null` requires raising/removing the key limit or replacing the key; waiting does not recover it.

- [ ] **Step 3: Run all release gates**

Backend:

```powershell
Set-Location src/backend
uv run --project . ruff check .
uv run --project . pytest tests
```

Frontend:

```powershell
Set-Location ../frontend
npm run audit:brand
npm test -- --run
npm run lint
npm run build
npm run test:visual
```

Expected: all commands exit `0`; existing documented lint warnings may remain but no new error/warning may be introduced.

- [ ] **Step 4: Run a live Docker recovery smoke test**

With a test OpenRouter key whose remaining limit is positive: upload one text-layer PDF, wait for `ready`, force the fake/provider test adapter to emit a key-limit `403`, verify the saved course becomes `paused_due_to_quota`, restore provider availability, press retry, and verify the same course id reaches `ready` without a second upload. Confirm a different user gets `404` from both job and retry endpoints.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md docs/api_contract.md .env.example
git commit -m "docs: add OpenRouter recovery runbook"
```

## Plan A Completion Criteria

- A `403 Key limit exceeded` causes one embedding attempt, not three.
- The user sees a quota/provider message, never a false scan/PDF diagnosis.
- The original upload remains available and can be re-indexed under the same course id.
- Retry and job status enforce ownership and do not leak technical provider details.
- Provider capacity is visible only to admins and is not part of container readiness.
- All backend, frontend, browser, and Docker recovery gates pass.
