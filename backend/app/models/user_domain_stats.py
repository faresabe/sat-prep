"""Rolling lifetime per-student per-domain aggregate."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserDomainStat(Base):
    __tablename__ = "user_domain_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("domains.id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_answered: Mapped[int] = mapped_column(Integer, default=0)
    total_correct: Mapped[int] = mapped_column(Integer, default=0)
    mastery: Mapped[float | None] = mapped_column(Numeric(5, 4))
    avg_time_ms: Mapped[int | None] = mapped_column(Integer)
    last_practiced_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )