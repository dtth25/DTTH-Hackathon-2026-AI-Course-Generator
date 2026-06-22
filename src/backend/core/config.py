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

load_dotenv("api_key.env")

# ─── Directory Constants ───────────────────────────────────────────────────────

UPLOAD_DIR = "uploads"
INDEX_DIR = "faiss_indices"
QUESTIONS_DIR = "questions"
CACHE_DIR = "cache"
AUDIO_DIR = "audio"
GUIDES_DIR = "guides"
FLASHCARDS_DIR = "flashcards"
MINDMAPS_DIR = "mindmaps"

for d in [UPLOAD_DIR, INDEX_DIR, QUESTIONS_DIR, CACHE_DIR, AUDIO_DIR, GUIDES_DIR, FLASHCARDS_DIR, MINDMAPS_DIR]:
    os.makedirs(d, exist_ok=True)

# ─── Model Configuration ───────────────────────────────────────────────────────

DEFAULT_MAX_CACHED_COURSES = 20
BATCH_SIZE = 30         # Chunks per batch for embedding
RETRY_DELAY = 10        # Seconds between batches
MAX_RETRY_DELAY = 60    # Max delay on 429 errors
EMBEDDING_MODEL = "gemini-embedding-2"
LLM_MODEL = "gemini-2.5-flash"

# ─── Path Helpers ──────────────────────────────────────────────────────────────

def generate_course_id() -> str:
    """Generate a short unique course ID."""
    return uuid.uuid4().hex[:12]


def get_course_path(course_id: str) -> Dict[str, str]:
    """Get all file paths for a course."""
    return {
        "faiss": os.path.join(INDEX_DIR, f"course_{course_id}"),
        "questions": os.path.join(QUESTIONS_DIR, f"course_{course_id}_questions.json"),
        "syllabus": os.path.join(QUESTIONS_DIR, f"course_{course_id}_syllabus.json"),
        "meta": os.path.join(QUESTIONS_DIR, f"course_{course_id}_meta.json"),
        "audio": os.path.join(AUDIO_DIR, f"course_{course_id}"),
        "guides": os.path.join(GUIDES_DIR, f"course_{course_id}"),
        "flashcards": os.path.join(FLASHCARDS_DIR, f"course_{course_id}_flashcards.json"),
        "mindmaps": os.path.join(MINDMAPS_DIR, f"course_{course_id}"),
    }


# ─── Embedding / LLM Factory ──────────────────────────────────────────────────

def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Get Gemini embeddings instance."""
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)


def get_llm(temperature: float = 0.1, max_output_tokens: int = 8192) -> ChatGoogleGenerativeAI:
    """Get Gemini LLM instance."""
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


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