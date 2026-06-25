# API Contract

Contract này bám theo routes hiện tại trong `src/backend/main.py`. Public generation chỉ có **Book, Slide, Quiz, Vid**.

## 1. Health & Management

- `GET /api/health`: trả trạng thái backend và danh sách `course_id`.
- `GET /api/courses`: trả danh sách `course_id` đã đăng ký.
- `GET /api/courses/all`: trả danh sách course kèm metadata local.
- `DELETE /api/courses/{course_id}`: xóa course khỏi cache, generated files và FAISS index.

## 2. Upload & Status

### `POST /api/upload`

Input: `multipart/form-data`.

Supported fields:
- `files`: một hoặc nhiều file PDF, DOCX, TXT.
- `file`: legacy single-file field, vẫn được hỗ trợ để tránh vỡ client cũ.

Validation:
- filename required.
- extension phải là `.pdf`, `.docx`, `.txt`.
- file không rỗng.
- mỗi file size <= 50MB.

Response:

```json
{
  "course_id": "abc123def456",
  "filename": "2 files",
  "filenames": ["intro.pdf", "exercise.docx"],
  "file_count": 2,
  "status": "processing",
  "message": "Đã nhận 2 file và đang phân tích tài liệu. ID tài liệu: abc123def456"
}
```

### `GET /api/course/{course_id}/status`

```json
{
  "course_id": "abc123def456",
  "status": "ready",
  "filenames": ["intro.pdf", "exercise.docx"],
  "file_count": 2
}
```

Possible statuses: `pending`, `processing`, `ready`, `failed`, `unknown`.

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

Response fields: `course_id`, `topic`, `total_slides`, `slides`, `json_url`, `pdf_url`.

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

Response fields: `course_id`, `topic`, `difficulty`, `total_questions`, `questions`, `json_url`, `pdf_url`.

### `POST /api/generate-vid`

Request:

```json
{
  "course_id": "abc123def456",
  "topic": "tổng quan",
  "duration_minutes": 3
}
```

Response fields: `course_id`, `vid`. Khi tạo thành công, `vid.status = "ready"` và `vid.url` trỏ tới `/api/course/{course_id}/vid/file`. Khi render lỗi, `vid.status = "failed"` và có `vid.error`.

## 4. Saved Artifacts

- `GET /api/course/{course_id}/book`
- `GET /api/course/{course_id}/book.pdf`
- `GET /api/course/{course_id}/slide`
- `GET /api/course/{course_id}/slide.json`
- `GET /api/course/{course_id}/slide.pdf`
- `GET /api/course/{course_id}/quiz`
- `GET /api/course/{course_id}/quiz.json`
- `GET /api/course/{course_id}/quiz.pdf`
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
