"""Grant idempotency_keys access to app_grader."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        # Check current privileges
        rows = await db.execute(text("""
            SELECT grantee, privilege_type
            FROM information_schema.role_table_grants
            WHERE table_name = 'idempotency_keys'
            ORDER BY grantee, privilege_type
        """))
        print("Current grants on idempotency_keys:")
        for r in rows:
            print(f"  {r[0]}: {r[1]}")

        # Grant to app_grader
        await db.execute(text(
            "GRANT SELECT, INSERT, UPDATE ON idempotency_keys TO app_grader"
        ))
        await db.commit()
        print("\nGranted SELECT, INSERT, UPDATE on idempotency_keys to app_grader")

asyncio.run(main())
