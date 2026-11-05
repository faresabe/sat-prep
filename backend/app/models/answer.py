import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.domain import Section
from app.models.question import Difficulty


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("module_attempts.id", ondelete="CASCADE")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="RESTRICT")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    section: Mapped[Section] = mapped_column(
        Enum(Section, name="section_type", create_type=False)
    )
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    skill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty_level", create_type=False)
    )
    selected_choice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    response_text: Mapped[str | None] = mapped_column(String(30))
    eliminated_choice_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[bool | None]
    time_spent_ms: Mapped[int] = mapped_column(Integer, default=0)
    visit_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    first_answered_at: Mapped[datetime | None]
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    module_attempt: Mapped["ModuleAttempt"] = relationship(back_populates="answers")