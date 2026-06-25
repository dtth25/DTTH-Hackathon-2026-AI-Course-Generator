"""Course lifecycle and vectorstore management for the four-output generator."""

import gc
import json
import os
import shutil
import threading
import time
from collections import OrderedDict
from typing import Optional, Sequence

from langchain_community.vectorstores import FAISS

from backend.core.config import DEFAULT_MAX_CACHED_COURSES, generate_course_id, get_course_path, logger
from backend.vector_db.faiss_manager import _drop_index, create_or_load_faiss, list_faiss_courses, load_existing_faiss


def _coerce_source_paths(source_paths: str | Sequence[str]) -> list[str]:
    """Normalize one or many upload paths."""
    if isinstance(source_paths, str):
        paths = [source_paths]
    else:
        paths = [str(path) for path in source_paths]
    return [path for path in paths if path]


class RAGChains:
    """Per-course container for the vectorstore used by Book, Slide, Quiz, and Vid."""

    def __init__(self, course_id: str, source_path: str | Sequence[str]):
        self.course_id = course_id
        self.source_paths = _coerce_source_paths(source_path)
        self.source_path = self.source_paths[0] if self.source_paths else ""
        self.vectorstore: Optional[FAISS] = None
        self.index_meta_path = get_course_path(course_id)["faiss_meta"]

    def get_resource_generator(self):
        """Create a ResourceGenerator for this course."""
        from backend.services.resource_gen import ResourceGenerator

        return ResourceGenerator(self)

    def initialise_chains_only(self) -> "RAGChains":
        """Validate that the vectorstore is loaded."""
        if self.vectorstore is None:
            raise ValueError("vectorstore must be set before initialising a course.")
        return self

    def initialise(self) -> "RAGChains":
        """Create or load the course vectorstore."""
        self.vectorstore = create_or_load_faiss(self.course_id, self.source_paths or self.source_path)
        return self.initialise_chains_only()

    def _load_existing_vectorstore(self) -> Optional[FAISS]:
        """Load an existing FAISS index from disk."""
        return load_existing_faiss(self.course_id)


