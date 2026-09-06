import json
from datetime import datetime, timedelta
import pytest

from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.provider_call import BookBudget, ProviderCall
from app.models.source_plan import SourcePlanRecord
from app.schemas.generator_output import (
    BookChapterContent,
    BookChapterPlan,
    BookOutline,
    BookSection,
)
from app.services import database
from app.services.book_checkpoint import (
    BOOK_PROMPT_REVISION,
    BookCheckpointStore,
    CheckpointIdentity,
    canonical_digest,
    checkpoint_key,
    checkpoint_write_fence,
    plan_digest,
    remove_book_checkpoints,
)
from app.schemas.generator_output import BookObjectiveCoverage
from app.schemas.source_plan import SourceObjective, SourcePlan, SourcePlanUnit
from app.services.book_model_policy import BookModelPolicy
from app.services.generator import Generator
from app.services.llm import LLMService
from app.services.provider_tokens import RequestEstimate
from app.core.config import settings
from app.services.provider_errors import ProviderErrorCode, classify_openrouter_error
from app.schemas.generation import BookGenerateRequest
from fastapi import BackgroundTasks
from types import SimpleNamespace


def _metadata(version_id):
    return json.dumps(
        {
            "study_pack": {
                "artifacts": {
                    "book": {
                        "active": None,
                        "versions": {version_id: {"status": "processing"}},
                    }
                }
            }
        }
    )


def _identity(course_id="cp-course", version_id="book-v1", budget_id="budget-v1"):
    return CheckpointIdentity(
        course_id=course_id,
        version_id=version_id,
        source_digest="a" * 64,
        source_plan_revision=1,
        model="google/gemini-2.5-flash",
        options_digest="b" * 64,
        prompt_revision=BOOK_PROMPT_REVISION,
        policy_revision="balanced-book-v1",
        budget_id=budget_id,
    )


def _outline():
    return BookOutline(
        title="Book",
        summary="Summary",
        chapters=[
            BookChapterPlan(
                chapter_number=1,
                chapter_title="Unit",
                description="Description",
                retrieval_query="unit",
                planned_sections=["Concept"],
            )
        ],
    )


def _chapter():
    return BookChapterContent(
        chapter_title="Unit",
        objectives=["Explain"],
        sections=[BookSection(title="Concept", content="Explain the concept")],
        key_points=["Concept"],
        review_questions=["Explain?"],
        source_chunk_ids=["e1"],
    )


def _seed_live(identity):
    with database.SessionLocal.begin() as db:
        db.add(
            Course(
                id=identity.course_id,
                user_id="owner",
                filenames=["source.txt"],
                metadata_json=_metadata(identity.version_id),
            )
        )
        db.add(
            BookBudget(
                id=identity.budget_id,
                course_id=identity.course_id,
                user_id="owner",
                version_id=identity.version_id,
            )
        )
        db.add(
            ProcessingJob(
                id="job-v1",
                course_id=identity.course_id,
                user_id="owner",
                job_type="book",
                status="running",
                worker_id="worker-v1",
                attempts=1,
                lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
                payload_json={
                    "version_id": identity.version_id,
                    "budget_id": identity.budget_id,
                },
            )
        )


def test_checkpoint_identity_invalidates_every_paid_content_dimension():
    base = checkpoint_key("a" * 64, "v1", "model", "b" * 64, "prompt", "policy")
    variants = {
        checkpoint_key("c" * 64, "v1", "model", "b" * 64, "prompt", "policy"),
        checkpoint_key("a" * 64, "v2", "model", "b" * 64, "prompt", "policy"),
        checkpoint_key("a" * 64, "v1", "other", "b" * 64, "prompt", "policy"),
        checkpoint_key("a" * 64, "v1", "model", "d" * 64, "prompt", "policy"),
        checkpoint_key("a" * 64, "v1", "model", "b" * 64, "new", "policy"),
        checkpoint_key("a" * 64, "v1", "model", "b" * 64, "prompt", "new"),
    }
    assert base not in variants
    assert len(variants) == 6


def test_provider_deadlines_and_timeout_classification_are_explicit():
    assert settings.OPENROUTER_CONNECT_TIMEOUT_SECONDS == 10
    assert settings.OPENROUTER_READ_TIMEOUT_SECONDS == 180
    assert settings.OPENROUTER_ATTEMPT_TIMEOUT_SECONDS == 180
    failure = classify_openrouter_error(TimeoutError("private timeout detail"))
    assert failure.code is ProviderErrorCode.TIMEOUT
    assert failure.automatic_retry is True


def test_identical_ready_cache_precedes_job_and_budget_admission(monkeypatch):
    from app.routers import generation

    with database.SessionLocal.begin() as db:
        db.add(
            Course(
                id="ready-cache-course",
                user_id="owner",
                filenames=["source.txt"],
                status="ready",
            )
        )
    fake = SimpleNamespace(
        find_ready_book_version=lambda *_args, **_kwargs: "ready-v1"
    )
    monkeypatch.setattr(generation, "get_generator", lambda: fake)
    monkeypatch.setattr(
        generation,
        "enqueue_generation_job",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("cache hit must precede admission")
        ),
    )
    with database.SessionLocal() as db:
        response = generation.generate_book(
            BackgroundTasks(),
            req=BookGenerateRequest(course_id="ready-cache-course"),
            course_id=None,
            user_prompt=None,
            detail_level=None,
            retry_version_id=None,
            new_variant=False,
            current_user=SimpleNamespace(id="owner", role="user"),
            db=db,
        )
    assert response.status == "ready"
    assert response.version_id == "ready-v1"
    assert response.job_id is None


def test_explicit_new_variant_bypasses_ready_cache(monkeypatch):
    from app.routers import generation

    with database.SessionLocal.begin() as db:
        db.add(
            Course(
                id="new-variant-course",
                user_id="owner",
                filenames=["source.txt"],
                status="ready",
            )
        )
    fake = SimpleNamespace(
        find_ready_book_version=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit new variant must bypass cache")
        )
    )
    monkeypatch.setattr(generation, "get_generator", lambda: fake)
    monkeypatch.setattr(
        generation,
        "enqueue_generation_job",
        lambda **_kwargs: (SimpleNamespace(id="job-new"), "version-new"),
    )
    with database.SessionLocal() as db:
        response = generation.generate_book(
            BackgroundTasks(),
            req=BookGenerateRequest(
                course_id="new-variant-course", new_variant=True
            ),
            course_id=None,
            user_prompt=None,
            detail_level=None,
            retry_version_id=None,
            new_variant=False,
            current_user=SimpleNamespace(id="owner", role="user"),
            db=db,
        )
    assert response.version_id == "version-new"
    assert response.job_id == "job-new"


def test_retry_job_payload_uses_persisted_options_prompt_and_budget(monkeypatch):
    from app.routers import generation

    course_id = "retry-payload-course"
    version_id = "retry-v1"
    stored_metadata = json.dumps(
        {
            "study_pack": {
                "artifacts": {
                    "book": {
                        "active": None,
                        "versions": {
                            version_id: {
                                "status": "error",
                                "options": {"detail_level": "Chuyên sâu"},
                                "user_prompt": "original prompt",
                            }
                        },
                    }
                }
            }
        }
    )
    with database.SessionLocal.begin() as db:
        course = Course(
            id=course_id,
            user_id="owner",
            filenames=["source.txt"],
            metadata_json=stored_metadata,
        )
        db.add(course)
        db.add(
            BookBudget(
                id="retry-budget",
                course_id=course_id,
                user_id="owner",
                version_id=version_id,
            )
        )
    monkeypatch.setattr(generation, "enforce_job_admission", lambda *_args: None)
    monkeypatch.setattr(
        generation, "reserve_version_or_raise", lambda *_args, **_kwargs: version_id
    )
    monkeypatch.setattr(generation, "dispatch_persisted_job", lambda *_args: None)
    with database.SessionLocal() as db:
        course = db.get(Course, course_id)
        job, _ = generation.enqueue_generation_job(
            background_tasks=BackgroundTasks(),
            db=db,
            course=course,
            generator=SimpleNamespace(),
            job_type="book",
            artifact="book",
            options={"detail_level": "Tiêu chuẩn"},
            payload_options={
                "detail_level": "Tiêu chuẩn",
                "user_prompt": "conflicting default",
            },
            retry_version_id=version_id,
        )
        db.refresh(job)
        assert job.payload_json["detail_level"] == "Chuyên sâu"
        assert job.payload_json["user_prompt"] == "original prompt"
        assert job.payload_json["budget_id"] == "retry-budget"


