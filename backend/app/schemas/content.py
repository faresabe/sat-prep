"""Pydantic schemas for content: domains, skills, passages, questions, choices."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─────────── Domains ───────────

class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section: str
    code: str
    name: str
    position: int


# ─────────── Skills ───────────

class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    section: str
    code: str
    name: str
    position: int


# ─────────── Passages ───────────

class PassageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    asset_key: str | None
    source: str | None
    status: str


# ─────────── Choices ───────────

class ChoiceRead(BaseModel):
    """A multiple-choice option. NO correctness info — safe to serve."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    content: str
    asset_key: str | None
    position: int


# ─────────── Questions ───────────

class QuestionRead(BaseModel):
    """A question as served to a student taking a test. No answers."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section: str
    domain_id: uuid.UUID
    skill_id: uuid.UUID
    passage_id: uuid.UUID | None
    question_type: str
    stem: str
    stem_asset_key: str | None
    difficulty: str
    calculator_allowed: bool
    choices: list[ChoiceRead] = []


class QuestionAdminRead(QuestionRead):
    """Admin/authoring view — includes metadata not shown to students."""
    revision: int
    status: str
    source: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ─────────── Admin: creation ───────────

class ChoiceCreate(BaseModel):
    label: str = Field(min_length=1, max_length=1)
    content: str
    asset_key: str | None = None
    position: int


class QuestionCreate(BaseModel):
    section: str
    domain_id: uuid.UUID
    skill_id: uuid.UUID
    passage_id: uuid.UUID | None = None
    question_type: str
    stem: str
    stem_asset_key: str | None = None
    difficulty: str
    calculator_allowed: bool = True
    source: str | None = None
    tags: list[str] = []
    choices: list[ChoiceCreate] = []
    correct_choice_label: str | None = None  # required for multiple_choice
    accepted_answers: list[str] = []         # required for grid_in
    explanation: str | None = None