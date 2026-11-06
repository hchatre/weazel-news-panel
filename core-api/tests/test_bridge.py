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
from app.services import outbox
from app.services.bridge import sign
from tests.conftest import auth, make_user

API = "/api/v1"
SECRET = "b" * 40


@pytest.fixture(autouse=True)
def bridge_config():
    s = get_settings()
    old = (s.BRIDGE_SECRET, s.DISCORD_WEBHOOK_PUBLISH, s.TICKET_TTL_SECONDS)
    s.BRIDGE_SECRET = SECRET
    yield
    s.BRIDGE_SECRET, s.DISCORD_WEBHOOK_PUBLISH, s.TICKET_TTL_SECONDS = old


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


def test_config_guards_for_bridge_and_discord():
    base = dict(ENVIRONMENT="test", JWT_SECRET="x" * 40)
    with pytest.raises(ValidationError):
        Settings(**base, AUTH_MODE="fivem")
    with pytest.raises(ValidationError):
        Settings(**base, AUTH_MODE="fivem", BRIDGE_SECRET="short")
    assert Settings(**base, AUTH_MODE="fivem", BRIDGE_SECRET="s" * 40)
    with pytest.raises(ValidationError):
        Settings(**base, AUTH_MODE="password", DISCORD_WEBHOOK_PUBLISH="https://evil.example/hook")
    assert Settings(**base, AUTH_MODE="password", DISCORD_WEBHOOK_PUBLISH="https://discord.com/api/webhooks/1/abc")


def test_password_login_still_works_in_fivem_mode(client, db):
    s = get_settings()
    old = s.AUTH_MODE
    s.AUTH_MODE = "fivem"
    try:
        make_user(db, "Pat", "journalist", email="pat@weazel.test")
        assert client.post(f"{API}/auth/login", json={"email": "pat@weazel.test", "password": "correct horse battery"}).status_code == 200
    finally:
        s.AUTH_MODE = old


# ------------------------------------------------------------------------------------------------ discord outbox
WEBHOOK = "https://discord.com/api/webhooks/123/SECRETTOKEN"


def publish(client, w, title="Port scandal", summary="Short public summary @everyone"):
    art = client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": title, "summary": summary, "body": "SECRET BODY TEXT", "internal_notes": "INTERNAL"}).json()
    for who, to in ((w.jo, "submitted"), (w.editor, "in_review"), (w.editor2, "approved"), (w.editor2, "published")):
        r = client.post(f"{API}/articles/{art['id']}/transition", headers=w.h(who), json={"to": to})
        assert r.status_code == 200, r.text
    return art


def test_publication_queues_one_safe_message_and_never_depends_on_discord(client, w, db):
    get_settings().DISCORD_WEBHOOK_PUBLISH = ""
    publish(client, w)
    assert db.scalar(select(func.count()).select_from(m.OutboxMessage)) == 0  # not configured: nothing queued, publication unaffected
    get_settings().DISCORD_WEBHOOK_PUBLISH = WEBHOOK
    art = publish(client, w, title="Second story")
    (row,) = db.scalars(select(m.OutboxMessage)).all()
    blob = json.dumps(row.payload)
    assert row.channel == "publish" and row.status == "pending" and row.event_key.startswith(f"article:{art['id']}:published")
    assert "SECRET BODY" not in blob and "INTERNAL" not in blob and "SECRETTOKEN" not in blob  # public facts only
    assert row.payload["allowed_mentions"] == {"parse": []} and "@everyone" not in blob  # cannot ping anyone
    assert outbox.enqueue(db, "publish", row.event_key, row.payload) is False  # the same event is never queued twice


def test_delivery_retry_backoff_and_giving_up(db):
    get_settings().DISCORD_WEBHOOK_PUBLISH = WEBHOOK
    outbox.enqueue(db, "publish", "evt:1", {"embeds": []})
    db.commit()
    now = datetime.now(timezone.utc)
    calls = []

    def flaky(channel, payload):
        calls.append(now)
        return outbox.SendResult(error="HTTP 503")

    assert outbox.process_due(db, flaky, now) == {"sent": 0, "retry": 1, "dead": 0}
    row = db.scalar(select(m.OutboxMessage))
    assert row.attempts == 1 and row.status == "pending" and row.next_attempt_at > now
    assert outbox.process_due(db, flaky, now) == {"sent": 0, "retry": 0, "dead": 0}  # not due yet: nothing is hammered
    delays = []
    t = now
    for _ in range(10):
        t = row.next_attempt_at + timedelta(seconds=1)
        outbox.process_due(db, flaky, t)
        db.refresh(row)
        if row.status == "dead":
            break
        delays.append((row.next_attempt_at - t).total_seconds())
    assert row.status == "dead" and row.attempts == get_settings().DISCORD_MAX_ATTEMPTS
    assert delays == sorted(delays) and delays[0] < delays[-1]  # exponential backoff
    ok = lambda c, p: outbox.SendResult(ok=True)
    row.status, row.attempts, row.next_attempt_at = "pending", 0, now
    db.commit()
    assert outbox.process_due(db, ok, now)["sent"] == 1 and db.scalar(select(m.OutboxMessage)).sent_at is not None
    assert outbox.process_due(db, ok, now)["sent"] == 0  # a delivered message is never sent again


def test_discord_responses_are_classified(db):
    get_settings().DISCORD_WEBHOOK_PUBLISH = WEBHOOK
    seen = {}

    def run(status, **kw):
        t = httpx.MockTransport(lambda r: (seen.setdefault("url", str(r.url)), httpx.Response(status, **kw))[1])
        return outbox.discord_send("publish", {"x": 1}, transport=t)

    assert run(204).ok
    r429 = run(429, json={"retry_after": 12.5})
    assert not r429.ok and r429.retry_after == 12.5 and not r429.permanent  # Discord's own wait is honoured
    assert run(500).permanent is False and run(404).permanent is True and run(401).permanent is True  # bad webhook: do not hammer
    get_settings().DISCORD_WEBHOOK_PUBLISH = ""
    assert outbox.discord_send("publish", {}).permanent  # not configured
    boom = outbox.discord_send.__wrapped__ if hasattr(outbox.discord_send, "__wrapped__") else None
    get_settings().DISCORD_WEBHOOK_PUBLISH = WEBHOOK

    def raise_(request):
        raise httpx.ConnectError("dns failed for https://discord.com/api/webhooks/123/SECRETTOKEN")

    res = outbox.discord_send("publish", {}, transport=httpx.MockTransport(raise_))
    assert not res.ok and not res.permanent and "SECRETTOKEN" not in res.error  # network errors retry and never echo the URL


def test_outbox_admin_view_hides_secrets_and_allows_retry(client, w, db):
    get_settings().DISCORD_WEBHOOK_PUBLISH = WEBHOOK
    publish(client, w)
    row = db.scalar(select(m.OutboxMessage))
    row.status, row.last_error = "dead", "HTTP 404"
    db.commit()
    assert client.get(f"{API}/admin/integrations/status", headers=w.h(w.jo)).status_code == 403
    r = client.get(f"{API}/admin/integrations/status", headers=w.h(w.admin))
    assert r.status_code == 200 and r.json()["outbox"]["dead"] == 1 and r.json()["bridge_configured"] is True
    assert "SECRETTOKEN" not in r.text and SECRET not in r.text and "embeds" not in r.text
    assert client.post(f"{API}/admin/integrations/outbox/{row.id}/retry", headers=w.h(w.admin)).json()["status"] == "pending"
    db.expire_all()
    assert db.get(m.OutboxMessage, row.id).attempts == 0
