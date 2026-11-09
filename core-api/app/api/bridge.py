"""Endpoints called by the FiveM game server (signed) and the one-time ticket exchange used by the browser."""
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import models as m
from app.api.common import clean_text
from app.config import get_settings
from app.db import get_db
from app.permissions import PUBLIC_STATUSES
from app.security import create_access_token, login_limiter
from app.services import audit
from app.services.bridge import verified_body

router = APIRouter(tags=["bridge"])
CID = re.compile(r"^[A-Za-z0-9]{3,50}$")


def _parse(model, body: bytes):
    try:
        return model.model_validate(json.loads(body or b"{}"))
    except (ValueError, ValidationError):
        raise HTTPException(422, "Invalid request body")


class Player(BaseModel):
    citizenid: str = Field(pattern=r"^[A-Za-z0-9]{3,50}$")
    name: str = Field(min_length=1, max_length=120)
    job: str = Field(min_length=1, max_length=50)
    grade: int = Field(ge=0, le=100)


def _mapping(db: Session):
    return {(j.job_name, j.grade_level): j.role_id for j in db.scalars(select(m.JobGradeMapping))}


def _default_role_id(db: Session):
    key = get_settings().FIVEM_DEFAULT_ROLE.strip()
    return db.scalar(select(m.Role.id).where(m.Role.key == key)) if key else None


def _apply_player(db: Session, p: Player, mapping: dict, roles: dict, default_role_id, out: dict):
    """Make the account of one character match what the game says. Employment maps to a role through the job table; a character whose
    job is not mapped (unemployed, any other job, former staff) gets the default role, so every character can open the newsroom.
    Never touched: accounts created locally and roles set by hand (`role_locked`)."""
    user = db.scalar(select(m.User).where(m.User.citizen_id == p.citizenid))
    if user is not None and user.source == "local":
        out["skipped_local"] += 1
        return user
    staff_role = mapping.get((p.job, p.grade))
    role_id = staff_role if staff_role is not None else default_role_id
    if role_id is None:  # unmapped and no default role configured: no newsroom access
        if user is not None and user.is_active:
            user.is_active, user.employment_status, user.employment_job, user.employment_grade = False, "former", p.job, p.grade
            user.token_version += 1  # sessions end immediately
            audit.record(db, None, "bridge.deactivated", "user", user.id, detail={"job": p.job, "grade": p.grade})
            out["deactivated"] += 1
        else:
            out["skipped_unmapped"] += 1
        return user
    if user is None:
        user = m.User(citizen_id=p.citizenid, display_name=clean_text(p.name, 120), role_id=role_id, source="fivem",
                      employment_job=p.job, employment_grade=p.grade, employment_status="active")
        db.add(user)
        db.flush()
        audit.record(db, None, "bridge.user_created", "user", user.id, detail={"role": roles[role_id]})
        out["created"] += 1
        return user
    changed = False
    if not user.is_active and user.employment_status == "former":  # deactivated by an earlier sync, not by a person
        user.is_active, user.employment_status, changed = True, "active", True
        audit.record(db, None, "bridge.reactivated", "user", user.id)
        out["reactivated"] += 1
    user.source = "fivem"
    user.display_name = clean_text(p.name, 120) or user.display_name
    user.employment_job, user.employment_grade = p.job, p.grade
    if user.role_id != role_id and not user.role_locked and user.is_active:
        audit.record(db, None, "bridge.role_changed", "user", user.id, detail={"from": roles.get(user.role_id), "to": roles[role_id]})
        if staff_role is None and user.role_id is not None and user.role_id != default_role_id:
            user.employment_status = "former"   # had a newsroom job, no longer does
        elif staff_role is not None and user.employment_status == "former":
            user.employment_status = "active"
        user.role_id = role_id
        user.token_version += 1
        out["role_changed"] += 1
        changed = True
    elif user.role_id is None and user.is_active:
        user.role_id = role_id
    out["updated"] += int(changed)
    return user


def _counters():
    return dict(created=0, updated=0, role_changed=0, deactivated=0, reactivated=0, skipped_local=0, skipped_unmapped=0)


class SessionIn(BaseModel):
    citizenid: str = Field(pattern=r"^[A-Za-z0-9]{3,50}$")
    # What the game server says about this character right now (read server-side from QBCore, never from the player's client).
    name: str | None = Field(default=None, min_length=1, max_length=120)
    job: str | None = Field(default=None, min_length=1, max_length=50)
    grade: int | None = Field(default=None, ge=0, le=100)


