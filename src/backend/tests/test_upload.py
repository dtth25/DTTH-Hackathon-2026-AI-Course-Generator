"""
Gate 1: File Upload Validation Tests
Kiểm tra endpoint POST /api/upload chỉ chấp nhận .pdf, .docx, .txt.
"""
import pytest
from fastapi.testclient import TestClient


class TestUploadValidation:
    """Gate 1: File Upload Validation — 10 test cases."""

    # ─── P0 Tests (Critical) ──────────────────────────────────────────────────

    def test_upload_pdf_valid(self, client: TestClient, sample_pdf: bytes):
        """TC_UPLOAD_01: Upload PDF hợp lệ → 200 + course_id"""
        response = client.post(
            "/api/upload",
            files={"file": ("document.pdf", sample_pdf, "application/pdf")},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "course_id" in data, "Response must contain course_id"
        assert data["status"] == "processing"

    def test_upload_docx_valid(self, client: TestClient, sample_docx: bytes):
        """TC_UPLOAD_02: Upload DOCX hợp lệ → 200"""
        response = client.post(
            "/api/upload",
            files={"file": ("document.docx", sample_docx,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

    def test_upload_txt_valid(self, client: TestClient, sample_txt: bytes):
        """TC_UPLOAD_03: Upload TXT hợp lệ → 200"""
        response = client.post(
            "/api/upload",
            files={"file": ("document.txt", sample_txt, "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

    def test_upload_png_rejected(self, client: TestClient, sample_png: bytes):
        """TC_UPLOAD_04: Upload file .png → 422 reject"""
        response = client.post(
            "/api/upload",
            files={"file": ("image.png", sample_png, "image/png")},
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        data = response.json()
        assert any("pdf" in str(err).lower() or "docx" in str(err).lower()
                   for err in (data.get("detail", "") if isinstance(data.get("detail"), str)
                               else str(data.get("detail", [])))), \
            "Error message must mention allowed formats"

    def test_upload_exe_rejected(self, client: TestClient):
        """TC_UPLOAD_05: Upload file .exe → 422 reject"""
        exe_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
        response = client.post(
            "/api/upload",
            files={"file": ("virus.exe", exe_content, "application/x-msdownload")},
        )
        assert response.status_code == 422

    def test_upload_jpg_rejected(self, client: TestClient, sample_jpg: bytes):
        """TC_UPLOAD_04b: Upload file .jpg → 422 reject"""
        response = client.post(
            "/api/upload",
            files={"file": ("photo.jpg", sample_jpg, "image/jpeg")},
        )
        assert response.status_code == 422

    def test_upload_zip_rejected(self, client: TestClient):
        """TC_UPLOAD_05b: Upload file .zip → 422 reject"""
        import zipfile
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("test.txt", "hello")
        response = client.post(
            "/api/upload",
            files={"file": ("archive.zip", zip_buffer.getvalue(), "application/zip")},
        )
        assert response.status_code == 422

    # ─── P1 Tests (Important) ─────────────────────────────────────────────────

    def test_upload_empty_file_rejected(self, client: TestClient, sample_empty_file: bytes):
        """TC_UPLOAD_08: Upload file rỗng → 422"""
        response = client.post(
            "/api/upload",
            files={"file": ("empty.pdf", sample_empty_file, "application/pdf")},
        )
        assert response.status_code == 422

    def test_upload_no_file_rejected(self, client: TestClient):
        """TC_UPLOAD_07: Không gửi file → 422"""
        response = client.post("/api/upload")
        assert response.status_code == 422

    # ─── P2 Tests (Polish) ────────────────────────────────────────────────────

    def test_upload_large_file_rejected(self, client: TestClient, sample_large_file: bytes):
        """TC_UPLOAD_06: Upload file > 50MB → 422"""
        response = client.post(
            "/api/upload",
            files={"file": ("large.pdf", sample_large_file, "application/pdf")},
        )
        assert response.status_code == 422