import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.test_module import ModuleLevel


class ScoreReport(Base):
    __tablename__ = "score_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rw_raw: Mapped[int | None] = mapped_column(SmallInteger)
    math_raw: Mapped[int | None] = mapped_column(SmallInteger)
    rw_scaled: Mapped[int | None] = mapped_column(SmallInteger)
    math_scaled: Mapped[int | None] = mapped_column(SmallInteger)
    total_scaled: Mapped[int | None] = mapped_column(SmallInteger)
    rw_theta: Mapped[float | None]
    math_theta: Mapped[float | None]
    rw_stage2_level: Mapped[ModuleLevel | None] = mapped_column(
        Enum(ModuleLevel, name="module_level", create_type=False)
    )
    math_stage2_level: Mapped[ModuleLevel | None] = mapped_column(
        Enum(ModuleLevel, name="module_level", create_type=False)
    )
    scoring_version: Mapped[str] = mapped_column(String(20))
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    attempt: Mapped["TestAttempt"] = relationship(back_populates="score_report")

    domain_results: Mapped[list["DomainResult"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )
    skill_results: Mapped[list["SkillResult"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )