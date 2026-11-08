from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app import models as m
from app.api.common import NOT_FOUND, clean_text, like_pattern
from app.deps import get_ctx, paginate, require
from app.permissions import LOW_TRUST_STATES, VERIFICATION_STATES
from app.services import audit
from app.services.access import (
    ACCESS_ORDER, Ctx, can_manage_access, entry_visible_filter, investigation_level, participant_access, visible_investigation_filter,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])
PRIORITIES = {"low", "normal", "high", "urgent"}
CLASSIFICATIONS = {"standard", "restricted", "confidential"}
ENTRY_TYPES = {"note", "event", "interview", "document", "correction"}
RELIABILITY = {"unassessed", "low", "medium", "high", "proven"}


def _lookup_ok(db: Session, kind: str, key: str) -> m.LookupValue:
    row = db.scalar(select(m.LookupValue).where(m.LookupValue.kind == kind, m.LookupValue.key == key, m.LookupValue.is_active.is_(True)))
    if row is None:
        raise HTTPException(422, f"Unknown {kind.replace('_', ' ')}")
    return row


def _load(ctx: Ctx, inv_id: int, need: str = "read") -> tuple[m.Investigation, str]:
    """Loads an investigation or answers 404 (never 403) when the user has no access, so existence does not leak."""
    inv = ctx.db.get(m.Investigation, inv_id)
    level = investigation_level(ctx, inv) if inv else None
    if inv is None or level is None or ACCESS_ORDER[level] < ACCESS_ORDER[need]:
        if inv is not None and level is not None:
            raise HTTPException(403, "Permission denied")
        raise NOT_FOUND
    return inv, level


def _row(inv: m.Investigation, level: str | None = None) -> dict:
    return {"id": inv.id, "reference": inv.reference, "title": inv.title, "summary": inv.summary, "inv_type": inv.inv_type, "status": inv.status,
            "priority": inv.priority, "classification": inv.classification, "opened_at": inv.opened_at, "target_date": inv.target_date,
            "closed_at": inv.closed_at, "is_archived": inv.is_archived, "version": inv.version, "my_access": level}


class InvestigationIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=5000)
    inv_type: str = "general"
    priority: str = "normal"
    classification: str = "standard"
    target_date: date | None = None


class InvestigationPatch(BaseModel):
    expected_version: int
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    inv_type: str | None = None
    status: str | None = None
    priority: str | None = None
    target_date: date | None = None
    closure_note: str | None = Field(default=None, max_length=5000)
    findings: str | None = Field(default=None, max_length=20000)
    open_questions: str | None = Field(default=None, max_length=10000)
    conclusions: str | None = Field(default=None, max_length=20000)
    internal_notes: str | None = Field(default=None, max_length=10000)


@router.get("")
def list_investigations(
    q: str | None = Query(default=None, max_length=100), status: str | None = None, inv_type: str | None = None, priority: str | None = None,
    classification: str | None = None, mine: bool = False, archived: bool = False, page: int = 1, page_size: int = 20,
    ctx: Ctx = Depends(get_ctx),
):
    db = ctx.db
    cond = [visible_investigation_filter(ctx), m.Investigation.is_archived.is_(archived)]
    if q:
        pat = like_pattern(q.strip())
        cond.append(or_(m.Investigation.title.ilike(pat, escape="\\"), m.Investigation.summary.ilike(pat, escape="\\"), m.Investigation.reference.ilike(pat, escape="\\")))
    if status:
        cond.append(m.Investigation.status == status)
    if inv_type:
        cond.append(m.Investigation.inv_type == inv_type)
    if priority:
        cond.append(m.Investigation.priority == priority)
    if classification:
        cond.append(m.Investigation.classification == classification)
    if mine:
        cond.append(m.Investigation.id.in_(select(m.InvestigationParticipant.investigation_id).where(m.InvestigationParticipant.user_id == ctx.user.id)))
    offset, limit = paginate(page, page_size)
    total = db.scalar(select(func.count()).select_from(m.Investigation).where(and_(*cond))) or 0  # counts use the same filter as the rows
    rows = list(db.scalars(select(m.Investigation).where(and_(*cond)).order_by(m.Investigation.updated_at.desc(), m.Investigation.id.desc()).offset(offset).limit(limit)))
    return {"items": [_row(i, investigation_level(ctx, i)) for i in rows], "total": total, "page": max(1, page), "page_size": limit}


