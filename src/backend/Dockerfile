FROM python:3.11-slim

# Install a pinned uv release so production builds do not change underneath us.
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv

# python:3.11-slim ships with ZERO system fonts, so PDF export (ReportLab) and video
# frame rendering (Pillow) both fell back to a non-Vietnamese font — diacritics rendered
# as tofu boxes in the container (worked locally only because Windows has Arial). Install
# DejaVu, which has full Vietnamese coverage and lands at exactly the path already listed
# in pdf_utils._FONT_CANDIDATES (/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-cjk fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Compose builds with context ./src so backend remains importable as package `backend`.
COPY backend/pyproject.toml backend/uv.lock ./backend/

WORKDIR /app/backend
ENV UV_HTTP_TIMEOUT=300
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

WORKDIR /app
COPY backend ./backend

# The backend imports its own modules as top-level `app.*` (see main.py:
# `from app.core.config import ...`). Because pyproject.toml has no [build-system],
# `app` is NOT installed as a package — it only resolves when cwd/PYTHONPATH is the
# backend dir itself. Running `backend.main:app` from /app crashes with
# `ModuleNotFoundError: No module named 'app'` (Python looks for /app/app, but the
# package lives at /app/backend/app). So run exactly like the documented local
# command: cwd + PYTHONPATH at /app/backend, entrypoint `main:app`.
ENV PYTHONPATH=/app/backend
WORKDIR /app/backend

EXPOSE 8000

# Run DB migrations before starting the server. There is no create_all() anywhere and
# the lifespan only seeds the admin — a fresh deploy has an EMPTY sqlite file, so without
# `alembic upgrade head` every query fails with "no such table: users". alembic lives in
# the main deps (installed even with --no-dev) and its script_location is %(here)s-relative,
# so it resolves from this WORKDIR. `exec` hands PID 1 / signals to uvicorn. Everything runs
# from /app/backend so alembic and the app agree on the same ./data/app.db (on the volume).
CMD ["sh", "-c", "uv run --project . alembic upgrade head && exec uv run --project . uvicorn main:app --host 0.0.0.0 --port 8000"]
