from __future__ import annotations

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

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_HOURS: int = 8

    # Database — Railway provides postgresql://, we need postgresql+asyncpg:// for async SQLAlchemy
    DATABASE_URL: str = "postgresql+asyncpg://pms_user:pms_password_dev@localhost:5432/pms_extraction"

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
    ANTHROPIC_API_KEY: str = ""

    # Azure Document Intelligence
    AZURE_DOC_INTELLIGENCE_KEY: str = ""
    AZURE_DOC_INTELLIGENCE_ENDPOINT: str = ""


settings = Settings()