@router.post("", status_code=201)
def create_investigation(data: InvestigationIn, ctx: Ctx = Depends(require("investigation.create"))):
    db = ctx.db
    _lookup_ok(db, "investigation_type", data.inv_type)
    if data.priority not in PRIORITIES or data.classification not in CLASSIFICATIONS:
        raise HTTPException(422, "Invalid priority or classification")
    year = datetime.now(timezone.utc).year
    seq = (db.scalar(select(func.count()).select_from(m.Investigation).where(m.Investigation.reference.like(f"WZ-{year}-%"))) or 0) + 1
    ref = f"WZ-{year}-{seq:04d}"
    while db.scalar(select(m.Investigation.id).where(m.Investigation.reference == ref)):
        seq += 1
        ref = f"WZ-{year}-{seq:04d}"
    inv = m.Investigation(reference=ref, title=clean_text(data.title, 255), summary=clean_text(data.summary, 5000, multiline=True), inv_type=data.inv_type,
                          priority=data.priority, classification=data.classification, target_date=data.target_date, created_by=ctx.user.id, platform_modified=True)
    db.add(inv)
    db.flush()
    db.add(m.InvestigationParticipant(investigation_id=inv.id, user_id=ctx.user.id, access="lead", added_by=ctx.user.id))
    audit.record(db, ctx.user, "investigation.create", "investigation", inv.id, detail={"classification": inv.classification}, investigation_id=inv.id)
    db.commit()
    return _row(inv, "lead")


@router.get("/{inv_id}")
def get_investigation(inv_id: int, ctx: Ctx = Depends(get_ctx)):
    inv, level = _load(ctx, inv_id)
    db = ctx.db
    parts = list(db.execute(select(m.InvestigationParticipant, m.User).join(m.User, m.User.id == m.InvestigationParticipant.user_id)
                            .where(m.InvestigationParticipant.investigation_id == inv.id)))
    data = _row(inv, level)
    data.update(findings=inv.findings, open_questions=inv.open_questions, conclusions=inv.conclusions, closure_note=inv.closure_note,
                participants=[{"user_id": u.id, "display_name": u.display_name, "access": p.access} for p, u in parts],
                can_edit=ACCESS_ORDER[level] >= 2, can_manage_access=can_manage_access(ctx, inv),
                internal_notes=inv.internal_notes if ACCESS_ORDER[level] >= 2 else None)
    arts = db.scalars(select(m.Article).join(m.ArticleInvestigation, m.ArticleInvestigation.article_id == m.Article.id).where(m.ArticleInvestigation.investigation_id == inv.id))
    data["articles"] = [{"id": a.id, "title": a.title, "status": a.status} for a in arts]
    return data


