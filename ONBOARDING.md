# SAT Prep Platform — Senior Engineer Onboarding Guide

---

## 1. HIGH-LEVEL OVERVIEW

### What is it?

A **digital SAT practice platform** that replicates the College Board's Bluebook adaptive test engine. Students take a two-module adaptive Reading & Writing (RW) test where their performance on Module 1 determines whether they get an easy or hard Module 2 — exactly how the real SAT works. After completing both modules, a score report is generated and a skills/domain analytics dashboard shows weaknesses.

### Architecture

```
Browser (localhost:5173)
│
│  React 18 + Vite + TypeScript + Tailwind
│  TanStack Query (server state) + Zustand (session state)
│  Axios (HTTP, auto-attaches X-User-Id + Idempotency-Key)
│
│  HTTP/REST (CORS allowed from :8000)
▼
FastAPI (localhost:8000, Python 3.12)
│
├── attempt_router.py    POST/GET lifecycle endpoints   ──── app_rw (NOBYPASSRLS)
├── router.py            POST submit endpoint           ──── app_grader (BYPASSRLS)
└── analytics/router.py  GET analytics endpoints        ──── app_rw (NOBYPASSRLS)
│
│  asyncpg + SQLAlchemy 2.0 async
▼
PostgreSQL 16 (satprep database, localhost:5432)
│
├── public schema          40 tables, 51 RLS policies, 16 triggers
└── grading schema         question_keys, spr_accepted_answers, question_explanations
                           (only app_grader and app_content_admin can read)

Off-line data pipeline (not running at runtime):
webscraper_bluebook/scraper.py → SAT_Downloads/*.json
→ canonicalize.py → canonical/questions.jsonl (3312 questions)
→ import.py → inserts into PostgreSQL
→ build_rw_test.py → creates the test structure from configs/rw_demo.yaml
```

### Tech Stack

| Layer | Choice |
|-------|--------|
| Frontend language | TypeScript |
| Frontend framework | React 18 |
| Build tool | Vite 6 |
| Styling | Tailwind CSS 3 |
| Server state | TanStack Query (React Query) v5 |
| Client state | Zustand v5 |
| Charts | Recharts |
| HTTP client | Axios 1.7 |
| Backend language | Python 3.12 |
| Backend framework | FastAPI 0.115 |
| ASGI server | Uvicorn + uvloop |
| ORM | SQLAlchemy 2.0 async |
| DB driver | asyncpg |
| Migrations | Alembic (baseline-only; schema from SQL script) |
| Logging | structlog |
| Validation | Pydantic v2 |
| DB | PostgreSQL 16 |
| Frontend tests | Vitest + Testing Library + MSW |
| Backend tests | pytest-asyncio |

---

## 2. REPO LAYOUT

```
bluebook_style/
├── backend/                    Python FastAPI app
│   ├── app/
│   │   ├── main.py             ← ENTRY POINT: app factory, middleware, router registration
│   │   ├── config.py           Pydantic Settings (reads .env)
│   │   ├── db.py               Two SQLAlchemy engine pools (app_rw + app_grader)
│   │   ├── deps.py             FastAPI dependencies: get_current_user_id, get_rw_db_with_context
│   │   ├── core/
│   │   │   ├── errors.py       Typed exception hierarchy (NotFound, Conflict, BadRequest…)
│   │   │   ├── idempotency.py  Reusable lookup/store helpers for Idempotency-Key header
│   │   │   └── logging.py      structlog configuration (dev=ConsoleRenderer, prod=JSON)
│   │   ├── models/             SQLAlchemy ORM models (20 files) — NOT used for queries
│   │   ├── modules/
│   │   │   ├── attempts/
│   │   │   │   ├── attempt_router.py  ← Lifecycle endpoints (start, state, answer)
│   │   │   │   ├── router.py          ← Submit endpoint (grader role)
│   │   │   │   ├── service.py         ← Submit orchestration logic
│   │   │   │   ├── grading.py         ← MC + grid-in grading functions
│   │   │   │   └── routing.py         ← Weighted score + routing algorithm
│   │   │   ├── analytics/
│   │   │   │   ├── router.py          Analytics endpoints (me, skills, domains, attempts)
│   │   │   │   └── score_builder.py   Score report aggregation pipeline
│   │   │   └── tests/                 (empty — placeholder for future test management)
│   │   ├── repositories/       (empty placeholder)
│   │   ├── schemas/            Pydantic schemas (some defined locally in routers instead)
│   │   └── services/           (empty placeholder)
│   ├── alembic/
│   │   └── versions/16d93f12d518_baseline.py  Stub migration — schema from SQL script
│   ├── scripts/                14 dev/ops utility scripts
│   ├── sat_db_build_all.sql    Full DB DDL: roles, schema, tables, triggers, RLS, seeds
│   ├── pyproject.toml
│   └── .env                    DATABASE_URL, DATABASE_URL_MIGRATION, DATABASE_URL_GRADER, JWT_SECRET
│
├── frontend/                   React app
│   ├── src/
│   │   ├── main.tsx            ← ENTRY POINT: React root, QueryClientProvider
│   │   ├── App.tsx             RouterProvider wrapper
│   │   ├── router.tsx          All routes (/, /take/:maId, /break, /result, /dashboard)
│   │   ├── api/
│   │   │   ├── client.ts       Axios instance + interceptors (X-User-Id, Idempotency-Key)
│   │   │   ├── attempts.ts     5 API functions (startAttempt, startModule, getModuleState…)
│   │   │   └── analytics.ts    4 API functions (getMe, getSkillStats, getDomainStats…)
│   │   ├── stores/
│   │   │   └── testSession.ts  Zustand: userId, attemptId, moduleAttemptId, submitResult
│   │   ├── hooks/
│   │   │   ├── useAttemptState.ts  React Query wrapper for module state
│   │   │   ├── useAutosave.ts      500ms debounced answer save
│   │   │   └── useTimer.ts         Countdown timer from deadline_at
│   │   ├── pages/
│   │   │   ├── StartTest.tsx   Test entry form (userId + testId)
│   │   │   ├── TakeTest.tsx    ← MAIN PAGE: questions, answers, timer, submit
│   │   │   ├── Break.tsx       Inter-section break countdown
│   │   │   ├── Result.tsx      Module 2 result + routing decision display
│   │   │   └── Dashboard.tsx   Analytics charts and history
│   │   ├── components/
│   │   │   ├── test/           QuestionCard, ChoiceList, Passage, Timer, Toolbar, Navigator
│   │   │   └── ui/             Button, Modal
│   │   └── types/api.ts        TypeScript interfaces matching backend Pydantic schemas
│   ├── .env.local              VITE_API_URL=http://localhost:8000
│   └── package.json
│
├── webscraper_bluebook/        Off-line question pipeline
│   ├── scraper.py / scraper_selenium_fill.py  Scrapers (not needed at runtime)
│   ├── canonicalize.py         Normalize scraper output → canonical/questions.jsonl
│   ├── import.py               Insert questions into DB (run once)
│   └── canonical/questions.jsonl  3312 SAT questions (source of truth)
│
├── configs/
│   └── rw_demo.yaml            Describes the adaptive RW test (modules, timing, routing)
│
├── docker-compose.yaml         PostgreSQL + Redis containers (optional if using local PG)
└── SAT_DB_Build_Guide.md       Step-by-step DB setup guide
```

**Entry points:**
- Backend: `backend/app/main.py` → `create_app()` → `app` (Uvicorn picks this up)
- Frontend: `frontend/src/main.tsx` → `ReactDOM.createRoot`

---

## 3. END-TO-END USER FLOWS

### Flow A: Starting a Test

**User action:** Enters UUID for userId and testId on the home screen, clicks "Start Test".

**Frontend** (`StartTest.tsx`):
1. Calls `startAttempt(testId)` → `POST /api/v1/attempts/start` with body `{test_id: <uuid>}` and headers `X-User-Id: <uuid>`, `Idempotency-Key: <uuid>`.
2. Gets back `{attempt_id, module_attempt_id}`.
3. Calls `startModule(module_attempt_id)` → `POST /api/v1/attempts/modules/<ma_id>/start`.
4. Saves both to Zustand via `setSession(attempt_id, module_attempt_id)`.
5. Navigates to `/take/<attempt_id>/<module_attempt_id>`.

