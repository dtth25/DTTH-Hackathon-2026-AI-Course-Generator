# Vector database package (FAISS)
"""
Vector database abstraction layer.
Currently using FAISS (local, disk-based) for grounded generation.
"""

from backend.vector_db.faiss_manager import (
    create_or_load_faiss,
    load_existing_faiss,
    list_faiss_courses,
    get_index_stats,
    _drop_index,
)

__all__ = [
    "create_or_load_faiss",
    "load_existing_faiss",
    "list_faiss_courses",
    "get_index_stats",
    "_drop_index",
]
