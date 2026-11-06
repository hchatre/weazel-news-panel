"""Idempotent defaults. Safe to run on every deploy: existing rows are never overwritten, so an administrator's
changes to roles, permissions or workflow survive. New permission keys added by an upgrade are inserted and
granted only to the roles that define them by default if the role has not been customised (never removed)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.permissions import (
    DEFAULT_CATEGORIES, DEFAULT_JOB_MAPPINGS, DEFAULT_LOOKUPS, DEFAULT_ROLES, DEFAULT_TRANSITIONS, PERMISSIONS,
)


def seed_defaults(db: Session) -> None:
    existing_perms = set(db.scalars(select(m.Permission.key)))
    new_perms = {k for k in PERMISSIONS if k not in existing_perms}
    for key in new_perms:
        db.add(m.Permission(key=key, description=PERMISSIONS[key]))
    db.flush()

    roles = {r.key: r for r in db.scalars(select(m.Role))}
    for key, name, rank, perms in DEFAULT_ROLES:
        if key in roles:
            continue
        role = m.Role(key=key, name=name, rank=rank, is_system=True)
        role.permissions = [m.RolePermission(permission_key=p) for p in sorted(perms)]
        db.add(role)
        roles[key] = role
    db.flush()

    # A permission introduced by an upgrade is granted to the default roles that define it, exactly once: at the moment the
    # permission first appears. After that an administrator's choice (removing it from a role) is never overwritten by a re-seed.
    if new_perms:
        for key, _name, _rank, perms in DEFAULT_ROLES:
            role = roles.get(key)
            if role is None:
                continue
            have_rp = {rp.permission_key for rp in role.permissions}
            for p in sorted((perms & new_perms) - have_rp):
                db.add(m.RolePermission(role_id=role.id, permission_key=p))
        db.flush()

    have = {(j.job_name, j.grade_level) for j in db.scalars(select(m.JobGradeMapping))}
    for job, grade, role_key in DEFAULT_JOB_MAPPINGS:
        if (job, grade) not in have:
            db.add(m.JobGradeMapping(job_name=job, grade_level=grade, role_id=roles[role_key].id))

    have_t = {(t.from_status, t.to_status) for t in db.scalars(select(m.WorkflowTransition))}
    for f, t, perm, indep, note in DEFAULT_TRANSITIONS:
        if (f, t) not in have_t:
            db.add(m.WorkflowTransition(from_status=f, to_status=t, permission_key=perm, independent=indep, requires_note=note))

    have_c = set(db.scalars(select(m.Category.key)))
    for key, en, fr in DEFAULT_CATEGORIES:
        if key not in have_c:
            db.add(m.Category(key=key, label_en=en, label_fr=fr))

    have_l = {(l.kind, l.key) for l in db.scalars(select(m.LookupValue))}
    for kind, rows in DEFAULT_LOOKUPS.items():
        for i, (key, en, fr, terminal) in enumerate(rows):
            if (kind, key) not in have_l:
                db.add(m.LookupValue(kind=kind, key=key, label_en=en, label_fr=fr, sort=i, is_terminal=terminal))
    db.commit()


if __name__ == "__main__":
    from app.db import SessionLocal

    with SessionLocal() as s:
        seed_defaults(s)
    print("defaults seeded")
