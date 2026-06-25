# Automated Testing Plan — AI Course Generator

> **Author:** QA / Tester (UI/UX & User Experience)
> **Version:** 2.0.0
> **Last Updated:** 2026-06-25

---

## 1. Overview

- **Total Test Cases:** 84 (Frontend UI) + 36 (Backend API) + 3 (E2E Integration)
- **Features Covered:** 8 (Upload, Course, Summary, Flashcard, Quiz, Slide, Mindmap, Custom Prompt)
- **Scope:** Frontend UI/UX validation + Backend API validation + E2E Integration
- **Priority Levels:** P0 (Critical), P1 (High), P2 (Medium)

---

## 2. Priority Definitions

| Priority | Description | Target |
|----------|-------------|--------|
| **P0** | Core workflow — must pass before any release | Upload, Course Gen, Citation display |
| **P1** | Important UX — should pass for MVP | Memory states, Quiz components, Navigation |
| **P2** | Nice to have — polish & edge cases | Animations, Export, Shuffle |

---

## 3. Frontend UI Tests (Playwright E2E)

### 3.1 Công cụ

| Công cụ | Mục đích |
|---------|----------|
| `@playwright/test` | E2E test runner |
| Playwright route interception | Mock API responses (không cần backend thật) |
| Page Object Model (POM) | Tái sử dụng code test, dễ bảo trì |
| GitHub Actions | CI server tự động |

### 3.2 Cấu trúc thư mục

```
src/frontend/
├── playwright.config.ts              # Cấu hình Playwright
├── tests/
│   ├── fixtures/
│   │   └── test-data.json            # Mock responses cho 8 features
│   ├── pages/                        # Page Object Models
│   │   ├── UploadPage.ts
│   │   ├── CoursePage.ts
│   │   ├── FlashcardPage.ts
│   │   ├── QuizPage.ts
│   │   ├── SummaryPage.ts
│   │   ├── SlidePage.ts
│   │   ├── MindmapPage.ts
│   │   └── CustomPromptPage.ts
│   └── e2e/                          # E2E test files
│       ├── upload.spec.ts            # 10 TCs
│       ├── course.spec.ts            # 9 TCs
│       ├── flashcard.spec.ts         # 13 TCs
│       ├── quiz.spec.ts              # 13 TCs
│       ├── summary.spec.ts           # 9 TCs
│       ├── slide.spec.ts             # 10 TCs
│       ├── mindmap.spec.ts           # 10 TCs
│       └── custom-prompt.spec.ts     # 10 TCs
```

### 3.3 Chiến lược Mock API

Tất cả test đều dùng **Playwright route interception** để mock API responses, không cần backend thật chạy. Mỗi mock response đều có trường `citations` để test Gate 2.

Ví dụ mock:
```typescript
await page.route('**/api/upload', async route => {
  await route.fulfill({
    status: 200,
    body: JSON.stringify({
      course_id: 'test-course-123',
      filename: 'sample.pdf',
      status: 'processing',
      message: 'Upload thành công'
    })
  });
});
```

### 3.4 Test Case Tables

#### 3.4.1 Upload

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_UPLOAD_01 | P0 | Upload | User chọn file PDF hợp lệ và click "Upload" | Hiển thị progress bar, sau đó thông báo "Upload thành công", file xuất hiện trong danh sách tài liệu |
| TC_UPLOAD_02 | P0 | Upload | User chọn file DOCX hợp lệ và click "Upload" | Upload thành công, file được liệt kê với icon DOCX |
| TC_UPLOAD_03 | P0 | Upload | User chọn file TXT hợp lệ và click "Upload" | Upload thành công, file được liệt kê |
| TC_UPLOAD_04 | P0 | Upload Validation | User chọn file .jpg/.png và click "Upload" | Hiển thị error message: "Chỉ chấp nhận file .pdf, .docx, .txt", file không được upload |
| TC_UPLOAD_05 | P0 | Upload Validation | User chọn file .exe/.zip và click "Upload" | Error message rõ ràng, upload bị reject ngay lập tức |
| TC_UPLOAD_06 | P1 | Upload | User chọn file > 10MB và click "Upload" | Hiển thị warning "File quá lớn" hoặc upload vẫn thành công (tùy backend config) |
| TC_UPLOAD_07 | P1 | Upload | User click "Chọn file" nhưng không chọn file nào, rồi click "Upload" | Validation error: "Vui lòng chọn file trước khi upload" |
| TC_UPLOAD_08 | P1 | Upload | User upload file đã tồn tại trong hệ thống | Warning message "File đã tồn tại", hỏi có muốn ghi đè không |
| TC_UPLOAD_09 | P2 | Upload | User click nút "Cancel" trong quá trình upload | Upload dừng ngay, UI trở về trạng thái ban đầu, không có file được thêm |
| TC_UPLOAD_10 | P2 | Upload | User upload file PDF bị corrupt/lỗi | Error message "File không thể đọc được", gợi ý kiểm tra lại file |

