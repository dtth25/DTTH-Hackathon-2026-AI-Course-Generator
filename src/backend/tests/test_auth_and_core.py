"""Automated tests for Core Infrastructure, Authentication, and CORS."""

from app.core.config import settings


def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_register_does_not_auto_login(client):
    """Register must NOT issue a token/cookie anymore — the account is unverified
    until /verify-email succeeds."""
    reg_data = {
        "email": "testuser@example.com",
        "password": "secretpassword123",
        "full_name": "Test User",
    }
    response = client.post("/api/auth/register", json=reg_data)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert "access_token" not in data
    assert settings.AUTH_COOKIE_NAME not in response.cookies

    # Login before verifying must be blocked
    login_res = client.post(
        "/api/auth/login",
        json={"email": "testuser@example.com", "password": "secretpassword123"},
    )
    assert login_res.status_code == 403
    assert login_res.json()["detail"]["code"] == "email_not_verified"


def test_auth_verify_email_wrong_then_right_code(client):
    reg_data = {
        "email": "verifyuser@example.com",
        "password": "secretpassword123",
        "full_name": "Verify User",
    }
    client.post("/api/auth/register", json=reg_data)

    wrong = client.post(
        "/api/auth/verify-email", json={"email": "verifyuser@example.com", "code": "999999"}
    )
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == {
        "code": "EMAIL_VERIFICATION_FAILED",
        "message": "Không thể xác thực email. Vui lòng kiểm tra email và mã rồi thử lại.",
    }

    right = client.post(
        "/api/auth/verify-email", json={"email": "verifyuser@example.com", "code": "000000"}
    )
    assert right.status_code == 200, right.text
    data = right.json()
    assert "access_token" in data
    assert data["user"]["is_verified"] is True
    assert settings.AUTH_COOKIE_NAME in right.cookies

    # Now login works normally
    login_res = client.post(
        "/api/auth/login",
        json={"email": "verifyuser@example.com", "password": "secretpassword123"},
    )
    assert login_res.status_code == 200


def test_auth_forgot_and_reset_password(client):
    reg_data = {
        "email": "resetuser@example.com",
        "password": "oldpassword123",
        "full_name": "Reset User",
    }
    client.post("/api/auth/register", json=reg_data)
    client.post("/api/auth/verify-email", json={"email": "resetuser@example.com", "code": "000000"})

    forgot_res = client.post("/api/auth/forgot-password", json={"email": "resetuser@example.com"})
    assert forgot_res.status_code == 200

    reset_res = client.post(
        "/api/auth/reset-password",
        json={"email": "resetuser@example.com", "code": "000000", "new_password": "newpassword456"},
    )
    assert reset_res.status_code == 200

    old_login = client.post(
        "/api/auth/login", json={"email": "resetuser@example.com", "password": "oldpassword123"}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login", json={"email": "resetuser@example.com", "password": "newpassword456"}
    )
    assert new_login.status_code == 200


def _register_and_verify(client, email: str, password: str = "password123") -> str:
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
    return res.json()["access_token"]


def test_auth_login_and_cookie_flow(client):
    # Setup user
    _register_and_verify(client, "loginuser@example.com", "loginpassword123")

    # 1. Login with credentials
    login_data = {
        "email": "loginuser@example.com",
        "password": "loginpassword123",
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

    # Check cookie
    cookie_val = response.cookies.get(settings.AUTH_COOKIE_NAME)
    assert cookie_val is not None

    # 2. Get me using ONLY the HttpOnly cookie (no Authorization header)
    client.cookies.set(settings.AUTH_COOKIE_NAME, cookie_val)
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "loginuser@example.com"


def test_auth_logout_blacklist(client):
    # Setup and login
    token = _register_and_verify(client, "logoutuser@example.com", "password123")

    # Verify access works
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 200
    )

    # Logout
    logout_res = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["detail"] == "Đăng xuất thành công."

    # Verify token is now blacklisted and rejected
    me_after_logout = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_after_logout.status_code == 401
    assert me_after_logout.json()["detail"] == {
        "code": "UNAUTHENTICATED",
        "message": "Phiên đăng nhập đã bị hủy. Vui lòng đăng nhập lại.",
    }


