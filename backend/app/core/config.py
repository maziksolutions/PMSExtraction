from __future__ import annotations

import os
from urllib.parse import quote, urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Maritime PMS Data Extraction Tool"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "production"
    EXPOSE_API_DOCS: bool = False

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_HOURS: int = 8
    MAX_REQUEST_SIZE_BYTES: int = 60 * 1024 * 1024
    REQUIRE_STRICT_UPLOAD_VALIDATION: bool = True
    ENFORCE_TRUSTED_HOST_MIDDLEWARE: bool = False

    # Database — Railway provides postgresql://, we need postgresql+asyncpg:// for async SQLAlchemy
    DATABASE_URL: str = "postgresql+asyncpg://pms_user:pms_password_dev@localhost:5432/pms_extraction"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Azure AD (optional SSO)
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://maritime-pms-tool-production.up.railway.app",
    ]
    ALLOWED_ORIGINS_REGEX: str = r"https://.*\.up\.railway\.app"
    TRUSTED_HOSTS: list[str] = [
        "localhost",
        "127.0.0.1",
        "*.up.railway.app",
        "*.railway.internal",
    ]

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # MinIO (local dev)
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "pms-manuals"

    # Azure Blob Storage (production — leave blank in dev to use MinIO)
    AZURE_STORAGE_ACCOUNT: str = ""
    AZURE_STORAGE_KEY: str = ""
    AZURE_STORAGE_CONTAINER: str = "pms-manuals"

    # Azure Translator
    AZURE_TRANSLATOR_KEY: str = ""
    AZURE_TRANSLATOR_ENDPOINT: str = "https://api.cognitive.microsofttranslator.com"

    # SharePoint / Graph API
    SHAREPOINT_REDIRECT_URI: str = "http://localhost:3000/auth/sharepoint/callback"

    # Default tenant
    DEFAULT_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"

    # OpenAI / AI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_ID: str = "gpt-4.1"
    OPENAI_VISION_MODEL_ID: str = "gpt-4.1"
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL_ID: str = "claude-sonnet-4-6"
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    EXTRACTION_MAX_TOKENS: int = 8192
    EXTRACTION_CHUNK_CHARS: int = 14000
    EXTRACTION_CHUNK_OVERLAP_CHARS: int = 500
    MANUAL_EXTRACTION_CONCURRENCY: int = 4
    MANUAL_SCREENING_CONCURRENCY: int = 2
    MANUAL_SCREENING_DELAY_SECONDS: float = 2.0
    HOT_PATH_MAINTENANCE_TTL_SECONDS: float = 300.0

    # File storage (local disk — ephemeral on Railway; mount a Volume for persistence)
    UPLOAD_DIR: str = "/tmp/pms_uploads"

    # Azure Document Intelligence
    AZURE_DOC_INTELLIGENCE_KEY: str = ""
    AZURE_DOC_INTELLIGENCE_ENDPOINT: str = ""

    @model_validator(mode="before")
    @classmethod
    def _apply_platform_aliases(cls, data):
        payload = dict(data or {})

        redis_url = (
            payload.get("REDIS_URL")
            or os.getenv("REDIS_URL")
            or payload.get("REDIS_PRIVATE_URL")
            or os.getenv("REDIS_PRIVATE_URL")
            or payload.get("REDIS_PUBLIC_URL")
            or os.getenv("REDIS_PUBLIC_URL")
        )
        if not redis_url:
            redis_host = (
                payload.get("REDISHOST")
                or os.getenv("REDISHOST")
                or payload.get("REDIS_HOST")
                or os.getenv("REDIS_HOST")
            )
            redis_port = (
                payload.get("REDISPORT")
                or os.getenv("REDISPORT")
                or payload.get("REDIS_PORT")
                or os.getenv("REDIS_PORT")
            )
            redis_user = (
                payload.get("REDISUSER")
                or os.getenv("REDISUSER")
                or payload.get("REDIS_USER")
                or os.getenv("REDIS_USER")
            )
            redis_password = (
                payload.get("REDISPASSWORD")
                or os.getenv("REDISPASSWORD")
                or payload.get("REDIS_PASSWORD")
                or os.getenv("REDIS_PASSWORD")
            )
            redis_db = (
                payload.get("REDIS_DB")
                or os.getenv("REDIS_DB")
                or payload.get("REDISDATABASE")
                or os.getenv("REDISDATABASE")
                or "0"
            )
            if redis_host:
                auth = ""
                if redis_user and redis_password:
                    auth = f"{quote(str(redis_user))}:{quote(str(redis_password))}@"
                elif redis_password:
                    auth = f":{quote(str(redis_password))}@"
                redis_url = f"redis://{auth}{redis_host}:{redis_port or '6379'}/{redis_db}"
        if redis_url:
            payload["REDIS_URL"] = redis_url

        database_url = (
            payload.get("DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or payload.get("POSTGRES_URL")
            or os.getenv("POSTGRES_URL")
            or payload.get("POSTGRESQL_URL")
            or os.getenv("POSTGRESQL_URL")
        )
        if database_url:
            payload["DATABASE_URL"] = database_url

        return payload

    @property
    def redis_url_safe(self) -> str:
        try:
            parsed = urlsplit(self.REDIS_URL)
            host = parsed.hostname or "unknown"
            port = parsed.port or ("6379" if parsed.scheme.startswith("redis") else "")
            return f"{parsed.scheme}://{host}{f':{port}' if port else ''}"
        except Exception:
            return "<unparsed>"

    @model_validator(mode="after")
    def _validate_security_defaults(self):
        is_prod_like = self.ENVIRONMENT.lower() not in {"dev", "development", "local", "test"}
        if len(self.SECRET_KEY or "") < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long.")
        if is_prod_like and self.SECRET_KEY == "dev-secret-key-change-in-production-min-32-chars":
            raise ValueError("Refusing to start with the default SECRET_KEY in production-like environments.")
        if self.MAX_REQUEST_SIZE_BYTES < 1024 * 1024:
            raise ValueError("MAX_REQUEST_SIZE_BYTES must be at least 1 MB.")
        return self


settings = Settings()
