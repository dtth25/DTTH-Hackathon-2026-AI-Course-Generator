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
- **KaTeX & Xử lý Toán học trên UI:**
  - Hỗ trợ hiển thị chữ tiếng Việt Unicode trong khối LaTeX bằng cách sử dụng cơ chế font fallback của hệ thống. Đồng thời chặn toàn bộ log cảnh báo nhiễu `No character metrics for` tại `console.warn` để giữ sạch console và terminal khi chạy Next.js dev server.
  - Ngăn chặn lỗi tràn công thức toán học và tràn chữ ra ngoài lề trên UI bằng cách bọc các thẻ span KaTeX trong CSS `overflow-x-auto max-w-full` và áp dụng `break-words` cho container chính của MarkdownBlock.
  - Chuyển đổi hiển thị của các mục **Mục tiêu**, **Ý chính cần nhớ**, và **Kiểm tra nhanh** từ việc split danh sách sang sử dụng `LessonMarkdownSection` (dùng `MarkdownBlock` để render toàn bộ). Việc này loại bỏ hoàn toàn lỗi vỡ cấu trúc KaTeX do các ký tự ngắt dòng `\n` hoặc dấu chấm phẩy phân tách các công thức.
  - Tối ưu hóa bộ lọc danh sách trong `MarkdownBlock` để tự động gộp các dòng xuống dòng thô (không có dấu bullet) vào dòng bullet trước đó. Điều này giúp ngăn chặn hoàn toàn lỗi KaTeX bị cắt đôi công thức toán học do ký tự xuống dòng `\n` chen giữa.
  - Hỗ trợ hiển thị định dạng khối mã nguồn (Markdown Code Block) bằng cách bảo toàn ký tự dấu backtick (\`) trong quá trình xử lý, và tự động render mã dưới dạng thẻ `<pre><code>` có style nền tối, font monospace, chống tràn và hiển thị tên ngôn ngữ ở góc trên bên phải.
  - Cải tiến bộ lọc xử lý ký tự xuống dòng thô trong công thức LaTeX (`replaceNewlinesOutsideMath`) bằng regex thông minh. Regex này phân biệt chính xác giữa ký tự xuống dòng thô đứng sát biến số toán học đơn lẻ (như `\na`, `\nx`, `\nb`) để chuyển đổi thành xuống dòng thực tế, và các lệnh LaTeX thực thụ bắt đầu bằng chữ n (như `\ne`, `\nu`, `\neq`, `\nabla`) để giữ nguyên cấu trúc toán học.
- **Xuất bản PDF của Book:**
  - Để tránh lỗi ô vuông trống (thiếu font) khi xuất Book ra PDF trên backend, các ký hiệu toán học đặc biệt (số mũ, chỉ số dưới, dấu vô cực, dấu thuộc tập hợp,...) sẽ được chuyển đổi sang định dạng ASCII tiêu chuẩn trước khi tạo PDF, đảm bảo file PDF tải về hiển thị rõ ràng, dễ đọc trong khi Web UI vẫn giữ nguyên công thức LaTeX đẹp mắt.

