import asyncio, sys
sys.path.append('.')
from app.utils.settings import settings
import asyncpg

async def main():
    dsn = settings.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://').replace('?ssl=require', '')
    conn = await asyncpg.connect(dsn, ssl='require')
    rows = await conn.fetch('SELECT id, status, session_token FROM interviews ORDER BY created_at DESC LIMIT 3')
    for r in rows:
        tok = str(r['session_token'] or '')
        print(f"id={r['id']}  status={r['status']}")
        print(f"token={tok}")
        print()
    await conn.close()

asyncio.run(main())
