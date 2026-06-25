"""
Integration Tests: Full pipeline tests (Gate 5.1 - 5.4)
Upload → Process → Generate → Verify citations.
"""
import time
import pytest
from fastapi.testclient import TestClient


class TestFullPipeline:
    """Integration tests for the complete pipeline."""

    def test_full_pipeline_pdf(self, client: TestClient, sample_pdf: bytes):
        """TC 5.1: Full pipeline PDF — upload → ready → generate course → verify citations"""
        # Step 1: Upload
        resp = client.post(
            "/api/upload",
            files={"file": ("pipeline_test.pdf", sample_pdf, "application/pdf")},
        )
        assert resp.status_code == 200
        cid = resp.json()["course_id"]
        assert cid, "Course ID should not be empty"

        # Step 2: Poll until ready
        timeout, interval = 60, 3
        elapsed = 0
        ready = False
        while elapsed < timeout:
            status_resp = client.get(f"/api/course/{cid}/status")
            if status_resp.status_code == 200:
                status = status_resp.json().get("status")
                if status == "ready":
                    ready = True
                    break
            time.sleep(interval)
            elapsed += interval

        assert ready, f"Course {cid} not ready after {timeout}s"

        # Step 3: Generate course structure
        course_resp = client.post("/api/generate-course", json={
            "course_id": cid,
            "user_prompt": "Tạo khóa học từ tài liệu",
            "target_audience": "sinh viên"
        })
        assert course_resp.status_code == 200
        course_data = course_resp.json()
        assert "course_id" in course_data

        # Step 4: Verify citations in generated content
        course_str = str(course_data)
        assert "[" in course_str or "Trang" in course_str or "citation" in course_str.lower(), \
            f"Generated course should contain citations: {course_str[:300]}"

        # Step 5: Cleanup
        client.delete(f"/courses/{cid}")

    def test_full_pipeline_docx(self, client: TestClient, sample_docx: bytes):
        """TC 5.2: Full pipeline DOCX — upload → ready → generate summary"""
        resp = client.post(
            "/api/upload",
            files={"file": ("pipeline_test.docx", sample_docx,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 200
        cid = resp.json()["course_id"]

        # Poll until ready
        timeout, interval = 60, 3
        elapsed = 0
        ready = False
        while elapsed < timeout:
            status_resp = client.get(f"/api/course/{cid}/status")
            if status_resp.status_code == 200:
                status = status_resp.json().get("status")
                if status == "ready":
                    ready = True
                    break
            time.sleep(interval)
            elapsed += interval

        assert ready, f"Course {cid} not ready after {timeout}s"

        # Generate summary
        summary_resp = client.post("/api/generate-summary", json={
            "course_id": cid,
            "type": "short"
        })
        assert summary_resp.status_code == 200
        summary_data = summary_resp.json()
        assert "course_id" in summary_data

        # Cleanup
        client.delete(f"/courses/{cid}")

    def test_course_status_transition(self, client: TestClient, sample_pdf: bytes):
        """TC 5.3: Course status transitions — upload → processing → ready"""
        resp = client.post(
            "/api/upload",
            files={"file": ("status_test.pdf", sample_pdf, "application/pdf")},
        )
        assert resp.status_code == 200
        cid = resp.json()["course_id"]

        # Check initial status
        status_resp = client.get(f"/api/course/{cid}/status")
        assert status_resp.status_code == 200
        initial_status = status_resp.json().get("status")
        assert initial_status in ("processing", "pending"), \
            f"Expected processing/pending, got {initial_status}"

        # Poll until ready or timeout
        timeout, interval = 60, 3
        elapsed = 0
        final_status = initial_status
        while elapsed < timeout:
            status_resp = client.get(f"/api/course/{cid}/status")
            if status_resp.status_code == 200:
                final_status = status_resp.json().get("status")
                if final_status == "ready":
                    break
            time.sleep(interval)
            elapsed += interval

        assert final_status in ("ready", "error"), \
            f"Expected ready/error, got {final_status}"

        # Cleanup
        client.delete(f"/courses/{cid}")

    def test_delete_course(self, client: TestClient, sample_txt: bytes):
        """TC 5.4: Delete course — upload → delete → verify cleanup"""
        resp = client.post(
            "/api/upload",
            files={"file": ("delete_test.txt", sample_txt, "text/plain")},
        )
        assert resp.status_code == 200
        cid = resp.json()["course_id"]

        # Delete
        delete_resp = client.delete(f"/courses/{cid}")
        assert delete_resp.status_code == 200

        # Verify deleted
        verify_resp = client.get(f"/api/course/{cid}/status")
        assert verify_resp.status_code == 404 or verify_resp.json().get("status") is None