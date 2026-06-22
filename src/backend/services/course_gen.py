"""
Course generation and management service.
Chỉ chứa: RAGChains (base chains + chat), CourseManager (LRU caching).
Mapping: Features 5.0, 6.1-6.3 [5, 9] — Tạo Course & Chapters.
Các chức năng tạo resource (Quiz, Flashcard, Slide...) được chuyển sang resource_gen.py.
"""
import os
import json
import time
import gc
import shutil
import threading
from collections import OrderedDict
from typing import List, Optional, Tuple, Dict, Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from backend.core.config import (
    get_embeddings,
    get_llm,
    format_docs,
    extract_json,
    sanitize_filename,
    generate_course_id,
    get_course_path,
    UPLOAD_DIR,
    INDEX_DIR,
    QUESTIONS_DIR,
    AUDIO_DIR,
    GUIDES_DIR,
    FLASHCARDS_DIR,
    DEFAULT_MAX_CACHED_COURSES,
    EMBEDDING_MODEL,
    LLM_MODEL,
    BATCH_SIZE,
    RETRY_DELAY,
    MAX_RETRY_DELAY,
    logger,
)
from backend.core.prompts import (
    SYLLABUS_PROMPT,
    JSON_QUESTION_FORMAT_INSTRUCTION,
    LATEX_SLIDE_INSTRUCTION,
    PODCAST_SCRIPT_PROMPT,
    STUDY_GUIDE_PROMPT,
    CONTINUE_GUIDE_PROMPT,
    SUMMARY_PROMPT,
    FLASHCARDS_PROMPT,
)
from backend.vector_db.faiss_manager import create_or_load_faiss, load_existing_faiss


# ═══════════════════════════════════════════════════════════════════════════════
# RAGChains — Per-course container for chains and generation logic
# ═══════════════════════════════════════════════════════════════════════════════