@router.post("/bridge/session")
async def issue_ticket(body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    """The game server vouches for a character (it knows the player's source -> character); we bring that character's account up to
    date from the job the game reports (creating it on first use) and mint a one-time ticket for it. The player's own client never
    supplies any of this, so it cannot ask for someone else's ticket or claim a job."""
    s = get_settings()
    data = _parse(SessionIn, body)
    if data.name and data.job is not None and data.grade is not None:
        roles = {r.id: r.key for r in db.scalars(select(m.Role))}
        user = _apply_player(db, Player(citizenid=data.citizenid, name=data.name, job=data.job, grade=data.grade),
                             _mapping(db), roles, _default_role_id(db), _counters())
        db.flush()
    else:
        user = db.scalar(select(m.User).where(m.User.citizen_id == data.citizenid))
    if user is None or not user.is_active or user.role_id is None:
        db.commit()
        raise HTTPException(404, "No newsroom account for this character")
    recent = db.scalar(select(func.count()).select_from(m.BridgeTicket).where(
        m.BridgeTicket.user_id == user.id, m.BridgeTicket.created_at > datetime.now(timezone.utc) - timedelta(minutes=1))) or 0
    if recent >= 5:
        db.commit()
        raise HTTPException(429, "Too many login tickets requested")
    ticket = secrets.token_urlsafe(32)
    db.add(m.BridgeTicket(token_hash=hashlib.sha256(ticket.encode()).hexdigest(), user_id=user.id,
                          expires_at=datetime.now(timezone.utc) + timedelta(seconds=s.TICKET_TTL_SECONDS)))
    audit.record(db, user, "bridge.ticket_issued", "user", user.id)
    db.commit()
    return {"ticket": ticket, "expires_in": s.TICKET_TTL_SECONDS, "url": f"{s.PUBLIC_BASE_URL.rstrip('/')}/fivem-login?ticket={ticket}"}


class ExchangeIn(BaseModel):
    ticket: str = Field(min_length=20, max_length=100)


@router.post("/auth/fivem-exchange")
def exchange(data: ExchangeIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.BRIDGE_SECRET or s.AUTH_MODE == "local":
        raise HTTPException(404, "Not available")
    key = f"ticket|{request.client.host if request.client else '?'}"
    if login_limiter.blocked(key, s.LOGIN_MAX_ATTEMPTS * 4, s.LOGIN_WINDOW_SECONDS):
        raise HTTPException(429, "Too many attempts, try again later")
    h = hashlib.sha256(data.ticket.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    # single atomic claim: two simultaneous exchanges of the same ticket cannot both succeed
    claimed = db.execute(update(m.BridgeTicket).where(m.BridgeTicket.token_hash == h, m.BridgeTicket.used_at.is_(None), m.BridgeTicket.expires_at > now)
                         .values(used_at=now).returning(m.BridgeTicket.user_id)).scalar_one_or_none()
    user = db.get(m.User, claimed) if claimed else None
    if user is None or not user.is_active or user.role_id is None:
        login_limiter.hit(key)
        db.rollback() if claimed is None else db.commit()
        raise HTTPException(401, "Invalid or expired ticket")
    user.last_login_at = now
    audit.record(db, user, "auth.login_fivem", "user", user.id)
    db.commit()
    return {"access_token": create_access_token(user.id, user.token_version), "token_type": "bearer", "expires_in": s.ACCESS_TOKEN_MINUTES * 60}


class SyncIn(BaseModel):
    players: list[Player] = Field(max_length=500)


@router.post("/bridge/sync-staff")
async def sync_staff(body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    """QBCore is authoritative for employment. Employment maps to an application role through the configurable job/grade table;
    a reported player whose job is not mapped drops to the default role (freelancer). Never touched: accounts created locally
    (administrators, password accounts) and roles set by hand (`role_locked`). Absent players are left alone."""
    data = _parse(SyncIn, body)
    mapping, default_role_id = _mapping(db), _default_role_id(db)
    roles = {r.id: r.key for r in db.scalars(select(m.Role))}
    out = _counters()
    for p in data.players:
        _apply_player(db, p, mapping, roles, default_role_id, out)
    db.commit()
    return out


@router.get("/bridge/staff-ids")
async def staff_ids(body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    """Citizen ids of newsroom staff that employment sync manages (everyone above the default role). The game server includes them in
    its next report even if their job changed, so a dismissal made while the player was offline still reaches the platform.
    Freelancers are not listed: their account is brought up to date whenever they open the tablet."""
    q = select(m.User.citizen_id).where(m.User.citizen_id.is_not(None), m.User.source.in_(["fivem", "legacy"]))
    default_role_id = _default_role_id(db)
    if default_role_id is not None:
        q = q.where(m.User.role_id.is_distinct_from(default_role_id))
    rows = db.scalars(q.order_by(m.User.id).limit(2000))
    return {"citizenids": list(rows)}


class PollIn(BaseModel):
    since: datetime | None = None
    online: list[str] = Field(default_factory=list, max_length=300)


@router.post("/bridge/news/poll")
async def poll_news(body: bytes = Depends(verified_body), db: Session = Depends(get_db)):
    """In-game delivery, pull model (same as the DOJ tablet): the game server asks what is new for the players who are ONLINE.
    Nothing is pushed to the game server and no Discord is involved. Only short titles leave the API.
    - `broadcast`: articles published since the cursor, for every online player (public news, same rule as /public).
    - `personal`: notifications created since the cursor for online staff (they already carry only what that person could read).
    The first call (no cursor) returns only the new cursor, so a restart never replays old news."""
    data = _parse(PollIn, body)
    s = get_settings()
    now = datetime.now(timezone.utc)
    if data.since is None:
        return {"now": now, "broadcast": [], "personal": []}
    since = data.since if data.since.tzinfo else data.since.replace(tzinfo=timezone.utc)
    ids = list(dict.fromkeys(c for c in data.online if CID.match(c)))
    if not ids:
        return {"now": now, "broadcast": [], "personal": []}
    limit = s.NEWS_POLL_MAX_ITEMS
    arts = db.scalars(select(m.Article).where(m.Article.status.in_(PUBLIC_STATUSES), m.Article.published_at > since, m.Article.published_at <= now)
                      .order_by(m.Article.published_at.asc()).limit(limit))
    broadcast = [{"article_id": a.id, "title": a.title[:120]} for a in arts]
    rows = db.execute(select(m.Notification, m.User.citizen_id).join(m.User, m.User.id == m.Notification.user_id)
                      .where(m.Notification.created_at > since, m.Notification.created_at <= now, m.User.citizen_id.in_(ids),
                             m.User.is_active.is_(True), m.User.role_id.is_not(None))
                      .order_by(m.Notification.id.asc()).limit(limit))
    personal = [{"citizenid": cid, "title": n.title[:120]} for n, cid in rows]
    return {"now": now, "broadcast": broadcast, "personal": personal}
