import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.question import ContentStatus


class TestType(str, enum.Enum):
    full_mock = "full_mock"
    section_practice = "section_practice"
    skill_practice = "skill_practice"


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None]
    test_type: Mapped[TestType] = mapped_column(
        Enum(TestType, name="test_type", create_type=False),
        default=TestType.full_mock,
    )
    is_adaptive: Mapped[bool] = mapped_column(Boolean, default=True)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", create_type=False),
        default=ContentStatus.draft,
    )
    published_at: Mapped[datetime | None]
    source: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["TestSection"]] = relationship(
        back_populates="test", cascade="all, delete-orphan"
    )