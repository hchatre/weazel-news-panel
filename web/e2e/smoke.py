"""Drives the built frontend in Chrome against a live core-api (dev data). Run: python e2e/smoke.py
Needs: API on :8000 with users jo@/ed@weazel.test (password DevPassword!2026), `npm run build && npm start` on :3000."""
import json, os, subprocess, sys, uuid
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("WEB", "http://127.0.0.1:3000")
PW = "DevPassword!2026"
XSS = '<img src=x onerror="window.__pwned=1">'

def login(page, email, pw=PW):
    page.goto(f"{BASE}/login")
    page.fill("#email", email); page.fill("#pw", pw); page.click("form button")

BRIDGE_JS = os.path.join(os.path.dirname(__file__), "..", "..", "fivem", "server", "bridge.js")
API = os.environ.get("API", "http://127.0.0.1:8000")
BRIDGE_SECRET = os.environ["WEAZEL_BRIDGE_SECRET"]  # same value the API was started with

def bridge(script):
    """Calls the real server/bridge.js, exactly as the game server would."""
    code = f"const b=require({json.dumps(BRIDGE_JS)});const c=b.client({{baseUrl:{json.dumps(API)},secret:{json.dumps(BRIDGE_SECRET)}}});(async()=>{{{script}}})().then(r=>console.log(JSON.stringify(r)))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"), args=["--no-sandbox"])
    page = b.new_page(); page.set_default_timeout(8000)
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))

    login(page, "jo@weazel.test", "wrong"); expect(page.locator("p[role=alert]")).to_contain_text("Sign-in failed")
    login(page, "jo@weazel.test"); expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    page.goto(f"{BASE}/articles/new"); page.fill("#title", "E2E story"); page.fill("#body", "Body text"); page.click("button:has-text('Save')")
    expect(page.get_by_role("heading", name="E2E story")).to_be_visible()
    page.fill("#b", "Edited body"); page.click("button:has-text('Save')"); expect(page.get_by_role("status").filter(has_text="Saved")).to_be_visible()
    page.click("button:has-text('submitted')"); expect(page.locator("h1 ~ div .chyron")).to_have_text("submitted")
    art_url = page.url

    # the author must not be able to review their own article
    expect(page.locator("button:has-text('in review')")).to_have_count(0)

    # investigation: hostile content is rendered as text
    page.goto(f"{BASE}/investigations"); page.fill("#nt", "E2E case"); page.click("button:has-text('Save')")
    page.locator("a:has-text('E2E case')").first.click(); page.fill("#ec", XSS); page.click("button:has-text('Add entry')")
    expect(page.locator("ol li").first).to_contain_text("<img src=x")
    assert page.evaluate("window.__pwned") is None

    # evidence: upload a real PNG, see its hash, and the UI offers no download to a role without evidence.download
    png = "/tmp/wz_e2e.png"; open(png, "wb").write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    page.fill("#evt", "Dock photo"); page.set_input_files("#evf", png); page.click("button:has-text('Upload')")
    expect(page.get_by_text("Dock photo")).to_be_visible(); expect(page.get_by_text("sha256 ")).to_be_visible()
    expect(page.locator("button:has-text('Download')")).to_have_count(0)
    page.click("button:has-text('Custody log')"); expect(page.get_by_text("uploaded", exact=False).first).to_be_visible()
    page.set_input_files("#evf", "/etc/hostname"); page.fill("#evt", "bad"); page.click("button:has-text('Upload')")
    expect(page.locator("p[role=alert]").first).to_contain_text("not allowed")

    # AI assistant (mock provider): output is labelled, citations shown, accepting records a decision but changes nothing
    page.click("button:has-text('Summarise timeline')")
    expect(page.get_by_text("AI-generated suggestion. Not verified").nth(1)).to_be_visible()
    expect(page.get_by_text("MOCK OUTPUT")).to_be_visible()
    page.click("button:has-text('Mark as accepted')"); expect(page.locator("span.chyron", has_text="accepted")).to_be_visible()
    expect(page.locator("ol li").first).to_contain_text("<img src=x")  # the timeline itself is untouched

    # French + theme switch
    page.click("button[aria-label='Language']"); expect(page.get_by_role("link", name="Enquêtes")).to_be_visible()
    page.click("button[aria-label='Thème']"); assert page.evaluate("document.documentElement.classList.contains('dark')") is False

    # editor can pick the article up for review; sign out ends access
    page.click("button[title='Déconnexion']"); expect(page).to_have_url(f"{BASE}/login")
    login(page, "ed@weazel.test"); expect(page.get_by_role("heading", name="Tableau de bord")).to_be_visible()
    bell = page.locator("button[aria-label^='Notifications']"); expect(bell).to_have_attribute("aria-label", __import__("re").compile(r"\(\d+\)"))
    bell.click(); expect(page.get_by_text("En attente de relecture").first).to_be_visible()  # kind text follows the UI language
    page.keyboard.press("Escape"); expect(page.locator("[role=dialog]")).to_have_count(0)
    page.goto(art_url); expect(page.locator("button:has-text('in review')")).to_be_visible()
    page.click("button:has-text('in review')"); expect(page.locator("h1 ~ div .chyron")).to_have_text("in review")

    # in-game sign-in: a signed ticket opens the app with no password, is stripped from the URL, and works only once
    cid = "E2E" + uuid.uuid4().hex[:8]
    assert bridge(f"return c.syncStaff([{{citizenid:'{cid}',name:'Gamer Reporter',job:'reporter',grade:1}}])")["json"]["created"] == 1
    url = bridge(f"return c.issueTicket('{cid}')")["json"]["url"]
    page.evaluate("sessionStorage.clear(); localStorage.setItem('wz_lang','en')")  # the earlier steps switched the UI to French
    page.goto(url); expect(page).to_have_url(f"{BASE}/dashboard")
    expect(page.get_by_text("Gamer Reporter")).to_be_visible()
    assert "ticket" not in page.url
    page.evaluate("sessionStorage.clear()"); page.goto(url)
    expect(page.locator("p[role=alert]")).to_contain_text("already used"); expect(page.get_by_role("link", name="Go to the sign-in page")).to_be_visible()
    page.goto(f"{BASE}/fivem-login"); expect(page.locator("p[role=alert]")).to_be_visible()  # no ticket at all
    # a journalist has no access to integrations (menu hidden and API refuses)
    page.evaluate("sessionStorage.clear()"); page.goto(bridge(f"return c.issueTicket('{cid}')")["json"]["url"]); expect(page).to_have_url(f"{BASE}/dashboard")
    expect(page.get_by_role("link", name="Integrations")).to_have_count(0)
    page.goto(f"{BASE}/admin/integrations"); expect(page.get_by_text("You do not have access")).to_be_visible()
    # an administrator sees the integration status, with no secrets on the page
    page.evaluate("sessionStorage.clear()"); login(page, "admin@weazel.test", "AdminPassword!2026")
    page.get_by_role("link", name="Integrations").click(); expect(page.get_by_text("FiveM bridge")).to_be_visible()
    expect(page.get_by_text("Configured").first).to_be_visible()
    assert BRIDGE_SECRET not in page.content()

    # ---- admin screens: every visible action does something real ----
    page.on("dialog", lambda d: d.accept())
    tag = uuid.uuid4().hex[:6]; hire = f"hire{tag}@weazel.test"; who = f"Test Hire {tag}"
    page.get_by_role("link", name="Staff").click(); expect(page.get_by_role("heading", name="Staff")).to_be_visible()
    page.get_by_role("button", name="Add a staff member").click()
    page.fill("#n", who); page.fill("#e", hire); page.fill("#pw", "a long enough password"); page.select_option("#ro", "intern")
    page.locator("form button", has_text="Add a staff member").click(); expect(page.get_by_text("Staff member added.")).to_be_visible()
    row = page.locator("tbody tr", has_text=who).first
    row.locator("button[aria-expanded]").first.click()
    page.locator("select[id^=r]").first.select_option("journalist"); page.get_by_role("button", name="Apply").first.click(); expect(page.get_by_text("Role changed.")).to_be_visible()
    page.get_by_role("button", name="Deactivate").click(); expect(page.get_by_text("Deactivated.")).to_be_visible()
    expect(page.locator("tbody tr", has_text=who).first.get_by_text("Inactive")).to_be_visible()
    page.get_by_role("link", name="Roles").click(); page.get_by_role("button", name="Journalist 20").click()
    expect(page.get_by_text("Permissions of this role")).to_be_visible(); page.get_by_role("button", name="Save", exact=True).click(); expect(page.get_by_text("Role saved.")).to_be_visible()
    page.get_by_role("link", name="Job grades").click(); expect(page.get_by_role("cell", name="reporter").first).to_be_visible()
    page.get_by_role("button", name="Save", exact=True).click(); expect(page.get_by_text("Job grade saved.")).to_be_visible()
    page.get_by_role("link", name="Workflow").click(); page.get_by_role("button", name="Save step").first.click(); expect(page.get_by_text("Step saved.")).to_be_visible()
    page.get_by_role("link", name="Audit log").click(); expect(page.get_by_role("cell", name="staff.recruit").first).to_be_visible()
    with page.expect_download() as dl: page.get_by_role("button", name="Export CSV").click()
    assert dl.value.suggested_filename == "audit.csv"
    page.fill("#fa", "staff.dismiss"); expect(page.get_by_role("cell", name="staff.dismiss").first).to_be_visible()

    # unauthenticated access redirects to login
    page.context.clear_cookies(); page.evaluate("sessionStorage.clear()"); page.goto(f"{BASE}/articles"); expect(page).to_have_url(f"{BASE}/login")
    assert not errors, errors
    b.close(); print("e2e OK")
