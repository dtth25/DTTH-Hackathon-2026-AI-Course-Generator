"""Common FastAPI dependencies."""

from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.models.user import User
from app.services.cache import cache
from app.services.database import get_db

security_bearer = HTTPBearer(auto_error=False)


def _unauthenticated(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Dependency to authenticate and return the current active user."""
    # Check Authorization header first, then HttpOnly cookie, then query param token
    token = (
        credentials.credentials
        if credentials and credentials.credentials
        else request.cookies.get(settings.AUTH_COOKIE_NAME) or request.query_params.get("token")
    )

    if not token:
        raise _unauthenticated("Vui lòng đăng nhập để truy cập tài nguyên này.")

    # Check if token is blacklisted (logged out)
    if cache.exists(f"blacklist:{token}"):
        raise _unauthenticated("Phiên đăng nhập đã bị hủy. Vui lòng đăng nhập lại.")

    payload = decode_access_token(token)
    if not payload:
        raise _unauthenticated("Phiên đăng nhập hết hạn hoặc không hợp lệ.")

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise _unauthenticated("Payload token không hợp lệ.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _unauthenticated("Tài khoản không tồn tại.")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa.",
        )

    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency requiring admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập chức năng quản trị.",
        )
    return current_user
