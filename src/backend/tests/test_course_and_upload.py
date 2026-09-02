"""Automated tests for Course Management and Upload Service."""

import os
import time


def get_auth_headers(client, email: str = "user@example.com", full_name: str = "User"):
    reg_data = {"email": email, "password": "password123", "full_name": full_name}
    res = client.post("/api/auth/register", json=reg_data)
    if res.status_code == 201:
        res = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
    else:
        # If already registered, login
        res = client.post(
            "/api/auth/login", json={"email": email, "password": "password123"}
        )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_single_file(client, test_upload_dir):
    headers = get_auth_headers(client, "single@example.com")
    files = [("files", ("test_doc.pdf", b"dummy pdf content", "application/pdf"))]
    response = client.post("/api/upload", headers=headers, files=files)
    assert response.status_code == 201, response.text
    data = response.json()
    assert len(data["course_id"]) == 12
    assert data["status"] == "processing"
    assert data["file_count"] == 1
    assert data["filenames"] == ["test_doc.pdf"]

    # Verify file saved on disk
    course_dir = os.path.join(test_upload_dir, data["course_id"])
    assert os.path.exists(course_dir)
    saved_files = os.listdir(course_dir)
    assert len(saved_files) == 1
    assert saved_files[0].endswith("_test_doc.pdf")


