from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Central config so debugging does not require searching many files."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # If true, upload still succeeds with a local demo course when Gemini fails.
    # This is useful for hackathon demos and for debugging PDF/frontend flow.
    demo_mode: bool = False
    auto_demo_on_ai_error: bool = True

    max_upload_mb: int = 50
    max_context_chars: int = 45000
    min_text_chars: int = 200
    enable_ocr: bool = False
    tesseract_cmd: str = ""
    ocr_lang: str = "vie+eng"

    uploads_dir: Path = PROJECT_DIR / "uploads"
    courses_dir: Path = PROJECT_DIR / "data" / "courses"
    frontend_dir: Path = PROJECT_DIR / "frontend"

    @property
    def has_google_api_key(self) -> bool:
        return bool(self.google_api_key.strip()) and "your_gemini_api_key_here" not in self.google_api_key

    @property
    def api_key_looks_like_google_key(self) -> bool:
        # Most Google API keys begin with AIza. This is only a warning signal,
        # not a hard security check.
        return self.google_api_key.strip().startswith("AIza")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.courses_dir.mkdir(parents=True, exist_ok=True)
    return settings
