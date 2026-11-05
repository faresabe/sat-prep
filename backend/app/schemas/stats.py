"""Pydantic schemas for user stats and analytics."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    attempts_completed: int
    questions_answered: int
    questions_correct: int
    overall_accuracy: float | None
    best_total_score: int | None
    latest_total_score: int | None
    last_attempt_at: datetime | None


class UserSkillStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: uuid.UUID
    total_answered: int
    total_correct: int
    accuracy_pct: float | None
    recent_accuracy: float | None
    recent_window: int
    mastery: float | None
    avg_time_ms: int | None
    last_practiced_at: datetime | None


class UserDomainStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain_id: uuid.UUID
    total_answered: int
    total_correct: int
    accuracy_pct: float | None
    mastery: float | None
    avg_time_ms: int | None
    last_practiced_at: datetime | None


class WeaknessReport(BaseModel):
    """A student's top weak skills/domains for the dashboard."""
    weakest_skills: list[UserSkillStatRead]
    weakest_domains: list[UserDomainStatRead]
    overall: UserStatRead | None