@router.patch("/{inv_id}")
def update_investigation(inv_id: int, data: InvestigationPatch, ctx: Ctx = Depends(get_ctx)):
    db = ctx.db
    inv, level = _load(ctx, inv_id, "write")  # write/lead participants, or investigation.edit on a standard case
    if data.expected_version != inv.version:
        raise HTTPException(409, "This investigation was changed by someone else. Reload first.")
    fields = data.model_dump(exclude_unset=True, exclude={"expected_version"})
    for name, value in fields.items():
        if name == "status":
            row = _lookup_ok(db, "investigation_status", value)
            if value != inv.status:
                inv.closed_at = datetime.now(timezone.utc) if row.is_terminal else None
                audit.record(db, ctx.user, "investigation.status", "investigation", inv.id, detail={"from": inv.status, "to": value}, investigation_id=inv.id)
            inv.status = value
        elif name == "inv_type":
            _lookup_ok(db, "investigation_type", value)
            inv.inv_type = value
        elif name == "priority":
            if value not in PRIORITIES:
                raise HTTPException(422, "Invalid priority")
            inv.priority = value
        elif name == "title":
            inv.title = clean_text(value, 255) or inv.title
        elif name == "target_date":
            inv.target_date = value
        else:
            setattr(inv, name, clean_text(value, 20000, multiline=True))
    inv.version += 1
    inv.platform_modified = True
    audit.record(db, ctx.user, "investigation.update", "investigation", inv.id, detail={"fields": sorted(fields)}, investigation_id=inv.id)
    db.commit()
    return _row(inv, level)


@router.post("/{inv_id}/archive")
def archive(inv_id: int, ctx: Ctx = Depends(require("investigation.archive"))):
    inv, level = _load(ctx, inv_id, "write")
    row = _lookup_ok(ctx.db, "investigation_status", "archived")
    inv.is_archived, inv.status, inv.closed_at = True, row.key, inv.closed_at or datetime.now(timezone.utc)
    inv.version += 1
    inv.platform_modified = True
    audit.record(ctx.db, ctx.user, "investigation.archive", "investigation", inv.id, investigation_id=inv.id)
    ctx.db.commit()
    return _row(inv, level)


# ----- access --------------------------------------------------------------------------------------------------
class ClassificationIn(BaseModel):
    classification: str


@router.put("/{inv_id}/classification")
def set_classification(inv_id: int, data: ClassificationIn, ctx: Ctx = Depends(get_ctx)):
    inv, level = _load(ctx, inv_id)
    if data.classification not in CLASSIFICATIONS:
        raise HTTPException(422, "Invalid classification")
    if not can_manage_access(ctx, inv):
        raise HTTPException(403, "Permission denied")
    if data.classification != inv.classification:
        audit.record(ctx.db, ctx.user, "investigation.classification", "investigation", inv.id,
                     detail={"from": inv.classification, "to": data.classification}, investigation_id=inv.id)
        inv.classification = data.classification
        inv.version += 1
        inv.platform_modified = True
        ctx.db.commit()
    return _row(inv, investigation_level(ctx, inv))


class ParticipantIn(BaseModel):
    user_id: int
    access: str = "read"


@router.put("/{inv_id}/participants")
def set_participant(inv_id: int, data: ParticipantIn, ctx: Ctx = Depends(get_ctx)):
    db = ctx.db
    inv, _ = _load(ctx, inv_id)
    if not can_manage_access(ctx, inv):
        raise HTTPException(403, "Permission denied")
    if data.access not in ACCESS_ORDER:
        raise HTTPException(422, "Invalid access level")
    target = db.get(m.User, data.user_id)
    if target is None or not target.is_active:
        raise HTTPException(422, "Unknown or inactive user")
    row = db.get(m.InvestigationParticipant, (inv.id, target.id))
    if row is None:
        db.add(m.InvestigationParticipant(investigation_id=inv.id, user_id=target.id, access=data.access, added_by=ctx.user.id))
    else:
        row.access = data.access
    audit.record(db, ctx.user, "investigation.participant", "investigation", inv.id, detail={"user_id": target.id, "access": data.access}, investigation_id=inv.id)
    from app.services.notify import notify
    # reference only, never the title: a confidential case's name is not leaked into a notification list
    notify(db, [target.id], "investigation.added", title=inv.reference, link=f"/investigations/{inv.id}", dedupe_key=f"inv:{inv.id}:added:{target.id}:{data.access}", exclude=ctx.user.id)
    db.commit()
    return {"ok": True}


