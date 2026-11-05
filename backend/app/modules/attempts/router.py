"""
router.py — FastAPI endpoints for attempt submission.

Uses app_grader for the submit path (has BYPASSRLS and writes is_correct).
Idempotency: pass an `Idempotency-Key` header to make retries safe.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency as idem
from app.core.logging import log
from app.db import get_grader_db, grader_sessionlocal
from app.deps import get_current_user_id
from app.modules.attempts import service
from app.modules.attempts.service import (
    SubmitError,
    SubmitConflict,
    SubmitPreconditionFailed,
)


router = APIRouter(prefix="/attempts", tags=["attempts"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/modules/{module_attempt_id}/submit",
    status_code=status.HTTP_200_OK,
)
async def submit_module(
    module_attempt_id: UUID,
    reason: str = "user",
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_grader_db),
):
    """
    Submit a module attempt. Idempotent when Idempotency-Key is provided.

    Idempotency note: the lookup uses the submit session (db). The store uses
    a *separate* session so that any error raised inside service.submit_module
    (which aborts the submit transaction) does not prevent the idempotency
    record from being written.
    """
    endpoint = "submit_module"
    request_body = {
        "module_attempt_id": str(module_attempt_id),
        "reason": reason,
    }

    # --- idempotency: replay path ---
    if idempotency_key:
        is_replay, cached = await idem.lookup(db, user_id, idempotency_key, request_body)
        if is_replay and cached:
            return cached["body"]

    # --- main path ---
    try:
        result = await service.submit_module(db, module_attempt_id, reason)
    except SubmitConflict as e:
        log.warning("submit_conflict", error=str(e),
                    module_attempt_id=str(module_attempt_id))
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except SubmitPreconditionFailed as e:
        log.error("submit_precondition_failed", error=str(e),
                  module_attempt_id=str(module_attempt_id))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))
    except SubmitError as e:
        log.warning("submit_error", error=str(e),
                    module_attempt_id=str(module_attempt_id))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception:
        log.exception("submit_unexpected_error",
                      module_attempt_id=str(module_attempt_id))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal error",
        )

    # --- idempotency: store result ---
    # Use a *separate* session so a prior transaction error in db cannot
    # bleed into this write. Non-fatal: if this fails, the submit already
    # succeeded and the client has its response.
    if idempotency_key:
        try:
            async with grader_sessionlocal() as idem_db:
                await idem.store(
                    idem_db,
                    user_id,
                    idempotency_key,
                    endpoint,
                    request_body,
                    response_status=200,
                    response_body=result,
                )
                await idem_db.commit()
        except Exception:
            log.warning(
                "idempotency_store_failed",
                module_attempt_id=str(module_attempt_id),
                idem_key=idempotency_key,
            )

    return result
