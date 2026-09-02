# HackaGen

HackaGen biến một hoặc nhiều tài liệu `.pdf`, `.docx`, `.txt` thành một **Document-to-Study-Pack** kết nối 4 học liệu cốt lõi: Book (Study Guide PDF), Slide, Quiz và Vid.

Code hiện tại là source of truth. README này mô tả đúng flow đang chạy trong repo: Chroma local, Auth v2, FastAPI backend, Next.js frontend và các generated artifacts lưu trên filesystem local.

## Tech Stack

| Layer | Công nghệ |
| --- | --- |
| Frontend | Next.js App Router, React 19, Tailwind CSS v4, shadcn/base-ui, lucide-react |
| Backend | FastAPI, Python 3.11+, LangChain |
| Dependency | `uv` cho backend, npm cho frontend |
| Vector DB | Chroma local persistent DB, bắt buộc cho local/dev demo |
| Persistence | Local filesystem JSON/generated files |
| Auth | JWT bearer token + HttpOnly cookie, user ownership, admin routes |
| AI Model | OpenRouter paid-only: `google/gemini-2.5-pro` cho toàn bộ feature |
| Embedding | OpenRouter `openai/text-embedding-3-small` |

## Product Surface

- **Study Pack Dashboard:** View tổng hợp từ cùng một document/course: Book (Study Guide PDF), Slide, Quiz, Vid, readiness, quality scores và grounding.
- **Book / Study Guide:** View theo chương/bài và file PDF download.
- **Slide:** Viewer từng slide và file PPTX download.
- **Quiz:** MCQ tương tác; đáp án/explanation chỉ hiện khi người học review hoặc submit; có answer-key PDF.
- **Vid:** Video dạng slide + voiceover, metadata JSON và MP4 download hoặc lỗi render rõ ràng.

Book, Slide, Quiz và Vid là 4 endpoint generation trực tiếp và duy nhất của Study Pack.

## Prerequisites

Cài các công cụ sau trước khi setup từ máy sạch:

- Python 3.11+.
- `uv`.
- Node.js 20+ và npm.
- OpenRouter API key (`OPENROUTER_API_KEY`).
- Không cần cài toolchain build native (C++ Build Tools/gcc) trên bất kỳ OS nào — `chromadb` (pin hiện tại trong `uv.lock`) ship sẵn wheel prebuilt cho Linux (manylinux x86_64/aarch64), macOS và Windows.
- Docker Engine + Docker Compose plugin nếu muốn chạy bằng Docker (khuyến nghị cho deploy lên Linux server — xem mục "Deploy lên Linux server").

Kiểm tra nhanh:

```bash
python --version
uv --version
node --version
npm --version
```

## Environment Setup

Tạo file env ở root repo:

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env -Force
```

Sửa `.env` và điền ít nhất:

```bash
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=google/gemini-2.5-pro
OPENROUTER_SLIDE_MODEL=google/gemini-2.5-pro
OPENROUTER_QUIZ_MODEL=google/gemini-2.5-pro
JWT_SECRET=change-this-dev-secret
VECTOR_DB_PROVIDER=chroma
CHROMA_PERSIST_DIR=./data/chroma
CHROMA_COLLECTION_NAME=ai_course_chunks
DATABASE_URL=sqlite:///./data/app.db
```

Nếu muốn bootstrap admin local/dev:

```bash
CREATE_DEFAULT_ADMIN=true
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-this-password
```

Copy file mẫu rồi điền key/secrets:

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env -Force
```

Điền `OPENROUTER_API_KEY` (bắt buộc). `OPENROUTER_MODEL` và mọi feature override mặc định đều là `google/gemini-2.5-pro`, để Book, Slide, Quiz, Vid và OCR dùng cùng mức chất lượng. Mỗi content/OCR call dùng trực tiếp model đã cấu hình cho feature đó và retry đúng model một lần nếu provider lỗi hoặc JSON không đúng schema; không chuyển sang model khác.

