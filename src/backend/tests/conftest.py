"""Shared pytest fixtures and configuration for backend tests."""

import os
import hashlib
import math
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models.course import Course  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.email_otp import EmailOtpCode  # noqa: F401
from app.services.cache import cache
from app.services.database import Base, get_db
from main import app

import app.services.database as db_service

# Setup in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db_service.engine = engine
db_service.SessionLocal = TestingSessionLocal


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
_test_client = TestClient(app)

TEST_UPLOAD_DIR = "test_uploads_tmp"
settings.UPLOAD_DIR = TEST_UPLOAD_DIR

# Keep pytest vector state isolated from local development data. The autouse fixture below
# injects an explicit deterministic embedding service for every test collection, so tests
# exercise the same explicit-vector Chroma boundary without provider calls or ambient
# default embedding functions.
TEST_CHROMA_DIR = "test_chroma_tmp"
settings.CHROMA_PERSIST_DIR = TEST_CHROMA_DIR
settings.CHROMA_COLLECTION_NAME = "test_ai_course_chunks"


class DeterministicTestEmbeddings:
    """Offline explicit vectors injected by pytest; never contacts a provider."""

    model = "deterministic-test-v1"
    dimensions = 32
    normalization_version = "test-exact-v1"

    def embed_texts(self, texts, *, model, dimensions, cache_scope):
        assert model == self.model
        assert dimensions == self.dimensions
        vectors = []
        for text in texts:
            vector = [0.0] * dimensions
            for token in text.casefold().split():
                digest = hashlib.sha256(token.strip(".,:;!?()[]{}\"").encode()).digest()
                vector[int.from_bytes(digest[:2], "big") % dimensions] += 1.0
            length = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / length for value in vector])
        return vectors


def _clean_upload_dir():
    os.makedirs(TEST_UPLOAD_DIR, exist_ok=True)
    for root, dirs, files in os.walk(TEST_UPLOAD_DIR, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except Exception:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except Exception:
                pass


@pytest.fixture(autouse=True)
def setup_database_and_storage(monkeypatch, tmp_path):
    """Create tables before each test and drop them after, clean upload dir."""
    from app.routers import generation as generation_router
    from app.services import vector_store
    from app.services.vector_store import close_vector_store

    close_vector_store()
    monkeypatch.setattr(
        vector_store,
        "_build_embedding_function",
        lambda: DeterministicTestEmbeddings(),
    )
    monkeypatch.setattr(settings, "EMBEDDING_CACHE_DIR", str(tmp_path / "embedding-cache"))
    generation_router._generator_instance = None
    settings.CHROMA_COLLECTION_NAME = f"test_chunks_{uuid.uuid4().hex}"
    Base.metadata.create_all(bind=engine)
    cache._store.clear()
    _clean_upload_dir()
    yield
    generation_router._generator_instance = None
    close_vector_store()
    Base.metadata.drop_all(bind=engine)
    _clean_upload_dir()


TEST_OTP_CODE = "000000"


@pytest.fixture(autouse=True)
def stub_email_delivery(monkeypatch):
    """Tests have no real Resend key configured — fix the OTP code so tests can complete
    the register->verify-email flow deterministically, and no-op the actual send so it
    doesn't hit the network or raise EmailNotConfiguredError."""
    from app.services import email_service, otp_service

    monkeypatch.setattr(otp_service, "generate_code", lambda: TEST_OTP_CODE)
    monkeypatch.setattr(email_service, "send_verification_code", lambda *a, **k: None)
    monkeypatch.setattr(email_service, "send_password_reset_code", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def stub_document_provider_preflight(monkeypatch):
    """Keep document/vector tests local; dedicated provider-health tests cover the preflight."""
    from datetime import UTC, datetime

    from app.services.provider_health import ProviderHealth

    monkeypatch.setattr(
        "app.services.document_processor.get_openrouter_health",
        lambda **_: ProviderHealth(
            available=True,
            error_code=None,
            checked_at=datetime.now(UTC),
            limit=None,
            limit_remaining=None,
            limit_reset=None,
            content_model_available=True,
            embedding_model_available=True,
        ),
    )



@pytest.fixture
def client():
    """Provide shared TestClient instance to test functions without importing conftest."""
    return _test_client


@pytest.fixture
def test_upload_dir():
    """Provide test upload directory path."""
    return TEST_UPLOAD_DIR
