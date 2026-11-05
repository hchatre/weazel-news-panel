import difflib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app import models as m
from app.api.common import NOT_FOUND, clean_text, like_pattern, safe_url
from app.deps import get_ctx, paginate, require
from app.permissions import ARTICLE_STATUSES, EDITABLE_BY_AUTHOR, EDITABLE_BY_EDITOR, PUBLIC_STATUSES
from app.services import audit, workflow
from app.services.access import Ctx, article_readable, investigation_level, visible_article_filter

router = APIRouter(prefix="/articles", tags=["articles"])
ARTICLE_TYPES = {"news", "feature", "opinion", "investigation", "breaking", "interview"}


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    subtitle: str = Field(default="", max_length=255)
    summary: str = Field(default="", max_length=2000)
    body: str = Field(default="", max_length=60000)
    category: str | None = None
    article_type: str = "news"
    tags: list[str] = Field(default_factory=list, max_length=20)
    is_breaking: bool = False
    cover_image_url: str | None = None
    cover_caption: str = Field(default="", max_length=300)
    cover_credit: str = Field(default="", max_length=200)
    source_refs: list[dict] = Field(default_factory=list, max_length=30)
    internal_notes: str = Field(default="", max_length=5000)


class ArticlePatch(BaseModel):
    expected_version: int
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    body: str | None = Field(default=None, max_length=60000)
    category: str | None = None
    article_type: str | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    is_breaking: bool | None = None
    cover_image_url: str | None = None
    cover_caption: str | None = Field(default=None, max_length=300)
    cover_credit: str | None = Field(default=None, max_length=200)
    source_refs: list[dict] | None = Field(default=None, max_length=30)
    internal_notes: str | None = Field(default=None, max_length=5000)
    change_note: str = Field(default="", max_length=300)


class TransitionIn(BaseModel):
    to: str
    note: str = Field(default="", max_length=4000)
    feedback: list[dict] = Field(default_factory=list, max_length=30)
    scheduled_for: datetime | None = None
    destination: str | None = Field(default=None, max_length=100)
    expected_version: int | None = None


class CorrectionIn(BaseModel):
    expected_version: int
    note: str = Field(min_length=3, max_length=4000)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    body: str | None = Field(default=None, max_length=60000)


def _category_id(db: Session, key: str | None) -> int | None:
    if not key:
        return None
    cid = db.scalar(select(m.Category.id).where(m.Category.key == key, m.Category.is_active.is_(True)))
    if cid is None:
        raise HTTPException(422, "Unknown category")
    return cid


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        t = clean_text(t, 50).lower()
        if t and t not in out:
            out.append(t)
    return out


def _get(ctx: Ctx, article_id: int) -> m.Article:
    art = ctx.db.get(m.Article, article_id)
    if art is None or not article_readable(ctx, art):
        raise NOT_FOUND
    return art


def _can_see_notes(ctx: Ctx, art: m.Article) -> bool:
    return ctx.can("article.notes.read") or ctx.can("article.review") or workflow.is_involved(ctx, art)


def can_edit(ctx: Ctx, art: m.Article) -> bool:
    if ctx.can("article.edit.any") and art.status in EDITABLE_BY_EDITOR:
        return True
    if art.status not in EDITABLE_BY_AUTHOR:
        return False
    if ctx.can("article.edit.own") and art.author_id == ctx.user.id:
        return True
    return ctx.can("article.edit.assigned") and workflow.is_involved(ctx, art)


def _names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {u.id: u.display_name for u in db.scalars(select(m.User).where(m.User.id.in_(ids)))}


def _summary_row(a: m.Article, names: dict[int, str]) -> dict:
    return {"id": a.id, "title": a.title, "subtitle": a.subtitle, "status": a.status, "category": a.category.key if a.category else None,
            "article_type": a.article_type, "is_breaking": a.is_breaking, "tags": a.tags or [],
            "author": names.get(a.author_id) or a.legacy_author_name, "author_id": a.author_id,
            "created_at": a.created_at, "updated_at": a.updated_at, "published_at": a.published_at, "scheduled_for": a.scheduled_for,
            "version": a.version}


