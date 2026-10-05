import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"
    voided = "voided"


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tests.id", ondelete="RESTRICT")
    )
    test_content_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status", create_type=False),
        default=AttemptStatus.in_progress,
    )
    time_multiplier: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
    last_activity_at: Mapped[datetime] = mapped_column(server_default=func.now())
    voided_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="test_attempts")
    modules: Mapped[list["ModuleAttempt"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    score_report: Mapped["ScoreReport | None"] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", uselist=False
    )