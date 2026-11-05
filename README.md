# SAT Prep — Adaptive Practice Test

A full-stack adaptive SAT practice platform modeled on College Board Bluebook.
RW section only. Two-stage adaptive routing (Module 1 → Easy/Hard Module 2).

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, structlog |
| Database | PostgreSQL 15+, 8 roles, RLS on 24 tables |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, TanStack Query, Zustand, Recharts |

---

## Quick Start

### 1. Database

```bash
# Start Postgres (or use local)
docker compose up -d postgres

# Run migrations
cd backend
alembic upgrade head
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Copy and fill in env vars
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install --legacy-peer-deps
cp .env.example .env.local

npm run dev
```

App: http://localhost:5173

---

## Environment Variables

### backend/.env

```env
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql+asyncpg://app_rw:<password>@localhost:5432/satprep
DATABASE_URL_MIGRATION=postgresql+asyncpg://app_owner:<password>@localhost:5432/satprep
DATABASE_URL_GRADER=postgresql+asyncpg://app_grader:<password>@localhost:5432/satprep
JWT_SECRET=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=["http://localhost:5173"]
```

### frontend/.env.local

```env
VITE_API_URL=http://localhost:8000
```

---

## Running Tests

### Backend

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/ -v    # Windows
# or
python -m pytest tests/ -v                       # Unix
```

Tests:
- `test_routing.py` — pure routing algorithm (11 tests)
- `test_grading.py` — `_parse_numeric` for grid-in (13 tests)
- `test_idempotency.py` — hash logic (4 tests)

### Frontend

```bash
cd frontend
npm run test
```

Tests:
- `useTimer.test.ts` — countdown, expire callback, null deadline
- `TakeTest.test.tsx` — renders questions, autosave fires on selection (MSW mock)

---

## API Endpoints

### Attempt Lifecycle

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/attempts/start` | Create test attempt + first module |
| POST | `/api/v1/attempts/modules/{ma_id}/start` | Start a module (sets deadline) |
| GET  | `/api/v1/attempts/modules/{ma_id}/state` | Load questions, answers, deadline |
| POST | `/api/v1/attempts/modules/{ma_id}/answer` | Save/update one answer |
| POST | `/api/v1/attempts/modules/{ma_id}/events` | Log interaction events |
| POST | `/api/v1/attempts/modules/{ma_id}/submit` | Grade and submit module |

### Analytics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/analytics/me` | Overall stats |
| GET | `/api/v1/analytics/me/skills` | Per-skill accuracy |
| GET | `/api/v1/analytics/me/domains` | Per-domain accuracy |
| GET | `/api/v1/analytics/me/attempts` | Attempt history |

All endpoints require `X-User-Id: <uuid>` header (dev mode — replace with JWT for production).

---

## Roles, RLS, and Idempotency

### Database Roles

| Role | Used by | Permissions |
|------|---------|-------------|
| `app_rw` | API read/write | Student-scoped via RLS |
| `app_grader` | Grading, score reports | BYPASSRLS, write `is_correct` |
| `app_auth` | Auth flows | User table writes |
| `app_owner` | Migrations | DDL owner |
| `app_content_admin` | Content management | Question/test management |
| `app_worker` | Background jobs | Reserved |
| `analytics_ro` | Read-only analytics | SELECT analytics tables |
| `backup_role` | Backups | pg_dump access |

### RLS

Every student-scoped API request calls:
```sql
SELECT set_config('app.user_id', '<uuid>', true),
       set_config('app.role', 'student', true)
```

This is done automatically by the `get_rw_db_with_context` dependency. RLS policies on all student tables filter rows by `app.user_id`. User A cannot see User B's attempts.

### Idempotency

All `POST`/`PATCH` requests accept an optional `Idempotency-Key` header.

- Same key + same body → returns cached response (no duplicate rows)
- Same key + different body → 409 Conflict
- The frontend auto-generates a UUID v4 `Idempotency-Key` for every mutating request

Keys are stored in the `idempotency_keys` table with a 24-hour TTL.

---

## Demo Test Setup

To build a demo RW test from scratch:

```bash
cd backend
python scripts/build_rw_test.py
```

This creates a published RW section-practice test in the DB and prints the test UUID.
Use that UUID in the frontend StartTest page.

See `configs/rw_demo.yaml` for the configuration.

---

## Score Report

When Module 2 (stage=2) is submitted and the attempt completes, a score report is generated synchronously:

- `rw_raw` = count of correct answers
- Per-domain and per-skill breakdowns stored in `domain_results` / `skill_results`
- Rolling lifetime aggregates updated in `user_skill_stats`, `user_domain_stats`, `user_stats`
- Idempotent: re-submitting rebuilds the report in-place

---

## Definition of Done

- [x] Student can start a test in the browser
- [x] Student can answer questions in Module 1
- [x] Timer counts down (server-authoritative) and auto-submits at 0
- [x] Submitting routes to Easy or Hard Module 2 based on weighted score
- [x] Student can complete Module 2
- [x] Score report is generated on completion
- [x] Dashboard shows latest score, skill weaknesses, domain breakdown, attempt history
- [x] Idempotency-Key returns same response, no duplicate rows
- [x] RLS enforced: user B sees zero rows from user A's attempts
- [x] Backend tests pass (27/27)
- [x] Frontend tests written (timer + autosave)