#### 3.4.2 Course

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_COURSE_01 | P0 | Course Generation | User chọn document và click "Generate Course" | Hiển thị loading spinner, sau đó hiển thị course structure với các modules |
| TC_COURSE_02 | P0 | Key Points | User xem course vừa tạo | Mỗi module có section **"Key Points"** được highlight, liệt kê các điểm chính |
| TC_COURSE_03 | P0 | Citation Display | User xem nội dung bài học | Mỗi đoạn nội dung có citation marker [1], [2] có thể click để xem source |
| TC_COURSE_04 | P1 | Course Navigation | User click vào tên module trong sidebar | Nội dung module hiển thị trong panel chính, highlight module đang active |
| TC_COURSE_05 | P1 | Course Progress | User đang trong quá trình generate course | Progress bar hiển thị % hoàn thành, text "Đang tạo bài học..." |
| TC_COURSE_06 | P1 | Course Error | Backend trả lỗi trong quá trình generate | Error message "Không thể tạo bài học. Vui lòng thử lại", nút "Retry" xuất hiện |
| TC_COURSE_07 | P1 | Course Expand/Collapse | User click icon expand/collapse bên cạnh module | Nội dung module ẩn/hiện với animation mượt mà |
| TC_COURSE_08 | P0 | Citation Click | User click vào citation marker [1] | Tooltip hoặc side panel hiển thị thông tin: "Trang 5 - Chapter 2.pdf" |
| TC_COURSE_09 | P2 | Empty State | User chưa upload file nào nhưng click "Generate Course" | Message: "Vui lòng upload tài liệu trước", redirect đến upload section |

#### 3.4.3 Summary

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_SUMMARY_01 | P0 | Summary Generation | User click "Generate Summary" | Loading indicator, sau đó hiển thị summary text trong panel |
| TC_SUMMARY_02 | P0 | Citation in Summary | User xem summary | Mỗi đoạn tóm tắt có citation [page X] liên kết đến source |
| TC_SUMMARY_03 | P1 | Summary Length — Short | User chọn độ dài "Ngắn" (Short) | Summary ~100-150 từ, concise |
| TC_SUMMARY_04 | P1 | Summary Length — Medium | User chọn độ dài "Trung bình" (Medium) | Summary ~300-400 từ |
| TC_SUMMARY_05 | P1 | Summary Length — Detailed | User chọn độ dài "Chi tiết" (Detailed) | Summary ~500-700 từ, đầy đủ hơn |
| TC_SUMMARY_06 | P1 | Regenerate Summary | User click "Regenerate" | Loading, sau đó hiển thị summary mới (có thể khác biệt) |
| TC_SUMMARY_07 | P1 | Summary Copy | User click nút "Copy" bên cạnh summary | Text được copy vào clipboard, hiển thị toast "Đã copy" |
| TC_SUMMARY_08 | P1 | Summary Error | Backend fail generate summary | Error message, nút "Thử lại" xuất hiện |
| TC_SUMMARY_09 | P2 | Summary Export | User click "Download" | File .txt hoặc .md được download với nội dung summary |

