from __future__ import annotations
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from langchain_openai import AzureChatOpenAI
from constants.config import settings

def _build_async_url(url: str) -> str:
    """Convert a sync DATABASE_URL to its async equivalent."""
    url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url

class App:
    engine = create_async_engine(
        _build_async_url(settings.DATABASE_URL),
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    smart_llm = AzureChatOpenAI(
        azure_deployment=settings.AZURE_DEPLOYMENT_SMART,
        api_key=settings.AZURE_OPENAI_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version="2024-08-01-preview",
        temperature=0.2,
        timeout=60,
    )

    fast_llm = AzureChatOpenAI(
        azure_deployment=settings.AZURE_DEPLOYMENT_FAST,
        api_key=settings.AZURE_OPENAI_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version="2024-08-01-preview",
        temperature=0.2,
        timeout=60,
    )
