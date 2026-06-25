"""
Async Endpoint Tests (Gate 6.1 - 6.3)
Test async task lifecycle: submit → poll → complete.
"""
import time
import pytest
from fastapi.testclient import TestClient


class TestAsyncEndpoints:
    """Tests for async background task endpoints."""

    def test_async_generate_course(self, client: TestClient, course_id: str):
        """TC 6.1: Async generate course — gọi async → poll task → verify"""
        # Submit async task
        resp = client.post("/api/generate-course-async", json={
            "course_id": course_id,
            "user_prompt": "Tạo khóa học về AI",
            "target_audience": "sinh viên"
        })
        assert resp.status_code == 200, f"Async submit failed: {resp.text}"
        task_data = resp.json()
        assert "task_id" in task_data
        assert task_data["status"] == "processing"

        # Poll task until completed
        task_id = task_data["task_id"]
        timeout, interval = 30, 2
        elapsed = 0
        result = None
        while elapsed < timeout:
            poll_resp = client.get(f"/task/{task_id}")
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                if poll_data.get("status") == "completed":
                    result = poll_data.get("result")
                    break
                elif poll_data.get("status") == "failed":
                    pytest.fail(f"Task failed: {poll_data.get('error')}")
            time.sleep(interval)
            elapsed += interval

        assert result is not None, f"Task {task_id} not completed after {timeout}s"

    def test_async_task_not_found(self, client: TestClient):
        """TC 6.2: GET /task/invalid_id → 404"""
        resp = client.get("/task/nonexistent-task-id-12345")
        assert resp.status_code == 404

    def test_async_generate_all_types(self, client: TestClient, course_id: str):
        """
        TC 6.3: Tất cả async generate types hoạt động.
        Submit tất cả async endpoints, poll từng cái.
        """
        async_endpoints = [
            ("summary", "/api/generate-summary-async", {"course_id": course_id, "type": "short"}),
            ("flashcards", "/api/generate-flashcards-async", {"course_id": course_id, "count": 5}),
            ("quiz", "/api/generate-quiz-async", {"course_id": course_id, "topic": "Kiến thức cơ bản", "quantity": 3, "difficulty": "easy"}),
            ("slides", "/api/generate-slides-async", {"course_id": course_id, "topic": "Giới thiệu", "num_slides": 3}),
            ("mindmap", "/api/generate-mindmap-async", {"course_id": course_id, "max_depth": 2}),
        ]

        task_ids = []
        for name, endpoint, payload in async_endpoints:
            resp = client.post(endpoint, json=payload)
            assert resp.status_code == 200, f"{name} async submit failed: {resp.text}"
            task_data = resp.json()
            assert "task_id" in task_data
            task_ids.append((name, task_data["task_id"]))

        # Poll each task
        timeout, interval = 60, 2
        for name, task_id in task_ids:
            elapsed = 0
            completed = False
            while elapsed < timeout:
                poll_resp = client.get(f"/task/{task_id}")
                if poll_resp.status_code == 200:
                    poll_data = poll_resp.json()
                    if poll_data.get("status") == "completed":
                        completed = True
                        break
                    elif poll_data.get("status") == "failed":
                        pytest.fail(f"{name} task failed: {poll_data.get('error')}")
                time.sleep(interval)
                elapsed += interval
            assert completed, f"{name} task {task_id} not completed after {timeout}s"