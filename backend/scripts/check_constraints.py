import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        for table in ["test_attempts", "module_attempts", "idempotency_keys"]:
            rows = await db.execute(text(f"""
                SELECT conname, contype, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = '{table}'::regclass
                AND contype IN ('u','p')
                ORDER BY contype
            """))
            print(f"\n=== {table} unique/pk constraints ===")
            for r in rows:
                print(f"  [{r[1]}] {r[0]}: {r[2]}")

asyncio.run(main())
