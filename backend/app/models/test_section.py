import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.domain import Section


class TestSection(Base):
    __tablename__ = "test_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE")
    )
    section: Mapped[Section] = mapped_column(
        Enum(Section, name="section_type", create_type=False)
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    break_seconds: Mapped[int | None] = mapped_column(Integer)
    break_skippable: Mapped[bool] = mapped_column(default=True)

    test: Mapped["Test"] = relationship(back_populates="sections")
    modules: Mapped[list["TestModule"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )