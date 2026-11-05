import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.domain import Section


class QuestionType(str, enum.Enum):
    multiple_choice = "multiple_choice"
    grid_in = "grid_in"


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ContentStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    published = "published"
    archived = "archived"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    root_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="RESTRICT")
    )
    section: Mapped[Section] = mapped_column(
        Enum(Section, name="section_type", create_type=False)
    )
    domain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domains.id", ondelete="RESTRICT")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT")
    )
    passage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passages.id", ondelete="RESTRICT")
    )
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type", create_type=False)
    )
    stem: Mapped[str]
    stem_asset_key: Mapped[str | None] = mapped_column(String(500))
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty_level", create_type=False)
    )
    calculator_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    irt_a: Mapped[float | None]
    irt_b: Mapped[float | None]
    irt_c: Mapped[float | None]
    source: Mapped[str | None] = mapped_column(String(200))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", create_type=False),
        default=ContentStatus.draft,
    )
    published_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    choices: Mapped[list["QuestionChoice"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    answer_key: Mapped["QuestionKey | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )