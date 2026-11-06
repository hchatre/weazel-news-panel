"""Outgoing messages with retry and de-duplication. Nothing is sent from a request: events are queued in the same transaction as the
action that caused them, and a worker delivers them. A queue entry survives restarts, an event is queued once (unique key), and a
failing Discord never blocks or fails publication."""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings

log = logging.getLogger("weazel.outbox")


def enqueue(db: Session, channel: str, event_key: str, payload: dict) -> bool:
    res = db.execute(insert(m.OutboxMessage).values(channel=channel, event_key=event_key[:120], payload=payload).on_conflict_do_nothing(index_elements=["event_key"]))
    return bool(res.rowcount)


def _safe(text: str, limit: int) -> str:
    # a zero-width space after "@" keeps @everyone / @here / <@id> from pinging anyone even if allowed_mentions were ignored
    return (text or "").replace("@", "@\u200b")[:limit]


def publish_payload(art: m.Article, author: str | None, kind: str) -> dict:
    s = get_settings()
    title = ("Correction: " if kind == "corrected" else "") + art.title
    embed = {"title": _safe(title, 256), "description": _safe(art.summary or "", 300), "url": f"{s.PUBLIC_BASE_URL.rstrip('/')}/articles/{art.id}",
             "footer": {"text": _safe(f"{author or 'Weazel News'}", 100)}}
    return {"allowed_mentions": {"parse": []}, "embeds": [embed]}  # only public facts: no body, notes, sources or investigation data


class SendResult:
    def __init__(self, ok=False, retry_after: float | None = None, permanent=False, error=""):
        self.ok, self.retry_after, self.permanent, self.error = ok, retry_after, permanent, error


def discord_send(channel: str, payload: dict, transport: httpx.BaseTransport | None = None) -> SendResult:
    url = {"publish": get_settings().DISCORD_WEBHOOK_PUBLISH}.get(channel, "")
    if not url:
        return SendResult(permanent=True, error="channel not configured")
    try:
        with httpx.Client(timeout=10, follow_redirects=False, transport=transport) as c:
            r = c.post(url, json=payload)
    except httpx.HTTPError as e:
        return SendResult(error=type(e).__name__)  # network trouble: retry; the URL is never put in the message
    if r.status_code in (200, 204):
        return SendResult(ok=True)
    if r.status_code == 429:
        try:
            wait = float(r.json().get("retry_after", r.headers.get("retry-after", 5)))
        except (ValueError, TypeError):
            wait = 5.0
        return SendResult(retry_after=min(max(wait, 1.0), 3600.0), error="rate limited")
    if 500 <= r.status_code < 600:
        return SendResult(error=f"HTTP {r.status_code}")
    return SendResult(permanent=True, error=f"HTTP {r.status_code}")  # bad webhook / payload: retrying cannot help


def process_due(db: Session, sender=discord_send, now: datetime | None = None, limit: int = 20) -> dict:
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    stats = {"sent": 0, "retry": 0, "dead": 0}
    rows = db.scalars(select(m.OutboxMessage).where(m.OutboxMessage.status == "pending", m.OutboxMessage.next_attempt_at <= now)
                      .order_by(m.OutboxMessage.id).limit(limit).with_for_update(skip_locked=True)).all()  # two workers never take the same row
    for row in rows:
        res = sender(row.channel, row.payload)
        row.attempts += 1
        if res.ok:
            row.status, row.sent_at, row.last_error = "sent", now, ""
            stats["sent"] += 1
        elif res.permanent or row.attempts >= s.DISCORD_MAX_ATTEMPTS:
            row.status, row.last_error = "dead", (res.error or "failed")[:200]
            stats["dead"] += 1
            log.warning("outbox message %s gave up after %s attempts: %s", row.id, row.attempts, res.error)
        else:
            delay = res.retry_after if res.retry_after else min(30 * 2 ** (row.attempts - 1), 3600)
            row.next_attempt_at, row.last_error = now + timedelta(seconds=delay), (res.error or "failed")[:200]
            stats["retry"] += 1
        db.commit()  # commit per message so a crash never re-sends one that was already delivered
    return stats