Backend chỉ load `.env` ở root repo bằng đường dẫn tuyệt đối. Khởi động lại backend sau khi đổi env để startup log hiển thị content model và embedding model đang active.

`PROCESSING_EXECUTION_MODE=inline` và `INLINE_PROCESSING_RECOVERY_ENABLED=true` trong `.env.example` chỉ dành cho local/dev chạy **một** process FastAPI: khi restart, app có thể đánh dấu retryable các job inline bị gián đoạn. Nếu deploy nhiều API process/replica, phải dùng `PROCESSING_EXECUTION_MODE=distributed` và `INLINE_PROCESSING_RECOVERY_ENABLED=false`; inline recovery không có lease liên-process. Queue/lease bền vững là phần mở rộng sau này.

## Backend Runbook

One-time setup:

```bash
cd src/backend
uv sync --all-extras
```

Chạy backend từ thư mục `src/backend` (không có `[build-system]` trong `pyproject.toml` nên `uv` không cài `backend`/`app` như package — import `app.*` chỉ resolve khi cwd đúng là `src/backend`):

```bash
uv run --project . uvicorn main:app --reload --port 8000
```

Backend chạy tại `http://127.0.0.1:8000`.

Kiểm tra readiness:

```bash
curl http://127.0.0.1:8000/health
```

Nếu `/health` trả `vector_db.ready=false`, kiểm tra lại `chromadb` và `CHROMA_PERSIST_DIR`. Backend vẫn có thể trả health, nhưng upload/generate sẽ fail cho tới khi Chroma ready.

## Frontend Runbook

One-time setup:

```bash
cd src/frontend
npm install
```

Run dev:

```bash
npm run dev
```

Frontend chạy tại `http://localhost:3000`.

Frontend gọi thẳng backend từ client-side (không qua proxy Next.js). Nếu backend không chạy ở `http://localhost:8000`, set 1 trong 2 biến (tương đương nhau) trước khi build/dev:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

Đây là biến `NEXT_PUBLIC_*` nên Next.js **inline lúc `next build`**, không đọc runtime — đổi giá trị bắt buộc phải build lại (`npm run build` hoặc, với Docker, `docker compose build frontend`), restart không đủ.

Demo production mode để không thấy Next.js dev indicator:

```bash
npm run build
npm run start
```

## First User Flow

1. Mở `http://localhost:3000/register` để tạo user, hoặc bật `CREATE_DEFAULT_ADMIN=true` rồi đăng nhập admin.
2. Upload một hoặc nhiều file `.pdf`, `.docx`, `.txt`.
3. Poll status đến khi document/course `completed` hoặc `ready`.
4. Mở dashboard Study Pack hoặc generate Book, Slide, Quiz, Vid.
5. Kiểm tra download: Book PDF, Slide PPTX, Quiz answer-key PDF, Vid MP4 nếu render thành công.

## Docker Compose (Backend + Frontend)

```bash
cp .env.example .env
# Sửa .env và điền OPENROUTER_API_KEY/JWT_SECRET
docker compose up -d --build
```

Chạy cả 2 service (`backend` cổng 8000, `frontend` cổng 3000) cùng lúc. Dữ liệu bền vững (Chroma vectors, SQLite, upload/artifact, embedding cache) được mount ra `./data/` trên host — restart container không mất dữ liệu.

## Deploy lên Linux server

Cách deploy khuyến nghị cho server thật (kể cả server trường) là Docker Compose ở trên. Ghi chú vận hành:

**Prerequisites**: chỉ cần Docker Engine + Docker Compose plugin. Không cần cài build toolchain (gcc/C++) — image build sẵn dùng wheel/base image chuẩn.

