FROM python:3.11-slim

# Install system dependencies & fonts for PDF generation
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-stix \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Compose builds with context ./src so backend remains importable as package `backend`.
COPY backend/pyproject.toml backend/uv.lock ./backend/

WORKDIR /app/backend
RUN uv sync --frozen --no-dev

WORKDIR /app
COPY backend ./backend

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uv", "run", "--project", "backend", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
