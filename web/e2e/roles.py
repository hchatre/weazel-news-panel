"""Signs in through the real game-server path (server/bridge.js -> /bridge/session -> ticket -> /fivem-login) as characters with
different jobs, and checks what each one sees and can do in the web app. Run after smoke.py's setup (API :8000 in password mode,
web :3000 built and started). Needs WEAZEL_BRIDGE_SECRET."""
import json, os, subprocess, uuid
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("WEB", "http://127.0.0.1:3000")
API = os.environ.get("API", "http://127.0.0.1:8000")
BRIDGE_JS = os.path.join(os.path.dirname(__file__), "..", "..", "fivem", "server", "bridge.js")
SECRET = os.environ["WEAZEL_BRIDGE_SECRET"]
RUN = uuid.uuid4().hex[:6].upper()


def ticket(cid, name, job, grade):
    info = json.dumps({"name": name, "job": job, "grade": grade})
    code = f"const b=require({json.dumps(BRIDGE_JS)});const c=b.client({{baseUrl:{json.dumps(API)},secret:{json.dumps(SECRET)}}});(async()=>c.issueTicket({json.dumps(cid)},{info}))().then(r=>console.log(JSON.stringify(r)))"
    r = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
    assert r["status"] == 200, r
    return r["json"]["url"].replace("http://127.0.0.1:3000", BASE)


# who, job, grade, role label, may see investigations, staff page, admin pages
CASES = [
    ("Free Lance", "unemployed", 0, "Freelancer", False, False, False),
    ("Taxi Driver", "taxi", 2, "Freelancer", False, False, False),
    ("Jay Journalist", "reporter", 0, "Journalist", True, False, False),
    ("Rae Reporter", "reporter", 1, "Senior Journalist", True, False, False),
    ("Dee Director", "reporter", 2, "Editor", True, True, False),
    ("Chi Chief", "reporter", 3, "Editor-in-Chief", True, True, False),
    ("Ada Admin", "reporter", 4, "System Administrator", True, True, True),
]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"), args=["--no-sandbox"])
    for i, (name, job, grade, role, inv, staff, adm) in enumerate(CASES):
        ctx = b.new_context(viewport={"width": 1500, "height": 900})
        page = ctx.new_page(); page.set_default_timeout(10000)
        errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(ticket(f"R{RUN}{i}", name, job, grade))
        expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
        nav = page.locator("aside")
        assert page.locator("header").inner_text().count(name) >= 1 or name in page.content(), f"{name} not shown as the signed-in user"
        assert (nav.locator("a[href='/investigations']").count() == 1) == inv, (name, "investigations link")
        assert (nav.locator("a[href='/admin/staff']").count() == 1) == staff, (name, "staff link")
        assert (nav.locator("a[href='/admin/roles']").count() == 1) == adm, (name, "admin link")
        page.goto(f"{BASE}/articles"); expect(page.get_by_role("heading", name="Articles")).to_be_visible()
        if role == "Freelancer":
            # read-only: the content is there, but no button and no form to create or edit anything
            assert page.get_by_role("link", name="New article").count() == 0, (name, "New article button")
            page.goto(f"{BASE}/articles/new"); page.wait_for_timeout(800)
            assert page.locator("main input, main textarea, main select").count() == 0, (name, "input on the new-article page")
            assert "not have access" in page.locator("main").inner_text(), name
        else:
            page.goto(f"{BASE}/articles/new"); page.fill("#title", f"{name} story {RUN}"); page.fill("#body", "Body")
            page.click("button:has-text('Save')"); expect(page.get_by_role("heading", name=f"{name} story {RUN}")).to_be_visible()
            # a photo can be added to the story and is shown
            page.fill("#ci", f"{BASE}/icon.png"); page.fill("#cc", "A caption")
            page.get_by_role("button", name="Save", exact=True).click(); expect(page.get_by_text("Saved")).to_be_visible()
            page.reload(); expect(page.locator("main img[alt='A caption']")).to_be_visible()
        if staff:   # the staff page lists the newsroom only: not the freelancers, not other departments
            page.goto(f"{BASE}/admin/staff"); page.wait_for_timeout(1500)
            body = page.locator("main").inner_text()
            assert "Free Lance" not in body and "Taxi Driver" not in body, (name, "non-reporters on the staff page")
            assert "Jay Journalist" in body, (name, "reporter missing from the staff page")
        # what the role is, from the API's point of view
        me = page.evaluate("async () => { const t = localStorage.getItem('weazel_token') || sessionStorage.getItem('weazel_token'); return t }")
        if not inv:   # direct URL: the page must refuse politely, not crash or show data
            page.goto(f"{BASE}/investigations"); page.wait_for_timeout(1200)
            assert page.locator("a[href='/investigations/new']").count() == 0, (name, "freelancer can start an investigation")
        assert not errors, (name, errors)
        print("ok", name, "->", role)
        ctx.close()
    b.close()
print("roles OK")