@router.delete("/{inv_id}/participants/{user_id}")
def remove_participant(inv_id: int, user_id: int, ctx: Ctx = Depends(get_ctx)):
    db = ctx.db
    inv, _ = _load(ctx, inv_id)
    if not can_manage_access(ctx, inv):
        raise HTTPException(403, "Permission denied")
    row = db.get(m.InvestigationParticipant, (inv.id, user_id))
    if row is None:
        raise NOT_FOUND
    if row.access == "lead":
        leads = db.scalar(select(func.count()).select_from(m.InvestigationParticipant).where(
            m.InvestigationParticipant.investigation_id == inv.id, m.InvestigationParticipant.access == "lead")) or 0
        if leads <= 1:
            raise HTTPException(409, "An investigation must keep at least one lead")
    db.delete(row)
    audit.record(db, ctx.user, "investigation.participant_removed", "investigation", inv.id, detail={"user_id": user_id}, investigation_id=inv.id)
    db.commit()
    return {"ok": True}


# ----- timeline ------------------------------------------------------------------------------------------------
class EntryIn(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    entry_type: str = "note"
    event_date: datetime | None = None
    verification: str = "unverified_claim"
    source_ref: str | None = Field(default=None, max_length=200)
    notes: str = Field(default="", max_length=5000)
    restricted: bool = False
    correction_of_id: int | None = None


def _entry(e: m.InvestigationEntry, names: dict[int, str]) -> dict:
    return {"id": e.id, "entry_type": e.entry_type, "event_date": e.event_date, "created_at": e.created_at, "content": e.content,
            "verification": e.verification, "source_ref": e.source_ref, "notes": e.notes, "restricted": e.restricted,
            "correction_of_id": e.correction_of_id, "author": names.get(e.author_id) or e.legacy_author_name,
            "verified_by": names.get(e.verified_by), "verified_at": e.verified_at}


@router.get("/{inv_id}/entries")
def list_entries(inv_id: int, verification: str | None = None, ctx: Ctx = Depends(get_ctx)):
    inv, level = _load(ctx, inv_id)
    cond = [m.InvestigationEntry.investigation_id == inv.id, entry_visible_filter(ctx, level)]
    if verification:
        cond.append(m.InvestigationEntry.verification == verification)
    rows = list(ctx.db.scalars(select(m.InvestigationEntry).where(and_(*cond)).order_by(m.InvestigationEntry.event_date, m.InvestigationEntry.id)))
    names = {u.id: u.display_name for u in ctx.db.scalars(select(m.User).where(m.User.id.in_({x for r in rows for x in (r.author_id, r.verified_by) if x})))} if rows else {}
    return [_entry(r, names) for r in rows]


@router.post("/{inv_id}/entries", status_code=201)
def add_entry(inv_id: int, data: EntryIn, ctx: Ctx = Depends(get_ctx)):
    db = ctx.db
    inv, level = _load(ctx, inv_id)
    part = participant_access(db, ctx.user.id, inv.id)
    if not (ctx.can("investigation.contribute") or (part and ACCESS_ORDER[part] >= 2)):
        raise HTTPException(403, "Permission denied")
    if data.verification not in VERIFICATION_STATES or data.entry_type not in ENTRY_TYPES:
        raise HTTPException(422, "Invalid verification status or entry type")
    if data.verification not in LOW_TRUST_STATES and not ctx.can("investigation.verify"):
        raise HTTPException(403, "You can only record rumours, unverified claims and hypotheses")
    if data.restricted and level != "lead" and not ctx.can("evidence.restrict"):
        raise HTTPException(403, "Only a lead can restrict an entry")
    if data.correction_of_id is not None:
        original = db.get(m.InvestigationEntry, data.correction_of_id)
        if original is None or original.investigation_id != inv.id:
            raise HTTPException(422, "Entry to correct not found in this investigation")
    entry = m.InvestigationEntry(
        investigation_id=inv.id, entry_type=data.entry_type, event_date=data.event_date or datetime.now(timezone.utc),
        content=clean_text(data.content, 10000, multiline=True), verification=data.verification, source_ref=clean_text(data.source_ref, 200) or None,
        notes=clean_text(data.notes, 5000, multiline=True), restricted=data.restricted, correction_of_id=data.correction_of_id, author_id=ctx.user.id,
        platform_modified=True)
    if data.verification not in LOW_TRUST_STATES:
        entry.verified_by, entry.verified_at = ctx.user.id, datetime.now(timezone.utc)
    db.add(entry)
    db.flush()
    audit.record(db, ctx.user, "investigation.entry_add", "investigation_entry", entry.id, detail={"verification": entry.verification}, investigation_id=inv.id)
    inv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _entry(entry, {ctx.user.id: ctx.user.display_name})


class VerificationIn(BaseModel):
    verification: str
    note: str = Field(min_length=3, max_length=2000)


@router.put("/{inv_id}/entries/{entry_id}/verification")
def set_verification(inv_id: int, entry_id: int, data: VerificationIn, ctx: Ctx = Depends(require("investigation.verify"))):
    """The only way a claim's status changes: a named person with `investigation.verify`, with a reason, audited.
    Nothing (including AI output) can call this on a person's behalf."""
    db = ctx.db
    inv, level = _load(ctx, inv_id)
    e = db.get(m.InvestigationEntry, entry_id)
    if e is None or e.investigation_id != inv.id:
        raise NOT_FOUND
    if e.restricted and level != "lead" and not ctx.can("evidence.restrict") and e.author_id != ctx.user.id:
        raise NOT_FOUND
    if data.verification not in VERIFICATION_STATES:
        raise HTTPException(422, "Invalid verification status")
    prev = e.verification
    e.verification, e.verified_by, e.verified_at = data.verification, ctx.user.id, datetime.now(timezone.utc)
    e.notes = (e.notes + ("\n" if e.notes else "") + f"[{prev} -> {data.verification}] " + clean_text(data.note, 2000)).strip()
    e.platform_modified = True
    audit.record(db, ctx.user, "investigation.verification", "investigation_entry", e.id, detail={"from": prev, "to": data.verification}, investigation_id=inv.id)
    db.commit()
    return _entry(e, {ctx.user.id: ctx.user.display_name})


# ----- tasks / leads -------------------------------------------------------------------------------------------
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    kind: str = "task"
    detail: str = Field(default="", max_length=5000)
    assignee_id: int | None = None
    due_date: date | None = None


class TaskPatch(BaseModel):
    status: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    assignee_id: int | None = None
    due_date: date | None = None


@router.get("/{inv_id}/tasks")
def list_tasks(inv_id: int, ctx: Ctx = Depends(get_ctx)):
    inv, _ = _load(ctx, inv_id)
    rows = list(ctx.db.scalars(select(m.InvestigationTask).where(m.InvestigationTask.investigation_id == inv.id).order_by(m.InvestigationTask.status.desc(), m.InvestigationTask.due_date.nullslast(), m.InvestigationTask.id)))
    names = {u.id: u.display_name for u in ctx.db.scalars(select(m.User).where(m.User.id.in_({r.assignee_id for r in rows if r.assignee_id})))} if rows else {}
    return [{"id": t.id, "kind": t.kind, "title": t.title, "detail": t.detail, "assignee_id": t.assignee_id, "assignee": names.get(t.assignee_id),
             "due_date": t.due_date, "status": t.status} for t in rows]


def _check_assignee(ctx: Ctx, inv: m.Investigation, assignee_id: int | None) -> None:
    if assignee_id is None:
        return
    user = ctx.db.get(m.User, assignee_id)
    if user is None or not user.is_active:
        raise HTTPException(422, "Unknown or inactive user")
    # an assignee must be able to see the investigation, otherwise the assignment would leak it through their task list
    from app.services.access import Ctx as C
    if investigation_level(C(ctx.db, user), inv) is None:
        raise HTTPException(422, "That user has no access to this investigation. Add them as a participant first.")


@router.post("/{inv_id}/tasks", status_code=201)
def add_task(inv_id: int, data: TaskIn, ctx: Ctx = Depends(get_ctx)):
    inv, _ = _load(ctx, inv_id)
    if not ctx.can("investigation.contribute"):
        raise HTTPException(403, "Permission denied")
    if data.kind not in {"lead", "task", "follow_up"}:
        raise HTTPException(422, "Invalid kind")
    _check_assignee(ctx, inv, data.assignee_id)
    t = m.InvestigationTask(investigation_id=inv.id, kind=data.kind, title=clean_text(data.title, 255), detail=clean_text(data.detail, 5000, multiline=True),
                            assignee_id=data.assignee_id, due_date=data.due_date, created_by=ctx.user.id)
    ctx.db.add(t)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "investigation.task_add", "investigation_task", t.id, investigation_id=inv.id)
    if t.assignee_id:  # _check_assignee already proved the assignee can see this investigation
        from app.services.notify import notify
        notify(ctx.db, [t.assignee_id], "task.assigned", title=t.title, link=f"/investigations/{inv.id}", dedupe_key=f"task:{t.id}:assigned:{t.assignee_id}", exclude=ctx.user.id)
    ctx.db.commit()
    return {"id": t.id}


