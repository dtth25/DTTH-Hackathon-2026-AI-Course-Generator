# Architecture & Data Flow Design

## 1. System Topology (Mối liên kết giữa các thành phần)

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT TIER                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Next.js 14+ (App Router)                 │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │  │
│  │  │  Upload Panel│  │  Course Panel│  │  Resource Panel  │   │  │
│  │  │  (File Drop) │  │  (Lesson View)│  │  (Flashcard/     │   │  │
│  │  │              │  │              │  │   Mindmap/Quiz)  │   │  │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │  │
│  │         │                 │                    │              │  │
│  │         └─────────────────┴────────────────────┘              │  │
│  │                            │                                  │  │
│  │                     fetch() / axios                           │  │
│  └────────────────────────────┼──────────────────────────────────┘  │
└───────────────────────────────┼────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          API TIER (FastAPI)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     FastAPI Application                       │  │
│  │                                                              │  │
│  │  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │  /api/upload    │  │/api/generate- │  │  /api/generate-│  │  │
│  │  │  (POST)         │  │course (POST)  │  │  resource      │  │  │
│  │  └────────┬────────┘  └──────┬───────┘  │  (POST)        │  │  │
│  │           │                  │           └────────────────┘  │  │
│  │           ▼                  ▼                               │  │
│  │  ┌──────────────────────────────────────────┐                │  │
│  │  │        Document Processor Service         │               │  │
│  │  │  (PyMuPDF + python-docx + built-in txt)   │               │  │
│  │  └──────────────────┬───────────────────────┘                │  │
│  │                     │                                         │  │
│  │                     ▼                                         │  │
│  │  ┌──────────────────────────────────────────┐                │  │
│  │  │          Chunking Engine                  │                │  │
│  │  │  (Semantic: theo Abstract/Heading/Para)   │               │  │
│  │  │  overlap: 20% giữa các chunk             │               │  │
│  │  └──────────────────┬───────────────────────┘                │  │
│  │                     │                                         │  │
│  │                     ▼                                         │  │
│  │  ┌──────────────────────────────────────────┐                │  │
│  │  │         Embedding Service                 │               │  │
│  │  │  (OpenAI text-embedding-3-small / 1536d)  │               │  │
│  │  └──────────────────┬───────────────────────┘                │  │
│  └─────────────────────┼────────────────────────────────────────┘  │
└────────────────────────┼───────────────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Milvus     │ │     Zep      │ │    LLM API   │
│  (Vector DB) │ │  (Memory)    │ │(Claude/GPT-4)│
│              │ │              │ │              │
│ collections: │ │ sessions:    │ │ prompt:      │
│  - chunks    │ │  - context   │ │  + context   │
│  - citations │ │  - history   │ │  + citations │
│              │ │  - pref      │ │  + format    │
└──────────────┘ └──────────────┘ └──────────────┘
```

## 2. RAG Pipeline (Luồng xử lý chi tiết)

### Step 1: Ingestion (Xử lý tài liệu)
| Loại file | Library | Output |
|-----------|---------|--------|
| PDF | PyMuPDF (fitz) | raw_text + page_numbers + tables (nếu có) |
| DOCX | python-docx | raw_text + heading hierarchy |
| TXT | built-in open() | raw_text |

- Tất cả text được normalize: loại bỏ extra whitespace, unicode normalize.
- Metadata gắn liền: `{source_file, page_number, total_pages, file_type}`.

### Step 2: Chunking Strategy
**Phương pháp: Semantic Chunking (không phải fixed-size)**

```
Tài liệu gốc
    │
    ├── Abstract / Section Heading ───────────── chunk_1 (page 1)
    │       ├── Paragraph 1.1                      
    │       └── Paragraph 1.2                      chunk_1 (tiếp)
    │
    ├── Section 2 Heading ───────────────────── chunk_2 (page 2-3)
    │       ├── Subsection 2.1 Heading ───────── chunk_2a (page 2)
    │       │     └── Nội dung                   
    │       └── Subsection 2.2                  
    │
    └── ...
