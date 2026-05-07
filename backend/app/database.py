from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# ── Async engine (used by FastAPI) ────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Sync engine (used by Celery workers) ──────────────────────────────────────
# Celery workers are synchronous; they cannot use asyncpg.
# We derive a psycopg2 URL from the asyncpg one.
_sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(_sync_url, pool_pre_ping=True)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
