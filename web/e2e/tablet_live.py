"""The tablet page (fivem/html) around the real web app and the real API, with a pretend game: what the game server would answer
to "unlock" is a real ticket from fivem/server/bridge.js for the character's CURRENT job. Checks that every open signs in fresh, and
that a job change shows up on screen (pushed by the game, and noticed by the page when the game says nothing).
Needs: API on :8000 (password mode, WEAZEL_BRIDGE_SECRET set), web on :3000 built and started, WEAZEL_BRIDGE_SECRET in the environment."""
import functools, http.server, json, os, subprocess, threading, uuid
from playwright.sync_api import sync_playwright, expect
import playwright.sync_api as _pw

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "fivem")
BRIDGE_JS = os.path.join(ROOT, "server", "bridge.js")
API = os.environ.get("API", "http://127.0.0.1:8000")
SECRET = os.environ["WEAZEL_BRIDGE_SECRET"]
CID = "LIVE" + uuid.uuid4().hex[:6].upper()
game = {"job": "unemployed", "grade": 0}   # the pretend game's idea of the character


def bridge(call):
    code = f"const b=require({json.dumps(BRIDGE_JS)});const c=b.client({{baseUrl:{json.dumps(API)},secret:{json.dumps(SECRET)}}});(async()=>{call})().then(r=>console.log(JSON.stringify(r)))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])


def player():
    return {"citizenid": CID, "name": "Live Person", "job": game["job"], "grade": game["grade"]}


def unlock_answer():
    r = bridge(f"c.issueTicket({json.dumps(CID)}, {json.dumps(player())})")
    return r["json"]["url"] if r["status"] == 200 else None


def sync_like_the_game():   # what the server does on QBCore:Server:OnJobUpdate
    bridge(f"c.syncStaff([{json.dumps(player())}])")


h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.join(ROOT, "html"))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
threading.Thread(target=srv.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"), args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1700, "height": 1000}); page.set_default_timeout(15000); expect.set_options(timeout=15000)
    asked = []
    def on_unlock():
        asked.append(1)
        return unlock_answer()
    page.expose_function("wz_unlock", on_unlock)
    page.add_init_script("""if (window.top === window) { window.GetParentResourceName = () => 'weazel';
        const f = window.fetch; window.fetch = (u, o) => { if (String(u).endsWith('/unlock')) window.wz_unlock().then(u => window.postMessage({action:'loadWeb', url:u, reason:'unavailable'}, '*')); return Promise.resolve({ok:true,json:()=>({})}); } }""")
    page.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
    page.evaluate("window.postMessage({action:'open', clock:{h:22,m:5,dow:2,d:10,mo:10}}, '*')")
    page.click("#lock")
    web = page.frame_locator("#webFrame")

    # 1. unemployed: signed in as the character, read-only
    expect(web.get_by_role("heading", name="Dashboard")).to_be_visible()
    assert web.locator("aside a[href='/investigations']").count() == 0
    web.locator("aside a[href='/articles']").click()
    expect(web.get_by_role("heading", name="Articles")).to_be_visible()
    assert web.get_by_role("link", name="New article").count() == 0
    print("ok unemployed: read-only")

    # 2. hired as director (grade 2) in game: the game tells the tablet, the page signs in again by itself
    game.update(job="reporter", grade=2); sync_like_the_game()
    page.evaluate("window.postMessage({action:'refresh'}, '*')")
    expect(web.locator("aside a[href='/investigations']")).to_be_visible()
    web.locator("aside a[href='/articles']").click()
    expect(web.get_by_role("link", name="New article")).to_be_visible()
    assert page.evaluate("!document.getElementById('tablet').classList.contains('locked')")
    print("ok promoted: role changed on screen, tablet stayed open")

    # 3. dismissed in game and the game says nothing to the tablet: the web page notices within ~10s and asks to sign in again
    n = len(asked)
    game.update(job="unemployed", grade=0); sync_like_the_game()
    deadline = 25000
    page.wait_for_timeout(deadline)
    assert len(asked) > n, "the page never asked for a new sign-in"
    expect(web.locator("aside a[href='/investigations']")).to_have_count(0)
    web.locator("aside a[href='/articles']").click()
    expect(web.get_by_role("heading", name="Articles")).to_be_visible()
    assert web.get_by_role("link", name="New article").count() == 0
    print("ok dismissed: read-only again without any message from the game")

    # 4. closing and opening again signs in again (a new ticket every open)
    n = len(asked)
    page.evaluate("window.postMessage({action:'close'}, '*')")
    page.evaluate("window.postMessage({action:'open', clock:{}}, '*')")
    page.click("#lock")
    expect(web.get_by_role("heading", name="Dashboard")).to_be_visible()
    assert len(asked) == n + 1
    print("ok reopened: new sign-in")
    b.close()
print("tablet live OK")
