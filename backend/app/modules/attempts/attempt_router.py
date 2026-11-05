"""
attempt_router.py — attempt lifecycle endpoints (start, module start, state, answer, events).

All student-owned operations use app_rw via get_rw_db_with_context (RLS enforced).
User ownership is verified on every request — non-owners get 404, not 403.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency as idem
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.logging import log
from app.deps import get_current_user_id, get_rw_db_with_context

router = APIRouter(prefix="/attempts", tags=["attempt-lifecycle"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response schemas (local to avoid circular imports)
# ─────────────────────────────────────────────────────────────────────────────

class StartAttemptBody(BaseModel):
    test_id: UUID


class StartAttemptResponse(BaseModel):
    attempt_id: UUID
    module_attempt_id: UUID


class StartModuleResponse(BaseModel):
    module_attempt_id: UUID
    status: str
    started_at: datetime | None
    deadline_at: datetime | None


class ChoiceOut(BaseModel):
    id: UUID
    label: str
    content: str
    asset_key: str | None
    position: int


class QuestionOut(BaseModel):
    id: UUID
    section: str
    domain_id: UUID
    skill_id: UUID
    passage_id: UUID | None
    question_type: str
    stem: str
    stem_asset_key: str | None
    difficulty: str
    calculator_allowed: bool
    position: int
    choices: list[ChoiceOut]


class AnswerOut(BaseModel):
    id: UUID
    question_id: UUID
    selected_choice_id: UUID | None
    response_text: str | None
    eliminated_choice_ids: list[UUID]
    is_flagged: bool
    time_spent_ms: int
    visit_count: int
    revision: int
    updated_at: datetime


class PassageOut(BaseModel):
    id: UUID
    content: str
    asset_key: str | None
    source: str | None


class ModuleStateResponse(BaseModel):
    module_attempt_id: UUID
    module_id: UUID
    status: str
    started_at: datetime | None
    deadline_at: datetime | None
    questions: list[QuestionOut]
    passages: dict[str, PassageOut]
    answers: list[AnswerOut]


class SaveAnswerBody(BaseModel):
    question_id: UUID
    selected_choice_id: UUID | None = None
    response_text: str | None = Field(default=None, max_length=30)
    eliminated_choice_ids: list[UUID] = []
    is_flagged: bool = False
    time_spent_ms: int = Field(default=0, ge=0)
    revision: int


class LogEventBody(BaseModel):
    question_id: UUID
    event_type: str
    payload: dict | None = None
    client_ts: datetime | None = None


class EventResponse(BaseModel):
    logged: bool


# ─────────────────────────────────────────────────────────────────────────────
# Ownership guard
# ─────────────────────────────────────────────────────────────────────────────

async def _assert_ma_owner(
    db: AsyncSession, ma_id: UUID, user_id: UUID
) -> dict:
    """Load the module_attempt and verify ownership. Returns the row dict."""
    row = (
        await db.execute(
            text(
                """
                SELECT ma.id, ma.attempt_id, ma.module_id, ma.sequence,
                       ma.status, ma.started_at, ma.deadline_at,
                       ma.submitted_at, ma.user_id,
                       ta.user_id AS ta_user_id,
                       tm.time_limit_sec, tm.question_target,
                       tm.stage, tm.level, tm.section_id
                  FROM module_attempts ma
                  JOIN test_attempts ta ON ta.id = ma.attempt_id
                  JOIN test_modules  tm ON tm.id = ma.module_id
                 WHERE ma.id = :id
                """
            ),
            {"id": str(ma_id)},
        )
    ).mappings().first()

    if row is None or row["ta_user_id"] != user_id:
        raise NotFound()
    return dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# POST /attempts/start
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/start",
    response_model=StartAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_attempt(
    body: StartAttemptBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> StartAttemptResponse:
    """
    Create a new test_attempt + first module_attempt (stage=1, not_started).
    Idempotent when Idempotency-Key is provided.
    """
    endpoint = "start_attempt"
    req_body = {"test_id": str(body.test_id)}

    if idempotency_key:
        is_replay, cached = await idem.lookup(db, user_id, idempotency_key, req_body)
        if is_replay and cached:
            return StartAttemptResponse(**cached["body"])

    # Check for existing in-progress attempt — resume it
    existing = (
        await db.execute(
            text(
                """
                SELECT ta.id AS attempt_id, ma.id AS module_attempt_id
                  FROM test_attempts ta
                  JOIN module_attempts ma ON ma.attempt_id = ta.id
                 WHERE ta.user_id = :uid
                   AND ta.test_id = :tid
                   AND ta.status = 'in_progress'
                   AND ma.status IN ('not_started', 'in_progress')
                 ORDER BY ma.sequence DESC
                 LIMIT 1
                """
            ),
            {"uid": str(user_id), "tid": str(body.test_id)},
        )
    ).mappings().first()

    if existing:
        result = StartAttemptResponse(
            attempt_id=existing["attempt_id"],
            module_attempt_id=existing["module_attempt_id"],
        )
        if idempotency_key:
            await idem.store(
                db, user_id, idempotency_key, endpoint, req_body, 201,
                result.model_dump(mode="json"),
            )
        return result

    # Validate test
    test_row = (
        await db.execute(
            text(
                """
                SELECT id, content_version, status, test_type
                  FROM tests
                 WHERE id = :id
                """
            ),
            {"id": str(body.test_id)},
        )
    ).mappings().first()

    if test_row is None:
        raise NotFound("test not found")
    if test_row["status"] != "published":
        raise BadRequest("test is not published")

    # Find the first section and first stage-1 module
    first_module = (
        await db.execute(
            text(
                """
                SELECT tm.id AS module_id, tm.time_limit_sec, ts.id AS section_id
                  FROM test_sections ts
                  JOIN test_modules  tm ON tm.section_id = ts.id AND tm.stage = 1
                 WHERE ts.test_id = :tid
                 ORDER BY ts.position, tm.stage
                 LIMIT 1
                """
            ),
            {"tid": str(body.test_id)},
        )
    ).mappings().first()

    if first_module is None:
        raise BadRequest("test has no modules")

    # Create test_attempt
    ta_row = (
        await db.execute(
            text(
                """
                INSERT INTO test_attempts
                    (user_id, test_id, test_content_version, status, time_multiplier)
                VALUES (:uid, :tid, :cv, 'in_progress', 1.0)
                RETURNING id
                """
            ),
            {
                "uid": str(user_id),
                "tid": str(body.test_id),
                "cv": test_row["content_version"],
            },
        )
    ).first()
    attempt_id = ta_row[0]

    # Create first module_attempt
    ma_row = (
        await db.execute(
            text(
                """
                INSERT INTO module_attempts
                    (attempt_id, user_id, module_id, sequence, status)
                VALUES (:aid, :uid, :mid, 1, 'not_started')
                RETURNING id
                """
            ),
            {
                "aid": str(attempt_id),
                "uid": str(user_id),
                "mid": str(first_module["module_id"]),
            },
        )
    ).first()
    ma_id = ma_row[0]

    log.info(
        "attempt_started",
        attempt_id=str(attempt_id),
        module_attempt_id=str(ma_id),
        user_id=str(user_id),
        test_id=str(body.test_id),
    )

    result = StartAttemptResponse(attempt_id=attempt_id, module_attempt_id=ma_id)

    if idempotency_key:
        await idem.store(
            db, user_id, idempotency_key, endpoint, req_body, 201,
            result.model_dump(mode="json"),
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# POST /attempts/modules/{ma_id}/start
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/modules/{ma_id}/start",
    response_model=StartModuleResponse,
)
async def start_module(
    ma_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> StartModuleResponse:
    """
    Transition module_attempt to in_progress and set deadline.
    Idempotent: if already in_progress, returns current state.
    """
    ma = await _assert_ma_owner(db, ma_id, user_id)

    if ma["status"] == "in_progress":
        return StartModuleResponse(
            module_attempt_id=ma_id,
            status=ma["status"],
            started_at=ma["started_at"],
            deadline_at=ma["deadline_at"],
        )

    if ma["status"] != "not_started":
        raise Conflict(f"module is already {ma['status']}")

    row = (
        await db.execute(
            text(
                """
                UPDATE module_attempts
                   SET status      = 'in_progress',
                       started_at  = now(),
                       deadline_at = now() + make_interval(secs => :secs)
                 WHERE id = :id
                RETURNING started_at, deadline_at
                """
            ),
            {"secs": ma["time_limit_sec"], "id": str(ma_id)},
        )
    ).first()

    log.info("module_started", module_attempt_id=str(ma_id), user_id=str(user_id))

    return StartModuleResponse(
        module_attempt_id=ma_id,
        status="in_progress",
        started_at=row[0],
        deadline_at=row[1],
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /attempts/modules/{ma_id}/state
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/modules/{ma_id}/state",
    response_model=ModuleStateResponse,
)
async def get_module_state(
    ma_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> ModuleStateResponse:
    """
    Returns questions, existing answers, and deadline.
    NEVER returns correct_choice or explanation for unsubmitted modules.
    """
    ma = await _assert_ma_owner(db, ma_id, user_id)

    # Questions ordered by position
    q_rows = (
        await db.execute(
            text(
                """
                SELECT q.id, q.section, q.domain_id, q.skill_id,
                       q.passage_id, q.question_type, q.stem,
                       q.stem_asset_key, q.difficulty, q.calculator_allowed,
                       mq.position
                  FROM module_questions mq
                  JOIN questions q ON q.id = mq.question_id
                 WHERE mq.module_id = :mid
                 ORDER BY mq.position
                """
            ),
            {"mid": str(ma["module_id"])},
        )
    ).mappings().all()

    question_ids = [r["id"] for r in q_rows]
    if not question_ids:
        raise BadRequest("module has no questions")

    # Choices for all questions (no correct_choice info)
    choice_rows = (
        await db.execute(
            text(
                """
                SELECT id, question_id, label, content, asset_key, position
                  FROM question_choices
                 WHERE question_id = ANY(:qids)
                 ORDER BY question_id, position
                """
            ),
            {"qids": question_ids},
        )
    ).mappings().all()

    choices_by_q: dict[UUID, list[ChoiceOut]] = {}
    for c in choice_rows:
        choices_by_q.setdefault(c["question_id"], []).append(
            ChoiceOut(
                id=c["id"],
                label=c["label"],
                content=c["content"],
                asset_key=c["asset_key"],
                position=c["position"],
            )
        )

    # Passages
    passage_ids = list({r["passage_id"] for r in q_rows if r["passage_id"]})
    passages: dict[str, PassageOut] = {}
    if passage_ids:
        p_rows = (
            await db.execute(
                text(
                    """
                    SELECT id, content, asset_key, source
                      FROM passages
                     WHERE id = ANY(:pids)
                    """
                ),
                {"pids": passage_ids},
            )
        ).mappings().all()
        for p in p_rows:
            passages[str(p["id"])] = PassageOut(
                id=p["id"],
                content=p["content"],
                asset_key=p["asset_key"],
                source=p["source"],
            )

    questions = [
        QuestionOut(
            id=r["id"],
            section=r["section"],
            domain_id=r["domain_id"],
            skill_id=r["skill_id"],
            passage_id=r["passage_id"],
            question_type=r["question_type"],
            stem=r["stem"],
            stem_asset_key=r["stem_asset_key"],
            difficulty=r["difficulty"],
            calculator_allowed=r["calculator_allowed"],
            position=r["position"],
            choices=choices_by_q.get(r["id"], []),
        )
        for r in q_rows
    ]

    # Existing answers
    ans_rows = (
        await db.execute(
            text(
                """
                SELECT id, question_id, selected_choice_id, response_text,
                       eliminated_choice_ids, is_flagged,
                       time_spent_ms, visit_count, revision, updated_at
                  FROM answers
                 WHERE module_attempt_id = :ma_id
                """
            ),
            {"ma_id": str(ma_id)},
        )
    ).mappings().all()

    answers = [
        AnswerOut(
            id=r["id"],
            question_id=r["question_id"],
            selected_choice_id=r["selected_choice_id"],
            response_text=r["response_text"],
            eliminated_choice_ids=r["eliminated_choice_ids"] or [],
            is_flagged=r["is_flagged"],
            time_spent_ms=r["time_spent_ms"],
            visit_count=r["visit_count"],
            revision=r["revision"],
            updated_at=r["updated_at"],
        )
        for r in ans_rows
    ]

    return ModuleStateResponse(
        module_attempt_id=ma_id,
        module_id=ma["module_id"],
        status=ma["status"],
        started_at=ma["started_at"],
        deadline_at=ma["deadline_at"],
        questions=questions,
        passages=passages,
        answers=answers,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /attempts/modules/{ma_id}/answer
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/modules/{ma_id}/answer",
    response_model=AnswerOut,
)
async def save_answer(
    ma_id: UUID,
    body: SaveAnswerBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> AnswerOut:
    """
    Upsert one answer. Rejects if module is not in_progress or past deadline.
    Optimistic concurrency: rejects if submitted revision <= stored revision.
    """
    ma = await _assert_ma_owner(db, ma_id, user_id)

    if ma["status"] != "in_progress":
        raise Conflict(f"module is {ma['status']}, not in_progress")

    # Deadline enforcement (2-second grace)
    if ma["deadline_at"]:
        deadline = ma["deadline_at"]
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now.timestamp() > deadline.timestamp() + 2:
            raise Conflict("module deadline has passed")

    # Load the question to get section/domain/skill/difficulty
    q_row = (
        await db.execute(
            text(
                """
                SELECT q.section, q.domain_id, q.skill_id, q.difficulty
                  FROM questions q
                  JOIN module_questions mq ON mq.question_id = q.id
                 WHERE q.id = :qid
                   AND mq.module_id = :mid
                """
            ),
            {"qid": str(body.question_id), "mid": str(ma["module_id"])},
        )
    ).mappings().first()

    if q_row is None:
        raise NotFound("question not found in this module")

    # Check existing revision
    existing = (
        await db.execute(
            text(
                "SELECT id, revision FROM answers "
                "WHERE module_attempt_id = :ma_id AND question_id = :qid"
            ),
            {"ma_id": str(ma_id), "qid": str(body.question_id)},
        )
    ).mappings().first()

    if existing and body.revision <= existing["revision"]:
        raise Conflict(
            f"revision {body.revision} is not greater than stored {existing['revision']}"
        )

    # Upsert
    # Note: :has_choice and :has_text are separate boolean params to avoid
    # asyncpg "could not determine data type" when the same param is used in
    # both a typed (column) and untyped (IS NOT NULL) context.
    row = (
        await db.execute(
            text(
                """
                INSERT INTO answers
                    (module_attempt_id, question_id, user_id, section,
                     domain_id, skill_id, difficulty,
                     selected_choice_id, response_text, eliminated_choice_ids,
                     is_flagged, time_spent_ms, revision, first_answered_at, visit_count)
                VALUES
                    (:ma_id, :qid, :uid, :section,
                     :domain_id, :skill_id, :difficulty,
                     :choice_id, :resp_text, :elim_ids,
                     :flagged, :time_ms, :revision,
                     CASE WHEN :has_choice OR :has_text
                          THEN now() ELSE NULL END,
                     1)
                ON CONFLICT (module_attempt_id, question_id)
                DO UPDATE SET
                    selected_choice_id   = EXCLUDED.selected_choice_id,
                    response_text        = EXCLUDED.response_text,
                    eliminated_choice_ids= EXCLUDED.eliminated_choice_ids,
                    is_flagged           = EXCLUDED.is_flagged,
                    time_spent_ms        = EXCLUDED.time_spent_ms,
                    revision             = EXCLUDED.revision,
                    visit_count          = answers.visit_count + 1,
                    first_answered_at    = COALESCE(answers.first_answered_at,
                        CASE WHEN EXCLUDED.selected_choice_id IS NOT NULL
                                  OR EXCLUDED.response_text IS NOT NULL
                             THEN now() ELSE NULL END),
                    updated_at           = now()
                RETURNING id, question_id, selected_choice_id, response_text,
                          eliminated_choice_ids, is_flagged,
                          time_spent_ms, visit_count, revision, updated_at
                """
            ),
            {
                "ma_id": str(ma_id),
                "qid": str(body.question_id),
                "uid": str(user_id),
                "section": q_row["section"],
                "domain_id": str(q_row["domain_id"]),
                "skill_id": str(q_row["skill_id"]),
                "difficulty": q_row["difficulty"],
                "choice_id": str(body.selected_choice_id) if body.selected_choice_id else None,
                "resp_text": body.response_text,
                "elim_ids": [str(x) for x in body.eliminated_choice_ids],
                "flagged": body.is_flagged,
                "time_ms": body.time_spent_ms,
                "revision": body.revision,
                "has_choice": body.selected_choice_id is not None,
                "has_text": body.response_text is not None,
            },
        )
    ).mappings().first()

    return AnswerOut(
        id=row["id"],
        question_id=row["question_id"],
        selected_choice_id=row["selected_choice_id"],
        response_text=row["response_text"],
        eliminated_choice_ids=row["eliminated_choice_ids"] or [],
        is_flagged=row["is_flagged"],
        time_spent_ms=row["time_spent_ms"],
        visit_count=row["visit_count"],
        revision=row["revision"],
        updated_at=row["updated_at"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /attempts/modules/{ma_id}/events
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/modules/{ma_id}/events",
    response_model=EventResponse,
)
async def log_event(
    ma_id: UUID,
    body: LogEventBody,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_rw_db_with_context),
) -> EventResponse:
    """
    Log a student interaction event via the SECURITY DEFINER function.
    """
    ma = await _assert_ma_owner(db, ma_id, user_id)

    # The log_answer_event function is SECURITY DEFINER — call it via SELECT
    await db.execute(
        text(
            """
            SELECT log_answer_event(
                :ma_id::uuid,
                :qid::uuid,
                :event_type,
                :payload::jsonb,
                :client_ts
            )
            """
        ),
        {
            "ma_id": str(ma_id),
            "qid": str(body.question_id),
            "event_type": body.event_type,
            "payload": str(body.payload) if body.payload else "{}",
            "client_ts": body.client_ts,
        },
    )

    return EventResponse(logged=True)
