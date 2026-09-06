"""Capped seven-job staging smoke against the official OpenRouter endpoint.

Run only in a disposable production-like staging stack. The script never prints
credentials, provider responses, prompts, source text, tokens, or raw chunk ids.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from app.models.provider_call import ProviderCall, ProviderTestBudget
from app.services.provider_usage import BudgetLimitError, reserve_test_budget, settle_test_budget, verified_request_bound
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
RUN_ID = str(uuid4())
TERMINAL = {"succeeded", "failed", "cancelled"}

# Keep the paid smoke output compact and free of job identifiers. The final JSON
# summary is the only operator-facing output from this script.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _provider_preflight() -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"}
    snapshots = {}
    for endpoint in ('key', 'credits', 'models'):
        response = httpx.get(f"{settings.OPENROUTER_BASE_URL}/{endpoint}", headers=headers,
                             timeout=settings.OPENROUTER_PREFLIGHT_TIMEOUT_SECONDS)
        response.raise_for_status()
        snapshots[endpoint] = response.json().get('data')
    key, credits = snapshots['key'], snapshots['credits']
    if not isinstance(key, dict) or not isinstance(credits, dict):
        raise RuntimeError('Provider capacity unavailable; smoke blocked.')
    remaining = key.get('limit_remaining')
    account_remaining = Decimal(str(credits['total_credits'])) - Decimal(str(credits['total_usage']))
    if not account_remaining.is_finite() or account_remaining <= 0 or (remaining is not None and Decimal(str(remaining)) <= 0):
        raise RuntimeError('Provider capacity not positive; smoke blocked.')
    selected = {settings.OPENROUTER_MODEL, settings.OPENROUTER_BOOK_MODEL or settings.OPENROUTER_MODEL,
                settings.OPENROUTER_EMBEDDING_MODEL}
    prices = {item['id']: item.get('pricing') for item in snapshots['models'] if item.get('id') in selected}
    if set(prices) != selected or any(not value for value in prices.values()):
        raise RuntimeError('Current model pricing unavailable; smoke blocked.')
    return {'pricing': prices, 'pricing_source': 'https://openrouter.ai/api/v1/models',
            'pricing_checked_at': datetime.now(UTC).isoformat()}


def _reserve_smoke(run_id):
    # No flag or user-supplied estimate can bypass unresolved billing semantics.
    # A complete seven-job envelope must include ingestion/OCR, query embeddings,
    # outline, all required chapters, title/quiz schemas, and same-model retries.
    with SessionLocal() as db:
        if db.scalar(select(ProviderTestBudget.run_id).where(ProviderTestBudget.state.in_(['active', 'blocked_unknown']))):
            raise BudgetLimitError('An earlier smoke reservation needs reconciliation')
    verified_request_bound(settings.OPENROUTER_BOOK_MODEL or settings.OPENROUTER_MODEL,
        {'messages': [{'role': 'user', 'content': 'Capped smoke plan'}], 'max_tokens': 8192}, 'generation')
    raise BudgetLimitError('A complete source-dependent seven-job allowance is required before dispatch')


def _response_cost(user_ids):
    with SessionLocal() as db:
        rows = db.scalars(select(ProviderCall).where(ProviderCall.user_id.in_(user_ids))).all()
        if not rows or any(row.cost is None for row in rows):
            return None
        return sum((Decimal(row.cost) / Decimal(1_000_000_000) for row in rows), Decimal('0'))


def _seed_users() -> None:
    if len(PASSWORD) < 12:
        raise RuntimeError("REAL_SMOKE_PASSWORD must contain at least 12 characters.")
    hashed = get_password_hash(PASSWORD)
    with SessionLocal() as db:
        for number in range(1, USER_COUNT + 1):
            email = f"provider-smoke-{RUN_ID}-{number:02d}@example.com"
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
            "email": f"provider-smoke-{RUN_ID}-{number:02d}@example.com",
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

    snapshot = _provider_preflight()
    run_id = RUN_ID
    try:
        upper_bound = _reserve_smoke(run_id)
    except BudgetLimitError:
        print(json.dumps({"status": "blocked_unverified_allowance", **snapshot, "provider_cost_usd": "0"}))
        return
    if not reserve_test_budget(run_id, upper_bound):
        raise RuntimeError("Smoke reservation denied.")
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
    with SessionLocal() as db:
        user_ids = list(db.scalars(select(User.id).where(User.email.like(f"provider-smoke-{RUN_ID}-%@example.com"))))
    observed_cost = _response_cost(user_ids)
    settle_test_budget(run_id, observed_cost)
    if observed_cost is None:
        raise RuntimeError("Unknown response cost; reservation remains held.")
    if observed_cost > BUDGET_USD:
        raise RuntimeError("Observed provider cost exceeded the predeclared smoke budget.")
    print(
        json.dumps(
            {
                "jobs": 7,
                "succeeded": 7,
                "grounded_artifacts": 2,
                "provider_cost_usd": str(observed_cost),
                **snapshot,
                "budget_usd": BUDGET_USD,
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