class RAGChains:
    """
    Container for all LangChain RAG chains for one course.
    Chỉ giữ: Chain builders, chat, syllabus.
    Resource generation (Quiz, Flashcard, Slide...) được delegate qua ResourceGenerator.
    """

    def __init__(self, course_id: str, pdf_path: str):
        self.course_id = course_id
        self.pdf_path = pdf_path
        self.chat_chain = None
        self.json_chain = None
        self.slide_chain = None
        self.syllabus_chain = None
        self.audio_chain = None
        self.guide_chain = None
        self.flashcard_chain = None
        self.vectorstore: Optional[FAISS] = None
        self.faiss_path = get_course_path(course_id)["faiss"]
        self.summary_chain = None

    def get_resource_generator(self):
        """Get ResourceGenerator instance for this course."""
        from backend.services.resource_gen import ResourceGenerator
        return ResourceGenerator(self)

    def get_mindmap_generator(self):
        """Get MindmapGenerator instance for this course."""
        from backend.services.mindmap_gen import MindmapGenerator
        return MindmapGenerator(self)
    
    def get_custom_processor(self):
        from backend.services.custom_processor import CustomProcessor
        return CustomProcessor(self)
    

    # ── Initialization ──────────────────────────────────────────────────────

    def initialise_chains_only(self) -> "RAGChains":
        """Build chains using pre-loaded vectorstore."""
        if self.vectorstore is None:
            raise ValueError("vectorstore must be set before initialising chains.")

        self.chat_chain, _ = self._build_chat_chain()
        self.json_chain, _ = self._build_json_chain()
        self.slide_chain = self._build_slide_chain()
        self.syllabus_chain = self._build_syllabus_chain()
        self.audio_chain = self._build_audio_chain()
        self.guide_chain = self._build_guide_chain()
        self.flashcard_chain = self._build_flashcard_chain()
        self.summary_chain = self._build_summary_chain()
        return self

    def initialise(self) -> "RAGChains":
        """Initialize vectorstore and all chains."""
        self.vectorstore = self._init_vectorstore()
        self.initialise_chains_only()
        return self

    def _init_vectorstore(self) -> FAISS:
        """Create or load FAISS vectorstore."""
        return create_or_load_faiss(self.faiss_path, self.pdf_path, self.course_id)

    def _load_existing_vectorstore(self) -> Optional[FAISS]:
        """Load existing FAISS index from disk."""
        return load_existing_faiss(self.faiss_path)

    # ── Chain Builders ──────────────────────────────────────────────────────

    def _build_chat_chain(self) -> Tuple[Any, Any]:
        """Build chat RAG chain."""
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})
        llm = get_llm(temperature=0.1, max_output_tokens=8192)
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Bạn là trợ lý ảo học tập thông minh.\n"
             "Trả lời ngắn gọn, rõ ràng dựa ngữ cảnh.\n"
             "Nếu không có thông tin, nói 'Tài liệu không nhắc đến'.\n\n"
             "Ngữ cảnh:\n{context}"),
            ("human", "{input}"),
        ])
        chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain, retriever

    def _build_json_chain(self) -> Tuple[Any, Any]:
        """Build JSON output chain (for questions)."""
        llm = get_llm(temperature=0.1, max_output_tokens=8192)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 20})
        prompt = ChatPromptTemplate.from_messages([
            ("system", JSON_QUESTION_FORMAT_INSTRUCTION),
            ("human", "BẮT BUỘC: Tạo ĐÚNG {quantity} câu trắc nghiệm MCQ mới về: {topic}. Đánh ID từ: {start_id}. (Tuyệt đối không làm thiếu số lượng)"),
        ])
        chain = (
            {
                "context": (lambda x: x["topic"]) | retriever | format_docs,
                "quantity": lambda x: x["quantity"],
                "topic": lambda x: x["topic"],
                "start_id": lambda x: x["start_id"],
            }
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain, retriever

    def _build_slide_chain(self) -> Any:
        """Build LaTeX slide generation chain."""
        llm = get_llm(temperature=0.1, max_output_tokens=8192)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 18})
        prompt = ChatPromptTemplate.from_messages([
            ("system", LATEX_SLIDE_INSTRUCTION),
            ("human", "Soạn bộ slide khoảng {num_slides} trang về chủ đề: {topic}"),
        ])
        chain = (
            {
                "context": (lambda x: x["topic"]) | retriever | format_docs,
                "topic": lambda x: x["topic"],
                "num_slides": lambda x: x["num_slides"],
            }
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain

    def _build_summary_chain(self) -> Any:
        """Build summary generation chain."""
        llm = get_llm(temperature=0.1)
        prompt = ChatPromptTemplate.from_messages([
            ("system", SUMMARY_PROMPT),
            ("human", "Hãy tạo bản tóm tắt súc tích cho tài liệu này."),
        ])
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        return (
            {"context": (lambda x: "tóm tắt toàn bộ nội dung tài liệu") | retriever | format_docs}
            | prompt
            | llm
            | StrOutputParser()
        )

    def _build_syllabus_chain(self) -> Any:
        """Build syllabus generation chain."""
        llm = get_llm(temperature=0.1, max_output_tokens=8192)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 10})
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYLLABUS_PROMPT),
            ("human", "Tạo syllabus cho tài liệu này."),
        ])
        chain = (
            {"context": retriever | format_docs}
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain

    def _build_audio_chain(self) -> Any:
        """Build podcast script generation chain."""
        llm = get_llm(temperature=0.3, max_output_tokens=8192)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 12})
        prompt = ChatPromptTemplate.from_messages([
            ("system", PODCAST_SCRIPT_PROMPT),
            ("human", "Tạo script podcast thảo luận về nội dung tài liệu."),
        ])
        chain = (
            {"context": (lambda x: x.get("topic", "") or "tổng quan") | retriever | format_docs}
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain

    def _build_guide_chain(self) -> Any:
        """Build study guide generation chain."""
        llm = get_llm(temperature=0.3, max_output_tokens=8192)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        prompt = ChatPromptTemplate.from_messages([
            ("system", STUDY_GUIDE_PROMPT),
            ("human", "Dựa trên các mảnh dữ liệu quan trọng nhất, hãy soạn bản Study Guide chi tiết cho TỪNG PHẦN của tài liệu. Không được tóm tắt sơ sài."),
        ])
        chain = (
            {"context": (lambda x: "nội dung chi tiết hệ thống hóa kiến thức") | retriever | format_docs}
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain

    def _build_flashcard_chain(self) -> Any:
        """Build flashcard generation chain."""
        llm = get_llm(temperature=0.2, max_output_tokens=16384)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        prompt = ChatPromptTemplate.from_messages([
            ("system", FLASHCARDS_PROMPT),
            ("human", "Tạo ĐÚNG 25 flashcards phân phối đều khái niệm quan trọng trong tài liệu."),
        ])
        chain = (
            {"context": (lambda x: x.get("topic", "") or "tổng quan") | retriever | format_docs}
            | prompt
            | llm
            | StrOutputParser()
        )
        return chain

    def _require_ready(self) -> None:
        """Ensure course is ready for operations."""
        if self.vectorstore is None:
            raise RuntimeError(f"Course '{self.course_id}' vectorstore not initialized.")

    # ── Chat ─────────────────────────────────────────────────────────────────

    def ask(self, question: str) -> str:
        """Chat with the course content."""
        self._require_ready()
        return self.chat_chain.invoke(question)

    # ── Syllabus (Course Outline) — Feature 5.0, 6.3 [9] ─────────────────────

    def generate_syllabus(self) -> list:
        """Generate course syllabus/outline."""
        self._require_ready()
        raw = self.syllabus_chain.invoke({})
        clean = extract_json(raw)
        syllabus = json.loads(clean, strict=False)

        s_path = get_course_path(self.course_id)["syllabus"]
        with open(s_path, "w", encoding="utf-8") as f:
            json.dump(syllabus, f, indent=2, ensure_ascii=False)

        return syllabus


# ═══════════════════════════════════════════════════════════════════════════════
# CourseManager — Multi-course management with LRU caching
# ═══════════════════════════════════════════════════════════════════════════════

class CourseManager:
    """
    Multi-course manager with LRU caching.
    - Lazy loading: only scan disk IDs at startup.
    - LRU eviction: remove least recently used when cache full.
    - Thread-safe: protected by threading.Lock.
    """

    def __init__(self, max_cached: int = DEFAULT_MAX_CACHED_COURSES):
        self._courses: Dict[str, RAGChains] = {}
        self._lock = threading.Lock()
        self._max_cached = max_cached
        self._all_course_ids: set = set()
        self._lru: OrderedDict[str, None] = OrderedDict()
        self._scan_existing_courses()

    def _scan_existing_courses(self):
        """Scan INDEX_DIR and register course IDs (no FAISS loaded)."""
        if not os.path.exists(INDEX_DIR):
            return
        found = 0
        for name in sorted(os.listdir(INDEX_DIR)):
            if name.startswith("course_") and os.path.isdir(
                os.path.join(INDEX_DIR, name)
            ):
                cid = name.replace("course_", "", 1)
                self._all_course_ids.add(cid)
                found += 1

        if found:
            logger.info(
                f"[LazyLoad] Registered {found} courses. "
                f"FAISS loads on-demand (max cache: {self._max_cached})."
            )

    def _evict_lru_course(self):
        """Remove least recently used course from cache."""
        if not self._lru:
            return
        evict_id = next(iter(self._lru))
        del self._lru[evict_id]
        if evict_id in self._courses:
            del self._courses[evict_id]
        logger.info(f"[LRU] Evicted course '{evict_id}' from cache.")
        gc.collect()

    def _ensure_course_loaded(self, course_id: str) -> Optional[RAGChains]:
        """Lazy-load a course into RAM if not cached."""
        with self._lock:
            if course_id in self._courses:
                if course_id in self._lru:
                    self._lru.move_to_end(course_id)
                else:
                    self._lru[course_id] = None
                return self._courses[course_id]

            if course_id not in self._all_course_ids:
                return None

            pdf_path = ""
            meta_path = get_course_path(course_id)["meta"]
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        pdf_path = meta.get("pdf_path", "")
                except Exception:
                    pass

            while len(self._courses) >= self._max_cached:
                self._evict_lru_course()

            try:
                rag = RAGChains(course_id, pdf_path)
                rag.vectorstore = rag._load_existing_vectorstore()
                if rag.vectorstore is None:
                    logger.warning(f"[LazyLoad] Course '{course_id}' has no valid FAISS.")
                    return None
                rag.initialise_chains_only()
                self._courses[course_id] = rag
                self._lru[course_id] = None
                logger.info(
                    f"[LazyLoad] Loaded course '{course_id}' into cache. "
                    f"Cache: {len(self._courses)}/{self._max_cached}"
                )
                return rag
            except Exception as e:
                logger.error(f"[LazyLoad] Failed to load course '{course_id}': {e}")
                return None

    def register_course_id(self, course_id: str, pdf_path: str):
        """Register a course without processing PDF."""
        self._all_course_ids.add(course_id)
        paths = get_course_path(course_id)
        with open(paths["meta"], "w", encoding="utf-8") as f:
            json.dump({
                "course_id": course_id,
                "pdf_path": pdf_path,
                "status": "pending",
                "created_at": time.time(),
            }, f, ensure_ascii=False)
        logger.info(f"[Register] Registered course '{course_id}'.")

    def process_new_course(self, course_id: str, pdf_path: str):
        """Background processing of a new course."""
        try:
            rag = RAGChains(course_id, pdf_path).initialise()
            with self._lock:
                self._courses[course_id] = rag
                self._lru[course_id] = None
                self._all_course_ids.add(course_id)
            paths = get_course_path(course_id)
            with open(paths["meta"], "r+", encoding="utf-8") as f:
                meta = json.load(f)
                meta["status"] = "ready"
                meta["ready_at"] = time.time()
                f.seek(0)
                json.dump(meta, f, ensure_ascii=False)
                f.truncate()
            logger.info(f"[Background] Course '{course_id}' processed successfully.")
        except Exception as e:
            logger.error(f"[Background] Failed processing '{course_id}': {e}")
            paths = get_course_path(course_id)
            try:
                with open(paths["meta"], "r+", encoding="utf-8") as f:
                    meta = json.load(f)
                    meta["status"] = "failed"
                    meta["error"] = str(e)
                    f.seek(0)
                    json.dump(meta, f, ensure_ascii=False)
                    f.truncate()
            except Exception:
                pass

    def get_course_status(self, course_id: str) -> str:
        """Get course ready status."""
        if course_id in self._courses:
            rag = self._courses[course_id]
            if rag.vectorstore is not None:
                return "ready"

        meta_path = get_course_path(course_id)["meta"]
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    return meta.get("status", "pending")
            except Exception:
                pass

        return "unknown"

    def create_course(self, pdf_path: str) -> str:
        """Synchronous course creation."""
        course_id = generate_course_id()
        rag = RAGChains(course_id, pdf_path).initialise()
        self._courses[course_id] = rag
        self._lru[course_id] = None
        self._all_course_ids.add(course_id)
        paths = get_course_path(course_id)
        with open(paths["meta"], "w", encoding="utf-8") as f:
            json.dump({
                "course_id": course_id,
                "pdf_path": pdf_path,
                "created_at": time.time(),
            }, f, ensure_ascii=False)
        return course_id

    def get_course(self, course_id: str) -> Optional[RAGChains]:
        """Get course with lazy loading."""
        return self._ensure_course_loaded(course_id)

    def remove_course(self, course_id: str):
        """Remove course from cache and disk."""
        with self._lock:
            if course_id in self._courses:
                del self._courses[course_id]
            if course_id in self._lru:
                del self._lru[course_id]
            self._all_course_ids.discard(course_id)

        paths = get_course_path(course_id)
        for p in paths.values():
            if os.path.exists(p):
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                except Exception:
                    pass

    def list_courses(self) -> list:
        """List all registered course IDs."""
        return sorted(self._all_course_ids)

    def contains(self, course_id: str) -> bool:
        """Check if course exists."""
        return course_id in self._all_course_ids