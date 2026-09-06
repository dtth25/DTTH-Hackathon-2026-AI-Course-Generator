from __future__ import annotations

import threading
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import Settings, settings
from app.jobs.tasks import execute_job
from app.models.course import Course
from app.models.processing_job import ProcessingJob
from app.models.provider_call import BookBudget, ProviderCall
from app.models.source_plan import SourcePlanRecord
from app.schemas.generator_output import (
    BookChapterContent,
    BookChapterPlan,
    BookObjectiveCoverage,
    BookOutline,
    BookSection,
)
from app.schemas.source_plan import SourceObjective, SourcePlan, SourcePlanUnit
from app.services import database
from app.services.book_model_policy import BookModelPolicy
from app.services.generator import Generator
from app.services.job_service import create_job
from app.services.llm import LLMService
from app.services.provider_guard import ProviderCapacityWait, ProviderGuard, ProviderPermit
from app.services.provider_tokens import RequestEstimate


class _FakeBookLLM(LLMService):
    def __init__(self, *, delays: dict[int, float] | None = None):
        self.model = BookModelPolicy.default().model
        self.book_policy = None
        self._test_mode = True
        self.client = None
        self.calls: list[str] = []
        self.started: list[int] = []
        self.finished: list[int] = []
        self.active = 0
        self.maximum_active = 0
        self.lock = threading.Lock()
        self.delays = delays or {}

    def with_book_policy(self, policy):
        clone = self
        clone.book_policy = policy
        clone.model = policy.model
        return clone

    @staticmethod
    def _estimate(output=100):
        policy = BookModelPolicy.default()
        return RequestEstimate(
            input_bound=100,
            output_bound=output,
            input_price=policy.input_price_ceiling,
            output_price=policy.output_price_ceiling,
            fixed_fees=Decimal("0"),
            method="test",
            revision="test",
            framing_allowance=0,
            calibration_state="test",
        )

    def estimate_source_plan_request(self, *_args, **_kwargs):
        return self._estimate(100)

    def estimate_book_outline_request(self, *_args, **_kwargs):
        return self._estimate(100)

    def estimate_book_chapter_request(
        self,
        _book_title,
        _plan,
        _total,
        _context,
        _detail_level,
        max_output_tokens,
        reasoning_tokens=0,
        *_args,
        **_kwargs,
    ):
        return self._estimate(max_output_tokens + reasoning_tokens)

    def generate_book_outline(self, *_args, **_kwargs):
        self.calls.append("outline")
        return BookOutline(
            title="Scheduled Book",
            summary="Summary",
            chapters=[
                BookChapterPlan(
                    chapter_number=index,
                    chapter_title=f"Unit {index}",
                    description=f"Explain unit {index}",
                    retrieval_query=f"unit {index}",
                    planned_sections=[f"Concept {index}"],
                )
                for index in range(1, 5)
            ],
        )

    def generate_book_chapter(
        self, _title, plan, _total, _context, _detail, valid_chunk_ids, **kwargs
    ):
        number = plan.chapter_number
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.started.append(number)
        time.sleep(self.delays.get(number, 0.02))
        try:
            required = kwargs["required_objectives"]
            objective_id, objective = next(iter(required.items()))
            with self.lock:
                self.calls.append(f"chapter-{number}")
                self.finished.append(number)
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
        finally:
            with self.lock:
                self.active -= 1


def _source_plan() -> SourcePlan:
    return SourcePlan(
        revision=1,
        source_digest="d" * 64,
        objectives=[
            SourceObjective(
                id=f"o{index}",
                text=f"Explain unit {index}",
                evidence_ids=[f"e{index}"],
            )
            for index in range(1, 5)
        ],
        units=[
            SourcePlanUnit(
                id=f"u{index}",
                title=f"Unit {index}",
                objective_ids=[f"o{index}"],
                evidence_ids=[f"e{index}"],
            )
            for index in range(1, 5)
        ],
    )


def _build_generator(monkeypatch, tmp_path, course_id: str, fake: _FakeBookLLM):
    plan = _source_plan()
    with database.SessionLocal.begin() as db:
        db.add(Course(id=course_id, user_id="owner", filenames=["source.txt"], status="ready"))
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
    generator = Generator(None, fake, {"book": fake})
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
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
    return generator


@pytest.mark.parametrize(("cap", "expected_max"), [(1, 1), (2, 2), (4, 4)])
def test_book_chapter_scheduler_respects_configured_cap_and_keeps_outline_order(
    monkeypatch, tmp_path, cap, expected_max
):
    monkeypatch.setattr(settings, "BOOK_CHAPTER_CONCURRENCY", cap)
    fake = _FakeBookLLM(delays={1: 0.05, 2: 0.04, 3: 0.03, 4: 0.01})
    generator = _build_generator(monkeypatch, tmp_path, f"course-{cap}", fake)
    version_id = generator.prepare_artifact_version(
        f"course-{cap}", "book", {"detail_level": "Tiêu chuẩn"}
    )

    result = generator.generate_book(
        f"course-{cap}", version_id=version_id, detail_level="Tiêu chuẩn"
    )

    assert result is not None
    assert fake.maximum_active == expected_max
    assert [chapter.chapter_title for chapter in result.chapters] == [
        "Unit 1",
        "Unit 2",
        "Unit 3",
        "Unit 4",
    ]
    assert set(fake.finished) == {1, 2, 3, 4}


