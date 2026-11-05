"""Delete all in-progress attempts for the test user so we can start fresh."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

USER_ID = "e43fef0a-1df0-4af2-959f-e5c1b3f98dd3"

async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        result = await db.execute(
            text("DELETE FROM test_attempts WHERE user_id = :uid RETURNING id"),
            {"uid": USER_ID}
        )
        deleted = result.rowcount
        await db.commit()
        print(f"Deleted {deleted} attempt(s) for user {USER_ID}")

asyncio.run(main())