def _detail(ctx: Ctx, art: m.Article) -> dict:
    db = ctx.db
    assignee_ids = list(db.scalars(select(m.ArticleAssignee.user_id).where(m.ArticleAssignee.article_id == art.id)))
    names = _names(db, {art.author_id, *assignee_ids} - {None})
    data = _summary_row(art, names)
    data.update(
        summary=art.summary, body=art.body, cover_image_url=art.cover_image_url, cover_caption=art.cover_caption,
        cover_credit=art.cover_credit, source_refs=art.source_refs or [], published_destination=art.published_destination,
        correction_note=art.correction_note, corrected_at=art.corrected_at,
        assignees=[{"id": i, "display_name": names.get(i)} for i in assignee_ids],
        can_edit=can_edit(ctx, art), allowed_transitions=workflow.allowed_transitions(ctx, art),
        can_correct=art.status in {"published", "corrected"} and ctx.can("article.correct"),
        internal_notes=art.internal_notes if _can_see_notes(ctx, art) else None,
    )
    # linked investigations: only those this user is allowed to know about (no existence leak)
    linked = []
    for inv in db.scalars(select(m.Investigation).join(m.ArticleInvestigation, m.ArticleInvestigation.investigation_id == m.Investigation.id)
                          .where(m.ArticleInvestigation.article_id == art.id)):
        if investigation_level(ctx, inv):
            linked.append({"id": inv.id, "reference": inv.reference, "title": inv.title})
    data["investigations"] = linked
    return data


@router.get("")
def list_articles(
    q: str | None = Query(default=None, max_length=100), status: str | None = None, category: str | None = None,
    author_id: int | None = None, mine: bool = False, assigned_to_me: bool = False, tag: str | None = None,
    breaking: bool | None = None, sort: str = "-updated_at", page: int = 1, page_size: int = 20, ctx: Ctx = Depends(get_ctx),
):
    db = ctx.db
    cond = [visible_article_filter(ctx)]
    if q:
        pat = like_pattern(q.strip())
        cond.append(or_(m.Article.title.ilike(pat, escape="\\"), m.Article.subtitle.ilike(pat, escape="\\"),
                        m.Article.summary.ilike(pat, escape="\\"), m.Article.body.ilike(pat, escape="\\")))
    if status:
        if status not in ARTICLE_STATUSES:
            raise HTTPException(422, "Unknown status")
        cond.append(m.Article.status == status)
    if category:
        cond.append(m.Article.category.has(m.Category.key == category))
    if author_id:
        cond.append(m.Article.author_id == author_id)
    if mine:
        cond.append(m.Article.author_id == ctx.user.id)
    if assigned_to_me:
        cond.append(exists().where(m.ArticleAssignee.article_id == m.Article.id, m.ArticleAssignee.user_id == ctx.user.id))
    if tag:
        cond.append(m.Article.tags.any(tag.lower()))
    if breaking is not None:
        cond.append(m.Article.is_breaking.is_(breaking))
    sorts = {"updated_at": m.Article.updated_at, "created_at": m.Article.created_at, "published_at": m.Article.published_at, "title": m.Article.title}
    col = sorts.get(sort.lstrip("-"))
    if col is None:
        raise HTTPException(422, "Unknown sort field")
    order = col.desc().nullslast() if sort.startswith("-") else col.asc().nullslast()
    offset, limit = paginate(page, page_size)
    total = db.scalar(select(func.count()).select_from(m.Article).where(and_(*cond))) or 0
    rows = list(db.scalars(select(m.Article).where(and_(*cond)).order_by(order, m.Article.id.desc()).offset(offset).limit(limit)))
    names = _names(db, {a.author_id for a in rows} - {None})
    return {"items": [_summary_row(a, names) for a in rows], "total": total, "page": max(1, page), "page_size": limit}


