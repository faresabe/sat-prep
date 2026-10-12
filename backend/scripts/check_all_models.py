"""Compare ALL SQLAlchemy models against the full DB schema.

Run: python -m scripts.check_all_models
"""

import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db import Base
from app.models import *  # noqa: F401, F403 — imports register all models


EXPECTED_UNMAPPED = {
    # Tables in the DB that we intentionally haven't mapped yet.
    # These are OK to be missing.
    "alembic_version",
    "auth_events",
    "audit_logs",
    "answer_events",
    "annotations",
    "break_sessions",
    "classes",
    "class_members",
    "data_requests",
    "email_verification_tokens",
    "idempotency_keys",
    "password_reset_tokens",
    "question_stats",
    "score_conversions",
    "user_consents",
    "user_goals",
    "grading.question_explanations",
    "grading.spr_accepted_answers",
}


async def main():
    engine = create_async_engine(settings.database_url)

    async with engine.connect() as conn:
        await conn.run_sync(check)

    await engine.dispose()


def check(connection):
    inspector = inspect(connection)

    # --- 1. Tables in the DB ---
    public_tables = set(inspector.get_table_names(schema="public"))
    grading_tables = {
        f"grading.{t}" for t in inspector.get_table_names(schema="grading")
    }
    # Filter out partitions (they end with _pYYYYMM or _default)
    def is_partition(t):
        return (
            t.endswith("_default")
            or (len(t) > 6 and t[-7:-6] == "_" and t[-6:].isdigit())
        )
    db_all = {
        t for t in (public_tables | grading_tables)
        if not is_partition(t)
    }
    # Remove alembic_version from the "expected unmapped" set for clarity
    db_all_no_alembic = db_all - {"alembic_version"}

    # --- 2. Tables from models ---
    model_all = set(Base.metadata.tables.keys())

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  DB tables (excluding partitions, alembic_version): {len(db_all_no_alembic)}")
    print(f"  Model tables:                                       {len(model_all)}")
    print(f"  Mapped (in both):                                   {len(model_all & db_all_no_alembic)}")
    print()

    # --- 3. Tables in models but not in DB (CRITICAL ERROR) ---
    only_in_models = model_all - db_all_no_alembic
    print("=" * 70)
    print("❌ TABLES IN MODELS BUT NOT IN DB  (these are bugs)")
    print("=" * 70)
    if not only_in_models:
        print("  ✅ None — every model points at a real table")
    else:
        for t in sorted(only_in_models):
            print(f"  ⚠️  {t}  — the model references a table that doesn't exist")
    print()

    # --- 4. Tables in DB but not in models (INFO) ---
    only_in_db = db_all_no_alembic - model_all
    print("=" * 70)
    print("ℹ️  TABLES IN DB BUT NOT IN MODELS")
    print("=" * 70)
    unexpected_unmapped = only_in_db - EXPECTED_UNMAPPED
    expected_unmapped_present = only_in_db & EXPECTED_UNMAPPED
    if not only_in_db:
        print("  (none — every DB table has a model)")
    else:
        if expected_unmapped_present:
            print(f"  Expected unmapped ({len(expected_unmapped_present)}):")
            for t in sorted(expected_unmapped_present):
                print(f"    • {t}")
        if unexpected_unmapped:
            print(f"\n  ⚠️  UNEXPECTED unmapped ({len(unexpected_unmapped)}):")
            for t in sorted(unexpected_unmapped):
                print(f"    ⚠️  {t}")
    print()

    # --- 5. Column-by-column comparison for mapped tables ---
    print("=" * 70)
    print("COLUMN COMPARISON (per mapped table)")
    print("=" * 70)

    problems = 0
    for table_key in sorted(model_all):
        model_table = Base.metadata.tables[table_key]
        schema = model_table.schema or "public"
        bare_name = model_table.name

        # Skip if not in DB
        if schema == "public" and bare_name not in public_tables:
            continue
        if schema != "public" and f"{schema}.{bare_name}" not in grading_tables:
            continue

        db_cols = {
            c["name"]: c
            for c in inspector.get_columns(bare_name, schema=schema)
        }
        model_cols = {c.name: c for c in model_table.columns}

        only_db = set(db_cols) - set(model_cols)
        only_model = set(model_cols) - set(db_cols)

        if not only_db and not only_model:
            print(f"  ✅ {schema}.{bare_name}: {len(model_cols)} columns match")
        else:
            problems += 1
            print(f"\n  ⚠️  {schema}.{bare_name}:")
            if only_db:
                for c in sorted(only_db):
                    print(f"      in DB only:    {c}")
            if only_model:
                for c in sorted(only_model):
                    print(f"      in model only: {c}")

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)
    if not only_in_models and problems == 0:
        print("  ✅ All models match the DB schema.")
    else:
        print(f"  ⚠️  {len(only_in_models)} table mismatches, {problems} column mismatches")


if __name__ == "__main__":
    asyncio.run(main())