def test_delete_account_wrong_password(client):
    token = _register_and_verify(client, "deletewrong@example.com", "password123")
    res = client.request(
        "DELETE",
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "not-the-right-password"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "wrong_password"


def test_auth_errors_use_stable_structured_codes(client, monkeypatch):
    from app.services import email_service
    from app.models.user import User
    from app.services.database import SessionLocal

    first = client.post(
        "/api/auth/register", json={"email": "duplicate@example.com", "password": "password123"}
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/api/auth/register", json={"email": "duplicate@example.com", "password": "password123"}
    )
    assert duplicate.json()["detail"]["code"] == "email_already_registered"

    invalid_login = client.post(
        "/api/auth/login", json={"email": "duplicate@example.com", "password": "wrong"}
    )
    assert invalid_login.json()["detail"]["code"] == "invalid_credentials"

    db = SessionLocal()
    try:
        db.query(User).filter(User.email == "duplicate@example.com").update({"is_active": False})
        db.commit()
    finally:
        db.close()
    disabled_login = client.post(
        "/api/auth/login", json={"email": "duplicate@example.com", "password": "password123"}
    )
    assert disabled_login.json()["detail"]["code"] == "account_disabled"

    already_verified = client.post(
        "/api/auth/register", json={"email": "verified@example.com", "password": "password123"}
    )
    assert already_verified.status_code == 201
    assert client.post(
        "/api/auth/verify-email", json={"email": "verified@example.com", "code": "000000"}
    ).status_code == 200
    repeat = client.post(
        "/api/auth/verify-email", json={"email": "verified@example.com", "code": "000000"}
    )
    assert repeat.json()["detail"]["code"] == "EMAIL_VERIFICATION_FAILED"

    invalid_verify = client.post(
        "/api/auth/verify-email", json={"email": "missing@example.com", "code": "000000"}
    )
    assert invalid_verify.json()["detail"]["code"] == "EMAIL_VERIFICATION_FAILED"
    invalid_reset = client.post(
        "/api/auth/reset-password",
        json={"email": "missing@example.com", "code": "000000", "new_password": "password456"},
    )
    assert invalid_reset.json()["detail"]["code"] == "PASSWORD_RESET_VERIFICATION_FAILED"

    def email_failure(*_args, **_kwargs):
        raise RuntimeError("untrusted mail provider detail")

    monkeypatch.setattr(email_service, "send_verification_code", email_failure)
    send_failure = client.post(
        "/api/auth/register", json={"email": "send-failure@example.com", "password": "password123"}
    )
    assert send_failure.json()["detail"] == {
        "code": "verification_email_send_failed",
        "message": "Không gửi được email xác thực. Vui lòng thử lại sau.",
    }


def test_auth_otp_failure_codes_are_structured(client):
    from datetime import datetime, timedelta

    from app.models.email_otp import EmailOtpCode
    from app.models.user import User
    from app.services import otp_service
    from app.services.database import SessionLocal

    email = "otp-errors@example.com"
    assert client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    ).status_code == 201

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        db.query(EmailOtpCode).filter(EmailOtpCode.user_id == user.id).delete()
        db.commit()
        missing = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
        assert missing.json()["detail"] == {
            "code": "EMAIL_VERIFICATION_FAILED",
            "message": "Không thể xác thực email. Vui lòng kiểm tra email và mã rồi thử lại.",
        }

        otp_service.create_otp(db, user, otp_service.PURPOSE_VERIFY_EMAIL)
        otp = db.query(EmailOtpCode).filter(EmailOtpCode.user_id == user.id).one()
        otp.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        expired = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
        assert expired.json()["detail"] == missing.json()["detail"]

        otp_service.create_otp(db, user, otp_service.PURPOSE_VERIFY_EMAIL)
        otp = db.query(EmailOtpCode).filter(EmailOtpCode.user_id == user.id).one()
        otp.attempts = settings.EMAIL_OTP_MAX_ATTEMPTS
        db.commit()
        locked = client.post("/api/auth/verify-email", json={"email": email, "code": "000000"})
        assert locked.json()["detail"] == missing.json()["detail"]

        reset_email = "otp-reset-errors@example.com"
        assert client.post(
            "/api/auth/register", json={"email": reset_email, "password": "password123"}
        ).status_code == 201
        reset_user = db.query(User).filter(User.email == reset_email).one()
        db.query(EmailOtpCode).filter(EmailOtpCode.user_id == reset_user.id).delete()
        db.commit()
        reset_missing = client.post(
            "/api/auth/reset-password",
            json={"email": reset_email, "code": "000000", "new_password": "password456"},
        )
        reset_detail = reset_missing.json()["detail"]
        assert reset_detail == {
            "code": "PASSWORD_RESET_VERIFICATION_FAILED",
            "message": "Không thể xác thực yêu cầu đặt lại mật khẩu. Vui lòng kiểm tra email và mã rồi thử lại.",
        }

        otp_service.create_otp(db, reset_user, otp_service.PURPOSE_RESET_PASSWORD)
        reset_otp = db.query(EmailOtpCode).filter(EmailOtpCode.user_id == reset_user.id).one()
        reset_otp.attempts = settings.EMAIL_OTP_MAX_ATTEMPTS
        db.commit()
        reset_locked = client.post(
            "/api/auth/reset-password",
            json={"email": reset_email, "code": "000000", "new_password": "password456"},
        )
        assert reset_locked.json()["detail"] == reset_detail

        unknown_reset = client.post(
            "/api/auth/reset-password",
            json={"email": "unknown-reset@example.com", "code": "000000", "new_password": "password456"},
        )
        assert unknown_reset.json()["detail"] == reset_detail
    finally:
        db.close()


def test_delete_account_purges_everything(client):
    from app.models.course import Course
    from app.models.email_otp import EmailOtpCode
    from app.models.user import User
    from app.services.database import SessionLocal

    token = _register_and_verify(client, "deleteme@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    course_res = client.post("/api/courses", headers=headers, json={"filenames": ["doc.pdf"]})
    assert course_res.status_code == 201

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "deleteme@example.com").first()
        assert user is not None
        user_id = user.id
        assert db.query(Course).filter(Course.user_id == user_id).count() == 1
    finally:
        db.close()

    del_res = client.request(
        "DELETE", "/api/auth/me", headers=headers, json={"password": "password123"}
    )
    assert del_res.status_code == 200, del_res.text

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == user_id).first() is None
        assert db.query(Course).filter(Course.user_id == user_id).count() == 0
        assert db.query(EmailOtpCode).filter(EmailOtpCode.user_id == user_id).count() == 0
    finally:
        db.close()

    # The token used to delete the account must be blacklisted immediately.
    me_after = client.get("/api/auth/me", headers=headers)
    assert me_after.status_code == 401


def test_cors_headers(client):
    # Test preflight OPTIONS request
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    response = client.options("/api/auth/login", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"
