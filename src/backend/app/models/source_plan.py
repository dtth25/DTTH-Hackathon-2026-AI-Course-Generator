"""Private persisted SourcePlan history and provenance."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint

from app.services.database import Base


class SourcePlanRecord(Base):
    __tablename__ = "source_plans"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "source_digest", "model", "prompt_revision",
            name="uq_source_plan_provenance",
        ),
        UniqueConstraint("course_id", "revision", name="uq_source_plan_revision"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    source_digest = Column(String(64), nullable=False)
    model = Column(String(255), nullable=False)
    prompt_revision = Column(String(100), nullable=False)
    plan_json = Column(Text, nullable=False)