#### 3.4.4 Flashcard — 4 trạng thái ghi nhớ (Again / Hard / Good / Easy)

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_FLASHCARD_01 | P0 | Flashcard Generation | User click "Generate Flashcards" | Loading, sau đó hiển thị bộ flashcard đầu tiên |
| TC_FLASHCARD_02 | P0 | Flashcard Front | User xem flashcard mới | Hiển thị mặt trước: câu hỏi / học thuật ngữ |
| TC_FLASHCARD_03 | P0 | Flip Card | User click vào flashcard hoặc nút "Flip" | Card lật với animation 3D, hiển thị mặt sau: đáp án + giải thích |
| TC_FLASHCARD_04 | P0 | Memory State — Again (Chưa nhớ) | User click nút "Again" sau khi xem mặt sau | Card chuyển đến cuối hàng đợi, progress bar giảm, text "Cần ôn lại" |
| TC_FLASHCARD_05 | P0 | Memory State — Hard (Nhớ một phần) | User click nút "Hard" sau khi xem mặt sau | Card được lên lịch ôn sớm, progress bar tăng nhẹ |
| TC_FLASHCARD_06 | P0 | Memory State — Good (Đã nhớ) | User click nút "Good" sau khi xem mặt sau | Card được lên lịch bình thường, progress bar tăng |
| TC_FLASHCARD_07 | P0 | Memory State — Easy (Đã nhớ kỹ) | User click nút "Easy" sau khi xem mặt sau | Card được lên lịch muộn hơn, progress bar tăng nhiều |
| TC_FLASHCARD_08 | P1 | Flashcard Navigation | User click nút "Next" sau khi đánh giá | Chuyển sang flashcard tiếp theo với animation slide |
| TC_FLASHCARD_09 | P1 | Flashcard Progress | User đang ôn tập | Hiển thị "Card X/Y" và progress bar % |
| TC_FLASHCARD_10 | P1 | Flashcard Complete | User hoàn thành tất cả cards | Hiển thị màn hình "Hoàn thành!", thống kê số cards đã ôn, nút "Ôn lại" |
| TC_FLASHCARD_11 | P0 | Citation in Flashcard | User xem mặt sau của card | Hiển thị "Nguồn: Trang X - File.pdf" |
| TC_FLASHCARD_12 | P2 | Shuffle Cards | User click nút "Shuffle" | Thứ tự cards được đảo ngẫu nhiên, animation shuffle |
| TC_FLASHCARD_13 | P2 | Auto-Play Mode | User click "Auto Play" | Cards tự động xoay vòng mỗi 5s |

#### 3.4.5 Quiz — 4 thành phần: Câu hỏi, 4 đáp án, Đáp án đúng, Giải thích

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_QUIZ_01 | P0 | Quiz Generation | User click "Generate Quiz" | Loading, sau đó hiển thị câu hỏi đầu tiên |
| TC_QUIZ_02 | P0 | Question Display | User xem câu hỏi | Hiển thị rõ ràng câu hỏi, đánh số thứ tự **(Câu 1/X)** |
| TC_QUIZ_03 | P0 | 4 Answer Options | User xem câu hỏi | Hiển thị đủ **4 đáp án** dạng button/radio, có thể click chọn |
| TC_QUIZ_04 | P1 | Select Answer | User click chọn 1 đáp án | Đáp án được highlight, nút "Submit" hoặc "Next" xuất hiện |
| TC_QUIZ_05 | P0 | Correct Answer Highlight | User submit một đáp án | **Đáp án đúng** highlight màu xanh + icon ✓ |
| TC_QUIZ_06 | P0 | Wrong Answer Highlight | User submit đáp án sai | Đáp án sai highlight màu đỏ, đáp án đúng highlight màu xanh |
| TC_QUIZ_07 | P0 | Explanation Display | User vừa submit đáp án | Section **"Giải thích"** xuất hiện, giải thích tại sao đáp án đúng |
| TC_QUIZ_08 | P1 | Quiz Progress | User đang làm quiz | Hiển thị progress bar và "Câu X/Y" |
| TC_QUIZ_09 | P1 | Quiz Completion | User hoàn thành tất cả câu hỏi | Hiển thị màn hình kết quả: Score (X/Y), %, nút "Làm lại" |
| TC_QUIZ_10 | P1 | Quiz Navigation — Next | User click "Next" sau khi trả lời | Chuyển sang câu hỏi tiếp theo |
| TC_QUIZ_11 | P0 | Citation in Quiz | User xem explanation | Hiển thị "Nguồn: Trang X" trong phần giải thích |
| TC_QUIZ_12 | P2 | Skip Question | User click "Bỏ qua" | Câu hỏi được đánh dấu chưa trả lời, chuyển sang câu tiếp |
| TC_QUIZ_13 | P2 | Review Answers | User click "Review" sau khi hoàn thành | Hiển thị tất cả câu hỏi với đáp án đúng/sai của user |

#### 3.4.6 Slide

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_SLIDE_01 | P0 | Slide Generation | User click "Generate Slides" | Loading, sau đó hiển thị slide đầu tiên |
| TC_SLIDE_02 | P1 | Slide Content | User xem slide | Slide hiển thị title, bullet points, có thể có hình ảnh |
| TC_SLIDE_03 | P1 | Slide Navigation — Next | User click nút "Next" (→) | Chuyển sang slide tiếp theo với animation fade/slide |
| TC_SLIDE_04 | P1 | Slide Navigation — Prev | User click nút "Prev" (←) | Quay lại slide trước |
| TC_SLIDE_05 | P1 | Slide Thumbnail | User click vào thumbnail trong sidebar | Nhảy trực tiếp đến slide tương ứng, thumbnail highlight |
| TC_SLIDE_06 | P1 | Slide Progress | User đang xem slide deck | Hiển thị "Slide X/Y" và progress dots |
| TC_SLIDE_07 | P0 | Citation in Slide | User xem slide | Mỗi slide có citation marker, click hiển thị source |
| TC_SLIDE_08 | P1 | Fullscreen Mode | User click nút "Fullscreen" | Slide chiếm toàn màn hình, nhấn ESC để thoát |
| TC_SLIDE_09 | P1 | Slide Error | Backend fail generate slides | Error message, nút "Retry" |
| TC_SLIDE_10 | P2 | Keyboard Shortcuts | User nhấn phím → hoặc ↓ | Chuyển đến slide tiếp theo (← hoặc ↑ để quay lại) |

#### 3.4.7 Mindmap

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_MINDMAP_01 | P0 | Mindmap Generation | User click "Generate Mindmap" | Loading, sau đó hiển thị sơ đồ tư duy với node trung tâm |
| TC_MINDMAP_02 | P1 | Node Display | User xem mindmap | Hiển thị node trung tâm + các nhánh con, màu sắc phân biệt |
| TC_MINDMAP_03 | P1 | Expand Node | User click vào node có dấu "+" | Nhánh con mở rộng ra, hiển thị thêm nodes |
| TC_MINDMAP_04 | P1 | Collapse Node | User click vào node có dấu "-" | Nhánh con thu gọn lại |
| TC_MINDMAP_05 | P1 | Node Click | User click vào node lá | Hiển thị tooltip hoặc side panel với nội dung chi tiết |
| TC_MINDMAP_06 | P1 | Pan Mindmap | User kéo thả (drag) canvas | Sơ đồ di chuyển theo chuột |
| TC_MINDMAP_07 | P1 | Zoom Mindmap | User scroll wheel hoặc pinch | Zoom in/out sơ đồ, có nút reset zoom |
| TC_MINDMAP_08 | P0 | Citation in Mindmap | User hover vào node | Tooltip hiển thị "Nguồn: Trang X" |
| TC_MINDMAP_09 | P2 | Mindmap Layout | User click "Re-layout" | Sơ đồ tự động sắp xếp lại bố cục đẹp hơn |
| TC_MINDMAP_10 | P2 | Export Mindmap | User click "Export" | Cho phép chọn định dạng (PNG, SVG, JSON) và download |

#### 3.4.8 Custom Prompt

| ID | Priority | Tính năng | Trường hợp test (Hành động của user) | Kết quả mong muốn (UI) |
|----|----------|-----------|--------------------------------------|------------------------|
| TC_CUSTOM_01 | P0 | Prompt Input | User click vào textarea "Nhập câu hỏi của bạn" | Textarea focus, hiển thị cursor, placeholder text |
| TC_CUSTOM_02 | P0 | Submit Prompt | User nhập câu hỏi hợp lệ và click "Gửi" | Loading, sau đó hiển thị câu trả lời AI trong chat panel |
| TC_CUSTOM_03 | P0 | Citation in Response | User xem câu trả lời AI | Response có citation markers [1], [2] có thể click |
| TC_CUSTOM_04 | P1 | Empty Prompt | User click "Gửi" mà không nhập gì | Validation error: "Vui lòng nhập câu hỏi", textarea border đỏ |
| TC_CUSTOM_05 | P1 | Very Long Prompt | User nhập prompt > 1000 ký tự | Textarea cho phép nhập, nhưng hiển thị counter "X/1000" |
| TC_CUSTOM_06 | P1 | Chat History | User đã hỏi nhiều câu | Hiển thị danh sách các câu hỏi/trả lời trước đó, có thể scroll |
| TC_CUSTOM_07 | P1 | Clear History | User click "Xóa lịch sử" | Hiển thị confirmation dialog "Bạn có chắc?", sau đó xóa toàn bộ chat |
| TC_CUSTOM_08 | P2 | Prompt Suggestion | User click vào gợi ý prompt có sẵn | Prompt tự động điền vào textarea |
| TC_CUSTOM_09 | P2 | Streaming Response | User gửi câu hỏi | Response hiển thị từ từ (typewriter effect) thay vì chờ full rồi mới hiện |
| TC_CUSTOM_10 | P1 | Error Handling | Backend fail xử lý prompt | Error message "Không thể xử lý. Vui lòng thử lại", nút retry |

