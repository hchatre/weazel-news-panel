from sqlalchemy import select

from app import models as m

API = "/api/v1"
NEW_USER = {"display_name": "New Hire", "email": "new.hire@weazel.test", "password": "a long enough password", "role": "intern"}


def test_only_settings_managers_see_roles_and_all_default_roles_exist(client, w):
    assert client.get(f"{API}/admin/roles", headers=w.h(w.eic)).status_code == 403  # EiC has no settings.manage by default
    roles = client.get(f"{API}/admin/roles", headers=w.h(w.admin)).json()
    assert {r["key"] for r in roles} == {"intern", "journalist", "senior_journalist", "editor", "investigative_editor", "editor_in_chief", "system_admin"}
    admin_role = next(r for r in roles if r["key"] == "system_admin")
    assert len(admin_role["permissions"]) == len(client.get(f"{API}/admin/permissions", headers=w.h(w.admin)).json())


def test_role_edit_cannot_escalate(client, w, db):
    body = {"name": "Evil", "rank": 10, "description": "", "permissions": ["article.create"]}
    # an editor-in-chief who is given settings.manage still cannot grant what they do not hold, nor touch equal/higher ranks
    db.add(m.UserPermission(user_id=w.eic.id, permission_key="settings.manage", effect="grant", reason="test"))
    db.commit()
    h = w.h(w.eic)
    assert client.put(f"{API}/admin/roles/helper", headers=h, json=body).status_code == 200
    assert client.put(f"{API}/admin/roles/helper", headers=h, json={**body, "permissions": ["article.create", "settings.manage", "source.read_identity", "audit.export"]}).status_code == 403  # audit.export is not held by the EiC
    assert client.put(f"{API}/admin/roles/helper", headers=h, json={**body, "rank": 50}).status_code == 403  # equal rank
    assert client.put(f"{API}/admin/roles/editor_in_chief", headers=h, json={**body, "rank": 10}).status_code == 403  # their own role
    assert client.put(f"{API}/admin/roles/system_admin", headers=h, json={**body, "rank": 10}).status_code == 403
    assert client.put(f"{API}/admin/roles/helper", headers=h, json={**body, "permissions": ["nope.nope"]}).status_code == 422
    assert client.put(f"{API}/admin/roles/Bad Key!", headers=h, json=body).status_code in (404, 422)


def test_admin_can_customise_roles_and_it_takes_effect_and_is_audited(client, w, db):
    roles = {r["key"]: r for r in client.get(f"{API}/admin/roles", headers=w.h(w.admin)).json()}
    editor = roles["editor"]
    perms = [p for p in editor["permissions"] if p != "article.publish"]
    r = client.put(f"{API}/admin/roles/editor", headers=w.h(w.admin), json={"name": "Desk Editor", "rank": 40, "description": "", "permissions": perms})
    assert r.status_code == 200
    assert "article.publish" not in client.get(f"{API}/auth/me", headers=w.h(w.editor)).json()["permissions"]
    row = db.scalars(select(m.AuditLog).where(m.AuditLog.action == "admin.role_update")).one()
    assert row.entity_id == "editor" and "article.publish" not in row.detail["permissions"]


def test_workflow_configuration_is_audited_and_changes_behaviour(client, w, db):
    def mk():
        a = client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": "T", "body": "B"}).json()
        client.post(f"{API}/articles/{a['id']}/transition", headers=w.h(w.jo), json={"to": "submitted"})
        return a["id"]
    a1 = mk()
    assert client.post(f"{API}/articles/{a1}/transition", headers=w.h(w.jo), json={"to": "in_review"}).status_code == 403
    r = client.put(f"{API}/admin/workflow/submitted/in_review", headers=w.h(w.admin), json={"permission": "article.submit", "independent": False, "requires_note": False})
    assert r.status_code == 200
    assert client.post(f"{API}/articles/{a1}/transition", headers=w.h(w.jo), json={"to": "in_review"}).status_code == 200  # reconfigured: author may now start review
    assert db.scalars(select(m.AuditLog).where(m.AuditLog.action == "admin.workflow_update")).one().detail["before"]["independent"] is True
    assert client.put(f"{API}/admin/workflow/submitted/in_review", headers=w.h(w.admin), json={"permission": "bogus", "independent": True, "requires_note": False}).status_code == 422
    assert client.put(f"{API}/admin/workflow/draft/published", headers=w.h(w.admin), json={"permission": "article.publish", "independent": False, "requires_note": False}).status_code == 404


def test_staff_lifecycle_with_rank_rules(client, w, db):
    h = w.h(w.eic)
    created = client.post(f"{API}/admin/users", headers=h, json=NEW_USER)
    assert created.status_code == 201 and created.json()["role"] == "intern"
    assert client.post(f"{API}/admin/users", headers=h, json=NEW_USER).status_code == 409
    assert client.post(f"{API}/admin/users", headers=h, json={**NEW_USER, "email": "x@y.test", "role": "system_admin"}).status_code == 403
    assert client.post(f"{API}/admin/users", headers=h, json={**NEW_USER, "email": "x@y.test", "role": "editor_in_chief"}).status_code == 403  # equal rank
    assert client.post(f"{API}/admin/users", headers=w.h(w.editor), json={**NEW_USER, "email": "z@y.test"}).status_code == 403
    assert client.post(f"{API}/admin/users", headers=h, json={**NEW_USER, "email": "weak@y.test", "password": "short"}).status_code == 422
    uid = created.json()["id"]
    assert client.put(f"{API}/admin/users/{uid}/role", headers=h, json={"role": "journalist"}).status_code == 200  # promotion
    assert client.put(f"{API}/admin/users/{uid}/role", headers=h, json={"role": "editor"}).status_code == 200
    assert client.put(f"{API}/admin/users/{uid}/role", headers=h, json={"role": "editor_in_chief"}).status_code == 403  # cannot promote above own rank
    assert client.put(f"{API}/admin/users/{uid}/role", headers=h, json={"role": "bogus"}).status_code == 422
    dismissed = client.post(f"{API}/admin/users/{uid}/deactivate", headers=h)
    assert dismissed.status_code == 200 and dismissed.json()["is_active"] is False and dismissed.json()["employment_status"] == "former"
    assert client.post(f"{API}/auth/login", json={"email": NEW_USER["email"], "password": NEW_USER["password"]}).status_code == 401
    actions = [r.action for r in db.scalars(select(m.AuditLog).order_by(m.AuditLog.id))]
    assert actions.count("staff.role_change") == 2 and "staff.dismiss" in actions and "staff.recruit" in actions


def test_no_self_promotion_no_acting_on_equals_or_superiors(client, w):
    h = w.h(w.eic)
    assert client.put(f"{API}/admin/users/{w.eic.id}/role", headers=h, json={"role": "journalist"}).status_code == 403  # self
    assert client.post(f"{API}/admin/users/{w.eic.id}/deactivate", headers=h).status_code == 403  # self
    assert client.put(f"{API}/admin/users/{w.eic2.id}/role", headers=h, json={"role": "intern"}).status_code == 403  # equal rank
    assert client.post(f"{API}/admin/users/{w.eic2.id}/deactivate", headers=h).status_code == 403
    assert client.post(f"{API}/admin/users/{w.admin.id}/deactivate", headers=h).status_code == 403  # superior
    assert client.put(f"{API}/admin/users/{w.jo.id}/role", headers=w.h(w.jo), json={"role": "editor"}).status_code == 403  # a journalist
    assert client.put(f"{API}/admin/users/{w.jo.id}/role", headers=w.h(w.editor), json={"role": "editor"}).status_code == 403  # editors cannot promote
    assert client.put(f"{API}/admin/users/99999/role", headers=h, json={"role": "intern"}).status_code == 404


def test_role_change_takes_effect_immediately_by_invalidating_tokens(client, w):
    old = w.h(w.jo)
    assert client.post(f"{API}/articles", headers=old, json={"title": "ok"}).status_code == 201
    assert client.put(f"{API}/admin/users/{w.jo.id}/role", headers=w.h(w.eic), json={"role": "intern"}).status_code == 200
    assert client.get(f"{API}/auth/me", headers=old).status_code == 401  # the token minted before the demotion is dead
    new = w.h(w.jo)
    assert "investigation.create" not in client.get(f"{API}/auth/me", headers=new).json()["permissions"]


def test_dismissal_blocks_existing_sessions(client, w):
    old = w.h(w.jane)
    client.post(f"{API}/admin/users/{w.jane.id}/deactivate", headers=w.h(w.eic))
    assert client.get(f"{API}/auth/me", headers=old).status_code == 401


