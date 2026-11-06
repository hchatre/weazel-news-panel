from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update

from app import models as m
from app.api.common import NOT_FOUND
from app.deps import get_ctx
from app.services.access import Ctx

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(unread: bool = False, limit: int = Query(30, ge=1, le=100), ctx: Ctx = Depends(get_ctx)):
    q = select(m.Notification).where(m.Notification.user_id == ctx.user.id)  # only ever your own
    if unread:
        q = q.where(m.Notification.read_at.is_(None))
    rows = ctx.db.scalars(q.order_by(m.Notification.id.desc()).limit(limit))
    return [{"id": n.id, "kind": n.kind, "title": n.title, "link": n.link, "created_at": n.created_at, "read": n.read_at is not None} for n in rows]


@router.get("/unread-count")
def unread_count(ctx: Ctx = Depends(get_ctx)):
    return {"count": ctx.db.scalar(select(func.count()).select_from(m.Notification).where(m.Notification.user_id == ctx.user.id, m.Notification.read_at.is_(None))) or 0}


@router.post("/read-all")
def read_all(ctx: Ctx = Depends(get_ctx)):
    ctx.db.execute(update(m.Notification).where(m.Notification.user_id == ctx.user.id, m.Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    ctx.db.commit()
    return {"ok": True}


@router.post("/{notification_id}/read")
def read_one(notification_id: int, ctx: Ctx = Depends(get_ctx)):
    n = ctx.db.get(m.Notification, notification_id)
    if n is None or n.user_id != ctx.user.id:
        raise NOT_FOUND
    n.read_at = n.read_at or datetime.now(timezone.utc)
    ctx.db.commit()
    return {"ok": True}
