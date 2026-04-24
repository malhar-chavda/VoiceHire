"""
Truncates all VoiceHire app tables and LangGraph checkpoint tables.
Keeps table structure intact — only deletes rows.
Run from project root: python scratch/clear_db.py
"""
import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.utils.settings import settings

import asyncpg

# Tables ordered to satisfy FK constraints (children first)
APP_TABLES = [
    "final_reports",
    "answers",
    "interviews",
    "resumes",
    "job_descriptions",
]

LANGGRAPH_TABLES = [
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
    # NOTE: do NOT truncate checkpoint_migrations — it tracks schema version
    #       and clearing it breaks LangGraph startup (CREATE INDEX CONCURRENTLY issue)
]

async def main():
    # Build raw DSN from DATABASE_URL
    raw_url = settings.DATABASE_URL
    # Convert SQLAlchemy async DSN to asyncpg DSN
    dsn = (
        raw_url
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
        .replace("postgresql+psycopg://",  "postgresql://")
    )

    print(f"Connecting to: {dsn.split('@')[-1]}")

    # asyncpg does not accept ssl=require as a query param; pass it natively
    use_ssl = "ssl=require" in dsn
    dsn_clean = dsn.replace("?ssl=require", "").replace("&ssl=require", "")

    conn = await asyncpg.connect(dsn_clean, ssl="require" if use_ssl else None)

    try:
        # ── App tables (CASCADE handles FK deps) ──────────────────
        print("\n[APP TABLES]")
        for tbl in APP_TABLES:
            try:
                result = await conn.execute(f"TRUNCATE TABLE {tbl} CASCADE;")
                print(f"  TRUNCATED  {tbl}")
            except Exception as e:
                print(f"  SKIPPED    {tbl}  ({e})")

        # ── LangGraph checkpoint tables ───────────────────────────
        print("\n[LANGGRAPH TABLES]")
        for tbl in LANGGRAPH_TABLES:
            try:
                result = await conn.execute(f"TRUNCATE TABLE {tbl} CASCADE;")
                print(f"  TRUNCATED  {tbl}")
            except Exception as e:
                print(f"  SKIPPED    {tbl}  ({e})")

        # ── Verify row counts ─────────────────────────────────────
        print("\n[VERIFICATION - all should be 0]")
        for tbl in APP_TABLES:
            try:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl};")
                status = "OK" if count == 0 else f"WARNING: {count} rows remain"
                print(f"  {tbl:25s}  rows={count}  {status}")
            except Exception as e:
                print(f"  {tbl:25s}  (table not found)")

        print("\nDatabase cleared successfully.")

    finally:
        await conn.close()

asyncio.run(main())