def test_upload_multiple_files_same_course(client, test_upload_dir):
    headers = get_auth_headers(client, "multi@example.com")
    files = [
        ("files[]", ("doc1.pdf", b"content 1", "application/pdf")),
        (
            "files[]",
            (
                "doc2.docx",
                b"content 2",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ),
    ]
    response = client.post("/api/upload", headers=headers, files=files)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["file_count"] == 2
    assert set(data["filenames"]) == {"doc1.pdf", "doc2.docx"}

    # Verify both files saved under same course_id
    course_dir = os.path.join(test_upload_dir, data["course_id"])
    assert len(os.listdir(course_dir)) == 2


def test_upload_too_many_files(client):
    headers = get_auth_headers(client, "toomany@example.com")
    files = [
        ("files", ("1.txt", b"a", "text/plain")),
        ("files", ("2.txt", b"b", "text/plain")),
        ("files", ("3.txt", b"c", "text/plain")),
        ("files", ("4.txt", b"d", "text/plain")),
        ("files", ("5.txt", b"e", "text/plain")),
        ("files", ("6.txt", b"f", "text/plain")),
    ]
    response = client.post("/api/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "tối đa 5 file" in response.json()["detail"]


def test_upload_invalid_extension_exe(client):
    headers = get_auth_headers(client, "exe@example.com")
    files = [("files", ("malicious.exe", b"MZ...", "application/octet-stream"))]
    response = client.post("/api/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "Định dạng file .exe không được hỗ trợ" in response.json()["detail"]


def test_upload_empty_file(client):
    headers = get_auth_headers(client, "empty@example.com")
    files = [("files", ("empty.pdf", b"", "application/pdf"))]
    response = client.post("/api/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "là file rỗng (0 bytes)" in response.json()["detail"]


def test_upload_file_too_large(client):
    headers = get_auth_headers(client, "large@example.com")
    # Simulate file larger than 50MB
    large_content = b"0" * (50 * 1024 * 1024 + 1)
    files = [("files", ("huge.pdf", large_content, "application/pdf"))]
    response = client.post("/api/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "vượt quá kích thước tối đa" in response.json()["detail"]


def test_courses_all_ownership(client):
    headers_a = get_auth_headers(client, "usera@example.com", "User A")
    headers_b = get_auth_headers(client, "userb@example.com", "User B")

    # User A uploads 1 file
    client.post(
        "/api/upload",
        headers=headers_a,
        files=[("files", ("docA.pdf", b"content A", "application/pdf"))],
    )
    # User B uploads 2 files
    client.post(
        "/api/upload",
        headers=headers_b,
        files=[("files", ("docB.pdf", b"content B", "application/pdf"))],
    )

    # Check A's list
    res_a = client.get("/api/courses/all", headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["total"] == 1
    assert res_a.json()["courses"][0]["filenames"] == ["docA.pdf"]

    # Check B's list
    res_b = client.get("/api/courses/all", headers=headers_b)
    assert res_b.status_code == 200
    assert res_b.json()["total"] == 1
    assert res_b.json()["courses"][0]["filenames"] == ["docB.pdf"]


def test_course_status_reflects_real_state_not_simulated(client):
    """/status must report the DB's real status — a course with no attached processing
    pipeline (created directly via POST /api/courses, bypassing upload) must stay
    "processing" indefinitely instead of being force-flipped to "ready" after a timer."""
    headers = get_auth_headers(client, "status@example.com")
    res = client.post(
        "/api/courses",
        headers=headers,
        json={"filenames": ["doc.pdf"]},
    )
    course_id = res.json()["id"]

    status_res1 = client.get(f"/api/course/{course_id}/status", headers=headers)
    assert status_res1.status_code == 200
    assert status_res1.json()["status"] == "processing"

    # Past the old 1.5s simulated-transition threshold — must still be genuinely processing,
    # not force-flipped by a timer with no real pipeline behind it.
    time.sleep(1.6)
    status_res2 = client.get(f"/api/course/{course_id}/status", headers=headers)
    assert status_res2.status_code == 200
    assert status_res2.json()["status"] == "processing"
    assert status_res2.json()["message"] == "Đang phân tích và xử lý tài liệu..."


def test_course_status_failed_exposes_safe_error(client):
    """A failed course exposes its closed public error code and safe Vietnamese copy."""
    from app.models.course import Course
    from app.services.database import SessionLocal

    headers = get_auth_headers(client, "failed_status@example.com")
    res = client.post(
        "/api/courses",
        headers=headers,
        json={"filenames": ["broken.pdf"]},
    )
    course_id = res.json()["id"]

    db = SessionLocal()
    try:
        course = db.query(Course).filter(Course.id == course_id).first()
        course.status = "failed"
        course.error_message = "raw extractor diagnostic must not reach clients"
        course.error_code = "DOCUMENT_TEXT_EXTRACTION_FAILED"
        db.commit()
    finally:
        db.close()

    status_res = client.get(f"/api/course/{course_id}/status", headers=headers)
    assert status_res.status_code == 200
    body = status_res.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "DOCUMENT_TEXT_EXTRACTION_FAILED"
    assert body["error"] == "Không thể đọc văn bản trong tệp."
    assert body["message"] == body["error"]

    list_res = client.get("/api/courses/all", headers=headers)
    assert list_res.status_code == 200
    items = [c for c in list_res.json()["courses"] if c["course_id"] == course_id]
    assert len(items) == 1
    assert items[0]["error_code"] == "DOCUMENT_TEXT_EXTRACTION_FAILED"
    assert items[0]["error"] == "Không thể đọc văn bản trong tệp."


def test_delete_course_and_cleanup(client, test_upload_dir):
    headers = get_auth_headers(client, "delete@example.com")
    res = client.post(
        "/api/upload",
        headers=headers,
        files=[("files", ("todelete.pdf", b"content", "application/pdf"))],
    )
    course_id = res.json()["course_id"]
    course_dir = os.path.join(test_upload_dir, course_id)
    assert os.path.exists(course_dir)

    # Delete course
    del_res = client.delete(f"/api/courses/{course_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify soft delete in DB (GET status returns 404)
    status_res = client.get(f"/api/course/{course_id}/status", headers=headers)
    assert status_res.status_code == 404

    # Verify filesystem cleanup
    assert not os.path.exists(course_dir)


def test_delete_course_unauthorized(client):
    headers_owner = get_auth_headers(client, "owner@example.com")
    headers_other = get_auth_headers(client, "other@example.com")

    res = client.post(
        "/api/upload",
        headers=headers_owner,
        files=[("files", ("doc.pdf", b"content", "application/pdf"))],
    )
    course_id = res.json()["course_id"]

    # Other user tries to delete
    del_res = client.delete(f"/api/courses/{course_id}", headers=headers_other)
    assert del_res.status_code == 404
