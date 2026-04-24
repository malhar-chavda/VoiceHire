import logging
import sys
import asyncio

if sys.platform == "win32": 
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  

from contextlib import asynccontextmanager # lifespan application
from typing import AsyncGenerator, Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.routes.job_description import router as jd_router
from app.routes.resume import router as resume_router
from app.routes.interview import router as interview_router
from app.routes.auth import router as auth_router
from app.routes.evaluation import router as evaluation_router
from app.routes.documents import router as documents_router  
from fastapi.staticfiles import StaticFiles #serving static files like html,css,js to be displayed on browser
import os

from app.services.postgres_db import create_tables, engine
from app.graph.workflow import init_graph
from app.utils.settings import settings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

#logger  

from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(   #PRINTING THE ERROR MESSAGES IN DEBUG_APP.LOG FILE
    'debug_app.log', maxBytes=50_000_000, backupCount=3
)
file_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, logging.StreamHandler()]
)
log = logging.getLogger("voicehire.main")

# Lifespan

@asynccontextmanager  
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]: 
    """
    FastAPI lifespan context manager.

    Everything BEFORE yield  → runs on startup
    Everything AFTER  yield  → runs on shutdown
    """
    # STARTUP
    log.info(" VoiceHire API starting up...")
    log.info(f" Environment : {settings.APP_ENV}")
    log.info(f" DB host : {_safe_db_host(settings.DATABASE_URL)}")

    try:
        async with engine.connect() as conn:   #database connection checking and runs a SELECT 1 query
            await conn.execute(text("SELECT 1"))
        log.info("PostgreSQL connection verified")
    except Exception as e:
        log.error(f"DB connection FAILED: {e}")
        raise
    # .env check
    if settings.STT_PROVIDER == "api" and not settings.OPENAI_API_KEY:  #checking the openai provider has required credentials
        log.warning(
            "STT_PROVIDER='api' requires OPENAI_API_KEY — it is not set. "
            "Spoken answers will fall back to empty text and score 0."
        )
    elif settings.STT_PROVIDER == "azure" and not settings.AZURE_SPEECH_KEY:  #checking the stt azure provider has required credentials
        log.warning(
            "STT_PROVIDER='azure' requires AZURE_SPEECH_KEY — it is not set. "
            "Spoken answers will fall back to empty text and score 0."
        )

    #creating tables if not exist from entities.py
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

    #langgraph initialization with postgres checkpointer
    #creates checkpoint tables and compiles the interview graph.
    try:
        conn_string = (
            settings.DATABASE_URL
            .replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
            .replace("ssl=require", "sslmode=require")
        )
        
        #use explicit pool with health checks and shorter idle timeouts for Azure stability
        pool_kwargs = {
            "max_size": 40,  #max 40 db connections
            "min_size": 1,   #min 1 db connection
            "max_idle": 30,  #rotate idle connections every 30s
            "num_workers": 1, #opening closing etc
            "check": AsyncConnectionPool.check_connection, #verifying connection(runs SELECT 1)
        }
        
        async with AsyncConnectionPool(conn_string, **pool_kwargs) as pool:
            log.info("Lifespan: AsyncConnectionPool context manager entered")
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            log.info("Lifespan: Checkpointer setup complete")
            
            # Compile and store in app state for reliable access across routes
            try:
                graph = await init_graph(checkpointer)
                setattr(app.state, "interview_graph", graph)
                log.info("Lifespan: interview_graph successfully stored in app.state")
            except Exception as e:
                log.error(f"Lifespan: Failed to initialize or store graph: {e}")
                raise
            
            log.info(f"Lifespan: VoiceHire API ready on http://{settings.APP_HOST}:{settings.APP_PORT}")
            yield   # application remains inside this pool context. Stops the lifespan function

    except Exception as e:
        log.error(f"LangGraph graph init FAILED: {e}")
        raise

    # SHUTDOWN
    log.info("VoiceHire API shutting down...")
    await engine.dispose()        #waits for active connections to finish, then closes
    log.info("System is gone! Nothing's left to care about here!!!")

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
    "http://127.0.0.1:3000",   # local frontend urls (Vite/React/Next)
    "http://localhost:5500",   # VS Code Live Server
    "http://127.0.0.1:5500",
]

ALLOWED_ORIGINS_PROD = [
    "https://yourdomain.com",  # replace before deploying # this is for the frontend to connect to the backend
]
#middleware to prevent CORS error when connecting to backend
app.add_middleware(  # controls which frontend access the backend
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS_DEV if settings.is_development else ALLOWED_ORIGINS_PROD, #connects frontend and backend running on different ports
    allow_credentials=True,   #frontend send credentials to the backend and vise versa
    allow_methods=["GET", "POST", "PUT", "DELETE"],   
    allow_headers=["Authorization", "Content-Type"],   #send metadata to the backend
)

app.include_router(auth_router, prefix="/api") 
app.include_router(documents_router, prefix="/api")
app.include_router(evaluation_router, prefix="/api/interview", tags=["Evaluation"])
app.include_router(interview_router, prefix="/api/interview", tags=["Interview"])
app.include_router(jd_router, prefix="/api")
app.include_router(resume_router, prefix="/api")


@app.get("/health", tags=["System"], include_in_schema=True)  #cloud will ping the endpoint to check if the server is running
async def health_check():
    """Liveness probe — confirms the API process is running."""
    return {"status": "ok", "env": settings.APP_ENV}


# Serve frontend at /ui  (must be mounted AFTER all API routes)
if os.path.isdir("frontend"):  #hosting frontend at /ui
    app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")
    log.info("Frontend served at /ui (http://%s:%s/ui/)", settings.APP_HOST, settings.APP_PORT)

def _safe_db_host(db_url: str) -> str:  #extract just the host from DATABASE_URL for safe logging
    """
    Strips credentials so they never appear in logs.
    Secures the db url by removing the credentials
    postgresql+asyncpg://user:pass@hostname:5432/db  →  hostname:5432/db
    """
    try:
        return db_url.split("@")[-1]
    except Exception:
        return "unknown"

if __name__ == "__main__":
    import selectors
    
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
    
    config = uvicorn.Config(
        app, 
        host=settings.APP_HOST, 
        port=settings.APP_PORT, 
        loop="asyncio",
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    if sys.platform == "win32":
        loop.run_until_complete(server.serve())
    else:
        asyncio.run(server.serve())