**Chỉ có ĐÚNG 1 file env cần quan tâm khi deploy: `.env` ở root repo.** Không phải `src/backend/.env` (không tồn tại, đừng tạo — backend luôn resolve `.env` theo đường dẫn tuyệt đối về root, bất kể cwd). Không phải `src/frontend/.env` (file đó chỉ để `npm run dev` local dùng — **Docker build không đọc nó**; giá trị thật được `docker-compose.yml` truyền vào qua build `arg` lấy từ root `.env`, xem `src/frontend/Dockerfile`). Nếu build script nào đó tự chạy `npm run build` trực tiếp trong `src/frontend` (không qua `docker compose build`), nó sẽ **không** thấy `NEXT_PUBLIC_API_BASE_URL` của root `.env` — đây chính là nguyên nhân bug "frontend gọi localhost:8000 sau khi deploy". Luôn deploy bằng đúng 1 lệnh `docker compose up -d --build` ở root, không tự build tay từng service.

**Kiến trúc mạng**: backend **không** có port nào ra host/internet — cả 2 service nằm chung 1 Docker network tên `hackagen-network`, browser người dùng không bao giờ gọi thẳng backend. Mọi request `/api/*` từ frontend đi qua chính domain của frontend, được `next.config.ts`'s `rewrites()` proxy server-side sang backend qua network nội bộ đó (`BACKEND_INTERNAL_URL=http://backend:8000`, tự cấu hình sẵn trong compose, không cần sửa). Chỉ cần mở/trỏ domain vào **đúng 1 cổng** (`FRONTEND_PORT`, mặc định 3000) ra ngoài. Nếu server đã có sẵn reverse proxy riêng (container khác, ngoài file compose này), attach nó vào network `hackagen-network` (`docker network connect hackagen-network <tên container proxy>`) là gọi được `frontend`/`backend` bằng tên container, không cần qua host port.

**Health check**: cả 2 container có `HEALTHCHECK` built-in của Docker — xem trạng thái bằng `docker compose ps` (cột STATUS hiện `healthy`/`unhealthy`), không cần tự `curl` để kiểm tra. Frontend chỉ start sau khi backend báo `healthy` (`depends_on: condition: service_healthy`).

**Checklist env production** (sửa trong `.env` ở root trước khi build):
- `NEXT_PUBLIC_API_BASE_URL` phải để **RỖNG** (`NEXT_PUBLIC_API_BASE_URL=`) — rỗng nghĩa là browser gọi same-origin rồi được proxy nội bộ như trên. Nếu điền domain/IP thật vào đây, browser sẽ cố gọi thẳng cổng 8000 và **fail** vì cổng đó không public. Next.js inline biến này lúc `next build`, nên đổi giá trị bắt buộc phải `docker compose build frontend` lại, restart container không đủ.
- `ALLOWED_ORIGINS` không còn bắt buộc cho luồng browser chính (browser giờ gọi same-origin, không phải cross-origin nữa) — có thể để nguyên default, không cần sửa.
- `OPENROUTER_API_KEY` phải là key thật, không phải placeholder.
- `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD` + `EMAIL_FROM_ADDRESS` phải là tài khoản Gmail thật (SMTP_PASSWORD là "App Password", không phải mật khẩu đăng nhập thường), và `EMAIL_DEV_FALLBACK=false` (hoặc bỏ hẳn dòng này) — bật `true` ở production nghĩa là user đăng ký "thành công" nhưng không ai nhận được mã xác thực.
- Cân nhắc bật `AUTH_COOKIE_SECURE=true` khi server đã có HTTPS.
- Nếu cổng 3000 đã bị chiếm trên server (ví dụ máy chạy nhiều app sau cùng 1 reverse proxy), set `FRONTEND_PORT=` trong `.env` — không cần sửa `docker-compose.yml`. Backend không có host port nên không có gì để đổi ở đó. Repo này **không** tự chạy reverse proxy/HTTPS nào — nếu server đã có sẵn nginx/Caddy riêng, chỉ cần trỏ nó vào đúng `FRONTEND_PORT` (hoặc attach thẳng vào network `hackagen-network`, xem phần Kiến trúc mạng ở trên).

