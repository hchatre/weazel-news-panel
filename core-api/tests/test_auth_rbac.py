import jwt
import pytest

from app import models as m
from app.config import Settings
from app.security import create_access_token
from tests.conftest import auth, make_user

API = "/api/v1"


def test_login_ok_and_me(client, w):
    r = client.post(f"{API}/auth/login", json={"email": "jo.journalist@weazel.test", "password": "correct horse battery"})
    assert r.status_code == 200
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["role"]["key"] == "journalist" and "article.create" in me["permissions"] and "staff.dismiss" not in me["permissions"]


def test_login_failures_are_indistinguishable_and_rate_limited(client, w):
    bad_pw = client.post(f"{API}/auth/login", json={"email": "jo.journalist@weazel.test", "password": "nope"})
    no_user = client.post(f"{API}/auth/login", json={"email": "ghost@weazel.test", "password": "nope"})
    assert bad_pw.status_code == no_user.status_code == 401 and bad_pw.json() == no_user.json()
    for _ in range(5):
        client.post(f"{API}/auth/login", json={"email": "jo.journalist@weazel.test", "password": "nope"})
    blocked = client.post(f"{API}/auth/login", json={"email": "jo.journalist@weazel.test", "password": "correct horse battery"})
    assert blocked.status_code == 429  # even the right password is refused while blocked


def test_inactive_user_cannot_login_or_use_old_token(client, w, db):
    headers = w.h(w.jo)
    w.jo.is_active = False
    db.commit()
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "jo.journalist@weazel.test", "password": "correct horse battery"}).status_code == 401


def test_requires_token_and_rejects_garbage_expired_and_forged(client, w):
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    forged = jwt.encode({"sub": str(w.admin.id), "tv": 0, "exp": 9999999999}, "another-secret-another-secret-123456", algorithm="HS256")
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = jwt.encode({"sub": str(w.jo.id), "tv": 0, "exp": 1}, "test-secret-test-secret-test-secret-123", algorithm="HS256")
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    none_alg = jwt.encode({"sub": str(w.admin.id), "tv": 0, "exp": 9999999999}, None, algorithm="none")
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401


def test_password_change_invalidates_old_tokens(client, w):
    old = w.h(w.jo)
    r = client.post(f"{API}/auth/change-password", headers=old, json={"current_password": "correct horse battery", "new_password": "a brand new passphrase"})
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=old).status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_user_without_role_has_no_permissions(client, w):
    me = client.get(f"{API}/auth/me", headers=w.h(w.stub)).json()
    assert me["permissions"] == []
    assert client.post(f"{API}/articles", headers=w.h(w.stub), json={"title": "x"}).status_code == 403


def test_individual_deny_beats_role_and_grant_adds(client, w, db):
    db.add(m.UserPermission(user_id=w.jo.id, permission_key="article.create", effect="deny", reason="test"))
    db.add(m.UserPermission(user_id=w.intern.id, permission_key="article.approve", effect="grant", reason="test"))
    db.commit()
    assert client.post(f"{API}/articles", headers=w.h(w.jo), json={"title": "x"}).status_code == 403
    perms = client.get(f"{API}/auth/me", headers=w.h(w.intern)).json()["permissions"]
    assert "article.approve" in perms


def test_every_privileged_route_rejects_unauthenticated_and_unprivileged(client, w):
    routes = [("get", "/admin/roles"), ("get", "/admin/audit"), ("get", "/staff"), ("post", "/admin/users"), ("get", "/admin/workflow"), ("get", "/admin/permissions")]
    for method, path in routes:
        assert getattr(client, method)(API + path).status_code == 401, path
        assert getattr(client, method)(API + path, headers=w.h(w.jo)).status_code in (403, 422), path


def test_config_guards():
    with pytest.raises(ValueError):
        Settings(AUTH_MODE="local", ENVIRONMENT="production")
    with pytest.raises(ValueError):
        Settings(AUTH_MODE="fivem", ENVIRONMENT="development")
    with pytest.raises(ValueError):
        Settings(AUTH_MODE="password", ENVIRONMENT="production", JWT_SECRET="change-me-to-a-long-random-string")
    with pytest.raises(ValueError):
        Settings(AUTH_MODE="password", ENVIRONMENT="production", JWT_SECRET="short")
    assert Settings(AUTH_MODE="password", ENVIRONMENT="production", JWT_SECRET="x" * 40, AI_PROVIDER="none").AUTH_MODE == "password"


def test_local_mode_resolves_single_admin_without_token(db, monkeypatch):
    from fastapi.testclient import TestClient
    from app import deps
    from app.main import app

    class S:
        AUTH_MODE = "local"
        LOCAL_ADMIN_NAME = "Local Administrator"
    monkeypatch.setattr(deps, "get_settings", lambda: S)
    r = TestClient(app).get(f"{API}/auth/me")
    assert r.status_code == 200 and r.json()["role"]["key"] == "system_admin"
