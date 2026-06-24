"""
Core configuration, paths, and utility functions.
"""
import os
import re
import json
import uuid
import hashlib
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import OrderedDict

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).resolve()
_BACKEND_DIR = _CONFIG_FILE.parents[1]
_SRC_DIR = _CONFIG_FILE.parents[2]
_ROOT_DIR = _CONFIG_FILE.parents[3]
_ENV_CANDIDATES = [
    Path.cwd() / ".env",
    Path.cwd() / "api_key.env",
    _BACKEND_DIR / ".env",
    _BACKEND_DIR / "api_key.env",
    _SRC_DIR / ".env",
    _SRC_DIR / "api_key.env",
    _ROOT_DIR / ".env",
    _ROOT_DIR / "api_key.env",
]

for env_path in _ENV_CANDIDATES:
    if env_path.exists():
        load_dotenv(env_path, override=False)

_GOOGLE_API_KEY = (
    os.getenv("GOOGLE_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("LLM_API_KEY")
)

if _GOOGLE_API_KEY and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = _GOOGLE_API_KEY

# ─── Directory Constants ───────────────────────────────────────────────────────

UPLOAD_DIR = "uploads"
INDEX_DIR = "indices"
QUESTIONS_DIR = "questions"
CACHE_DIR = "cache"
BOOKS_DIR = "books"
SLIDES_DIR = "slides"
VIDEOS_DIR = "videos"

for d in [UPLOAD_DIR, INDEX_DIR, QUESTIONS_DIR, CACHE_DIR, BOOKS_DIR, SLIDES_DIR, VIDEOS_DIR]:
    os.makedirs(d, exist_ok=True)

# ─── Vector DB Configuration ───────────────────────────────────────────────────
# Vector DB: FAISS (disk-based, no Docker).

# ─── Model Configuration ───────────────────────────────────────────────────────

DEFAULT_MAX_CACHED_COURSES = 20
BATCH_SIZE = 30         # Chunks per batch for embedding
RETRY_DELAY = 10        # Seconds between batches
MAX_RETRY_DELAY = 60    # Max delay on 429 errors


def _normalize_embedding_model(model_name: Optional[str]) -> str:
    """Normalize Gemini embedding model names for LangChain batch embeddings."""
    model = (model_name or "models/embedding-001").strip()
    if model in {"gemini-embedding-2", "models/gemini-embedding-2"}:
        logger.warning(
            "EMBEDDING_MODEL=%s is not compatible with current LangChain batch "
            "embedding flow. Falling back to models/embedding-001.",
            model,
        )
        return "models/embedding-001"
    if not model.startswith("models/"):
        model = f"models/{model}"
    return model


EMBEDDING_MODEL = _normalize_embedding_model(os.getenv("EMBEDDING_MODEL"))
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")

# ─── Path Helpers ──────────────────────────────────────────────────────────────

def generate_course_id() -> str:
    """Generate a short unique course ID."""
    return uuid.uuid4().hex[:12]


def get_course_path(course_id: str) -> Dict[str, str]:
    """Get all file paths for a course."""
    return {
        "faiss_meta": os.path.join(INDEX_DIR, f"faiss_{course_id}.json"),
        "questions": os.path.join(QUESTIONS_DIR, f"course_{course_id}_questions.json"),
        "meta": os.path.join(QUESTIONS_DIR, f"course_{course_id}_meta.json"),
        "book": os.path.join(BOOKS_DIR, f"course_{course_id}_book.json"),
        "book_pdf": os.path.join(BOOKS_DIR, f"course_{course_id}_book.pdf"),
        "slides": os.path.join(SLIDES_DIR, f"course_{course_id}_slides.json"),
        "videos": os.path.join(VIDEOS_DIR, f"course_{course_id}"),
    }


# ─── Embedding / LLM Factory ──────────────────────────────────────────────────

def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Get Gemini embeddings instance."""
    api_key = _require_google_api_key()
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key)


def get_llm(temperature: float = 0.1, max_output_tokens: int = 8192) -> ChatGoogleGenerativeAI:
    """Get Gemini LLM instance."""
    api_key = _require_google_api_key()
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _require_google_api_key() -> str:
    """Return configured Gemini API key or raise an actionable error."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing Gemini API key. Set GOOGLE_API_KEY in your shell or in one of: "
            ".env, api_key.env, src/api_key.env, src/backend/.env. "
            "Legacy aliases GEMINI_API_KEY and LLM_API_KEY are also accepted."
        )
    return api_key


# ─── Utility Functions ─────────────────────────────────────────────────────────

def format_docs(docs: List[Document]) -> str:
    """Format documents for prompt context."""
    return "\n\n".join(doc.page_content for doc in docs)


def extract_json(text: Any) -> str:
    """Extract JSON array/object from LLM text output."""
    text_str = str(text)
    # Remove markdown code fences
    text_str = re.sub(r'```json|```', '', text_str, flags=re.IGNORECASE).strip()
    # Grab the first outermost [...] or {...} block
    match = re.search(r"(\[.*\]|\{.*\})", text_str, re.DOTALL)
    if match:
        return match.group(1).strip()
    return "[]"


def sanitize_filename(name: str) -> str:
    """Convert string to safe filename."""
    import unidecode
    name = unidecode.unidecode(name)
    name = re.sub(r'\s+', '_', name.lower().strip())
    name = re.sub(r'[^\w\s\-]', '', name)
    return name if name else "general_topic"


def get_cache_key(content: str) -> str:
    """Generate MD5 cache key from content."""
    return hashlib.md5(content.encode()).hexdigest()


def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent injection attacks."""
    if not isinstance(text, str):
        return str(text)
    text = "".join(ch for ch in text if ch.isprintable() or ch == "\n")
    text = text.strip()
    return text


def _timestamp() -> str:
    """Get formatted timestamp for logging."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