@router.post("", status_code=201)
def create_article(data: ArticleIn, ctx: Ctx = Depends(require("article.create"))):
    db = ctx.db
    if data.article_type not in ARTICLE_TYPES:
        raise HTTPException(422, "Unknown article type")
    art = m.Article(
        title=clean_text(data.title, 255), subtitle=clean_text(data.subtitle, 255), summary=clean_text(data.summary, 2000, multiline=True),
        body=clean_text(data.body, 60000, multiline=True), category_id=_category_id(db, data.category), article_type=data.article_type,
        tags=_clean_tags(data.tags), is_breaking=data.is_breaking, author_id=ctx.user.id, status="draft",
        cover_image_url=safe_url(data.cover_image_url), cover_caption=clean_text(data.cover_caption, 300), cover_credit=clean_text(data.cover_credit, 200),
        source_refs=data.source_refs, internal_notes=clean_text(data.internal_notes, 5000, multiline=True), platform_modified=True)
    if not art.title:
        raise HTTPException(422, "Title is required")
    db.add(art)
    db.flush()
    workflow.snapshot(db, art, ctx.user.id, "created")
    audit.record(db, ctx.user, "article.create", "article", art.id)
    db.commit()
    return _detail(ctx, art)


@router.get("/{article_id}")
def get_article(article_id: int, ctx: Ctx = Depends(get_ctx)):
    return _detail(ctx, _get(ctx, article_id))


@router.patch("/{article_id}")
def update_article(article_id: int, data: ArticlePatch, ctx: Ctx = Depends(get_ctx)):
    db = ctx.db
    art = _get(ctx, article_id)
    if not can_edit(ctx, art):
        if art.status in PUBLIC_STATUSES:
            raise HTTPException(409, "A published article cannot be edited; use the correction process")
        raise HTTPException(403, "You cannot edit this article in its current state")
    if data.expected_version != art.version:
        raise HTTPException(409, "This article was changed by someone else. Reload before saving.")
    fields = data.model_dump(exclude_unset=True, exclude={"expected_version", "change_note"})
    content_changed = False
    for name, value in fields.items():
        if name == "category":
            art.category_id = _category_id(db, value)
        elif name == "article_type":
            if value not in ARTICLE_TYPES:
                raise HTTPException(422, "Unknown article type")
            art.article_type = value
        elif name == "tags":
            art.tags = _clean_tags(value)
        elif name == "cover_image_url":
            art.cover_image_url = safe_url(value)
        elif name in {"title", "subtitle", "summary", "body", "internal_notes"}:
            cleaned = clean_text(value, 60000 if name == "body" else 5000 if name == "internal_notes" else 2000 if name == "summary" else 255,
                                 multiline=name in {"body", "summary", "internal_notes"})
            if name == "title" and not cleaned:
                raise HTTPException(422, "Title is required")
            if name in {"title", "subtitle", "summary", "body"} and getattr(art, name) != cleaned:
                content_changed = True
            setattr(art, name, cleaned)
        elif name in {"cover_caption", "cover_credit"}:
            setattr(art, name, clean_text(value, 300))
        else:
            setattr(art, name, value)
    art.version += 1
    art.platform_modified = True
    if content_changed:
        workflow.snapshot(db, art, ctx.user.id, data.change_note)
    db.execute(m.ArticleAutosave.__table__.delete().where(m.ArticleAutosave.article_id == art.id, m.ArticleAutosave.user_id == ctx.user.id))
    audit.record(db, ctx.user, "article.update", "article", art.id, detail={"fields": sorted(fields)})
    db.commit()
    return _detail(ctx, art)


