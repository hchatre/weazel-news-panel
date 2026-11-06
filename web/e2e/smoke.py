"""Drives the built frontend in Chrome against a live core-api (dev data). Run: python e2e/smoke.py
Needs: API on :8000 with users jo@/ed@weazel.test (password DevPassword!2026), `npm run build && npm start` on :3000."""
import os, sys
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("WEB", "http://127.0.0.1:3000")
PW = "DevPassword!2026"
XSS = '<img src=x onerror="window.__pwned=1">'

def login(page, email, pw=PW):
    page.goto(f"{BASE}/login")
    page.fill("#email", email); page.fill("#pw", pw); page.click("form button")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"), args=["--no-sandbox"])
    page = b.new_page(); page.set_default_timeout(8000)
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))

    login(page, "jo@weazel.test", "wrong"); expect(page.locator("p[role=alert]")).to_contain_text("Sign-in failed")
    login(page, "jo@weazel.test"); expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    page.goto(f"{BASE}/articles/new"); page.fill("#title", "E2E story"); page.fill("#body", "Body text"); page.click("button:has-text('Save')")
    expect(page.get_by_role("heading", name="E2E story")).to_be_visible()
    page.fill("#b", "Edited body"); page.click("button:has-text('Save')"); expect(page.get_by_role("status").filter(has_text="Saved")).to_be_visible()
    page.click("button:has-text('submitted')"); expect(page.locator("h1 ~ div .badge")).to_have_text("submitted")
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
    page.click("button:has-text('Mark as accepted')"); expect(page.locator("span.badge", has_text="accepted")).to_be_visible()
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
    page.click("button:has-text('in review')"); expect(page.locator("h1 ~ div .badge")).to_have_text("in review")

    # unauthenticated access redirects to login
    page.context.clear_cookies(); page.evaluate("sessionStorage.clear()"); page.goto(f"{BASE}/articles"); expect(page).to_have_url(f"{BASE}/login")
    assert not errors, errors
    b.close(); print("e2e OK")
