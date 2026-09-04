"""Deterministic OpenRouter-compatible server for ENVIRONMENT=loadtest only."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if os.environ.get("ENVIRONMENT") != "loadtest":
    raise SystemExit("mock OpenRouter is forbidden outside ENVIRONMENT=loadtest")

TOKEN = os.environ.get("LOAD_TEST_CONTROL_TOKEN", "")
if len(TOKEN) < 16:
    raise SystemExit("LOAD_TEST_CONTROL_TOKEN must contain at least 16 characters")

CONTENT_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-pro")
EMBED_MODEL = os.environ.get("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
STATE = {"mode": "healthy", "calls": {}, "total": 0}
LOCK = threading.Lock()


def _record(path: str) -> None:
    with LOCK:
        STATE["total"] += 1
        STATE["calls"][path] = STATE["calls"].get(path, 0) + 1


def _embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [round((byte - 127.5) / 127.5, 6) for byte in digest]


def _content(schema_name: str) -> dict:
    section = {"title": "Khái niệm", "content": "Nội dung kiểm thử có căn cứ từ tài liệu. " * 70}
    chapter = {
        "chapter_title": "Nền tảng",
        "introduction": "Tóm lược tài liệu kiểm thử.",
        "objectives": ["Hiểu nội dung"],
        "sections": [section],
        "key_points": ["Ý chính"],
        "review_questions": ["Điều gì quan trọng?"],
        "source_chunk_ids": [],
    }
    fixtures = {
        "CourseTitleOutput": {"title": "Tài liệu kiểm thử tải"},
        "BookOutline": {
            "title": "Sách kiểm thử",
            "summary": "Tóm tắt từ tài liệu.",
            "preface": "Lời mở đầu từ tài liệu.",
            "chapters": [
                {
                    "chapter_number": number,
                    "chapter_title": f"Nền tảng {number}",
                    "description": "Nội dung chính.",
                    "retrieval_query": "nội dung kiểm thử",
                    "planned_sections": ["Khái niệm"],
                }
                for number in range(1, 5)
            ],
        },
        "BookChapterContent": chapter,
        "BookOutput": {
            "title": "Sách kiểm thử",
            "summary": "Tóm tắt từ tài liệu.",
            "preface": "Lời mở đầu.",
            "chapters": [chapter],
        },
        "SlidesOutput": {
            "title": "Slide kiểm thử",
            "slides": [
                {
                    "slide_number": 1,
                    "title": "Nội dung",
                    "layout_type": "default",
                    "bullet_points": ["Ý chính từ tài liệu"],
                    "source_chunk_ids": [],
                }
            ],
        },
        "QuizOutput": {
            "title": "Quiz kiểm thử",
            "questions": [
                {
                    "question_number": 1,
                    "question_text": "Nội dung nào xuất hiện?",
                    "difficulty": "Medium",
                    "options": [
                        {"key": k, "text": v} for k, v in zip("ABCD", ["Nội dung kiểm thử", "Sai 1", "Sai 2", "Sai 3"])
                    ],
                    "correct_answer": "A",
                    "explanation": "Đáp án nằm trong tài liệu.",
                    "source_chunk_ids": [],
                }
            ],
        },
        "VidOutput": {
            "title": "Video kiểm thử",
            "total_duration_seconds": 2,
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "Nội dung",
                    "on_screen_text": "Ý chính",
                    "key_points": ["Từ tài liệu"],
                    "diagram": None,
                    "narration": "Đây là nội dung kiểm thử ngắn từ tài liệu đã tải lên.",
                    "duration_seconds": 2,
                    "source_chunk_ids": [],
                }
            ],
        },
    }
    return fixtures.get(schema_name, fixtures["CourseTitleOutput"])


class Handler(BaseHTTPRequestHandler):
    server_version = "HackaGenLoadAdapter/1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(
            json.dumps(
                {
                    "method": self.command,
                    "path": self.path.split("?", 1)[0],
                    "status": args[1] if len(args) > 1 else None,
                }
            ),
            flush=True,
        )

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def _fault(self) -> bool:
        mode = STATE["mode"]
        if mode == "healthy":
            return False
        status = {"key-limit": 402, "rate-limit": 429, "unavailable": 503}[mode]
        headers = {"Retry-After": "2"} if status in {429, 503} else {}
        body = json.dumps({"error": {"code": mode, "message": "deterministic load-test fault"}}).encode()
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            return self._json(200, {"ready": True})
        if path == "/__control/stats":
            if not self._authorized():
                return self._json(404, {"detail": "not found"})
            with LOCK:
                snapshot = json.loads(json.dumps(STATE))
            return self._json(200, snapshot)
        _record(path)
        if self._fault():
            return
        if path == "/api/v1/key":
            return self._json(200, {"data": {"limit": 1000000, "limit_remaining": 1000000, "usage": 0}})
        if path == "/api/v1/models":
            return self._json(200, {"data": [{"id": CONTENT_MODEL}]})
        if path == "/api/v1/embeddings/models":
            return self._json(200, {"data": [{"id": EMBED_MODEL}]})
        return self._json(404, {"detail": "not found"})

    def do_PUT(self) -> None:
        if self.path != "/__control/fault" or not self._authorized():
            return self._json(404, {"detail": "not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size) or b"{}")
            mode = payload.get("mode")
        except Exception:
            return self._json(400, {"detail": "invalid json"})
        if mode not in {"healthy", "key-limit", "rate-limit", "unavailable"}:
            return self._json(422, {"detail": "invalid mode"})
        with LOCK:
            STATE["mode"] = mode
            STATE["calls"] = {}
            STATE["total"] = 0
        return self._json(200, {"mode": mode})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        _record(path)
        if self._fault():
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size) or b"{}")
        except Exception:
            return self._json(400, {"detail": "invalid json"})
        if path == "/api/v1/embeddings":
            values = payload.get("input", [])
            values = [values] if isinstance(values, str) else values
            return self._json(
                200,
                {
                    "object": "list",
                    "model": payload.get("model", EMBED_MODEL),
                    "data": [
                        {"object": "embedding", "index": i, "embedding": _embedding(str(value))}
                        for i, value in enumerate(values)
                    ],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        if path == "/api/v1/chat/completions":
            schema = (
                ((payload.get("response_format") or {}).get("json_schema") or {}).get("name")
            ) or "CourseTitleOutput"
            content = json.dumps(_content(schema), ensure_ascii=False)
            return self._json(
                200,
                {
                    "id": "loadtest",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": payload.get("model", CONTENT_MODEL),
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )
        return self._json(404, {"detail": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
