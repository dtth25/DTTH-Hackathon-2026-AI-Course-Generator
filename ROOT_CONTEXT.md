# Project Context: AI Course Generator

## 1. Product Soul
- **Mục tiêu:** Biến tài liệu thô (PDF, DOCX, TXT) thành đúng 4 output: **Book, Slide, Quiz, Vid**.
- **Giá trị cốt lõi:** Tự động hệ thống hóa kiến thức thành artifact học tập có thể đọc, trình chiếu, luyện tập và xem dạng video.
- **Đối tượng:** Học sinh, giáo viên, người tự học và nhóm làm nội dung đào tạo.

## 2. Mandatory Tech Stack
- **Frontend:** Next.js App Router, React, Tailwind CSS, shadcn/base-ui, lucide-react.
- **Backend:** FastAPI, Python 3.11+, LangChain, dependency management bằng `uv`.
- **Vector DB:** FAISS local disk-based. Mỗi course lưu index tại `indices/faiss_{course_id}/` và metadata tại `indices/faiss_{course_id}.json`.
- **Persistence:** Local filesystem JSON/generated files: `books/`, `slides/`, `questions/`, `videos/`.
- **AI Models:** Google Gemini qua LangChain Google GenAI: `gemini-2.5-flash` cho LLM và `models/embedding-001` cho batch embeddings.

## 3. Guiding Principles & Constraints
- **Only 4 Outputs:** Public API/UI chỉ có Book, Slide, Quiz, Vid.
- **No Additional Chats:** Không có chat tự do hoặc custom prompt độc lập.
- **No Public Source Metadata:** Public response không trả `page`, `source`, `chunk_id`.
- **Grounded Generation:** Nội dung AI phải dựa trên retrieved chunks từ FAISS/local index.
- **Backend-only AI calls:** Frontend không gọi LLM trực tiếp; mọi AI flow đi qua FastAPI.
- **No-Auth v1:** Không làm đăng nhập, thanh toán hoặc phân quyền trong phiên bản Hackathon.

## 4. Core Pipeline

```text
[Upload] -> [Parse] -> [Chunk] -> [Embed] -> [FAISS] -> [Retrieve] -> [Generate]
   |          |          |          |          |           |              |
   |          |          |          |          |           |              +-- Book
   |          |          |          |          |           |              +-- Slide
   |          |          |          |          |           |              +-- Quiz
   |          |          |          |          |           |              +-- Vid
   v          v          v          v          v           v
 course_id  raw_text   chunks     vectors   local index  top_k
```

## 5. Non-Negotiable Gates
1. **Upload validation** - chỉ chấp nhận `.pdf`, `.docx`, `.txt`, không file rỗng, không quá 50MB.
2. **Only 4 public outputs** - không merge endpoint/UI/docs cho output ngoài Book, Slide, Quiz, Vid.
3. **No public source metadata** - không trả `page`, `source`, `chunk_id` trong API response public.
4. **Backend-only AI** - tất cả LLM/embedding calls phải nằm ở backend.
5. **Backend dùng `uv`** để quản lý Python dependencies.
6. **No Auth/Payment v1** - tập trung core AI pipeline.
