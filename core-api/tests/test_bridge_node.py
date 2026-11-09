"""Cross-language check: the real server/bridge.js (run by Node) talks to a real running API process.
Proves the signature scheme matches byte for byte. Skipped if Node is missing."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest
from sqlalchemy import select

from app import models as m
from app.services.bridge import sign as py_sign

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRIDGE_JS = os.path.join(ROOT, "fivem", "server", "bridge.js")
SECRET = "n" * 40
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@pytest.fixture(scope="module")
def api_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "WEAZEL_BRIDGE_SECRET": SECRET, "WEAZEL_ENVIRONMENT": "test", "WEAZEL_AUTH_MODE": "password",
           "WEAZEL_PUBLIC_BASE_URL": "http://localhost:3000"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
                            cwd=os.path.join(ROOT, "core-api"), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("API did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def node(script: str, api_url: str, secret: str = SECRET):
    code = f"const b=require({json.dumps(BRIDGE_JS)}); const c=b.client({{baseUrl:{json.dumps(api_url)},secret:{json.dumps(secret)}}});" \
           f"(async()=>{{ {script} }})().then(r=>console.log(JSON.stringify(r))).catch(e=>{{console.log(JSON.stringify({{error:e.message}}))}})"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_node_and_python_sign_identically():
    out = node("return b.sign('k'.repeat(32),'post','/api/v1/bridge/session','1700000000','abcdef0123456789',Buffer.from('{\"a\":1}'))", "http://x")
    assert out == py_sign("k" * 32, "POST", "/api/v1/bridge/session", "1700000000", "abcdef0123456789", b'{"a":1}')


def test_full_flow_from_node_to_api(api_url, db):
    players = [{"citizenid": "ABC123", "name": "Jo Reporter", "job": "reporter", "grade": 0}, {"citizenid": "COP999", "name": "Cop", "job": "police", "grade": 4}]
    r = node(f"return c.syncStaff({json.dumps(players)})", api_url)
    assert r["status"] == 200 and r["json"]["created"] == 2 and r["json"]["skipped_unmapped"] == 0
    db.expire_all()
    assert db.scalar(select(m.User).where(m.User.citizen_id == "ABC123")).role.key == "journalist"
    ids = node("return c.staffIds()", api_url)  # a signed GET with an empty body
    assert ids["status"] == 200 and ids["json"]["citizenids"] == ["ABC123"]   # the police officer is a freelancer: not listed
    t = node("return c.issueTicket('ABC123')", api_url)
    assert t["status"] == 200 and t["json"]["url"].startswith("http://localhost:3000/fivem-login?ticket=")
    ex = httpx.post(f"{api_url}/api/v1/auth/fivem-exchange", json={"ticket": t["json"]["ticket"]})
    assert ex.status_code == 200
    assert node("return c.issueTicket('NOBODY1')", api_url)["status"] == 404
    info = node("return c.issueTicket('NEWBIE1', {name:'New Person', job:'unemployed', grade:0})", api_url)
    assert info["status"] == 200   # first open creates the account from what the server reports
    assert "error" in node("return c.issueTicket('bad id!')", api_url)  # refused before anything is sent


def test_wrong_secret_stale_clock_and_replay_are_rejected(api_url):
    assert node("return c.syncStaff([])", api_url, secret="z" * 40)["status"] == 401
    assert node("return c.request({path:'/api/v1/bridge/sync-staff',body:{players:[]},ts:Math.floor(Date.now()/1000)-3600})", api_url)["status"] == 401
    first = node("return c.request({path:'/api/v1/bridge/sync-staff',body:{players:[]},nonce:'fixednonce0123456789'})", api_url)
    again = node("return c.request({path:'/api/v1/bridge/sync-staff',body:{players:[]},nonce:'fixednonce0123456789'})", api_url)
    assert (first["status"], again["status"]) == (200, 401)


def test_unconfigured_or_unreachable_never_hangs_or_leaks(api_url):
    assert "not configured" in node("return c.syncStaff([])", api_url, secret="short")["error"]
    unreachable = node("return c.request({path:'/x',body:{},timeoutMs:1500})", "http://127.0.0.1:9")
    assert "error" in unreachable and SECRET not in json.dumps(unreachable)
