"""Verify what role app_grader actually connects as."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def main():
    print("Grader URL:", settings.database_url_grader[:60], "...")
    engine = create_async_engine(settings.database_url_grader, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        row = (await db.execute(text(
            "SELECT current_user, session_user, "
            "pg_has_role(current_user, 'app_grader', 'MEMBER') as is_grader"
        ))).first()
        print(f"current_user:  {row[0]}")
        print(f"session_user:  {row[1]}")
        print(f"is app_grader: {row[2]}")

        # Test the actual query that fails
        try:
            r = await db.execute(text("SELECT id FROM test_modules LIMIT 1"))
            print("test_modules: OK")
        except Exception as e:
            print(f"test_modules: FAILED — {e}")

asyncio.run(main())
