from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings
from app.db import get_db
from app.permissions import PUBLIC_STATUSES

router = APIRouter(prefix="/public", tags=["public"])


def _public(a: m.Article, name: str | None, body: bool) -> dict:
    # explicit allow-list: internal notes, assignees, revision data and source references are never included
    d = {"id": a.id, "title": a.title, "subtitle": a.subtitle, "summary": a.summary, "category": a.category.key if a.category else None,
         "author": name or a.legacy_author_name, "published_at": a.published_at, "is_breaking": a.is_breaking, "cover_image_url": a.cover_image_url,
         "cover_caption": a.cover_caption, "cover_credit": a.cover_credit, "corrected_at": a.corrected_at, "correction_note": a.correction_note}
    if body:
        d["body"] = a.body
    return d


def _enabled() -> None:
    if not get_settings().PUBLIC_READ_ENABLED:
        raise HTTPException(404, "Not found")


@router.get("/articles")
def list_public(page: int = 1, page_size: int = Query(default=15, le=50), db: Session = Depends(get_db)):
    _enabled()
    page = max(1, page)
    q = select(m.Article).where(m.Article.status.in_(PUBLIC_STATUSES))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(db.scalars(q.order_by(m.Article.published_at.desc().nullslast(), m.Article.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    names = {u.id: u.display_name for u in db.scalars(select(m.User).where(m.User.id.in_({a.author_id for a in rows if a.author_id})))} if rows else {}
    return {"items": [_public(a, names.get(a.author_id), False) for a in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/articles/{article_id}")
def get_public(article_id: int, db: Session = Depends(get_db)):
    _enabled()
    a = db.get(m.Article, article_id)
    if a is None or a.status not in PUBLIC_STATUSES:
        raise HTTPException(404, "Not found")
    author = db.get(m.User, a.author_id) if a.author_id else None
    return _public(a, author.display_name if author else None, True)
