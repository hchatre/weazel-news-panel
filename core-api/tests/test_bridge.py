import json
import time
import uuid

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update
from datetime import datetime, timedelta, timezone

from app import models as m
from app.config import Settings, get_settings
from app.services.bridge import sign
from tests.conftest import auth, make_user

API = "/api/v1"
SECRET = "b" * 40


@pytest.fixture(autouse=True)
def bridge_config():
    s = get_settings()
    old = (s.BRIDGE_SECRET, s.TICKET_TTL_SECONDS)
    s.BRIDGE_SECRET = SECRET
    yield
    s.BRIDGE_SECRET, s.TICKET_TTL_SECONDS = old


def post(client, path, body, *, secret=SECRET, ts=None, nonce=None, sign_path=None, raw=None, headers=None):
    raw = raw if raw is not None else json.dumps(body).encode()
    ts = str(int(time.time()) if ts is None else ts)
    nonce = nonce or uuid.uuid4().hex
    sig = sign(secret, "POST", sign_path or f"{API}{path}", ts, nonce, raw)
    h = {"X-Weazel-Timestamp": ts, "X-Weazel-Nonce": nonce, "X-Weazel-Signature": sig, "Content-Type": "application/json", **(headers or {})}
    return client.post(f"{API}{path}", content=raw, headers=h)


def sync(client, *players, **kw):
    return post(client, "/bridge/sync-staff", {"players": list(players)}, **kw)


def pl(cid, job="reporter", grade=1, name="Test Person"):
    return {"citizenid": cid, "name": name, "job": job, "grade": grade}


def user(db, cid):
    db.expire_all()
    return db.scalar(select(m.User).where(m.User.citizen_id == cid))


# ------------------------------------------------------------------------------------------- authentication
def test_bridge_is_off_without_a_secret(client):
    get_settings().BRIDGE_SECRET = ""
    assert sync(client, pl("ABC123")).status_code == 503
    assert client.post(f"{API}/auth/fivem-exchange", json={"ticket": "x" * 30}).status_code == 404


def test_every_kind_of_bad_request_is_rejected_identically(client, db):
    good = [pl("ABC123")]
    now = int(time.time())
    bad = {
        "wrong secret": sync(client, *good, secret="c" * 40),
        "stale timestamp": sync(client, *good, ts=now - 3600),
        "future timestamp": sync(client, *good, ts=now + 3600),
        "signed for another path": sync(client, *good, sign_path=f"{API}/bridge/session"),
        "short nonce": sync(client, *good, nonce="abc"),
        "non-hex nonce": sync(client, *good, nonce="!" * 20),
        "no headers": client.post(f"{API}/bridge/sync-staff", json={"players": good}),
        "user bearer token instead": client.post(f"{API}/bridge/sync-staff", json={"players": good}, headers=auth(make_user(db, "Admin", "system_admin"))),
    }
    for name, r in bad.items():
        assert r.status_code == 401, name
    assert len({r.text for r in bad.values()}) == 1  # nothing to learn from the failure mode
    assert user(db, "ABC123") is None  # and nothing was written


def test_tampered_body_is_rejected(client, db):
    raw = json.dumps({"players": [pl("ABC123")]}).encode()
    ts, nonce = str(int(time.time())), uuid.uuid4().hex
    sig = sign(SECRET, "POST", f"{API}/bridge/sync-staff", ts, nonce, raw)
    tampered = raw.replace(b"grade\": 1", b"grade\": 3")
    r = client.post(f"{API}/bridge/sync-staff", content=tampered, headers={"X-Weazel-Timestamp": ts, "X-Weazel-Nonce": nonce, "X-Weazel-Signature": sig})
    assert tampered != raw and r.status_code == 401


def test_replay_is_refused_and_bad_signatures_do_not_consume_nonces(client, db):
    nonce = uuid.uuid4().hex
    assert sync(client, pl("ABC123"), nonce=nonce).status_code == 200
    assert sync(client, pl("ABC123"), nonce=nonce).status_code == 401  # exact same signed request again
    before = db.scalar(select(func.count()).select_from(m.BridgeNonce))
    for _ in range(3):
        sync(client, pl("ABC123"), secret="c" * 40)
    assert db.scalar(select(func.count()).select_from(m.BridgeNonce)) == before  # outsiders cannot fill the table