@router.patch("/{inv_id}/tasks/{task_id}")
def update_task(inv_id: int, task_id: int, data: TaskPatch, ctx: Ctx = Depends(get_ctx)):
    inv, _ = _load(ctx, inv_id)
    t = ctx.db.get(m.InvestigationTask, task_id)
    if t is None or t.investigation_id != inv.id:
        raise NOT_FOUND
    if not (ctx.can("investigation.contribute") or t.assignee_id == ctx.user.id):
        raise HTTPException(403, "Permission denied")
    fields = data.model_dump(exclude_unset=True)
    if "status" in fields:
        if fields["status"] not in {"open", "done", "dropped"}:
            raise HTTPException(422, "Invalid status")
        t.status = fields["status"]
        t.completed_at = datetime.now(timezone.utc) if t.status != "open" else None
    if "assignee_id" in fields:
        _check_assignee(ctx, inv, fields["assignee_id"])
        t.assignee_id = fields["assignee_id"]
        if t.assignee_id:
            from app.services.notify import notify
            notify(ctx.db, [t.assignee_id], "task.assigned", title=t.title, link=f"/investigations/{inv.id}", dedupe_key=f"task:{t.id}:assigned:{t.assignee_id}", exclude=ctx.user.id)
    if "title" in fields:
        t.title = clean_text(fields["title"], 255)
    if "due_date" in fields:
        t.due_date = fields["due_date"]
    ctx.db.commit()
    return {"ok": True}


# ----- sources -------------------------------------------------------------------------------------------------
class SourceIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._\- ]+$")
    description: str = Field(default="", max_length=3000)
    reliability: str = "unassessed"
    assessment_notes: str = Field(default="", max_length=5000)


class SourcePatch(BaseModel):
    description: str | None = Field(default=None, max_length=3000)
    reliability: str | None = None
    assessment_notes: str | None = Field(default=None, max_length=5000)


class IdentityIn(BaseModel):
    identity: str = Field(min_length=1, max_length=2000)


def _source_row(s: m.Source, ctx: Ctx) -> dict:
    row = {"id": s.id, "investigation_id": s.investigation_id, "code": s.code, "description": s.description, "reliability": s.reliability,
           "assessment_notes": s.assessment_notes, "created_at": s.created_at}
    if ctx.can("source.read_identity"):  # even the existence of an identity record is not shown to everyone
        row["has_identity"] = ctx.db.get(m.SourceIdentity, s.id) is not None
    return row


@router.get("/{inv_id}/sources")
def list_sources(inv_id: int, ctx: Ctx = Depends(require("source.read"))):
    inv, _ = _load(ctx, inv_id)
    return [_source_row(s, ctx) for s in ctx.db.scalars(select(m.Source).where(m.Source.investigation_id == inv.id).order_by(m.Source.code))]


