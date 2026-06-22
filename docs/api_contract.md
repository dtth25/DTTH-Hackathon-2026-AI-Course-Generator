# API Contract

## Thông tin chung

- **Base URL**: `http://localhost:8001/api`
- **Server**: FastAPI (Python)
- **CORS**: Cho phép tất cả origins (`*`)
- **Rate Limit**: Tối đa 30 requests/60s/IP (áp dụng toàn cục qua middleware, mọi endpoint đều bị giới hạn)
- **Upload tối đa**: 50MB
- **Async timeout**: Task bất đồng bộ tối đa 5 phút, nếu quá sẽ tự động failed

### Data Models Chung

```json
// ErrorResponse — dùng cho mọi response lỗi (4xx, 5xx)
{
  "error": true,
  "message": "Mô tả lỗi chi tiết",
  "code": "INVALID_FILE_FORMAT",
  "details": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| error | boolean | `true` nếu là lỗi |
| message | string | Mô tả lỗi cho người dùng |
| code | string | Mã lỗi (xem bảng dưới) |
| details | object/null | Chi tiết lỗi (validation errors, stack trace,...) hoặc null |

**Mã lỗi chuẩn**:

| Code | HTTP Status | Ý nghĩa |
|------|-------------|---------|
| `INVALID_FILE_FORMAT` | 400 | File không đúng định dạng (.pdf, .docx, .txt) |
| `FILE_EMPTY` | 400 | File rỗng |
| `FILE_TOO_LARGE` | 400 | File > 50MB |
| `FILE_CORRUPT` | 400 | File bị hỏng, không đọc được |
| `INVALID_INPUT` | 400 | Input không hợp lệ |
| `NOT_FOUND` | 404 | Resource không tồn tại |
| `COURSE_NOT_READY` | 409 | Course chưa xử lý xong |
| `RATE_LIMITED` | 429 | Quá nhiều requests |
| `SYSTEM_ERROR` | 500 | Lỗi hệ thống không xác định |
| `SERVICE_UNAVAILABLE` | 503 | Hệ thống chưa khởi tạo |

```json
// Citation — dùng trong mọi response generate
"citations": [
  {
    "page": 5,
    "source": "tailieu.pdf",
    "chunk_id": "chunk_42"
  },
  {
    "page": 7,
    "source": "tailieu.pdf",
    "chunk_id": "chunk_58"
  }
]
```

---

## 1. Health & Management

### 1.1. Health Check

Kiểm tra hệ thống đã sẵn sàng chưa.

```
GET /api/health
```

**Response** (`HealthResponse`):
```json
{
  "status": "ok",
  "service": "ai-course-generator",
  "version": "1.0.0"
}
```

**Status Codes**:
- `200`: OK
- `503`: Hệ thống chưa khởi tạo (response: `ErrorResponse`)

**Error example**:
```json
{
  "error": true,
  "message": "Hệ thống chưa khởi tạo. Vui lòng thử lại sau.",
  "code": "SERVICE_UNAVAILABLE",
  "details": null
}
```

---

### 1.2. List Courses

Lấy danh sách các course ID.

```
GET /api/courses
```

**Response** (`CoursesListResponse`):
```json
{
  "courses": ["course_abc123", "course_def456"]
}
```

---

### 1.3. List All Courses With Metadata

Lấy danh sách tất cả courses kèm thông tin chi tiết.

```
GET /api/courses/all
```

**Response** (`CourseDetailListResponse`):
```json
{
  "courses": [
    {
      "course_id": "abc123",
      "status": "ready",
      "pdf_path": "uploads/1712345678_tailieu.pdf",
      "created_at": "2025-01-01 12:00:00"
    }
  ],
  "total": 1
}
```

---

### 1.4. Delete Course

Xóa một course và toàn bộ dữ liệu liên quan.

```
DELETE /api/courses/{course_id}
```

**Path Parameters**:
| Name | Type | Description |
|------|------|-------------|
| course_id | string | ID của course cần xóa |

**Response** (`DeleteCourseResponse`):
```json
{
  "status": "deleted",
  "course_id": "abc123"
}
```

**Status Codes**:
- `200`: Đã xóa thành công
- `404`: Không tìm thấy course (response: `ErrorResponse`)
- `503`: Hệ thống chưa khởi tạo

**Error example (404)**:
```json
{
  "error": true,
  "message": "Không tìm thấy course 'invalid_id'.",
  "code": "NOT_FOUND",
  "details": null
}
```

---

## 2. Upload

### 2.1. Upload File

Upload tài liệu (PDF, DOCX, TXT) để tạo course mới. Backend sẽ xử lý bất đồng bộ.

```
POST /api/upload
```

**Request**: `multipart/form-data`
| Field | Type | Description |
|-------|------|-------------|
| file | File | File tài liệu (PDF/DOCX/TXT) |

**Response** (`UploadResponse`):
```json
{
  "course_id": "abc123def456",
  "filename": "tailieu.pdf",
  "status": "processing",
  "message": "File 'tailieu.pdf' đã được nhận và đang được phân tích. ID khóa học: abc123def456"
}
```

**Status Codes**:
- `200`: Upload thành công (xử lý ngầm)
- `400`: File không hợp lệ — xem các Error examples bên dưới
- `503`: Hệ thống chưa khởi tạo

**Định dạng hỗ trợ**: `.pdf`, `.docx`, `.txt`

**Error examples (400)**:

```json
// Sai định dạng
{
  "error": true,
  "message": "File 'image.png' không được hỗ trợ. Chỉ chấp nhận .pdf, .docx, .txt.",
  "code": "INVALID_FILE_FORMAT",
  "details": null
}