**Backend — start_attempt** (`attempt_router.py`):
1. `get_current_user_id` dep: reads `X-User-Id` header → parses UUID.
2. `get_rw_db_with_context` dep: opens `app_rw` session, sets `app.user_id` + `app.role='student'` as transaction config vars (RLS activation).
3. Idempotency check: looks up `idempotency_keys` by `(user_id, idem_key)`.
4. Checks for existing in-progress attempt for this user+test → resumes if found.
5. Validates test exists and is `published`.
6. Finds the first `test_section` → first `test_module` (stage=1).
7. INSERTs `test_attempts` (status='in_progress'), INSERTs `module_attempts` (status='not_started').
8. Returns `{attempt_id, module_attempt_id}`.

**Backend — start_module** (`attempt_router.py`):
1. Loads module_attempt, verifies ownership (`_assert_ma_owner`).
2. If already `in_progress`: returns current state (idempotent).
3. UPDATEs `module_attempts` → `status='in_progress'`, sets `started_at=now()`, `deadline_at=now() + make_interval(secs => time_limit_sec)`.
4. Returns `{module_attempt_id, status, started_at, deadline_at}`.

**Tables touched:** `test_attempts` (INSERT), `module_attempts` (INSERT, UPDATE), `tests`, `test_sections`, `test_modules`, `idempotency_keys`.

---

### Flow B: Answering a Question

**User action:** Clicks choice "B" on question 5.

**Frontend** (`TakeTest.tsx`):
1. `handleSelect(questionId, choiceId)` fires.
2. Immediately updates `localAnswers` Map (optimistic UI — no waiting for server).
3. Calls `autosave({question_id, selected_choice_id, eliminated_choice_ids, is_flagged, time_spent_ms, revision})` — debounced 500ms.
4. After 500ms, `useAutosave` fires `saveAnswer(maId, body)` → `POST /api/v1/attempts/modules/<ma_id>/answer`.

**Backend — save_answer** (`attempt_router.py`):
1. `_assert_ma_owner` verifies ownership.
2. Checks module status is `in_progress` and deadline hasn't passed (2-second grace).
3. Validates the question belongs to this module (JOIN with `module_questions`).
4. Checks existing `revision` — rejects if submitted revision ≤ stored revision (optimistic concurrency).
5. `INSERT ... ON CONFLICT DO UPDATE` (upsert) on `answers`, increments `visit_count`, updates `updated_at`.
6. Returns full `AnswerOut` object.

**Frontend** (`useAutosave.ts`): On success, invalidates `['moduleState', maId]` React Query cache → triggers a background re-fetch of fresh server state.

**Tables touched:** `answers` (upsert), `module_questions`, `questions`.

---

### Flow C: Submitting Module 1 (Routing)

**User action:** Clicks "Review & Submit" → "Submit" in the confirm modal.

**Frontend** (`TakeTest.tsx`):
1. `handleSubmit('user')` → `submitMutation.mutate('user')`.
2. Calls `submitModule(maId, 'user')` → `POST /api/v1/attempts/modules/<ma_id>/submit?reason=user` with `Idempotency-Key` header.

**Backend — submit_module** (`router.py`):
1. `get_current_user_id` parses `X-User-Id`.
2. `get_grader_db` opens `app_grader` session (BYPASSRLS — can write `is_correct`, `routing_decisions`).
3. Idempotency lookup.
4. Calls `service.submit_module(db, module_attempt_id, reason)`.

**service.submit_module** (`service.py`):
1. **Lock:** `SELECT ... FOR UPDATE` on `module_attempts` (prevents double-submit race).
2. **Grade:** `grade_module(db, ma_id)`:
   - MC: `UPDATE answers SET is_correct = (selected_choice_id = correct_choice_id) FROM grading.question_keys` — one SQL UPDATE.
   - Grid-in: Python-side parse + tolerance match vs `grading.spr_accepted_answers`.
   - Loads difficulty stats: `GROUP BY difficulty COUNT(*) FILTER WHERE is_correct`.
3. **Weighted score:** `(correct_easy×1 + correct_medium×2 + correct_hard×3) / (total_easy×1 + total_medium×2 + total_hard×3)` → Decimal, 4dp.
4. **Route:** If `weighted_score >= threshold (0.65)` → "hard", else → "easy".
5. **Write routing_decisions** (MUST happen before step 6 — trigger enforces this).
6. **Create stage-2 module_attempt** (status='not_started').
7. **UPDATE module_attempts** → `status='submitted'`, grading fields → fires `trg_enforce_module_order` and `trg_immutable_submitted`.
8. Returns `{module_attempt_id, question_count, correct_count, weighted_score, next: {type: "next_module", module_attempt_id: <stage2_id>, level: "easy"|"hard", ...}}`.

**Frontend — onSuccess:**
1. Saves `submitResult` to Zustand store.
2. Sees `next.type === 'next_module'`.
3. Calls `startModule(next.module_attempt_id)` → starts the stage-2 timer.
4. Navigates to `/take/<stage2_maId>`.

**Tables touched:** `answers` (UPDATE is_correct), `grading.question_keys` (read), `grading.spr_accepted_answers` (read), `routing_decisions` (INSERT), `module_attempts` (UPDATE + INSERT for stage-2), `idempotency_keys` (INSERT, separate session).

---

### Flow D: Submitting Module 2 + Score Report

Same flow as C, except stage=2. After `_handle_break_or_complete`:
- Since `break_seconds=null` (single-section test): `UPDATE test_attempts SET status='completed'`.
- Returns `{next: {type: "attempt_complete"}}`.
- Calls `build_score_report(db, attempt_id)`:
  1. Loads all answers from both modules for this attempt.
  2. Counts `rw_raw` (total correct), aggregates by domain + skill.
  3. Finds routing decision for `rw_stage2_level`.
  4. Upserts `score_reports`, inserts `domain_results`, `skill_results`.
  5. Upserts `user_skill_stats`, `user_domain_stats`, `user_stats` (rolling totals — additive).

**Frontend:** Navigates to `/result`, reads `submitResult` from Zustand, displays score + routing decision.

---

### Flow E: Viewing the Dashboard

**User action:** Clicks "View Dashboard" from Result page.

**Frontend** (`Dashboard.tsx`): 4 parallel React Query requests:
```
GET /api/v1/analytics/me          → totals, best/latest score, accuracy
GET /api/v1/analytics/me/skills   → per-skill stats (sorted by accuracy ASC)
GET /api/v1/analytics/me/domains  → per-domain stats
GET /api/v1/analytics/me/attempts → last 50 attempts
```

All go through `get_rw_db_with_context` → RLS filters every SELECT to the calling user's data only. Renders Recharts BarChart for domains, list of weakest 8 skills, recent attempt history.

---

## 4. DATABASE LAYER

### Schema overview (40 tables)

**Content tables (read-only at runtime):**

| Table | What it stores |
|-------|---------------|
| `domains` | 8 domains (4 RW + 4 MATH) |
| `skills` | 29 skills linked to domains |
| `passages` | Shared reading passages |
| `questions` | 3312 questions with stem (HTML), difficulty, type, section |
| `question_choices` | A/B/C/D choices per MC question |
| `tests` | The test definition |
| `test_sections` | Section within a test (RW/MATH, position, break config) |
| `test_modules` | Module within a section (stage 1/2, level, time limit, routing config) |
| `module_questions` | Questions assigned to each module (with position) |
| `grading.question_keys` | Correct choice per MC question (app_grader only) |
| `grading.spr_accepted_answers` | Accepted raw values for grid-in questions |
| `grading.question_explanations` | Explanations (only returned post-submission) |

**Attempt tables (written during a test):**

| Table | What it stores |
|-------|---------------|
| `test_attempts` | One row per student test attempt |
| `module_attempts` | One row per module within an attempt |
| `answers` | One row per question per module attempt (upserted on each save) |
| `routing_decisions` | The routing result after stage-1 |
| `break_sessions` | Break start/end tracking (multi-section tests) |

**Analytics tables (written at stage-2 submit):**

| Table | What it stores |
|-------|---------------|
| `score_reports` | One report per completed attempt |
| `domain_results` | Per-domain breakdown for a score report |
| `skill_results` | Per-skill breakdown with difficulty splits |
| `user_skill_stats` | Rolling totals per user+skill across all attempts |
| `user_domain_stats` | Rolling totals per user+domain |
| `user_stats` | Single-row totals per user (attempts, questions, best score) |

**Infrastructure tables:**

| Table | What it stores |
|-------|---------------|
| `users` | User accounts |
| `idempotency_keys` | Cached POST responses, TTL 24h |

### How the schema is created

`backend/sat_db_build_all.sql` is the single source of truth — 2043 lines of DDL. It is **not** run by Alembic. The Alembic baseline (`16d93f12d518_baseline.py`) is a stub that marks the database as up-to-date so Alembic doesn't try to re-apply anything.

