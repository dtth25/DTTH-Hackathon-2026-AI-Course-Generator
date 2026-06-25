# Product Requirements Document: AI Course Generator

## 1. Product Soul
- **Mục tiêu:** Biến một hoặc nhiều tài liệu PDF, DOCX, TXT thành đúng 4 output học tập: **Book, Slide, Quiz, Vid**.
- **Giá trị cốt lõi:** Giảm thời gian đọc hiểu và tự động hệ thống hóa kiến thức thành artifact dễ học, dễ trình bày và dễ ôn tập.
- **Đối tượng:** Học sinh, giáo viên, người tự học và nhóm làm nội dung đào tạo.

## 2. Current Source of Truth
Code hiện tại là source of truth cho project. Các tài liệu phải bám theo implementation hiện có:
- **Frontend:** Next.js App Router, React, Tailwind CSS, shadcn/base-ui, lucide-react.
- **Backend:** FastAPI, Python 3.11+, LangChain, dependency management bằng `uv`.
- **Vector DB:** FAISS local disk-based.
- **Persistence:** Local filesystem JSON và generated files.
- **AI:** Gemini `gemini-2.5-flash` và batch embeddings bằng `models/embedding-001`.

## 3. Core User Flow
1. User upload một hoặc nhiều file `.pdf`, `.docx` hoặc `.txt`.
2. Backend validate từng file, lưu file, tạo `course_id`, xử lý cả bộ tài liệu ở background.
3. Backend parse text, chunk tài liệu, tạo embeddings và lưu một FAISS index chung cho `course_id`.
4. User poll `/api/course/{course_id}/status` đến khi `ready`.
5. User gọi một trong 4 endpoint AI qua FastAPI: Book, Slide, Quiz hoặc Vid.
6. Frontend hiển thị artifact trong workspace; tạo output mới không làm mất output cũ.
7. User có thể tải Book PDF, Slide JSON/PDF, Quiz JSON/PDF và Vid MP4.

## 4. Non-Negotiable Constraints
- **Only 4 Outputs:** Public product chỉ có Book, Slide, Quiz, Vid.
- **No Additional Chats:** Không có chat tự do, custom prompt độc lập hoặc output phụ ngoài 4 output.
- **No Public Source Metadata:** Response public không trả `page`, `source`, `chunk_id`, `citations`.
- **Grounded Generation:** Output AI phải dựa trên chunks truy xuất từ FAISS/local index.
- **Backend-only AI:** Frontend không gọi Gemini/LLM trực tiếp.
- **No-Auth v1:** Không đăng nhập, thanh toán hoặc phân quyền trong Hackathon version.
- **File validation:** `/api/upload` chỉ nhận `.pdf`, `.docx`, `.txt`, không nhận file rỗng hoặc file quá 50MB mỗi file.

## 5. Public Outputs
- **Book:** Sách học tập theo chương/bài, có view đọc trên UI và file PDF tải xuống.
- **Slide:** Viewer từng slide có nút trước/sau, kèm JSON và PDF tải xuống.
- **Quiz:** Bộ câu hỏi MCQ tương tác; không hiện đáp án trước khi user nộp bài; có JSON và PDF tải xuống.
- **Vid:** Video học tập dạng slide + voiceover, lưu metadata JSON và file MP4; nếu render lỗi phải trả trạng thái lỗi rõ ràng.

## 6. Known Implementation Notes
- API upload ưu tiên multipart field `files` cho multi-document; legacy field `file` vẫn được hỗ trợ.
- Book thay thế public concept "Course"; `course_id` chỉ còn là ID nội bộ của bộ tài liệu đã index.
- FAISS metadata vẫn được giữ nội bộ để truy xuất và debug, nhưng không xuất hiện trong public response.
- Demo cho người dùng nên chạy production frontend bằng `npm run build && npm run start` để tránh Next.js dev indicator.
