# API Contract

Contract này bám theo routes hiện tại trong `src/backend/main.py`. Public generation chỉ có **Book, Slide, Quiz, Vid**.

## 1. Health & Management

### `GET /api/health`

```json
{
  "status": "ok",
  "course_id": null,
  "courses": ["abc123"]
}
```

### `GET /api/courses`
Trả danh sách `course_id` đã đăng ký.

### `GET /api/courses/all`
Trả danh sách course kèm metadata local.

### `DELETE /api/courses/{course_id}`
Xóa course khỏi cache, generated files và FAISS index.

## 2. Upload & Status

### `POST /api/upload`

Input: `multipart/form-data` với đúng một field:
- `file`: PDF, DOCX hoặc TXT

Validation:
- filename required
- extension phải là `.pdf`, `.docx`, `.txt`
- file không rỗng
- file size <= 50MB

Response:

```json
{
  "course_id": "abc123def456",
  "filename": "document.pdf",
  "status": "processing",
  "message": "File 'document.pdf' đã được nhận và đang được phân tích. ID tài liệu: abc123def456"
}
```

### `GET /api/course/{course_id}/status`

```json
{
  "course_id": "abc123def456",
  "status": "ready"
}
```

Possible statuses: `pending`, `ready`, `failed`, `unknown`.

## 3. Generation

Tất cả generation endpoints yêu cầu course ở trạng thái `ready`. Response public không trả `page`, `source`, `chunk_id`.

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

Response fields: `course_id`, `topic`, `total_slides`, `slides`.

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

Response fields: `course_id`, `topic`, `difficulty`, `total_questions`, `questions`.

### `POST /api/generate-vid`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "tổng quan",
  "duration_minutes": 3
}
```

Response fields: `course_id`, `vid`. `vid.url` trỏ tới `/api/course/{course_id}/vid/file`.

## 4. Saved Artifacts

- `GET /api/course/{course_id}/book`
- `GET /api/course/{course_id}/book.pdf`
- `GET /api/course/{course_id}/slide`
- `GET /api/course/{course_id}/quiz`
- `GET /api/course/{course_id}/vid`
- `GET /api/course/{course_id}/vid/file`
- `GET /api/course/{course_id}/files`
- `GET /api/course/{course_id}/stats`

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
