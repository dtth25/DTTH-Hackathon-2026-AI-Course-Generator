# TESTING WORKFLOW

## Mục tiêu
- Đảm bảo mọi API và pipeline tuân thủ các ràng buộc dự án (Citation-First, file validation, backend-only).
- Cung cấp bộ kiểm thử tự động để phát hiện regressions sớm.

## Phạm vi
- Kiểm thử API backend (FastAPI): upload, generate-* endpoints, health.
- Kiểm thử tích hợp RAG → kiểm tra `citations` và traceability tới chunk_id.
- Kiểm thử file validation cho `.pdf`, `.docx`, `.txt`.

## Trách nhiệm
- QA Lead: định nghĩa test cases, duyệt kết quả test, quyết định khi fail.
- Backend Dev: viết/fix endpoint theo spec và hỗ trợ test dữ liệu giả (fixtures).
- CI: chạy toàn bộ test trên mỗi PR, block merge nếu test fail.

## Non-Negotiable Gates (tự động hoá kiểm tra)
1. File upload validation — endpoint `/api/upload` chỉ chấp nhận `.pdf`, `.docx`, `.txt`.
2. Citation-First — mọi response sinh ra từ LLM **phải** có trường `citations: [{page, source, chunk_id}]`.
3. No-LLM-from-frontend — frontend không được gọi model trực tiếp (kiểm tra bằng audit logs / integration tests).

## Công cụ & Thư viện
- Test runner: `pytest` (+ `pytest-asyncio` nếu cần)
- HTTP client: `httpx` (async) hoặc `requests`
- Test coverage: `coverage.py`
- CI: GitHub Actions (workflow chạy `pytest`)

## Structure gợi ý cho thư mục test

- `tests/unit/` — unit tests cho các helper, chunking logic
- `tests/integration/` — API integration tests (upload, generate-course, health)
- `tests/e2e/` — end-to-end, kiểm tra flow upload → embed → retrieve → generate

## Ví dụ test: Upload validation (pytest + httpx)

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_upload_rejects_unsupported_file(app):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        files = {"file": ("malware.exe", b"dummy", "application/octet-stream")}
        r = await ac.post("/api/upload", files=files)
    assert r.status_code == 400
    assert "unsupported file type" in r.json().get("detail", "").lower()

@pytest.mark.asyncio
async def test_upload_accepts_pdf(app, tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    async with AsyncClient(app=app, base_url="http://test") as ac:
        files = {"file": ("sample.pdf", pdf.read_bytes(), "application/pdf")}
        r = await ac.post("/api/upload", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "file_id" in data

```

## Ví dụ test: Citation presence & traceability

```python
def test_generate_course_includes_citations(client, sample_file_id):
    payload = {"file_id": sample_file_id, "user_prompt": "Tạo khóa học 3 chương"}
    r = client.post("/api/generate-course", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "course" in data
    # Citation-First gate
    assert "citations" in data["course"]
    for c in data["course"]["citations"]:
        assert set(c.keys()) >= {"page", "source", "chunk_id"}

```

## Kiểm tra No-hallucination / Traceability
- Với mỗi output chính (course, summary, flashcards), chạy retriever trên `chunk_id` trong `citations` và verify nội dung trả về chứa văn bản tương ứng.
- Nếu retriever không trả về chunk phù hợp, test phải fail.

## CI (GitHub Actions) — gợi ý workflow

```yaml
name: CI Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r src/backend/requirements.txt
      - name: Run tests
        run: |
          cd src/backend
          pytest -q

```

## Test data & Fixtures
- Cung cấp fixtures cho: small PDF sample, sample DOCX, sample text file.
- Mock external calls (OpenAI/Gemini/Milvus) trong unit/integration bằng fixtures hoặc bằng test doubles.

## Chấm dứt & Báo cáo
- Nếu CI fail: tạo issue tự động + block merge.
- QA Lead đánh giá lỗi: severity/priority, assign cho dev tương ứng.

## Hướng dẫn chạy local

```bash
# trong workspace root
cd src/backend
# kích hoạt venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
pytest -q
```

## Liên kết tài liệu
- Xem spec API tại [docs/api_contract.md](docs/api_contract.md)
- Quy tắc agent tại [AGENTS.md](AGENTS.md)

---
Document tạo bởi QA Lead — chứa các bước kiểm thử tự động và gates bắt buộc.
