"""Create a test student user for dev testing."""
import asyncio
import uuid
from sqlalchemy import text
from app.db import sessionlocal
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def main():
    # Use app_owner (migration URL) which has full permissions
    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Check if already exists
        row = (await db.execute(
            text("SELECT id, email FROM users WHERE email = 'testuser@dev.local'")
        )).first()
        if row:
            print(f"User ID:  {row[0]}")
            print(f"Email:    {row[1]}")
            return

        uid = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, role, is_active)
                VALUES (:id, :email, 'dev-hash-not-real', 'Test Student', 'student', true)
            """),
            {"id": str(uid), "email": "testuser@dev.local"}
        )
        await db.commit()
        print(f"User ID:  {uid}")
        print(f"Email:    testuser@dev.local")

asyncio.run(main())
