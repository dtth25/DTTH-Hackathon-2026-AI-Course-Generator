# API Contract

Contract này bám theo routes hiện tại trong `src/backend/main.py`.

Product surface hiện tại là **Document-to-Study-Pack**: user upload tài liệu và xem một dashboard học tập kết nối 4 học liệu cốt lõi: Book (Study Guide PDF), Slide, Quiz, Vid và grounding. Public generation endpoints là **Book/Study Guide, Slide, Quiz, Vid**.

## 1. Health & Management

### Auth & Admin

Auth supports Bearer JWT and an HttpOnly cookie named `agy_session` for browser flows. Upload, dashboard, generation, output, job, and delete endpoints require an active user unless explicitly marked as health or public demo.

- `POST /api/auth/register`: create a user. Email is lowercased and unique. Password is hashed with bcrypt. Default role is `user`.
- `POST /api/auth/login`: return `{ access_token, token_type, user }` and set the auth cookie.
- `POST /api/auth/logout`: clear the auth cookie.
- `GET /api/auth/me`: return the current public user profile. Response never contains `password_hash`.
- Admin endpoints require `require_admin`: `GET /api/admin/users`, `GET /api/admin/users/{user_id}`, `PATCH /api/admin/users/{user_id}`, `POST /api/admin/users/{user_id}/disable`, `POST /api/admin/users/{user_id}/enable`, `POST /api/admin/users/{user_id}/make-admin`, `POST /api/admin/users/{user_id}/make-user`, `DELETE /api/admin/users/{user_id}`, `POST /api/admin/users/{user_id}/reset-password`.
- Disabled users cannot login/use protected APIs; backend prevents deleting, disabling, or demoting the last active admin.
- First admin bootstrap uses `CREATE_DEFAULT_ADMIN=true`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and only creates an admin if no admin exists. The password is never logged.

- `GET /health`: readiness endpoint cho frontend proxy. Không gọi AI warm-up. Response gồm `status`, `ready`, `details.upload_dir`, `details.output_dir`, `details.vector_db`, `details.config_loaded`, `vector_db_provider`, `vector_db_ready`, `chroma_persist_dir`, `chroma_collection_name`, `startup_duration_seconds`, `error`. Với `VECTOR_DB_PROVIDER=chroma`, nếu Chroma thiếu hoặc không initialize được thì `vector_db_ready=false` và không fallback sang simple/local store.
- Health response có thể kèm `storage_provider`, `storage_ready`, `job_queue_provider`, `job_queue_ready`, `cache_provider`, `cache_ready` để chuẩn bị production provider switch.
- `GET /api/health`: trả trạng thái backend và danh sách `course_id`.
- `GET /api/courses`: trả danh sách `course_id` đã đăng ký.
- `GET /api/courses/all`: trả danh sách course kèm metadata local.
- `DELETE /api/courses/{course_id}`: xóa course khỏi cache, generated files và vector DB.
- `DELETE /api/documents/{document_id}` hoặc `DELETE /documents/{document_id}`: xóa document, upload file, vector entries, generated outputs và cache hash do ứng dụng quản lý khi có thể. Endpoint yêu cầu user sở hữu document, trừ admin.

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
  "progress": 30,
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

## 3. Generation

Tất cả generation endpoints yêu cầu course ở trạng thái `ready`. Response public không trả `page`, `source`, `chunk_id` hoặc `citations`.

### `POST /api/generate-book`

Request:

```json
{
  "course_id": "abc123def456",
  "user_prompt": "Tập trung vào phần nhập môn",
  "target_audience": "sinh viên"
}
```

Response:

```json
{
  "course_id": "abc123def456",
  "book": {
    "title": "string",
    "description": "string",
    "estimated_duration": "3-5 giờ",
    "chapters": []
  },
  "pdf_url": "/api/course/abc123def456/book.pdf"
}
```

### `POST /api/generate-slide`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "Cơ học",
  "num_slides": 8
}
```

Response fields: `course_id`, `topic`, `total_slides`, `slides`, `pptx_url`.

`slides[]` public fields:
- `slide_number`: sequential slide number.
- `title`: slide title.
- `layout_type` (optional): `default`, `two_column`, or `quote`.
- `bullet_points`: concise bullet points on the slide.
- `source_chunk_ids`: internal grounding chunk ids (not shown raw to end users).

Note: teaching/speaker notes and graphic-design hints are intentionally NOT part of the slide output — slides are rendered as clean 16:9 artifacts with no meta-instruction text.

### `POST /api/generate-quiz`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "Cơ học",
  "quantity": 10,
  "difficulty": "medium"
}
```

Response fields: `course_id`, `topic`, `difficulty`, `total_questions`, `questions`, `answer_key_url`.

`questions[]` public fields:
- `question_type` (optional): `concept`, `application`, `formula`, `scenario`, or similar.
- `question`: question text.
- `options`: answer options.
- `correct`: zero-based index for internal UI scoring and answer-key export.
- `explanation`: teaching explanation, shown only after user review/submission in UI.
- `difficulty` (optional): normalized difficulty label.

### `POST /api/generate-vid`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "tổng quan",
  "duration_minutes": 3,
  "learning_mode": "normal",
  "video_renderer": "simple_templates",
  "allow_renderer_fallback": true
}
```

Optional:
- `learning_mode`: `normal` hoặc `high_yield`.
- `video_renderer`: `simple_templates` hoặc `manim`. `simple_slides` cũ vẫn được backend nhận như alias tương thích. Nếu `manim` chưa khả dụng và `allow_renderer_fallback = true`, backend fallback sang renderer thường và trả `vid.renderer_message`.
- `allow_renderer_fallback`: mặc định `true`.

Response fields: `course_id`, `vid`. Khi tạo thành công, `vid.status = "ready"` và `vid.url` trỏ tới `/api/course/{course_id}/vid/file`. Khi render lỗi hoặc storyboard không đạt quality gate, `vid.status = "failed"` và có lỗi thân thiện trong `vid.error`.

`vid.scenes[]` public fields: `scene_index`, `scene_type`, `title`, `key_message`, `screen_text`, `voiceover`, `visual_template`, `visual_data`, `duration_seconds`, `animation_notes`, `source_chunk_ids`.

Metadata video có thể gồm: `quality_report`, `transcript`, `subtitles_srt`, `quick_quiz`, `videos`, `playlist_plan`, `progress_states`, `renderer`, `renderer_message`, `debug_log`. `debug_log` là log rút gọn, không trả full FFmpeg stderr.

## 4. Saved Artifacts

- `GET /api/course/{course_id}/book`
- `GET /api/course/{course_id}/book.pdf`
- `GET /api/course/{course_id}/slide`
- `GET /api/course/{course_id}/slide.pptx`
- `GET /api/course/{course_id}/slide.pdf`
- `GET /api/course/{course_id}/quiz`
- `GET /api/course/{course_id}/quiz-key.pdf`
- `GET /api/course/{course_id}/vid`
- `GET /api/course/{course_id}/vid/file`
- `GET /api/course/{course_id}/files`
- `GET /api/course/{course_id}/stats`
- `GET /api/course/{course_id}/study-pack`

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
