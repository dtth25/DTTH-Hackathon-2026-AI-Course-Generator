"""Atomic, ownership-scoped persistence for shared source plans."""

from __future__ import annotations

import json
from collections.abc import Callable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.source_plan import SourcePlanRecord
from app.schemas.source_plan import SourcePlan


def source_plan_request_revision(
    course_id: str,
    source_digest: str,
    model: str,
    prompt_revision: str,
    *,
    db_session_factory=None,
) -> int:
    """Return the persisted or next revision used to frame a source-plan request."""

    if db_session_factory is None:
        from app.services.database import SessionLocal

        db_session_factory = SessionLocal
    with db_session_factory() as db:
        existing = db.query(SourcePlanRecord).filter_by(
            course_id=course_id,
            source_digest=source_digest,
            model=model,
            prompt_revision=prompt_revision,
        ).first()
        if existing is not None:
            return existing.revision
        return (
            db.query(func.max(SourcePlanRecord.revision))
            .filter(SourcePlanRecord.course_id == course_id)
            .scalar()
            or 0
        ) + 1


def get_or_create_source_plan(
    course_id: str,
    source_digest: str,
    model: str,
    prompt_revision: str,
    *,
    db_session_factory=None,
    create: Callable[[int], SourcePlan] | None = None,
) -> SourcePlan:
    """Return one plan for an owned course/source/model/prompt tuple.

    The course lock is the singleflight boundary. Plan history has its own table, so
    unrelated artifact metadata writers cannot erase committed revisions.
    """
    values = (course_id, source_digest, model, prompt_revision)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("Source-plan provenance values must be non-empty")
    if db_session_factory is None:
        from app.services.database import SessionLocal

        db_session_factory = SessionLocal

    db: Session = db_session_factory()
    try:
        if db.bind is not None and db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        course_query = db.query(Course).filter(
            Course.id == course_id, Course.is_deleted.is_(False)
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            course_query = course_query.with_for_update()
        course = course_query.first()
        if course is None:
            raise ValueError("Course not found")

        existing = db.query(SourcePlanRecord).filter_by(
            course_id=course_id,
            source_digest=source_digest,
            model=model,
            prompt_revision=prompt_revision,
        ).first()
        if existing is not None:
            db.commit()
            return SourcePlan.model_validate_json(existing.plan_json)
        if create is None:
            raise ValueError("No source-plan builder was supplied")

        revision = (
            db.query(func.max(SourcePlanRecord.revision))
            .filter(SourcePlanRecord.course_id == course_id)
            .scalar()
            or 0
        ) + 1
        plan = create(revision)
        if plan.revision != revision or plan.source_digest != source_digest:
            raise ValueError("Source-plan builder returned mismatched provenance")
        db.add(
            SourcePlanRecord(
                course_id=course_id,
                owner_id=course.user_id,
                revision=revision,
                source_digest=source_digest,
                model=model,
                prompt_revision=prompt_revision,
                plan_json=json.dumps(plan.model_dump(), ensure_ascii=False),
            )
        )
        db.commit()
        return plan
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
