"""Pydantic schemas for test attempts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─────────── Requests ───────────

class StartAttemptRequest(BaseModel):
    test_id: uuid.UUID


class StartModuleRequest(BaseModel):
    """Start the next module of an in-progress attempt."""
    module_id: uuid.UUID


class SaveAnswerRequest(BaseModel):
    """Upsert one answer. Sent on every autosave."""
    question_id: uuid.UUID
    selected_choice_id: uuid.UUID | None = None
    response_text: str | None = Field(default=None, max_length=30)
    eliminated_choice_ids: list[uuid.UUID] = []
    is_flagged: bool = False
    time_spent_ms: int = Field(default=0, ge=0)
    revision: int


class SubmitModuleRequest(BaseModel):
    reason: str = "user"  # user | timeout | admin | system


# ─────────── Responses ───────────

class AnswerRead(BaseModel):
    """A saved answer. is_correct is null until graded."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    selected_choice_id: uuid.UUID | None
    response_text: str | None
    eliminated_choice_ids: list[uuid.UUID]
    is_flagged: bool
    time_spent_ms: int
    visit_count: int
    revision: int
    is_correct: bool | None
    updated_at: datetime


class ModuleAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    sequence: int
    status: str
    started_at: datetime | None
    deadline_at: datetime | None
    submitted_at: datetime | None
    submit_reason: str | None
    question_count: int | None
    correct_count: int | None
    weighted_score: float | None


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_id: uuid.UUID
    test_content_version: int
    status: str
    time_multiplier: float
    started_at: datetime
    completed_at: datetime | None
    last_activity_at: datetime


class AttemptDetail(AttemptRead):
    """Attempt with its modules."""
    modules: list[ModuleAttemptRead] = []


class ModuleServeResponse(BaseModel):
    """What a student gets when starting or resuming a module."""
    module_attempt: ModuleAttemptRead
    questions: list[dict]  # list of QuestionRead dicts (avoid circular import)