# API Contract

Contract này bám theo routes hiện tại trong `src/backend/main.py`.

Product surface hiện tại là **Document-to-Study-Pack**: user upload tài liệu và xem một dashboard học tập kết nối 4 học liệu cốt lõi: Book (Study Guide PDF), Slide, Quiz, Vid và grounding. Public generation endpoints là **Book/Study Guide, Slide, Quiz, Vid**.

## 1. Health & Management

### Auth & Admin

Auth supports Bearer JWT and an HttpOnly cookie named `agy_session` for browser flows. Upload, dashboard, generation, output, job, and delete endpoints require an active user unless explicitly marked as health or public demo.

- `POST /api/auth/register`, `/verify-email`, `/resend-verification`, `/forgot-password`, `/reset-password`, `/login`, and `/logout` implement account lifecycle and session creation/clear.
- `GET /api/auth/me` returns the current public user profile; `DELETE /api/auth/me` deletes the caller's account. Neither exposes `password_hash`.
- Admin routes are exactly `GET /api/admin/users` and `GET /api/admin/provider-health`; both require `require_admin`.

- `GET /health`: readiness endpoint cho frontend proxy. Không gọi AI warm-up. Response gồm `status`, `ready`, `details.upload_dir`, `details.output_dir`, `details.vector_db`, `details.config_loaded`, `vector_db_provider`, `vector_db_ready`, `chroma_persist_dir`, `chroma_collection_name`, `startup_duration_seconds`, `error`. Với `VECTOR_DB_PROVIDER=chroma`, nếu Chroma thiếu hoặc không initialize được thì `vector_db_ready=false` và không fallback sang simple/local store.
- `GET /api/health`: trả trạng thái backend và danh sách `course_id`.
- `GET /api/courses/all`: trả danh sách course kèm metadata local.
- `POST /api/courses`: tạo course thủ công; `PATCH /api/courses/{course_id}` đổi tên; `DELETE /api/courses/{course_id}` xóa course và local upload storage mà app quản lý.

### `GET /api/admin/provider-health`

Admin-only cached OpenRouter preflight. It is not part of `/health` readiness and it never returns a key, key hash, bearer token, raw provider response, or technical diagnostic. Query `force=true` bypasses the short cache.

```json
{
  "available": true,
  "error_code": null,
  "checked_at": "2026-09-02T12:00:00Z",
  "limit": 10,
  "limit_remaining": 5.5,
  "limit_reset": "monthly",
  "content_model_available": true,
  "embedding_model_available": true
}
```

`error_code` in this admin diagnostic is an internal operational code; it is not a frontend/user error contract. The public document and artifact APIs expose only the provider-neutral `AI_*` codes listed below.

## 2. Upload & Status

### `POST /api/upload`

Input: `multipart/form-data`.

Supported fields:
- `files`: một hoặc nhiều file PDF, DOCX, TXT.
- `files[]`: compatibility spelling for `files`.

Validation:
- filename required.
- extension phải là `.pdf`, `.docx`, `.txt`.
- file không rỗng.
- mỗi file size <= 50MB.
- tối đa 5 file mỗi request.

Response:

```json
{
  "course_id": "abc123def456",
  "document_id": "a-separate-upload-id",
  "filenames": ["intro.pdf", "exercise.docx"],
  "file_count": 2,
  "status": "processing",
  "message": "Đã nhận 2 file và đang phân tích...",
  "job_id": "uuid"
}
```

`course_id` is the identifier used by polling, retry, outputs, and ownership checks. Save `job_id` as well when a client needs the durable preprocess-job envelope.

### `GET /api/course/{course_id}/status`

```json
{
  "course_id": "abc123def456",
  "status": "ready",
  "stage": "completed",
  "progress": 100,
  "message": "Tài liệu đã sẵn sàng.",
  "filenames": ["intro.pdf", "exercise.docx"],
  "file_count": 2,
  "error": null,
  "error_code": null,
  "failure_stage": null,
  "can_retry": false,
  "recommended_action": null,
  "job_id": "uuid"
}
```

The canonical polling endpoint above has an alias at `GET /api/courses/{course_id}/status`. Relevant course states are `processing`, `ready`, `failed`, and `paused_due_to_quota`. A quota/key-capacity failure uses `paused_due_to_quota`; it is not a scan/PDF diagnosis.

When preprocessing fails, the endpoint returns a safe structured failure envelope:

```json
{
  "course_id": "abc123def456",
  "status": "paused_due_to_quota",
  "stage": "failed",
  "failure_stage": "embedding_failed",
  "progress": 0,
  "message": "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
  "error": "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
  "can_retry": true,
  "recommended_action": "restore_provider_quota",
  "error_code": "AI_QUOTA_EXHAUSTED",
  "job_id": "uuid"
}
```

`can_retry` tells the UI that retry is permitted after the recommended operator/user action. Supported actions are `restore_provider_quota`, `retry_later`, `contact_admin`, and `upload_clearer_pdf`. `technical_error` is retained only on the server for logs/admin diagnosis; it is never returned to regular users in course, job, or artifact responses.

Public `error_code` values are closed and provider-neutral: `AI_CONFIGURATION_ERROR`, `AI_ACCESS_DENIED`, `AI_QUOTA_EXHAUSTED`, `AI_RATE_LIMITED`, `AI_UNAVAILABLE`, `AI_TIMEOUT`, `AI_REQUEST_FAILED`, `DOCUMENT_TEXT_EXTRACTION_FAILED`, `DOCUMENT_SCHEDULING_FAILED`, `DOCUMENT_PROCESSING_FAILED`, `DOCUMENT_PROCESSING_PERSISTENCE_FAILED`, `DOCUMENT_PROCESSING_CANCELLED`, `INLINE_PROCESSING_INTERRUPTED`, `ARTIFACT_SOURCE_UNAVAILABLE`, `BOOK_GENERATION_FAILED`, `SLIDE_GENERATION_FAILED`, `QUIZ_GENERATION_FAILED`, and `VIDEO_GENERATION_FAILED`. Clients must not branch on raw `OPENROUTER_*` codes or provider text.

### `POST /api/documents/{course_id}/retry`

Retries preprocessing from the saved upload file without requiring a second upload. It is accepted only while the same owned course is `failed` or `paused_due_to_quota`; active/ready courses return `409`, a missing saved source returns `409`, and another user receives `404`. An administrator may retry for support, while the resulting job remains owned by the course owner.

```json
{
  "document_id": "abc123def456",
  "status": "processing",
  "stage": "extracting",
  "progress": 0,
  "message": "Đang thử lại xử lý tài liệu từ tệp đã tải lên.",
  "job_id": "uuid"
}
```

### `GET /documents/{document_id}/sources`

Stable source-grounding endpoint for UI panels. `GET /api/documents/{document_id}/sources` is also available.

Query:
- `ids`: optional comma-separated `source_chunk_ids` generated by Study Pack outputs.
- `developer`: optional boolean. Defaults to `false`; when `true` and the requester is admin, response may include internal `source_chunk_id` for debugging.

Public response hides internal chunk ids by default and returns clean excerpts only:

```json
{
  "document_id": "abc123def456",
  "total_source_chunks": 12,
  "matched_source_chunks": 2,
  "sources": [
    {
      "page": 3,
      "excerpt": "Short cleaned source excerpt..."
    }
  ]
}
```

The frontend should show `page` and `excerpt` to users. `source_chunk_id` must only be displayed when developer mode is explicitly enabled.

### `GET /api/jobs/{job_id}`

Durable preprocess-job metadata endpoint. The owner (or an administrator) may read it; another user receives `404`. Current local/dev execution is inline `BackgroundTasks`, while the stored schema is intentionally compatible with a future durable worker.

```json
{
  "id": "uuid",
  "document_id": "abc123def456",
  "user_id": "uuid",
  "job_type": "preprocess",
  "status": "queued",
  "progress": 0,
  "message": "Đang chờ xử lý",
  "error": null,
  "error_code": null,
  "created_at": "2026-09-02T12:00:00",
  "updated_at": "2026-09-02T12:00:00",
  "completed_at": null
}
```

## 3. Generation and Saved Artifacts

All generation endpoints require an owned, non-deleted course and return a queued `GenerateResponse` with `course_id`, `status`, `message`, `estimated_time`, and `version_id`. Content is fetched from its artifact endpoint after processing; a generation request does not return a completed book, slide deck, quiz, or video inline.

- `POST /api/generate-book`: body/query fields `course_id`, `user_prompt`, `detail_level`, `retry_version_id`.
- `POST /api/generate-slide`: `course_id`, `topic`, `mode`, `focus_prompt`, `retry_version_id`.
- `POST /api/generate-quiz`: `course_id`, `topic`, `quantity`, `difficulty`, `retry_version_id`.
- `POST /api/generate-vid`: `course_id`, `topic`, `format`, `voice`, `user_prompt`, `retry_version_id`.

Artifact status endpoints are `GET /api/course/{course_id}/book`, `/slide`, `/quiz`, and `/vid`; each also has the equivalent `/api/courses/{course_id}/...` path. Their envelope has `status`, `error`, `error_code`, `progress`, `data`, `version_id`, `active_version`, and `versions`. `status` is exactly `empty`, `processing`, `ready`, or `error`; terminal failures use `error`, never `failed`. Public artifact errors use the same provider-neutral code boundary and never return `technical_error`.

Downloads are `GET /api/course/{course_id}/book.pdf`, `/slide.pptx`, `/slide.pdf`, `/slide-images/{slide_num}`, `/quiz-key.pdf`, and `/vid.mp4`, with matching `/api/courses/{course_id}/...` aliases. Artifact-version management is only under the singular path: `PATCH` or `DELETE /api/course/{course_id}/artifacts/{artifact}/versions/{version_id}`.

## 4. Study Pack

### `GET /api/course/{course_id}/study-pack`

Returns the connected document dashboard. This endpoint does not create a separate AI output; it reads saved Study Guide/book, slide, quiz, vid and course stats, then derives dashboard-ready readiness and quality scores from the same structured source.

```json
{
  "course_id": "abc123def456",
  "stats": {},
  "study_pack": {
    "title": "string",
    "book": {},
    "slides": [],
    "quiz": [],
    "vid": {},
    "readiness": {
      "study_guide_pdf": true,
      "slides": true,
      "quiz": true,
      "vid": true
    },
    "quality_scores": {
      "study_guide_pdf": 90,
      "slides": 88,
      "quiz": 92,
      "vid": 89
    },
    "grounding": {
      "num_chunks": 120,
      "quality_score": 85,
      "warnings": []
    }
  }
}
```

## 5. Deprecated Surface

Các route output cũ không còn là public API và phải trả 404 nếu gọi:
- `/api/chat`
- `/api/custom-prompt`
- `/api/generate-course`
- `/api/generate-summary`
- `/api/generate-flashcards`
- `/api/generate-mindmap`
- `/api/generate-podcast/{course_id}`
- `/api/generate-study-guide/{course_id}`
- mọi async generation route cũ
