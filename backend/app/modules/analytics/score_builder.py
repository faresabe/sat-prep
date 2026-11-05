"""
score_builder.py — build or rebuild a score report for a completed attempt.

Runs synchronously inside the submit transaction (no background worker).
Uses the grader session (BYPASSRLS) so it can write to score_reports,
domain_results, skill_results, and the rolling user_*_stats tables.

Idempotent: if a score_report already exists for the attempt,
its children are deleted and re-inserted in the same transaction.
"""
from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log

SCORING_VERSION = "v1"


async def build_score_report(db: AsyncSession, attempt_id: UUID) -> UUID:
    """
    Build the score report for a completed attempt.

    Steps:
      1. Load all answers joined to questions (skill_id, domain_id, difficulty).
      2. Aggregate rw_raw, domain_results, skill_results.
      3. Find the routing decision to get rw_stage2_level.
      4. Upsert score_reports (idempotent via delete-children approach).
      5. Insert domain_results and skill_results.
      6. Upsert user_skill_stats, user_domain_stats, user_stats.

    Returns the score_report.id.
    """
    log.info("score_report_building", attempt_id=str(attempt_id))

    # ── 1. Load answers with metadata ────────────────────────────────────────
    rows = (
        await db.execute(
            text(
                """
                SELECT a.id, a.question_id, a.skill_id, a.domain_id,
                       a.difficulty, a.is_correct, a.time_spent_ms,
                       a.selected_choice_id, a.response_text
                  FROM answers a
                  JOIN module_attempts ma ON ma.id = a.module_attempt_id
                 WHERE ma.attempt_id = :aid
                """
            ),
            {"aid": str(attempt_id)},
        )
    ).mappings().all()

    # ── 2. Load attempt owner ────────────────────────────────────────────────
    ta = (
        await db.execute(
            text("SELECT user_id FROM test_attempts WHERE id = :aid"),
            {"aid": str(attempt_id)},
        )
    ).mappings().first()

    if ta is None:
        raise ValueError(f"attempt {attempt_id} not found")

    user_id: UUID = ta["user_id"]

    # ── 3. Find routing decision for stage2_level ────────────────────────────
    routing = (
        await db.execute(
            text(
                """
                SELECT rd.chosen_level
                  FROM routing_decisions rd
                  JOIN module_attempts   ma ON ma.id = rd.from_module_attempt_id
                 WHERE ma.attempt_id = :aid
                 LIMIT 1
                """
            ),
            {"aid": str(attempt_id)},
        )
    ).first()
    rw_stage2_level = routing[0] if routing else None

    # ── 4. Aggregate ─────────────────────────────────────────────────────────
    rw_raw = sum(1 for r in rows if r["is_correct"] is True)

    # Per-domain
    domain_agg: dict[UUID, dict] = {}
    for r in rows:
        d = domain_agg.setdefault(
            r["domain_id"],
            {"total": 0, "correct": 0, "unanswered": 0, "time_ms": []},
        )
        d["total"] += 1
        if r["is_correct"] is True:
            d["correct"] += 1
        if r["selected_choice_id"] is None and r["response_text"] is None:
            d["unanswered"] += 1
        if r["time_spent_ms"]:
            d["time_ms"].append(r["time_spent_ms"])

    # Per-skill (with per-difficulty breakdown)
    skill_agg: dict[UUID, dict] = {}
    for r in rows:
        s = skill_agg.setdefault(
            r["skill_id"],
            {
                "domain_id": r["domain_id"],
                "total": 0, "correct": 0, "unanswered": 0, "time_ms": [],
                "easy_total": 0, "easy_correct": 0,
                "medium_total": 0, "medium_correct": 0,
                "hard_total": 0, "hard_correct": 0,
            },
        )
        s["total"] += 1
        diff = r["difficulty"]
        s[f"{diff}_total"] += 1
        if r["is_correct"] is True:
            s["correct"] += 1
            s[f"{diff}_correct"] += 1
        if r["selected_choice_id"] is None and r["response_text"] is None:
            s["unanswered"] += 1
        if r["time_spent_ms"]:
            s["time_ms"].append(r["time_spent_ms"])

    # ── 5. Upsert score_report ───────────────────────────────────────────────
    existing = (
        await db.execute(
            text("SELECT id FROM score_reports WHERE attempt_id = :aid"),
            {"aid": str(attempt_id)},
        )
    ).first()

    report_id: UUID
    if existing:
        report_id = existing[0]
        # Delete children (cascades would also work but explicit is safer)
        await db.execute(
            text("DELETE FROM domain_results WHERE report_id = :rid"),
            {"rid": str(report_id)},
        )
        await db.execute(
            text("DELETE FROM skill_results WHERE report_id = :rid"),
            {"rid": str(report_id)},
        )
        await db.execute(
            text(
                """
                UPDATE score_reports
                   SET rw_raw         = :rw_raw,
                       rw_stage2_level= :stage2_level,
                       scoring_version= :version,
                       generated_at   = now()
                 WHERE id = :rid
                """
            ),
            {
                "rw_raw": rw_raw,
                "stage2_level": rw_stage2_level,
                "version": SCORING_VERSION,
                "rid": str(report_id),
            },
        )
    else:
        r = (
            await db.execute(
                text(
                    """
                    INSERT INTO score_reports
                        (attempt_id, user_id, rw_raw, rw_stage2_level, scoring_version)
                    VALUES (:aid, :uid, :rw_raw, :stage2_level, :version)
                    RETURNING id
                    """
                ),
                {
                    "aid": str(attempt_id),
                    "uid": str(user_id),
                    "rw_raw": rw_raw,
                    "stage2_level": rw_stage2_level,
                    "version": SCORING_VERSION,
                },
            )
        ).first()
        report_id = r[0]

    # ── 6. Insert domain_results ─────────────────────────────────────────────
    for domain_id, d in domain_agg.items():
        accuracy = round(d["correct"] / d["total"] * 100, 2) if d["total"] else 0.0
        avg_time = int(sum(d["time_ms"]) / len(d["time_ms"])) if d["time_ms"] else None
        await db.execute(
            text(
                """
                INSERT INTO domain_results
                    (report_id, domain_id, total, correct, unanswered, accuracy, avg_time_ms)
                VALUES (:rid, :did, :total, :correct, :unanswered, :accuracy, :avg_time)
                """
            ),
            {
                "rid": str(report_id),
                "did": str(domain_id),
                "total": d["total"],
                "correct": d["correct"],
                "unanswered": d["unanswered"],
                "accuracy": accuracy,
                "avg_time": avg_time,
            },
        )

    # ── 7. Insert skill_results ──────────────────────────────────────────────
    for skill_id, s in skill_agg.items():
        accuracy = round(s["correct"] / s["total"] * 100, 2) if s["total"] else 0.0
        avg_time = int(sum(s["time_ms"]) / len(s["time_ms"])) if s["time_ms"] else None
        await db.execute(
            text(
                """
                INSERT INTO skill_results
                    (report_id, skill_id, domain_id,
                     total, correct, unanswered, accuracy, avg_time_ms,
                     easy_total, easy_correct,
                     medium_total, medium_correct,
                     hard_total, hard_correct)
                VALUES
                    (:rid, :sid, :did,
                     :total, :correct, :unanswered, :accuracy, :avg_time,
                     :et, :ec, :mt, :mc, :ht, :hc)
                """
            ),
            {
                "rid": str(report_id),
                "sid": str(skill_id),
                "did": str(s["domain_id"]),
                "total": s["total"],
                "correct": s["correct"],
                "unanswered": s["unanswered"],
                "accuracy": accuracy,
                "avg_time": avg_time,
                "et": s["easy_total"],
                "ec": s["easy_correct"],
                "mt": s["medium_total"],
                "mc": s["medium_correct"],
                "ht": s["hard_total"],
                "hc": s["hard_correct"],
            },
        )

    # ── 8. Upsert user_skill_stats ───────────────────────────────────────────
    for skill_id, s in skill_agg.items():
        avg_time = int(sum(s["time_ms"]) / len(s["time_ms"])) if s["time_ms"] else None
        await db.execute(
            text(
                """
                INSERT INTO user_skill_stats
                    (user_id, skill_id, total_answered, total_correct, avg_time_ms,
                     last_practiced_at)
                VALUES (:uid, :sid, :total, :correct, :avg_time, now())
                ON CONFLICT (user_id, skill_id) DO UPDATE SET
                    total_answered    = user_skill_stats.total_answered + EXCLUDED.total_answered,
                    total_correct     = user_skill_stats.total_correct  + EXCLUDED.total_correct,
                    avg_time_ms       = COALESCE(EXCLUDED.avg_time_ms, user_skill_stats.avg_time_ms),
                    last_practiced_at = now(),
                    updated_at        = now()
                """
            ),
            {
                "uid": str(user_id),
                "sid": str(skill_id),
                "total": s["total"],
                "correct": s["correct"],
                "avg_time": avg_time,
            },
        )

    # ── 9. Upsert user_domain_stats ──────────────────────────────────────────
    for domain_id, d in domain_agg.items():
        avg_time = int(sum(d["time_ms"]) / len(d["time_ms"])) if d["time_ms"] else None
        await db.execute(
            text(
                """
                INSERT INTO user_domain_stats
                    (user_id, domain_id, total_answered, total_correct, avg_time_ms,
                     last_practiced_at)
                VALUES (:uid, :did, :total, :correct, :avg_time, now())
                ON CONFLICT (user_id, domain_id) DO UPDATE SET
                    total_answered    = user_domain_stats.total_answered + EXCLUDED.total_answered,
                    total_correct     = user_domain_stats.total_correct  + EXCLUDED.total_correct,
                    avg_time_ms       = COALESCE(EXCLUDED.avg_time_ms, user_domain_stats.avg_time_ms),
                    last_practiced_at = now(),
                    updated_at        = now()
                """
            ),
            {
                "uid": str(user_id),
                "did": str(domain_id),
                "total": d["total"],
                "correct": d["correct"],
                "avg_time": avg_time,
            },
        )

    # ── 10. Upsert user_stats ────────────────────────────────────────────────
    total_q = len(rows)
    await db.execute(
        text(
            """
            INSERT INTO user_stats
                (user_id, attempts_completed, questions_answered,
                 questions_correct, latest_total_score, last_attempt_at)
            VALUES (:uid, 1, :total_q, :correct, :score, now())
            ON CONFLICT (user_id) DO UPDATE SET
                attempts_completed  = user_stats.attempts_completed + 1,
                questions_answered  = user_stats.questions_answered + EXCLUDED.questions_answered,
                questions_correct   = user_stats.questions_correct  + EXCLUDED.questions_correct,
                latest_total_score  = EXCLUDED.latest_total_score,
                best_total_score    = GREATEST(
                                        COALESCE(user_stats.best_total_score, 0),
                                        EXCLUDED.latest_total_score),
                last_attempt_at     = now(),
                updated_at          = now()
            """
        ),
        {"uid": str(user_id), "total_q": total_q, "correct": rw_raw, "score": rw_raw},
    )

    log.info(
        "score_report_built",
        attempt_id=str(attempt_id),
        report_id=str(report_id),
        rw_raw=rw_raw,
        rw_stage2_level=rw_stage2_level,
    )

    return report_id
