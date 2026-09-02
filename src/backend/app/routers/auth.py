"""Authentication router."""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import logger, settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    clear_auth_cookie,
    create_access_token,
    get_password_hash,
    set_auth_cookie,
    verify_password,
)
from app.models.course import Course
from app.models.email_otp import EmailOtpCode
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas.user import (
    DeleteAccountRequest,
    ForgotPasswordRequest,
    MessageResponse,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    VerifyEmailRequest,
)
from app.services import email_service, otp_service
from app.services.cache import cache
from app.services.otp_service import OtpVerificationError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_request_token(request: Request) -> Optional[str]:
    """Read the JWT from either the Authorization header or the HttpOnly cookie —
    shared by logout and account deletion, both of which blacklist the current token."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return request.cookies.get(settings.AUTH_COOKIE_NAME)


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> Any:
    """Register a new user (unverified) and email a 6-digit verification code.

    Does NOT log the user in — login is blocked until /verify-email succeeds."""
    existing_user = db.query(User).filter(User.email == user_in.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được sử dụng. Vui lòng chọn email khác.",
        )

    db_user = User(
        email=user_in.email.lower(),
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role="user",
        is_active=True,
        is_verified=False,
    )
    db.add(db_user)
    db.flush()

    code = otp_service.create_otp(db, db_user, otp_service.PURPOSE_VERIFY_EMAIL, commit=False)

    try:
        email_service.send_verification_code(db_user.email, code)
    except Exception as e:
        db.rollback()
        logger.error("Failed to send verification email during register: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không gửi được email xác thực. Vui lòng thử lại sau.",
        )

    db.commit()
    return {
        "email": db_user.email,
        "message": "Đăng ký thành công. Vui lòng kiểm tra email để lấy mã xác thực.",
    }


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(
    payload: VerifyEmailRequest, response: Response, db: Session = Depends(get_db)
) -> Any:
    """Confirm a verification code and log the user in on success."""
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email hoặc mã không đúng.")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã được xác thực trước đó.")

    try:
        otp_service.verify_otp(db, user, otp_service.PURPOSE_VERIFY_EMAIL, payload.code)
    except OtpVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    user.is_verified = True
    db.commit()
    db.refresh(user)

    access_token = create_access_token({"sub": user.id, "role": user.role})
    set_auth_cookie(response, access_token)
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)) -> Any:
    """Re-send a verification code. Response is intentionally generic to avoid leaking
    whether an email is registered."""
    generic = {"message": "Nếu email hợp lệ và chưa xác thực, mã mới đã được gửi."}

    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or user.is_verified:
        return generic

    if otp_service.seconds_until_resend_allowed(db, user, otp_service.PURPOSE_VERIFY_EMAIL) > 0:
        return generic

    code = otp_service.create_otp(db, user, otp_service.PURPOSE_VERIFY_EMAIL)
    try:
        email_service.send_verification_code(user.email, code)
    except Exception as e:
        logger.error("Failed to resend verification email: %s", e)
    return generic


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> Any:
    """Always responds generically to avoid leaking which emails are registered."""
    generic = {"message": "Nếu email tồn tại, mã đặt lại mật khẩu đã được gửi."}

    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not user.is_active:
        return generic

    if otp_service.seconds_until_resend_allowed(db, user, otp_service.PURPOSE_RESET_PASSWORD) > 0:
        return generic

    code = otp_service.create_otp(db, user, otp_service.PURPOSE_RESET_PASSWORD)
    try:
        email_service.send_password_reset_code(user.email, code)
    except Exception as e:
        logger.error("Failed to send password reset email: %s", e)
    return generic


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> Any:
    """Verify the reset code and set a new password. Does not auto-login."""
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email hoặc mã không đúng.")

    try:
        otp_service.verify_otp(db, user, otp_service.PURPOSE_RESET_PASSWORD, payload.code)
    except OtpVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại."}


@router.post("/login", response_model=TokenResponse)
def login(
    user_in: UserLogin, response: Response, db: Session = Depends(get_db)
) -> Any:
    """Authenticate user credentials and set HttpOnly JWT cookie."""
    user = db.query(User).filter(User.email == user_in.email.lower()).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản của bạn đã bị vô hiệu hóa.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_not_verified",
                "message": "Tài khoản chưa xác thực email. Vui lòng kiểm tra email hoặc gửi lại mã.",
            },
        )

    access_token = create_access_token({"sub": user.id, "role": user.role})
    set_auth_cookie(response, access_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Invalidate current JWT token by adding to blacklist and clearing HttpOnly cookie."""
    token = _get_request_token(request)

    if token:
        # Blacklist token in memory cache for remaining TTL (default 7 days = 604800s)
        cache.set(
            f"blacklist:{token}", "revoked", ttl_seconds=settings.JWT_EXPIRE_MINUTES * 60
        )

    clear_auth_cookie(response)
    return {"detail": "Đăng xuất thành công."}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> Any:
    """Get current authenticated user information."""
    return current_user


@router.delete("/me", response_model=MessageResponse)
def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Permanently delete the caller's own account: every course's uploads + vector store
    chunks, processing jobs, all OTP codes, and the user row itself. SQLite doesn't enforce the FK
    ondelete=CASCADE on these tables (no PRAGMA foreign_keys=ON anywhere in this codebase),
    so each dependent table is cleaned up explicitly rather than relying on it."""
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mật khẩu không chính xác.")

    courses = db.query(Course).filter(Course.user_id == current_user.id).all()
    course_ids = [course.id for course in courses]
    db.query(ProcessingJob).filter(
        or_(
            ProcessingJob.user_id == current_user.id,
            ProcessingJob.course_id.in_(course_ids),
        )
    ).delete(synchronize_session=False)
    if courses:
        from app.services.document_processor import get_document_processor

        processor = get_document_processor()
        for course in courses:
            processor.purge_course_storage(course.id)
            db.delete(course)

    db.query(EmailOtpCode).filter(EmailOtpCode.user_id == current_user.id).delete()
    db.delete(current_user)
    db.commit()

    token = _get_request_token(request)
    if token:
        cache.set(f"blacklist:{token}", "revoked", ttl_seconds=settings.JWT_EXPIRE_MINUTES * 60)
    clear_auth_cookie(response)

    return {"message": "Tài khoản đã được xóa vĩnh viễn."}
