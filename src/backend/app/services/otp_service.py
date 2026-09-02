"""One-time code generation/verification for email verification and password reset."""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_otp import EmailOtpCode
from app.models.user import User

PURPOSE_VERIFY_EMAIL = "verify_email"
PURPOSE_RESET_PASSWORD = "reset_password"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_code() -> str:
    """Cryptographically random 6-digit code, zero-padded."""
    return f"{secrets.randbelow(1_000_000):06d}"


def latest_active_code(db: Session, user: User, purpose: str) -> Optional[EmailOtpCode]:
    return (
        db.query(EmailOtpCode)
        .filter(
            EmailOtpCode.user_id == user.id,
            EmailOtpCode.purpose == purpose,
            EmailOtpCode.consumed_at.is_(None),
        )
        .order_by(EmailOtpCode.created_at.desc())
        .first()
    )


def seconds_until_resend_allowed(db: Session, user: User, purpose: str) -> int:
    """0 if a new code may be sent now, otherwise seconds remaining in the cooldown."""
    existing = latest_active_code(db, user, purpose)
    if existing is None:
        return 0
    elapsed = (datetime.utcnow() - existing.created_at).total_seconds()
    remaining = settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


def create_otp(db: Session, user: User, purpose: str, commit: bool = True) -> str:
    """Invalidate any prior unconsumed code for this purpose and issue a fresh one.
    Returns the plaintext code — the only time it's ever available in cleartext.

    commit=False lets a caller (e.g. register) fold this into a larger transaction
    that it may still need to roll back (e.g. if sending the email fails)."""
    db.query(EmailOtpCode).filter(
        EmailOtpCode.user_id == user.id,
        EmailOtpCode.purpose == purpose,
        EmailOtpCode.consumed_at.is_(None),
    ).delete()

    code = generate_code()
    otp = EmailOtpCode(
        user_id=user.id,
        purpose=purpose,
        code_hash=_hash_code(code),
        expires_at=datetime.utcnow() + timedelta(minutes=settings.EMAIL_OTP_EXPIRE_MINUTES),
    )
    db.add(otp)
    if commit:
        db.commit()
    else:
        db.flush()
    return code


class OtpVerificationError(Exception):
    """A stable machine code plus safe public copy for an OTP check failure."""

    def __init__(self, code: str, message: str, *, remaining_attempts: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.remaining_attempts = remaining_attempts

    def detail(self) -> dict:
        detail = {"code": self.code, "message": self.message}
        if self.remaining_attempts is not None:
            detail["remaining_attempts"] = self.remaining_attempts
        return detail


def verify_otp(db: Session, user: User, purpose: str, submitted_code: str) -> None:
    """Raises OtpVerificationError on any failure; returns None (and consumes the code) on success."""
    otp = latest_active_code(db, user, purpose)
    if otp is None:
        raise OtpVerificationError("otp_missing", "Không tìm thấy mã xác thực đang hiệu lực. Vui lòng gửi lại mã.")

    if datetime.utcnow() > otp.expires_at:
        raise OtpVerificationError("otp_expired", "Mã xác thực đã hết hạn. Vui lòng gửi lại mã.")

    if otp.attempts >= settings.EMAIL_OTP_MAX_ATTEMPTS:
        raise OtpVerificationError("otp_locked", "Mã đã bị khóa do nhập sai quá nhiều lần. Vui lòng gửi lại mã.")

    if _hash_code(submitted_code.strip()) != otp.code_hash:
        otp.attempts += 1
        db.commit()
        remaining = max(0, settings.EMAIL_OTP_MAX_ATTEMPTS - otp.attempts)
        raise OtpVerificationError(
            "otp_invalid", "Mã xác thực không đúng.", remaining_attempts=remaining
        )

    otp.consumed_at = datetime.utcnow()
    db.commit()
