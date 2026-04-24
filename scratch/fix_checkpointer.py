"""
Recovery: directly re-populates checkpoint_migrations using asyncpg (autocommit).
The LangGraph tables + indexes already exist — we just need to restore the
migration tracking records so setup() becomes a no-op on next startup.

Usage: python scratch/fix_checkpointer.py
"""
import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.utils.settings import settings
import asyncpg

# Inspect how many migrations LangGraph has in the installed version
try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    num_migrations = len(AsyncPostgresSaver.MIGRATIONS)
    print(f"Detected {num_migrations} LangGraph migrations.")
except Exception:
    num_migrations = 9   # safe upper bound for langgraph >=0.2
    print(f"Could not inspect LangGraph migrations — using upper bound {num_migrations}.")


async def main():
    raw = settings.DATABASE_URL
    dsn = (
        raw.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgresql+psycopg2://",  "postgresql://")
           .replace("postgresql+psycopg://",   "postgresql://")
    )
    use_ssl = "ssl=require" in dsn
    dsn_clean = dsn.replace("?ssl=require", "").replace("&ssl=require", "")

    print(f"Connecting to: {dsn_clean.split('@')[-1]}")
    conn = await asyncpg.connect(dsn_clean, ssl="require" if use_ssl else None)

    try:
        # Check current state of checkpoint_migrations
        rows = await conn.fetch("SELECT v FROM checkpoint_migrations ORDER BY v;")
        current = [r["v"] for r in rows]
        print(f"Current migration records: {current}")

        # Insert all versions that are missing
        inserted = 0
        for v in range(1, num_migrations + 1):
            if v not in current:
                await conn.execute(
                    "INSERT INTO checkpoint_migrations (v) VALUES ($1) ON CONFLICT DO NOTHING;", v
                )
                print(f"  Inserted migration v={v}")
                inserted += 1
            else:
                print(f"  Skipped  migration v={v} (already present)")

        if inserted == 0:
            print("checkpoint_migrations already fully populated — nothing to do.")
        else:
            print(f"\nInserted {inserted} migration records. Server should now start normally.")

    finally:
        await conn.close()


asyncio.run(main())
