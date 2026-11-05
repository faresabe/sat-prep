import asyncio
from sqlalchemy import text
from app.db import sessionlocal

async def main():
    async with sessionlocal() as db:
        rows = await db.execute(text("SELECT id, email FROM users LIMIT 5"))
        for r in rows:
            print(r[0], r[1])

asyncio.run(main())
