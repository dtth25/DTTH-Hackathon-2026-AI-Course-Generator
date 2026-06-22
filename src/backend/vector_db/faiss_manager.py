"""
FAISS vector store manager.
Sử dụng FAISS hiện tại, sau này có thể chuyển sang Milvus.
"""
import os
import time
import logging
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.vectorstores import VectorStoreRetriever

from backend.core.config import (
    get_embeddings,
    INDEX_DIR,
    BATCH_SIZE,
    RETRY_DELAY,
    MAX_RETRY_DELAY,
    logger,
)

from backend.services.doc_processor import get_text_from_any_file


def create_or_load_faiss(
    faiss_path: str,
    pdf_path: str,
    course_id: str,
) -> FAISS:
    """
    Create a new FAISS index from a PDF, or load an existing one.
    """
    embeddings = get_embeddings()

    if os.path.exists(faiss_path):
        logger.info(f"[Course {course_id}] Found existing FAISS index, loading...")
        return FAISS.load_local(
            faiss_path, embeddings, allow_dangerous_deserialization=True
        )

    logger.info(f"[Course {course_id}] Building new vectorstore from PDF...")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    valid_docs = get_text_from_any_file(pdf_path)
    if not valid_docs:
        raise ValueError("PDF contains no valid text content.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200, chunk_overlap=200
    )
    splits = text_splitter.split_documents(valid_docs)
    num_chunks = len(splits)
    logger.info(f"[Course {course_id}] Split into {num_chunks} chunks.")
    logger.info(f"[Course {course_id}] Creating embeddings in batches...")

    # Build vectorstore with rate limit handling
    vectorstore = FAISS.from_documents(
        documents=splits[:BATCH_SIZE], embedding=embeddings
    )
    for i in range(BATCH_SIZE, num_chunks, BATCH_SIZE):
        time.sleep(RETRY_DELAY)
        batch = splits[i:i + BATCH_SIZE]
        end_idx = min(i + BATCH_SIZE, num_chunks)
        logger.info(f" -> Chunks {i} to {end_idx}...")
        try:
            vectorstore.add_documents(batch)
        except Exception as e:
            if "429" in str(e):
                logger.warning(" -> Rate limited. Waiting 60s...")
                time.sleep(MAX_RETRY_DELAY)
                vectorstore.add_documents(batch)
            else:
                raise e

    vectorstore.save_local(faiss_path)
    logger.info(f"[Course {course_id}] FAISS index saved successfully.")
    return vectorstore


def load_existing_faiss(faiss_path: str) -> Optional[FAISS]:
    """Load existing FAISS index from disk if it exists."""
    if not os.path.exists(faiss_path):
        return None
    try:
        embeddings = get_embeddings()
        vs = FAISS.load_local(
            faiss_path, embeddings, allow_dangerous_deserialization=True
        )
        logger.info(f"[Restore] Loaded FAISS from {faiss_path}.")
        return vs
    except Exception as e:
        logger.error(f"[Restore] Failed to load FAISS: {e}")
        return None