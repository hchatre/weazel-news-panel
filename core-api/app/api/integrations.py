from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app import models as m
from app.api.common import NOT_FOUND
from app.config import get_settings
from app.deps import require
from app.services import audit
from app.services.access import Ctx

router = APIRouter(prefix="/admin/integrations", tags=["integrations"])


@router.get("/status")
def status(ctx: Ctx = Depends(require("settings.manage"))):
    s = get_settings()
    counts = dict(ctx.db.execute(select(m.OutboxMessage.status, func.count()).group_by(m.OutboxMessage.status)).all())
    rows = ctx.db.scalars(select(m.OutboxMessage).where(m.OutboxMessage.status != "sent").order_by(m.OutboxMessage.id.desc()).limit(50))
    # Never returns webhook URLs, the bridge secret, or message payloads.
    return {"bridge_configured": bool(s.BRIDGE_SECRET), "auth_mode": s.AUTH_MODE, "discord_publish_configured": bool(s.DISCORD_WEBHOOK_PUBLISH),
            "ai_provider": s.AI_PROVIDER, "outbox": {k: counts.get(k, 0) for k in ("pending", "sent", "dead")},
            "pending_or_failed": [{"id": r.id, "channel": r.channel, "event_key": r.event_key, "status": r.status, "attempts": r.attempts,
                                   "last_error": r.last_error, "next_attempt_at": r.next_attempt_at} for r in rows]}


@router.post("/outbox/{msg_id}/retry")
def retry(msg_id: int, ctx: Ctx = Depends(require("settings.manage"))):
    row = ctx.db.get(m.OutboxMessage, msg_id)
    if row is None:
        raise NOT_FOUND
    if row.status == "dead":
        row.status, row.attempts, row.last_error = "pending", 0, ""
        audit.record(ctx.db, ctx.user, "outbox.retry", "outbox", row.id, detail={"channel": row.channel})
        ctx.db.commit()
    return {"ok": True, "status": row.status}
