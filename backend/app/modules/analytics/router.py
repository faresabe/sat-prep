"""
analytics/router.py — student analytics endpoints.

All read from app_rw with RLS context (only the calling user's data).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user_id, get_rw_db_with_context

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    total_attempts: int
    best_score: int | None
    latest_score: int | None
    latest_attempt_id: UUID | None
    overall_accuracy: float | None


class SkillStat(BaseModel):
    skill_id: UUID
    skill_code: str
    skill_name: str
    domain: str
    total: int
    correct: int
    accuracy_pct: float | None


class DomainStat(BaseModel):
    domain_id: UUID
    domain_code: str
    domain_name: str
    total: int
    correct: int
    accuracy_pct: float | None


class AttemptHistoryItem(BaseModel):
    attempt_id: UUID
    started_at: str
    completed_at: str | None
    rw_raw: int | None
    rw_scaled: int | None
    stage2_level: str | None


# ─────────────────────────────────────────────────────────────────────────────
# GET /analytics/me
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
async def get_me(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> MeResponse:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    us.attempts_completed,
                    us.best_total_score,
                    us.latest_total_score,
                    us.questions_answered,
                    us.questions_correct,
                    (
                        SELECT ta.id
                          FROM test_attempts ta
                         WHERE ta.user_id = :uid
                           AND ta.status = 'completed'
                         ORDER BY ta.completed_at DESC NULLS LAST
                         LIMIT 1
                    ) AS latest_attempt_id
                  FROM user_stats us
                 WHERE us.user_id = :uid
                """
            ),
            {"uid": str(user_id)},
        )
    ).mappings().first()

    if row is None:
        return MeResponse(
            total_attempts=0,
            best_score=None,
            latest_score=None,
            latest_attempt_id=None,
            overall_accuracy=None,
        )

    accuracy: float | None = None
    if row["questions_answered"] and row["questions_answered"] > 0:
        accuracy = round(
            row["questions_correct"] / row["questions_answered"] * 100, 1
        )

    return MeResponse(
        total_attempts=row["attempts_completed"],
        best_score=row["best_total_score"],
        latest_score=row["latest_total_score"],
        latest_attempt_id=row["latest_attempt_id"],
        overall_accuracy=accuracy,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /analytics/me/skills
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/me/skills", response_model=list[SkillStat])
async def get_skill_stats(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> list[SkillStat]:
    rows = (
        await db.execute(
            text(
                """
                SELECT uss.skill_id,
                       s.code        AS skill_code,
                       s.name        AS skill_name,
                       d.name        AS domain,
                       uss.total_answered AS total,
                       uss.total_correct  AS correct,
                       CASE WHEN uss.total_answered > 0
                            THEN ROUND(uss.total_correct::numeric
                                       / uss.total_answered * 100, 1)
                            ELSE NULL
                       END AS accuracy_pct
                  FROM user_skill_stats uss
                  JOIN skills  s ON s.id = uss.skill_id
                  JOIN domains d ON d.id = s.domain_id
                 WHERE uss.user_id = :uid
                 ORDER BY accuracy_pct ASC NULLS LAST, total DESC
                """
            ),
            {"uid": str(user_id)},
        )
    ).mappings().all()

    return [
        SkillStat(
            skill_id=r["skill_id"],
            skill_code=r["skill_code"],
            skill_name=r["skill_name"],
            domain=r["domain"],
            total=r["total"],
            correct=r["correct"],
            accuracy_pct=float(r["accuracy_pct"]) if r["accuracy_pct"] is not None else None,
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# GET /analytics/me/domains
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/me/domains", response_model=list[DomainStat])
async def get_domain_stats(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> list[DomainStat]:
    rows = (
        await db.execute(
            text(
                """
                SELECT uds.domain_id,
                       d.code AS domain_code,
                       d.name AS domain_name,
                       uds.total_answered AS total,
                       uds.total_correct  AS correct,
                       CASE WHEN uds.total_answered > 0
                            THEN ROUND(uds.total_correct::numeric
                                       / uds.total_answered * 100, 1)
                            ELSE NULL
                       END AS accuracy_pct
                  FROM user_domain_stats uds
                  JOIN domains d ON d.id = uds.domain_id
                 WHERE uds.user_id = :uid
                 ORDER BY accuracy_pct ASC NULLS LAST, total DESC
                """
            ),
            {"uid": str(user_id)},
        )
    ).mappings().all()

    return [
        DomainStat(
            domain_id=r["domain_id"],
            domain_code=r["domain_code"],
            domain_name=r["domain_name"],
            total=r["total"],
            correct=r["correct"],
            accuracy_pct=float(r["accuracy_pct"]) if r["accuracy_pct"] is not None else None,
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# GET /analytics/me/attempts
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/me/attempts", response_model=list[AttemptHistoryItem])
async def get_attempt_history(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> list[AttemptHistoryItem]:
    rows = (
        await db.execute(
            text(
                """
                SELECT ta.id          AS attempt_id,
                       ta.started_at,
                       ta.completed_at,
                       sr.rw_raw,
                       sr.rw_scaled,
                       sr.rw_stage2_level AS stage2_level
                  FROM test_attempts ta
                  LEFT JOIN score_reports sr ON sr.attempt_id = ta.id
                 WHERE ta.user_id = :uid
                 ORDER BY ta.started_at DESC
                 LIMIT 50
                """
            ),
            {"uid": str(user_id)},
        )
    ).mappings().all()

    return [
        AttemptHistoryItem(
            attempt_id=r["attempt_id"],
            started_at=r["started_at"].isoformat(),
            completed_at=r["completed_at"].isoformat() if r["completed_at"] else None,
            rw_raw=r["rw_raw"],
            rw_scaled=r["rw_scaled"],
            stage2_level=r["stage2_level"],
        )
        for r in rows
    ]