**Chạy**: `docker compose up -d --build` dựng cả backend + frontend. Sau **mọi** lần `git pull` có đổi code, chạy lại đúng lệnh này (không chỉ `docker compose restart`) — đặc biệt bắt buộc nếu đổi bất kỳ biến `NEXT_PUBLIC_*` nào, vì nó bị bake cứng vào frontend lúc build.

**Dữ liệu**: toàn bộ state bền vững nằm ở `./data/` trên host (`app-data/` = Chroma + SQLite, `uploads/`, `outputs/`, `cache/`) — đây là phần cần backup định kỳ.

**Ngoài phạm vi repo**: reverse proxy (nginx/Caddy) và HTTPS/TLS đứng trước cổng 3000 là trách nhiệm người vận hành server — repo này chưa có config sẵn cho phần đó. Chỉ cần route đúng 1 cổng 3000, không cần route cổng 8000 nữa.

## Local Architecture

Local/dev mode hiện tại — **không có provider-abstraction layer nào**, mỗi thứ dưới đây là 1 implementation cụ thể duy nhất, không phải 1 trong nhiều provider chọn được qua env:

- Frontend: Next.js App Router trong `src/frontend`.
- Backend: FastAPI trong `src/backend`.
- Vector DB: Chroma, code thật ở `src/backend/app/services/vector_store.py`, lưu local tại `CHROMA_PERSIST_DIR`. Không có interface/2nd provider nào khác trong repo.
- File storage: filesystem thô (`os.path` + `UPLOAD_DIR`), rải rác trong `document_processor.py`/`generator.py`/`upload.py` — không có service module riêng.
- Job queue: FastAPI `BackgroundTasks` gọi trực tiếp trong router — không có queue/broker thật.
- Cache: `src/backend/app/services/cache.py` — dùng thật cho JWT blacklist + document/embedding cache.
- Database: SQLite qua `DATABASE_URL`.
- Auth: Bearer JWT + HttpOnly cookie; protected APIs require active user.

Postgres, Redis worker/cache, S3/R2 storage, Qdrant/Milvus/pgvector chỉ là hướng mở rộng tương lai — **chưa có code nào** cho các provider này. `.env.example` giữ lại tên biến (`VECTOR_DB_PROVIDER`, `STORAGE_PROVIDER`, `JOB_QUEUE_PROVIDER`, `CACHE_PROVIDER`, `MILVUS_*`, `S3_*`, `REDIS_URL`...) làm chỗ đặt tên sẵn cho lần thực sự implement, nhưng set chúng trong `.env` hôm nay không có tác dụng gì — không có field `Settings` nào đọc các biến đó.

## Chroma Notes

Chroma là vector database bắt buộc, và là **provider duy nhất** trong code hiện tại (`app/services/vector_store.py`) — không có FAISS hay `vector_db/` package nào trong repo để chuyển sang; `VECTOR_DB_PROVIDER` không phải field `Settings` nào và không có tác dụng gì (xem "Local Architecture" ở trên).

Chroma được dùng vì app cần:

- Persistent collection local.
- Filter theo `document_id` và `user_id`.
- Metadata `chunk_type`, `quality_score`, `use_for_generation`.
- Delete/copy document chunks cho ownership và duplicate-upload cache.

Data mặc định nằm dưới `src/data/chroma` nếu backend start từ `src`. Muốn clear demo vectors thì stop backend rồi xóa folder đó.

## API Flow

Các route chính:

- Readiness: `GET /health`.
- Auth: `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me` và alias `/api/auth/...`.
- Admin users: `/admin/users`, `/admin/users/{user_id}`, `/admin/users/{user_id}/disable|enable|make-admin|make-user|reset-password`.
- Upload/status: `POST /api/upload`, `GET /documents/{document_id}/status`, `GET /api/course/{course_id}/status`.
- Source grounding: `GET /documents/{document_id}/sources`, alias `/api/documents/{document_id}/sources`.
- Direct generation: `POST /api/generate-book`, `/api/generate-slide`, `/api/generate-quiz`, `/api/generate-vid`.
- Study Pack/course outputs: `/api/course/{course_id}/study-pack`, `/readiness`, `/stats`.
- Saved artifacts: `/api/course/{course_id}/book`, `/book.pdf`, `/slide`, `/slide.pptx`, `/quiz`, `/quiz-key.pdf`, `/vid`, `/vid/file`, `/files`.
- Delete: `DELETE /api/courses/{course_id}`, `DELETE /api/documents/{document_id}`, `DELETE /documents/{document_id}`.

