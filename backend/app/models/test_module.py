import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ModuleLevel(str, enum.Enum):
    router = "router"
    easy = "easy"
    hard = "hard"


class TestModule(Base):
    __tablename__ = "test_modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_sections.id", ondelete="CASCADE")
    )
    stage: Mapped[int] = mapped_column(SmallInteger)
    level: Mapped[ModuleLevel] = mapped_column(
        Enum(ModuleLevel, name="module_level", create_type=False)
    )
    time_limit_sec: Mapped[int] = mapped_column(Integer)
    question_target: Mapped[int] = mapped_column(SmallInteger)
    routing_threshold: Mapped[float | None] = mapped_column(Numeric(4, 3))
    routing_weight_easy: Mapped[int | None] = mapped_column(SmallInteger)
    routing_weight_medium: Mapped[int | None] = mapped_column(SmallInteger)
    routing_weight_hard: Mapped[int | None] = mapped_column(SmallInteger)

    section: Mapped["TestSection"] = relationship(back_populates="modules")