@router.post("/{article_id}/transition")
def do_transition(article_id: int, data: TransitionIn, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if data.expected_version is not None and data.expected_version != art.version:
        raise HTTPException(409, "This article was changed by someone else. Reload first.")
    workflow.transition(ctx, art, data.to, note=data.note, feedback=data.feedback, scheduled_for=data.scheduled_for, destination=data.destination)
    ctx.db.commit()
    return _detail(ctx, art)


@router.post("/{article_id}/correct")
def correct_article(article_id: int, data: CorrectionIn, ctx: Ctx = Depends(require("article.correct"))):
    """The only way to change a published article: the original text stays in the revision history, a visible
    correction note is attached, and the event is audited."""
    db = ctx.db
    art = _get(ctx, article_id)
    if art.status not in {"published", "corrected"}:
        raise HTTPException(409, "Only published articles can be corrected")
    if data.expected_version != art.version:
        raise HTTPException(409, "This article was changed by someone else. Reload first.")
    if not any([data.title, data.summary is not None, data.body is not None]):
        raise HTTPException(422, "Nothing to correct")
    workflow.snapshot(db, art, ctx.user.id, "before correction")
    if data.title:
        art.title = clean_text(data.title, 255)
    if data.summary is not None:
        art.summary = clean_text(data.summary, 2000, multiline=True)
    if data.body is not None:
        art.body = clean_text(data.body, 60000, multiline=True)
    prev = art.status
    art.status, art.correction_note = "corrected", clean_text(data.note, 4000, multiline=True)
    art.corrected_at = datetime.now(timezone.utc)
    art.version += 1
    art.platform_modified = True
    workflow.snapshot(db, art, ctx.user.id, "correction: " + data.note[:200])
    db.add(m.ArticleEvent(article_id=art.id, actor_id=ctx.user.id, kind="correction", from_status=prev, to_status="corrected", note=art.correction_note))
    audit.record(db, ctx.user, "article.correct", "article", art.id)
    db.commit()
    return _detail(ctx, art)


# ----- autosave / recovery ------------------------------------------------------------------------------------
class AutosaveIn(BaseModel):
    base_version: int
    payload: dict


@router.put("/{article_id}/autosave")
def autosave(article_id: int, data: AutosaveIn, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if not can_edit(ctx, art):
        raise HTTPException(403, "You cannot edit this article")
    allowed = {"title", "subtitle", "summary", "body", "tags", "category", "internal_notes"}
    payload = {k: v for k, v in data.payload.items() if k in allowed}
    if len(str(payload)) > 100000:
        raise HTTPException(413, "Autosave too large")
    row = ctx.db.get(m.ArticleAutosave, (art.id, ctx.user.id))
    if row is None:
        ctx.db.add(m.ArticleAutosave(article_id=art.id, user_id=ctx.user.id, payload=payload, base_version=data.base_version))
    else:
        row.payload, row.base_version = payload, data.base_version
    ctx.db.commit()
    return {"saved": True}


@router.get("/{article_id}/autosave")
def get_autosave(article_id: int, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    row = ctx.db.get(m.ArticleAutosave, (art.id, ctx.user.id))
    if row is None:
        return {"autosave": None}
    return {"autosave": {"payload": row.payload, "base_version": row.base_version, "updated_at": row.updated_at, "stale": row.base_version != art.version}}


# ----- history ------------------------------------------------------------------------------------------------
@router.get("/{article_id}/revisions")
def revisions(article_id: int, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if art.status in PUBLIC_STATUSES and not (ctx.can("article.read") or workflow.is_involved(ctx, art)):
        raise HTTPException(403, "Permission denied")
    rows = list(ctx.db.scalars(select(m.ArticleRevision).where(m.ArticleRevision.article_id == art.id).order_by(m.ArticleRevision.revision_no)))
    names = _names(ctx.db, {r.saved_by for r in rows} - {None})
    return [{"revision_no": r.revision_no, "saved_by": names.get(r.saved_by), "change_note": r.change_note, "created_at": r.created_at, "title": r.title} for r in rows]


@router.get("/{article_id}/revisions/{a}/diff/{b}")
def diff(article_id: int, a: int, b: int, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if art.status in PUBLIC_STATUSES and not (ctx.can("article.read") or workflow.is_involved(ctx, art)):
        raise HTTPException(403, "Permission denied")
    ra, rb = (ctx.db.scalar(select(m.ArticleRevision).where(m.ArticleRevision.article_id == art.id, m.ArticleRevision.revision_no == n)) for n in (a, b))
    if ra is None or rb is None:
        raise NOT_FOUND
    changed = [f for f in ("title", "subtitle", "summary", "body") if getattr(ra, f) != getattr(rb, f)]
    lines = list(difflib.unified_diff(ra.body.splitlines(), rb.body.splitlines(), f"revision {a}", f"revision {b}", lineterm="", n=2))
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    return {"from": a, "to": b, "changed_fields": changed, "title": {"from": ra.title, "to": rb.title}, "body_diff": lines, "lines_added": added, "lines_removed": removed}


@router.get("/{article_id}/events")
def events(article_id: int, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if not (ctx.can("article.read") or workflow.is_involved(ctx, art)):
        raise HTTPException(403, "Permission denied")
    rows = list(ctx.db.scalars(select(m.ArticleEvent).where(m.ArticleEvent.article_id == art.id).order_by(m.ArticleEvent.id)))
    names = _names(ctx.db, {r.actor_id for r in rows} - {None})
    return [{"id": r.id, "kind": r.kind, "actor": names.get(r.actor_id), "from_status": r.from_status, "to_status": r.to_status,
             "note": r.note, "feedback": r.feedback, "created_at": r.created_at} for r in rows]


class CommentIn(BaseModel):
    note: str = Field(min_length=1, max_length=4000)


@router.post("/{article_id}/comments", status_code=201)
def add_review_comment(article_id: int, data: CommentIn, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if not (ctx.can("article.review") or workflow.is_involved(ctx, art)):
        raise HTTPException(403, "Permission denied")
    ctx.db.add(m.ArticleEvent(article_id=art.id, actor_id=ctx.user.id, kind="comment", note=clean_text(data.note, 4000, multiline=True)))
    ctx.db.commit()
    return {"ok": True}


class AssigneesIn(BaseModel):
    user_ids: list[int] = Field(max_length=10)


@router.put("/{article_id}/assignees")
def set_assignees(article_id: int, data: AssigneesIn, ctx: Ctx = Depends(require("article.edit.any"))):
    db = ctx.db
    art = _get(ctx, article_id)
    users = list(db.scalars(select(m.User).where(m.User.id.in_(data.user_ids), m.User.is_active.is_(True))))
    if len(users) != len(set(data.user_ids)):
        raise HTTPException(422, "Unknown or inactive user")
    db.execute(m.ArticleAssignee.__table__.delete().where(m.ArticleAssignee.article_id == art.id))
    for u in users:
        db.add(m.ArticleAssignee(article_id=art.id, user_id=u.id))
    db.add(m.ArticleEvent(article_id=art.id, actor_id=ctx.user.id, kind="assignment", note=", ".join(u.display_name for u in users)))
    audit.record(db, ctx.user, "article.assign", "article", art.id, detail={"user_ids": sorted(u.id for u in users)})
    db.commit()
    return _detail(ctx, art)


@router.put("/{article_id}/investigations/{investigation_id}")
def link_investigation(article_id: int, investigation_id: int, ctx: Ctx = Depends(get_ctx)):
    art = _get(ctx, article_id)
    if not can_edit(ctx, art):
        raise HTTPException(403, "You cannot edit this article")
    inv = ctx.db.get(m.Investigation, investigation_id)
    if inv is None or not investigation_level(ctx, inv):
        raise NOT_FOUND  # same answer whether it does not exist or is not yours to know about
    if ctx.db.get(m.ArticleInvestigation, (art.id, inv.id)) is None:
        ctx.db.add(m.ArticleInvestigation(article_id=art.id, investigation_id=inv.id))
        audit.record(ctx.db, ctx.user, "article.link_investigation", "article", art.id, detail={"investigation_id": inv.id}, investigation_id=inv.id)
        ctx.db.commit()
    return _detail(ctx, art)
