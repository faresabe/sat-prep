import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserStat(Base):
    __tablename__ = "user_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attempts_completed: Mapped[int] = mapped_column(Integer, default=0)
    questions_answered: Mapped[int] = mapped_column(Integer, default=0)
    questions_correct: Mapped[int] = mapped_column(Integer, default=0)
    best_total_score: Mapped[int | None] = mapped_column(SmallInteger)
    latest_total_score: Mapped[int | None] = mapped_column(SmallInteger)
    last_attempt_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )