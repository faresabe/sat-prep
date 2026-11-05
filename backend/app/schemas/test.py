"""Pydantic schemas for tests, sections, modules, module questions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ─────────── Module questions ───────────

class ModuleQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: uuid.UUID
    position: int


# ─────────── Modules ───────────

class TestModuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage: int
    level: str
    time_limit_sec: int
    question_target: int
    routing_threshold: float | None


class TestModuleDetail(TestModuleRead):
    questions: list[ModuleQuestionRead] = []


# ─────────── Sections ───────────

class TestSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section: str
    position: int
    break_seconds: int | None
    break_skippable: bool
    modules: list[TestModuleRead] = []


# ─────────── Tests ───────────

class TestRead(BaseModel):
    """Test metadata — no questions."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    test_type: str
    is_adaptive: bool
    content_version: int
    status: str
    published_at: datetime | None


class TestDetail(TestRead):
    """Test with its sections and modules (still no questions)."""
    sections: list[TestSectionRead] = []