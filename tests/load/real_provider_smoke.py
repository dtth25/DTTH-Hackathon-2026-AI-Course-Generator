"""Capped seven-job staging smoke against the official OpenRouter endpoint.

Run only in a disposable production-like staging stack. The script never prints
credentials, provider responses, prompts, source text, tokens, or raw chunk ids.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User
from app.services.database import SessionLocal


BASE_URL = os.environ.get("REAL_SMOKE_BASE_URL", "http://frontend:3000")
PASSWORD = os.environ.get("REAL_SMOKE_PASSWORD", "")
BUDGET_USD = float(os.environ.get("REAL_SMOKE_BUDGET_USD", "0.35"))
USER_COUNT = 5
TERMINAL = {"succeeded", "failed", "cancelled"}

# Keep the paid smoke output compact and free of job identifiers. The final JSON
# summary is the only operator-facing output from this script.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _provider_usage() -> tuple[float, float | None]:
    response = httpx.get(
        f"{settings.OPENROUTER_BASE_URL}/key",
        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        timeout=settings.OPENROUTER_PREFLIGHT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    usage = data.get("usage")
    remaining = data.get("limit_remaining")
    if not isinstance(usage, (int, float)) or isinstance(usage, bool):
        raise RuntimeError("Provider usage is unavailable; paid smoke is blocked.")
    if remaining is not None and (
        not isinstance(remaining, (int, float)) or isinstance(remaining, bool)
    ):
        raise RuntimeError("Provider capacity is invalid; paid smoke is blocked.")
    return float(usage), None if remaining is None else float(remaining)


def _seed_users() -> None:
    if len(PASSWORD) < 12:
        raise RuntimeError("REAL_SMOKE_PASSWORD must contain at least 12 characters.")
    hashed = get_password_hash(PASSWORD)
    with SessionLocal() as db:
        for number in range(1, USER_COUNT + 1):
            email = f"provider-smoke-{number:02d}@example.com"
            user = db.query(User).filter(User.email == email).one_or_none()
            if user is None:
                db.add(
                    User(
                        email=email,
                        hashed_password=hashed,
                        is_verified=True,
                        is_active=True,
                    )
                )
        db.commit()


def _login(client: httpx.Client, number: int) -> str:
    response = client.post(
        "/api/auth/login",
        json={
            "email": f"provider-smoke-{number:02d}@example.com",
            "password": PASSWORD,
        },
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Staging login returned no access token.")
    return token


def _poll_job(
    client: httpx.Client, token: str, job_id: str, timeout_seconds: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    headers = {"Authorization": f"Bearer {token}"}
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}", headers=headers)
        response.raise_for_status()
        body = response.json()
        if body.get("status") in TERMINAL:
            return body
        time.sleep(2)
    raise RuntimeError("A capped smoke job did not reach a terminal state in time.")


def _upload(number: int) -> dict[str, str]:
    source = (
        f"Provider smoke document {number}. "
        "The verified lesson states that bounded queues protect interactive traffic, "
        "worker isolation prevents video rendering from blocking document ingestion, "
        "and every generated claim must remain grounded in the uploaded document. "
    ) * 8
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        token = _login(client, number)
        response = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"files": (f"provider-smoke-{number}.txt", source, "text/plain")},
        )
        response.raise_for_status()
        body = response.json()
        state = _poll_job(client, token, body["job_id"], 600)
        if state.get("status") != "succeeded":
            raise RuntimeError("A capped ingestion job failed.")
        return {"token": token, "course_id": body["course_id"]}


def _generate(kind: str, uploaded: dict[str, str]) -> str:
    if kind == "book":
        path = "/api/generate-book"
        payload = {"course_id": uploaded["course_id"], "detail_level": "Tóm tắt"}
    else:
        path = "/api/generate-quiz"
        payload = {
            "course_id": uploaded["course_id"],
            "quantity": 3,
            "difficulty": "easy",
        }
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        response = client.post(
            path,
            headers={"Authorization": f"Bearer {uploaded['token']}"},
            json=payload,
        )
        response.raise_for_status()
        state = _poll_job(client, uploaded["token"], response.json()["job_id"], 900)
        if state.get("status") != "succeeded":
            raise RuntimeError("A capped generation job failed.")
    return uploaded["course_id"]


def _collect_chunk_ids(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source_chunk_ids" and isinstance(item, list):
                found.extend(chunk_id for chunk_id in item if isinstance(chunk_id, str))
            else:
                found.extend(_collect_chunk_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_chunk_ids(item))
    return found


def _verify_grounding(course_id: str) -> None:
    # Artifact JSON is persisted beside the uploaded course under UPLOAD_DIR.
    # OUTPUT_DIR only contains rendered/exported files and therefore cannot be
    # used to validate the internal source references.
    root = Path(settings.UPLOAD_DIR) / course_id
    references: list[str] = []
    for path in root.rglob("*.json"):
        try:
            references.extend(_collect_chunk_ids(json.loads(path.read_text("utf-8"))))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    if not references or any(not item.startswith(f"{course_id}_") for item in references):
        raise RuntimeError("Internal grounding validation failed.")


def main() -> None:
    if settings.ENVIRONMENT != "production":
        raise RuntimeError("Real-provider smoke requires a production-like staging stack.")
    if settings.OPENROUTER_BASE_URL != "https://openrouter.ai/api/v1":
        raise RuntimeError("Real-provider smoke requires the official endpoint.")
    if BUDGET_USD <= 0 or BUDGET_USD > 0.50:
        raise RuntimeError("REAL_SMOKE_BUDGET_USD must be within (0, 0.50].")

    usage_before, remaining = _provider_usage()
    if remaining is not None and remaining <= 0:
        raise RuntimeError("Provider capacity is not positive; paid smoke is blocked.")
    _seed_users()

    with ThreadPoolExecutor(max_workers=USER_COUNT) as pool:
        uploads = list(pool.map(_upload, range(1, USER_COUNT + 1)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        grounded_courses = list(
            pool.map(lambda item: _generate(*item), (("book", uploads[0]), ("quiz", uploads[1])))
        )
    for course_id in grounded_courses:
        _verify_grounding(course_id)

    time.sleep(5)
    usage_after, _ = _provider_usage()
    observed_cost = max(0.0, usage_after - usage_before)
    if observed_cost > BUDGET_USD:
        raise RuntimeError("Observed provider cost exceeded the predeclared smoke budget.")
    print(
        json.dumps(
            {
                "jobs": 7,
                "succeeded": 7,
                "grounded_artifacts": 2,
                "provider_cost_usd": round(observed_cost, 6),
                "budget_usd": BUDGET_USD,
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
