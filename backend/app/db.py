from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


# --- API runtime (app_rw, RLS-enforced) ---
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

sessionlocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# --- Grading path (app_grader, BYPASSRLS) ---
grader_engine = create_async_engine(
    settings.database_url_grader,
    echo=settings.debug,
    pool_pre_ping=True,
)

grader_sessionlocal = async_sessionmaker(
    grader_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Default API dependency — uses app_rw."""
    async with sessionlocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_grader_db() -> AsyncGenerator[AsyncSession, None]:
    """Grading dependency — uses app_grader. Bypasses RLS, can write is_correct."""
    async with grader_sessionlocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise