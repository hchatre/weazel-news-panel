import json

from sqlalchemy import select

from app import models as m

API = "/api/v1"
CASE = {"title": "Dockyard corruption", "summary": "Kickbacks at the port", "inv_type": "corruption", "priority": "high"}


def new_case(client, w, user=None, **over):
    r = client.post(f"{API}/investigations", headers=w.h(user or w.jo), json={**CASE, **over})
    assert r.status_code == 201, r.text
    return r.json()


def entry(client, w, user, inv_id, **over):
    return client.post(f"{API}/investigations/{inv_id}/entries", headers=w.h(user), json={"content": "A claim", **over})


# ---------------------------------------------------------------------------------------------- lifecycle
def test_create_assign_update_archive(client, w):
    c = new_case(client, w)
    assert c["reference"].startswith("WZ-") and c["my_access"] == "lead"
    d = client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.jo)).json()
    assert [p["display_name"] for p in d["participants"]] == ["Jo Journalist"]
    assert client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.jane.id, "access": "write"}).status_code == 200
    up = client.patch(f"{API}/investigations/{c['id']}", headers=w.h(w.jane), json={"expected_version": d["version"], "status": "active", "findings": "Port officials met suppliers"})
    assert up.status_code == 200 and up.json()["status"] == "active"
    d2 = client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.jane)).json()
    assert d2["findings"].startswith("Port") and d2["version"] == d["version"] + 1
    assert client.patch(f"{API}/investigations/{c['id']}", headers=w.h(w.jane), json={"expected_version": d["version"], "title": "stale"}).status_code == 409
    assert client.post(f"{API}/investigations/{c['id']}/archive", headers=w.h(w.jane)).status_code == 403  # journalists cannot archive
    arch = client.post(f"{API}/investigations/{c['id']}/archive", headers=w.h(w.editor))
    assert arch.status_code == 200 and arch.json()["is_archived"] and arch.json()["status"] == "archived"
    assert client.get(f"{API}/investigations", headers=w.h(w.jo)).json()["total"] == 0
    assert client.get(f"{API}/investigations?archived=true", headers=w.h(w.jo)).json()["total"] == 1


def test_configurable_status_and_type_are_validated(client, w):
    assert client.post(f"{API}/investigations", headers=w.h(w.jo), json={**CASE, "inv_type": "made_up"}).status_code == 422
    c = new_case(client, w)
    v = c["version"]
    assert client.patch(f"{API}/investigations/{c['id']}", headers=w.h(w.jo), json={"expected_version": v, "status": "made_up"}).status_code == 422
    closed = client.patch(f"{API}/investigations/{c['id']}", headers=w.h(w.jo), json={"expected_version": v, "status": "concluded"}).json()
    assert closed["closed_at"] is not None  # a terminal status records the closure date


def test_intern_cannot_create_but_can_contribute_only_low_trust(client, w):
    assert client.post(f"{API}/investigations", headers=w.h(w.intern), json=CASE).status_code == 403
    c = new_case(client, w)
    assert entry(client, w, w.intern, c["id"], verification="rumour").status_code == 201
    assert entry(client, w, w.intern, c["id"], verification="unverified_claim").status_code == 201
    for bad in ("confirmed", "denial", "disputed"):
        assert entry(client, w, w.intern, c["id"], verification=bad).status_code == 403, bad
    assert entry(client, w, w.intern, c["id"], verification="bogus").status_code == 422


# ---------------------------------------------------------------------------------------------- timeline integrity
def test_timeline_entries_carry_provenance_and_cannot_be_edited_or_deleted(client, w):
    c = new_case(client, w)
    e = entry(client, w, w.jo, c["id"], verification="confirmed", event_date="2026-01-02T10:00:00+00:00", source_ref="SRC-A1", entry_type="event").json()
    assert e["author"] == "Jo Journalist" and e["verified_by"] == "Jo Journalist" and e["event_date"].startswith("2026-01-02")
    for method in ("patch", "put", "delete"):
        assert getattr(client, method)(f"{API}/investigations/{c['id']}/entries/{e['id']}", headers=w.h(w.jo)).status_code in (404, 405)
    corr = entry(client, w, w.jo, c["id"], content="Date was the 3rd", entry_type="correction", correction_of_id=e["id"]).json()
    assert corr["correction_of_id"] == e["id"]
    other = new_case(client, w)
    assert entry(client, w, w.jo, other["id"], correction_of_id=e["id"]).status_code == 422  # cannot "correct" another case's entry


def test_verification_is_human_only_audited_and_needs_a_reason(client, w, db):
    c = new_case(client, w)
    e = entry(client, w, w.jo, c["id"], verification="rumour").json()
    url = f"{API}/investigations/{c['id']}/entries/{e['id']}/verification"
    assert client.put(url, headers=w.h(w.intern), json={"verification": "confirmed", "note": "I think so"}).status_code == 403
    assert client.put(url, headers=w.h(w.jo), json={"verification": "confirmed", "note": ""}).status_code == 422
    ok = client.put(url, headers=w.h(w.jo), json={"verification": "confirmed", "note": "Two independent witnesses"})
    assert ok.status_code == 200 and ok.json()["verification"] == "confirmed" and ok.json()["verified_by"] == "Jo Journalist"
    row = db.scalars(select(m.AuditLog).where(m.AuditLog.action == "investigation.verification")).one()
    assert row.detail == {"from": "rumour", "to": "confirmed"} and row.investigation_id == c["id"]


# ---------------------------------------------------------------------------------------------- confidentiality
def test_confidential_case_is_invisible_to_everyone_but_participants_even_admin(client, w):
    c = new_case(client, w, classification="confidential", title="Mole inside the newsroom")
    entry(client, w, w.jo, c["id"], content="unique-needle-entry")
    for u in (w.jane, w.editor, w.inv_editor, w.eic, w.admin, w.intern, w.senior):
        h = w.h(u)
        assert client.get(f"{API}/investigations/{c['id']}", headers=h).status_code == 404, u.display_name
        assert client.get(f"{API}/investigations/{c['id']}/entries", headers=h).status_code == 404
        assert client.get(f"{API}/investigations/{c['id']}/sources", headers=h).status_code in (403, 404)
        assert client.get(f"{API}/investigations/{c['id']}/tasks", headers=h).status_code == 404
        assert client.post(f"{API}/investigations/{c['id']}/entries", headers=h, json={"content": "x"}).status_code == 404
        assert client.patch(f"{API}/investigations/{c['id']}", headers=h, json={"expected_version": 1, "title": "x"}).status_code == 404
        listing = client.get(f"{API}/investigations", headers=h).json()
        assert listing["total"] == 0 and listing["items"] == []
        assert client.get(f"{API}/investigations?q=Mole", headers=h).json()["total"] == 0
        res = client.get(f"{API}/search?q=Mole", headers=h).json()
        assert res["investigations"] == []
        assert client.get(f"{API}/search?q=unique-needle-entry", headers=h).json()["entries"] == []
        dash = client.get(f"{API}/dashboard", headers=h).json()
        assert dash["active_investigations_total"] == 0 and dash["active_investigations"] == []
        assert "Mole" not in json.dumps(dash)
    assert client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.jo)).status_code == 200
    assert client.get(f"{API}/search?q=unique-needle-entry", headers=w.h(w.jo)).json()["entries"][0]["investigation_id"] == c["id"]


def test_same_404_for_missing_and_hidden(client, w):
    c = new_case(client, w, classification="confidential")
    hidden = client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.editor))
    missing = client.get(f"{API}/investigations/99999", headers=w.h(w.editor))
    assert hidden.status_code == missing.status_code == 404 and hidden.json() == missing.json()


def test_restricted_case_visible_to_privileged_roles_read_only(client, w):
    c = new_case(client, w, classification="restricted")
    for u in (w.jane, w.senior, w.intern, w.editor):
        assert client.get(f"{API}/investigations/{c['id']}", headers=w.h(u)).status_code == 404, u.display_name
    for u in (w.inv_editor, w.eic):
        assert client.get(f"{API}/investigations/{c['id']}", headers=w.h(u)).status_code == 200
        assert client.get(f"{API}/investigations", headers=w.h(u)).json()["total"] == 1
    d = client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.eic)).json()
    assert d["my_access"] == "read" and d["internal_notes"] is None and d["can_edit"] is False
    # reading a restricted case without being a participant never allows editing, even with investigation.edit
    assert client.patch(f"{API}/investigations/{c['id']}", headers=w.h(w.eic), json={"expected_version": d["version"], "title": "x"}).status_code == 403


def test_classification_changes_need_lead_or_manage_access_and_are_audited(client, w, db):
    c = new_case(client, w)
    assert client.put(f"{API}/investigations/{c['id']}/classification", headers=w.h(w.jane), json={"classification": "restricted"}).status_code == 403
    assert client.put(f"{API}/investigations/{c['id']}/classification", headers=w.h(w.jo), json={"classification": "confidential"}).status_code == 200
    assert client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.jane)).status_code == 404  # downgrade of visibility takes effect immediately
    row = db.scalars(select(m.AuditLog).where(m.AuditLog.action == "investigation.classification")).one()
    assert row.detail == {"from": "standard", "to": "confidential"}
    assert client.put(f"{API}/investigations/{c['id']}/classification", headers=w.h(w.jo), json={"classification": "bogus"}).status_code == 422


def test_participants_grant_access_and_last_lead_is_protected(client, w):
    c = new_case(client, w, classification="confidential")
    assert client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.editor), json={"user_id": w.editor.id, "access": "lead"}).status_code == 404  # cannot grant yourself access
    assert client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.jane.id, "access": "read"}).status_code == 200
    assert client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.jane)).status_code == 200
    assert client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jane), json={"user_id": w.jane.id, "access": "lead"}).status_code == 403  # a reader cannot promote themselves
    assert client.delete(f"{API}/investigations/{c['id']}/participants/{w.jo.id}", headers=w.h(w.jo)).status_code == 409  # last lead
    assert client.delete(f"{API}/investigations/{c['id']}/participants/{w.jane.id}", headers=w.h(w.jo)).status_code == 200
    assert client.get(f"{API}/investigations/{c['id']}", headers=w.h(w.jane)).status_code == 404  # access ends at once
    assert client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.stub.id, "access": "read"}).status_code == 200


def test_reader_participant_cannot_write(client, w):
    c = new_case(client, w, classification="confidential")
    client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.jane.id, "access": "read"})
    # jane has investigation.contribute by role, but a read-only participant is still read-only on the record fields
    assert client.patch(f"{API}/investigations/{c['id']}", headers=w.h(w.jane), json={"expected_version": 1, "title": "x"}).status_code == 403
    assert client.post(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.jane), json={"code": "S1"}).status_code == 403


def test_restricted_entries_hidden_from_non_leads(client, w):
    c = new_case(client, w)
    client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.jane.id, "access": "write"})
    entry(client, w, w.jo, c["id"], content="public-facing note")
    entry(client, w, w.jo, c["id"], content="needle-restricted", restricted=True)
    assert len(client.get(f"{API}/investigations/{c['id']}/entries", headers=w.h(w.jo)).json()) == 2
    seen = client.get(f"{API}/investigations/{c['id']}/entries", headers=w.h(w.jane)).json()
    assert [e["content"] for e in seen] == ["public-facing note"]
    assert client.get(f"{API}/search?q=needle-restricted", headers=w.h(w.jane)).json()["entries"] == []
    assert entry(client, w, w.jane, c["id"], restricted=True).status_code == 403  # only a lead can restrict


# ---------------------------------------------------------------------------------------------- sources
def test_source_identity_is_separate_permissioned_and_audited(client, w, db):
    c = new_case(client, w, classification="restricted")
    client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.jane.id, "access": "write"})
    s = client.post(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.jo), json={"code": "SRC-A1", "description": "Port clerk", "reliability": "medium"}).json()
    assert "identity" not in json.dumps(s) and "has_identity" not in s
    sid = f"{API}/investigations/sources/{s['id']}/identity"
    assert client.put(sid, headers=w.h(w.jo), json={"identity": "John Real Name"}).status_code == 403  # journalist: source.manage but not read_identity
    # the investigative editor can read the restricted case but is not on it: reading never grants writing
    assert client.put(sid, headers=w.h(w.inv_editor), json={"identity": "John Real Name"}).status_code == 403
    client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.inv_editor.id, "access": "write"})
    assert client.put(sid, headers=w.h(w.inv_editor), json={"identity": "John Real Name"}).status_code == 200
    for u in (w.jo, w.jane, w.editor, w.intern, w.senior):
        assert client.get(sid, headers=w.h(u)).status_code == 403, u.display_name
    listed = client.get(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.jo)).text
    assert "John Real Name" not in listed and "has_identity" not in listed
    assert client.get(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.inv_editor)).json()[0]["has_identity"] is True
    got = client.get(sid, headers=w.h(w.inv_editor))
    assert got.status_code == 200 and got.json()["identity"] == "John Real Name"
    reads = db.scalars(select(m.AuditLog).where(m.AuditLog.action == "source.identity_read")).all()
    assert len(reads) == 1 and reads[0].actor_id == w.inv_editor.id and reads[0].entity_id == str(s["id"])
    everything = json.dumps([r.detail for r in db.scalars(select(m.AuditLog))])
    assert "John Real Name" not in everything  # the identity is never written to the audit log
    assert "John Real Name" not in client.get(f"{API}/search?q=Port", headers=w.h(w.inv_editor)).text
    assert "John Real Name" not in client.get(f"{API}/search?q=John", headers=w.h(w.inv_editor)).text  # identities are not searchable


def test_identity_of_a_confidential_case_needs_participation_not_just_permission(client, w):
    c = new_case(client, w, classification="confidential")
    s = client.post(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.jo), json={"code": "SRC-B"}).json()
    sid = f"{API}/investigations/sources/{s['id']}/identity"
    assert client.get(sid, headers=w.h(w.inv_editor)).status_code == 404  # has the permission, not in the case
    assert client.get(sid, headers=w.h(w.admin)).status_code == 404
    assert client.patch(f"{API}/investigations/sources/{s['id']}", headers=w.h(w.inv_editor), json={"reliability": "high"}).status_code == 404


