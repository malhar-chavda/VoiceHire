import platform
import collections
platform._wmi_query = lambda *args, **kwargs: ["9"]
uname_result = collections.namedtuple("uname_result", "system node release version machine processor")
platform.uname = lambda: uname_result("Windows", "PC", "10", "10.0.26200", "AMD64", "AMD64")
platform.machine = lambda: "AMD64"
platform.win32_ver = lambda *args, **kwargs: ('10', '10.0.26200', 'SP0', 'Multiprocessor Free')

import logging
import sys
import io
import os

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles

from endpoints.job_description import router as jd_router
from endpoints.candidates import router as resume_router
from endpoints.interview import router as interview_router
from endpoints.auth import router as auth_router
from endpoints.evaluation import router as evaluation_router
from endpoints.documents import router as documents_router

from utils.core.data.postgres_db import create_tables, engine
from constants.config import settings
from logging.handlers import RotatingFileHandler

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

file_handler = RotatingFileHandler(
    'debug_app.log', maxBytes=50_000_000, backupCount=3, encoding='utf-8'
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)
log = logging.getLogger("voicehire.main")

# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("VoiceHire API starting up...")
    log.info(f"Environment: {settings.APP_ENV}")
    log.info(f"DB host: {_safe_db_host(settings.DATABASE_URL)}")

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("PostgreSQL connection verified")
    except Exception as e:
        log.error(f"DB connection FAILED: {e}")
        raise

    try:
        await create_tables()
        log.info("Tables verified / created.")
    except Exception as e:
        log.error(f"Table creation FAILED: {e}")
        raise

    log.info(f"VoiceHire API ready on http://{settings.APP_HOST}:{settings.APP_PORT}")
    yield

    log.info("VoiceHire API shutting down...")
    try:
        await engine.dispose()
    except Exception as e:
        log.warning(f"Error during engine disposal: {e}")
    log.info("Shutdown complete.")


app = FastAPI(
    title="VoiceHire API",
    description="VoiceHire pipeline",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Middleware
ALLOWED_ORIGINS_DEV = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8006",
    "http://127.0.0.1:8006",
]

ALLOWED_ORIGINS_PROD = [
    "https://yourdomain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS_DEV if settings.is_development else ALLOWED_ORIGINS_PROD,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(evaluation_router, prefix="/api/interview", tags=["Evaluation"])
app.include_router(interview_router, prefix="/api/interview", tags=["Interview"])
app.include_router(jd_router, prefix="/api")
app.include_router(resume_router, prefix="/api")


@app.get("/health", tags=["System"], include_in_schema=True)
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}


# Serve frontend
if os.path.isdir("frontend"):
    app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")
    log.info("Frontend served at /ui (http://%s:%s/ui/)", settings.APP_HOST, settings.APP_PORT)


def _safe_db_host(db_url: str) -> str:
    try:
        return db_url.split("@")[-1]
    except Exception:
        return "unknown"


if __name__ == "__main__":
    log.info(f"Starting VoiceHire API on http://{settings.APP_HOST}:{settings.APP_PORT}")
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
        reload_includes=["*.py"],
        reload_excludes=["*.log", "*.db", "*.sqlite3", "*.pyc"],
        log_level="info",
        loop="asyncio"
    )
