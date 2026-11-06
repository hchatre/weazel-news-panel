import hashlib
import os
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as m
from app.config import get_settings
from app.services.notify import notify
from tests.test_investigations import API, new_case

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"x" * 50


@pytest.fixture(autouse=True)
def storage(tmp_path):
    s = get_settings()
    old = (s.STORAGE_DIR, s.MAX_UPLOAD_MB)
    s.STORAGE_DIR = str(tmp_path)
    yield tmp_path
    s.STORAGE_DIR, s.MAX_UPLOAD_MB = old


def files_on_disk(root: Path) -> list[Path]:
    return [p for p in (root / "evidence").glob("*")] if (root / "evidence").exists() else []


def upload(client, w, user, inv_id, name="photo.png", data=PNG, **form):
    return client.post(f"{API}/investigations/{inv_id}/evidence", headers=w.h(user),
                       files={"file": (name, data, "application/octet-stream")}, data={"title": "Exhibit A", **form})


def grant(client, w, inv_id, user, access):
    assert client.put(f"{API}/investigations/{inv_id}/participants", headers=w.h(w.jo), json={"user_id": user.id, "access": access}).status_code == 200


# ----------------------------------------------------------------------------------------------- evidence
def test_upload_hashes_stores_under_random_name_and_logs_custody(client, w, storage):
    c = new_case(client, w)
    r = upload(client, w, w.jo, c["id"], name="../../etc/Secret Photo.png")
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["sha256"] == hashlib.sha256(PNG).hexdigest() and ev["size_bytes"] == len(PNG) and ev["kind"] == "image"
    assert "/" not in ev["filename"] and ".." not in ev["filename"]
    (f,) = files_on_disk(storage)
    assert f.name != ev["filename"] and len(f.name) == 32 and f.read_bytes() == PNG  # random name, original bytes
    log = client.get(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/custody", headers=w.h(w.jo)).json()
    assert [x["action"] for x in log] == ["uploaded"] and log[0]["actor"] == "Jo Journalist"


@pytest.mark.parametrize("name,data,why", [
    ("run.exe", b"MZ\x90\x00", "extension"), ("page.html", b"<script>1</script>", "extension"), ("pic.svg", b"<svg onload=1>", "extension"),
    ("fake.png", b"this is plain text", "content mismatch"), ("fake.pdf", PNG, "content mismatch"), ("empty.png", b"", "empty"),
    ("noext", PNG, "extension"), ("bin.txt", b"abc\x00def", "content mismatch"),
])
def test_rejected_uploads_leave_nothing_on_disk(client, w, storage, name, data, why):
    c = new_case(client, w)
    assert upload(client, w, w.jo, c["id"], name=name, data=data).status_code == 422, why
    assert files_on_disk(storage) == []
    assert client.get(f"{API}/investigations/{c['id']}/evidence", headers=w.h(w.jo)).json() == []


def test_size_limit_is_enforced_and_cleaned_up(client, w, storage):
    get_settings().MAX_UPLOAD_MB = 1
    c = new_case(client, w)
    assert upload(client, w, w.jo, c["id"], data=PNG + b"\x00" * (1024 * 1024)).status_code == 413
    assert files_on_disk(storage) == []


def test_upload_needs_permission_and_write_access(client, w):
    c = new_case(client, w)
    assert upload(client, w, w.intern, c["id"]).status_code == 403  # can read a standard case but lacks evidence.upload / write access
    hidden = new_case(client, w, classification="confidential")
    assert upload(client, w, w.intern, hidden["id"]).status_code == 404  # a confidential case does not exist for them
    grant(client, w, c["id"], w.jane, "read")
    assert upload(client, w, w.jane, c["id"]).status_code == 403  # read-only participant
    grant(client, w, c["id"], w.jane, "write")
    assert upload(client, w, w.jane, c["id"]).status_code == 201
    assert upload(client, w, w.jane, c["id"], restricted="true").status_code == 403  # may not self-restrict without the permission
    assert client.post(f"{API}/investigations/{c['id']}/evidence", files={"file": ("a.png", PNG)}, data={"title": "x"}).status_code == 401


def test_download_is_permissioned_attachment_only_and_audited(client, w):
    c = new_case(client, w)
    ev = upload(client, w, w.jo, c["id"], name="note.pdf", data=PDF).json()
    url = f"{API}/investigations/{c['id']}/evidence/{ev['id']}/download"
    assert client.get(url, headers=w.h(w.jo)).status_code == 403  # journalists can list but not download by default
    grant(client, w, c["id"], w.senior, "read")
    r = client.get(url, headers=w.h(w.senior))
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/octet-stream" and r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"
    actions = [x["action"] for x in client.get(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/custody", headers=w.h(w.jo)).json()]
    assert actions == ["uploaded", "downloaded"]
    assert w.db.scalar(select(m.AuditLog).where(m.AuditLog.action == "evidence.download")) is not None


def test_confidential_case_evidence_is_invisible_to_everyone_else_even_admin(client, w):
    c = new_case(client, w, classification="confidential")
    ev = upload(client, w, w.jo, c["id"]).json()
    base = f"{API}/investigations/{c['id']}/evidence"
    for u in (w.admin, w.eic, w.inv_editor, w.senior):
        assert client.get(base, headers=w.h(u)).status_code == 404
        assert client.get(f"{base}/{ev['id']}/download", headers=w.h(u)).status_code == 404
        assert client.post(f"{base}/{ev['id']}/verify", headers=w.h(u)).status_code == 404


def test_restricted_evidence_is_hidden_from_ordinary_participants(client, w):
    c = new_case(client, w)
    grant(client, w, c["id"], w.senior, "write")
    grant(client, w, c["id"], w.inv_editor, "write")
    ev = upload(client, w, w.jo, c["id"]).json()  # standard
    assert client.put(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/restriction", headers=w.h(w.jo), json={"restricted": True}).status_code == 403  # journalist lacks evidence.restrict
    assert client.put(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/restriction", headers=w.h(w.editor), json={"restricted": True}).status_code == 403  # a plain editor does not hold it either
    assert client.put(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/restriction", headers=w.h(w.inv_editor), json={"restricted": True}).status_code == 200
    base = f"{API}/investigations/{c['id']}/evidence"
    assert [e["id"] for e in client.get(base, headers=w.h(w.inv_editor)).json()] == [ev["id"]]
    assert client.get(base, headers=w.h(w.senior)).json() == []  # no evidence.restrict, not uploader, not lead
    assert client.get(f"{base}/{ev['id']}/download", headers=w.h(w.senior)).status_code == 404
    assert [e["id"] for e in client.get(base, headers=w.h(w.jo)).json()] == [ev["id"]]  # the lead still sees it
    log = [x["action"] for x in client.get(f"{base}/{ev['id']}/custody", headers=w.h(w.inv_editor)).json()]
    assert log == ["uploaded", "restricted"]


def test_tampering_is_detected(client, w, storage):
    c = new_case(client, w)
    grant(client, w, c["id"], w.senior, "write")
    ev = upload(client, w, w.jo, c["id"]).json()
    url = f"{API}/investigations/{c['id']}/evidence/{ev['id']}/verify"
    assert client.post(url, headers=w.h(w.senior)).json()["ok"] is True
    (f,) = files_on_disk(storage)
    f.write_bytes(PNG + b"tampered")
    assert client.post(url, headers=w.h(w.senior)).json()["ok"] is False
    actions = [x["action"] for x in client.get(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/custody", headers=w.h(w.jo)).json()]
    assert actions[-2:] == ["integrity_ok", "integrity_failed"]
    f.unlink()
    assert client.get(f"{API}/investigations/{c['id']}/evidence/{ev['id']}/download", headers=w.h(w.senior)).status_code == 410


def test_evidence_is_never_deleted_only_archived_with_a_reason(client, w):
    c = new_case(client, w)
    grant(client, w, c["id"], w.inv_editor, "write")
    ev = upload(client, w, w.jo, c["id"]).json()
    base = f"{API}/investigations/{c['id']}/evidence/{ev['id']}"
    for u in (w.jo, w.admin):
        assert client.delete(base, headers=w.h(u)).status_code in (404, 405)  # there is no delete route at all
    assert len(client.get(f"{API}/investigations/{c['id']}/evidence", headers=w.h(w.jo)).json()) == 1
    assert client.put(f"{base}/archive", headers=w.h(w.inv_editor), json={"archived": True, "note": ""}).status_code == 422
    assert client.put(f"{base}/archive", headers=w.h(w.inv_editor), json={"archived": True, "note": "Duplicate of exhibit B"}).status_code == 200
    assert client.get(f"{API}/investigations/{c['id']}/evidence", headers=w.h(w.jo)).json() == []
    assert len(client.get(f"{API}/investigations/{c['id']}/evidence?include_archived=true", headers=w.h(w.jo)).json()) == 1


def test_evidence_cannot_cross_investigations(client, w):
    a, b = new_case(client, w), new_case(client, w, title="Other")
    ev = upload(client, w, w.jo, a["id"]).json()
    assert client.post(f"{API}/investigations/{b['id']}/evidence/{ev['id']}/verify", headers=w.h(w.jo)).status_code in (403, 404)
    assert client.get(f"{API}/investigations/{b['id']}/evidence/{ev['id']}/custody", headers=w.h(w.jo)).status_code == 404


# ------------------------------------------------------------------------------------------ notifications
def notes(client, w, user):
    return client.get(f"{API}/notifications", headers=w.h(user)).json()


def test_dedupe_is_per_user_and_key(w, db):
    assert notify(db, [w.jo.id], "x", title="t", link="/l", dedupe_key="k1") == 1
    assert notify(db, [w.jo.id], "x", title="t", link="/l", dedupe_key="k1") == 0  # a retry never duplicates
    assert notify(db, [w.jo.id, w.jane.id], "x", title="t", link="/l", dedupe_key="k1") == 1  # only the new recipient
    assert notify(db, [w.jo.id], "x", title="t", link="/l", dedupe_key="k1", exclude=w.jo.id) == 0  # actors are not notified of their own action
    w.stub.is_active = False
    db.commit()
    assert notify(db, [w.stub.id], "x", title="t", link="/l", dedupe_key="k2") == 0  # deactivated users get nothing


def test_article_workflow_notifies_the_right_people_only(client, w):
    art = client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": "Port scandal", "body": "text"}).json()
    assert client.post(f"{API}/articles/{art['id']}/transition", headers=w.h(w.jo), json={"to": "submitted"}).status_code == 200
    assert [n["kind"] for n in notes(client, w, w.editor)] == ["article.awaiting_review"]
    assert notes(client, w, w.jo) == [] and notes(client, w, w.intern) == [] and notes(client, w, w.jane) == []  # author, and people who cannot review, hear nothing
    assert notes(client, w, w.editor)[0]["link"] == f"/articles/{art['id']}"
    client.post(f"{API}/articles/{art['id']}/transition", headers=w.h(w.editor), json={"to": "in_review"})
    v = client.get(f"{API}/articles/{art['id']}", headers=w.h(w.editor)).json()["version"]
    r = client.post(f"{API}/articles/{art['id']}/transition", headers=w.h(w.editor), json={"to": "revision_requested", "note": "Needs a second source", "expected_version": v})
    assert r.status_code == 200
    assert {n["kind"] for n in notes(client, w, w.jo)} == {"article.in_review", "article.revision_requested"}
    assert all(n["kind"] != "article.revision_requested" for n in notes(client, w, w.editor))  # the reviewer is not told about their own decision


def test_task_assignment_and_participant_notices_do_not_leak_titles(client, w):
    c = new_case(client, w, title="TOP SECRET MAYOR CASE", classification="confidential")
    grant(client, w, c["id"], w.jane, "write")
    t = client.post(f"{API}/investigations/{c['id']}/tasks", headers=w.h(w.jo), json={"title": "Call the clerk", "assignee_id": w.jane.id})
    assert t.status_code == 201
    got = notes(client, w, w.jane)
    assert {n["kind"] for n in got} == {"investigation.added", "task.assigned"}
    assert not any("SECRET" in n["title"] for n in got)  # participant notice carries the reference only
    assert next(n for n in got if n["kind"] == "investigation.added")["title"] == c["reference"]
    # reassigning to someone without access is refused, so no notification can reveal the case
    assert client.post(f"{API}/investigations/{c['id']}/tasks", headers=w.h(w.jo), json={"title": "x", "assignee_id": w.intern.id}).status_code == 422
    assert notes(client, w, w.intern) == []


def test_notifications_are_private_and_markable(client, w, db):
    notify(db, [w.jo.id], "x", title="for jo", link="/a", dedupe_key="a")
    notify(db, [w.jane.id], "x", title="for jane", link="/b", dedupe_key="b")
    db.commit()
    jo_note = notes(client, w, w.jo)[0]
    assert [n["title"] for n in notes(client, w, w.jo)] == ["for jo"]
    assert client.get(f"{API}/notifications/unread-count", headers=w.h(w.jo)).json() == {"count": 1}
    assert client.post(f"{API}/notifications/{jo_note['id']}/read", headers=w.h(w.jane)).status_code == 404  # someone else's
    assert client.post(f"{API}/notifications/{jo_note['id']}/read", headers=w.h(w.jo)).status_code == 200
    assert client.get(f"{API}/notifications/unread-count", headers=w.h(w.jo)).json() == {"count": 0}
    assert client.get(f"{API}/notifications/unread-count", headers=w.h(w.jane)).json() == {"count": 1}
    assert client.post(f"{API}/notifications/read-all", headers=w.h(w.jane)).status_code == 200
    assert client.get(f"{API}/notifications/unread-count", headers=w.h(w.jane)).json() == {"count": 0}
    assert client.get(f"{API}/notifications").status_code == 401