def test_source_validation(client, w):
    c = new_case(client, w)
    h = w.h(w.jo)
    assert client.post(f"{API}/investigations/{c['id']}/sources", headers=h, json={"code": "<script>"}).status_code == 422
    assert client.post(f"{API}/investigations/{c['id']}/sources", headers=h, json={"code": "S1", "reliability": "godlike"}).status_code == 422
    assert client.post(f"{API}/investigations/{c['id']}/sources", headers=h, json={"code": "S1"}).status_code == 201
    assert client.post(f"{API}/investigations/{c['id']}/sources", headers=h, json={"code": "S1"}).status_code == 409
    assert client.post(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.intern), json={"code": "S2"}).status_code == 403


# ---------------------------------------------------------------------------------------------- tasks / no side channels
def test_tasks_leads_and_assignee_must_have_access(client, w):
    c = new_case(client, w, classification="confidential")
    base = f"{API}/investigations/{c['id']}/tasks"
    bad = client.post(base, headers=w.h(w.jo), json={"title": "Call the clerk", "assignee_id": w.jane.id})
    assert bad.status_code == 422  # assigning would leak the case to Jane's task list
    client.put(f"{API}/investigations/{c['id']}/participants", headers=w.h(w.jo), json={"user_id": w.jane.id, "access": "write"})
    t = client.post(base, headers=w.h(w.jo), json={"title": "Call the clerk", "kind": "lead", "assignee_id": w.jane.id, "due_date": "2030-01-01"})
    assert t.status_code == 201
    dash = client.get(f"{API}/dashboard", headers=w.h(w.jane)).json()
    assert [x["title"] for x in dash["my_tasks"]] == ["Call the clerk"]
    assert client.patch(f"{base}/{t.json()['id']}", headers=w.h(w.jane), json={"status": "done"}).status_code == 200
    client.delete(f"{API}/investigations/{c['id']}/participants/{w.jane.id}", headers=w.h(w.jo))
    assert client.get(f"{API}/dashboard", headers=w.h(w.jane)).json()["my_tasks"] == []  # removed from the case: task no longer shown
    assert client.patch(f"{base}/{t.json()['id']}", headers=w.h(w.jane), json={"status": "open"}).status_code == 404


def test_staff_workload_does_not_reveal_hidden_investigations(client, w):
    new_case(client, w, classification="confidential")
    new_case(client, w)
    for_editor = {r["display_name"]: r for r in client.get(f"{API}/staff", headers=w.h(w.editor)).json()}
    assert for_editor["Jo Journalist"]["active_investigations"] == 1  # the confidential one is not counted for the editor
    for_jo = {r["display_name"]: r for r in client.get(f"{API}/staff", headers=w.h(w.inv_editor)).json()}
    assert for_jo["Jo Journalist"]["active_investigations"] == 1
    assert all("email" not in r for r in for_editor.values())


def test_audit_log_honours_investigation_visibility(client, w):
    c = new_case(client, w, classification="confidential", title="Hidden")
    open_case = new_case(client, w, title="Visible")
    for_eic = client.get(f"{API}/admin/audit?page_size=100", headers=w.h(w.eic)).json()
    ids = {r["entity_id"] for r in for_eic["items"] if r["action"] == "investigation.create"}
    assert str(open_case["id"]) in ids and str(c["id"]) not in ids
    assert for_eic["total"] == len(for_eic["items"])
    csv = client.get(f"{API}/admin/audit/export", headers=w.h(w.admin))
    assert csv.status_code == 200 and f"investigation,{c['id']}" not in csv.text
    assert client.get(f"{API}/admin/audit/export", headers=w.h(w.eic)).status_code == 403  # audit.read without audit.export
    own = client.get(f"{API}/admin/audit?page_size=100", headers=w.h(w.jo))
    assert own.status_code == 403


def test_search_across_types_respects_permissions(client, w):
    c = new_case(client, w, title="Searchable dock story")
    client.post(f"{API}/investigations/{c['id']}/sources", headers=w.h(w.jo), json={"code": "DOCK-1", "description": "dock worker"})
    client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": "Dock article", "body": "text", "category": "crime"})
    res = client.get(f"{API}/search?q=dock", headers=w.h(w.jo)).json()
    assert res["investigations"] and res["articles"] and res["sources"]
    low = client.get(f"{API}/search?q=dock", headers=w.h(w.intern)).json()
    assert low["articles"] == [] and low["investigations"]  # standard case readable by interns, draft article not
    assert client.get(f"{API}/search?q=d", headers=w.h(w.jo)).status_code == 422
    assert client.get(f"{API}/search?q=%25%25", headers=w.h(w.jo)).json()["investigations"] == []  # % is literal, not a wildcard
