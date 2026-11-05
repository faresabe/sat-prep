"""Records how a stage-1 module decided the stage-2 level."""

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.test_module import ModuleLevel


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    from_module_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("module_attempts.id", ondelete="CASCADE"),
        unique=True,
    )
    to_module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_modules.id", ondelete="RESTRICT")
    )
    score: Mapped[float] = mapped_column(Numeric(6, 4))
    threshold: Mapped[float] = mapped_column(Numeric(4, 3))
    chosen_level: Mapped[ModuleLevel] = mapped_column(
        Enum(ModuleLevel, name="module_level", create_type=False)
    )
    algorithm_version: Mapped[str] = mapped_column(String(20))
    decided_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    from_module_attempt: Mapped["ModuleAttempt"] = relationship()
    to_module: Mapped["TestModule"] = relationship()