Upload dùng multipart field `files` cho multi-document. Legacy field `file` vẫn được hỗ trợ cho single-file client cũ.

## Security & Metadata Policy

- Frontend không gọi LLM trực tiếp. Mọi AI call đi qua FastAPI.
- Upload/generation/output/delete yêu cầu active user, trừ health/demo public routes được đánh dấu rõ.
- User thường chỉ truy cập document/output của mình; admin có quyền quản trị/hỗ trợ.
- Generation response không được lộ raw/internal `source`, `chunk_id`, `citations` hoặc debug markers.
- `source_chunk_ids` được giữ trong artifact metadata để UI truy vấn grounding.
- Source panel có thể hiển thị `page` + excerpt sạch; `source_chunk_id` chỉ hiện khi developer mode bật và requester là admin.

## Test Gates

Backend:

```bash
cd src/backend
uv run ruff check .
uv run pytest tests
```

Frontend:

```powershell
cd src/frontend
npm run audit:brand
npm run capture:product
npm run test:visual
npm test -- --run
npm run lint
npm run build
```

`npm run capture:product` chỉ cập nhật ảnh trong `src/frontend/public/product` sau khi fixture đã được kiểm tra để không chứa tên, email, tên tệp hoặc nội dung tài liệu thật. Mở và xem lại cả ba ảnh sau mỗi lần capture. Chỉ cập nhật visual baselines sau một thay đổi thiết kế có chủ đích, đã được duyệt; không dùng update snapshot để che một regression ngoài ý muốn.

Manual smoke trước demo:

- Register/login thành công.
- Upload ít nhất 2 tài liệu.
- Poll đến khi tài liệu sẵn sàng.
- Dashboard Study Pack hiển thị Book, Slide, Quiz, Vid/readiness/grounding.
- Generate đủ Book, Slide, Quiz, Vid.
- Generate output mới không làm mất output cũ.
- Slide có Next/Previous và PPTX download.
- Quiz chọn đáp án được, không lộ đáp án/explanation trước submit/review.
- Book đọc được trong web và tải PDF được.
- Vid trả player/download MP4 hoặc lỗi rõ ràng nếu render thất bại.
- User A không truy cập được document/output của User B; admin có thể hỗ trợ/quản trị.

## Non-Negotiable Gates

1. **Connected Study Pack:** Book (Study Guide PDF), Slide, Quiz, Vid, readiness/quality/grounding phải xuất phát từ cùng nguồn cấu trúc.
2. **Four Direct Generation Endpoints:** Book, Slide, Quiz, Vid là 4 endpoint generation trực tiếp và duy nhất của Study Pack.
3. **No Additional Chats:** Không có chat tự do hoặc custom prompt độc lập ngoài hệ sinh thái Study Pack.
4. **No Raw Public Source Metadata:** Generation response không lộ raw/internal `source`, `chunk_id`, `citations` hoặc debug markers; `source_chunk_ids` và source excerpt/page display theo API contract.
5. **Grounded Generation:** Output phải dựa trên retrieved chunks từ Chroma/local index sau khi lọc noisy/TOC/debug text.
6. **Auth & Ownership:** Protected APIs require active user; regular users only access their own documents/outputs, admins can manage/support.
7. **File Validation:** Chỉ chấp nhận `.pdf`, `.docx`, `.txt`, không file rỗng, không quá 50MB mỗi file.
8. **Backend-only AI:** Frontend không gọi LLM trực tiếp.
9. **Code Style:** Backend Ruff-compatible, Frontend ESLint/build không lỗi.
