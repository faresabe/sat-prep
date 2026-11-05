import uuid

from sqlalchemy import ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class QuestionChoice(Base):
    __tablename__ = "question_choices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(String(1))
    content: Mapped[str]
    asset_key: Mapped[str | None] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(SmallInteger)

    question: Mapped["Question"] = relationship(back_populates="choices")