def test_atomic_typed_outline_manifest_and_chapter_survive_retry(tmp_path):
    identity = _identity()
    _seed_live(identity)
    store = BookCheckpointStore(str(tmp_path), identity)
    fence = checkpoint_write_fence(
        database.SessionLocal,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    outline = _outline()
    allocation = canonical_digest([{"unit_id": "u1"}])
    assert store.save_outline(outline, ["e1"], fence)
    assert store.save_manifest(
        outline_digest=canonical_digest(outline.model_dump(mode="json")),
        allocation_digest=allocation,
        plans=outline.chapters,
        evidence_ids=["e1"],
        fence=fence,
    )
    assert store.save_chapter(
        0,
        _chapter(),
        outline_digest=canonical_digest(outline.model_dump(mode="json")),
        allocation_digest=allocation,
        expected_plan_digest=plan_digest(outline.chapters[0]),
        evidence_ids=["e1"],
        fence=fence,
    )
    assert store.load_outline(["e1"]) == outline
    assert store.load_chapter(
        0,
        outline_digest=canonical_digest(outline.model_dump(mode="json")),
        allocation_digest=allocation,
        expected_plan_digest=plan_digest(outline.chapters[0]),
        valid_evidence_ids=["e1"],
    ) == _chapter()

    (store.directory / "chapter-1.json").write_text("{broken", encoding="utf-8")
    assert store.load_chapter(
        0,
        outline_digest=canonical_digest(outline.model_dump(mode="json")),
        allocation_digest=allocation,
        expected_plan_digest=plan_digest(outline.chapters[0]),
        valid_evidence_ids=["e1"],
    ) is None


def test_stale_cancelled_or_deleted_owner_cannot_replace_checkpoint(tmp_path):
    identity = _identity(course_id="fenced-course", budget_id="fenced-budget")
    _seed_live(identity)
    store = BookCheckpointStore(str(tmp_path), identity)
    live_fence = checkpoint_write_fence(
        database.SessionLocal,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    assert store.save_outline(_outline(), ["e1"], live_fence)
    original = (store.directory / "outline.json").read_bytes()

    with database.SessionLocal.begin() as db:
        db.get(ProcessingJob, "job-v1").cancel_requested = True
    changed = _outline().model_copy(update={"title": "replacement"})
    assert store.save_outline(changed, ["e1"], live_fence) is False
    assert (store.directory / "outline.json").read_bytes() == original

    with database.SessionLocal.begin() as db:
        db.get(ProcessingJob, "job-v1").cancel_requested = False
        db.get(Course, identity.course_id).is_deleted = True
    assert store.save_outline(changed, ["e1"], live_fence) is False
    assert (store.directory / "outline.json").read_bytes() == original


@pytest.mark.parametrize(
    "invalidator",
    ["stale-attempt", "expired-lease", "payload-version", "payload-budget", "version-removed"],
)
def test_checkpoint_fence_rejects_stale_identity_dimensions(tmp_path, invalidator):
    identity = _identity(course_id=f"fence-{invalidator}", budget_id=f"budget-{invalidator}")
    _seed_live(identity)
    store = BookCheckpointStore(str(tmp_path), identity)
    fence = checkpoint_write_fence(
        database.SessionLocal,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    assert store.save_outline(_outline(), ["e1"], fence)
    original = (store.directory / "outline.json").read_bytes()
    changed = _outline().model_copy(update={"title": "replacement"})
    with database.SessionLocal.begin() as db:
        job = db.get(ProcessingJob, "job-v1")
        if invalidator == "stale-attempt":
            job.attempts = 2
        elif invalidator == "expired-lease":
            job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        elif invalidator == "payload-version":
            job.payload_json = {**job.payload_json, "version_id": "other"}
        elif invalidator == "payload-budget":
            job.payload_json = {**job.payload_json, "budget_id": "other"}
        else:
            course = db.get(Course, identity.course_id)
            metadata = json.loads(course.metadata_json)
            del metadata["study_pack"]["artifacts"]["book"]["versions"][identity.version_id]
            course.metadata_json = json.dumps(metadata)
    assert store.save_outline(changed, ["e1"], fence) is False
    assert (store.directory / "outline.json").read_bytes() == original


def test_checkpoint_promotion_is_restored_when_database_commit_fails(tmp_path):
    identity = _identity(course_id="commit-fault-course", budget_id="commit-fault-budget")
    _seed_live(identity)
    store = BookCheckpointStore(str(tmp_path), identity)
    live_fence = checkpoint_write_fence(
        database.SessionLocal,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    assert store.save_outline(_outline(), ["e1"], live_fence)
    original = (store.directory / "outline.json").read_bytes()

    class CommitFaultSession:
        def __init__(self):
            self.session = database.SessionLocal()

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            raise RuntimeError("injected commit fault")

    fault_session_created = False

    def commit_fault_factory():
        nonlocal fault_session_created
        if not fault_session_created:
            fault_session_created = True
            return CommitFaultSession()
        return database.SessionLocal()

    failed_fence = checkpoint_write_fence(
        commit_fault_factory,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    changed = _outline().model_copy(update={"title": "replacement"})
    with pytest.raises(RuntimeError, match="injected commit fault"):
        store.save_outline(changed, ["e1"], failed_fence)
    assert (store.directory / "outline.json").read_bytes() == original


def test_failed_checkpoint_recovery_cannot_overwrite_newer_fenced_write(tmp_path):
    identity = _identity(course_id="recovery-race-course", budget_id="recovery-race-budget")
    _seed_live(identity)
    store = BookCheckpointStore(str(tmp_path), identity)
    live_fence = checkpoint_write_fence(
        database.SessionLocal,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    assert store.save_outline(_outline(), ["e1"], live_fence)
    newer = _outline().model_copy(update={"title": "newer committed checkpoint"})

    class InterleavedCommitFaultSession:
        def __init__(self):
            self.session = database.SessionLocal()
            self.recovered = False

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            raise RuntimeError("injected commit fault")

        def rollback(self):
            self.session.rollback()
            if not self.recovered:
                self.recovered = True
                assert store.save_outline(newer, ["e1"], live_fence)

    fault_session_created = False

    def interleaved_fault_factory():
        nonlocal fault_session_created
        if not fault_session_created:
            fault_session_created = True
            return InterleavedCommitFaultSession()
        return database.SessionLocal()

    failed_fence = checkpoint_write_fence(
        interleaved_fault_factory,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    failed = _outline().model_copy(update={"title": "failed checkpoint"})
    with pytest.raises(RuntimeError, match="injected commit fault"):
        store.save_outline(failed, ["e1"], failed_fence)
    assert store.load_outline(["e1"]).title == "newer committed checkpoint"


@pytest.mark.parametrize("has_prior_checkpoint", [True, False])
def test_failed_recovery_preserves_newer_identical_checkpoint(
    tmp_path, has_prior_checkpoint
):
    identity = _identity(
        course_id=f"identical-race-{has_prior_checkpoint}",
        budget_id=f"identical-budget-{has_prior_checkpoint}",
    )
    _seed_live(identity)
    store = BookCheckpointStore(str(tmp_path), identity)
    live_fence = checkpoint_write_fence(
        database.SessionLocal,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    if has_prior_checkpoint:
        prior = _outline().model_copy(update={"title": "older checkpoint"})
        assert store.save_outline(prior, ["e1"], live_fence)
    identical = _outline().model_copy(update={"title": "identical new checkpoint"})

    class IdenticalInterleavedFaultSession:
        def __init__(self):
            self.session = database.SessionLocal()
            self.interleaved = False

        def __getattr__(self, name):
            return getattr(self.session, name)

        def commit(self):
            raise RuntimeError("injected identical commit fault")

        def rollback(self):
            self.session.rollback()
            if not self.interleaved:
                self.interleaved = True
                assert store.save_outline(identical, ["e1"], live_fence)

    fault_session_created = False

    def fault_factory():
        nonlocal fault_session_created
        if not fault_session_created:
            fault_session_created = True
            return IdenticalInterleavedFaultSession()
        return database.SessionLocal()

    failed_fence = checkpoint_write_fence(
        fault_factory,
        identity,
        job_id="job-v1",
        worker_id="worker-v1",
        attempt_number=1,
    )
    with pytest.raises(RuntimeError, match="injected identical commit fault"):
        store.save_outline(identical, ["e1"], failed_fence)
    assert store.load_outline(["e1"]).title == "identical new checkpoint"

def test_version_cleanup_removes_only_its_private_checkpoint_tree(tmp_path):
    first = BookCheckpointStore(str(tmp_path), _identity(version_id="v1"))
    second = BookCheckpointStore(
        str(tmp_path), _identity(version_id="v2", budget_id="budget-v2")
    )
    first.directory.mkdir(parents=True)
    second.directory.mkdir(parents=True)
    (first.directory / "marker").write_text("one", encoding="utf-8")
    (second.directory / "marker").write_text("two", encoding="utf-8")
    remove_book_checkpoints(str(tmp_path), "cp-course", "v1")
    assert not first.directory.exists()
    assert second.directory.exists()


def test_failed_book_resume_calls_only_unfinished_chapters(
    tmp_path, monkeypatch
):
    course_id = "resume-course"
    with database.SessionLocal.begin() as db:
        db.add(
            Course(
                id=course_id,
                user_id="owner",
                filenames=["source.txt"],
                status="ready",
            )
        )

    class FakeBookLLM(LLMService):
        def __init__(self):
            self.model = BookModelPolicy.default().model
            self.book_policy = None
            self._test_mode = True
            self.calls = []
            self.fail_chapter_three = True
            self.soft_chapter_three = False
            self.client = None

        def with_book_policy(self, policy):
            self.book_policy = policy
            self.model = policy.model
            return self

        @staticmethod
        def _estimate(output=1_000):
            return RequestEstimate(
                input_bound=100,
                output_bound=output,
                input_price=BookModelPolicy.default().input_price_ceiling,
                output_price=BookModelPolicy.default().output_price_ceiling,
                fixed_fees=BookModelPolicy.default().input_price_ceiling * 0,
                method="test",
                revision="test",
                framing_allowance=0,
                calibration_state="test",
            )

        def estimate_source_plan_request(self, *_args, **_kwargs):
            return self._estimate(2_400)

        def estimate_book_outline_request(self, *_args, **_kwargs):
            return self._estimate(_args[-2] + _args[-1])

        def estimate_book_chapter_request(self, *_args, **_kwargs):
            return self._estimate(_args[-3] + _args[-2])

        def generate_book_outline(self, *_args, **_kwargs):
            self.calls.append("outline")
            return BookOutline(
                title="Resume Book",
                summary="Summary",
                chapters=[
                    BookChapterPlan(
                        chapter_number=i,
                        chapter_title=f"Unit {i}",
                        description=f"Explain unit {i}",
                        retrieval_query=f"unit {i}",
                        planned_sections=[f"Concept {i}"],
                    )
                    for i in range(1, 5)
                ],
            )

        def generate_book_chapter(
            self, _title, plan, _total, _context, _detail, valid_chunk_ids, **kwargs
        ):
            self.calls.append(f"chapter-{plan.chapter_number}")
            if plan.chapter_number == 3 and self.fail_chapter_three:
                raise RuntimeError("deterministic chapter failure")
            if plan.chapter_number == 3 and self.soft_chapter_three:
                return self._call_openrouter_strict(
                    "private chapter request",
                    BookChapterContent,
                    lambda: None,
                    100,
                )
            required = kwargs["required_objectives"]
            objective_id, objective = next(iter(required.items()))
            return BookChapterContent(
                chapter_title=plan.chapter_title,
                objectives=[objective],
                sections=[BookSection(title="Concept", content=objective)],
                objective_coverage=[
                    BookObjectiveCoverage(
                        objective_id=objective_id,
                        objective=objective,
                        section_indices=[0],
                    )
                ],
                key_points=[objective],
                review_questions=["Explain?"],
                source_chunk_ids=list(valid_chunk_ids),
            )

    plan = SourcePlan(
        revision=1,
        source_digest="c" * 64,
        objectives=[
            SourceObjective(id=f"o{i}", text=f"Explain unit {i}", evidence_ids=[f"e{i}"])
            for i in range(1, 5)
        ],
        units=[
            SourcePlanUnit(
                id=f"u{i}",
                title=f"Unit {i}",
                objective_ids=[f"o{i}"],
                evidence_ids=[f"e{i}"],
            )
            for i in range(1, 5)
        ],
    )
    fake = FakeBookLLM()
    generator = Generator(None, fake, {"book": fake})
    monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    with database.SessionLocal.begin() as db:
        db.add(
            SourcePlanRecord(
                course_id=course_id,
                owner_id="owner",
                revision=plan.revision,
                source_digest=plan.source_digest,
                model=fake.model,
                prompt_revision="source-plan-v1",
                plan_json=plan.model_dump_json(),
            )
        )
    monkeypatch.setattr(
        generator,
        "_source_plan_inputs",
        lambda *_args, **_kwargs: (
            plan.source_digest,
            "source",
            ["e1", "e2", "e3", "e4"],
        ),
    )
    monkeypatch.setattr(generator, "_get_source_plan", lambda *_args, **_kwargs: plan)

    def plan_context(_course_id, _plan, *args, **kwargs):
        unit_ids = kwargs.get("unit_ids")
        selected = (
            list(plan.units)
            if kwargs.get("all_units")
            else [unit for unit in plan.units if unit.id in set(unit_ids or [])]
        )
        ids = list(
            kwargs.get("evidence_ids_override")
            or {evidence for unit in selected for evidence in unit.evidence_ids}
        )
        return "source", ids, selected

    monkeypatch.setattr(generator, "_plan_context", plan_context)
    monkeypatch.setattr(
        generator,
        "_generate_pdf_book",
        lambda _course, _book, artifact_dir: (
            __import__("pathlib").Path(artifact_dir).joinpath("book.pdf").write_bytes(b"pdf")
        ),
    )

    version_id = generator.prepare_artifact_version(
        course_id, "book", {"detail_level": "Tiêu chuẩn"}
    )
    assert generator.generate_book(
        course_id, version_id=version_id, detail_level="Tiêu chuẩn"
    ) is None
    assert fake.calls == ["outline", "chapter-1", "chapter-2", "chapter-3"]
    with database.SessionLocal.begin() as db:
        budget = db.query(BookBudget).filter_by(
            course_id=course_id, version_id=version_id
        ).one()
        original_budget_id = budget.id
        budget.spent = 55_000_000
        budget.reserved = 0

    from billiard.exceptions import SoftTimeLimitExceeded
    from app.jobs.tasks import execute_job
    from app.services.job_service import create_job
    from app.services.provider_usage import settle_call

    dispatched = []

    def soft_limited_provider(**_kwargs):
        dispatched.append(1)
        raise SoftTimeLimitExceeded()

    fake.fail_chapter_three = False
    fake.soft_chapter_three = True
    fake.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=soft_limited_provider))
    )
    monkeypatch.setattr(
        "app.services.provider_usage.verified_request_bound",
        lambda *_args: __import__("decimal").Decimal("0.001"),
    )
    generator.prepare_artifact_version(
        course_id,
        "book",
        {"detail_level": "ignored"},
        user_prompt="ignored",
        retry_version_id=version_id,
    )
    with database.SessionLocal() as db:
        job = create_job(
            db,
            course_id=course_id,
            user_id="owner",
            job_type="book",
            payload_json={
                "course_id": course_id,
                "version_id": version_id,
                "budget_id": original_budget_id,
                "detail_level": "Tiêu chuẩn",
                "user_prompt": "",
            },
        )
        job_id = job.id
    monkeypatch.setattr("app.jobs.tasks.get_generator", lambda: generator)
    delivery = execute_job(job_id, worker_id="soft-worker")
    assert delivery is not None
    assert delivery.queue_name == "generation"
    assert dispatched == [1]
    assert "chapter-3" in fake.calls[-2:]
    checkpoint_files = list(
        (__import__("pathlib").Path(tmp_path) / course_id / "artifacts" / "book" / ".checkpoints")
        .rglob("chapter-*.json")
    )
    assert len(checkpoint_files) in {2, 3}
    with database.SessionLocal.begin() as db:
        retry_job = db.get(ProcessingJob, job_id)
        assert retry_job.status == "retry_scheduled"
        retry_job.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        interrupted_call_id = db.query(ProviderCall).filter_by(job_id=job_id).one().call_id

    settle_call(interrupted_call_id, __import__("decimal").Decimal("0.001"))
    fake.soft_chapter_three = False
    result = execute_job(job_id, worker_id="retry-worker")
    assert result is None
    assert fake.calls.count("outline") == 1
    assert fake.calls.count("chapter-1") == 1
    assert fake.calls.count("chapter-2") == 1
    assert fake.calls.count("chapter-3") == 3
    assert fake.calls.count("chapter-4") == 1
    with database.SessionLocal() as db:
        assert db.get(ProcessingJob, job_id).status == "succeeded"
        assert db.query(BookBudget).filter_by(
            course_id=course_id, version_id=version_id
        ).one().id == original_budget_id
        assert generator.find_ready_book_version(
            course_id,
            {"detail_level": "Tiêu chuẩn"},
            "",
            db_session=db,
        ) == version_id

    with database.SessionLocal() as db:
        def remove_candidate_after_files(_course_id, _version_id):
            course = db.get(Course, course_id)
            metadata = json.loads(course.metadata_json)
            del metadata["study_pack"]["artifacts"]["book"]["versions"][version_id]
            course.metadata_json = json.dumps(metadata)
            db.flush()

        monkeypatch.setattr(
            generator,
            "_ready_cache_before_final_lock",
            remove_candidate_after_files,
        )
        assert generator.find_ready_book_version(
            course_id,
            {"detail_level": "Tiêu chuẩn"},
            "",
            db_session=db,
        ) is None

    monkeypatch.setattr(
        generator,
        "_ready_cache_before_final_lock",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        generator,
        "_source_plan_inputs",
        lambda *_args, **_kwargs: (
            "d" * 64,
            "changed",
            ["e1", "e2", "e3", "e4"],
        ),
    )
    with database.SessionLocal() as db:
        assert generator.find_ready_book_version(
            course_id,
            {"detail_level": "Tiêu chuẩn"},
            "",
            db_session=db,
        ) is None