def test_old_nonces_are_purged(client, db):
    db.add(m.BridgeNonce(nonce="old" * 8, seen_at=datetime.now(timezone.utc) - timedelta(hours=2)))
    db.commit()
    assert sync(client, pl("ABC123")).status_code == 200
    assert db.get(m.BridgeNonce, "old" * 8) is None


# ------------------------------------------------------------------------------------------------ tickets
def test_ticket_flow_single_use_expiring_hashed(client, db):
    assert sync(client, pl("ABC123", grade=1)).json()["created"] == 1
    t = post(client, "/bridge/session", {"citizenid": "ABC123"})
    assert t.status_code == 200
    body = t.json()
    assert body["url"].endswith(f"/fivem-login?ticket={body['ticket']}")
    stored = db.scalar(select(m.BridgeTicket))
    assert body["ticket"] not in stored.token_hash and len(stored.token_hash) == 64  # only a hash is kept
    ex = client.post(f"{API}/auth/fivem-exchange", json={"ticket": body["ticket"]})
    assert ex.status_code == 200
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {ex.json()['access_token']}"}).json()
    assert me["role"]["key"] == "journalist"
    assert client.post(f"{API}/auth/fivem-exchange", json={"ticket": body["ticket"]}).status_code == 401  # single use
    assert db.scalar(select(m.AuditLog).where(m.AuditLog.action == "auth.login_fivem")) is not None


