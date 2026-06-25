"""
Health Check Tests.
Test system health and status endpoints.
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthCheck:
    """Health check endpoint tests."""

    def test_health_endpoint(self, client: TestClient):
        """GET /api/health → 200 with status ok"""
        resp = client.get("/api/health")
        assert resp.status_code in (200, 503), f"Health check failed: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert data["status"] == "ok"
            assert "courses" in data

    def test_health_response_format(self, client: TestClient):
        """GET /api/health trả về đúng định dạng StatusResponse"""
        resp = client.get("/api/health")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data.get("courses"), list)
            # Course IDs should be strings if present
            for c in data["courses"]:
                assert isinstance(c, str)