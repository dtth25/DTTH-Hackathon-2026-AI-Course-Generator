# API Contract (Current Implementation)

This contract follows the routes currently declared in `src/backend/main.py`.

## 1. Health & Management

### `GET /api/health`
Returns backend health and registered courses.

```json
{
  "status": "ok",
  "course_id": null,
  "courses": ["abc123"]
}
```

### `GET /api/courses`
Returns registered course IDs.

### `GET /api/courses/all`
Returns course IDs with available local metadata.

### `DELETE /api/courses/{course_id}`
Deletes a course from cache, local generated files and FAISS index.

## 2. Upload & Status

### `POST /api/upload`

Input: `multipart/form-data` with one field:
- `file`: PDF, DOCX or TXT

Validation:
- filename required
- extension must be `.pdf`, `.docx`, `.txt`
- file must not be empty
- file size must be <= 50MB

Response:

```json
{
  "course_id": "abc123def456",
  "filename": "document.pdf",
  "status": "processing",
  "message": "File 'document.pdf' đã được nhận và đang được phân tích. ID khóa học: abc123def456"
}
```

### `GET /api/course/{course_id}/status`

```json
{
  "course_id": "abc123def456",
  "status": "ready",
  "pdf_path": "uploads/..."
}
```

Possible statuses include `pending`, `ready`, `failed`, `unknown`.

## 3. Chat

### `POST /api/chat`

Request:

```json
{
  "course_id": "abc123def456",
  "question": "Tóm tắt chương chính của tài liệu"
}
```

Response:

```json
{
  "answer": "string",
  "course_id": "abc123def456",
  "citations": [
    {"page": 1, "source": "document.pdf", "chunk_id": 0}
  ]
}
```

## 4. Generation - Sync

All sync generation endpoints require an existing ready course and return `citations` when they generate AI content.

### `POST /api/generate-course`

Request:

```json
{
  "course_id": "abc123def456",
  "user_prompt": "Tạo khóa học nhập môn",
  "target_audience": "sinh viên"
}
```

Response:

```json
{
  "course_id": "abc123def456",
  "course": {},
  "citations": [
    {"page": 1, "source": "document.pdf", "chunk_id": 0}
  ]
}
```

### `POST /api/generate-summary`

Request:

```json
{
  "course_id": "abc123def456",
  "type": "detailed"
}
```

Response fields: `course_id`, `filename`, `summary`, `citations`.

### `POST /api/generate-flashcards`

Request:

```json
{
  "course_id": "abc123def456",
  "count": 20
}
```

Response fields: `course_id`, `total`, `flashcards`, `citations`.

### `POST /api/generate-quiz`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "Cơ học",
  "quantity": 20,
  "difficulty": "medium"
}
```

Response fields: `course_id`, `topic`, `difficulty`, `total_questions`, `questions`, `citations`.

### `POST /api/generate-slides`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "Cơ học",
  "num_slides": 10
}
```

Response: Returns `text/html` — a self-contained Reveal.js HTML presentation with citation footers, hero title slide, two-column content layout with images, and bullet-by-bullet fragment animations.

Async version (`POST /api/generate-slides-async`) stores the same HTML string as task result.

### `POST /api/generate-mindmap`

Request:

```json
{
  "course_id": "abc123def456",
  "max_depth": 3
}
```

Response fields: `course_id`, `mindmap`, `citations`.

### `POST /api/custom-prompt`

Request:

```json
{
  "course_id": "abc123def456",
  "prompt": "Tóm tắt tài liệu này trong 5 ý chính"
}
```

Response fields: `course_id`, `prompt`, `prompt_type`, `result`, `citations`.

### Path-style sync endpoints

These endpoints currently use `course_id` in the path:
- `POST /api/generate-podcast/{course_id}`
- `POST /api/generate-study-guide/{course_id}`

## 5. Generation - Async

Async endpoints create a background task and return:

```json
{
  "task_id": "task123",
  "status": "processing"
}
```

Current async endpoints:
- `POST /api/generate-course-async`
- `POST /api/generate-summary-async`
- `POST /api/generate-flashcards-async`
- `POST /api/generate-quiz-async`
- `POST /api/generate-slides-async`
- `POST /api/generate-mindmap-async`
- `POST /api/custom-prompt-async/{course_id}`
- `POST /api/generate-podcast-async/{course_id}`
- `POST /api/generate-study-guide-async/{course_id}`

### `GET /api/task/{task_id}`

Returns task status, result when completed, or error when failed.

## 6. Saved Content

Current saved-content endpoints:
- `GET /api/course/{course_id}/questions`
- `GET /api/course/{course_id}/syllabus`
- `GET /api/course/{course_id}/slides`
- `GET /api/course/{course_id}/audio`
- `GET /api/course/{course_id}/study-guide`
- `GET /api/course/{course_id}/summary`
- `GET /api/course/{course_id}/flashcards`
- `GET /api/course/{course_id}/mindmap`
- `GET /api/course/{course_id}/files`
- `GET /api/course/{course_id}/stats`

## 7. Frontend Integration Warning

Backend `/api/upload` currently accepts one multipart field named `file`. The current frontend upload helper sends `files`, so the upload integration must be fixed in a separate frontend/backend integration PR.
