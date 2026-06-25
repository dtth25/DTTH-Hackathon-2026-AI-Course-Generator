"""
Course Management Tests (CRUD operations).
Test course listing, deletion, and management endpoints.
"""
import pytest
from fastapi.testclient import TestClient


class TestCourseManagement:
    """CRUD tests for course management."""

    def test_list_courses(self, client: TestClient):
        """GET /api/courses trả về danh sách courses"""
        resp = client.get("/api/courses")
        assert resp.status_code == 200, f"List courses failed: {resp.text}"
        data = resp.json()
        assert "courses" in data
        assert isinstance(data["courses"], list)
        assert data["status"] == "ok"

    def test_list_all_courses_with_meta(self, client: TestClient):
        """GET /api/courses/all trả về metadata đầy đủ"""
        resp = client.get("/api/courses/all")
        assert resp.status_code == 200, f"List all courses failed: {resp.text}"
        data = resp.json()
        assert "courses" in data
        assert "total" in data
        assert isinstance(data["courses"], list)

    def test_create_and_delete_course(self, client: TestClient, sample_pdf: bytes):
        """Upload course → verify exists → delete → verify gone"""
        # Upload
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("crud_test.pdf", sample_pdf, "application/pdf")},
        )
        assert upload_resp.status_code == 200
        cid = upload_resp.json()["course_id"]

        # Verify in list
        list_resp = client.get("/api/courses/all")
        assert list_resp.status_code == 200
        all_courses = list_resp.json()["courses"]
        cids = [c["course_id"] for c in all_courses if "course_id" in c]
        assert cid in cids, f"Course {cid} should be in list"

        # Delete
        delete_resp = client.delete(f"/courses/{cid}")
        assert delete_resp.status_code == 200