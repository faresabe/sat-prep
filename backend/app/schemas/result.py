"""Pydantic schemas for score reports and results."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DomainResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain_id: uuid.UUID
    total: int
    correct: int
    unanswered: int
    accuracy: float
    avg_time_ms: int | None


class SkillResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: uuid.UUID
    domain_id: uuid.UUID
    total: int
    correct: int
    unanswered: int
    accuracy: float
    avg_time_ms: int | None
    easy_total: int
    easy_correct: int
    medium_total: int
    medium_correct: int
    hard_total: int
    hard_correct: int


class ScoreReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_id: uuid.UUID
    rw_raw: int | None
    math_raw: int | None
    rw_scaled: int | None
    math_scaled: int | None
    total_scaled: int | None
    rw_stage2_level: str | None
    math_stage2_level: str | None
    scoring_version: str
    generated_at: datetime


class ScoreReportDetail(ScoreReportRead):
    """Full report with per-domain and per-skill breakdowns."""
    domain_results: list[DomainResultRead] = []
    skill_results: list[SkillResultRead] = []