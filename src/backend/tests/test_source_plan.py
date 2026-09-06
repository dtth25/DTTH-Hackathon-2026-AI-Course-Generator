import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

from app.models.course import Course
from app.models.source_plan import SourcePlanRecord
from app.schemas.source_plan import (
    CanonicalEquation,
    GlossaryEntry,
    SourceObjective,
    SourcePlan,
    SourcePlanUnit,
)
from app.schemas.generator_output import (
    BookChapter,
    BookOutput,
    BookSection,
    QuizOption,
    QuizOutput,
    QuizQuestion,
    SlideItem,
    SlidesOutput,
    VidOutput,
    VidScene,
)
from app.services.database import Base, SessionLocal
from app.services.generator import Generator
from app.services.llm import LLMService
from app.services.public_errors import sanitize_public_payload
from app.services.source_plan import get_or_create_source_plan
from app.services.vector_store import Document, get_vector_store


EQUATION = r"\frac{a+b}{c+d}"


def _plan(revision: int, digest: str, evidence_ids=None) -> SourcePlan:
    evidence_ids = evidence_ids or ["evidence-1"]
    objectives = [
        SourceObjective(
            id=f"objective-{index}", text=f"Giải thích mục tiêu {index}", evidence_ids=evidence_ids
        )
        for index in range(1, 6)
    ]
    return SourcePlan(
        revision=revision,
        source_digest=digest,
        objectives=objectives,
        glossary=[
            GlossaryEntry(
                term="Tỉ số tổng",
                definition="Tổng ở tử số chia cho tổng ở mẫu số.",
                evidence_ids=evidence_ids,
            )
        ],
        equations=[
            CanonicalEquation(
                name="Tỉ số tổng", latex=EQUATION, meaning="Tỉ số hai tổng", evidence_ids=evidence_ids
            )
        ],
        units=[
            SourcePlanUnit(
                id=f"unit-{index}",
                title=f"Đơn vị {index}",
                objective_ids=[f"objective-{index}"],
                evidence_ids=evidence_ids,
            )
            for index in range(1, 6)
        ],
    )


def _ratio_plan() -> SourcePlan:
    plan = _plan(1, "a" * 64)
    plan.glossary[0].term = "Ratio"
    plan.glossary[0].definition = "Numerator divided by denominator."
    plan.equations[0].name = "Ratio"
    return plan


