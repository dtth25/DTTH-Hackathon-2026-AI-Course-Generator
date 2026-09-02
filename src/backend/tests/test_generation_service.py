"""Automated tests for Generation Service and AI API completion (Checkpoint 8 / Prompt 5)."""

import json
import os
from app.models.course import Course
from app.services.database import SessionLocal
from app.services.generator import Generator
from app.services.llm import LLMService
from app.services.vector_store import Document, get_vector_store


def test_get_generator_wires_per_feature_openrouter_models(monkeypatch):
    """Book/Vid share the default (Pro) model; Slide/Quiz get their own Flash-model
    LLMService instance — see OPENROUTER_{BOOK,SLIDE,QUIZ,VID}_MODEL in config.py."""
    from app.core.config import settings
    from app.routers import generation as generation_router

    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "google/gemini-2.5-pro")
    monkeypatch.setattr(settings, "OPENROUTER_BOOK_MODEL", "")
    monkeypatch.setattr(settings, "OPENROUTER_SLIDE_MODEL", "google/gemini-2.5-pro")
    monkeypatch.setattr(settings, "OPENROUTER_QUIZ_MODEL", "google/gemini-2.5-pro")
    monkeypatch.setattr(settings, "OPENROUTER_VID_MODEL", "")

    generation_router._generator_instance = None
    gen = generation_router.get_generator()
    try:
        assert set(gen.feature_llms.keys()) == {"book", "slides", "quiz", "vid"}
        # Book/Vid have no override -> share the same default LLMService instance.
        assert gen.feature_llms["book"] is gen.llm
        assert gen.feature_llms["vid"] is gen.llm
        assert gen.llm.model == "google/gemini-2.5-pro"
        # Slide/Quiz get their own instance running the Flash model.
        assert gen.feature_llms["slides"] is not gen.llm
        assert gen.feature_llms["slides"].model == "google/gemini-2.5-pro"
        assert gen.feature_llms["quiz"] is not gen.llm
        assert gen.feature_llms["quiz"].model == "google/gemini-2.5-pro"
    finally:
        generation_router._generator_instance = None


def test_llm_service_and_prompts():
    """Test LLMService initialization, prompt loading, and structured output generation."""
    llm = LLMService()
    assert llm.prompts_dir is not None
    assert os.path.exists(os.path.join(llm.prompts_dir, "book_outline.txt"))
    assert os.path.exists(os.path.join(llm.prompts_dir, "book_chapter.txt"))
    assert os.path.exists(os.path.join(llm.prompts_dir, "slides.txt"))
    assert os.path.exists(os.path.join(llm.prompts_dir, "quiz.txt"))
    assert os.path.exists(os.path.join(llm.prompts_dir, "vid.txt"))

    # Test generation methods
    context = "[Chunk ID: chunk_1] (Tài liệu: doc.pdf, Trang: 1): Trí tuệ nhân tạo là lĩnh vực khoa học máy tính."
    valid_cids = ["chunk_1", "chunk_2"]

    outline = llm.generate_book_outline(context=context, detail_level="Tiêu chuẩn", user_prompt="", doc_names="doc.pdf")
    assert outline.title != ""
    assert outline.preface != ""
    assert len(outline.chapters) >= 4
    assert outline.chapters[0].retrieval_query != ""

    chapter = llm.generate_book_chapter(
        book_title=outline.title,
        chapter_plan=outline.chapters[0],
        total_chapters=len(outline.chapters),
        context=context,
        detail_level="Tiêu chuẩn",
        valid_chunk_ids=valid_cids,
    )
    assert chapter.chapter_title != ""
    assert len(chapter.sections) > 0
    assert len(chapter.source_chunk_ids) > 0

    slides = llm.generate_slides(context=context, topic="AI", num_slides=3, valid_chunk_ids=valid_cids)
    assert slides.title != ""
    assert len(slides.slides) > 0
    assert len(slides.slides[0].source_chunk_ids) > 0

    quiz = llm.generate_quiz(context=context, topic="AI", quantity=3, valid_chunk_ids=valid_cids)
    assert quiz.title != ""
    assert len(quiz.questions) > 0
    assert len(quiz.questions[0].options) == 4
    assert quiz.questions[0].correct_answer in ["A", "B", "C", "D"]
    assert len(quiz.questions[0].source_chunk_ids) > 0

    vid = llm.generate_vid(context=context, topic="AI", fmt="overview", user_prompt="", valid_chunk_ids=valid_cids)
    assert vid.title != ""
    assert len(vid.scenes) > 0
    assert len(vid.scenes[0].source_chunk_ids) > 0
    assert not vid.scenes[0].narration.startswith("Chào mừng")

    prompt = llm._load_prompt(
        "vid.txt", topic="AI", user_prompt="(không có)", scene_hint="4-5 phân cảnh",
        narration_hint="20-30 từ", format_guidance="Nhịp nhanh, dứt khoát.", context=context,
    )
    assert "Nhịp nhanh, dứt khoát" in prompt
    assert "Cấm mở bằng" in prompt
    assert "comparison" in prompt
    assert "tối đa 2-3 phân cảnh" in prompt
    assert "{format_guidance}" not in prompt


