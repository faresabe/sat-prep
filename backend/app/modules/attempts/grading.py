"""
grading.py — grade every answer in a module attempt.

Runs as app_grader (has BYPASSRLS and write access to is_correct).
All functions take an AsyncSession and DO NOT commit — the caller owns
the transaction. This module is deliberately free of business orchestration.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log


class GradingError(Exception):
    """Raised when grading cannot proceed (bad data, unexpected state)."""


# ---------------------------------------------------------------------------
# 1. Multiple-choice grading
# ---------------------------------------------------------------------------

async def grade_multiple_choice(db: AsyncSession, module_attempt_id: UUID) -> int:
    """
    Set is_correct for MC answers that haven't been graded yet.
    Returns the number of rows updated.
    """
    result = await db.execute(
        text(
            """
            UPDATE answers a
               SET is_correct = (a.selected_choice_id = k.correct_choice_id)
              FROM grading.question_keys k
             WHERE k.question_id = a.question_id
               AND a.module_attempt_id = :ma_id
               AND a.selected_choice_id IS NOT NULL
               AND a.is_correct IS NULL
            """
        ),
        {"ma_id": str(module_attempt_id)},
    )
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# 2. Grid-in grading — done in Python, not SQL
# ---------------------------------------------------------------------------
#
# Why Python: the DB trigger allows response_text like "1/2", ".5", "0.5".
# A regex in SQL is fragile and slow. We fetch the accepted answers for the
# questions in this module, parse both sides, and write the boolean back.
#
# The accepted-answer set is small (usually 1-3 per question), so the extra
# round trip is cheap.

def _parse_numeric(raw: str | None) -> Decimal | None:
    """
    Parse an SAT-style grid-in string into a Decimal, or None if unparseable.

    Handles: "5", "5.0", ".5", "0.5", "-3", "1/2", "-7/8".
    """
    if raw is None:
        return None
    s = raw.strip().replace(",", "")
    if not s:
        return None
    try:
        if "/" in s:
            num, den = s.split("/", 1)
            n = Decimal(num)
            d = Decimal(den)
            if d == 0:
                return None
            return n / d
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


async def grade_grid_in(db: AsyncSession, module_attempt_id: UUID) -> int:
    """
    Grade grid-in answers. For each ungraded row:
      - compare response_text against raw_value (exact string match), OR
      - compare parsed numeric values (with small tolerance), OR
      - if accepted.numeric_value is NULL, fall back to raw match only.
    Returns the number of rows updated.
    """
    # Load ungraded grid-in rows with their accepted answers
    rows = (
        await db.execute(
            text(
                """
                SELECT a.id AS answer_id,
                       a.question_id,
                       a.response_text
                  FROM answers a
                 WHERE a.module_attempt_id = :ma_id
                   AND a.response_text IS NOT NULL
                   AND a.is_correct IS NULL
                """
            ),
            {"ma_id": str(module_attempt_id)},
        )
    ).mappings().all()

    if not rows:
        return 0

    question_ids = list({r["question_id"] for r in rows})

    accepted_rows = (
        await db.execute(
            text(
                """
                SELECT question_id, raw_value, numeric_value
                  FROM grading.spr_accepted_answers
                 WHERE question_id = ANY(:qids)
                """
            ),
            {"qids": question_ids},
        )
    ).mappings().all()

    accepted: dict[UUID, list[dict]] = {}
    for r in accepted_rows:
        accepted.setdefault(r["question_id"], []).append(dict(r))

    updated = 0
    for row in rows:
        qid = row["question_id"]
        student_raw = row["response_text"]
        student_num = _parse_numeric(student_raw)

        is_correct = False
        for a in accepted.get(qid, []):
            # Exact raw match
            if a["raw_value"] == student_raw:
                is_correct = True
                break
            # Numeric match with tolerance
            if a["numeric_value"] is not None and student_num is not None:
                if abs(Decimal(a["numeric_value"]) - student_num) <= Decimal("0.0001"):
                    is_correct = True
                    break

        await db.execute(
            text("UPDATE answers SET is_correct = :ok WHERE id = :id"),
            {"ok": is_correct, "id": row["answer_id"]},
        )
        updated += 1

    return updated


# ---------------------------------------------------------------------------
# 3. Difficulty stats — used by routing
# ---------------------------------------------------------------------------

async def load_difficulty_stats(
    db: AsyncSession, module_attempt_id: UUID
) -> dict[str, dict[str, int]]:
    """
    Return {"easy": {"correct": n, "total": n}, "medium": ..., "hard": ...}.

    'total' counts ALL questions assigned to the module (from module_questions),
    so unanswered questions are included. 'correct' counts only rows where
    is_correct = TRUE. Unanswered = wrong by convention.
    """
    # Totals from module_questions JOIN questions (all questions in the module)
    total_rows = (
        await db.execute(
            text(
                """
                SELECT q.difficulty, COUNT(*) AS total
                  FROM module_questions mq
                  JOIN questions q ON q.id = mq.question_id
                 WHERE mq.module_id = (
                     SELECT module_id FROM module_attempts WHERE id = :ma_id
                 )
                 GROUP BY q.difficulty
                """
            ),
            {"ma_id": str(module_attempt_id)},
        )
    ).all()

    # Correct counts from answers (only answered + graded questions)
    correct_rows = (
        await db.execute(
            text(
                """
                SELECT q.difficulty, COUNT(*) AS correct
                  FROM answers a
                  JOIN questions q ON q.id = a.question_id
                 WHERE a.module_attempt_id = :ma_id
                   AND a.is_correct = TRUE
                 GROUP BY q.difficulty
                """
            ),
            {"ma_id": str(module_attempt_id)},
        )
    ).all()

    stats = {
        "easy": {"correct": 0, "total": 0},
        "medium": {"correct": 0, "total": 0},
        "hard": {"correct": 0, "total": 0},
    }
    for difficulty, total in total_rows:
        if difficulty in stats:
            stats[difficulty]["total"] = total or 0
    for difficulty, correct in correct_rows:
        if difficulty in stats:
            stats[difficulty]["correct"] = correct or 0
    return stats


# ---------------------------------------------------------------------------
# 4. One-shot: grade everything and return counts
# ---------------------------------------------------------------------------

async def grade_module(db: AsyncSession, module_attempt_id: UUID) -> dict:
    """
    Runs both grading steps, then returns stats.

    Idempotent: rows already graded (is_correct NOT NULL) are untouched.

    Returns:
        {
          "mc_graded": int,
          "grid_graded": int,
          "stats": {"easy": {...}, "medium": {...}, "hard": {...}},
          "total_correct": int,
          "total_questions": int,
        }
    """
    mc_count = await grade_multiple_choice(db, module_attempt_id)
    grid_count = await grade_grid_in(db, module_attempt_id)

    stats = await load_difficulty_stats(db, module_attempt_id)
    total_correct = sum(stats[k]["correct"] for k in stats)
    total_questions = sum(stats[k]["total"] for k in stats)

    log.info(
        "module_graded",
        module_attempt_id=str(module_attempt_id),
        mc_graded=mc_count,
        grid_graded=grid_count,
        total_correct=total_correct,
        total_questions=total_questions,
    )

    return {
        "mc_graded": mc_count,
        "grid_graded": grid_count,
        "stats": stats,
        "total_correct": total_correct,
        "total_questions": total_questions,
    }