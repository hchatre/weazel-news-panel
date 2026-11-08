from sqlalchemy import select

from app import models as m
from app import permissions as P
from app.seed import seed_defaults


def role_perms(db, key):
    r = db.scalar(select(m.Role).where(m.Role.key == key))
    return {rp.permission_key for rp in db.scalars(select(m.RolePermission).where(m.RolePermission.role_id == r.id))}


def test_new_permission_reaches_existing_default_roles_once(db, monkeypatch):
    monkeypatch.setitem(P.PERMISSIONS, "demo.new", "A permission added by an upgrade")
    roles = [(k, n, r, p | {"demo.new"} if k == "journalist" else p) for k, n, r, p in P.DEFAULT_ROLES]
    monkeypatch.setattr(P, "DEFAULT_ROLES", roles)
    import app.seed as seed
    monkeypatch.setattr(seed, "DEFAULT_ROLES", roles)
    monkeypatch.setattr(seed, "PERMISSIONS", P.PERMISSIONS)
    assert "demo.new" not in role_perms(db, "journalist")
    seed_defaults(db)
    assert "demo.new" in role_perms(db, "journalist") and "demo.new" not in role_perms(db, "intern")
    # an administrator removes it; a later re-seed must respect that
    r = db.scalar(select(m.Role).where(m.Role.key == "journalist"))
    db.query(m.RolePermission).filter_by(role_id=r.id, permission_key="demo.new").delete()
    db.commit()
    seed_defaults(db)
    assert "demo.new" not in role_perms(db, "journalist")