def test_generator_all_artifacts_and_validation(client):
    """Test Generator service RAG retrieval, scoring > 70, filesystem saving, and PDF/PPTX generation."""
    db = SessionLocal()
    try:
        # Create a dummy course
        course_id = "test_gen_srv"
        course = Course(
            id=course_id,
            user_id="user_gen_srv",
            filenames=["ai_doc.pdf"],
            status="ready",
            stage="completed",
            progress=100,
            chunk_count=2,
            embedding_status="completed",
            quality_score=0,
        )
        db.add(course)
        db.commit()
    finally:
        db.close()

    vs = get_vector_store()
    vs.add_documents(
        [
            Document(content="Trí tuệ nhân tạo là mô phỏng trí tuệ con người.", metadata={"chunk_id": "chunk_1", "source_file": "ai_doc.pdf", "page": 1}),
            Document(content="Học sâu (Deep Learning) là tập con của học máy.", metadata={"chunk_id": "chunk_2", "source_file": "ai_doc.pdf", "page": 2}),
        ],
        course_id=course_id,
    )

    llm = LLMService()
    gen = Generator(vs, llm)

    # Generate all 4 core artifacts (Book, Slide, Quiz, Vid)
    book_out = gen.generate_book(course_id=course_id, detail_level="Tiêu chuẩn")
    slides_out = gen.generate_slides(course_id=course_id, topic="AI", num_slides=3)
    quiz_out = gen.generate_quiz(course_id=course_id, topic="AI", quantity=3)
    vid_out = gen.generate_vid(course_id=course_id, topic="AI", fmt="overview")
    assert book_out is not None
    assert book_out.title != ""
    assert book_out.preface != ""
    assert len(book_out.chapters) >= 4
    assert slides_out.title != ""
    assert quiz_out.title != ""
    assert vid_out.title != ""

    # Verify filesystem storage
    art_dir = gen._get_artifact_dir(course_id)
    for fname in [
        "book.json", "book.pdf", "slides.json", "slide.pptx", "quiz.json", "quiz-key.pdf",
        "vid.json", "vid.mp4",
    ]:
        fpath = os.path.join(art_dir, fname)
        assert os.path.exists(fpath), f"Expected file {fname} to exist at {fpath}"
        assert os.path.getsize(fpath) > 0, f"File {fname} is empty"

    # Book PDF smoke test: real cover + preface + TOC + >=4 chapters -> multiple pages
    book_pdf_path = os.path.join(art_dir, "book.pdf")
    with open(book_pdf_path, "rb") as f:
        assert f.read(4) == b"%PDF", "book.pdf is not a valid PDF file"
    import fitz
    pdf_doc = fitz.open(book_pdf_path)
    assert pdf_doc.page_count >= 8, f"Expected book.pdf to have >= 8 pages, got {pdf_doc.page_count}"
    pdf_doc.close()

    # Book artifact status must reach "ready"
    assert gen.get_artifact_status(course_id, "book").get("status") == "ready"

    # Verify quality score > 70 and readiness flags in DB
    db = SessionLocal()
    try:
        import json
        course_upd = db.query(Course).filter(Course.id == course_id).first()
        assert course_upd.quality_score > 70, f"Expected quality score > 70, got {course_upd.quality_score}"
        meta_dict = json.loads(course_upd.metadata_json) if isinstance(course_upd.metadata_json, str) else course_upd.metadata_json
        sp_meta = meta_dict["study_pack"]
        assert sp_meta["readiness"]["study_guide_pdf"] is True
        assert sp_meta["readiness"]["slides"] is True
        assert sp_meta["readiness"]["quiz"] is True
        assert sp_meta["readiness"]["vid"] is True
    finally:
        db.close()

    # Clean up Chroma
    vs.delete_course(course_id)


