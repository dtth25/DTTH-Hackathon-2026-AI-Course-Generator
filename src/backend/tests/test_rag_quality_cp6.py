"""CP6 regressions for honest structural scoring and source-faithful retrieval."""

import json

from app.schemas.generator_output import (
    BookChapter,
    BookOutput,
    BookOutline,
    BookSection,
    SlideItem,
    SlidesOutput,
    validate_and_score_output,
)
from app.services.retrieval import retrieve_evidence, select_evidence
from app.services.document_processor import _legacy_extraction_compatibility_score
from app.services.vector_store import Document
from app.schemas.source_document import ExtractionReport
from app.models.course import Course
from app.models.user import User
from app.services.database import SessionLocal
from app.services.generator import Generator


def test_empty_allowed_evidence_makes_citations_invalid_and_faithfulness_unknown():
    deck = SlidesOutput(
        title="Arithmetic",
        slides=[SlideItem(slide_number=1, title="Claim", bullet_points=["2 + 2 = 5"], source_chunk_ids=["c1"])],
    )

    _, report, warnings = validate_and_score_output(deck, "slides", valid_chunk_ids=[])

    assert warnings
    assert report.citation_validity == 0
    assert report.faithfulness is None
    assert "factual" not in report.labels


def test_missing_citations_are_reported():
    deck = SlidesOutput(
        title="Deck",
        slides=[SlideItem(slide_number=1, title="Claim", bullet_points=["Claim without evidence"])],
    )

    _, report, warnings = validate_and_score_output(deck, "slides", valid_chunk_ids=["c1"])

    assert report.citation_validity == 0
    assert any("thiếu trích dẫn" in warning for warning in warnings)


def test_book_chapter_cannot_cite_another_chapters_evidence():
    section = BookSection(title="Section", content="word " * 400)
    book = BookOutput(
        title="Book",
        summary="Summary",
        chapters=[
            BookChapter(chapter_title="A", introduction="intro", sections=[section], source_chunk_ids=["b-only"]),
            BookChapter(chapter_title="B", introduction="intro", sections=[section], source_chunk_ids=["b-only"]),
        ],
    )

    _, report, warnings = validate_and_score_output(
        book,
        "book",
        valid_chunk_ids=["a-only", "b-only"],
        unit_valid_chunk_ids={0: ["a-only"], 1: ["b-only"]},
    )

    assert report.citation_validity == 50
    assert any("Chương 'A'" in warning and "không tồn tại" in warning for warning in warnings)


def test_dedupe_uses_full_case_and_whitespace_preserving_content():
    docs = [
        Document(content="Shared heading\nA = 1", metadata={"chunk_id": "eq-A", "page": 1}),
        Document(content="Shared heading\na = 1", metadata={"chunk_id": "eq-a", "page": 2}),
        Document(content="Shared heading\nif ok:\n    run()", metadata={"chunk_id": "code-4", "page": 3}),
        Document(content="Shared heading\nif ok:\n  run()", metadata={"chunk_id": "code-2", "page": 4}),
        Document(content="Shared heading\n" + "x" * 180 + " first", metadata={"chunk_id": "long-1", "page": 5}),
        Document(content="Shared heading\n" + "x" * 180 + " second", metadata={"chunk_id": "long-2", "page": 6}),
    ]

    selected = select_evidence(docs, k=10)

    assert [doc.metadata["chunk_id"] for doc in selected] == [
        "eq-A", "eq-a", "code-4", "code-2", "long-1", "long-2"
    ]


def test_only_noise_or_front_matter_is_source_insufficient():
    docs = [
        Document(content="ISBN 000 publisher copyright", metadata={"chunk_id": "front", "is_front_matter": True}),
        Document(content="Page 1 of 1", metadata={"chunk_id": "noise", "is_noise": True}),
    ]

    assert select_evidence(docs, k=5) == []


def test_selection_keeps_similarity_rank_before_source_sort():
    docs = [
        Document(content="rank one", metadata={"chunk_id": "one", "source_file": "z.txt", "page": 9}),
        Document(content="rank two", metadata={"chunk_id": "two", "source_file": "a.txt", "page": 2}),
        Document(content="rank three", metadata={"chunk_id": "three", "source_file": "a.txt", "page": 1}),
    ]

    selected = select_evidence(docs, k=2)

    assert [doc.metadata["chunk_id"] for doc in selected] == ["two", "one"]


