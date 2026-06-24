# DTTH-Hackathon-2026 AI Course Generator

Biến tài liệu thô (PDF, DOCX, TXT) thành đúng 4 output học tập: **Book, Slide, Quiz, Vid**.

## Tech Stack

| Layer | Công nghệ |
| --- | --- |
| Frontend | Next.js App Router, React 19, Tailwind CSS v4, shadcn/base-ui, lucide-react |
| Backend | FastAPI, Python 3.11+, LangChain |
| Dependency | `uv` cho backend, npm cho frontend |
| Vector DB | FAISS local disk-based |
| Persistence | Local filesystem JSON/generated files |
| AI Model | Gemini `gemini-2.5-flash` |
| Embedding | Gemini `models/embedding-001` via LangChain batch embeddings |

## Public Outputs

- **Book:** JSON view theo chương/bài và file PDF download.
- **Slide:** Slide JSON gồm title, content, layout hint và image suggestion.
- **Quiz:** MCQ kèm đáp án đúng và giải thích.
- **Vid:** Video học tập dạng slide + voiceover, có metadata JSON và MP4.

## Cấu Trúc Thư Mục

```text
├── docs/
│   ├── PRD.md
│   ├── api_contract.md
│   └── architecture_design.md
├── src/
│   ├── backend/
│   │   ├── main.py
│   │   ├── core/
│   │   ├── services/
│   │   └── vector_db/
│   └── frontend/
│       ├── src/app/
│       ├── src/components/
│       └── src/lib/
├── AGENTS.md
├── ROOT_CONTEXT.md
├── docker-compose.yml
└── .env.example
```

## Backend Runbook

### One-time setup

```bash
cd src/backend
uv sync --all-extras
```

Tạo environment cho Gemini:

```bash
export GOOGLE_API_KEY="your_gemini_api_key_here"
```

Trên Windows PowerShell:

```powershell
$env:GOOGLE_API_KEY="your_gemini_api_key_here"
```

### Every-time run

Chạy từ thư mục `src` để import path `backend.main` khớp package hiện tại:

```bash
cd src
uv run --project backend uvicorn backend.main:app --reload --port 8000
```

Backend chạy tại `http://localhost:8000`.

## Frontend Runbook

```bash
cd src/frontend
npm install
npm run dev
```

Frontend chạy tại `http://localhost:3000`. Nếu backend không chạy ở port mặc định, set `NEXT_PUBLIC_API_BASE_URL`.

## Docker Backend Option

```bash
cp .env.example .env
# Sửa .env và điền GOOGLE_API_KEY
docker compose up --build backend
```

Runtime files khi chạy Docker được mount vào `runtime/`.

## API Flow

1. `POST /api/upload` với multipart field **`file`** để tạo `course_id`.
2. `GET /api/course/{course_id}/status` để poll đến khi `ready`.
3. Gọi một trong 4 endpoint generation qua FastAPI.
4. Frontend render artifact; Book có thêm link PDF.

Các route chính:
- Health/management: `/api/health`, `/api/courses`, `/api/courses/all`, `DELETE /api/courses/{course_id}`.
- Upload/status: `/api/upload`, `/api/course/{course_id}/status`.
- Generation: `/api/generate-book`, `/api/generate-slide`, `/api/generate-quiz`, `/api/generate-vid`.
- Saved artifacts: `/api/course/{course_id}/book`, `/book.pdf`, `/slide`, `/quiz`, `/vid`, `/vid/file`, `/files`, `/stats`.

## Non-Negotiable Gates

1. **Only 4 Outputs:** Public API/UI/docs chỉ có Book, Slide, Quiz, Vid.
2. **No Additional Chats:** Không có chat tự do hoặc custom prompt độc lập.
3. **No Public Source Metadata:** Public API không trả `page`, `source`, `chunk_id`.
4. **Grounded Generation:** Output phải dựa trên retrieved chunks từ FAISS/local index.
5. **No-Auth v1:** Không login/thanh toán/phân quyền trong Hackathon version.
6. **File validation:** Chỉ chấp nhận `.pdf`, `.docx`, `.txt`, không file rỗng, không quá 50MB.
7. **Backend-only AI:** Frontend không gọi LLM trực tiếp.