```bash
# If roles already exist, extract just the schema portion (line 41 onwards):
sed -n '41,2043p' backend/sat_db_build_all.sql > /tmp/schema_only.sql
PGPASSWORD=fares psql -h localhost -U app_owner -d satprep -f /tmp/schema_only.sql
```

### DB roles

| Role | BYPASSRLS | Used for |
|------|-----------|----------|
| `app_owner` | yes | DDL, migrations, scripts |
| `app_rw` | no | All student API reads/writes (RLS enforced) |
| `app_grader` | yes | Grading (write `is_correct`), routing_decisions, score reports |
| `app_auth` | yes | Auth flows (reserved) |
| `app_content_admin` | yes | Question management (reserved) |
| `app_worker` | yes | Background jobs (reserved) |
| `analytics_ro` | no | Read-only analytics (reserved) |
| `backup_role` | no | pg_dump backups |

All passwords are `fares` in the dev environment.

### RLS

Enabled on 24 tables. Policies use `current_setting('app.user_id')`. `get_rw_db_with_context` sets this at the start of every `app_rw` transaction. `app_grader` bypasses all policies.

### Connection & pooling

`backend/app/db.py` creates two async engine pools:
- `engine` → `DATABASE_URL` (app_rw) → `sessionlocal`
- `grader_engine` → `DATABASE_URL_GRADER` (app_grader) → `grader_sessionlocal`

Both use asyncpg with `pool_pre_ping=True`. Sessions are per-request via FastAPI dependencies.

---

## 5. CONFIGURATION & ENVIRONMENT

### Backend env (`backend/.env`)

| Variable | Example |
|----------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://app_rw:fares@localhost:5432/satprep` |
| `DATABASE_URL_MIGRATION` | `postgresql+asyncpg://app_owner:fares@localhost:5432/satprep` |
| `DATABASE_URL_GRADER` | `postgresql+asyncpg://app_grader:fares@localhost:5432/satprep` |
| `JWT_SECRET` | `dev-secret-change-in-production` |
| `CORS_ORIGINS` | `["http://localhost:5173"]` |

### Frontend env (`frontend/.env.local`)

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `http://localhost:8000` |

### Run locally from scratch (in order)

```bash
# 1. Start PostgreSQL
sudo systemctl start postgresql

# 2. Create DB schema (if starting fresh)
sed -n '41,2043p' backend/sat_db_build_all.sql > /tmp/schema.sql
PGPASSWORD=fares psql -h localhost -U app_owner -d satprep -f /tmp/schema.sql

# 3. Import questions (run once)
cd webscraper_bluebook
/path/to/.venv_linux/bin/pip install psycopg
python import.py

# 4. Create the adaptive test structure
cd ../backend
PYTHONPATH=. .venv_linux/bin/python scripts/build_rw_test.py
# → prints test UUID

# 5. Create a dev user
PYTHONPATH=. .venv_linux/bin/python scripts/create_user.py
# → prints user UUID

# 6. Start backend
.venv_linux/bin/uvicorn app.main:app --reload --port 8000

# 7. Start frontend (new terminal)
cd ../frontend
npm run dev
```

### Running tests

```bash
# Frontend
cd frontend && npm run test

# Backend
cd backend && .venv_linux/bin/pytest
```

---

## 6. DATA & ASSETS

### Question bank: `webscraper_bluebook/canonical/questions.jsonl`

3312 lines, one JSON object per line:

```json
{
  "source_id": "cbid_abc123",
  "section": "RW | MATH",
  "domain_name": "Information and Ideas",
  "skill_name": "Inferences",
  "difficulty": "easy | medium | hard",
  "question_type": "multiple_choice | grid_in",
  "stem": "<p>HTML question text</p>",
  "choices": [{"label": "A", "content": "HTML"}, ...],
  "correct_labels": ["B"],
  "correct_answers": ["3/4", ".75"],
  "explanation": "HTML explanation"
}
```

Questions with explanations are published on import; others stay draft.

### Config: `configs/rw_demo.yaml`

Defines the adaptive test: 3 modules (router, easy, hard), routing threshold 0.65, weights (easy=1, medium=2, hard=3), 27 questions per module.

---

## 7. KEY LOGIC / NON-OBVIOUS PARTS

### 7.1 Adaptive routing algorithm (`routing.py`)

```
weighted_score = (correct_easy×1 + correct_medium×2 + correct_hard×3)
               / (total_easy×1   + total_medium×2   + total_hard×3)

score >= 0.65  →  hard module
score <  0.65  →  easy module
```

Hard questions count 3× more than easy. Weights and threshold are stored per `test_module` row — tunable without code changes.

### 7.2 DB trigger order constraint (`service.py`)

The trigger `trg_enforce_module_order` fires when a module_attempt transitions to `submitted`. For stage-1, it validates that a `routing_decisions` row already exists. Therefore `service.py` **must**:
1. INSERT `routing_decisions` ← first
2. UPDATE `module_attempts` SET status='submitted' ← second

Reversing these causes a DB-level check_violation.

### 7.3 Dual DB sessions for submit (`router.py`)

The idempotency store after a successful submit uses a **separate `grader_sessionlocal` session** from the main submit session. This prevents a failed/aborted submit transaction from blocking the idempotency record write. The store is non-fatal — if it fails, the submit still returns successfully.

### 7.4 RLS via `set_config` (`deps.py`)

```python
await session.execute(
    text("SELECT set_config('app.user_id', :uid, true), "
         "       set_config('app.role', 'student', true)"),
    {"uid": str(uid)},
)
```

The `true` third argument makes it transaction-local — resets automatically when the transaction ends. DB policies filter rows by `current_setting('app.user_id', true)`.

### 7.5 Optimistic concurrency in answers

Every answer save includes a `revision` counter (client-side, incremented per question via `revisionRef` in `TakeTest.tsx`). The backend rejects upserts where `revision ≤ stored revision`. On 409, the frontend refetches authoritative state.

### 7.6 Autosave debounce (`useAutosave.ts`)

500ms debounce after last change. Uses `pendingRef` — rapid selections don't queue multiple calls, only the latest state is sent.

### 7.7 Score report is synchronous, non-fatal

`build_score_report` runs inline in the submit request. If it throws, `service.py` logs the error and returns the submit result anyway. Students never get a 500 because of a score report failure.

### 7.8 No real auth yet

`X-User-Id` header is taken at face value. No JWT validation in active code paths. The `jwt_secret` env var and `python-jose` package are installed but unused. Fine for dev; needs JWT before public deployment.

### 7.9 No background jobs

No Celery, no Redis queues, no cron jobs. `REDIS_URL` defaults to `""` and nothing uses it. Score reports are synchronous. Idempotency keys accumulate (no cleanup job).

---

## 8. HOW TO EXTEND IT

### Adding a new API endpoint

1. Add response schema (in the router file or `schemas/`).
2. Add the route handler with appropriate `Depends(get_rw_db_with_context)` or `Depends(get_grader_db)`.
3. Write raw SQL (the codebase uses raw SQL throughout, not ORM queries).
4. Add the TypeScript type to `frontend/src/types/api.ts`.
5. Add the API function to the relevant `frontend/src/api/*.ts` file.
6. Use `useQuery` or `useMutation` in the page component.

### Adding a new page

1. Create `frontend/src/pages/NewPage.tsx`.
2. Add route to `frontend/src/router.tsx`.
3. Link from wherever appropriate.

### Adding a new question type

1. Add enum value to DB enum + Python `QuestionType` enum in `models/question.py`.
2. Update `webscraper_bluebook/import.py` to handle the new type.
3. Update `grading.py` to grade it.
4. Update `QuestionCard.tsx` to render it.

### Adding a MATH section

The schema already supports it. You'd need to import MATH questions, create a YAML config, and run `build_rw_test.py`. The routing logic is section-agnostic.

---

## 9. GOTCHAS & KNOWN ISSUES

### The venv was built on Windows

`.venv/` uses `Scripts/` (Windows). On Linux, use `.venv_linux/`. All commands use `.venv_linux/bin/` prefix.

### PostgreSQL peer auth

Always pass `-h localhost` to force TCP auth:
```bash
PGPASSWORD=fares psql -h localhost -U app_rw -d satprep
```
Without it, psql uses Unix socket peer auth and fails unless your Linux username matches the PG role name.

### DB permissions gap after fresh SQL build

