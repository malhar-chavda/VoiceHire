from __future__ import annotations
"""
Async SQLAlchemy engine + session factory for Voice_Hire.

Provides
    engine AsyncEngine  (used by main.py lifespan to create tables)
    AsyncSessionLocal async_sessionmaker (used by nodes for DB writes)
    get_db() FastAPI dependency that yields an AsyncSession per request

Why async
    FastAPI is async-native. Using a sync engine with async routes forces
    a thread-pool workaround. AsyncEngine + AsyncSession integrates cleanly
    with FastAPI's event loop no blocking, no thread overhead.

Usage in a node (LangGraph):
    from services.postgres_db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(some_model_instance)
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.utils.settings import settings

# Engine

def _build_async_url(url: str) -> str:
    """Convert a sync DATABASE_URL to its async equivalent."""

    url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


engine = create_async_engine(
    _build_async_url(settings.DATABASE_URL),

    echo=False, # True in dev/staging - logs every SQL statement to console
                # False in production  - silent (use proper logging instead)

    pool_size=10, # Number of persistent connections kept open.

    max_overflow=20, 

    pool_pre_ping=True, #sends SELECT 1 query to check the liveness of the db

    pool_recycle=1800, #Force-recycle connections after 30 minutes regardless of activity.
)

#Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, #saves the candidate data to conserve memory
)
 
#FastAPI dependency
async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    """
    Injects a DB session into any route through depends(get_db).
    Automatically commits on success, rolls back on exception,
    and always closes the session when the request ends.
    """
    async with AsyncSessionLocal() as session:  # creates a new session for each request
        try:
            yield session
            await session.commit()  # commits the transaction
        except Exception:
            await session.rollback()  # rolls back the transaction on exception
            raise
        finally:
            await session.close()  # closes the session

# table creation  (called from main.py lifespan)
async def create_tables() -> None:
    """imports all the database models """
    from app.structure.entities import (  
        Base,
        JobDescription,
        Resume,
        Interview,
        Answer,
        FinalReport,
    )

    async with engine.begin() as conn: #using run_sync to create tables 
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))


