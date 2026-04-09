"""
ORVANTA Cloud - Application configuration
Loads environment variables with sensible defaults.
"""

from typing import List, Optional
import json

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ORVANTA"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://warops:warops_secret@localhost:5432/warops_db"
    DATABASE_URL_SYNC: str = "postgresql://warops:warops_secret@localhost:5432/warops_db"
    SQL_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-this-to-a-random-64-char-string-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8080",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",")]
        return value

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_async_database_url(cls, value):
        db_url = str(value or "").strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return db_url

    @field_validator("DATABASE_URL_SYNC", mode="before")
    @classmethod
    def normalize_sync_database_url(cls, value):
        db_url = str(value or "").strip()
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    # Ollama and AI routing
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    OLLAMA_CHAT_MODEL: str = "llama3.1:8b"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    GROQ_API_KEY: Optional[str] = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "openai/gpt-oss-20b"

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openrouter/free"

    NVIDIA_API_KEY: Optional[str] = None
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "openai/gpt-oss-20b"

    AI_CHAT_PROVIDER_ORDER: str = "groq,openrouter,nvidia,ollama,local"
    AI_CHAT_HISTORY_LIMIT: int = 8
    AI_CHAT_MAX_TOKENS: int = 420
    AI_CHAT_TIMEOUT_SECONDS: float = 45.0
    AI_CHAT_TEMPERATURE: float = 0.2
    OLLAMA_CHAT_ATTEMPT_TIMEOUT_SECONDS: float = 12.0
    AI_CHAT_ENABLE_WEB_CONTEXT: bool = True
    AI_CHAT_WEB_MAX_RESULTS: int = 4
    AI_CHAT_WEB_LOOKUP_TIMEOUT_SECONDS: float = 10.0

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@orvanta.local"
    SMTP_STARTTLS: bool = True
    SMTP_USE_TLS: bool = False
    SMTP_INBOX_URL: Optional[str] = None
    FRONTEND_URL: str = "http://localhost:3000"
    GOOGLE_CLIENT_ID: Optional[str] = None
    CLERK_ISSUER: Optional[str] = None
    CLERK_SECRET_KEY: Optional[str] = None
    CLERK_DEFAULT_ORG_ID: Optional[str] = None
    SUPABASE_URL: Optional[str] = None
    SUPABASE_JWT_ISSUER: Optional[str] = None
    SUPABASE_JWT_AUDIENCE: Optional[str] = "authenticated"

    # ACLED
    ACLED_API_KEY: Optional[str] = None
    ACLED_EMAIL: Optional[str] = None

    # GDELT
    GDELT_ENABLED: bool = True

    # Source policy
    OFFICIAL_ONLY_MODE: bool = True
    AUTO_INGEST_ENABLED: bool = False
    LIVE_SYNC_COOLDOWN_MINUTES: int = 5
    LIVE_SYNC_MAX_PER_FEED: int = 12
    LIVE_SYNC_BACKLOG_LIMIT: int = 150
    LIVE_SYNC_AUTO_ENABLED: bool = True
    LIVE_SYNC_AUTO_INTERVAL_SECONDS: int = 300

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
