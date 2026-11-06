from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings
from app.db import get_db
from app.deps import get_ctx
from app.security import create_access_token, hash_password, login_limiter, verify_password
from app.services import audit
from app.services.access import Ctx

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if s.AUTH_MODE not in {"password", "fivem"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Password login is disabled in this mode")
    email = data.email.strip().lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    if login_limiter.blocked(key, s.LOGIN_MAX_ATTEMPTS, s.LOGIN_WINDOW_SECONDS):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
    user = db.scalar(select(m.User).where(func.lower(m.User.email) == email))
    ok = verify_password(data.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        login_limiter.hit(key)
        audit.record(db, None, "auth.login_failed", "user", user.id if user else None, detail={"email": email[:80]})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")  # same answer for every failure
    login_limiter.reset(key)
    user.last_login_at = datetime.now(timezone.utc)
    audit.record(db, user, "auth.login", "user", user.id)
    db.commit()
    return {"access_token": create_access_token(user.id, user.token_version), "token_type": "bearer",
            "expires_in": s.ACCESS_TOKEN_MINUTES * 60}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx)):
    u = ctx.user
    return {"id": u.id, "display_name": u.display_name, "email": u.email, "citizen_id": u.citizen_id, "language": u.language,
            "role": {"key": u.role.key, "name": u.role.name, "rank": u.role.rank} if u.role else None,
            "permissions": sorted(ctx.perms), "auth_mode": get_settings().AUTH_MODE}


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


@router.post("/change-password")
def change_password(data: PasswordChange, ctx: Ctx = Depends(get_ctx)):
    u = ctx.user
    if get_settings().AUTH_MODE != "password" or not verify_password(data.current_password, u.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    u.password_hash = hash_password(data.new_password)
    u.token_version += 1  # every previously issued token stops working
    audit.record(ctx.db, u, "auth.password_changed", "user", u.id)
    ctx.db.commit()
    return {"access_token": create_access_token(u.id, u.token_version), "token_type": "bearer"}
