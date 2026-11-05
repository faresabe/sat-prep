"""
idempotency.py — reusable idempotency-key lookup/store helper.

The idempotency_keys table schema:
  user_id UUID, idem_key TEXT, endpoint TEXT,
  request_hash TEXT, response_status INT, response_body JSONB,
  expires_at TIMESTAMPTZ

Usage:
  1. Call lookup() — if (True, cached) → return cached response immediately.
  2. On success, call store() with the response status + body.
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _hash_body(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


async def lookup(
    db: AsyncSession,
    user_id: UUID,
    idem_key: str,
    body: dict,
) -> tuple[bool, dict | None]:
    """
    Returns (is_replay, cached_response).
    Raises HTTP 409 if the key exists but body hash differs.
    """
    request_hash = _hash_body(body)

    row = (
        await db.execute(
            text(
                """
                SELECT request_hash, response_status, response_body
                  FROM idempotency_keys
                 WHERE user_id = :uid
                   AND idem_key = :key
                   AND expires_at > now()
                """
            ),
            {"uid": str(user_id), "key": idem_key},
        )
    ).mappings().first()

    if row is None:
        return False, None

    if row["request_hash"] != request_hash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency-Key reused with a different request body",
        )

    if row["response_status"] is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Original request is still being processed",
        )

    return True, {
        "status": row["response_status"],
        "body": row["response_body"],
    }


async def store(
    db: AsyncSession,
    user_id: UUID,
    idem_key: str,
    endpoint: str,
    body: dict,
    response_status: int,
    response_body: dict,
) -> None:
    """Upsert the result for a completed request."""
    request_hash = _hash_body(body)

    await db.execute(
        text(
            """
            INSERT INTO idempotency_keys
                (user_id, idem_key, endpoint, request_hash, response_status, response_body)
            VALUES (:uid, :key, :ep, :hash, :status, CAST(:body AS jsonb))
            ON CONFLICT (user_id, idem_key)
            DO UPDATE SET response_status = EXCLUDED.response_status,
                          response_body   = EXCLUDED.response_body
            """
        ),
        {
            "uid": str(user_id),
            "key": idem_key,
            "ep": endpoint,
            "hash": request_hash,
            "status": response_status,
            "body": json.dumps(response_body),
        },
    )
