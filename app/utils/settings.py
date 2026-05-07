from __future__ import annotations
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

"""
All hardcoded default values and environment-driven configuration for the Voice_Hire pipeline.
"""


# LLM — AZURE OPENAI
# Default deployment name — must match what you created in Azure OpenAI Studio

DEFAULT_LLM_MODEL: str = "gpt-4o"


# API version — update when Microsoft releases a newer stable version

AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"


# Embedding deployment name — used by chunk_and_embed node

DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"

EMBEDDING_DIMENSIONS: int = 1536


# Temperature per LLM call type

# 0.0 = fully deterministic, 1.0 = fully creative

LLM_TEMPERATURE_EXTRACTION: float = 0.0   # extract_structured_data — needs exact JSON

LLM_TEMPERATURE_MATCHING: float = 0.1   # llm_match_and_gap       — needs consistent scores

LLM_TEMPERATURE_QUESTIONS: float = 0.7   # generate_questions       — needs varied questions

LLM_TEMPERATURE_SCORING: float = 0.0   # quick_score + eval_batch — needs consistent scores

LLM_TEMPERATURE_FOLLOWUP: float = 0.5   # generate_followup        — needs contextual variety

LLM_TEMPERATURE_REPORT: float = 0.2   # generate_final_report    — needs professional tone


# Max tokens per LLM call type

LLM_MAX_TOKENS_EXTRACTION: int = 2000

LLM_MAX_TOKENS_MATCHING: int = 1500

LLM_MAX_TOKENS_QUESTIONS: int = 2000

LLM_MAX_TOKENS_QUICK_SCORE: int = 500

LLM_MAX_TOKENS_FOLLOWUP: int = 300

LLM_MAX_TOKENS_EVAL_BATCH: int = 4000

LLM_MAX_TOKENS_REPORT: int = 3000


# Retry settings for Azure OpenAI API calls

LLM_MAX_RETRIES: int           = 3

LLM_RETRY_DELAY_SECONDS: float = 2.0   # base delay exponential backoff applied on top


# PIPELINE THRESHOLDS


# Skill matching score_gate

# Candidates below this score → rejection path

MATCH_SCORE_THRESHOLD: float = 60.0        # 0.0â€“100.0


# Answer scoring

# Answers below this score in standalone evaluation → follow-up generated

QUICK_SCORE_THRESHOLD: float = 0.6         # 0.0â€“1.0


# Max follow-up questions per root question

MAX_FOLLOWUPS_PER_QUESTION: int = 2


# Total interview questions generated per candidate session

MAX_INTERVIEW_QUESTIONS: int = 10


# Minimum questions regardless of how many skill gaps exist

MIN_INTERVIEW_QUESTIONS: int = 5


# Max retries for any single pipeline operation

PIPELINE_MAX_RETRIES: int = 3


# PIPELINE DECISION VALUES

class PipelineDecision:

    PENDING = "pending"

    REJECTED = "rejected"

    SHORTLISTED = "shortlisted"

    HIRE = "hire"

    HOLD = "hold"

    REJECT = "reject"

    ERROR = "error"


# AUDIO CONFIGURATION (Gemini Live Defaults)

STT_LANGUAGE: str = "en"

MAX_AUDIO_DURATION_SECONDS: int = 300


# AZURE BLOB STORAGE FOLDER LAYOUT

BLOB_FOLDER_JD: str = "jd"

BLOB_FOLDER_RESUME: str = "resume"

BLOB_FOLDER_AUDIO: str = "audio"

BLOB_FOLDER_REPORTS: str = "reports"


ALLOWED_DOCUMENT_EXTENSIONS: list = [".pdf", ".docx", ".doc", ".txt"]

MAX_DOCUMENT_SIZE_MB: int = 10


# INTERVIEW SESSION

INTERVIEW_LINK_EXPIRY_HOURS: int = 48

SILENCE_TIMEOUT_SECONDS: int = 10


# SCORING SCALES

MATCH_SCORE_MIN: float = 0.0

MATCH_SCORE_MAX: float = 100.0

QUICK_SCORE_MIN: float = 0.0

QUICK_SCORE_MAX: float = 1.0

QUESTION_SCORE_MIN: float = 0.0

QUESTION_SCORE_MAX: float = 10.0

FINAL_SCORE_MIN: float = 0.0

FINAL_SCORE_MAX: float = 100.0


# EMAIL SUBJECT LINES

READY             = "ready"

WAIT              = "wait"


class Settings(BaseSettings):

    """

    All environment-driven configuration for Voice_Hire.


    Sections:

        1.  Azure OpenAI — LLM + embeddings

        2.  Azure Blob — file storage (JD, resume, audio)

        3.  Azure PostgreSQL — relational DB

        Section:

        1.  Azure OpenAI LLM + embeddings
        1.  Google Gemini Realtime Speech loop

        2.  Azure OpenAI LLM + embeddings (Matching/Parsing)

        3.  Azure Blob file storage (JD, resume, audio)

        4.  Azure Communication Email notifications

        5.  Azure PostgreSQL Relational DB

        6.  FastAPI server config + JWT

        7.  Pipeline thresholds

    """
    model_config = SettingsConfigDict(

        env_file=".env",

        env_file_encoding="utf-8",

        case_sensitive=True,    # DATABASE_URL Ã¢â€°  database_url

        extra="ignore",         # unknown .env keys are silently ignored

    )

    

    FOLLOW_UP_THRESHOLD: float = 7.0  # Out of 10

    MAX_FOLLOW_UPS: int = 2           # Prevent infinite loops


    #  GOOGLE GEMINI 

    # Used for Realtime Speech-to-Speech loop

    GEMINI_API_KEY: str = "AIzaSyA87PFg-4FJDFQRk-iTF2uVDeP5yyLfm24"


    #  AZURE OPENAI 

    # Used by: services/azure_openai.py


    AZURE_OPENAI_API_KEY: str

    # Your Azure OpenAI resource key — required, no default


    AZURE_OPENAI_ENDPOINT: str


    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"

    # Update when Microsoft releases new versions


    AZURE_DEPLOYMENT_FAST: str = "gpt-4.1-mini"

    # Used for Parsing, Interview loop, generating questions

    

    AZURE_DEPLOYMENT_SMART: str = "gpt-4.1"

    # Used for Matching, Final decision evaluations


    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-small"

    # Embedding deployment name — used by chunk_and_embed node


    #  AZURE BLOB STORAGE 

    # Used by: services/azure_blob.py


    AZURE_STORAGE_CONNECTION_STRING: str

    # Full connection string from Azure Portal Ã¢â€ â€™ Storage Account Ã¢â€ â€™ Access Keys


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

    # Overrides utils/constants.py defaults — change via .env without touching code


    MATCH_SCORE_THRESHOLD: float = MATCH_SCORE_THRESHOLD

    QUICK_SCORE_THRESHOLD: float = QUICK_SCORE_THRESHOLD

    MAX_FOLLOWUPS_PER_QUESTION: int = MAX_FOLLOWUPS_PER_QUESTION

    MAX_INTERVIEW_QUESTIONS: int = MAX_INTERVIEW_QUESTIONS

    PIPELINE_MAX_RETRIES: int = PIPELINE_MAX_RETRIES

    INTERVIEW_LINK_EXPIRY_HOURS: int = INTERVIEW_LINK_EXPIRY_HOURS


    #  COMPUTED PROPERTIES 
    @property   
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache(maxsize=1)   #remembers the result of a function (least recently used cache). 2nd call is made from the memory not from the .env file

                        #reading from RAM 

def get_settings() -> Settings:

    return Settings()


settings: Settings = get_settings()


