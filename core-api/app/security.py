import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        # constant-ish work so an unknown account is not distinguishable by timing
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"y", bcrypt.gensalt(rounds=4)))
        return False
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "tv": token_version, "iat": now, "exp": now + timedelta(minutes=s.ACCESS_TOKEN_MINUTES)}
    return jwt.encode(payload, s.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


class RateLimiter:
    """In-memory sliding window. Fine for one API process; use a shared store if you run several."""

    def __init__(self):
        self.hits: dict[str, list[float]] = {}

    def blocked(self, key: str, max_hits: int, window: int) -> bool:
        now = time.monotonic()
        recent = [t for t in self.hits.get(key, []) if now - t < window]
        self.hits[key] = recent
        return len(recent) >= max_hits

    def hit(self, key: str) -> None:
        self.hits.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self.hits.clear()
        else:
            self.hits.pop(key, None)


login_limiter = RateLimiter()