def test_expired_unknown_and_inactive_tickets_fail(client, db):
    sync(client, pl("ABC123"))
    t1 = post(client, "/bridge/session", {"citizenid": "ABC123"}).json()["ticket"]
    db.execute(update(m.BridgeTicket).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()
    assert client.post(f"{API}/auth/fivem-exchange", json={"ticket": t1}).status_code == 401
    assert client.post(f"{API}/auth/fivem-exchange", json={"ticket": "z" * 43}).status_code == 401
    t2 = post(client, "/bridge/session", {"citizenid": "ABC123"}).json()["ticket"]
    u = user(db, "ABC123")
    u.is_active = False
    db.commit()
    assert client.post(f"{API}/auth/fivem-exchange", json={"ticket": t2}).status_code == 401  # dismissed between issue and use


def test_session_needs_an_existing_active_account_and_is_rate_limited(client, db):
    assert post(client, "/bridge/session", {"citizenid": "NOBODY1"}).status_code == 404
    assert db.scalar(select(func.count()).select_from(m.BridgeTicket)) == 0
    assert post(client, "/bridge/session", {"citizenid": "bad id!"}).status_code == 422
    sync(client, pl("ABC123"))
    codes = [post(client, "/bridge/session", {"citizenid": "ABC123"}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    stub = make_user(db, "No Role", None)
    stub.citizen_id = "NOROLE1"
    db.commit()
    assert post(client, "/bridge/session", {"citizenid": "NOROLE1"}).status_code == 404  # an account without a role cannot sign in


# ------------------------------------------------------------------------------------------------ staff sync
def test_sync_maps_employment_to_roles_and_ignores_non_staff(client, db):
    r = sync(client, pl("AAA111", grade=0), pl("BBB222", grade=2), pl("CCC333", job="police", grade=4), pl("DDD444", grade=3)).json()
    assert r["created"] == 3 and r["skipped_unmapped"] == 1
    assert [user(db, c).role.key for c in ("AAA111", "BBB222", "DDD444")] == ["intern", "editor", "editor_in_chief"]
    assert user(db, "CCC333") is None  # no account is created for non-staff
    assert user(db, "AAA111").source == "fivem" and user(db, "AAA111").password_hash is None  # no password: ticket login only


def test_promotion_and_dismissal_take_effect_immediately(client, db):
    sync(client, pl("AAA111", grade=1))
    u = user(db, "AAA111")
    old = auth(u)
    assert client.get(f"{API}/auth/me", headers=old).status_code == 200
    r = sync(client, pl("AAA111", grade=2)).json()
    assert r["role_changed"] == 1 and user(db, "AAA111").role.key == "editor"
    assert client.get(f"{API}/auth/me", headers=old).status_code == 401  # old token no longer valid; permissions refresh at next login
    cur = auth(user(db, "AAA111"))
    assert sync(client, pl("AAA111", job="unemployed", grade=0)).json()["deactivated"] == 1
    assert client.get(f"{API}/auth/me", headers=cur).status_code == 401
    assert user(db, "AAA111").employment_status == "former"
    assert post(client, "/bridge/session", {"citizenid": "AAA111"}).status_code == 404
    assert sync(client, pl("AAA111", grade=1)).json()["reactivated"] == 1  # hired again
    assert user(db, "AAA111").is_active and user(db, "AAA111").role.key == "journalist"


def test_absent_players_manual_deactivation_and_local_accounts_are_left_alone(client, db):
    sync(client, pl("AAA111"), pl("BBB222"))
    sync(client, pl("AAA111"))  # BBB222 is simply not in this batch
    assert user(db, "BBB222").is_active
    b = user(db, "BBB222")
    b.is_active = False  # an administrator suspended them by hand (employment still "active")
    admin = make_user(db, "Root", "system_admin")
    admin.citizen_id = "ROOT999"
    db.commit()
    r = sync(client, pl("BBB222", grade=2), pl("ROOT999", job="unemployed", grade=0)).json()
    assert r["reactivated"] == 0 and not user(db, "BBB222").is_active
    assert r["skipped_local"] == 1 and user(db, "ROOT999").is_active and user(db, "ROOT999").role.key == "system_admin"


def test_hand_assigned_roles_survive_syncs(client, db):
    sync(client, pl("AAA111", grade=1))
    admin = make_user(db, "Root", "system_admin")
    r = client.put(f"{API}/admin/users/{user(db, 'AAA111').id}/role", headers=auth(admin), json={"role": "senior_journalist"})
    assert r.status_code == 200 and user(db, "AAA111").role_locked
    assert sync(client, pl("AAA111", grade=1)).json()["role_changed"] == 0
    assert user(db, "AAA111").role.key == "senior_journalist"  # QBCore does not overwrite a deliberate decision
    assert user(db, "AAA111").employment_grade == 1  # but the employment mirror stays current


def test_legacy_stub_is_matched_by_citizen_id_and_adopted(client, db):
    db.add(m.User(citizen_id="LEG123", display_name="LEG123", source="legacy", role_id=None))
    db.commit()
    sync(client, pl("LEG123", grade=1, name="Real Name"))
    u = user(db, "LEG123")
    assert u.source == "fivem" and u.display_name == "Real Name" and u.role.key == "journalist"
    assert db.scalar(select(func.count()).select_from(m.User).where(m.User.citizen_id == "LEG123")) == 1  # linked, not duplicated


def test_sync_rejects_malformed_or_oversized_payloads(client, db):
    assert sync(client, pl("bad id")).status_code == 422
    assert sync(client, {**pl("AAA111"), "grade": -1}).status_code == 422
    assert sync(client, {**pl("AAA111"), "job": ""}).status_code == 422
    assert post(client, "/bridge/sync-staff", None, raw=b"not json").status_code == 422
    assert sync(client, *[pl(f"U{i:05d}") for i in range(501)]).status_code == 422
    assert db.scalar(select(func.count()).select_from(m.User)) == 0


def test_config_guards_for_bridge():
    base = dict(ENVIRONMENT="test", JWT_SECRET="x" * 40)
    with pytest.raises(ValidationError):
        Settings(**base, AUTH_MODE="fivem")
    with pytest.raises(ValidationError):
        Settings(**base, AUTH_MODE="fivem", BRIDGE_SECRET="short")
    assert Settings(**base, AUTH_MODE="fivem", BRIDGE_SECRET="s" * 40)


def test_password_login_still_works_in_fivem_mode(client, db):
    s = get_settings()
    old = s.AUTH_MODE
    s.AUTH_MODE = "fivem"
    try:
        make_user(db, "Pat", "journalist", email="pat@weazel.test")
        assert client.post(f"{API}/auth/login", json={"email": "pat@weazel.test", "password": "correct horse battery"}).status_code == 200
    finally:
        s.AUTH_MODE = old


# ------------------------------------------------------------------------------------------------ in-game news delivery

def publish(client, w, title="Port scandal", summary="Short public summary @everyone"):
    art = client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": title, "summary": summary, "body": "SECRET BODY TEXT", "internal_notes": "INTERNAL"}).json()
    for who, to in ((w.jo, "submitted"), (w.editor, "in_review"), (w.editor2, "approved"), (w.editor2, "published")):
        r = client.post(f"{API}/articles/{art['id']}/transition", headers=w.h(who), json={"to": to})
        assert r.status_code == 200, r.text
    return art


def poll(client, since, online, **kw):
    return post(client, "/bridge/news/poll", {"since": since.isoformat() if since else None, "online": online}, **kw)


def test_poll_requires_a_valid_signature(client):
    assert poll(client, None, [], secret="z" * 40).status_code == 401
    assert client.post(f"{API}/bridge/news/poll", json={"since": None, "online": []}).status_code == 401


def test_first_poll_returns_only_a_cursor_so_a_restart_never_replays_news(client, w):
    publish(client, w)
    r = poll(client, None, ["JO12345"]).json()
    assert r["broadcast"] == [] and r["personal"] == [] and r["now"]


def test_published_news_is_broadcast_to_online_players_and_staff_get_personal_notices(client, w, db):
    from datetime import datetime, timezone
    w.jo.citizen_id = "JO12345"
    db.commit()
    before = datetime.now(timezone.utc)
    art = publish(client, w, title="Port scandal")
    r = poll(client, before, ["JO12345", "NOTSTAFF9"])
    assert r.status_code == 200
    data = r.json()
    assert [b["title"] for b in data["broadcast"]] == ["Port scandal"] and data["broadcast"][0]["article_id"] == art["id"]
    assert any(p["citizenid"] == "JO12345" for p in data["personal"])   # the author hears about the decision, in game
    assert "SECRET BODY TEXT" not in r.text and "INTERNAL" not in r.text and "Short public summary" not in r.text  # titles only


def test_nobody_online_means_nothing_is_delivered(client, w, db):
    from datetime import datetime, timezone
    w.jo.citizen_id = "JO12345"
    db.commit()
    before = datetime.now(timezone.utc)
    publish(client, w)
    assert poll(client, before, []).json()["broadcast"] == []
    assert poll(client, before, ["bad id!", "x"]).json()["broadcast"] == []   # malformed ids are ignored, not trusted


def test_personal_notices_only_go_to_the_player_they_belong_to(client, w, db):
    from datetime import datetime, timezone
    w.jo.citizen_id = "JO12345"
    db.commit()
    before = datetime.now(timezone.utc)
    publish(client, w)
    other = poll(client, before, ["SOMEONE99"]).json()
    assert other["personal"] == [] and len(other["broadcast"]) == 1   # news is public, the notice is not


def test_unpublished_work_is_never_broadcast_and_old_news_is_not_replayed(client, w, db):
    from datetime import datetime, timezone
    client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": "Secret draft", "body": "x"})
    before = datetime.now(timezone.utc)
    assert poll(client, before, ["ANYONE1"]).json()["broadcast"] == []
    publish(client, w, title="Real news")
    after = datetime.now(timezone.utc)
    assert poll(client, after, ["ANYONE1"]).json()["broadcast"] == []   # the cursor moved past it
    titles = [b["title"] for b in poll(client, before, ["ANYONE1"]).json()["broadcast"]]
    assert titles == ["Real news"]


def test_an_article_that_is_no_longer_public_is_not_broadcast(client, w, db):
    from datetime import datetime, timezone
    before = datetime.now(timezone.utc)
    art = publish(client, w, title="Pulled story")
    db.get(m.Article, art["id"]).status = "archived"   # published_at stays set, but the story is no longer public
    db.commit()
    assert poll(client, before, ["ANYONE1"]).json()["broadcast"] == []