def test_same_page_presentation_uses_canonical_block_order_before_similarity_rank():
    docs = [
        Document(content="later", metadata={"chunk_id": "later", "source_file": "a.txt", "page": 1, "block_order": 9}),
        Document(content="earlier", metadata={"chunk_id": "earlier", "source_file": "a.txt", "page": 1, "block_order": 2}),
    ]

    selected = select_evidence(docs, k=2)

    assert [doc.metadata["chunk_id"] for doc in selected] == ["earlier", "later"]


def test_coverage_retrieval_includes_bounded_lower_ranked_document_for_outline():
    class FakeStore:
        def search(self, **_kwargs):
            return [
                Document(content=f"ranked A {index}", metadata={"chunk_id": f"a-{index}", "source_file": "a.txt", "page": index})
                for index in range(1, 8)
            ]

        def get_course_chunks(
            self,
            _course_id,
            chunk_ids=None,
            provider="openrouter",
            *,
            source_file=None,
            limit=None,
            offset=None,
        ):
            assert chunk_ids is None
            assert provider == "openrouter"
            rows = {
                "a.txt": [Document(content="substantive A", metadata={"chunk_id": "a-source", "source_file": "a.txt", "page": 1})],
                "b.txt": [Document(content="lower-ranked substantive B", metadata={"chunk_id": "b-source", "source_file": "b.txt", "page": 4})],
            }[source_file]
            start = offset or 0
            return rows[start : start + limit]

    selected = retrieve_evidence(
        "course",
        "overview",
        4,
        vector_store=FakeStore(),
        coverage_sources=["a.txt", "b.txt"],
    )

    assert any("lower-ranked substantive B" in document.content for document in selected)
    assert len(selected) <= 4


def test_book_outline_prompt_receives_lower_ranked_substantive_document():
    course_id = "cp6-outline-coverage"
    with SessionLocal() as db:
        db.add(
            Course(
                id=course_id,
                user_id="owner",
                filenames=["a.txt", "b.txt"],
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=8,
                embedding_status="completed",
                embedding_provider="openrouter",
            )
        )
        db.commit()

    coverage_calls = []

    class FakeStore:
        def search(self, **_kwargs):
            return [
                Document(content=f"ranked A {index}", metadata={"chunk_id": f"a-{index}", "source_file": "a.txt", "page": index})
                for index in range(1, 26)
            ]

        def get_course_chunks(
            self,
            _course_id,
            chunk_ids=None,
            provider="openrouter",
            *,
            source_file=None,
            limit=None,
            offset=None,
        ):
            coverage_calls.append((source_file, offset, limit))
            rows = {
                "a.txt": [Document(content="substantive A", metadata={"chunk_id": "a-source", "source_file": "a.txt", "page": 1})],
                "b.txt": [
                    Document(
                        content="ISBN 000 publisher copyright",
                        metadata={"chunk_id": "b-front", "source_file": "b.txt", "is_front_matter": True},
                    ),
                    Document(
                        content="Page 2 of 9",
                        metadata={"chunk_id": "b-noise", "source_file": "b.txt", "is_noise": True},
                    ),
                    Document(
                        content="lower-ranked substantive B",
                        metadata={"chunk_id": "b-source", "source_file": "b.txt", "page": 4},
                    ),
                ],
            }[source_file]
            start = offset or 0
            return rows[start : start + limit]

    captured = {}

    class FakeBookLLM:
        def generate_book_outline(self, context, *_args):
            captured["context"] = context
            return BookOutline(title="Book", summary="Summary", preface="Preface", chapters=[])

    generator = Generator(FakeStore(), FakeBookLLM())

    assert generator.generate_book(course_id) is None
    assert "lower-ranked substantive B" in captured["context"]
    assert coverage_calls[:2] == [("b.txt", 0, 2), ("b.txt", 2, 2)]


def _quality_payload(citation_validity: int) -> dict:
    return {
        "structural_validity": 100,
        "citation_validity": citation_validity,
        "source_coverage": citation_validity,
        "extraction_complete": True,
        "faithfulness": None,
        "indexed_chunk_count": 1,
        "invalid_citation_count": 0,
        "missing_citation_count": 0,
        "labels": ["structural checks", "source coverage"],
    }


