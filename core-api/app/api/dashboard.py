from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, func, select, text

from app import models as m
from app.deps import get_ctx
from app.permissions import PUBLIC_STATUSES
from app.services.access import Ctx, visible_article_filter, visible_investigation_filter

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(get_ctx)):
    db, now = ctx.db, datetime.now(timezone.utc)
    vis_art, vis_inv = visible_article_filter(ctx), visible_investigation_filter(ctx)
    out: dict = {}

    def count(q) -> int:
        return db.scalar(q) or 0

    if ctx.can("article.review") or ctx.can("article.approve"):
        out["awaiting_review"] = [{"id": a.id, "title": a.title, "status": a.status, "updated_at": a.updated_at} for a in db.scalars(
            select(m.Article).where(m.Article.status.in_(["submitted", "in_review"]), vis_art).order_by(m.Article.updated_at).limit(10))]
        out["awaiting_review_total"] = count(select(func.count()).select_from(m.Article).where(m.Article.status.in_(["submitted", "in_review"]), vis_art))
    mine = (m.Article.author_id == ctx.user.id) | exists().where(m.ArticleAssignee.article_id == m.Article.id, m.ArticleAssignee.user_id == ctx.user.id)
    out["revision_requests"] = [{"id": a.id, "title": a.title, "updated_at": a.updated_at} for a in db.scalars(
        select(m.Article).where(m.Article.status == "revision_requested", mine).order_by(m.Article.updated_at.desc()).limit(10))]
    out["my_drafts"] = count(select(func.count()).select_from(m.Article).where(m.Article.status.in_(["idea", "draft"]), m.Article.author_id == ctx.user.id))
    out["scheduled"] = [{"id": a.id, "title": a.title, "scheduled_for": a.scheduled_for} for a in db.scalars(
        select(m.Article).where(m.Article.status == "scheduled", vis_art).order_by(m.Article.scheduled_for).limit(10))]
    out["breaking_recent"] = [{"id": a.id, "title": a.title, "published_at": a.published_at} for a in db.scalars(
        select(m.Article).where(m.Article.is_breaking.is_(True), m.Article.status.in_(PUBLIC_STATUSES), m.Article.published_at > now - timedelta(days=7))
        .order_by(m.Article.published_at.desc()).limit(5))]

    active = and_(vis_inv, m.Investigation.is_archived.is_(False), m.Investigation.status.notin_(
        select(m.LookupValue.key).where(m.LookupValue.kind == "investigation_status", m.LookupValue.is_terminal.is_(True))))
    out["active_investigations_total"] = count(select(func.count()).select_from(m.Investigation).where(active))
    out["active_investigations"] = [{"id": i.id, "reference": i.reference, "title": i.title, "priority": i.priority, "status": i.status} for i in db.scalars(
        select(m.Investigation).where(active).order_by(m.Investigation.updated_at.desc()).limit(8))]

    visible_ids = select(m.Investigation.id).where(vis_inv)
    out["my_tasks"] = [{"id": t.id, "title": t.title, "due_date": t.due_date, "investigation_id": t.investigation_id} for t in db.scalars(
        select(m.InvestigationTask).where(m.InvestigationTask.assignee_id == ctx.user.id, m.InvestigationTask.status == "open",
                                          m.InvestigationTask.investigation_id.in_(visible_ids)).order_by(m.InvestigationTask.due_date.nullslast()).limit(10))]
    horizon = date.today() + timedelta(days=14)
    out["upcoming_deadlines"] = (
        [{"type": "task", "id": t.id, "title": t.title, "due_date": t.due_date, "investigation_id": t.investigation_id} for t in db.scalars(
            select(m.InvestigationTask).where(m.InvestigationTask.status == "open", m.InvestigationTask.due_date <= horizon,
                                              m.InvestigationTask.investigation_id.in_(visible_ids)).order_by(m.InvestigationTask.due_date).limit(10))]
        + [{"type": "investigation", "id": i.id, "title": i.title, "due_date": i.target_date, "investigation_id": i.id} for i in db.scalars(
            select(m.Investigation).where(active, m.Investigation.target_date <= horizon).order_by(m.Investigation.target_date).limit(10))])

    weeks = db.execute(text("""
        SELECT date_trunc('week', published_at)::date AS wk, count(*) FROM articles
        WHERE published_at > now() - interval '8 weeks' AND status IN ('published','corrected') GROUP BY 1 ORDER BY 1""")).all()
    out["publication_by_week"] = [{"week": r[0], "count": r[1]} for r in weeks]
    out["review_turnaround_hours_median"] = db.scalar(text("""
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (e2.created_at - e1.created_at))/3600)
        FROM article_events e1 JOIN article_events e2 ON e2.article_id = e1.article_id AND e1.to_status = 'submitted'
         AND e2.to_status IN ('approved','revision_requested') AND e2.created_at > e1.created_at
        WHERE e2.created_at > now() - interval '30 days'"""))
    if ctx.can("staff.view"):
        rows = db.execute(select(m.User.id, m.User.display_name, func.count(m.ArticleAssignee.article_id)).join(
            m.ArticleAssignee, m.ArticleAssignee.user_id == m.User.id).join(m.Article, m.Article.id == m.ArticleAssignee.article_id).where(
            m.Article.status.in_(["idea", "draft", "submitted", "in_review", "revision_requested"]), m.User.is_active.is_(True)).group_by(m.User.id, m.User.display_name))
        out["workload"] = [{"user_id": r[0], "display_name": r[1], "assigned_articles": r[2]} for r in rows]
    if ctx.can("settings.manage"):
        try:
            db.execute(text("select 1"))
            out["services"] = {"database": "ok"}
        except Exception:
            out["services"] = {"database": "error"}
    out["recent_activity"] = [{"article_id": e.article_id, "kind": e.kind, "to_status": e.to_status, "at": e.created_at} for e in db.scalars(
        select(m.ArticleEvent).join(m.Article, m.Article.id == m.ArticleEvent.article_id).where(vis_art).order_by(m.ArticleEvent.id.desc()).limit(10))]
    return out