class CourseManager:
    """Multi-course manager with lazy loading and LRU eviction."""

    def __init__(self, max_cached: int = DEFAULT_MAX_CACHED_COURSES):
        self._courses: dict[str, RAGChains] = {}
        self._lock = threading.Lock()
        self._max_cached = max_cached
        self._all_course_ids: set[str] = set()
        self._lru: OrderedDict[str, None] = OrderedDict()
        self._scan_existing_courses()

    def _scan_existing_courses(self) -> None:
        """Register course IDs that already have FAISS metadata on disk."""
        try:
            found = 0
            for course_id in list_faiss_courses():
                self._all_course_ids.add(course_id)
                found += 1

            if found:
                logger.info(
                    "[LazyLoad] Registered %s courses from FAISS indices. Max cache: %s.",
                    found,
                    self._max_cached,
                )
        except Exception as exc:
            logger.warning("[LazyLoad] Could not scan FAISS indices: %s", exc)

    def _evict_lru_course(self) -> None:
        """Evict the least recently used course from memory."""
        if not self._lru:
            return

        evict_id = next(iter(self._lru))
        del self._lru[evict_id]
        self._courses.pop(evict_id, None)
        logger.info("[LRU] Evicted course '%s' from cache.", evict_id)
        gc.collect()

    def _ensure_course_loaded(self, course_id: str) -> Optional[RAGChains]:
        """Lazy-load a course into memory if it is registered."""
        with self._lock:
            if course_id in self._courses:
                if course_id in self._lru:
                    self._lru.move_to_end(course_id, last=True)
                else:
                    self._lru[course_id] = None
                return self._courses[course_id]

            if course_id not in self._all_course_ids:
                return None

            source_paths: list[str] = []
            meta_path = get_course_path(course_id)["meta"]
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        raw_paths = meta.get("source_paths") or meta.get("source_path") or meta.get("pdf_path") or []
                        source_paths = _coerce_source_paths(raw_paths)
                except Exception:
                    source_paths = []

            while len(self._courses) >= self._max_cached:
                self._evict_lru_course()

            try:
                rag = RAGChains(course_id, source_paths)
                rag.vectorstore = rag._load_existing_vectorstore()
                if rag.vectorstore is None:
                    logger.warning("[LazyLoad] Course '%s' has no valid FAISS index.", course_id)
                    return None
                rag.initialise_chains_only()
                self._courses[course_id] = rag
                self._lru[course_id] = None
                return rag
            except Exception as exc:
                logger.error("[LazyLoad] Failed to load course '%s': %s", course_id, exc)
                return None

    def register_course_id(self, course_id: str, source_path: str | Sequence[str]) -> None:
        """Register a course before background document processing starts."""
        source_paths = _coerce_source_paths(source_path)
        self._all_course_ids.add(course_id)
        paths = get_course_path(course_id)
        with open(paths["meta"], "w", encoding="utf-8") as f:
            json.dump(
                {
                    "course_id": course_id,
                    "source_path": source_paths[0] if source_paths else "",
                    "source_paths": source_paths,
                    "pdf_path": source_paths[0] if source_paths else "",
                    "filenames": [os.path.basename(path) for path in source_paths],
                    "file_count": len(source_paths),
                    "status": "pending",
                    "created_at": time.time(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info("[Register] Registered course '%s'.", course_id)

    def process_new_course(self, course_id: str, source_path: str | Sequence[str]) -> None:
        """Parse, chunk, embed, and index a newly uploaded document."""
        try:
            source_paths = _coerce_source_paths(source_path)
            paths = get_course_path(course_id)
            with open(paths["meta"], "r+", encoding="utf-8") as f:
                meta = json.load(f)
                meta["status"] = "processing"
                meta["processing_started_at"] = time.time()
                f.seek(0)
                json.dump(meta, f, ensure_ascii=False, indent=2)
                f.truncate()

            rag = RAGChains(course_id, source_paths).initialise()
            with self._lock:
                self._courses[course_id] = rag
                self._lru[course_id] = None
                self._all_course_ids.add(course_id)

            with open(paths["meta"], "r+", encoding="utf-8") as f:
                meta = json.load(f)
                meta["status"] = "ready"
                meta["ready_at"] = time.time()
                f.seek(0)
                json.dump(meta, f, ensure_ascii=False, indent=2)
                f.truncate()
            logger.info("[Background] Course '%s' processed successfully.", course_id)
        except Exception as exc:
            logger.error("[Background] Failed processing '%s': %s", course_id, exc)
            paths = get_course_path(course_id)
            try:
                with open(paths["meta"], "r+", encoding="utf-8") as f:
                    meta = json.load(f)
                    meta["status"] = "failed"
                    meta["error"] = str(exc)
                    f.seek(0)
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                    f.truncate()
            except Exception:
                pass

    def get_course_status(self, course_id: str) -> str:
        """Return course processing status."""
        if course_id in self._courses and self._courses[course_id].vectorstore is not None:
            return "ready"

        meta_path = get_course_path(course_id)["meta"]
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("status", "pending")
            except Exception:
                pass

        return "unknown"

    def create_course(self, source_path: str | Sequence[str]) -> str:
        """Synchronously create and index a course."""
        course_id = generate_course_id()
        source_paths = _coerce_source_paths(source_path)
        rag = RAGChains(course_id, source_paths).initialise()
        self._courses[course_id] = rag
        self._lru[course_id] = None
        self._all_course_ids.add(course_id)

        with open(get_course_path(course_id)["meta"], "w", encoding="utf-8") as f:
            json.dump(
                {
                    "course_id": course_id,
                    "source_path": source_paths[0] if source_paths else "",
                    "source_paths": source_paths,
                    "pdf_path": source_paths[0] if source_paths else "",
                    "filenames": [os.path.basename(path) for path in source_paths],
                    "file_count": len(source_paths),
                    "status": "ready",
                    "created_at": time.time(),
                    "ready_at": time.time(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        return course_id

    def get_course(self, course_id: str) -> Optional[RAGChains]:
        """Get a course, lazy-loading it from FAISS if needed."""
        return self._ensure_course_loaded(course_id)

    def remove_course(self, course_id: str) -> None:
        """Remove a course from memory, generated files, and FAISS."""
        with self._lock:
            self._courses.pop(course_id, None)
            self._lru.pop(course_id, None)
            self._all_course_ids.discard(course_id)

        try:
            _drop_index(course_id)
        except Exception as exc:
            logger.warning("[Remove] Failed to drop FAISS index for '%s': %s", course_id, exc)

        for path in get_course_path(course_id).values():
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception as exc:
                    logger.warning("[Remove] Failed to remove '%s': %s", path, exc)

    def list_courses(self) -> list[str]:
        """List all registered course IDs."""
        return sorted(self._all_course_ids)

    def contains(self, course_id: str) -> bool:
        """Return whether a course ID is registered."""
        return course_id in self._all_course_ids
