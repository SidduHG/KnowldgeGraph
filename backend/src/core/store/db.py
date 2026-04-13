from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Dependency for FastAPI routes ─────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# ── Convenience context manager ───────────────────────────────────────────────
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# ── Init DB (run migrations) ──────────────────────────────────────────────────
async def init_db() -> None:
    migration_file = Path(__file__).parent / "migrations" / "001_initial.sql"
    if not migration_file.exists():
        logger.error("Migration file not found: %s", migration_file)
        return

    raw_sql = migration_file.read_text(encoding="utf-8")
    # split on ; but ignore empty statements
    statements = [s.strip() for s in raw_sql.split(";") if s.strip()]

    async with engine.begin() as conn:
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:
                # table/index already exists → safe to ignore
                if "already exists" in str(exc).lower():
                    continue
                logger.warning("Migration warning: %s", exc)

    logger.info("✓ Database schema ready")

async def close_db() -> None:
    await engine.dispose()
    logger.info("Database connections closed")