```

- **Min chunk:** 100 tokens (tránh chunk quá ngắn).
- **Max chunk:** 1000 tokens (tránh mất ngữ cảnh).
- **Overlap:** 20% giữa các chunk liền kề.
- **Metadata mỗi chunk:** `{chunk_id, page_range, heading_path, source_file, token_count}`.

### Step 3: Embedding
- **Model:** `text-embedding-3-small` (OpenAI) — 1536 dimensions.
  - Lý do: Chi phí thấp, tốc độ cao, đủ quality cho retrieval.
  - Fallback: `text-embedding-3-large` nếu cần accuracy cao hơn.
- **Batch size:** 20 chunks / request (tránh rate limit).
- **Cache:** Embedding được cache locally (file `.embedding_cache/`) để tránh re-embed khi re-run.

### Step 4: Vector Storage (Milvus)
- **Collection:** `course_chunks`
  - Fields: `id` (int64), `vector` (float_vector[1536]), `text` (varchar), `metadata` (json), `page` (int64), `source` (varchar).
  - Index type: `IVF_FLAT` (tốc độ / accuracy balance).
  - Metric type: `IP` (Inner Product — tối ưu cho OpenAI embeddings).
- **Hybrid search:** Kết hợp vector similarity + fulltext search (BM25) trên field `text`.
  - Weight: vector 0.7, fulltext 0.3 (tuning parameter).
  - Top-K: 10 chunks (có thể điều chỉnh).
- **Citation tracking:**
  - Kết quả retrieval luôn kèm `{chunk_id, page, source_file, score}`.
  - Các chunk này sẽ được inject vào LLM prompt để đảm bảo citation chính xác.

### Step 5: Memory Layer (Zep)
- **Mục đích:** Lưu ngữ cảnh phiên làm việc của user.
- **Session key:** `session_id` (tạo random khi load trang, vì No-Auth).
- **Dữ liệu lưu:**
  - File đã upload (`file_id`, `filename`).
  - Lịch sử conversation (prompts + responses).
  - User preferences (nếu có, vd: độ dài tóm tắt).
- **TTL:** 24 giờ (tự động xoá sau 1 ngày).

### Step 6: Generation (LLM)
- **Model:** Claude 3.5 Sonnet (ưu tiên) hoặc GPT-4o.
- **Prompt template structure:**
  ```
  System: Bạn là trợ lý tạo khóa học. Dựa vào context dưới đây, hãy tạo nội dung.
          LUÔN LUÔN trích dẫn số trang và nguồn trong [].
          KHÔNG được thêm thông tin không có trong context.
  Context: [top-K chunks từ Milvus + metadata]
  User prompt: [người dùng nhập]
  Output format: JSON strict (theo API contract)
  ```
- **Citation injection:**
  ```json
  "citations": [
    {"page": 5, "source": "physics_textbook.pdf", "chunk_id": "chunk_42"},
    {"page": 7, "source": "physics_textbook.pdf", "chunk_id": "chunk_58"}
  ]
  ```

## 3. API Flow Mapping

| Endpoint | Flow |
|----------|------|
| `POST /api/upload` | File validation → PyMuPDF/docx/txt parse → Chunk → Embed → Milvus insert → return `file_id` |
| `POST /api/generate-course` | Nhận `file_id` + `user_prompt` → Query Milvus (hybrid search) → Lấy Zep context → Build prompt → Call LLM → Parse response → Attach citations → Return |
| `POST /api/generate-resource` | Tương tự generate-course nhưng output format khác (flashcard/mindmap/quiz) |

## 4. Key Design Decisions & Rationale

| Decision | Option chọn | Lý do |
|----------|-------------|-------|
| Semantic chunking (không fixed-size) | Theo heading/paragraph | Tài liệu học tập có cấu trúc rõ ràng; chunk theo heading giữ đúng ngữ cảnh logic |
| Milvus hybrid search | vector (0.7) + fulltext (0.3) | Fulltext BM25 bắt chính xác keyword, vector bắt semantic; kết hợp để recall > 90% |
| Zep cho memory (không Redis thuần) | Zep | Hỗ trợ sẵn session management + TTL + persistent; tiết kiệm code |
| OpenAI embedding (không open-source) | text-embedding-3-small | Chi phí thấp, quality cao, dễ integrate; không cần self-host model |
| JSON strict output (không markdown) | JSON schema trong prompt | Dễ parse ở Frontend, giảm hallucination format |

## 5. Error Handling & Retry Policy

| Error type | Strategy |
|------------|----------|
| File parse fail (corrupt PDF) | Return 400 + error message "File không thể đọc được" |
| Milvus connection fail | Retry 3 lần (exponential backoff: 1s, 2s, 4s) → timeout 10s |
| LLM API fail (rate limit) | Retry 2 lần + jitter 2-5s → return 503 nếu vẫn fail |
| Embedding fail | Retry 1 lần → skip chunk (log warning) |
| Invalid file type | Return 400 ngay lập tức (không vào pipeline) |