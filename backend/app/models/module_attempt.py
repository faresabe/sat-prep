import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Numeric, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ModuleAttemptStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    submitted = "submitted"


class SubmitReason(str, enum.Enum):
    user = "user"
    timeout = "timeout"
    admin = "admin"
    system = "system"


class ModuleAttempt(Base):
    __tablename__ = "module_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_modules.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[ModuleAttemptStatus] = mapped_column(
        Enum(ModuleAttemptStatus, name="module_attempt_status", create_type=False),
        default=ModuleAttemptStatus.not_started,
    )
    started_at: Mapped[datetime | None]
    deadline_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    submit_reason: Mapped[SubmitReason | None] = mapped_column(
        Enum(SubmitReason, name="submit_reason", create_type=False)
    )
    question_count: Mapped[int | None] = mapped_column(SmallInteger)
    correct_count: Mapped[int | None] = mapped_column(SmallInteger)
    weighted_score: Mapped[float | None] = mapped_column(Numeric(6, 4))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    attempt: Mapped["TestAttempt"] = relationship(back_populates="modules")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="module_attempt", cascade="all, delete-orphan"
    )