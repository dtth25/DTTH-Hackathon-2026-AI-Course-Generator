# Architecture Design

## 1. System Overview

```text
Frontend (Next.js)
  -> FastAPI Backend
  -> Document Processor
  -> FAISS Local Index
  -> ResourceGenerator
  -> Local Generated Artifacts
```

Public product surface chỉ có 4 output:
- Book
- Slide
- Quiz
- Vid

## 2. Upload & Indexing Flow

1. Frontend gửi `POST /api/upload` với multipart field `file`.
2. Backend validate extension, empty file và size <= 50MB.
3. Backend lưu file vào `uploads/`, tạo `course_id`, ghi metadata vào `questions/course_{course_id}_meta.json`.
4. Background thread parse text bằng document processor.
5. Text được chunk, embed bằng Gemini embeddings và lưu vào FAISS local index.
6. Khi index sẵn sàng, status chuyển thành `ready`.

## 3. Generation Flow

```text
course_id
  -> load FAISS vectorstore
  -> retrieve top-k chunks
  -> prompt Gemini
  -> normalize/fallback
  -> save artifact
  -> return public response
```

Resource generation nằm trong `ResourceGenerator`:
- `generate_book`
- `generate_slides_v2`
- `generate_quiz_v2`
- `generate_vid`

FAISS metadata vẫn được giữ nội bộ cho retrieval/debug, nhưng public response không trả `page`, `source`, `chunk_id`.

## 4. Backend Modules

| Module | Responsibility |
| --- | --- |
| `backend.main` | FastAPI routes, validation, response shape |
| `backend.services.course_gen` | Course lifecycle, lazy loading, LRU cache |
| `backend.services.doc_processor` | PDF/DOCX/TXT extraction |
| `backend.services.resource_gen` | Book, Slide, Quiz, Vid generation |
| `backend.vector_db.faiss_manager` | FAISS create/load/list/drop |
| `backend.core.prompts` | Prompt templates for 4 outputs |
| `backend.core.config` | Paths, model factories, utility helpers |

## 5. Local Storage

| Path | Purpose |
| --- | --- |
| `uploads/` | Original uploaded files |
| `indices/faiss_{course_id}/` | FAISS index |
| `indices/faiss_{course_id}.json` | FAISS metadata |
| `questions/course_{course_id}_meta.json` | Course lifecycle metadata |
| `questions/course_{course_id}_questions.json` | Quiz JSON |
| `books/course_{course_id}_book.json` | Book JSON |
| `books/course_{course_id}_book.pdf` | Book PDF |
| `slides/course_{course_id}_slides.json` | Slide JSON |
| `videos/course_{course_id}/vid.json` | Vid metadata |
| `videos/course_{course_id}/vid.mp4` | Vid MP4 |

## 6. Architecture Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Public outputs | Book, Slide, Quiz, Vid | Hackathon scope rõ, ít phân tán |
| AI boundary | Frontend -> FastAPI -> LLM | Không expose API key ở client |
| Retrieval | FAISS local | Dễ chạy demo, không cần external vector DB |
| Book export | JSON + PDF | UI đọc nhanh, PDF dễ chia sẻ |
| Public metadata | Không trả page/source/chunk | Product mới không hiển thị source metadata |
| Auth | Không có trong v1 | Tập trung core generation flow |
