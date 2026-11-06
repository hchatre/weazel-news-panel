import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from app import models as m
from app.api.common import NOT_FOUND, clean_text
from app.deps import get_ctx, paginate, require
from app.security import hash_password
from app.services import audit
from app.services.access import Ctx, visible_investigation_filter

router = APIRouter(tags=["admin"])


# ----- roles & permissions -------------------------------------------------------------------------------------
@router.get("/admin/permissions")
def list_permissions(ctx: Ctx = Depends(require("settings.manage"))):
    return [{"key": p.key, "description": p.description} for p in ctx.db.scalars(select(m.Permission).order_by(m.Permission.key))]


@router.get("/admin/roles")
def list_roles(ctx: Ctx = Depends(require("settings.manage"))):
    return [{"key": r.key, "name": r.name, "rank": r.rank, "is_system": r.is_system, "description": r.description,
             "permissions": sorted(p.permission_key for p in r.permissions)} for r in ctx.db.scalars(select(m.Role).order_by(m.Role.rank))]


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=0, le=99)
    description: str = Field(default="", max_length=500)
    permissions: list[str]


@router.put("/admin/roles/{key}")
def upsert_role(key: str, data: RoleIn, ctx: Ctx = Depends(require("settings.manage"))):
    """Anti-escalation: you can only grant permissions you hold yourself, and never create or edit a role of
    equal or higher rank than your own (the system administrator rank cannot be assigned through the API)."""
    db = ctx.db
    if not key.replace("_", "").isalnum() or len(key) > 50:
        raise HTTPException(422, "Invalid role key")
    known = set(db.scalars(select(m.Permission.key)))
    unknown = set(data.permissions) - known
    if unknown:
        raise HTTPException(422, f"Unknown permissions: {sorted(unknown)}")
    if set(data.permissions) - ctx.perms:
        raise HTTPException(403, "You cannot grant permissions you do not hold yourself")
    if data.rank >= ctx.rank:
        raise HTTPException(403, "You cannot create or edit a role of equal or higher rank than your own")
    role = db.scalar(select(m.Role).where(m.Role.key == key))
    if role is None:
        role = m.Role(key=key, name=data.name, rank=data.rank, description=data.description)
        db.add(role)
        db.flush()
    else:
        if role.rank >= ctx.rank:
            raise HTTPException(403, "You cannot edit a role of equal or higher rank than your own")
        role.name, role.rank, role.description = data.name, data.rank, data.description
        db.execute(m.RolePermission.__table__.delete().where(m.RolePermission.role_id == role.id))
    for p in sorted(set(data.permissions)):
        db.add(m.RolePermission(role_id=role.id, permission_key=p))
    audit.record(db, ctx.user, "admin.role_update", "role", key, detail={"permissions": sorted(set(data.permissions)), "rank": data.rank})
    db.commit()
    return {"ok": True}


@router.get("/admin/job-mappings")
def list_mappings(ctx: Ctx = Depends(require("settings.manage"))):
    rows = ctx.db.execute(select(m.JobGradeMapping, m.Role).join(m.Role, m.Role.id == m.JobGradeMapping.role_id).order_by(m.JobGradeMapping.job_name, m.JobGradeMapping.grade_level))
    return [{"job_name": j.job_name, "grade_level": j.grade_level, "role": r.key} for j, r in rows]


class MappingIn(BaseModel):
    job_name: str = Field(min_length=1, max_length=50)
    grade_level: int = Field(ge=0, le=100)
    role: str


@router.put("/admin/job-mappings")
def set_mapping(data: MappingIn, ctx: Ctx = Depends(require("settings.manage"))):
    db = ctx.db
    role = db.scalar(select(m.Role).where(m.Role.key == data.role))
    if role is None:
        raise HTTPException(422, "Unknown role")
    if role.rank >= ctx.rank:
        raise HTTPException(403, "You cannot map a job grade to a role of equal or higher rank than your own")
    row = db.scalar(select(m.JobGradeMapping).where(m.JobGradeMapping.job_name == data.job_name, m.JobGradeMapping.grade_level == data.grade_level))
    if row is None:
        db.add(m.JobGradeMapping(job_name=data.job_name, grade_level=data.grade_level, role_id=role.id))
    else:
        row.role_id = role.id
    audit.record(db, ctx.user, "admin.job_mapping", "job_mapping", f"{data.job_name}:{data.grade_level}", detail={"role": data.role})
    db.commit()
    return {"ok": True}


@router.get("/admin/workflow")
def list_workflow(ctx: Ctx = Depends(require("settings.manage"))):
    return [{"from": t.from_status, "to": t.to_status, "permission": t.permission_key, "independent": t.independent, "requires_note": t.requires_note, "is_active": t.is_active}
            for t in ctx.db.scalars(select(m.WorkflowTransition).order_by(m.WorkflowTransition.id))]


class TransitionCfg(BaseModel):
    permission: str
    independent: bool
    requires_note: bool
    is_active: bool = True


@router.put("/admin/workflow/{from_status}/{to_status}")
def update_transition(from_status: str, to_status: str, data: TransitionCfg, ctx: Ctx = Depends(require("settings.manage"))):
    db = ctx.db
    t = db.scalar(select(m.WorkflowTransition).where(m.WorkflowTransition.from_status == from_status, m.WorkflowTransition.to_status == to_status))
    if t is None:
        raise NOT_FOUND
    if not db.get(m.Permission, data.permission):
        raise HTTPException(422, "Unknown permission")
    before = {"permission": t.permission_key, "independent": t.independent, "requires_note": t.requires_note, "is_active": t.is_active}
    t.permission_key, t.independent, t.requires_note, t.is_active = data.permission, data.independent, data.requires_note, data.is_active
    audit.record(db, ctx.user, "admin.workflow_update", "workflow", f"{from_status}>{to_status}", detail={"before": before, "after": data.model_dump()})
    db.commit()
    return {"ok": True}


# ----- users / staff -------------------------------------------------------------------------------------------
def _user_row(u: m.User) -> dict:
    return {"id": u.id, "display_name": u.display_name, "email": u.email, "citizen_id": u.citizen_id, "role": u.role.key if u.role else None,
            "role_rank": u.role.rank if u.role else None, "is_active": u.is_active, "employment_job": u.employment_job,
            "employment_grade": u.employment_grade, "employment_status": u.employment_status, "source": u.source, "last_login_at": u.last_login_at}


@router.get("/staff")
def staff(ctx: Ctx = Depends(require("staff.view"))):
    db = ctx.db
    vis = visible_investigation_filter(ctx)
    out = []
    for u in db.scalars(select(m.User).where(m.User.role_id.is_not(None)).order_by(m.User.display_name)):
        row = _user_row(u)
        row.pop("email", None)
        row["open_articles"] = db.scalar(select(func.count()).select_from(m.Article).where(
            m.Article.author_id == u.id, m.Article.status.in_(["idea", "draft", "submitted", "in_review", "revision_requested"]))) or 0
        # only investigations the viewer may see are counted, so workload cannot reveal hidden cases
        row["active_investigations"] = db.scalar(select(func.count()).select_from(m.InvestigationParticipant).join(
            m.Investigation, m.Investigation.id == m.InvestigationParticipant.investigation_id).where(
            m.InvestigationParticipant.user_id == u.id, m.Investigation.is_archived.is_(False), vis)) or 0
        out.append(row)
    return out


class UserIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    role: str
    citizen_id: str | None = Field(default=None, max_length=50)


def _guard_target(ctx: Ctx, target: m.User, new_role: m.Role | None = None) -> None:
    if target.id == ctx.user.id:
        raise HTTPException(403, "You cannot change your own role or status")
    if target.role and target.role.rank >= ctx.rank:
        raise HTTPException(403, "You cannot act on someone of equal or higher rank")
    if new_role is not None and new_role.rank >= ctx.rank:
        raise HTTPException(403, "You cannot assign a role of equal or higher rank than your own")


@router.post("/admin/users", status_code=201)
def create_user(data: UserIn, ctx: Ctx = Depends(require("staff.recruit"))):
    db = ctx.db
    role = db.scalar(select(m.Role).where(m.Role.key == data.role))
    if role is None:
        raise HTTPException(422, "Unknown role")
    if role.rank >= ctx.rank:
        raise HTTPException(403, "You cannot assign a role of equal or higher rank than your own")
    email = data.email.strip().lower()
    if db.scalar(select(m.User.id).where(func.lower(m.User.email) == email)):
        raise HTTPException(409, "Email already in use")
    u = m.User(display_name=clean_text(data.display_name, 120), email=email, password_hash=hash_password(data.password), role_id=role.id,
               citizen_id=data.citizen_id or None, source="local")
    db.add(u)
    db.flush()
    audit.record(db, ctx.user, "staff.recruit", "user", u.id, detail={"role": role.key})
    db.commit()
    return _user_row(u)


class RoleChange(BaseModel):
    role: str


@router.put("/admin/users/{user_id}/role")
def change_role(user_id: int, data: RoleChange, ctx: Ctx = Depends(require("staff.promote"))):
    db = ctx.db
    target, role = db.get(m.User, user_id), db.scalar(select(m.Role).where(m.Role.key == data.role))
    if target is None:
        raise NOT_FOUND
    if role is None:
        raise HTTPException(422, "Unknown role")
    _guard_target(ctx, target, role)
    prev = target.role.key if target.role else None
    target.role_id = role.id
    if target.source != "local":
        target.role_locked = True  # hand-assigned: the next employment sync must not undo it
    target.token_version += 1  # their old tokens stop working so the new permissions apply immediately
    audit.record(db, ctx.user, "staff.role_change", "user", target.id, detail={"from": prev, "to": role.key})
    db.commit()
    return _user_row(target)


@router.post("/admin/users/{user_id}/deactivate")
def deactivate(user_id: int, ctx: Ctx = Depends(require("staff.dismiss"))):
    db = ctx.db
    target = db.get(m.User, user_id)
    if target is None:
        raise NOT_FOUND
    _guard_target(ctx, target)
    target.is_active, target.employment_status = False, "former"
    target.token_version += 1
    audit.record(db, ctx.user, "staff.dismiss", "user", target.id)
    db.commit()
    return _user_row(target)


class OverrideIn(BaseModel):
    permission: str
    effect: str
    reason: str = Field(min_length=3, max_length=500)


@router.put("/admin/users/{user_id}/permissions")
def set_override(user_id: int, data: OverrideIn, ctx: Ctx = Depends(require("settings.manage"))):
    db = ctx.db
    target = db.get(m.User, user_id)
    if target is None:
        raise NOT_FOUND
    _guard_target(ctx, target)
    if data.effect not in {"grant", "deny"} or not db.get(m.Permission, data.permission):
        raise HTTPException(422, "Invalid permission or effect")
    if data.effect == "grant" and data.permission not in ctx.perms:
        raise HTTPException(403, "You cannot grant a permission you do not hold yourself")
    row = db.get(m.UserPermission, (target.id, data.permission))
    if row is None:
        db.add(m.UserPermission(user_id=target.id, permission_key=data.permission, effect=data.effect, reason=clean_text(data.reason, 500), created_by=ctx.user.id))
    else:
        row.effect, row.reason, row.created_by = data.effect, clean_text(data.reason, 500), ctx.user.id
    target.token_version += 1
    audit.record(db, ctx.user, "admin.user_permission", "user", target.id, detail={"permission": data.permission, "effect": data.effect})
    db.commit()
    return {"ok": True}


# ----- audit ---------------------------------------------------------------------------------------------------
def _audit_query(ctx: Ctx, action: str | None, entity_type: str | None, actor_id: int | None):
    # audit rows tied to an investigation honour the same record-level rule as the investigation itself
    cond = [or_(m.AuditLog.investigation_id.is_(None), m.AuditLog.investigation_id.in_(select(m.Investigation.id).where(visible_investigation_filter(ctx))))]
    if action:
        cond.append(m.AuditLog.action.like(action.replace("%", "") + "%"))
    if entity_type:
        cond.append(m.AuditLog.entity_type == entity_type)
    if actor_id:
        cond.append(m.AuditLog.actor_id == actor_id)
    return and_(*cond)


@router.get("/admin/audit")
def read_audit(action: str | None = None, entity_type: str | None = None, actor_id: int | None = None, page: int = 1, page_size: int = 50,
               ctx: Ctx = Depends(require("audit.read"))):
    db = ctx.db
    cond = _audit_query(ctx, action, entity_type, actor_id)
    offset, limit = paginate(page, page_size)
    total = db.scalar(select(func.count()).select_from(m.AuditLog).where(cond)) or 0
    rows = list(db.scalars(select(m.AuditLog).where(cond).order_by(m.AuditLog.id.desc()).offset(offset).limit(limit)))
    names = {u.id: u.display_name for u in db.scalars(select(m.User).where(m.User.id.in_({r.actor_id for r in rows if r.actor_id})))} if rows else {}
    return {"items": [{"id": r.id, "at": r.at, "actor": names.get(r.actor_id), "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id, "detail": r.detail} for r in rows],
            "total": total, "page": max(1, page), "page_size": limit}


@router.get("/admin/audit/export")
def export_audit(action: str | None = None, ctx: Ctx = Depends(require("audit.read", "audit.export"))):
    db = ctx.db
    cond = _audit_query(ctx, action, None, None)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "at", "actor_id", "action", "entity_type", "entity_id"])
    for r in db.scalars(select(m.AuditLog).where(cond).order_by(m.AuditLog.id).limit(50000)):
        # spreadsheet formula injection guard on every free-text field
        w.writerow([r.id, r.at.isoformat(), r.actor_id, *[("'" + v if str(v or "")[:1] in "=+-@" else v) for v in (r.action, r.entity_type, r.entity_id)]])
    audit.record(db, ctx.user, "audit.export", "audit", None)
    db.commit()
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit.csv"})