---

## 4. Critical Checkpoints (Ràng buộc bắt buộc từ AGENTS.md + ROOT_CONTEXT.md)

Dưới đây là các checkpoints mà **mọi test case phải verify**:

### ✅ Gate 1: File Upload Validation
- **TC liên quan:** TC_UPLOAD_01 → TC_UPLOAD_10
- **Check:** Endpoint chỉ chấp nhận `.pdf`, `.docx`, `.txt`. Reject mọi format khác với error message rõ ràng.

### ✅ Gate 2: Citation Check
- **TC liên quan:** TC_COURSE_03, TC_COURSE_08, TC_SUMMARY_02, TC_FLASHCARD_11, TC_QUIZ_11, TC_SLIDE_07, TC_MINDMAP_08, TC_CUSTOM_03
- **Check:** Mọi response AI phải có trường `citations: [{page, source}]`. Mỗi citation trace được về chunk_id trong Milvus.

### ✅ Gate 3: No Hallucination
- **Check ngang (cross-check):** Nội dung AI sinh ra phải bám sát tài liệu gốc. Không được "quá chung chung" (too generic).

### ✅ Gate 4: No Direct LLM Call from Frontend
- **Check ngang:** Tất cả request AI đều phải qua FastAPI backend. Không có direct API call từ client-side.

---

## 5. Backend API Tests (Pytest)

### 5.1 Công cụ

| Công cụ | Mục đích |
|---------|----------|
| `pytest` + `pytest-asyncio` | Chạy unit test và integration test |
| `httpx` (TestClient/AsyncClient) | Gọi API thực tế |
| `pytest-cov` | Đo coverage (yêu cầu >= 70%) |
| `ruff` | Linting PEP8 |
| `mypy` | Type checking |
| GitHub Actions | CI server tự động |

### 5.2 Cấu trúc thư mục

```
src/backend/tests/
├── conftest.py              # Fixtures: test client, test course, sample files
├── test_upload.py           # Gate 1: Upload validation (10 TCs)
├── test_citations.py        # Gate 2+3: Citation present + traceability (14 TCs)
├── test_full_pipeline.py    # Integration: upload → process → generate (4 TCs)
├── test_async_endpoints.py  # Async task lifecycle (3 TCs)
├── test_course_management.py# CRUD courses (3 TCs)
├── test_health.py           # Health check (2 TCs)
└── validate_citations.py    # Script CI riêng cho citation gate
```

### 5.3 Danh sách Test Cases chi tiết

#### 5.3.1 Gate 1 — File Upload Validation

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1.1 | Upload PDF hợp lệ | File .pdf 1MB | 200 + `course_id` |
| 1.2 | Upload DOCX hợp lệ | File .docx 1MB | 200 |
| 1.3 | Upload TXT hợp lệ | File .txt 1MB | 200 |
| 1.4 | Upload file .png | File .png | 422 — reject |
| 1.5 | Upload file .jpg | File .jpg | 422 — reject |
| 1.6 | Upload file .exe | File .exe | 422 — reject |
| 1.7 | Upload file .zip | File .zip | 422 — reject |
| 1.8 | Upload file rỗng | File 0 byte | 422 — reject |
| 1.9 | Upload file > 50MB | File 51MB | 422 — reject |
| 1.10 | Không gửi file | POST thiếu field `file` | 422 |

#### 5.3.2 Gate 2 — Citation Check (mọi endpoint AI)

