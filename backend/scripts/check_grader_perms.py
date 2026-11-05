"""Check what app_grader can and cannot access."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TABLES_NEEDED = [
    "test_attempts", "module_attempts", "answers", "routing_decisions",
    "idempotency_keys", "score_reports", "domain_results", "skill_results",
    "user_skill_stats", "user_domain_stats", "user_stats", "break_sessions",
    "questions", "test_modules", "test_sections",
]

async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        rows = await db.execute(text("""
            SELECT table_name, grantee, string_agg(privilege_type, ', ' ORDER BY privilege_type) AS privs
            FROM information_schema.role_table_grants
            WHERE grantee = 'app_grader'
            GROUP BY table_name, grantee
            ORDER BY table_name
        """))
        has_access = {}
        for r in rows:
            has_access[r[0]] = r[2]

        print(f"{'Table':<30} {'app_grader privs'}")
        print("-" * 60)
        for t in TABLES_NEEDED:
            privs = has_access.get(t, "❌ NO ACCESS")
            print(f"{t:<30} {privs}")

asyncio.run(main())
