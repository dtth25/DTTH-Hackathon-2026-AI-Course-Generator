from fastapi.testclient import TestClient

from backend import main


class FakeResourceGenerator:
    def generate_book(self, user_prompt: str, target_audience: str):
        return {
            "book": {"title": "Book", "chapters": []},
            "pdf_url": "/api/course/course123/book.pdf",
        }

    def generate_slides_v2(self, topic: str, num_slides: int):
        return {"slides": [{"title": "Slide 1", "content": "Content"}]}

    def generate_quiz_v2(self, topic: str, quantity: int, difficulty: str):
        return {
            "questions": [
                {
                    "question": "Question?",
                    "options": ["A", "B"],
                    "correct": 0,
                    "explanation": "Because A.",
                }
            ]
        }

    def generate_vid(self, topic: str, duration_minutes: int):
        return {"vid": {"filename": "vid.mp4", "url": "/api/course/course123/vid/file", "scenes": []}}


class FakeRag:
    def get_resource_generator(self):
        return FakeResourceGenerator()


class FakeCourseManager:
    def __init__(self):
        self.registered_paths = []

    def get_course_status(self, course_id: str):
        return "ready"

    def get_course(self, course_id: str):
        return FakeRag()

    def list_courses(self):
        return ["course123"]

    def contains(self, course_id: str):
        return True

    def register_course_id(self, course_id: str, source_path):
        self.registered_paths = source_path if isinstance(source_path, list) else [source_path]

    def process_new_course(self, course_id: str, source_path):
        return None


def client(monkeypatch):
    fake_manager = FakeCourseManager()
    monkeypatch.setattr(main, "CourseManager", lambda: fake_manager)
    monkeypatch.setattr(main, "course_manager", fake_manager)
    return TestClient(main.app)


def assert_no_public_source_metadata(payload):
    text = str(payload)
    assert "citations" not in text
    assert "chunk_id" not in text
    assert "'page'" not in text
    assert '"page"' not in text
    assert "'source'" not in text
    assert '"source"' not in text


def test_generation_contract_has_only_four_public_outputs(monkeypatch):
    test_client = client(monkeypatch)

    requests = [
        ("/api/generate-book", {"course_id": "course123"}),
        ("/api/generate-slide", {"course_id": "course123", "topic": "topic"}),
        ("/api/generate-quiz", {"course_id": "course123", "topic": "topic"}),
        ("/api/generate-vid", {"course_id": "course123", "topic": "topic"}),
    ]

    for path, body in requests:
        response = test_client.post(path, json=body)
        assert response.status_code == 200
        assert_no_public_source_metadata(response.json())

        if path == "/api/generate-slide":
            assert response.json()["pdf_url"].endswith("/slide.pdf")
            assert response.json()["json_url"].endswith("/slide.json")
        if path == "/api/generate-quiz":
            assert response.json()["pdf_url"].endswith("/quiz.pdf")
            assert response.json()["json_url"].endswith("/quiz.json")


def test_removed_generation_routes_are_not_registered(monkeypatch):
    test_client = client(monkeypatch)

    removed_routes = [
        "/api/chat",
        "/api/custom-prompt",
        "/api/generate-course",
        "/api/generate-summary",
        "/api/generate-flashcards",
        "/api/generate-mindmap",
    ]

    for path in removed_routes:
        response = test_client.post(path, json={"course_id": "course123"})
        assert response.status_code == 404


def test_upload_rejects_unsupported_extension(monkeypatch):
    test_client = client(monkeypatch)

    response = test_client.post(
        "/api/upload",
        files={"file": ("notes.exe", b"bad", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_upload_accepts_multiple_documents(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "UPLOAD_DIR", str(tmp_path))
    test_client = client(monkeypatch)

    response = test_client.post(
        "/api/upload",
        files=[
            ("files", ("a.txt", b"hello", "text/plain")),
            ("files", ("b.txt", b"world", "text/plain")),
        ],
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["file_count"] == 2
    assert payload["filenames"] == ["a.txt", "b.txt"]
    assert payload["status"] == "processing"