| # | Endpoint | Kiểm tra |
|---|----------|----------|
| 2.1 | `POST /api/chat` | `citations` array không rỗng |
| 2.2 | `POST /api/generate-course` | Mỗi item có `{page, source, chunk_id}` |
| 2.3 | `POST /api/generate-summary` | `citations` tồn tại |
| 2.4 | `POST /api/generate-flashcards` | `citations` tồn tại |
| 2.5 | `POST /api/generate-quiz` | `citations` tồn tại |
| 2.6 | `POST /api/generate-slides` | `citations` tồn tại |
| 2.7 | `POST /api/generate-mindmap` | `citations` tồn tại |
| 2.8 | `POST /api/custom-prompt` | `citations` tồn tại |
| 2.9 | Async endpoints | Poll task → kết quả có `citations` |

#### 5.3.3 Gate 3 — No Hallucination / Traceability

| # | Test Case | Mô tả |
|---|-----------|-------|
| 3.1 | page hợp lệ | `page` <= tổng số trang file gốc |
| 3.2 | chunk_id tồn tại | `chunk_id` có trong Milvus metadata |
| 3.3 | source trùng filename | `source` trong citation = tên file đã upload |
| 3.4 | Nội dung không chung chung | AI output chứa từ khóa từ document gốc |
| 3.5 | Không hallucination | AI không thêm thông tin ngoài tài liệu |

#### 5.3.4 Gate 4 — Backend-only AI

| # | Test Case | Mô tả |
|---|-----------|-------|
| 4.1 | Scan frontend code | `grep` tìm `gemini`, `generativeai`, `ChatGoogleGenerativeAI` trong `src/frontend/` → 0 matches |

#### 5.3.5 Integration Tests

| # | Test Case | Mô tả |
|---|-----------|-------|
| 5.1 | Full pipeline PDF | Upload → poll `ready` → generate course → verify citations |
| 5.2 | Full pipeline DOCX | Upload → poll `ready` → generate summary |
| 5.3 | Course status transitions | Upload → `processing` → `ready` |
| 5.4 | Delete course | Upload → delete → verify cleanup |

#### 5.3.6 Async Endpoint Tests

| # | Test Case | Mô tả |
|---|-----------|-------|
| 6.1 | Async generate course | Gọi async → poll task → verify |
| 6.2 | Async task not found | GET `/api/task/invalid_id` → 404 |
| 6.3 | Tất cả async generate types | Course, summary, flashcards, quiz, slides, mindmap, custom prompt, podcast, study guide |

---

## 6. E2E Integration Tests

### 6.1 Mục tiêu

Kiểm tra luồng full-stack: Frontend → Backend → Milvus → Response. Các test này chạy với cả Frontend và Backend thật.

### 6.2 Cấu trúc

```
tests/
├── conftest.py                    # Fixtures: start frontend + backend + milvus
├── test_full_flow.py              # Upload → Process → Generate → Verify citations
└── requirements.txt               # Python dependencies
```

### 6.3 Test Cases

| # | Test Case | Mô tả |
|---|-----------|-------|
| E2E_01 | Upload PDF → Generate Course → Check citations | Upload file, đợi processing, generate course, verify citations |
| E2E_02 | Upload DOCX → Generate Summary → Check length | Kiểm tra summary với 3 độ dài |
| E2E_03 | Upload TXT → Full pipeline | Upload → Quiz → Flashcard → Mindmap → Slide → Custom Prompt |

---

## 7. Quy trình CI/CD

### 7.1 Backend CI (`backend-ci.yml`)

Pipeline gồm 3 job chạy tuần tự:

```
Job 1: Lint & Type Check (Gate 5)
  ├─ ruff lint
  └─ mypy type check

Job 2: Run Tests (Gates 1-4)
  ├─ pytest + coverage >= 70%
  ├─ validate_citations.py (Gate 2+3)
  └─ grep frontend for LLM calls (Gate 4)

Job 3: Quality Gates Summary
  └─ Tổng hợp kết quả các Gate
```

### 7.2 Frontend CI (`frontend-ci.yml`)

```
Job 1: Lint & Build
  ├─ next lint
  └─ next build

Job 2: Playwright Tests
  ├─ npx playwright install
  ├─ npx playwright test (P0 tests only on PR)
  └─ npx playwright test --shard=1/3 (full suite on merge)
```

### 7.3 E2E Integration CI (`full-e2e.yml`)

```
Job 1: Start Services
  ├─ docker-compose up milvus zep
  └─ Start backend (uvicorn)

Job 2: Run E2E Tests
  ├─ Start frontend (next dev)
  ├─ pytest tests/test_full_flow.py
  └─ Stop all services
```

---

## 8. Điều kiện Pass/Fail

