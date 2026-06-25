# DTTH-Hackathon-2026 AI Course Generator

Biến một hoặc nhiều tài liệu PDF, DOCX, TXT thành đúng 4 output học tập: **Book, Slide, Quiz, Vid**.

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
- **Slide:** Viewer từng slide, JSON download và PDF download.
- **Quiz:** MCQ tương tác, không lộ đáp án trước khi nộp bài, JSON download và PDF download.
- **Vid:** Video học tập dạng slide + voiceover, metadata JSON và MP4 download.

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

Khi demo cho người dùng, chạy production mode để không thấy Next.js dev indicator:

```bash
cd src/frontend
npm run build
npm run start
```

## Docker Backend Option

```bash
cp .env.example .env
# Sửa .env và điền GOOGLE_API_KEY
docker compose up --build backend
```

Runtime files khi chạy Docker được mount vào `runtime/`.

## API Flow

1. `POST /api/upload` với multipart field **`files`** để upload một hoặc nhiều tài liệu vào cùng một `course_id`.
2. Legacy field **`file`** vẫn được hỗ trợ cho single-file client cũ.
3. `GET /api/course/{course_id}/status` để poll đến khi `ready`.
4. Gọi một trong 4 endpoint generation qua FastAPI.
5. Frontend render artifact; Book/Slide/Quiz/Vid đều có download tương ứng khi tạo xong.

Các route chính:
- Health/management: `/api/health`, `/api/courses`, `/api/courses/all`, `DELETE /api/courses/{course_id}`.
- Upload/status: `/api/upload`, `/api/course/{course_id}/status`.
- Generation: `/api/generate-book`, `/api/generate-slide`, `/api/generate-quiz`, `/api/generate-vid`.
- Saved artifacts: `/api/course/{course_id}/book`, `/book.pdf`, `/slide`, `/slide.json`, `/slide.pdf`, `/quiz`, `/quiz.json`, `/quiz.pdf`, `/vid`, `/vid/file`, `/files`, `/stats`.

## Test Gates

Backend:

```bash
cd src/backend
uv run ruff check .
uv run pytest tests
```

Frontend:

```bash
cd src/frontend
npm run lint
npm run build
```

Manual smoke trước demo:
- Upload ít nhất 2 tài liệu.
- Poll đến khi tài liệu sẵn sàng.
- Generate đủ Book, Slide, Quiz, Vid.
- Generate output mới không làm mất output cũ.
- Slide có Next/Previous và download.
- Quiz chọn đáp án được, không lộ đáp án trước submit.
- Book đọc được trong web và tải PDF được.
- Vid trả player/download MP4 hoặc lỗi rõ ràng nếu render thất bại.

## Non-Negotiable Gates

1. **Only 4 Outputs:** Public API/UI/docs chỉ có Book, Slide, Quiz, Vid.
2. **No Additional Chats:** Không có chat tự do hoặc custom prompt độc lập.
3. **No Public Source Metadata:** Public API không trả `page`, `source`, `chunk_id`, `citations`.
4. **Grounded Generation:** Output phải dựa trên retrieved chunks từ FAISS/local index.
5. **No-Auth v1:** Không login/thanh toán/phân quyền trong Hackathon version.
6. **File validation:** Chỉ chấp nhận `.pdf`, `.docx`, `.txt`, không file rỗng, không quá 50MB mỗi file.
7. **Backend-only AI:** Frontend không gọi LLM trực tiếp.