def test_generation_api_endpoints_complete(client):
    """Test full generation API flow: trigger background generation, verify study pack, retrieval, and downloads."""
    # Register & login
    reg_data = {"email": "gen_api@example.com", "password": "password123", "full_name": "Gen API User"}
    res = client.post("/api/auth/register", json=reg_data)
    if res.status_code == 201:
        res = client.post("/api/auth/verify-email", json={"email": "gen_api@example.com", "code": "000000"})
    else:
        res = client.post("/api/auth/login", json={"email": "gen_api@example.com", "password": "password123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload a dummy file to create a course
    files = [("files", ("test_gen_api.pdf", b"Dummy AI doc content for API testing", "application/pdf"))]
    res_upload = client.post("/api/upload", headers=headers, files=files)
    assert res_upload.status_code == 201
    course_id = res_upload.json()["course_id"]

    # Trigger generation endpoints
    for ep in ["/api/generate-book", "/api/generate-slide", "/api/generate-quiz", "/api/generate-vid"]:
        res_gen = client.post(f"{ep}?course_id={course_id}", headers=headers)
        assert res_gen.status_code == 200, res_gen.text
        assert res_gen.json()["status"] == "queued"

    # Verify study pack stats and readiness (BackgroundTasks executed synchronously by TestClient)
    res_sp = client.get(f"/api/course/{course_id}/study-pack", headers=headers)
    assert res_sp.status_code == 200, res_sp.text
    sp_data = res_sp.json()
    assert sp_data["stats"]["has_book"] is True
    assert sp_data["stats"]["has_book_pdf"] is True
    assert sp_data["stats"]["has_slide"] is True
    assert sp_data["stats"]["has_slide_pptx"] is True
    assert sp_data["stats"]["has_quiz"] is True
    assert sp_data["stats"]["has_quiz_answer_key"] is True
    assert sp_data["stats"]["has_vid"] is True
    assert sp_data["stats"]["quality_score"] > 70

    # Verify retrieval endpoints return generated JSON
    res_book = client.get(f"/api/course/{course_id}/book", headers=headers)
    assert res_book.status_code == 200
    book_body = res_book.json()
    assert book_body["status"] == "ready"
    assert book_body["error"] is None
    assert book_body["data"]["title"] != ""
    assert len(book_body["data"]["chapters"]) > 0
    assert "source_chunk_ids" not in book_body["data"]["chapters"][0]

    res_slide = client.get(f"/api/course/{course_id}/slide", headers=headers)
    assert res_slide.status_code == 200
    slide_body = res_slide.json()
    assert slide_body["status"] == "ready"
    assert len(slide_body["data"]["slides"]) > 0
    assert "source_chunk_ids" not in slide_body["data"]["slides"][0]

    res_quiz = client.get(f"/api/course/{course_id}/quiz", headers=headers)
    assert res_quiz.status_code == 200
    quiz_body = res_quiz.json()
    assert quiz_body["status"] == "ready"
    assert len(quiz_body["data"]) > 0  # quiz envelope data is the list of questions
    assert "source_chunk_ids" not in quiz_body["data"][0]

    res_vid = client.get(f"/api/course/{course_id}/vid", headers=headers)
    assert res_vid.status_code == 200
    vid_body = res_vid.json()
    assert vid_body["status"] == "ready"
    assert len(vid_body["data"]["scenes"]) > 0
    assert "source_chunk_ids" not in vid_body["data"]["scenes"][0]

    # Verify download endpoints return 200 OK with file content
    for file_ep, content_type in [
        ("/book.pdf", "application/pdf"),
        ("/slide.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("/quiz-key.pdf", "application/pdf"),
        ("/vid.mp4", "video/mp4"),
    ]:
        res_dl = client.get(f"/api/course/{course_id}{file_ep}", headers=headers)
        assert res_dl.status_code == 200, f"Failed on {file_ep}: {res_dl.text}"
        assert len(res_dl.content) > 0
        assert content_type in res_dl.headers.get("content-type", "")

    # Test health endpoints
    res_h = client.get("/health")
    assert res_h.status_code == 200
    assert "ready" in res_h.json()
    res_ah = client.get("/api/health")
    assert res_ah.status_code == 200
    assert "course_ids" in res_ah.json()



    res_src = client.get(f"/documents/{course_id}/sources", headers=headers)
    assert res_src.status_code == 200
    assert "sources" in res_src.json()


def test_book_generator_error_propagation():
    """LLM failures during the multi-pass Book pipeline must record a real error status and
    must NOT write a partial/placeholder book.json or book.pdf."""
    from app.services.llm import LLMGenerationError

    db = SessionLocal()
    try:
        course_id = "test_book_err"
        course = Course(
            id=course_id,
            user_id="user_book_err",
            filenames=["doc.pdf"],
            status="ready",
            stage="completed",
            progress=100,
            chunk_count=0,
            embedding_status="completed",
            quality_score=0,
        )
        db.add(course)
        db.commit()
    finally:
        db.close()

    vs = get_vector_store()
    llm = LLMService()
    gen = Generator(vs, llm)
    art_dir = gen._get_artifact_dir(course_id)

    # This course has no real chunks; stub retrieval so the empty-context guard passes and
    # we actually exercise the LLM-failure path this test is about (the empty-context guard
    # itself is covered by test_generator_empty_context_guard below).
    gen._retrieve_context = lambda *a, **k: (
        "[Chunk ID: chunk_1] (Tài liệu: doc.pdf, Trang: 1):\nNội dung mẫu để kiểm thử.",
        ["chunk_1"],
    )

    def _raise(*args, **kwargs):
        raise LLMGenerationError("boom")

    # Case 1: outline call itself fails -> whole book aborts before any chapter work.
    original_outline = llm.generate_book_outline
    llm.generate_book_outline = _raise
    try:
        result = gen.generate_book(course_id=course_id, detail_level="Tiêu chuẩn")
    finally:
        llm.generate_book_outline = original_outline

    assert result is None
    assert not os.path.exists(os.path.join(art_dir, "book.json"))
    assert not os.path.exists(os.path.join(art_dir, "book.pdf"))
    status_info = gen.get_artifact_status(course_id, "book")
    assert status_info["status"] == "error"
    assert status_info["error"] == "Không thể tạo sách ôn tập. Vui lòng thử lại."
    assert status_info["error_code"] == "BOOK_GENERATION_FAILED"
    assert "boom" in status_info["technical_error"]

    # Case 2: outline succeeds (fallback), but every chapter call fails -> still a hard error.
    original_chapter = llm.generate_book_chapter
    llm.generate_book_chapter = _raise
    try:
        result2 = gen.generate_book(course_id=course_id, detail_level="Tiêu chuẩn")
    finally:
        llm.generate_book_chapter = original_chapter

    assert result2 is None
    assert not os.path.exists(os.path.join(art_dir, "book.json"))
    assert not os.path.exists(os.path.join(art_dir, "book.pdf"))
    status_info2 = gen.get_artifact_status(course_id, "book")
    assert status_info2["status"] == "error"
    assert status_info2["error"] == "Không thể tạo sách ôn tập. Vui lòng thử lại."
    assert status_info2["error_code"] == "BOOK_GENERATION_FAILED"
    assert "boom" in status_info2["technical_error"]

    vs.delete_course(course_id)


def test_generator_empty_context_guard():
    """A course with zero retrievable chunks (e.g. an image-only PDF whose text never got
    extracted/indexed) must fail every generator with a clear error — NOT produce a
    'no context provided' apology artifact marked ready (which is what left Study Guide
    abstaining, Quiz stuck at 100%, and Video narrating filler)."""
    db = SessionLocal()
    try:
        course_id = "test_empty_ctx"
        db.add(
            Course(
                id=course_id,
                user_id="user_empty_ctx",
                filenames=["scan.pdf"],
                status="ready",
                stage="completed",
                progress=100,
                chunk_count=0,
                embedding_status="completed",
                quality_score=0,
            )
        )
        db.commit()
    finally:
        db.close()

    gen = Generator(get_vector_store(), LLMService())
    art_dir = gen._get_artifact_dir(course_id)

    for artifact, run in (
        ("book", lambda: gen.generate_book(course_id=course_id)),
        ("slides", lambda: gen.generate_slides(course_id=course_id)),
        ("quiz", lambda: gen.generate_quiz(course_id=course_id)),
        ("vid", lambda: gen.generate_vid(course_id=course_id)),
    ):
        assert run() is None, f"{artifact} should abort on empty context"
        info = gen.get_artifact_status(course_id, artifact)
        assert info["status"] == "error", f"{artifact} status should be error"
        assert "Không tìm thấy nội dung" in (info.get("error") or ""), f"{artifact} error message"

    # No placeholder artifacts were written despite the 'ready' course status.
    for fname in ("book.json", "slides.json", "quiz.json", "vid.json"):
        assert not os.path.exists(os.path.join(art_dir, fname)), f"{fname} must not exist"


def test_book_api_error_status_envelope(client, monkeypatch):
    """GET /api/course/{id}/book must surface a real error via the status envelope when the
    background generation job fails, instead of silently reporting readiness."""
    from app.routers.generation import get_generator
    from app.services.llm import LLMGenerationError

    reg_data = {"email": "book_err_api@example.com", "password": "password123", "full_name": "Book Err User"}
    res = client.post("/api/auth/register", json=reg_data)
    if res.status_code == 201:
        res = client.post("/api/auth/verify-email", json={"email": "book_err_api@example.com", "code": "000000"})
    else:
        res = client.post("/api/auth/login", json={"email": "book_err_api@example.com", "password": "password123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    files = [("files", ("book_err.pdf", b"Dummy doc content", "application/pdf"))]
    res_upload = client.post("/api/upload", headers=headers, files=files)
    assert res_upload.status_code == 201
    course_id = res_upload.json()["course_id"]

    generator = get_generator()

    def _raise(*args, **kwargs):
        raise LLMGenerationError("api-boom")

    # Patch the actual LLM instance the "book" feature routes through — this may be a
    # The shared client remains injectable for isolated generation tests.
    monkeypatch.setattr(generator._llm_for("book"), "generate_book_outline", _raise)

    res_gen = client.post(f"/api/generate-book?course_id={course_id}", headers=headers)
    assert res_gen.status_code == 200, res_gen.text

    res_book = client.get(f"/api/course/{course_id}/book", headers=headers)
    assert res_book.status_code == 200
    body = res_book.json()
    assert body["status"] == "error"
    assert body["error"] == "Không thể tạo sách ôn tập. Vui lòng thử lại."
    assert body["error_code"] == "BOOK_GENERATION_FAILED"
    assert "api-boom" not in res_book.text
    assert "OPENROUTER" not in res_book.text.upper()
    assert body["data"] is None


def test_all_artifact_status_apis_sanitize_legacy_raw_diagnostics(client):
    """Successful status envelopes must never publish persisted exception text."""
    email = "artifact-safe-status@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "full_name": "Safe Status"},
    )
    verified = client.post(
        "/api/auth/verify-email", json={"email": email, "code": "000000"}
    )
    headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]

    raw_errors = {
        "book": "Failed to fetch OpenRouter upstream",
        "slides": "Failed to fetch provider response",
        "quiz": "OpenRouter request body leaked",
        "vid": "ffmpeg stderr: /srv/private/input.mp4",
    }
    with SessionLocal() as db:
        course = Course(
            user_id=user_id,
            filenames=["source.txt"],
            status="ready",
            stage="completed",
            progress=100,
            embedding_status="completed",
            metadata_json=json.dumps(
                {
                    "study_pack": {
                        "artifacts": {
                            artifact: {
                                "status": "error",
                                "error": raw_error,
                                "error_code": "OPENROUTER_REQUEST_FAILED",
                                "technical_error": raw_error,
                            }
                            for artifact, raw_error in raw_errors.items()
                        }
                    }
                }
            ),
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        course_id = course.id

    for endpoint in ("book", "slide", "quiz", "vid"):
        response = client.get(f"/api/course/{course_id}/{endpoint}", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert body["error_code"] == "AI_REQUEST_FAILED"
        assert body["error"] == "Không thể hoàn thành yêu cầu AI. Vui lòng thử lại."
        assert "failed to fetch" not in response.text.lower()
        assert "ffmpeg" not in response.text.lower()
        assert "openrouter" not in response.text.lower()

    renamed = client.patch(
        f"/api/courses/{course_id}", json={"name": "Tên an toàn"}, headers=headers
    )
    assert renamed.status_code == 200
    assert "metadata_json" not in renamed.json()
    assert "technical_error" not in renamed.text
    assert "openrouter" not in renamed.text.lower()