| Gate | Điều kiện Pass | Hành động nếu Fail |
|------|----------------|--------------------|
| Gate 1 — Upload | 100% test upload pass | **Block merge** → báo Lead |
| Gate 2 — Citation | 100% response có citations | **Block merge** → gán Backend Dev |
| Gate 3 — Traceability | Citation traceable về Milvus metadata | **Block merge** → gán Backend Dev |
| Gate 4 — Backend-only | 0 LLM call từ frontend | **Block merge** → gán Frontend Dev |
| Gate 5 — Code style | ruff 0 lỗi + mypy pass | Warning (Lead có thể bypass) |
| Coverage | >= 70% | Warning |
| Frontend UI Test | 100% P0 pass | **Block merge** → gán Frontend Dev |
| E2E Integration | 3/3 test pass | **Block merge** → gán cả 2 Dev |

---

## 9. Traceability Matrix

### Frontend UI Tests

| Feature | P0 | P1 | P2 | Total |
|---------|----|----|----|-------|
| Upload | 5 | 3 | 2 | 10 |
| Course | 4 | 4 | 1 | 9 |
| Summary | 2 | 6 | 1 | 9 |
| Flashcard | 8 | 3 | 2 | 13 |
| Quiz | 7 | 4 | 2 | 13 |
| Slide | 2 | 7 | 1 | 10 |
| Mindmap | 2 | 6 | 2 | 10 |
| Custom Prompt | 3 | 5 | 2 | 10 |
| **Total** | **33** | **38** | **13** | **84** |

### Backend API Tests

| Module | Số test case | Gates |
|--------|-------------|-------|
| test_upload.py | 10 | Gate 1 |
| test_citations.py | 14 | Gate 2+3 |
| test_full_pipeline.py | 4 | Integration |
| test_async_endpoints.py | 3 | Async |
| test_course_management.py | 3 | CRUD |
| test_health.py | 2 | Health |
| **Total** | **36** | |

### E2E Integration Tests

| Module | Số test case |
|--------|-------------|
| test_full_flow.py | 3 |
| **Total** | **3** |

---

## 10. Pre-merge Checklist (chạy thủ công)

- [ ] Gate 1: Upload validation pass
- [ ] Gate 2: Mọi endpoint trả về `citations`
- [ ] Gate 3: Citation trace ngược về chunk metadata
- [ ] Gate 4: Frontend không chứa LLM import
- [ ] Gate 5: Code style pass (ruff + mypy)
- [ ] Frontend UI Test: P0 pass
- [ ] Integration: Full pipeline hoạt động
- [ ] Regression: Các test cũ vẫn pass

---

## 11. Các bước triển khai

### Phase 1: Cập nhật tài liệu (đã xong)
- [x] Merge frontend + backend plan vào file automated-testing.md

### Phase 2: Backend Tests
- [ ] Tạo thư mục `src/backend/tests/`
- [ ] Tạo `conftest.py` với fixtures
- [ ] Tạo `test_upload.py` (Gate 1)
- [ ] Tạo `test_citations.py` (Gate 2+3)
- [ ] Tạo `test_full_pipeline.py` (Integration)
- [ ] Tạo `test_async_endpoints.py` (Async)
- [ ] Tạo `test_course_management.py` (CRUD)
- [ ] Tạo `test_health.py` (Health)
- [ ] Tạo `validate_citations.py` (CI script)

### Phase 3: Frontend Tests
- [ ] Cài đặt Playwright trong `src/frontend/`
- [ ] Tạo `playwright.config.ts`
- [ ] Tạo `tests/fixtures/test-data.json`
- [ ] Tạo 8 Page Object Models
- [ ] Viết 8 test files theo thứ tự P0 → P1 → P2
- [ ] Thêm scripts vào `package.json`

### Phase 4: CI/CD
- [ ] Tạo `.github/workflows/backend-ci.yml`
- [ ] Tạo `.github/workflows/frontend-ci.yml`
- [ ] Tạo `.github/workflows/full-e2e.yml`

### Phase 5: E2E Integration
- [ ] Tạo `tests/conftest.py`
- [ ] Tạo `tests/test_full_flow.py`
- [ ] Tạo `tests/requirements.txt`

---

*Tài liệu này được tạo bởi QA Dev, dựa trên PRD.md, ROOT_CONTEXT.md, AGENTS.md, api_contract.md và architecture_design.md.*