def test_job_mapping_cannot_map_to_higher_role(client, w):
    assert client.get(f"{API}/admin/job-mappings", headers=w.h(w.admin)).json()[3] == {"job_name": "reporter", "grade_level": 3, "role": "editor_in_chief"}
    ok = client.put(f"{API}/admin/job-mappings", headers=w.h(w.admin), json={"job_name": "reporter", "grade_level": 4, "role": "editor_in_chief"})
    assert ok.status_code == 200
    assert client.put(f"{API}/admin/job-mappings", headers=w.h(w.admin), json={"job_name": "reporter", "grade_level": 5, "role": "system_admin"}).status_code == 403  # admin never comes from a job
    assert client.put(f"{API}/admin/job-mappings", headers=w.h(w.admin), json={"job_name": "reporter", "grade_level": 5, "role": "nope"}).status_code == 422
    assert client.put(f"{API}/admin/job-mappings", headers=w.h(w.eic), json={"job_name": "reporter", "grade_level": 5, "role": "intern"}).status_code == 403


def test_individual_overrides_are_guarded(client, w, db):
    h = w.h(w.admin)
    r = client.put(f"{API}/admin/users/{w.jo.id}/permissions", headers=h, json={"permission": "article.publish", "effect": "grant", "reason": "covering for editor"})
    assert r.status_code == 200
    assert "article.publish" in client.get(f"{API}/auth/me", headers=w.h(w.jo)).json()["permissions"]
    assert client.put(f"{API}/admin/users/{w.jo.id}/permissions", headers=h, json={"permission": "article.publish", "effect": "grant", "reason": ""}).status_code == 422  # a reason is mandatory
    assert client.put(f"{API}/admin/users/{w.jo.id}/permissions", headers=h, json={"permission": "nope", "effect": "grant", "reason": "abc"}).status_code == 422
    assert client.put(f"{API}/admin/users/{w.jo.id}/permissions", headers=w.h(w.eic), json={"permission": "article.create", "effect": "deny", "reason": "abc"}).status_code == 403  # no settings.manage
    assert db.scalars(select(m.AuditLog).where(m.AuditLog.action == "admin.user_permission")).one().detail == {"permission": "article.publish", "effect": "grant"}


def test_audit_is_append_only_through_the_api(client, w):
    for method in ("put", "patch", "delete", "post"):
        assert getattr(client, method)(f"{API}/admin/audit/1", headers=w.h(w.admin)).status_code in (404, 405)
    assert client.delete(f"{API}/admin/audit", headers=w.h(w.admin)).status_code == 405


def test_failed_logins_are_audited_without_passwords(client, w, db):
    client.post(f"{API}/auth/login", json={"email": "jo.journalist@weazel.test", "password": "super-secret-guess"})
    rows = db.scalars(select(m.AuditLog).where(m.AuditLog.action == "auth.login_failed")).all()
    assert len(rows) == 1 and "super-secret-guess" not in str(rows[0].detail)


def test_dashboard_is_permission_aware_and_complete(client, w):
    a = client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": "Waiting", "body": "b", "category": "crime"}).json()
    client.post(f"{API}/articles/{a['id']}/transition", headers=w.h(w.jo), json={"to": "submitted"})
    ed = client.get(f"{API}/dashboard", headers=w.h(w.editor)).json()
    assert ed["awaiting_review_total"] == 1 and ed["awaiting_review"][0]["title"] == "Waiting"
    assert "workload" in ed and "services" not in ed  # staff.view yes, settings.manage no
    jo = client.get(f"{API}/dashboard", headers=w.h(w.jo)).json()
    assert "awaiting_review" not in jo and "workload" not in jo and jo["my_drafts"] == 0
    adm = client.get(f"{API}/dashboard", headers=w.h(w.admin)).json()
    assert adm["services"] == {"database": "ok"}
    for key in ("revision_requests", "scheduled", "breaking_recent", "active_investigations", "my_tasks", "upcoming_deadlines", "publication_by_week", "recent_activity"):
        assert key in ed, key


def test_security_headers_and_health(client):
    r = client.get("/health")
    assert r.json() == {"status": "ok", "database": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"


def test_assignable_roles_lists_only_roles_below_the_caller_and_needs_a_staff_permission(client, w):
    eic = client.get(f"{API}/staff/assignable-roles", headers=w.h(w.eic))   # a chief can fill role pickers without settings.manage
    assert eic.status_code == 200
    keys = {r["key"] for r in eic.json()}
    assert "editor" in keys and "intern" in keys and "editor_in_chief" not in keys and "system_admin" not in keys
    assert client.get(f"{API}/staff/assignable-roles", headers=w.h(w.jo)).status_code == 403   # a journalist has no staff permission
