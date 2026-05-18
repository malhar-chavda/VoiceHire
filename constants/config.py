from __future__ import annotations
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    """
    Environment-driven configuration for VoiceHire.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # CORE 
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8006
    APP_ENV: str = "development"
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    SECRET_KEY: str = "change-this-before-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"

    # RECRUITER AUTH
    RECRUITER_USERNAME: str = "admin"
    RECRUITER_PASSWORD: str = "admin123"

    # GOOGLE GEMINI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash-live-preview"

    # AZURE OPENAI 
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    AZURE_DEPLOYMENT_FAST: str = "gpt-4o-mini"
    AZURE_DEPLOYMENT_SMART: str = "gpt-4o"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # --- AZURE BLOB STORAGE ---
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER_NAME: str = "voicehire-uploads"
    BLOB_FOLDER_JD: str = "jd"
    BLOB_FOLDER_RESUME: str = "resume"
    BLOB_FOLDER_AUDIO: str = "audio"
    BLOB_FOLDER_REPORTS: str = "reports"

    # --- AZURE COMMUNICATION SERVICES (EMAIL) ---
    AZURE_COMMUNICATION_CONNECTION_STRING: str = ""
    AZURE_SENDER_EMAIL: str = "donotreply@yourdomain.azurecomm.net"

    # --- AZURE POSTGRESQL ---
    DATABASE_URL: str = ""

    # --- PIPELINE THRESHOLDS ---
    MATCH_SCORE_THRESHOLD: float = 60.0
    QUICK_SCORE_THRESHOLD: float = 0.6
    FOLLOW_UP_THRESHOLD: float = 7.0
    MAX_FOLLOWUPS_PER_QUESTION: int = 2
    MAX_INTERVIEW_QUESTIONS: int = 10
    MIN_INTERVIEW_QUESTIONS: int = 5
    PIPELINE_MAX_RETRIES: int = 3
    INTERVIEW_LINK_EXPIRY_HOURS: int = 48
    SILENCE_TIMEOUT_SECONDS: int = 10

    # --- DOCUMENT CONFIG ---
    ALLOWED_DOCUMENT_EXTENSIONS: list[str] = [".pdf", ".docx", ".doc", ".txt"]
    MAX_DOCUMENT_SIZE_MB: int = 10

    # --- LLM TEMPERATURES ---
    LLM_TEMPERATURE_EXTRACTION: float = 0.0
    LLM_TEMPERATURE_MATCHING: float = 0.1
    LLM_TEMPERATURE_QUESTIONS: float = 0.7
    LLM_TEMPERATURE_SCORING: float = 0.0
    LLM_TEMPERATURE_FOLLOWUP: float = 0.5
    LLM_TEMPERATURE_REPORT: float = 0.2

    # --- LLM MAX TOKENS ---
    LLM_MAX_TOKENS_EXTRACTION: int = 2000
    LLM_MAX_TOKENS_MATCHING: int = 1500
    LLM_MAX_TOKENS_QUESTIONS: int = 2000
    LLM_MAX_TOKENS_QUICK_SCORE: int = 500
    LLM_MAX_TOKENS_FOLLOWUP: int = 300
    LLM_MAX_TOKENS_EVAL_BATCH: int = 4000
    LLM_MAX_TOKENS_REPORT: int = 3000

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    # --- EMAIL SUBJECTS ---
    EMAIL_SUBJECT_INTERVIEW_INVITE: str = "Your interview invitation — VoiceHire"
    EMAIL_SUBJECT_REJECTION: str = "Update on your application — VoiceHire"
    EMAIL_SUBJECT_HIRE: str = "Congratulations! Next steps — VoiceHire"
    EMAIL_SUBJECT_HOLD: str = "Application update — VoiceHire"
    EMAIL_SUBJECT_POST_REJECT: str = "Update on your application — VoiceHire"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

@lru_cache(maxsize=1)
def get_settings() -> Config:
    return Config()

settings: Config = get_settings()
