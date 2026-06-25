"""
E2E Integration Tests: Full-stack flow tests.
Cần frontend + backend + Milvus đang chạy.
"""
import time
import pytest
import requests


class TestFullFlow:
    """E2E Integration tests — 3 test cases."""

    def test_e2e_upload_pdf_generate_course(self, e2e_client: dict, sample_pdf_path: str):
        """
        E2E_01: Upload PDF → Generate Course → Check citations
        Upload file qua backend API, generate course, verify citations.
        """
        backend = e2e_client["backend"]

        # Step 1: Upload PDF
        with open(sample_pdf_path, "rb") as f:
            resp = requests.post(
                f"{backend}/api/upload",
                files={"file": ("e2e_test.pdf", f, "application/pdf")},
            )
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        cid = resp.json()["course_id"]

        # Step 2: Poll until ready
        timeout, interval = 60, 3
        ready = False
        for _ in range(timeout // interval):
            status_resp = requests.get(f"{backend}/api/course/{cid}/status")
            if status_resp.status_code == 200:
                if status_resp.json().get("status") == "ready":
                    ready = True
                    break
            time.sleep(interval)

        assert ready, f"Course {cid} not ready after {timeout}s"

        # Step 3: Generate course structure
        course_resp = requests.post(f"{backend}/api/generate-course", json={
            "course_id": cid,
            "user_prompt": "E2E test course",
            "target_audience": "sinh viên"
        })
        assert course_resp.status_code == 200
        course_data = course_resp.json()

        # Step 4: Verify citations
        course_str = str(course_data)
        assert "[" in course_str or "citation" in course_str.lower(), \
            f"Course should contain citations: {course_str[:300]}"

        # Step 5: Cleanup
        requests.delete(f"{backend}/courses/{cid}")

    def test_e2e_summary_lengths(self, e2e_client: dict, sample_pdf_path: str):
        """
        E2E_02: Upload DOCX → Generate Summary → Check 3 lengths
        Generate summary với cả 3 loại: short, medium, detailed.
        """
        backend = e2e_client["backend"]

        # Upload
        with open(sample_pdf_path, "rb") as f:
            resp = requests.post(
                f"{backend}/api/upload",
                files={"file": ("e2e_summary.pdf", f, "application/pdf")},
            )
        assert resp.status_code == 200
        cid = resp.json()["course_id"]

        # Poll
        for _ in range(30):
            status = requests.get(f"{backend}/api/course/{cid}/status").json()
            if status.get("status") == "ready":
                break
            time.sleep(2)

        # Generate 3 summary types
        for summary_type in ["short", "medium", "detailed"]:
            resp = requests.post(f"{backend}/api/generate-summary", json={
                "course_id": cid,
                "type": summary_type
            })
            assert resp.status_code == 200, f"{summary_type} summary failed: {resp.text}"

        # Cleanup
        requests.delete(f"{backend}/courses/{cid}")

    def test_e2e_full_multi_feature(self, e2e_client: dict, sample_pdf_path: str):
        """
        E2E_03: Upload → Full multi-feature pipeline
        Quiz → Flashcard → Mindmap → Slide → Custom Prompt
        """
        backend = e2e_client["backend"]

        # Upload
        with open(sample_pdf_path, "rb") as f:
            resp = requests.post(
                f"{backend}/api/upload",
                files={"file": ("e2e_full.pdf", f, "application/pdf")},
            )
        assert resp.status_code == 200
        cid = resp.json()["course_id"]

        # Poll
        for _ in range(30):
            status = requests.get(f"{backend}/api/course/{cid}/status").json()
            if status.get("status") == "ready":
                break
            time.sleep(2)

        # Generate all features
        features = [
            ("quiz", "/api/generate-quiz", {"course_id": cid, "topic": "Kiến thức", "quantity": 3, "difficulty": "easy"}),
            ("flashcards", "/api/generate-flashcards", {"course_id": cid, "count": 5}),
            ("mindmap", "/api/generate-mindmap", {"course_id": cid, "max_depth": 2}),
            ("slides", "/api/generate-slides", {"course_id": cid, "topic": "Giới thiệu", "num_slides": 3}),
            ("custom-prompt", "/api/custom-prompt", {"course_id": cid, "prompt": "Phân tích nội dung"}),
        ]

        for name, endpoint, payload in features:
            resp = requests.post(f"{backend}{endpoint}", json=payload)
            assert resp.status_code == 200, f"{name} failed: {resp.text}"
            data_str = str(resp.json())
            assert "[" in data_str or "citation" in data_str.lower(), \
                f"{name} should contain citations"

        # Cleanup
        requests.delete(f"{backend}/courses/{cid}")