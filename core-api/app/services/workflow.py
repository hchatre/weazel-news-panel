from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app import models as m
from app.services import audit
from app.services.access import Ctx


def is_involved(ctx: Ctx, art: m.Article) -> bool:
    """Author or assignee: the people who cannot independently review or approve their own work."""
    if art.author_id == ctx.user.id:
        return True
    return ctx.db.scalar(select(m.ArticleAssignee.user_id).where(
        m.ArticleAssignee.article_id == art.id, m.ArticleAssignee.user_id == ctx.user.id)) is not None


def snapshot(db, art: m.Article, user_id: int | None, note: str = "") -> m.ArticleRevision:
    last = db.scalar(select(m.ArticleRevision.revision_no).where(m.ArticleRevision.article_id == art.id)
                     .order_by(m.ArticleRevision.revision_no.desc()).limit(1)) or 0
    rev = m.ArticleRevision(article_id=art.id, revision_no=last + 1, title=art.title, subtitle=art.subtitle, summary=art.summary,
                            body=art.body, saved_by=user_id, change_note=note[:300])
    db.add(rev)
    db.flush()  # sessions do not autoflush: without this a second snapshot in the same request reuses the number
    return rev


def allowed_transitions(ctx: Ctx, art: m.Article) -> list[dict]:
    """What THIS user may do now. Informational for the UI; transition() re-checks everything."""
    out = []
    rows = ctx.db.scalars(select(m.WorkflowTransition).where(
        m.WorkflowTransition.from_status == art.status, m.WorkflowTransition.is_active.is_(True)))
    for t in rows:
        if _deny_reason(ctx, art, t) is None:
            out.append({"to": t.to_status, "requires_note": t.requires_note})
    return out


def _deny_reason(ctx: Ctx, art: m.Article, t: m.WorkflowTransition) -> str | None:
    if not ctx.can(t.permission_key):
        return "Permission denied"
    involved = is_involved(ctx, art)
    if t.permission_key == "article.edit.own" and art.author_id != ctx.user.id:
        return "Only the author can do this"
    if t.permission_key == "article.submit" and not (involved or ctx.can("article.edit.any")):
        return "Only the author, an assignee or an editor can submit this article"
    if t.independent and involved:
        return "Independent review is required: you cannot do this on your own work"
    return None


def transition(ctx: Ctx, art: m.Article, to_status: str, *, note: str = "", feedback: list | None = None,
               scheduled_for: datetime | None = None, destination: str | None = None) -> m.Article:
    db = ctx.db
    t = db.scalar(select(m.WorkflowTransition).where(
        m.WorkflowTransition.from_status == art.status, m.WorkflowTransition.to_status == to_status,
        m.WorkflowTransition.is_active.is_(True)))
    if t is None:
        raise HTTPException(409, f"Cannot move an article from '{art.status}' to '{to_status}'")
    reason = _deny_reason(ctx, art, t)
    if reason:
        raise HTTPException(403, reason)
    note = (note or "").strip()
    feedback = [f for f in (feedback or []) if isinstance(f, dict) and str(f.get("comment", "")).strip()]
    if t.requires_note and not note and not feedback:
        raise HTTPException(422, "A note or specific feedback is required for this step")
    now = datetime.now(timezone.utc)
    if to_status == "scheduled":
        if scheduled_for is None or scheduled_for.tzinfo is None or scheduled_for <= now:
            raise HTTPException(422, "scheduled_for must be a future timestamp with a time zone")
        art.scheduled_for = scheduled_for
    if to_status == "published":
        art.published_at = now
        art.published_destination = (destination or art.published_destination or "newsroom")[:100]
        art.scheduled_for = None
    if to_status == "submitted":
        if not art.title.strip() or not art.body.strip():
            raise HTTPException(422, "Title and body are required before submitting")
        snapshot(db, art, ctx.user.id, "submitted for review")
    if to_status == "corrected":
        art.correction_note, art.corrected_at = note, now
    from_status = art.status
    art.status = to_status
    art.version += 1
    art.platform_modified = True
    db.add(m.ArticleEvent(article_id=art.id, actor_id=ctx.user.id, kind="transition", from_status=from_status, to_status=to_status,
                          note=note[:4000], feedback=[{"field": str(f.get("field", ""))[:40], "comment": str(f["comment"])[:2000]} for f in feedback]))
    audit.record(db, ctx.user, f"article.{to_status}", "article", art.id, detail={"from": from_status, "to": to_status})
    return art
