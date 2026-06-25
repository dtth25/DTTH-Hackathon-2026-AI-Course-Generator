"""
FAISS vector store manager.
Local, disk-based, no Docker required.
"""
import os
import json
import time
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from backend.core.config import (
    get_embeddings,
    INDEX_DIR,
    BATCH_SIZE,
    RETRY_DELAY,
    MAX_RETRY_DELAY,
    logger,
)

from backend.services.doc_processor import get_text_from_any_file


def _index_path(course_id: str) -> str:
    """Path to FAISS index folder for a course."""
    return os.path.join(INDEX_DIR, f"faiss_{course_id}")


def _drop_index(course_id: str):
    """Remove FAISS index for a course."""
    path = _index_path(course_id)
    if os.path.exists(path):
        import shutil
        shutil.rmtree(path)
        logger.info(f"[FAISS] Dropped index '{path}'")


def _coerce_source_paths(source_paths: str | Sequence[str]) -> list[str]:
    """Normalize one or many upload paths into a non-empty list."""
    if isinstance(source_paths, str):
        paths = [source_paths]
    else:
        paths = [str(path) for path in source_paths]
    return [path for path in paths if path]


def create_or_load_faiss(
    course_id: str,
    source_paths: str | Sequence[str],
) -> FAISS:
    """
    Create a new FAISS vector store from a document, or load an existing one.

    Args:
        course_id: Unique course identifier.
        source_paths: Path or paths to PDF/DOCX/TXT files.

    Returns:
        FAISS vector store instance.
    """
    index_path = _index_path(course_id)

    # Load existing index if available
    if os.path.exists(index_path) and os.path.exists(os.path.join(index_path, "index.faiss")):
        logger.info(f"[Course {course_id}] Found existing FAISS index, loading...")
        return FAISS.load_local(
            index_path,
            get_embeddings(),
            allow_dangerous_deserialization=True,
        )

    paths = _coerce_source_paths(source_paths)
    if not paths:
        raise ValueError("No upload files were provided.")

    logger.info("[Course %s] Building new FAISS index from %s file(s)...", course_id, len(paths))

    valid_docs: list[Document] = []
    for doc_index, path in enumerate(paths):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        file_docs = get_text_from_any_file(path)
        filename = os.path.basename(path)
        for doc in file_docs:
            doc.metadata["doc_id"] = doc_index
            doc.metadata["source_file"] = filename
            doc.metadata["course_id"] = course_id
        valid_docs.extend(file_docs)

    if not valid_docs:
        raise ValueError("File contains no valid text content.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200, chunk_overlap=200
    )
    splits = text_splitter.split_documents(valid_docs)
    num_chunks = len(splits)
    logger.info(f"[Course {course_id}] Split into {num_chunks} chunks.")

    # Add internal source metadata for retrieval and debugging.
    for idx, doc in enumerate(splits):
        doc.metadata["chunk_id"] = idx
        doc.metadata["course_id"] = course_id
        doc.metadata.setdefault("source_file", os.path.basename(paths[0]))
        if "page" not in doc.metadata:
            doc.metadata["page"] = idx // 5 + 1  # Approximate page mapping

    logger.info(f"[Course {course_id}] Creating embeddings and indexing into FAISS...")

    # Build with rate-limit handling (Gemini free tier limits)
    embeddings = get_embeddings()
    try:
        vectorstore = FAISS.from_documents(
            documents=splits[:BATCH_SIZE],
            embedding=embeddings,
        )
    except Exception as e:
        if "429" in str(e) or "ResourceExhausted" in str(e):
            logger.warning(" -> Rate limited. Waiting 60s...")
            time.sleep(MAX_RETRY_DELAY)
            vectorstore = FAISS.from_documents(
                documents=splits[:BATCH_SIZE],
                embedding=embeddings,
            )
        else:
            raise e

    # Add remaining batches
    for i in range(BATCH_SIZE, num_chunks, BATCH_SIZE):
        time.sleep(RETRY_DELAY)
        batch = splits[i:i + BATCH_SIZE]
        end_idx = min(i + BATCH_SIZE, num_chunks)
        logger.info(f" -> Chunks {i} to {end_idx}...")
        try:
            vectorstore.add_documents(batch)
        except Exception as e:
            if "429" in str(e) or "ResourceExhausted" in str(e):
                logger.warning(" -> Rate limited. Waiting 60s...")
                time.sleep(MAX_RETRY_DELAY)
                vectorstore.add_documents(batch)
            else:
                raise e

    # Persist to disk
    os.makedirs(index_path, exist_ok=True)
    vectorstore.save_local(index_path)

    # Save metadata
    meta_path = os.path.join(INDEX_DIR, f"faiss_{course_id}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "course_id": course_id,
            "index_path": index_path,
            "num_chunks": num_chunks,
            "num_documents": len(paths),
            "source_files": [os.path.basename(path) for path in paths],
            "created_at": time.time(),
        }, f, indent=2)

    logger.info(f"[Course {course_id}] FAISS index saved to '{index_path}'.")
    return vectorstore


def load_existing_faiss(course_id: str) -> Optional[FAISS]:
    """Load existing FAISS index for a course if it exists."""
    index_path = _index_path(course_id)
    try:
        if not os.path.exists(os.path.join(index_path, "index.faiss")):
            logger.warning(f"[Restore] FAISS index for '{course_id}' not found.")
            return None
        vs = FAISS.load_local(
            index_path,
            get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        logger.info(f"[Restore] Loaded FAISS index for '{course_id}'.")
        return vs
    except Exception as e:
        logger.error(f"[Restore] Failed to load FAISS index: {e}")
        return None


def list_faiss_courses() -> List[str]:
    """List all course IDs that have FAISS indices."""
    courses = []
    if not os.path.exists(INDEX_DIR):
        return courses
    for fname in os.listdir(INDEX_DIR):
        if fname.startswith("faiss_") and fname.endswith(".json"):
            course_id = fname[len("faiss_"):-len(".json")]
            courses.append(course_id)
    return sorted(courses)


def get_index_stats(course_id: str) -> Dict[str, Any]:
    """Get statistics about a FAISS index."""
    index_path = _index_path(course_id)
    meta_path = os.path.join(INDEX_DIR, f"faiss_{course_id}.json")
    if not os.path.exists(os.path.join(index_path, "index.faiss")):
        return {"exists": False}
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    return {
        "exists": True,
        "index_path": index_path,
        "num_chunks": meta.get("num_chunks"),
        "created_at": meta.get("created_at"),
    }
