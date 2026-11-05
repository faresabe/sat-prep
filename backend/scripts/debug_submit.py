"""Run a full submit cycle and print the exact traceback."""
import asyncio, traceback
from sqlalchemy import text
from app.db import grader_sessionlocal
from app.modules.attempts import service

USER_ID = "e43fef0a-1df0-4af2-959f-e5c1b3f98dd3"

async def main():
    async with grader_sessionlocal() as db:
        # Find the in-progress module attempt
        row = (await db.execute(text("""
            SELECT ma.id, ma.status
            FROM module_attempts ma
            JOIN test_attempts ta ON ta.id = ma.attempt_id
            WHERE ta.user_id = :uid
            ORDER BY ma.created_at DESC LIMIT 5
        """), {"uid": USER_ID})).all()

        print("Recent module attempts:")
        for r in row:
            print(f"  {r[0]}  status={r[1]}")

        in_progress = [r for r in row if r[1] == "in_progress"]
        if not in_progress:
            print("\nNo in-progress module attempt found.")
            return

        ma_id = in_progress[0][0]
        print(f"\nSubmitting module_attempt: {ma_id}")
        try:
            result = await service.submit_module(db, ma_id, "user")
            await db.commit()
            print("Success:", result)
        except Exception:
            await db.rollback()
            print("\nFull traceback:")
            traceback.print_exc()

asyncio.run(main())
