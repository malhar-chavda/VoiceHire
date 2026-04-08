"""
Async SQLAlchemy engine + session factory for Voice_Hire.

Provides:
    engine — AsyncEngine  (used by main.py lifespan to create tables)
    AsyncSessionLocal — async_sessionmaker (used by nodes for DB writes)
    get_db() — FastAPI dependency that yields an AsyncSession per request

Why async?
    FastAPI is async-native. Using a sync engine with async routes forces
    a thread-pool workaround. AsyncEngine + AsyncSession integrates cleanly
    with FastAPI's event loop — no blocking, no thread overhead.

Usage in a node (LangGraph):
    from services.postgres_db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(some_model_instance)

Usage in a FastAPI route (via dependency injection):
    from services.postgres_db import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.post("/something")
    async def my_route(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Candidate))
        ...
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from utils.settings import settings

# Engine

def _build_async_url(url: str) -> str:
    """
    Convert a sync DATABASE_URL to its async equivalent.

    SQLAlchemy async requires the +asyncpg driver, not +psycopg2.
    This lets you keep DATABASE_URL as the standard psycopg2 format
    in .env and converts it automatically here.
    """
    url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


engine = create_async_engine(
    _build_async_url(settings.DATABASE_URL),

    echo=False, # True in dev/staging  → logs every SQL statement to console
                # False in production  → silent (use proper logging instead)

    pool_size=10, # Number of persistent connections kept open.

    max_overflow=20, # Extra connections allowed beyond pool_size under burst load.
    # Total max concurrent connections = pool_size + max_overflow = 30

    pool_pre_ping=True,
    # Sends a lightweight "SELECT 1" before handing out a connection.
    # Prevents "SSL connection has been closed unexpectedly" errors
    # that happen when Azure drops idle connections after ~30 minutes.

    pool_recycle=1800,
    # Force-recycle connections after 30 minutes regardless of activity.
    # Works alongside pool_pre_ping as a double guard against stale connections.
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    # expire_on_commit=False means ORM objects stay accessible after commit.
    # Without this, accessing an attribute after session.commit() would
    # trigger a lazy-load — which fails silently in async context.
)

# FastAPI dependency
async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    """
    FastAPI dependency — yields one AsyncSession per request.

    Injects a DB session into any route via Depends(get_db).
    Automatically commits on success, rolls back on exception,
    and always closes the session when the request ends.

    Example:
        @router.post("/candidates")
        async def create_candidate(
            data: CandidateSchema,
            db: AsyncSession = Depends(get_db)
        ):
            candidate = Candidate(**data.model_dump())
            db.add(candidate)
            await db.commit()
            return candidate
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# table creation  (called from main.py lifespan)
async def create_tables() -> None:

    # Import every model so SQLAlchemy registers them with Base.metadata —
    # Even if the import looks unused, removing it will silently skip
    # that table during create_all().
    from structure.entities import (  
        Base,
        JobDescription,
        Resume,
        Interview,
        Answer,
        FinalReport,
    )

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))