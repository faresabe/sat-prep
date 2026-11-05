"""Grant all permissions app_grader needs. Run once after DB setup."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Every table the grader role touches during submit + score report
GRANTS = [
    ("test_attempts",           "SELECT, UPDATE"),
    ("test_sections",           "SELECT"),
    ("test_modules",            "SELECT"),
    ("module_attempts",         "SELECT, INSERT, UPDATE"),
    ("module_questions",        "SELECT"),
    ("answers",                 "SELECT, UPDATE"),
    ("routing_decisions",       "SELECT, INSERT"),
    ("break_sessions",          "SELECT, INSERT"),
    ("score_reports",           "SELECT, INSERT, UPDATE"),
    ("domain_results",          "SELECT, INSERT, DELETE"),
    ("skill_results",           "SELECT, INSERT, DELETE"),
    ("user_skill_stats",        "SELECT, INSERT, UPDATE"),
    ("user_domain_stats",       "SELECT, INSERT, UPDATE"),
    ("user_stats",              "SELECT, INSERT, UPDATE"),
    ("idempotency_keys",        "SELECT, INSERT, UPDATE"),
    ("questions",               "SELECT"),
    ("domains",                 "SELECT"),
    ("skills",                  "SELECT"),
    ("passages",                "SELECT"),
    ("question_choices",        "SELECT"),
    ("tests",                   "SELECT"),
    ("users",                   "SELECT"),
]

GRADING_GRANTS = [
    ("grading.question_keys",        "SELECT"),
    ("grading.spr_accepted_answers", "SELECT"),
]

async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        for table, privs in GRANTS:
            await db.execute(text(f"GRANT {privs} ON {table} TO app_grader"))
            print(f"  OK  {privs:40s} {table}")

        for table, privs in GRADING_GRANTS:
            await db.execute(text(f"GRANT {privs} ON {table} TO app_grader"))
            print(f"  OK  {privs:40s} {table}")

        await db.commit()
        print("\nAll grants applied.")

asyncio.run(main())
