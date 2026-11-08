from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings
from app.db import get_db
from app.security import decode_access_token
from app.services.access import Ctx


def _local_admin(db: Session) -> m.User:
    user = db.scalar(select(m.User).where(m.User.email == "local@weazel.local"))
    if user is None:
        role = db.scalar(select(m.Role).where(m.Role.key == "system_admin"))
        user = m.User(email="local@weazel.local", display_name=get_settings().LOCAL_ADMIN_NAME, role_id=role.id if role else None,
                      source="local", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_ctx(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> Ctx:
    settings = get_settings()
    if settings.AUTH_MODE == "local":
        return Ctx(db, _local_admin(db))
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(authorization[7:].strip())
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    try:
        user = db.get(m.User, int(claims["sub"]))
    except (ValueError, TypeError):
        user = None
    # token_version lets an administrator invalidate every token of a user (password change, dismissal)
    if user is None or not user.is_active or claims.get("tv") != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return Ctx(db, user)


def require(*perms: str):
    """Route dependency: every listed permission is required (checked server-side, not by the UI)."""
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        missing = [p for p in perms if not ctx.can(p)]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
        return ctx
    return dep


def paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return (page - 1) * page_size, page_size
