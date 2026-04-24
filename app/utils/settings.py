"""
Loads all environment variables from .env using Pydantic BaseSettings.

Stack: Azure OpenAI + Azure Blob Storage + Azure PostgreSQL
       + ElevenLabs TTS + Whisper STT

Usage (anywhere in the project):
    from utils.settings import settings

    db_url   = settings.DATABASE_URL
    api_key  = settings.AZURE_OPENAI_API_KEY

Rules:
  - Always import the singleton `settings`, never instantiate Settings() yourself
  - Never use os.environ directly in nodes or services
  - All fields have typed defaults — required fields (no default) will
    raise ValidationError on startup if missing from .env
  - .env values always override the defaults defined here
"""

from __future__ import annotations
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils.constants import (
    DEFAULT_LLM_MODEL,
    INTERVIEW_LINK_EXPIRY_HOURS,
    MAX_FOLLOWUPS_PER_QUESTION,
    MAX_INTERVIEW_QUESTIONS,
    MATCH_SCORE_THRESHOLD,
    PIPELINE_MAX_RETRIES,
    QUICK_SCORE_THRESHOLD,
)

class Settings(BaseSettings):
    """
    All environment-driven configuration for Voice_Hire.

    Sections:
        1.  Azure OpenAI — LLM + embeddings
        2.  Azure Blob — file storage (JD, resume, audio)
        3.  Azure PostgreSQL — relational DB
        4.  Azure Cognitive — TTS / STT (primary voice and recognition)
        5.  Whisper — STT (optional fallback)
        6.  FastAPI — server config + JWT
        7.  Pipeline — thresholds (override constants.py defaults)
        8.  LangGraph — checkpointer backend
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,    # DATABASE_URL ≠ database_url
        extra="ignore",         # unknown .env keys are silently ignored
    )
    
    FOLLOW_UP_THRESHOLD: float = 7.0  # Out of 10
    MAX_FOLLOW_UPS: int = 2           # Prevent infinite loops

    #  GOOGLE GEMINI 
    # Used for Realtime Speech-to-Speech loop
    GEMINI_API_KEY: str = ""


    #  AZURE OPENAI 
    # Used by: services/azure_openai.py

    AZURE_OPENAI_API_KEY: str
    # Your Azure OpenAI resource key — required, no default

    AZURE_OPENAI_ENDPOINT: str

    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    # Update when Microsoft releases new versions

    AZURE_DEPLOYMENT_FAST: str = "gpt-4.1-mini"
    # Used for Parsing, Interview loop, generating questions
    
    AZURE_DEPLOYMENT_SMART: str = "gpt-4.1"
    # Used for Matching, Final decision evaluations

    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-small"
    # Embedding deployment name — used by chunk_and_embed node

    #  AZURE BLOB STORAGE 
    # Used by: services/azure_blob.py

    AZURE_STORAGE_CONNECTION_STRING: str
    # Full connection string from Azure Portal → Storage Account → Access Keys

    AZURE_STORAGE_CONTAINER_NAME: str = "voicehire-uploads"
    # Container inside your storage account
    # Sub-folders: jd/, resume/, audio/, reports/

    #  AZURE COMMUNICATION SERVICES (EMAIL) 
    AZURE_COMMUNICATION_CONNECTION_STRING: str = "endpoint=...;accesskey=..."
    AZURE_SENDER_EMAIL: str = "donotreply@yourdomain.azurecomm.net"


    #  AZURE POSTGRESQL 
    # Used by: services/postgres_db.py

    DATABASE_URL: str
    # Format: postgresql+psycopg2://user:password@host:5432/dbname
    # Azure: postgresql+psycopg2://adminuser%40server:pass@server.postgres.database.azure.com:5432/voicehire_db

    #  AZURE COGNITIVE SERVICES (TTS / STT) 
    # Used for both TTS (primary voice) and optionally STT

    AZURE_SPEECH_KEY: str
    AZURE_SPEECH_REGION: str
    # e.g. "eastus", "southindia"

    # WHISPER STT 
    # STT_PROVIDER options:
    #   "api"   — OpenAI Whisper API (needs OPENAI_API_KEY)
    #   "azure" — Azure Cognitive STT (needs AZURE_SPEECH_KEY)
    #   "local" — faster-whisper (no key needed)

    STT_PROVIDER: str = "api"

    OPENAI_API_KEY: str = ""
    # Only needed if STT_PROVIDER = "api"
    # All LLM calls use Azure OpenAI — this is Whisper only

    WHISPER_MODEL: str = "whisper-1"

    #  7. FASTAPI 
    # Used by: app/main.py

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8006 
    APP_ENV: str = "development"
    # "development" | "staging" | "production"

    FRONTEND_BASE_URL: str = "http://localhost:3000"
    # The public-facing URL of the frontend app.
    # Used to build interview links sent via email.
    # Example (production): https://app.voicehire.io


    SECRET_KEY: str = "change-this-before-production"
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    # MUST be overridden in production .env

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"

    #  RECRUITER AUTH (Single User)
    RECRUITER_USERNAME: str = "admin"
    RECRUITER_PASSWORD: str = "admin123" 
    # Must be hashed in production, but for simplicity we allow plain-text override in .env

    #PIPELINE THRESHOLDS 
    # Overrides utils/constants.py defaults — change via .env without touching code

    MATCH_SCORE_THRESHOLD: float = MATCH_SCORE_THRESHOLD
    QUICK_SCORE_THRESHOLD: float = QUICK_SCORE_THRESHOLD
    MAX_FOLLOWUPS_PER_QUESTION: int = MAX_FOLLOWUPS_PER_QUESTION
    MAX_INTERVIEW_QUESTIONS: int = MAX_INTERVIEW_QUESTIONS
    PIPELINE_MAX_RETRIES: int = PIPELINE_MAX_RETRIES
    INTERVIEW_LINK_EXPIRY_HOURS: int = INTERVIEW_LINK_EXPIRY_HOURS

    #  LANGGRAPH 
    # Used by: graph/workflow.py

    LANGGRAPH_CHECKPOINTER: str = "sqlite"
    # "memory" — dev/testing only (no persistence)
    # "sqlite" — local dev
    # "postgres" — production (uses DATABASE_URL)

    LANGGRAPH_CHECKPOINT_DB: str = "./checkpoints.db"
    # Only used when LANGGRAPH_CHECKPOINTER = "sqlite"

    #  COMPUTED PROPERTIES 
    
    @property   
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def use_azure_speech(self) -> bool:
        """Mandatory check for Azure Speech configuration."""
        if not (self.AZURE_SPEECH_KEY and self.AZURE_SPEECH_REGION):
            return False
        return True

    @property
    def azure_openai_headers(self) -> dict[str, str]:
        """Ready-to-use headers for direct Azure OpenAI API calls."""
        return {
            "api-key": self.AZURE_OPENAI_API_KEY,
            "Content-Type": "application/json",
        }

@lru_cache(maxsize=1)   #remembers the result of a function (least recently used cache). 2nd call is made from the memory not from the .env file
                        #reading from RAM 
def get_settings() -> Settings:
    return Settings()

settings: Settings = get_settings()