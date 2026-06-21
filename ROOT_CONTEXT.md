# Project Context: AI Course Generator

## 1. Product Soul (Tóm lược PRD)
- **Mục tiêu:** Biến tài liệu thô (PDF, DOCX, TXT) thành hệ sinh thái học tập đa phương tiện.
- **Giá trị cốt lõi:** Tiết kiệm thời gian đọc hiểu và hệ thống hóa kiến thức tự động.
- **Đối tượng:** Học sinh, giáo viên, người tự học.

## 2. Mandatory Tech Stack (Chốt cứng)
- **Frontend:** Next.js 14+ (App Router), Tailwind CSS.
- **Backend:** FastAPI (Python 3.11+).
- **Vector DB:** Milvus (Dành cho RAG và Citation).
- **Memory Layer:** Zep (Lưu ngữ cảnh phiên làm việc).
- **AI Models:** Ưu tiên Claude 3.5 Sonnet hoặc GPT-4o.

## 3. Guiding Principles & Constraints
- **Citation-First:** Mọi nội dung AI sinh ra (bài học, tóm tắt) PHẢI kèm trích dẫn số trang/nguồn từ tài liệu gốc [1, 2].
- **No-Auth v1:** Không làm chức năng Đăng nhập/Thanh toán trong phiên bản Hackathon (tập trung Core AI).
- **Agentic Workflow:** Sử dụng AI để viết code, con người đóng vai trò giám sát (Jury) và thẩm định logic.

## 4. Core Pipeline (Tổng quan luồng xử lý)

```
[Upload] → [Parse] → [Chunk] → [Embed] → [Milvus] → [Retrieve] → [RAG] → [Generate]
   │          │          │          │          │           │           │         │
   │          │          │          │          │           │           │         └──  Course
   │          │          │          │          │           │           │              Summary
   │          │          │          │          │           │           │              Flashcard
   │          │          │          │          │           │           │              Mindmap
   ▼          ▼          ▼          ▼          ▼           ▼           ▼
 file_id   raw_text   chunks     vectors   indexed     top_k       LLM prompt
                                                +Zep(ctx)         + Citation
```

## 5. Non-Negotiable Gates (Tóm tắt cho agents)
1. **Mọi API input phải validate format** — chỉ chấp nhận `.pdf`, `.docx`, `.txt`.
2. **Mọi output AI phải có trường `citations`** — mỗi citation phải trace được về chunk_id trong Milvus.
3. **Không được gọi LLM trực tiếp từ Frontend** — tất cả qua FastAPI.
4. **Backend chỉ dùng `uv`** để quản lý Python dependencies (không pip).