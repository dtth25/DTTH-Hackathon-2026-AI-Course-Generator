"""Durable exact-money provider accounting. Amounts are integer nanodollars."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    JSON,
)

from app.services.database import Base


class BookBudget(Base):
    __tablename__ = "book_budgets"
    __table_args__ = (
        UniqueConstraint("course_id", "version_id"),
        CheckConstraint("ceiling >= 0 AND spent >= 0 AND reserved >= 0"),
    )
    id = Column(String, primary_key=True)
    course_id = Column(String, ForeignKey("courses.id"), index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    version_id = Column(String)
    ceiling = Column(BigInteger, nullable=False, default=95_000_000)
    spent = Column(BigInteger, nullable=False, default=0)
    reserved = Column(BigInteger, nullable=False, default=0)
    state = Column(String(32), nullable=False, default="active")
    incident_code = Column(String(80))
    model_policy = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "model": "google/gemini-2.5-flash",
            "input_price_ceiling": "0.30",
            "output_price_ceiling": "2.50",
            "reasoning_budget": 512,
            "revision": "balanced-book-v1",
            "require_parameters": True,
            "provider_sort": "throughput",
            "structured_output": "json_schema",
            "output_cap_parameter": "max_tokens",
        },
    )
    allocation_digest = Column(String(64))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (CheckConstraint("reserved >= 0 AND (cost IS NULL OR cost >= 0)"),)
    call_id = Column(String, primary_key=True)
    budget_id = Column(String, ForeignKey("book_budgets.id"), index=True)
    job_id = Column(String, ForeignKey("processing_jobs.id"), index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    course_id = Column(String, ForeignKey("courses.id"), index=True)
    job_attempt = Column(Integer)
    provider_attempt = Column(Integer, nullable=False, default=1)
    feature = Column(String(32), nullable=False, default="generation")
    stage = Column(String(32), nullable=False, default="generating")
    model = Column(String(160))
    bound_metadata = Column(JSON)
    response_id = Column(String(200), unique=True)
    reserved = Column(BigInteger, nullable=False, default=0)
    cost = Column(BigInteger)
    original_cost = Column(String(100))
    input_tokens = Column(BigInteger)
    output_tokens = Column(BigInteger)
    state = Column(String(32), nullable=False, default="reserved")
    outcome = Column(String(32))
    elapsed_ms = Column(BigInteger)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)


class ProviderTestBudget(Base):
    __tablename__ = "provider_test_budgets"
    __table_args__ = (CheckConstraint("ceiling >= 0 AND spent >= 0 AND reserved >= 0"),)
    run_id = Column(String, primary_key=True)
    ceiling = Column(BigInteger, nullable=False)
    spent = Column(BigInteger, nullable=False, default=0)
    reserved = Column(BigInteger, nullable=False, default=0)
    state = Column(String(32), nullable=False, default="active")


class ProviderStage(Base):
    __tablename__ = "provider_stages"
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("processing_jobs.id"), nullable=False, index=True)
    attempt = Column(Integer, nullable=False)
    stage = Column(String(32), nullable=False)
    chapter = Column(Integer)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    elapsed_ms = Column(BigInteger)
