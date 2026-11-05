"""Check table ownership and current grants for app_grader."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        # Who owns the tables
        rows = await db.execute(text("""
            SELECT tableowner, tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename IN ('test_modules', 'test_sections', 'module_attempts', 'answers')
            ORDER BY tablename
        """))
        print("Table owners:")
        for r in rows:
            print(f"  {r[1]:30s} owned by {r[0]}")

        # What role is DATABASE_URL_MIGRATION connecting as
        row = (await db.execute(text("SELECT current_user, session_user"))).first()
        print(f"\nConnected as: current_user={row[0]}, session_user={row[1]}")

        # Check if grant actually took effect
        rows2 = await db.execute(text("""
            SELECT grantee, string_agg(privilege_type, ', ' ORDER BY privilege_type)
            FROM information_schema.role_table_grants
            WHERE table_name = 'test_modules' AND grantee = 'app_grader'
            GROUP BY grantee
        """))
        print("\napp_grader privs on test_modules:")
        for r in rows2:
            print(f"  {r[0]}: {r[1]}")
        
        # Try granting again explicitly
        print("\nRe-granting SELECT on test_modules to app_grader...")
        await db.execute(text("GRANT SELECT ON TABLE public.test_modules TO app_grader"))
        await db.execute(text("GRANT SELECT ON TABLE public.test_sections TO app_grader"))
        await db.commit()
        print("Done.")

asyncio.run(main())
