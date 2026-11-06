"""FiveM bridge authentication. The game server signs every request; the API trusts nothing the browser or a player sends about identity.

Canonical string signed with HMAC-SHA256:  METHOD \\n PATH \\n TIMESTAMP \\n NONCE \\n SHA256(BODY)
Rejected: wrong/missing signature, timestamp outside the allowed skew (stale or future), a nonce seen before (replay), body over 256 KB.
All rejections look identical to the caller (401) so nothing is learned from the failure mode."""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings
from app.db import get_db

MAX_BODY = 256 * 1024
REJECT = HTTPException(401, "Invalid bridge request")


def canonical(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    return "\n".join([method.upper(), path, timestamp, nonce, hashlib.sha256(body).hexdigest()]).encode()


def sign(secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    return hmac.new(secret.encode(), canonical(method, path, timestamp, nonce, body), hashlib.sha256).hexdigest()


async def verified_body(request: Request, db: Session = Depends(get_db)) -> bytes:
    s = get_settings()
    if not s.BRIDGE_SECRET:
        raise HTTPException(503, "The FiveM bridge is not configured")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "Request too large")
    ts, nonce, sig = (request.headers.get(h, "") for h in ("x-weazel-timestamp", "x-weazel-nonce", "x-weazel-signature"))
    if not (ts.isdigit() and 16 <= len(nonce) <= 64 and nonce.isalnum() and len(sig) == 64):
        raise REJECT
    if abs(time.time() - int(ts)) > s.BRIDGE_MAX_SKEW_SECONDS:
        raise REJECT
    expected = sign(s.BRIDGE_SECRET, request.method, request.url.path, ts, nonce, body)
    if not hmac.compare_digest(expected, sig.lower()):
        raise REJECT
    # Only a correctly signed request may consume a nonce, so outsiders cannot fill the table.
    db.execute(delete(m.BridgeNonce).where(m.BridgeNonce.seen_at < datetime.now(timezone.utc) - timedelta(seconds=s.BRIDGE_MAX_SKEW_SECONDS * 2 + 60)))
    db.add(m.BridgeNonce(nonce=nonce))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise REJECT  # the same signed request was already used
    return body
