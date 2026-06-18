import json
import re
import unicodedata
from pathlib import Path


def safe_filename(name: str, fallback: str = "document") -> str:
    stem = Path(name).stem if name else fallback
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", ascii_name).strip("._-")
    return ascii_name or fallback


def extract_json_object(text: str) -> dict:
    """Fallback parser when an LLM still wraps JSON with prose or markdown."""
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Không tìm thấy JSON object trong phản hồi AI.")
    return json.loads(match.group(1))
