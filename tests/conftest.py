"""
Fixtures for E2E Integration Tests.
Starts frontend + backend + Milvus for full-stack testing.
"""
import os
import subprocess
import time
import pytest
import requests
from typing import Generator


FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def backend_server() -> Generator[str, None, None]:
    """Start FastAPI backend server."""
    proc = subprocess.Popen(
        ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=os.path.join(os.path.dirname(__file__), "..", "src", "backend"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for backend to be ready
    for _ in range(30):
        try:
            resp = requests.get(f"{BACKEND_URL}/api/health", timeout=2)
            if resp.status_code in (200, 503):
                break
        except requests.ConnectionError:
            pass
        time.sleep(1)

    yield BACKEND_URL
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="session")
def frontend_server() -> Generator[str, None, None]:
    """Start Next.js frontend server."""
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=os.path.join(os.path.dirname(__file__), "..", "src", "frontend"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for frontend to be ready
    for _ in range(60):
        try:
            resp = requests.get(FRONTEND_URL, timeout=2)
            if resp.status_code == 200:
                break
        except requests.ConnectionError:
            pass
        time.sleep(2)

    yield FRONTEND_URL
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def e2e_client(backend_server, frontend_server) -> dict:
    """Provide both URLs for E2E tests."""
    return {
        "frontend": frontend_server,
        "backend": backend_server,
    }


@pytest.fixture(scope="module")
def sample_pdf_path() -> str:
    """Path to sample PDF for E2E tests."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", "sample.pdf")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        # Create minimal PDF
        with open(path, "wb") as f:
            f.write(
                b"%PDF-1.4\n"
                b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
                b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
                b"xref\n0 4\n0000000000 65535 f \n"
                b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
                b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
                b"startxref\n180\n%%%%EOF"
            )
    return path