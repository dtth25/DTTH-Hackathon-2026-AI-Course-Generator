# DTTH-Hackathon-2026 AI Course Generator

Biến tài liệu thô (PDF, DOCX, TXT) thành hệ sinh thái học tập đa phương tiện — bài học, tóm tắt, flashcards, mindmap — tự động bằng AI.

## Tech Stack

| Layer | Công nghệ |
|-------|-----------|
| Frontend | Next.js 14+ (App Router), Tailwind CSS |
| Backend | FastAPI (Python 3.11+) |
| Vector DB | Milvus (RAG + Citation) |
| Memory | Zep (Session context) |
| AI Model | Claude 3.5 Sonnet / GPT-4o |

## Cấu trúc thư mục

```
├── docs/                    # Tài liệu thiết kế
│   ├── PRD.md               # Product Requirements Document
│   ├── api_contract.md      # API Contract (v1.0)
│   └── architecture_design.md   # Architecture & Data Flow
├── src/
│   ├── backend/             # FastAPI application
│   │   ├── main.py          # Entry point
│   │   └── services/        # Business logic
│   ├── frontend/            # Next.js application
│   └── shared/              # Shared types/constants
├── tests/                   # Test suites
├── AGENTS.md                # Agent orchestration protocol
├── ROOT_CONTEXT.md          # Project context for AI agents
└── .env.example             # Environment variables template
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Milvus (local hoặc cloud)
- API key: của Google

### Backend

```bash
# Clone & cd vào project
cd src/backend

# Tạo virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/Mac

# Cài dependencies (dùng uv để tối ưu)
pip install uv
uv pip install -r requirements.txt

# Copy env
cp ../../.env.example .env
# Sửa .env với API key của bạn

# Chạy server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd src/frontend
npm install
npm run dev
```

Mở `http://localhost:3000`

### Kiểm tra

```bash
# Backend health check
curl http://localhost:8000/health

# Upload tài liệu
curl -X POST http://localhost:8000/api/upload -F "file=@document.pdf"
```

## Non-Negotiable Gates

1. **Citation-First:** Mọi output AI phải có trường `citations` trace được về chunk trong Milvus.
2. **No-Auth v1:** Không login/thanh toán — tập trung Core AI Pipeline.
3. **File validation:** Chỉ chấp nhận `.pdf`, `.docx`, `.txt`.
4. **Backend call only:** Frontend không gọi LLM trực tiếp, mọi request qua FastAPI.

## Development Workflow

Xem chi tiết tại [`AGENTS.md`](AGENTS.md) — quy trình phối hợp giữa các vai (Lead, Backend, Frontend, QA).