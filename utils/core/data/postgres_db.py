from __future__ import annotations
"""
Async SQLAlchemy engine + session factory for Voice_Hire.

Provides
    engine AsyncEngine  (used by main.py lifespan to create tables)
    AsyncSessionLocal async_sessionmaker (used by nodes for DB writes)
    get_db() FastAPI dependency that yields an AsyncSession per request
"""

from collections.abc import AsyncGenerator
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.app import App

# Proxy objects from App class
engine = App.engine
AsyncSessionLocal = App.AsyncSessionLocal

# FastAPI dependency
async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    """
    Injects a DB session into any route through depends(get_db).
    Automatically commits on success, rolls back on exception,
    and always closes the session when the request ends.
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

# table creation (called from main.py lifespan)
async def create_tables() -> None:
    """Imports all the database models and creates tables."""
    from models.entities import (
        Base,
        JobDescription,
        Resume,
        Interview,
        Answer,
        FinalReport,
    )

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))