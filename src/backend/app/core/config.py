"""Application settings and configuration loaded from environment variables."""

import logging
import sys
from pathlib import Path
from typing import List, Literal, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

logger = logging.getLogger("api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Single source of truth: the .env at the project root, regardless of the process cwd.
# (config.py -> core -> app -> backend -> src -> project root)
_ROOT_ENV_FILE = str(Path(__file__).resolve().parents[4] / ".env")
_DEFAULT_JWT_SECRET = "CHANGE_THIS_DEV_SECRET"


class Settings(BaseSettings):
    """Core application settings with strict startup validation."""

    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Required variables per specifications
    DATABASE_URL: str = Field(
        ..., description="Database connection URL (e.g. sqlite:///./app.db)"
    )
    JWT_SECRET: str = Field(
        ..., description="Secret key for JWT encoding and decoding"
    )
    OPENROUTER_API_KEY: str = Field(..., description="OpenRouter API key")
    OPENROUTER_MODEL: str = Field(
        default="google/gemini-2.5-pro",
        description="Default paid OpenRouter model — used directly by Book/Vid, and as the fallback for any feature without its own override",
    )

    # Per-feature model overrides — mirrors the old GEMINI_{FEATURE}_MODEL pattern. Blank
    # falls back to OPENROUTER_MODEL; every default is Gemini 2.5 Pro for consistent
    # generation quality across Book, Slide, Quiz, Vid, and OCR.
    OPENROUTER_BOOK_MODEL: str = Field(default="", description="OpenRouter model override for Book generation (falls back to OPENROUTER_MODEL)")
    OPENROUTER_SLIDE_MODEL: str = Field(default="google/gemini-2.5-pro", description="OpenRouter model override for Slide generation (falls back to OPENROUTER_MODEL)")
    OPENROUTER_QUIZ_MODEL: str = Field(default="google/gemini-2.5-pro", description="OpenRouter model override for Quiz generation (falls back to OPENROUTER_MODEL)")
    OPENROUTER_VID_MODEL: str = Field(default="", description="OpenRouter model override for Vid generation (falls back to OPENROUTER_MODEL)")

    # Optional variables
    ALLOWED_ORIGINS: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="CORS allowed origins",
    )
    UPLOAD_DIR: str = Field(
        default="uploads", description="Directory for storing uploaded files"
    )
    OUTPUT_DIR: str = Field(
        default="outputs", description="Directory for storing generated outputs"
    )
    JWT_EXPIRE_MINUTES: int = Field(
        default=10080,
        description="JWT expiration time in minutes (default 7 days)",
    )
    AUTH_COOKIE_NAME: str = Field(
        default="agy_session", description="Name of the HttpOnly auth cookie"
    )
    AUTH_COOKIE_SECURE: bool = Field(
        default=False, description="Whether auth cookie requires HTTPS"
    )

    # Email verification / password reset — sent via SMTP (Gmail: smtp.gmail.com + an
    # App Password, not the account password). Left blank by default so a fresh checkout
    # without SMTP set up still boots; attempting to
    # actually send an email with these unset fails loudly at call time instead of
    # crashing the whole app over a feature not yet configured.
    SMTP_HOST: str = Field(default="smtp.gmail.com", description="SMTP server host for transactional email")
    SMTP_PORT: int = Field(default=587, description="SMTP server port (587 = STARTTLS)")
    SMTP_USER: str = Field(default="", description="SMTP login username, e.g. a Gmail address")
    SMTP_PASSWORD: str = Field(
        default="", description="SMTP login password — for Gmail this must be an App Password, not the account password"
    )
    EMAIL_FROM_ADDRESS: str = Field(
        default="",
        description=(
            "Sender shown to recipients, e.g. 'HackaGen <account@gmail.com>'. Falls back "
            "to SMTP_USER when blank. The email portion should match SMTP_USER — Gmail "
            "rejects/rewrites a From address that isn't the authenticated account (or one "
            "of its verified Send-As aliases)."
        ),
    )
    EMAIL_DEV_FALLBACK: bool = Field(
        default=False,
        description=(
            "When true AND SMTP_USER/SMTP_PASSWORD is unset, log OTP codes to the server "
            "console instead of failing — local/dev testing convenience only. Never enable "
            "in production: it lets register/reset-password 'succeed' with nobody actually "
            "receiving the code."
        ),
    )
    EMAIL_OTP_EXPIRE_MINUTES: int = Field(default=10, description="OTP code validity window")
    EMAIL_OTP_MAX_ATTEMPTS: int = Field(default=5, description="Max wrong-code guesses before an OTP is locked")
    EMAIL_OTP_RESEND_COOLDOWN_SECONDS: int = Field(
        default=60, description="Minimum seconds between two OTP sends for the same purpose"
    )

    # Default admin bootstrap — idempotent, runs once at startup if enabled.
    CREATE_DEFAULT_ADMIN: bool = Field(default=False, description="Seed a default admin user at startup")
    ADMIN_EMAIL: str = Field(default="", description="Email for the seeded default admin")
    ADMIN_PASSWORD: str = Field(default="", description="Password for the seeded default admin")
    CHROMA_PERSIST_DIR: str = Field(
        default="data/chroma", description="ChromaDB persistent directory"
    )
    CHROMA_COLLECTION_NAME: str = Field(
        default="ai_course_chunks", description="ChromaDB collection name"
    )
    CHROMA_MODE: str = Field(default="embedded", pattern="^(embedded|http)$")
    CHROMA_HOST: str = Field(default="localhost")
    CHROMA_PORT: int = Field(default=8000, ge=1, le=65535)
    CHROMA_SSL: bool = Field(default=False)
    CHROMA_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1.0, le=60.0)

    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, description="Chunks per embed_content batch call")
    EMBEDDING_BATCH_DELAY: float = Field(default=0, description="Seconds to sleep between embedding batches")
    EMBEDDING_MAX_RETRIES: int = Field(default=3, description="Max retries per embedding batch on failure")
    EMBEDDING_MAX_RETRY_DELAY: float = Field(default=60, description="Max backoff delay (seconds) between embedding retries")
    EMBEDDING_REQUESTS_PER_MINUTE: int = Field(default=72, description="Client-side rate limit for embedding API calls")
    EMBEDDING_CACHE_DIR: str = Field(default="cache/chunk_embeddings", description="Directory for content-hash embedding cache")
    EMBEDDING_DIMENSIONS: int = Field(default=1536, ge=1, description="Requested OpenRouter embedding dimensions")
    EMBEDDING_NORMALIZATION_VERSION: str = Field(default="exact-v1", min_length=1, description="Stable embedding input normalization identity")

    OPENROUTER_EMBEDDING_MODEL: str = Field(default="openai/text-embedding-3-small", description="OpenRouter embedding model slug")
    OPENROUTER_MAX_IN_FLIGHT: int = Field(default=6, ge=1, le=32)
    OPENROUTER_RPM: int = Field(default=60, ge=1, le=1000)
    OPENROUTER_CIRCUIT_FAILURES: int = Field(default=5, ge=2, le=20)
    OPENROUTER_CIRCUIT_WINDOW_SECONDS: int = Field(default=60, ge=10, le=300)
    OPENROUTER_CIRCUIT_OPEN_SECONDS: int = Field(default=30, ge=5, le=300)
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
    OPENROUTER_PREFLIGHT_TTL_SECONDS: int = Field(default=30, ge=5, le=300)
    OPENROUTER_PREFLIGHT_TIMEOUT_SECONDS: float = Field(default=5.0, ge=1.0, le=20.0)
    OPENROUTER_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1.0, le=60.0)
    OPENROUTER_READ_TIMEOUT_SECONDS: float = Field(default=180.0, ge=10.0, le=600.0)
    OPENROUTER_ATTEMPT_TIMEOUT_SECONDS: float = Field(default=180.0, ge=10.0, le=600.0)
    PROVIDER_CAPACITY_WAIT_MIN_SECONDS: int = Field(default=1, ge=1, le=10)
    PROVIDER_CAPACITY_WAIT_MAX_SECONDS: int = Field(default=3, ge=1, le=30)
    PROVIDER_CAPACITY_WAITER_TTL_SECONDS: int = Field(default=15, ge=5, le=120)
    BOOK_CHAPTER_CONCURRENCY: int = Field(default=2, ge=1, le=4)
    ENVIRONMENT: str = Field(
        default="local", pattern="^(local|test|loadtest|production)$"
    )
    JOB_QUEUE_PROVIDER: str = Field(default="inline", pattern="^(inline|celery)$")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    DB_POOL_SIZE: int = Field(default=10, ge=2, le=50)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=120)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=300, le=7200)
    MAX_PENDING_JOBS_PER_USER: int = Field(default=4, ge=1, le=20)
    MAX_PENDING_JOBS_GLOBAL: int = Field(default=200, ge=10, le=2000)
    JOB_LEASE_SECONDS: int = Field(default=3600, ge=60, le=7200)
    # Inline BackgroundTasks have no cross-process lease. Recovery is opt-in only for
    # an operator-controlled, single-process local deployment; it is not multi-process safe.
    PROCESSING_EXECUTION_MODE: Literal["inline", "distributed"] = Field(default="inline")
    INLINE_PROCESSING_RECOVERY_ENABLED: bool = Field(default=False)

    # Document chunking tuning
    DOCUMENT_CHUNK_SIZE: int = Field(default=1800, description="Target chunk size in characters")
    DOCUMENT_CHUNK_OVERLAP: int = Field(default=120, description="Overlap in characters between consecutive chunks")

    # OCR fallback for scanned PDF pages (rendered page image -> OpenRouter vision text extraction)
    PDF_ENABLE_OCR: bool = Field(default=True, description="Enable OCR fallback for low-text (scanned) PDF pages")
    PDF_OCR_MAX_PAGES: int = Field(default=12, description="Hard cap on number of pages OCR'd per document")
    PDF_OCR_DPI: int = Field(default=120, description="DPI used when rendering a scanned page to an image for OCR")
    PDF_TEXT_MIN_CHARS_PER_PAGE: int = Field(default=50, description="Below this many extracted chars, a page is considered a scan candidate")
    PDF_SCAN_SAMPLE_PAGES: int = Field(default=12, description="Number of pages sampled to decide whether a document is scanned")


    @field_validator("DATABASE_URL", "JWT_SECRET", "OPENROUTER_API_KEY", mode="before")
    @classmethod
    def validate_required_not_empty(cls, value: str, info) -> str:
        if value is None or not str(value).strip():
            raise ValueError(
                f"Required environment variable '{info.field_name}' cannot be missing or empty!"
            )
        return str(value).strip()

    @staticmethod
    def _is_free_model_slug(model: str) -> bool:
        normalized = model.casefold()
        return normalized.endswith(":free") or normalized.split("/")[-1] == "free"

    @field_validator("OPENROUTER_MODEL", mode="before")
    @classmethod
    def validate_paid_openrouter_model(cls, value: str) -> str:
        model = str(value or "").strip()
        if not model:
            raise ValueError("OPENROUTER_MODEL cannot be missing or empty")
        if cls._is_free_model_slug(model):
            raise ValueError("OPENROUTER_MODEL must reference a paid model")
        return model

    @field_validator("OPENROUTER_EMBEDDING_MODEL", "EMBEDDING_NORMALIZATION_VERSION", mode="before")
    @classmethod
    def validate_embedding_identity(cls, value: str, info) -> str:
        identity = str(value or "").strip()
        if not identity:
            raise ValueError(f"{info.field_name} cannot be missing or empty")
        if info.field_name == "OPENROUTER_EMBEDDING_MODEL" and cls._is_free_model_slug(identity):
            raise ValueError("OPENROUTER_EMBEDDING_MODEL must reference a paid model")
        return identity

    @field_validator(
        "OPENROUTER_BOOK_MODEL", "OPENROUTER_SLIDE_MODEL", "OPENROUTER_QUIZ_MODEL", "OPENROUTER_VID_MODEL",
        mode="before",
    )
    @classmethod
    def validate_paid_feature_model_override(cls, value: str, info) -> str:
        model = str(value or "").strip()
        if not model:
            return ""  # blank = no override, falls back to OPENROUTER_MODEL
        if cls._is_free_model_slug(model):
            raise ValueError(f"{info.field_name} must reference a paid model")
        return model

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Union[List[str], str]) -> List[str]:
        if isinstance(value, str):
            import json

            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed]
            except Exception:
                return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_admin_bootstrap(self) -> "Settings":
        if self.CREATE_DEFAULT_ADMIN and (not self.ADMIN_EMAIL.strip() or not self.ADMIN_PASSWORD.strip()):
            raise ValueError(
                "CREATE_DEFAULT_ADMIN=true requires ADMIN_EMAIL and ADMIN_PASSWORD to also be set"
            )
        return self

    @model_validator(mode="after")
    def validate_provider_capacity_wait_window(self) -> "Settings":
        if self.PROVIDER_CAPACITY_WAIT_MIN_SECONDS > self.PROVIDER_CAPACITY_WAIT_MAX_SECONDS:
            raise ValueError(
                "PROVIDER_CAPACITY_WAIT_MIN_SECONDS cannot exceed PROVIDER_CAPACITY_WAIT_MAX_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def validate_production_queue_provider(self) -> "Settings":
        if self.ENVIRONMENT == "production" and self.JOB_QUEUE_PROVIDER != "celery":
            raise ValueError(
                "ENVIRONMENT=production requires JOB_QUEUE_PROVIDER=celery"
            )
        return self

    @model_validator(mode="after")
    def validate_deployment_auth_and_email_safety(self) -> "Settings":
        if self.ENVIRONMENT not in {"production", "loadtest"}:
            return self
        if self.JWT_SECRET == _DEFAULT_JWT_SECRET:
            raise ValueError(
                f"ENVIRONMENT={self.ENVIRONMENT} requires JWT_SECRET to be changed"
            )
        if self.EMAIL_DEV_FALLBACK:
            raise ValueError(
                f"ENVIRONMENT={self.ENVIRONMENT} requires EMAIL_DEV_FALLBACK=false"
            )
        return self

    @model_validator(mode="after")
    def validate_openrouter_base_url(self) -> "Settings":
        official_url = "https://openrouter.ai/api/v1"
        self.OPENROUTER_BASE_URL = self.OPENROUTER_BASE_URL.rstrip("/")
        if self.ENVIRONMENT != "loadtest" and self.OPENROUTER_BASE_URL != official_url:
            raise ValueError(
                "A non-official OPENROUTER_BASE_URL is allowed only in loadtest"
            )
        return self

    @model_validator(mode="after")
    def validate_production_database(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            try:
                database_driver = make_url(self.DATABASE_URL).drivername
            except ArgumentError as exc:
                raise ValueError(
                    "ENVIRONMENT=production requires a valid PostgreSQL DATABASE_URL "
                    "using postgresql+psycopg://"
                ) from exc
            if database_driver != "postgresql+psycopg":
                raise ValueError(
                    "ENVIRONMENT=production requires a PostgreSQL DATABASE_URL "
                    "using postgresql+psycopg://"
                )
        return self


try:
    settings = Settings()
    logger.info(
        "Configuration loaded successfully (content_model=%s, embedding_model=%s).",
        settings.OPENROUTER_MODEL,
        settings.OPENROUTER_EMBEDDING_MODEL,
    )
except Exception as e:
    logger.critical(
        "FATAL: Configuration validation failed at startup! Missing or invalid required environment variables."
    )
    logger.critical("Error details: %s", e)
    # Crash on missing required vars per acceptance criteria
    sys.exit(1)