def test_get_or_create_is_atomic_owner_scoped_and_revisions_follow_source(tmp_path):
    database = tmp_path / "source-plan.db"
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add_all(
            [
                Course(id="course-a", user_id="owner-a", status="ready"),
                Course(id="course-b", user_id="owner-b", status="ready"),
            ]
        )
        db.commit()

    calls = 0
    calls_lock = Lock()

    def build(digest):
        def inner(revision):
            nonlocal calls
            with calls_lock:
                calls += 1
            return _plan(revision, digest)

        return inner

    def acquire(_):
        return get_or_create_source_plan(
            "course-a", "a" * 64, "selected-model", "prompt-v1",
            db_session_factory=factory, create=build("a" * 64),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        plans = list(pool.map(acquire, range(4)))
    assert calls == 1
    assert {plan.revision for plan in plans} == {1}

    changed = get_or_create_source_plan(
        "course-a", "b" * 64, "selected-model", "prompt-v1",
        db_session_factory=factory, create=build("b" * 64),
    )
    other_owner = get_or_create_source_plan(
        "course-b", "a" * 64, "selected-model", "prompt-v1",
        db_session_factory=factory, create=build("a" * 64),
    )
    assert changed.revision == 2
    assert other_owner.revision == 1
    assert calls == 3


def test_plan_history_survives_actual_artifact_binding(tmp_path):
    course_id = "plan-binding-race"
    engine = create_engine(
        f"sqlite:///{tmp_path / 'binding-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add(Course(id=course_id, user_id="owner", status="ready"))
        db.commit()
    first = get_or_create_source_plan(
        course_id, "a" * 64, "model", "prompt",
        db_session_factory=factory, create=lambda revision: _plan(revision, "a" * 64),
    )
    generator = Generator(None, LLMService(model="model"))
    version_id = generator.prepare_artifact_version(
        course_id, "slides", {"mode": "lesson"}, db_session_factory=factory
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        create_second = pool.submit(
            get_or_create_source_plan,
            course_id, "b" * 64, "model", "prompt",
            db_session_factory=factory,
            create=lambda revision: _plan(revision, "b" * 64),
        )
        bind = pool.submit(
            generator._bind_version_to_plan,
            course_id, "slides", version_id, first, factory,
            selected_model="model",
        )
        second = create_second.result()
        bind.result()
    with factory() as db:
        assert [row.revision for row in db.query(SourcePlanRecord).order_by(SourcePlanRecord.revision)] == [1, 2]
    assert first.revision == 1 and second.revision == 2


def test_source_plan_schema_rejects_blank_duplicate_and_unknown_references():
    payload = _plan(1, "a" * 64).model_dump()
    payload["objectives"][0]["id"] = "   "
    with pytest.raises(ValidationError):
        SourcePlan.model_validate(payload)
    payload = _plan(1, "a" * 64).model_dump()
    payload["objectives"][1]["id"] = payload["objectives"][0]["id"]
    with pytest.raises(ValidationError):
        SourcePlan.model_validate(payload)
    payload = _plan(1, "a" * 64).model_dump()
    payload["units"][0]["objective_ids"] = ["unknown"]
    with pytest.raises(ValidationError):
        SourcePlan.model_validate(payload)


def test_feature_override_selects_and_invalidates_plan_model(monkeypatch):
    course_id = "feature-model-plan"
    with SessionLocal() as db:
        db.add(Course(id=course_id, user_id="owner", filenames=["x.txt"], status="ready"))
        db.commit()
    store = get_vector_store()
    store.add_documents(
        [Document(content="Nội dung nguồn", metadata={"chunk_id": "evidence-1", "source_file": "x.txt"})],
        course_id=course_id,
    )
    default = LLMService(model="default-model")
    feature = LLMService(model="feature-model")
    monkeypatch.setattr(feature, "generate_source_plan", lambda _c, d, r, ids: _plan(r, d, ids))
    generator = Generator(store, default, {"slides": feature})
    first = generator._get_source_plan(course_id, "slides")
    monkeypatch.setattr(generator, "_generate_pptx_slides", lambda *args, **kwargs: "slide.pptx")
    version_id = generator.prepare_artifact_version(course_id, "slides", {"mode": "lesson"})
    assert generator.generate_slides(course_id, "Đơn vị", 2, version_id=version_id)
    with SessionLocal() as db:
        metadata = json.loads(db.get(Course, course_id).metadata_json)
        assert metadata["study_pack"]["artifacts"]["slides"]["versions"][version_id]["source_plan_model"] == "feature-model"
    feature.model = "feature-model-v2"
    second = generator._get_source_plan(course_id, "slides")
    assert first.revision == 1
    assert second.revision == 2
    with SessionLocal() as db:
        assert {row.model for row in db.query(SourcePlanRecord)} == {"feature-model", "feature-model-v2"}


def test_non_book_plan_does_not_reuse_book_model_identity(monkeypatch):
    course_id = "book-and-slides-model-plan"
    with SessionLocal() as db:
        db.add(Course(id=course_id, user_id="owner", filenames=["x.txt"], status="ready"))
        db.commit()
    store = get_vector_store()
    store.add_documents(
        [Document(content="Nội dung nguồn", metadata={"chunk_id": "evidence-1", "source_file": "x.txt"})],
        course_id=course_id,
    )
    flash = LLMService(model="google/gemini-2.5-flash")
    pro = LLMService(model="google/gemini-2.5-pro")
    monkeypatch.setattr(flash, "generate_source_plan", lambda _c, d, r, ids: _plan(r, d, ids))
    monkeypatch.setattr(pro, "generate_source_plan", lambda _c, d, r, ids: _plan(r, d, ids))
    generator = Generator(store, pro)

    book_plan = generator._get_source_plan(course_id, "book", selected_llm=flash)
    book_version = generator.prepare_artifact_version(
        course_id, "book", {"detail_level": "Tiêu chuẩn"}
    )
    generator._bind_version_to_plan(
        course_id,
        "book",
        book_version,
        book_plan,
        selected_model=flash.model,
    )
    slides_plan = generator._get_source_plan(course_id, "slides", selected_llm=pro)

    assert book_plan.revision == 1
    assert slides_plan.revision == 2
    with SessionLocal() as db:
        assert {row.model for row in db.query(SourcePlanRecord)} == {
            "google/gemini-2.5-flash",
            "google/gemini-2.5-pro",
        }


def test_exact_unit_assignment_with_overlapping_titles(monkeypatch):
    plan = _plan(1, "a" * 64, ["evidence-a"])
    plan.units[0].title = "Bảo toàn năng lượng"
    plan.units[0].evidence_ids = ["evidence-a"]
    plan.units[1].title = "Truyền năng lượng"
    plan.units[1].evidence_ids = ["evidence-b"]
    store = type(
        "Store",
        (),
        {"get_course_chunks": lambda _self, _course, ids: [
            Document(content=cid, metadata={"chunk_id": cid}) for cid in ids
        ]},
    )()
    generator = Generator(store, LLMService(model="model"))
    context, evidence, units = generator._plan_context(
        "course", plan, unit_ids=["unit-1"]
    )
    assert evidence == ["evidence-a"]
    assert [unit.id for unit in units] == ["unit-1"]
    assert "evidence-b" not in context


def test_visible_canonical_content_is_repaired_or_rejected():
    plan = _plan(1, "a" * 64)
    generator = Generator(None, LLMService(model="model"))
    omitted = SlidesOutput(
        title="Bài học", slides=[SlideItem(slide_number=1, title="Mở đầu", bullet_points=["Nội dung"], source_chunk_ids=["evidence-1"])]
    )
    generator._enforce_canonical_consistency(omitted, "slides", plan, plan.units[:1])
    visible = json.dumps(omitted.model_dump(), ensure_ascii=False)
    assert EQUATION in visible
    assert "Tổng ở tử số chia cho tổng ở mẫu số." in visible

    contradictions = {
        "book": BookOutput(
            title="Tỉ số tổng", summary="Mẫu số chia cho tử số", chapters=[
                BookChapter(chapter_title="Tỉ số tổng", sections=[BookSection(title="Sai", content="a+b/c+d")])
            ],
        ),
        "slides": SlidesOutput(
            title="Tỉ số tổng", slides=[SlideItem(slide_number=1, title="Tỉ số tổng", bullet_points=["Mẫu số chia cho tử số", "a+b/c+d"])]
        ),
        "quiz": QuizOutput(
            title="Tỉ số tổng", questions=[QuizQuestion(
                question_number=1,
                question_text="Tỉ số tổng là gì?",
                options=[QuizOption(key=key, text="Mẫu số chia cho tử số") for key in "ABCD"],
                correct_answer="A",
                explanation="a+b/c+d",
            )],
        ),
        "vid": VidOutput(
            title="Tỉ số tổng", total_duration_seconds=0,
            scenes=[VidScene(scene_number=1, title="Tỉ số tổng", narration="Mẫu số chia cho tử số a+b/c+d")],
        ),
    }
    for artifact, contradictory in contradictions.items():
        with pytest.raises(ValueError, match="canonical"):
            generator._enforce_canonical_consistency(
                contradictory, artifact, plan, plan.units[:1]
            )


def test_mixed_canonical_and_contradictory_claims_are_rejected_in_all_artifacts():
    plan = _plan(1, "a" * 64)
    plan.glossary[0].term = "Ratio"
    plan.glossary[0].definition = "Numerator divided by denominator."
    plan.equations[0].name = "Ratio"
    generator = Generator(None, LLMService(model="model"))
    mixed = f"Ratio: Numerator divided by denominator. {EQUATION}. Ratio = a+b/c+d. Ratio means denominator divided by numerator."
    outputs = {
        "book": BookOutput(
            title="Ratio lesson",
            summary="Canonical ratio lesson",
            chapters=[BookChapter(
                chapter_title="Ratio",
                sections=[BookSection(title="Definition", content=mixed)],
            )],
        ),
        "slides": SlidesOutput(
            title="Ratio lesson",
            slides=[SlideItem(slide_number=1, title="Ratio", bullet_points=[mixed])],
        ),
        "quiz": QuizOutput(
            title="Ratio quiz",
            questions=[QuizQuestion(
                question_number=1,
                question_text="What is Ratio?",
                options=[
                    QuizOption(key="A", text="Denominator divided by numerator."),
                    QuizOption(key="B", text="Numerator divided by denominator."),
                    QuizOption(key="C", text="A difference."),
                    QuizOption(key="D", text="A product."),
                ],
                correct_answer="A",
                explanation=mixed,
            )],
        ),
        "vid": VidOutput(
            title="Ratio lesson",
            total_duration_seconds=0,
            scenes=[VidScene(scene_number=1, title="Ratio", narration=mixed)],
        ),
    }
    for artifact, output in outputs.items():
        with pytest.raises(ValueError, match="canonical"):
            generator._enforce_canonical_consistency(output, artifact, plan, plan.units[:1])


def test_book_summary_only_canonical_contradiction_is_rejected():
    plan = _plan(1, "a" * 64)
    plan.glossary[0].term = "Ratio"
    plan.glossary[0].definition = "Numerator divided by denominator."
    plan.equations[0].name = "Ratio"
    generator = Generator(None, LLMService(model="model"))
    book = BookOutput(
        title="Ratio lesson",
        summary="Ratio = a+b/c+d. Ratio means denominator divided by numerator.",
        preface="Ratio introduction",
        chapters=[BookChapter(
            chapter_title="Ratio",
            sections=[BookSection(
                title="Canonical definition",
                content=f"Ratio: Numerator divided by denominator. {EQUATION}",
            )],
        )],
    )
    with pytest.raises(ValueError, match="canonical"):
        generator._enforce_canonical_consistency(book, "book", plan, plan.units[:1])


def test_quiz_canonical_explanation_cannot_mask_incorrect_selected_answer():
    plan = _plan(1, "a" * 64)
    plan.glossary[0].term = "Ratio"
    plan.glossary[0].definition = "Numerator divided by denominator."
    plan.equations[0].name = "Ratio"
    generator = Generator(None, LLMService(model="model"))
    quiz = QuizOutput(
        title="Ratio quiz",
        questions=[QuizQuestion(
            question_number=1,
            question_text="What is Ratio?",
            options=[
                QuizOption(key="A", text="Denominator divided by numerator."),
                QuizOption(key="B", text="Numerator divided by denominator."),
                QuizOption(key="C", text="A difference."),
                QuizOption(key="D", text="A product."),
            ],
            correct_answer="A",
            explanation=f"Ratio: Numerator divided by denominator. {EQUATION}",
        )],
    )
    with pytest.raises(ValueError, match="canonical"):
        generator._enforce_canonical_consistency(quiz, "quiz", plan, plan.units[:1])


@pytest.mark.parametrize(
    "conflict",
    [
        r"Ratio = \frac{a-b}{c-d}.",
        "Ratio is not Numerator divided by denominator.",
        "Ratio means Numerator divided by denominator, but Ratio means denominator divided by numerator.",
    ],
)
def test_each_exact_conflicting_claim_is_rejected_across_artifact_schemas(conflict):
    plan = _ratio_plan()
    generator = Generator(None, LLMService(model="model"))
    canonical = f"Ratio: Numerator divided by denominator. {EQUATION}."
    content = f"{canonical} {conflict}"
    outputs = {
        "book": BookOutput(
            title="Ratio lesson", summary="Overview",
            chapters=[BookChapter(
                chapter_title="Ratio", sections=[BookSection(title="Definition", content=content)]
            )],
        ),
        "slides": SlidesOutput(
            title="Ratio lesson",
            slides=[SlideItem(slide_number=1, title="Ratio", bullet_points=[content])],
        ),
        "quiz": QuizOutput(
            title="Ratio quiz",
            questions=[QuizQuestion(
                question_number=1,
                question_text="Apply Ratio to the example.",
                options=[QuizOption(key=key, text=f"Option {key}") for key in "ABCD"],
                correct_answer="A",
                explanation=content,
            )],
        ),
        "vid": VidOutput(
            title="Ratio lesson", total_duration_seconds=0,
            scenes=[VidScene(scene_number=1, title="Ratio", narration=content)],
        ),
    }
    for artifact, output in outputs.items():
        with pytest.raises(ValueError, match="canonical"):
            generator._enforce_canonical_consistency(output, artifact, plan, plan.units[:1])


@pytest.mark.parametrize(
    "conflict",
    [
        r"Ratio = \frac{a-b}{c-d}.",
        "Ratio is not Numerator divided by denominator.",
        "Ratio means Numerator divided by denominator, but Ratio means denominator divided by numerator.",
    ],
)
def test_each_exact_conflict_is_rejected_in_book_summary(conflict):
    plan = _ratio_plan()
    generator = Generator(None, LLMService(model="model"))
    book = BookOutput(
        title="Ratio lesson",
        summary=conflict,
        chapters=[BookChapter(
            chapter_title="Ratio",
            sections=[BookSection(
                title="Canonical",
                content=f"Ratio: Numerator divided by denominator. {EQUATION}.",
            )],
        )],
    )
    with pytest.raises(ValueError, match="canonical"):
        generator._enforce_canonical_consistency(book, "book", plan, plan.units[:1])


@pytest.mark.parametrize(
    ("question", "selected"),
    [
        ("What is Ratio?", "Not Numerator divided by denominator."),
        ("Which equation defines Ratio?", r"\frac{a-b}{c-d}"),
    ],
)
def test_quiz_selected_answer_preserves_negation_and_math_operators(question, selected):
    plan = _ratio_plan()
    generator = Generator(None, LLMService(model="model"))
    quiz = QuizOutput(
        title="Ratio quiz",
        questions=[QuizQuestion(
            question_number=1,
            question_text=question,
            options=[
                QuizOption(key="A", text=selected),
                QuizOption(key="B", text="Numerator divided by denominator."),
                QuizOption(key="C", text=EQUATION),
                QuizOption(key="D", text="A distractor."),
            ],
            correct_answer="A",
            explanation=f"Ratio: Numerator divided by denominator. {EQUATION}.",
        )],
    )
    with pytest.raises(ValueError, match="canonical"):
        generator._enforce_canonical_consistency(quiz, "quiz", plan, plan.units[:1])


def _canonical_claim_output(artifact, content):
    if artifact == "book":
        return BookOutput(
            title="Ratio lesson", summary="Overview",
            chapters=[BookChapter(
                chapter_title="Ratio", sections=[BookSection(title="Definition", content=content)]
            )],
        )
    if artifact == "slides":
        return SlidesOutput(
            title="Ratio lesson",
            slides=[SlideItem(slide_number=1, title="Ratio", bullet_points=[content])],
        )
    if artifact == "quiz":
        return QuizOutput(title="Ratio quiz", questions=[QuizQuestion(
            question_number=1, question_text="Apply Ratio to the example.",
            options=[QuizOption(key=key, text=f"Option {key}") for key in "ABCD"],
            correct_answer="A", explanation=content,
        )])
    return VidOutput(
        title="Ratio lesson", total_duration_seconds=0,
        scenes=[VidScene(scene_number=1, title="Ratio", narration=content)],
    )


@pytest.mark.parametrize("artifact", ["book", "slides", "quiz", "vid"])
@pytest.mark.parametrize("suffix", ["!", "!!", "!+1"])
def test_math_claim_factorial_is_not_sentence_punctuation(artifact, suffix):
    plan = _ratio_plan()
    content = (
        f"Ratio: Numerator divided by denominator. Ratio = {EQUATION}. "
        f"Ratio = {EQUATION}{suffix}."
    )
    output = _canonical_claim_output(artifact, content)
    with pytest.raises(ValueError, match="canonical"):
        Generator.__new__(Generator)._enforce_canonical_consistency(
            output, artifact, plan, plan.units[:1]
        )


@pytest.mark.parametrize("artifact", ["book", "slides", "quiz", "vid"])
@pytest.mark.parametrize("equation", ["0.5", "-0.5", ".5", "0.5 + 1.25", "5!"])
def test_math_claim_correct_decimal_and_factorial_are_preserved(artifact, equation):
    plan = _ratio_plan()
    plan.equations[0].latex = equation
    content = f"Ratio: Numerator divided by denominator. Ratio = {equation}."
    output = _canonical_claim_output(artifact, content)
    # Ensure acceptance comes from comparing the full value, not skipping an
    # empty claim (which previously happened for a leading decimal point).
    assert Generator._named_claim_values([content], "Ratio", equation_only=True) == [equation]
    Generator.__new__(Generator)._enforce_canonical_consistency(
        output, artifact, plan, plan.units[:1]
    )


@pytest.mark.parametrize("artifact", ["book", "slides", "quiz", "vid"])
@pytest.mark.parametrize("joiner", [" and ", " but ", ", and ", ", but "])
@pytest.mark.parametrize("conflicting", [False, True])
def test_math_claim_repeated_explicit_conjunctions(artifact, joiner, conflicting):
    plan = _ratio_plan()
    second = "denominator divided by numerator" if conflicting else "Numerator divided by denominator"
    content = (
        f"Ratio: Numerator divided by denominator. Ratio = {EQUATION}. "
        f"Ratio means Numerator divided by denominator{joiner}Ratio means {second}."
    )
    output = _canonical_claim_output(artifact, content)
    generator = Generator.__new__(Generator)
    if conflicting:
        with pytest.raises(ValueError, match="canonical"):
            generator._enforce_canonical_consistency(output, artifact, plan, plan.units[:1])
    else:
        generator._enforce_canonical_consistency(output, artifact, plan, plan.units[:1])


@pytest.mark.parametrize("named", [False, True])
@pytest.mark.parametrize(
    ("canonical", "selected", "valid"),
    [(EQUATION, EQUATION + "!", False), (EQUATION, EQUATION + "!+1", False),
     (EQUATION, r"\frac{a-b}{c-d}", False), ("0.5", "0.5", True),
     ("0.5", "0", False), ("5!", "5", False)],
)
def test_math_claim_quiz_selected_equation_tokens(canonical, selected, valid, named):
    plan = _ratio_plan()
    plan.equations[0].latex = canonical
    quiz = _canonical_claim_output(
        "quiz", f"Ratio: Numerator divided by denominator. Ratio = {canonical}."
    )
    quiz.questions[0].question_text = "Which equation defines Ratio?"
    quiz.questions[0].options[0].text = f"Ratio = {selected}." if named else selected
    generator = Generator.__new__(Generator)
    if valid:
        generator._enforce_canonical_consistency(quiz, "quiz", plan, plan.units[:1])
    else:
        with pytest.raises(ValueError, match="canonical"):
            generator._enforce_canonical_consistency(quiz, "quiz", plan, plan.units[:1])


def test_connected_artifacts_share_plan_and_hide_internal_provenance(monkeypatch):
    course_id = "shared-plan-course"
    with SessionLocal() as db:
        db.add(
            Course(
                id=course_id,
                user_id="owner",
                filenames=["math.txt"],
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=1,
                embedding_status="completed",
            )
        )
        db.commit()
    store = get_vector_store()
    store.add_documents(
        [
            Document(
                content=f"Tỉ số tổng dùng công thức {EQUATION}. Tỉ số tổng là tổng ở tử số chia cho tổng ở mẫu số.",
                metadata={"chunk_id": "evidence-1", "source_file": "math.txt", "page": 1},
            )
        ],
        course_id=course_id,
    )
    llm = LLMService(model="selected-model")
    monkeypatch.setattr(
        llm, "generate_source_plan",
        lambda context, digest, revision, ids: _plan(revision, digest, ids),
    )
    generator = Generator(store, llm)
    from app.services import provider_usage

    admission_order = []
    real_capacity_check = provider_usage.require_estimated_book_capacity
    real_get_source_plan = generator._get_source_plan

    def tracked_capacity(*args, **kwargs):
        admission_order.append(("capacity", kwargs.get("residual_usd", 0)))
        return real_capacity_check(*args, **kwargs)

    def tracked_source_plan(*args, **kwargs):
        admission_order.append(("source-plan", 0))
        return real_get_source_plan(*args, **kwargs)

    monkeypatch.setattr(provider_usage, "require_estimated_book_capacity", tracked_capacity)
    monkeypatch.setattr(generator, "_get_source_plan", tracked_source_plan)
    monkeypatch.setattr(generator, "_generate_pdf_book", lambda *args, **kwargs: "book.pdf")
    monkeypatch.setattr(generator, "_generate_pptx_slides", lambda *args, **kwargs: "slide.pptx")
    monkeypatch.setattr(generator, "_generate_pdf_quiz_key", lambda *args, **kwargs: "quiz.pdf")
    monkeypatch.setattr(generator, "_generate_video_mp4", lambda *args, **kwargs: "vid.mp4")

    versions = {
        "book": generator.prepare_artifact_version(course_id, "book", {"detail_level": "Tiêu chuẩn"}),
        "slides": generator.prepare_artifact_version(course_id, "slides", {"mode": "lesson"}),
        "quiz": generator.prepare_artifact_version(course_id, "quiz", {"quantity": 2, "difficulty": "medium"}),
        "vid": generator.prepare_artifact_version(course_id, "vid", {"format": "overview", "voice": "female"}),
    }
    assert generator.generate_book(course_id, version_id=versions["book"])
    assert admission_order[0][0] == "capacity"
    assert admission_order[0][1] > 0
    assert admission_order[1][0] == "source-plan"
    assert sum(item[0] == "capacity" for item in admission_order) >= 8
    assert generator.generate_slides(course_id, "Đơn vị", 2, version_id=versions["slides"])
    assert generator.generate_quiz(course_id, "Đơn vị", 2, version_id=versions["quiz"])
    assert generator.generate_vid(course_id, "Đơn vị", "overview", version_id=versions["vid"])

    revisions = set()
    old_book_path = None
    for artifact, filename in (("book", "book.json"), ("slides", "slides.json"), ("quiz", "quiz.json"), ("vid", "vid.json")):
        path = Path(generator._get_artifact_dir(course_id)) / artifact / versions[artifact] / filename
        payload = json.loads(path.read_text("utf-8"))
        revisions.add(payload["source_plan"]["revision"])
        assert payload["source_plan"]["canonical_equations"][0]["latex"] == EQUATION
        assert payload["source_plan"]["glossary"][0]["definition"] == "Tổng ở tử số chia cho tổng ở mẫu số."
        visible_payload = dict(payload)
        visible_payload.pop("source_plan")
        visible = json.dumps(visible_payload, ensure_ascii=False)
        assert EQUATION in visible
        assert "Tổng ở tử số chia cho tổng ở mẫu số." in visible
        if artifact == "book":
            old_book_path = path
        public = sanitize_public_payload(payload)
        assert "source_plan" not in public
        assert "evidence-1" not in json.dumps(public)
    assert revisions == {1, 2}
    assert all(unit.evidence_ids for unit in generator._get_source_plan(course_id).units)
    with SessionLocal() as db:
        metadata = json.loads(db.get(Course, course_id).metadata_json)
        artifact_versions = metadata["study_pack"]["artifacts"]
        assert {
            artifact_versions[name]["versions"][versions[name]]["source_plan_model"]
            for name in versions
        } == {"google/gemini-2.5-flash", "selected-model"}

    generator.delete_artifact_version(course_id, "slides", versions["slides"])
    with SessionLocal() as db:
        assert db.query(SourcePlanRecord).filter_by(course_id=course_id).count() == 2

    store.add_documents(
        [Document(content="Nguồn đã thay đổi.", metadata={"chunk_id": "evidence-2", "source_file": "math.txt", "page": 2})],
        course_id=course_id,
    )
    new_plan = generator._get_source_plan(course_id)
    assert new_plan.revision == 3
    assert old_book_path and json.loads(old_book_path.read_text("utf-8"))["source_plan"]["revision"] == 1
    new_version = generator.prepare_artifact_version(course_id, "slides", {"mode": "lesson"})
    assert generator.generate_slides(course_id, "Đơn vị", 2, version_id=new_version)
    new_payload = json.loads(
        (Path(generator._get_artifact_dir(course_id)) / "slides" / new_version / "slides.json").read_text("utf-8")
    )
    assert new_payload["source_plan"]["revision"] == 3
    assert EQUATION in json.dumps({k: v for k, v in new_payload.items() if k != "source_plan"}, ensure_ascii=False)