// File rỗng
{
  "error": true,
  "message": "File không thể đọc được hoặc không có nội dung.",
  "code": "FILE_EMPTY",
  "details": null
}

// File quá lớn
{
  "error": true,
  "message": "File vượt quá giới hạn 50MB.",
  "code": "FILE_TOO_LARGE",
  "details": null
}

// File bị hỏng
{
  "error": true,
  "message": "File bị hỏng và không thể đọc được. Vui lòng kiểm tra lại file.",
  "code": "FILE_CORRUPT",
  "details": null
}
```

---

### 2.2. Get Course Status

Kiểm tra trạng thái xử lý của course.

```
GET /api/course/{course_id}/status
```

**Path Parameters**:
| Name | Type | Description |
|------|------|-------------|
| course_id | string | ID của course |

**Response** (`CourseStatusResponse`):
```json
{
  "course_id": "abc123",
  "status": "ready",
  "pdf_path": "uploads/1712345678_tailieu.pdf"
}
```

**Các trạng thái**:
| Status | Ý nghĩa |
|--------|---------|
| `pending` | File vừa upload, chưa xử lý |
| `processing` | Đang phân tích nội dung |
| `ready` | Đã sẵn sàng để generate resources |
| `error` | Có lỗi trong quá trình xử lý |

**Error example (404)**:
```json
{
  "error": true,
  "message": "Không tìm thấy course 'abc123'.",
  "code": "NOT_FOUND",
  "details": null
}
```

---

## 3. Chat

### 3.1. Chat

Đặt câu hỏi với nội dung course (RAG).

```
POST /api/chat
```

**Request Body** (`ChatRequest`):
```json
{
  "course_id": "abc123",
  "question": "Nội dung chính của chương 1 là gì?"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| question | string | 1-2000 ký tự, required | Câu hỏi |

**Response** (`ChatResponse`):
```json
{
  "answer": "Chương 1 trình bày về...",
  "course_id": "abc123",
  "citations": [
    {"page": 5, "source": "tailieu.pdf", "chunk_id": "chunk_42"},
    {"page": 7, "source": "tailieu.pdf", "chunk_id": "chunk_58"}
  ]
}
```

**Status Codes**:
- `200`: OK
- `404`: Không tìm thấy course
- `409`: Course chưa sẵn sàng (status ≠ "ready")
- `500`: Lỗi xử lý

**Error example (409)**:
```json
{
  "error": true,
  "message": "Course 'abc123' chưa sẵn sàng. Trạng thái hiện tại: processing.",
  "code": "COURSE_NOT_READY",
  "details": null
}
```

---

## 4. Generate Resources (Sync)

Các endpoints đồng bộ — trả về kết quả ngay lập tức. Phù hợp cho dữ liệu nhỏ.

**⚠️ Mọi response từ generate endpoints đều PHẢI có field `citations`** trace được về chunk trong Milvus.

### 4.1. Generate Course

Tạo khóa học có cấu trúc từ tài liệu đã upload.

```
POST /api/generate-course
```

**Request Body** (`GenerateCourseRequest`):
```json
{
  "course_id": "abc123",
  "user_prompt": "Tạo khóa học gồm 5 chương cho sinh viên đại học",
  "target_audience": "sinh viên đại học"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| user_prompt | string | 1-2000 ký tự, optional | Yêu cầu bổ sung |
| target_audience | string | 1-200 ký tự, optional | Đối tượng học |

**Response** (`GenerateCourseResponse`):
```json
{
  "course_id": "abc123",
  "course": {
    "title": "Khóa học: Vật lý đại cương",
    "description": "Khóa học bao gồm các kiến thức nền tảng về cơ học, nhiệt học và điện từ.",
    "chapters": [
      {
        "title": "Chương 1: Cơ học",
        "lessons": [
          {"title": "Bài 1: Động lực học chất điểm"},
          {"title": "Bài 2: Công và năng lượng"}
        ]
      }
    ]
  },
  "citations": [
    {"page": 3, "source": "tailieu.pdf", "chunk_id": "chunk_10"},
    {"page": 15, "source": "tailieu.pdf", "chunk_id": "chunk_42"}
  ]
}
```

---

### 4.2. Generate Summary

Tạo bản tóm tắt (ngắn, chi tiết, ý chính, kết luận).

```
POST /api/generate-summary
```

**Request Body** (`GenerateSummaryRequest`):
```json
{
  "course_id": "abc123",
  "type": "detailed"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| type | string | optional: "short", "detailed", "key_points", "conclusion". Default: "detailed" | Loại tóm tắt |

**Response** (`SummaryResponse`):
```json
{
  "course_id": "abc123",
  "summary": "# Tóm tắt\n\n## Ngắn gọn\n...\n\n## Chi tiết\n...",
  "filename": "summary.md",
  "citations": [
    {"page": 1, "source": "tailieu.pdf", "chunk_id": "chunk_1"},
    {"page": 5, "source": "tailieu.pdf", "chunk_id": "chunk_15"}
  ]
}
```

---

### 4.3. Generate Flashcards

```
POST /api/generate-flashcards
```

**Request Body** (`GenerateFlashcardsRequest`):
```json
{
  "course_id": "abc123",
  "count": 20
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| count | integer | 1-50, optional, default 20 | Số lượng flashcard |

**Response** (`FlashcardsResponse`):
```json
{
  "course_id": "abc123",
  "flashcards": [
    {"question": "Câu hỏi 1?", "answer": "Đáp án 1"}
  ],
  "total": 20,
  "citations": [
    {"page": 2, "source": "tailieu.pdf", "chunk_id": "chunk_8"},
    {"page": 3, "source": "tailieu.pdf", "chunk_id": "chunk_12"}
  ]
}
```

---

### 4.4. Generate Quiz (MCQ)

```
POST /api/generate-quiz
```

**Request Body** (`GenerateQuizRequest`):
```json
{
  "course_id": "abc123",
  "topic": "Kiến thức tổng quát",
  "quantity": 20,
  "difficulty": "medium"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| topic | string | 1-200 ký tự, required | Chủ đề câu hỏi |
| quantity | integer | 1-30, optional, default 20 | Số lượng câu hỏi |
| difficulty | string | optional: "easy", "medium", "hard". Default: "medium" | Mức độ khó |

**Response** (`QuizResponse`):
```json
{
  "course_id": "abc123",
  "topic": "Kiến thức tổng quát",
  "difficulty": "medium",
  "questions": [
    {
      "question": "Câu hỏi 1?",
      "options": ["A", "B", "C", "D"],
      "correct": 0,
      "explanation": "Giải thích..."
    }
  ],
  "total_questions": 20,
  "citations": [
    {"page": 10, "source": "tailieu.pdf", "chunk_id": "chunk_30"},
    {"page": 12, "source": "tailieu.pdf", "chunk_id": "chunk_35"}
  ]
}
```

---

### 4.5. Generate Slides

Nội dung slide để thuyết trình.

```
POST /api/generate-slides
```

**Request Body** (`GenerateSlidesRequest`):
```json
{
  "course_id": "abc123",
  "topic": "Chương 1",
  "num_slides": 10
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| topic | string | 1-200 ký tự, required | Chủ đề slide |
| num_slides | integer | 3-30, optional | Số lượng slide |

**Response** (`SlidesResponse`):
```json
{
  "course_id": "abc123",
  "topic": "Chương 1",
  "slides": [
    {
      "title": "Giới thiệu",
      "content": "Nội dung chính của slide...",
      "layout_hint": "title-and-content",
      "image_suggestion": "biểu đồ tròn"
    },
    {
      "title": "Nội dung chính",
      "content": "...",
      "layout_hint": "two-column",
      "image_suggestion": null
    }
  ],
  "total_slides": 10,
  "citations": [
    {"page": 5, "source": "tailieu.pdf", "chunk_id": "chunk_15"}
  ]
}
```

---

### 4.6. Generate Mind Map

Tạo bản đồ tư duy từ nội dung tài liệu.

```
POST /api/generate-mindmap
```

**Request Body** (`GenerateMindmapRequest`):
```json
{
  "course_id": "abc123",
  "max_depth": 3
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| max_depth | integer | 2-5, optional, default 3 | Độ sâu tối đa của mind map |

**Response** (`MindmapResponse`):
```json
{
  "course_id": "abc123",
  "mindmap": {
    "central_topic": "Vật lý đại cương",
    "branches": [
      {
        "title": "Cơ học",
        "children": [
          {"title": "Động lực học", "children": []},
          {"title": "Công và năng lượng", "children": []}
        ]
      },
      {
        "title": "Nhiệt học",
        "children": []
      }
    ]
  },
  "citations": [
    {"page": 3, "source": "tailieu.pdf", "chunk_id": "chunk_10"},
    {"page": 20, "source": "tailieu.pdf", "chunk_id": "chunk_50"}
  ]
}
```

---

### 4.7. Custom Prompt

Xử lý prompt tùy chỉnh của người dùng.

```
POST /api/custom-prompt
```

**Request Body** (`CustomPromptRequest`):
```json
{
  "course_id": "abc123",
  "prompt": "Tóm tắt tài liệu này trong 5 ý chính dành cho học sinh cấp 3"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| course_id | string | required | ID của course |
| prompt | string | 1-2000 ký tự, required | Yêu cầu xử lý tùy chỉnh |

**Response** (`CustomPromptResponse`):
```json
{
  "course_id": "abc123",
  "result": "Nội dung AI trả lời theo prompt...",
  "citations": [
    {"page": 1, "source": "tailieu.pdf", "chunk_id": "chunk_1"},
    {"page": 3, "source": "tailieu.pdf", "chunk_id": "chunk_9"}
  ]
}
```

---

### 4.8. Generate Study Guide (Bonus)

```
POST /api/generate-study-guide
```

**Request Body** (`GenerateStudyGuideRequest`):
```json
{
  "course_id": "abc123"
}
```

**Response** (`StudyGuideResponse`):
```json
{
  "course_id": "abc123",
  "guide": "# Hướng dẫn ôn tập\n\n## Chương 1...",
  "filename": "study_guide_abc123.md",
  "citations": [
    {"page": 1, "source": "tailieu.pdf", "chunk_id": "chunk_1"}
  ]
}
```

---

### 4.9. Generate Syllabus (Bonus)

```
POST /api/generate-syllabus
```

**Request Body** (`GenerateSyllabusRequest`):
```json
{
  "course_id": "abc123"
}
```

**Response** (`SyllabusResponse`):
```json
{
  "course_id": "abc123",
  "syllabus": [
    {"title": "Chương 1", "description": "...", "duration": "2 buổi"},
    {"title": "Chương 2", "description": "...", "duration": "3 buổi"}
  ],
  "citations": [
    {"page": 1, "source": "tailieu.pdf", "chunk_id": "chunk_1"}
  ]
}
```

---

### 4.10. Generate Podcast Script (Bonus)

```
POST /api/generate-podcast
```

**Request Body** (`GeneratePodcastRequest`):
```json
{
  "course_id": "abc123"
}
```

**Response** (`PodcastScriptResponse`):
```json
{
  "course_id": "abc123",
  "script": [
    {"speaker": "host", "text": "Xin chào..."},
    {"speaker": "expert", "text": "Hôm nay chúng ta..."}
  ],
  "estimated_duration": "15 phút",
  "citations": [
    {"page": 1, "source": "tailieu.pdf", "chunk_id": "chunk_1"}
  ]
}
```

---

## 5. Generate Resources (Async)

Các endpoints bất đồng bộ — trả về `task_id` để polling. Phù hợp cho dữ liệu lớn, tránh timeout.

**Các async endpoints**:

| Method | Endpoint | Task Type |
|--------|----------|-----------|
| POST | `/api/generate-course-async` | course |
| POST | `/api/generate-summary-async` | summary |
| POST | `/api/generate-flashcards-async` | flashcards |
| POST | `/api/generate-quiz-async` | quiz |
| POST | `/api/generate-slides-async` | slides |
| POST | `/api/generate-mindmap-async` | mindmap |
| POST | `/api/custom-prompt-async` | custom_prompt |

**Request Body**: Giống hệt sync version tương ứng.

**Response** (`TaskResponse`):
```json
{
  "task_id": "task_abc123",
  "status": "processing"
}
```

---

## 6. Task Polling

Poll trạng thái của một background task.

```
GET /api/task/{task_id}
```

**Response** (`TaskPollResponse`):
```json
// Khi đang xử lý
{
  "task_id": "task_abc123",
  "status": "processing",
  "task_type": "flashcards",
  "course_id": "abc123",
  "created_at": "2025-01-01 12:00:00",
  "updated_at": "2025-01-01 12:02:00",
  "elapsed_seconds": 120,
  "result": null
}

// Khi hoàn thành
{
  "task_id": "task_abc123",
  "status": "completed",
  "task_type": "flashcards",
  "course_id": "abc123",
  "created_at": "2025-01-01 12:00:00",
  "updated_at": "2025-01-01 12:05:00",
  "elapsed_seconds": 300,
  "result": [
    {"question": "...", "answer": "..."}
  ]
}
```

**Các trạng thái**: `processing` → `completed` | `failed`

Khi `status = "failed"`, response có thêm field `error`:
```json
{
  "task_id": "task_abc123",
  "status": "failed",
  "error": "Course 'abc' chưa sẵn sàng.",
  ...
}
```

---

## 7. Get Saved Content

Truy xuất nội dung đã được generate từ trước (đã lưu vào ổ đĩa).

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/course/{course_id}/course` | Lấy khóa học đã lưu |
| GET | `/api/course/{course_id}/summary` | Lấy summary đã lưu |
| GET | `/api/course/{course_id}/flashcards` | Lấy flashcards đã lưu |
| GET | `/api/course/{course_id}/questions` | Lấy questions đã lưu |
| GET | `/api/course/{course_id}/slides` | Lấy slides đã lưu |
| GET | `/api/course/{course_id}/mindmap` | Lấy mind map đã lưu |
| GET | `/api/course/{course_id}/study-guide` | Lấy study guide |
| GET | `/api/course/{course_id}/syllabus` | Lấy syllabus đã lưu |
| GET | `/api/course/{course_id}/audio` | Lấy podcast script |
| GET | `/api/course/{course_id}/files` | List tất cả files đã generate |
| GET | `/api/course/{course_id}/stats` | Thống kê course |

**Status Codes**: `404` nếu chưa có nội dung tương ứng.

### 7.1. List All Course Files

```
GET /api/course/{course_id}/files
```

**Response**:
```json
{
  "course_id": "abc123",
  "files": {
    "course": "courses/course_abc123/course.json",
    "summary": "courses/course_abc123/summary.json",
    "flashcards": "flashcards/course_abc123_flashcards.json",
    "questions": "questions/course_abc123_questions.json",
    "slides": ["slides_chuong_1.json"],
    "mindmap": "mindmaps/course_abc123_mindmap.json",
    "guides": ["study_guide.md"],
    "audio": ["podcast_script.json"]
  }
}
```

### 7.2. Get Course Stats

```
GET /api/course/{course_id}/stats
```

**Response**:
```json
{
  "course_id": "abc123",
  "status": "ready",
  "generated_at": "2025-01-01 12:05:00",
  "total_questions": 20,
  "total_flashcards": 15,
  "total_slides": 10,
  "has_course": true,
  "has_summary": true,
  "has_study_guide": true,
  "has_mindmap": false,
  "has_podcast": true
}
```

---

## 8. Tổng hợp Endpoints

### 8.1. Health & Management (4)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/health` | Health check |
| GET | `/api/courses` | List course IDs |
| GET | `/api/courses/all` | List courses + metadata |
| DELETE | `/api/courses/{course_id}` | Xóa course |

### 8.2. Upload (2)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/upload` | Upload file, tạo course |
| GET | `/api/course/{course_id}/status` | Check processing status |

### 8.3. Chat (1)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/chat` | Chat với course (RAG) |

### 8.4. Generate — Sync (10)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/generate-course` | Tạo khóa học |
| POST | `/api/generate-summary` | Tạo tóm tắt |
| POST | `/api/generate-flashcards` | Tạo flashcards |
| POST | `/api/generate-quiz` | Tạo câu hỏi MCQ |
| POST | `/api/generate-slides` | Tạo slides |
| POST | `/api/generate-mindmap` | Tạo mind map |
| POST | `/api/custom-prompt` | Xử lý prompt tùy chỉnh |
| POST | `/api/generate-study-guide` | Tạo study guide |
| POST | `/api/generate-syllabus` | Tạo syllabus |
| POST | `/api/generate-podcast` | Tạo podcast script |

### 8.5. Generate — Async (7)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/generate-course-async` | Course background |
| POST | `/api/generate-summary-async` | Summary background |
| POST | `/api/generate-flashcards-async` | Flashcards background |
| POST | `/api/generate-quiz-async` | Quiz background |
| POST | `/api/generate-slides-async` | Slides background |
| POST | `/api/generate-mindmap-async` | Mind map background |
| POST | `/api/custom-prompt-async` | Custom prompt background |

### 8.6. Task (1)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/task/{task_id}` | Poll task status |

### 8.7. Get Saved Content (11)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/course/{course_id}/course` | Lấy course đã lưu |
| GET | `/api/course/{course_id}/summary` | Lấy summary đã lưu |
| GET | `/api/course/{course_id}/flashcards` | Lấy flashcards |
| GET | `/api/course/{course_id}/questions` | Lấy questions |
| GET | `/api/course/{course_id}/slides` | Lấy slides |
| GET | `/api/course/{course_id}/mindmap` | Lấy mind map |
| GET | `/api/course/{course_id}/study-guide` | Lấy study guide |
| GET | `/api/course/{course_id}/syllabus` | Lấy syllabus |
| GET | `/api/course/{course_id}/audio` | Lấy podcast script |
| GET | `/api/course/{course_id}/files` | List tất cả files |
| GET | `/api/course/{course_id}/stats` | Thống kê course |

**Tổng cộng**: **36 endpoints** (4 + 2 + 1 + 10 + 7 + 1 + 11).

---

## 9. Flow khuyến nghị cho Frontend

### 9.1. Upload & tạo course

```
POST /api/upload (file)
  → nhận course_id + status: "processing"
  → GET /api/course/{course_id}/status (poll mỗi 2s)
  → status: "ready" → có thể chat & generate
```

### 9.2. Generate nội dung

```
Option A (sync — nhanh, dữ liệu nhỏ):
  POST /api/generate-flashcards (body: {course_id, count})
  → nhận kết quả ngay + citations

Option B (async — tránh timeout cho dữ liệu lớn):
  POST /api/generate-flashcards-async (body: {course_id, count})
  → nhận task_id
  → GET /api/task/{task_id} (poll mỗi 2-3s)
  → status: "completed" → lấy result từ task
```

### 9.3. Lấy lại nội dung cũ

```
GET /api/course/{course_id}/flashcards
GET /api/course/{course_id}/questions
GET /api/course/{course_id}/summary
...
```

### 9.4. Xóa course

```
DELETE /api/courses/{course_id}