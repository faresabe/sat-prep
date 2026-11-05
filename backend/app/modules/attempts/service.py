"""
service.py — orchestrate the submit-module operation.

Runs as app_grader (BYPASSRLS). One transaction. All-or-nothing.

Caller owns the transaction. This module does NOT commit or rollback.

Order of operations matters:
  1. Lock and load the module attempt
  2. Grade every answer
  3. Compute weighted score
  4. (Stage 1 only) write routing_decisions BEFORE the module UPDATE,
     because trg_enforce_module_order validates the routing_decisions
     row exists when the module transitions to 'submitted'.
  5. Create the next module_attempt (Stage 2, or break, or complete)
  6. Mark the current module_attempt submitted (fires the trigger)
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.modules.attempts.grading import grade_module, GradingError
from app.modules.analytics.score_builder import build_score_report
from app.modules.attempts.routing import (
    compute_weighted_score,
    decide_level,
    DEFAULT_THRESHOLD,
    DEFAULT_WEIGHT_EASY,
    DEFAULT_WEIGHT_MEDIUM,
    DEFAULT_WEIGHT_HARD,
    ALGORITHM_VERSION,
)


class SubmitError(Exception):
    """Raised when the module cannot be submitted (bad state, missing config, etc.)."""


class SubmitConflict(SubmitError):
    """Raised when the module is already submitted or not in the expected state."""


class SubmitPreconditionFailed(SubmitError):
    """Raised when the module config or routing cannot be resolved."""


VALID_REASONS = {"user", "timeout", "admin", "system"}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

async def _load_module_attempt(db: AsyncSession, module_attempt_id: UUID) -> dict:
    """
    Lock only the module_attempt row FOR UPDATE, then fetch module/section data.
    Splitting the lock from the join avoids needing FOR UPDATE privilege on
    test_modules and test_sections.
    """
    # Step 1: lock just module_attempts
    ma_row = (
        await db.execute(
            text(
                """
                SELECT id, attempt_id, user_id, module_id, sequence, status
                  FROM module_attempts
                 WHERE id = :id
                 FOR UPDATE
                """
            ),
            {"id": str(module_attempt_id)},
        )
    ).mappings().first()

    if ma_row is None:
        raise SubmitError(f"module_attempt {module_attempt_id} not found")

    # Step 2: fetch module + section metadata (no lock needed)
    meta_row = (
        await db.execute(
            text(
                """
                SELECT tm.stage, tm.section_id,
                       tm.routing_threshold,
                       tm.routing_weight_easy,
                       tm.routing_weight_medium,
                       tm.routing_weight_hard,
                       ts.test_id, ts.section, ts.position, ts.break_seconds
                  FROM test_modules  tm
                  JOIN test_sections ts ON ts.id = tm.section_id
                 WHERE tm.id = :module_id
                """
            ),
            {"module_id": str(ma_row["module_id"])},
        )
    ).mappings().first()

    if meta_row is None:
        raise SubmitError(f"test_modules/sections not found for module {ma_row['module_id']}")

    return {**dict(ma_row), **dict(meta_row)}


async def _find_stage2_module(db: AsyncSession, section_id: UUID, level: str) -> UUID:
    row = (
        await db.execute(
            text(
                """
                SELECT id FROM test_modules
                 WHERE section_id = :sid AND stage = 2 AND level = :lvl
                """
            ),
            {"sid": str(section_id), "lvl": level},
        )
    ).first()

    if row is None:
        raise SubmitPreconditionFailed(
            f"no stage-2 module for level={level} in section {section_id}"
        )
    return row[0]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

async def _create_stage2(
    db: AsyncSession,
    ma: dict,
    weighted: Decimal,
    threshold: Decimal,
    chosen_level: str,
) -> UUID:
    to_module_id = await _find_stage2_module(db, ma["section_id"], chosen_level)

    # 1. routing_decisions — must exist before the module UPDATE fires the trigger
    await db.execute(
        text(
            """
            INSERT INTO routing_decisions
                (from_module_attempt_id, to_module_id, score, threshold,
                 chosen_level, algorithm_version)
            VALUES (:from_id, :to_id, :score, :threshold, :level, :version)
            """
        ),
        {
            "from_id": str(ma["id"]),
            "to_id": str(to_module_id),
            "score": str(weighted),
            "threshold": str(threshold),
            "level": chosen_level,
            "version": ALGORITHM_VERSION,
        },
    )

    # 2. Stage-2 module_attempt (not_started). Trigger does NOT fire on INSERT.
    row = (
        await db.execute(
            text(
                """
                INSERT INTO module_attempts
                    (attempt_id, user_id, module_id, sequence, status)
                VALUES (:attempt_id, :user_id, :module_id, :sequence, 'not_started')
                RETURNING id
                """
            ),
            {
                "attempt_id": str(ma["attempt_id"]),
                "user_id": str(ma["user_id"]),
                "module_id": str(to_module_id),
                "sequence": ma["sequence"] + 1,
            },
        )
    ).first()

    return row[0]


async def _handle_break_or_complete(db: AsyncSession, ma: dict) -> dict:
    # No break configured → attempt is done
    if not ma["break_seconds"]:
        await db.execute(
            text(
                """
                UPDATE test_attempts
                   SET status = 'completed', completed_at = now()
                 WHERE id = :id
                """
            ),
            {"id": str(ma["attempt_id"])},
        )
        return {"type": "attempt_complete"}

    # Is there another section after this one?
    next_section = (
        await db.execute(
            text(
                """
                SELECT id FROM test_sections
                 WHERE test_id = :tid AND position > :pos
                 ORDER BY position
                 LIMIT 1
                """
            ),
            {"tid": str(ma["test_id"]), "pos": ma["position"]},
        )
    ).first()

    if next_section is None:
        await db.execute(
            text(
                """
                UPDATE test_attempts
                   SET status = 'completed', completed_at = now()
                 WHERE id = :id
                """
            ),
            {"id": str(ma["attempt_id"])},
        )
        return {"type": "attempt_complete"}

    row = (
        await db.execute(
            text(
                """
                INSERT INTO break_sessions
                    (attempt_id, user_id, after_section_id, started_at, ends_at)
                VALUES (:aid, :uid, :sid, now(), now() + make_interval(secs => :secs))
                RETURNING id
                """
            ),
            {
                "aid": str(ma["attempt_id"]),
                "uid": str(ma["user_id"]),
                "sid": str(ma["section_id"]),
                "secs": ma["break_seconds"],
            },
        )
    ).first()

    return {"type": "break", "break_session_id": str(row[0])}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def submit_module(
    db: AsyncSession,
    module_attempt_id: UUID,
    reason: str = "user",
) -> dict:
    """
    Grade + submit a module attempt.

    Caller owns the transaction. This function performs no commit/rollback.

    Returns:
        {
          "module_attempt_id": str,
          "question_count": int,
          "correct_count": int,
          "weighted_score": float,
          "next": {"type": "next_module", "module_attempt_id": str,
                   "level": "easy" | "hard",
                   "weighted_score": float, "threshold": float}
               | {"type": "break", "break_session_id": str}
               | {"type": "attempt_complete"},
        }
    """
    if reason not in VALID_REASONS:
        raise SubmitError(f"invalid reason: {reason}")

    log_ctx = {"module_attempt_id": str(module_attempt_id), "reason": reason}

    # 1. Lock and load
    ma = await _load_module_attempt(db, module_attempt_id)

    log_ctx.update(
        {
            "attempt_id": str(ma["attempt_id"]),
            "user_id": str(ma["user_id"]),
            "stage": ma["stage"],
            "sequence": ma["sequence"],
        }
    )

    if ma["status"] != "in_progress":
        raise SubmitConflict(f"module is {ma['status']}, not in_progress")

    log.info("submit_started", **log_ctx)

    # 2. Grade
    try:
        grade_result = await grade_module(db, module_attempt_id)
    except GradingError as e:
        log.error("grading_failed", error=str(e), **log_ctx)
        raise

    stats = grade_result["stats"]
    total_q = grade_result["total_questions"]
    total_c = grade_result["total_correct"]

    # 3. Weighted score (used by routing on stage 1, stored on both stages)
    threshold = Decimal(str(ma["routing_threshold"] or DEFAULT_THRESHOLD))
    w_e = ma["routing_weight_easy"] or DEFAULT_WEIGHT_EASY
    w_m = ma["routing_weight_medium"] or DEFAULT_WEIGHT_MEDIUM
    w_h = ma["routing_weight_hard"] or DEFAULT_WEIGHT_HARD

    weighted = compute_weighted_score(
        correct_easy=stats["easy"]["correct"],
        correct_medium=stats["medium"]["correct"],
        correct_hard=stats["hard"]["correct"],
        total_easy=stats["easy"]["total"],
        total_medium=stats["medium"]["total"],
        total_hard=stats["hard"]["total"],
        weight_easy=w_e,
        weight_medium=w_m,
        weight_hard=w_h,
    )

    # 4. Stage 1: route and create Stage 2 before the module UPDATE
    next_action: dict | None = None
    if ma["stage"] == 1:
        chosen_level = decide_level(weighted, threshold)
        new_ma_id = await _create_stage2(db, ma, weighted, threshold, chosen_level)

        log.info(
            "routing_decision",
            chosen_level=chosen_level,
            weighted_score=float(weighted),
            threshold=float(threshold),
            **log_ctx,
        )

        next_action = {
            "type": "next_module",
            "module_attempt_id": str(new_ma_id),
            "level": chosen_level,
            "weighted_score": float(weighted),
            "threshold": float(threshold),
        }

    # 5. Mark this module submitted — fires trg_enforce_module_order
    await db.execute(
        text(
            """
            UPDATE module_attempts
               SET status         = 'submitted',
                   submitted_at   = now(),
                   submit_reason  = :reason,
                   question_count = :qcount,
                   correct_count  = :ccount,
                   weighted_score = :wscore
             WHERE id = :id
            """
        ),
        {
            "reason": reason,
            "qcount": total_q,
            "ccount": total_c,
            "wscore": str(weighted),
            "id": str(module_attempt_id),
        },
    )

    # 6. Stage 2: break or complete + score report
    if ma["stage"] == 2:
        next_action = await _handle_break_or_complete(db, ma)
        # Generate score report when attempt is now complete
        if next_action and next_action.get("type") == "attempt_complete":
            try:
                await build_score_report(db, ma["attempt_id"])
            except Exception as exc:
                log.error(
                    "score_report_failed",
                    attempt_id=str(ma["attempt_id"]),
                    error=str(exc),
                )
                # Don't fail the submit — score report failure is non-fatal

    log.info(
        "submit_completed",
        question_count=total_q,
        correct_count=total_c,
        weighted_score=float(weighted),
        next_type=next_action["type"] if next_action else None,
        **log_ctx,
    )

    return {
        "module_attempt_id": str(module_attempt_id),
        "question_count": total_q,
        "correct_count": total_c,
        "weighted_score": float(weighted),
        "next": next_action,
    }