@router.post("/{inv_id}/sources", status_code=201)
def add_source(inv_id: int, data: SourceIn, ctx: Ctx = Depends(require("source.manage"))):
    inv, _ = _load(ctx, inv_id, "write")
    if data.reliability not in RELIABILITY:
        raise HTTPException(422, "Invalid reliability")
    if ctx.db.scalar(select(m.Source.id).where(m.Source.investigation_id == inv.id, m.Source.code == data.code.strip())):
        raise HTTPException(409, "A source with this code already exists in this investigation")
    s = m.Source(investigation_id=inv.id, code=data.code.strip(), description=clean_text(data.description, 3000, multiline=True), reliability=data.reliability,
                 assessment_notes=clean_text(data.assessment_notes, 5000, multiline=True), created_by=ctx.user.id)
    ctx.db.add(s)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "source.create", "source", s.id, investigation_id=inv.id)
    ctx.db.commit()
    return _source_row(s, ctx)


def _source(ctx: Ctx, source_id: int, need: str = "read") -> tuple[m.Source, m.Investigation]:
    s = ctx.db.get(m.Source, source_id)
    if s is None:
        raise NOT_FOUND
    inv, _ = _load(ctx, s.investigation_id, need)
    return s, inv


@router.patch("/sources/{source_id}")
def update_source(source_id: int, data: SourcePatch, ctx: Ctx = Depends(require("source.manage"))):
    s, inv = _source(ctx, source_id, "write")
    fields = data.model_dump(exclude_unset=True)
    if "reliability" in fields:
        if fields["reliability"] not in RELIABILITY:
            raise HTTPException(422, "Invalid reliability")
        s.reliability = fields["reliability"]
    if "description" in fields:
        s.description = clean_text(fields["description"], 3000, multiline=True)
    if "assessment_notes" in fields:
        s.assessment_notes = clean_text(fields["assessment_notes"], 5000, multiline=True)
    audit.record(ctx.db, ctx.user, "source.update", "source", s.id, detail={"fields": sorted(fields)}, investigation_id=inv.id)
    ctx.db.commit()
    return _source_row(s, ctx)


@router.get("/sources/{source_id}/identity")
def read_identity(source_id: int, ctx: Ctx = Depends(require("source.read_identity"))):
    s, inv = _source(ctx, source_id)
    ident = ctx.db.get(m.SourceIdentity, s.id)
    # the read is recorded BEFORE the value is returned and the record commits even if the response fails
    audit.record(ctx.db, ctx.user, "source.identity_read", "source", s.id, investigation_id=inv.id)
    ctx.db.commit()
    if ident is None:
        raise NOT_FOUND
    return {"source_id": s.id, "code": s.code, "identity": ident.identity}


@router.put("/sources/{source_id}/identity")
def write_identity(source_id: int, data: IdentityIn, ctx: Ctx = Depends(require("source.read_identity", "source.manage"))):
    s, inv = _source(ctx, source_id, "write")
    ident = ctx.db.get(m.SourceIdentity, s.id)
    if ident is None:
        ctx.db.add(m.SourceIdentity(source_id=s.id, identity=clean_text(data.identity, 2000, multiline=True), updated_by=ctx.user.id))
    else:
        ident.identity, ident.updated_by = clean_text(data.identity, 2000, multiline=True), ctx.user.id
    audit.record(ctx.db, ctx.user, "source.identity_write", "source", s.id, investigation_id=inv.id)  # the value itself is never logged
    ctx.db.commit()
    return {"ok": True}
