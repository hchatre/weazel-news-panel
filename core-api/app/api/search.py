from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select

from app import models as m
from app.api.common import like_pattern, snippet
from app.deps import get_ctx
from app.services.access import Ctx, visible_article_filter, visible_investigation_filter

router = APIRouter(tags=["search"])


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=100), limit: int = Query(default=10, ge=1, le=25), ctx: Ctx = Depends(get_ctx)):
    """Global search. Every branch applies the same visibility rule as the matching list endpoint, and restricted
    timeline entries are filtered per investigation, so a hit can never reveal a record the user cannot open."""
    db, pat = ctx.db, like_pattern(q.strip())
    esc = "\\"
    arts = db.scalars(select(m.Article).where(and_(visible_article_filter(ctx), or_(
        m.Article.title.ilike(pat, escape=esc), m.Article.summary.ilike(pat, escape=esc), m.Article.body.ilike(pat, escape=esc)))
    ).order_by(m.Article.updated_at.desc()).limit(limit))
    invs = db.scalars(select(m.Investigation).where(and_(visible_investigation_filter(ctx), or_(
        m.Investigation.title.ilike(pat, escape=esc), m.Investigation.summary.ilike(pat, escape=esc), m.Investigation.reference.ilike(pat, escape=esc)))
    ).order_by(m.Investigation.updated_at.desc()).limit(limit))

    visible_ids = select(m.Investigation.id).where(visible_investigation_filter(ctx))
    entry_hits = []
    for e in db.scalars(select(m.InvestigationEntry).where(and_(
            m.InvestigationEntry.investigation_id.in_(visible_ids), m.InvestigationEntry.content.ilike(pat, escape=esc)))
            .order_by(m.InvestigationEntry.created_at.desc()).limit(limit * 3)):
        from app.services.access import entry_visible_filter, investigation_level
        inv = db.get(m.Investigation, e.investigation_id)
        level = investigation_level(ctx, inv)
        if level is None:
            continue
        if e.restricted and level != "lead" and not ctx.can("evidence.restrict") and e.author_id != ctx.user.id:
            continue
        entry_hits.append({"id": e.id, "investigation_id": inv.id, "reference": inv.reference, "snippet": snippet(e.content, q), "verification": e.verification})
        if len(entry_hits) >= limit:
            break

    sources = []
    if ctx.can("source.read"):  # identities are never searched
        for s in db.scalars(select(m.Source).where(and_(m.Source.investigation_id.in_(visible_ids), or_(
                m.Source.code.ilike(pat, escape=esc), m.Source.description.ilike(pat, escape=esc)))).limit(limit)):
            sources.append({"id": s.id, "investigation_id": s.investigation_id, "code": s.code, "snippet": snippet(s.description, q)})

    return {
        "articles": [{"id": a.id, "title": a.title, "status": a.status, "snippet": snippet(a.summary or a.body, q)} for a in arts],
        "investigations": [{"id": i.id, "reference": i.reference, "title": i.title, "status": i.status} for i in invs],
        "entries": entry_hits, "sources": sources,
    }
