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

1. Frontend gửi `POST /api/upload` với multipart field `files` cho một hoặc nhiều tài liệu.
2. Backend vẫn hỗ trợ legacy field `file` cho single-file client cũ.
3. Backend validate extension, empty file và size <= 50MB mỗi file.
4. Backend lưu files vào `uploads/{course_id}/`, tạo `course_id`, ghi metadata vào `questions/course_{course_id}_meta.json`.
5. Background thread parse text từng tài liệu bằng document processor.
6. Text được chunk, embed bằng Gemini embeddings và lưu vào một FAISS local index chung cho `course_id`.
7. Khi index sẵn sàng, status chuyển thành `ready`.

## 3. Generation Flow

```text
course_id
  -> load FAISS vectorstore
  -> retrieve top-k chunks from the full corpus
  -> clean internal extraction markers
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

FAISS metadata vẫn được giữ nội bộ cho retrieval/debug, nhưng public response không trả `page`, `source`, `chunk_id`, `citations`.

## 4. Backend Modules

| Module | Responsibility |
| --- | --- |
| `backend.main` | FastAPI routes, validation, response shape |
| `backend.services.course_gen` | Course lifecycle, lazy loading, LRU cache |
| `backend.services.doc_processor` | PDF/DOCX/TXT extraction |
| `backend.services.resource_gen` | Book, Slide, Quiz, Vid generation and artifact export |
| `backend.vector_db.faiss_manager` | FAISS create/load/list/drop |
| `backend.core.prompts` | Prompt templates for 4 outputs |
| `backend.core.config` | Paths, model factories, utility helpers |

## 5. Local Storage

| Path | Purpose |
| --- | --- |
| `uploads/{course_id}/` | Original uploaded files for one corpus |
| `indices/faiss_{course_id}/` | FAISS index |
| `indices/faiss_{course_id}.json` | FAISS metadata |
| `questions/course_{course_id}_meta.json` | Course lifecycle metadata |
| `questions/course_{course_id}_questions.json` | Quiz JSON |
| `questions/course_{course_id}_quiz.pdf` | Quiz PDF |
| `books/course_{course_id}_book.json` | Book JSON |
| `books/course_{course_id}_book.pdf` | Book PDF |
| `slides/course_{course_id}_slides.json` | Slide JSON |
| `slides/course_{course_id}_slides.pdf` | Slide PDF |
| `videos/course_{course_id}/vid.json` | Vid metadata |
| `videos/course_{course_id}/vid.mp4` | Vid MP4 |

## 6. Architecture Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Public outputs | Book, Slide, Quiz, Vid | Hackathon scope rõ, ít phân tán |
| Multi-document | One `course_id` per uploaded corpus | User cần tạo học liệu từ nhiều tài liệu cùng lúc |
| AI boundary | Frontend -> FastAPI -> LLM | Không expose API key ở client |
| Retrieval | FAISS local | Dễ chạy demo, không cần external vector DB |
| Artifact export | JSON + PDF/MP4 where applicable | UI học nhanh, file dễ chia sẻ |
| Public metadata | Không trả page/source/chunk | Product mới không hiển thị source metadata |
| Auth | Không có trong v1 | Tập trung core generation flow |