def _seed_versioned_quality_course(course_id: str) -> None:
    old_report = _quality_payload(25)
    new_report = _quality_payload(100)
    metadata = {
        "study_pack": {
            "artifacts": {
                "slides": {
                    "active": "new",
                    "versions": {
                        "old": {"status": "ready", "created_at": "2026-01-01", "quality_report": old_report},
                        "new": {"status": "ready", "created_at": "2026-01-02", "quality_report": new_report},
                    },
                }
            },
            "quality_reports": {"slides": new_report},
        }
    }
    with SessionLocal() as db:
        db.add(
            Course(
                id=course_id,
                user_id="owner",
                filenames=["source.txt"],
                status="ready",
                stage="completed",
                metadata_json=json.dumps(metadata),
            )
        )
        db.commit()


def test_deleting_active_version_refreshes_study_pack_quality_report(monkeypatch):
    course_id = "cp6-quality-version-fallback"
    _seed_versioned_quality_course(course_id)
    monkeypatch.setattr("app.services.generator.remove_artifact_version", lambda *_args: None)
    generator = Generator(None, None)

    generator.delete_artifact_version(course_id, "slides", "new")

    assert generator.get_artifact_status(course_id, "slides")["quality_report"]["citation_validity"] == 25
    report = generator.get_study_pack(course_id).study_pack.quality_reports["slides"]
    assert report.citation_validity == 25


def test_deleting_last_version_clears_study_pack_quality_report(monkeypatch):
    course_id = "cp6-quality-version-empty"
    _seed_versioned_quality_course(course_id)
    monkeypatch.setattr("app.services.generator.remove_artifact_version", lambda *_args: None)
    generator = Generator(None, None)
    generator.delete_artifact_version(course_id, "slides", "new")

    generator.delete_artifact_version(course_id, "slides", "old")

    assert generator.get_artifact_status(course_id, "slides") == {}
    assert "slides" not in generator.get_study_pack(course_id).study_pack.quality_reports


def test_legacy_ingestion_score_reflects_extraction_completion_not_chunk_count():
    complete = ExtractionReport(total_pages=1, extracted_pages=[1], complete=True)
    incomplete = ExtractionReport(total_pages=2, extracted_pages=[1], damaged_pages=[2], complete=False)

    assert _legacy_extraction_compatibility_score([complete]) == 100
    assert _legacy_extraction_compatibility_score([incomplete]) == 0


def test_generate_persist_and_read_keeps_redacted_artifact_quality_report(monkeypatch, client):
    course_id = "cp6-quality-boundary"
    email = "cp6-quality@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "password123", "full_name": "CP6"})
    verified = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
    token = verified.json()["access_token"]
    with SessionLocal() as db:
        owner = db.query(User).filter(User.email == email).one()
        db.add(
            Course(
                id=course_id,
                user_id=owner.id,
                filenames=["source.txt"],
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=1,
                embedding_status="completed",
            )
        )
        db.commit()

    class FakeLLM:
        def generate_slides(self, *_args, **_kwargs):
            return SlidesOutput(
                title="Deck",
                slides=[
                    SlideItem(slide_number=1, title="Invalid", bullet_points=["claim"], source_chunk_ids=["not-retrieved"]),
                    SlideItem(slide_number=2, title="Missing", bullet_points=["claim"], source_chunk_ids=[]),
                ],
            )

    generator = Generator(None, FakeLLM())
    monkeypatch.setattr(
        generator,
        "_retrieve_context",
        lambda *_args, **_kwargs: ("[Chunk ID: allowed] source", ["allowed"]),
    )
    monkeypatch.setattr(generator, "_generate_pptx_slides", lambda *_args, **_kwargs: "unused")
    version_id = generator.prepare_artifact_version(course_id, "slides", {"mode": "lesson"})

    output = generator.generate_slides(course_id, topic="Topic", num_slides=2, version_id=version_id)

    assert output is not None
    persisted = generator.get_artifact_status(course_id, "slides", version_id)["quality_report"]
    assert persisted["citation_validity"] == 0
    assert persisted["invalid_citation_count"] == 1
    assert persisted["missing_citation_count"] == 1
    assert persisted["faithfulness"] is None
    assert "not-retrieved" not in str(persisted)
    pack_report = generator.get_study_pack(course_id).study_pack.quality_reports["slides"]
    assert pack_report.model_dump() == persisted
    response = client.get(
        f"/api/course/{course_id}/slide?version={version_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    public_report = response.json()["quality_report"]
    assert public_report == persisted
    assert "not-retrieved" not in response.text