Several grants were applied manually after the initial SQL build. Re-running `sat_db_build_all.sql` requires also running:
```bash
PYTHONPATH=. .venv_linux/bin/python scripts/fix_grader_perms.py
```
Or apply these grants manually:
```sql
GRANT UPDATE ON answers TO app_grader;
GRANT SELECT, INSERT, UPDATE, DELETE ON idempotency_keys TO app_rw;
GRANT SELECT, INSERT, UPDATE ON idempotency_keys TO app_grader;
GRANT UPDATE ON module_attempts TO app_grader;
GRANT UPDATE ON test_attempts TO app_grader;
GRANT INSERT, UPDATE ON score_reports, domain_results, skill_results,
      user_skill_stats, user_domain_stats, user_stats TO app_grader;
```

### `node_modules` was built on Windows

Delete and reinstall on Linux:
```bash
cd frontend && rm -rf node_modules package-lock.json && npm install
```

### No auth

`X-User-Id` is taken at face value. Any client can impersonate any user.

### `currentQuestionIndex` in Zustand is dead code

`testSession.ts` tracks it but `TakeTest.tsx` uses local `useState` instead. The store field is never read or written.

### Alembic migration is a stub

Never run `alembic revision --autogenerate` — it will try to create all 40 tables that already exist. Write schema changes as raw SQL + a manual Alembic migration.

### Score report stores raw score only

`rw_scaled` column exists but the conversion table lookup is not implemented. Dashboard and Result show raw counts only.

---

## 10. QUICK REFERENCE

### Start servers

```bash
# Backend
cd backend
.venv_linux/bin/uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev
# → http://localhost:5173
```

### Connect to DB

```bash
# API role (RLS enforced)
PGPASSWORD=fares psql -h localhost -U app_rw -d satprep

# Owner role (DDL / scripts)
PGPASSWORD=fares psql -h localhost -U app_owner -d satprep
```

### Useful DB queries

```sql
-- All users
SELECT id, email, role FROM users;

-- All tests
SELECT id, slug, status FROM tests;

-- Recent attempts
SELECT id, status, started_at, completed_at
  FROM test_attempts ORDER BY started_at DESC LIMIT 10;

-- Module attempts for a user
SELECT ma.id, ma.status, ma.sequence, ma.correct_count, ma.weighted_score
  FROM module_attempts ma
  JOIN test_attempts ta ON ta.id = ma.attempt_id
 WHERE ta.user_id = 'd0712ba7-cac5-4ab9-b9b2-1d7c148a4955'
 ORDER BY ma.sequence;

-- Reset in-progress attempts for re-testing
UPDATE test_attempts SET status='abandoned'
 WHERE status='in_progress'
   AND user_id='d0712ba7-cac5-4ab9-b9b2-1d7c148a4955';
```

### Run scripts

```bash
cd backend

# Create a dev user
PYTHONPATH=. .venv_linux/bin/python scripts/create_user.py

# Build the demo test
PYTHONPATH=. .venv_linux/bin/python scripts/build_rw_test.py

# Debug a failing submit
PYTHONPATH=. .venv_linux/bin/python scripts/debug_submit.py

# Reset attempts for re-testing
PYTHONPATH=. .venv_linux/bin/python scripts/reset_attempts.py

# Check model vs DB schema alignment
PYTHONPATH=. .venv_linux/bin/python scripts/check_all_models.py

# Fix DB permissions after a fresh SQL build
PYTHONPATH=. .venv_linux/bin/python scripts/fix_grader_perms.py
```

### Run tests

```bash
cd frontend && npm run test     # vitest
cd backend && .venv_linux/bin/pytest
```

### API endpoints (all at localhost:8000)

```
GET  /health
GET  /docs                   (dev only)

POST /api/v1/attempts/start
POST /api/v1/attempts/modules/{ma_id}/start
GET  /api/v1/attempts/modules/{ma_id}/state
POST /api/v1/attempts/modules/{ma_id}/answer
POST /api/v1/attempts/modules/{ma_id}/events
POST /api/v1/attempts/modules/{ma_id}/submit

GET  /api/v1/analytics/me
GET  /api/v1/analytics/me/skills
GET  /api/v1/analytics/me/domains
GET  /api/v1/analytics/me/attempts
```

All endpoints require `X-User-Id: <uuid>` header.

### Dev credentials

```
User ID:  d0712ba7-cac5-4ab9-b9b2-1d7c148a4955
Email:    testuser@dev.local

Test ID:  61ef9e99-3ef5-41e2-b967-34d338e95109
Title:    RW Demo — Adaptive Practice
```
