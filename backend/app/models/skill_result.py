"""Per-attempt performance by skill, split by difficulty."""

import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SkillResult(Base):
    __tablename__ = "skill_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("score_reports.id", ondelete="CASCADE")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT")
    )
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    total: Mapped[int] = mapped_column(SmallInteger)
    correct: Mapped[int] = mapped_column(SmallInteger)
    unanswered: Mapped[int] = mapped_column(SmallInteger, default=0)
    accuracy: Mapped[float] = mapped_column(Numeric(5, 2))
    avg_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Split by difficulty
    easy_total: Mapped[int] = mapped_column(SmallInteger, default=0)
    easy_correct: Mapped[int] = mapped_column(SmallInteger, default=0)
    medium_total: Mapped[int] = mapped_column(SmallInteger, default=0)
    medium_correct: Mapped[int] = mapped_column(SmallInteger, default=0)
    hard_total: Mapped[int] = mapped_column(SmallInteger, default=0)
    hard_correct: Mapped[int] = mapped_column(SmallInteger, default=0)

    report: Mapped["ScoreReport"] = relationship(back_populates="skill_results")
    skill: Mapped["Skill"] = relationship()
    