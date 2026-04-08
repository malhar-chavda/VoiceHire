from __future__ import annotations  

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from contextlib import asynccontextmanager # lifespan application
from typing import AsyncGenerator  

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.routes.job_description import router as jd_router
from app.routes.resume import router as resume_router
from app.routes.interview import router as interview_router


from services.postgres_db import create_tables, engine 
from utils.settings import settings  

# Logger  

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("voicehire.main")

# Lifespan

@asynccontextmanager  
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]: 
    """
    FastAPI lifespan context manager.

    Everything BEFORE yield  → runs on startup
    Everything AFTER  yield  → runs on shutdown

    Replaces the deprecated @app.on_event("startup") pattern.
    """
    # STARTUP
    log.info(" VoiceHire API starting up...")
    log.info(f" Environment : {settings.APP_ENV}")
    log.info(f" DB host : {_safe_db_host(settings.DATABASE_URL)}")

    # 1 verify DB connection before attempting table creation
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("PostgreSQL connection verified")
    except Exception as e:
        log.error(f"PostgreSQL connection FAILED: {e}")
        log.error("Check DATABASE_URL in your .env file")
        raise   # abort startup — no point running without a DB

    # 2  create tables if they don't exist
    # Uses CREATE TABLE IF NOT EXISTS internally — safe on every restart.
    # Existing tables and their data are never modified.
    try:
        await create_tables()
        log.info("Tables verified / created:")
        log.info(" -> job_description")
        log.info(" -> resume")
        log.info(" -> interview")
        log.info(" -> answer")
        log.info(" -> final_report")
    except Exception as e:
        log.error(f"Table creation FAILED: {e}")
        raise

    log.info(f"  VoiceHire API ready on http://{settings.APP_HOST}:{settings.APP_PORT}")

    yield   # ← application runs here, handling requests

    # SHUTDOWN
    log.info("VoiceHire API shutting down...")
    await engine.dispose()
    # dispose() waits for active connections to finish, then closes
    # all pooled connections cleanly — no dangling connections on Azure.
    log.info("Database engine disposed. Goodbye.")

# App
app = FastAPI(
    title="VoiceHire API",
    description="VoiceHire pipeline",
    version="1.0.0",
    docs_url="/docs",          
    redoc_url="/redoc",         
    lifespan=lifespan,
)

# Middleware  #
ALLOWED_ORIGINS_DEV = [   
    "http://localhost:3000",   
    "http://localhost:8501",    
    "http://127.0.0.1:8501",
]

ALLOWED_ORIGINS_PROD = [
    "https://yourdomain.com",  # replace before deploying # this is for the frontend to connect to the backend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS_DEV if settings.is_development else ALLOWED_ORIGINS_PROD,   # this is for the frontend to connect to the backend
    allow_credentials=True,   # this is for the frontend to send cookies to the backend
    allow_methods=["GET", "POST", "PUT", "DELETE"],   # this is for the frontend to send requests to the backend
    allow_headers=["Authorization", "Content-Type"],   # send headers to the backend
)

app.include_router(interview_router, prefix="/api/interview", tags=["Interview"])
# app.include_router(candidate_router, prefix="/api/candidate", tags=["Candidate"])
# app.include_router(files_router,     prefix="/api/files",     tags=["Files"])

app.include_router(jd_router)
app.include_router(resume_router)


# @app.get("/status", tags=["Status"])
# async def health_check() -> dict:
#     """
#     Lightweight health check endpoint.
#     Used by Azure App Service / load balancer to verify the app is alive.
#     Does NOT hit the database — for DB health use /health/db.
#     """
#     return {
#         "status": "ok",
#         "environment": settings.APP_ENV,
#         "version": "1.0.0",
#     }


# @app.get("/status/db", tags=["Status"])
# async def db_health_check() -> dict:
#     """
#     Database connectivity check.
#     Runs a lightweight SELECT 1 against PostgreSQL.
#     """
#     try:
#         async with engine.connect() as conn:
#             await conn.execute(text("SELECT 1"))
#         return {"status": "ok", "database": "connected"}
#     except Exception as e:
#         return {"status": "error", "database": str(e)}

def _safe_db_host(db_url: str) -> str:
    """
    Extract just the host from DATABASE_URL for safe logging.
    Strips credentials so they never appear in logs.

    postgresql+asyncpg://user:pass@hostname:5432/db  →  hostname:5432/db
    """
    try:
        return db_url.split("@")[-1]
    except Exception:
        return "unknown"

if __name__ == "__main__":

    uvicorn.run(
        "main:app", 
        host="127.0.0.1",
        port=8000,
        reload=True 
    )


    #  0;c;1;P;c;5;o;1;f;0;0l;3;0v;3;0g;1;0o;0;0a;1;0f;0;1b;0