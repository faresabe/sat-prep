"""Pydantic schemas for user profile endpoints."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRead(BaseModel):
    """Public user profile. Never includes password_hash."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    email_verified_at: datetime | None
    target_score: int | None
    test_date: date | None
    timezone: str | None
    grade_level: int | None
    onboarding_completed_at: datetime | None
    created_at: datetime


class UserUpdate(BaseModel):
    """Fields a user can update on their own profile."""
    full_name: str | None = Field(default=None, max_length=200)
    target_score: int | None = Field(default=None, ge=400, le=1600)
    test_date: date | None = None
    timezone: str | None = Field(default=None, max_length=50)
    grade_level: int | None = Field(default=None, ge=9, le=12)


class UserAdminRead(UserRead):
    """Admin view of a user — includes extra fields."""
    failed_login_count: int
    locked_until: datetime | None
    last_login_at: datetime | None
    deleted_at: datetime | None