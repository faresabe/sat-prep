"""Per-attempt performance by domain. Derived from answers."""

import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DomainResult(Base):
    __tablename__ = "domain_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("score_reports.id", ondelete="CASCADE")
    )
    domain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domains.id", ondelete="RESTRICT")
    )
    total: Mapped[int] = mapped_column(SmallInteger)
    correct: Mapped[int] = mapped_column(SmallInteger)
    unanswered: Mapped[int] = mapped_column(SmallInteger, default=0)
    accuracy: Mapped[float] = mapped_column(Numeric(5, 2))
    avg_time_ms: Mapped[int | None] = mapped_column(Integer)

    report: Mapped["ScoreReport"] = relationship(back_populates="domain_results")
    domain: Mapped["Domain"] = relationship()