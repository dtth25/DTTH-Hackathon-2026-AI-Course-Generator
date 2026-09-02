"""Admin router skeleton."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.deps import get_db, require_admin
from app.models.user import User
from app.schemas.user import UserResponse
from app.services.provider_health import get_openrouter_health

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def get_all_users(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin endpoint to list all users."""
    users = db.query(User).all()
    user_list = [UserResponse.model_validate(u) for u in users]
    return {"users": user_list, "message": f"Hello Admin {admin_user.email}"}


@router.get("/provider-health")
def provider_health(
    force: bool = False,
    _: User = Depends(require_admin),
) -> dict:
    """Expose only cached, redacted provider capacity state to administrators."""
    return get_openrouter_health(force=force).model_dump()
