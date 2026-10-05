import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class QuestionKey(Base):
    __tablename__ = "question_keys"
    __table_args__ = {"schema": "grading"}

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    correct_choice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    question: Mapped["Question"] = relationship(back_populates="answer_key")