def test_bounded_and_sequential_book_outputs_have_identical_schema_and_grounding(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "BOOK_CHAPTER_CONCURRENCY", 1)
    sequential_llm = _FakeBookLLM()
    sequential = _build_generator(monkeypatch, tmp_path / "seq", "course-seq", sequential_llm)
    sequential_version = sequential.prepare_artifact_version(
        "course-seq", "book", {"detail_level": "Tiêu chuẩn"}
    )
    sequential_output = sequential.generate_book(
        "course-seq", version_id=sequential_version, detail_level="Tiêu chuẩn"
    )

    monkeypatch.setattr(settings, "BOOK_CHAPTER_CONCURRENCY", 4)
    bounded_llm = _FakeBookLLM(delays={1: 0.04, 2: 0.03, 3: 0.02, 4: 0.01})
    bounded = _build_generator(monkeypatch, tmp_path / "bounded", "course-bounded", bounded_llm)
    bounded_version = bounded.prepare_artifact_version(
        "course-bounded", "book", {"detail_level": "Tiêu chuẩn"}
    )
    bounded_output = bounded.generate_book(
        "course-bounded", version_id=bounded_version, detail_level="Tiêu chuẩn"
    )

    assert bounded_output.model_dump(mode="json") == sequential_output.model_dump(mode="json")
    assert bounded_llm.maximum_active == 4


def test_generation_capacity_wait_is_short_fair_and_deduplicates_waiters():
    clock_value = 1_800_000_000.0

    def clock():
        return clock_value

    guard = ProviderGuard(
        redis_client=None,
        settings_obj=SimpleNamespace(
            ENVIRONMENT="local",
            JOB_QUEUE_PROVIDER="inline",
            OPENROUTER_MAX_IN_FLIGHT=1,
            OPENROUTER_RPM=60,
            OPENROUTER_CIRCUIT_FAILURES=5,
            OPENROUTER_CIRCUIT_WINDOW_SECONDS=60,
            OPENROUTER_CIRCUIT_OPEN_SECONDS=30,
            PROVIDER_CAPACITY_WAIT_MIN_SECONDS=1,
            PROVIDER_CAPACITY_WAIT_MAX_SECONDS=1,
            PROVIDER_CAPACITY_WAITER_TTL_SECONDS=15,
        ),
        clock=clock,
    )
    first = guard.acquire("generation", owner_key="u1", job_key="j1", request_id="u1-r1")
    with pytest.raises(ProviderCapacityWait) as waiting:
        guard.acquire("generation", owner_key="u2", job_key="j2", request_id="u2-r1")
    assert waiting.value.reason == "inflight"
    assert waiting.value.retry_after == 1
    with pytest.raises(ProviderCapacityWait):
        guard.acquire("generation", owner_key="u2", job_key="j2", request_id="u2-r1")
    assert guard._local_job_requests["generation"][("u2", "j2")] == ["u2-r1"]

    guard.release(first)
    with pytest.raises(ProviderCapacityWait) as fairness:
        guard.acquire("generation", owner_key="u1", job_key="j1", request_id="u1-r2")
    assert fairness.value.reason == "fairness"
    second = guard.acquire("generation", owner_key="u2", job_key="j2", request_id="u2-r1")
    assert isinstance(second, ProviderPermit)


def test_capacity_continuation_does_not_spend_or_consume_failure_attempts(
    monkeypatch,
):
    course_id = "capacity-course"
    version_id = "book-v1"
    with database.SessionLocal.begin() as db:
        db.add(Course(id=course_id, user_id="owner", filenames=["source.txt"], status="ready"))
        budget = BookBudget(
            id="budget",
            course_id=course_id,
            user_id="owner",
            version_id=version_id,
            state="active",
            model_policy=BookModelPolicy.default().model_dump(mode="json"),
        )
        db.add(budget)
    with database.SessionLocal() as db:
        job = create_job(
            db,
            course_id=course_id,
            user_id="owner",
            job_type="book",
            payload_json={
                "course_id": course_id,
                "version_id": version_id,
                "budget_id": "budget",
            },
        )
        job_id = job.id

    generator = SimpleNamespace(
        generate_book=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProviderCapacityWait(2, reason="fairness", request_id="waiter")
        )
    )
    monkeypatch.setattr("app.jobs.tasks.get_generator", lambda: generator)

    delivery = execute_job(job_id, worker_id="worker-a")

    assert delivery is not None
    assert delivery.queue_name == "generation"
    assert delivery.countdown <= 2
    with database.SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == "retry_scheduled"
        assert job.attempts == 1
        assert job.failure_attempts == 0
        assert job.product_stage == "capacity_wait"
        assert job.next_attempt_at is not None
        assert db.query(ProviderCall).count() == 0


def test_book_chapter_concurrency_setting_defaults_and_range():
    configured = Settings(
        DATABASE_URL="sqlite:///./test.db",
        JWT_SECRET="test-secret",
        OPENROUTER_API_KEY="test-key",
    )

    assert configured.BOOK_CHAPTER_CONCURRENCY == 2
    assert Settings(
        DATABASE_URL="sqlite:///./test.db",
        JWT_SECRET="test-secret",
        OPENROUTER_API_KEY="test-key",
        BOOK_CHAPTER_CONCURRENCY=4,
    ).BOOK_CHAPTER_CONCURRENCY == 4
    with pytest.raises(ValueError):
        Settings(
            DATABASE_URL="sqlite:///./test.db",
            JWT_SECRET="test-secret",
            OPENROUTER_API_KEY="test-key",
            BOOK_CHAPTER_CONCURRENCY=5,
        )
