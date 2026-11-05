"""
deps.py — FastAPI dependencies for the SAT Prep API.

get_rw_db_with_context:
  Opens an app_rw session and sets the per-request RLS config vars
  (app.user_id, app.role) so row-level security can filter by user.

get_current_user_id:
  Extracts the user UUID from the X-User-Id header (dev mode).
  Replace with JWT decoding when auth is ready.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import sessionlocal


async def get_current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> UUID:
    """
    DEV: Read user UUID from X-User-Id header.
    Replace with JWT subject extraction for production auth.
    """
    if not x_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing X-User-Id")
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid X-User-Id")


async def get_rw_db_with_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an app_rw session with RLS context variables set for the current user.
    Every student-scoped read endpoint should use this dependency.
    """
    # Validate header
    if not x_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing X-User-Id")
    try:
        uid = UUID(x_user_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid X-User-Id")

    async with sessionlocal() as session:
        try:
            # Set per-transaction RLS config vars
            await session.execute(
                text(
                    "SELECT set_config('app.user_id', :uid, true), "
                    "       set_config('app.role', 'student', true)"
                ),
                {"uid": str(uid)},
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
