"""Quick sanity check — show all tests regardless of status."""
import asyncio
from sqlalchemy import text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


async def main():
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        tests = (await db.execute(
            text("SELECT id, slug, status FROM tests ORDER BY created_at DESC LIMIT 10")
        )).all()

        if not tests:
            print("No tests in DB.")
            return

        for t in tests:
            print(f"{t[0]}  {t[1]}  {t[2]}")

            rows = (await db.execute(
                text("""
                    SELECT tm.stage, tm.level, COUNT(mq.question_id) as q
                      FROM test_modules tm
                      JOIN test_sections ts ON ts.id = tm.section_id
                      LEFT JOIN module_questions mq ON mq.module_id = tm.id
                     WHERE ts.test_id = :tid
                     GROUP BY tm.stage, tm.level
                     ORDER BY tm.stage, tm.level
                """),
                {"tid": str(t[0])}
            )).all()
            for r in rows:
                print(f"  stage={r[0]} level={r[1]} questions={r[2]}")


asyncio.run(main())
