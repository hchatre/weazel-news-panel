"""Loads html/lbphone/index.html in headless Chrome with a stubbed `fetchNui` (what LB Phone provides inside the phone).
Checks rendering, navigation, error states and that hostile article text can never become markup or script.
It cannot show that LB Phone 2.8.1 actually loads or hosts this page."""
import functools
import http.server
import json
import os
import re
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "html", "lbphone")
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
XSS = ['<img src=x onerror="window.__pwned=1">', "<script>window.__pwned=1</script>", '"><svg onload=window.__pwned=1>', "<iframe srcdoc='<script>parent.__pwned=1</script>'></iframe>"]

INIT = """
window.__pwned = 0; window.__calls = [];
window.__reply = {};
window.fetchNui = (name, data) => { window.__calls.push({name, data}); const r = window.__reply[name]; return Promise.resolve(typeof r === 'function' ? r(data) : r); };
"""


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


class PhoneUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=ROOT))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/index.html"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.srv.shutdown()

    def open(self, init_js="", **replies):
        page = self.browser.new_page()
        page.set_default_timeout(3000)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.add_init_script(INIT + "window.__reply = " + json.dumps(replies) + ";" + init_js)
        page.goto(self.url)
        return page

    def test_hostile_titles_authors_summaries_and_bodies_are_literal_text(self):
        items = [{"id": i, "title": p, "summary": p, "author": p, "category": p, "published_at": p, "is_breaking": True} for i, p in enumerate(XSS, 1)]
        page = self.open(getFeed={"items": items, "page": 1, "total": 4})
        page.wait_for_selector(".card")
        titles = page.eval_on_selector_all(".card h2", "els => els.map(e => e.textContent)")
        self.assertEqual(titles, XSS)
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate("window.__pwned"), 0)
        self.assertEqual(page.locator("main img, main svg, main iframe, main script").count(), 0)
        page.evaluate("""() => { window.__reply.getArticle = { id: 1, title: %s, subtitle: %s, author: %s, category: 'x', published_at: 'x', body: %s, correction_note: %s }; }"""
                      % tuple(json.dumps(XSS[i]) for i in (0, 1, 2, 3, 0)))
        page.click(".card")
        page.wait_for_selector("article")
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate("window.__pwned"), 0)
        self.assertEqual(page.locator("article img, article svg, article iframe, article script").count(), 0)
        self.assertIn(XSS[3], page.locator("article").text_content())
        self.assertEqual(self.errors, [])

    def test_navigation_and_requests(self):
        page = self.open(init_js="""window.__reply.getFeed = (d) => ({ items: [{ id: d.page * 10, title: 'Story ' + d.page, summary: 's', author: 'Jo', category: 'c', published_at: '2026-01-10T09:30:00Z' }], page: d.page, total: 40 });""")
        page.wait_for_selector(".card")
        self.assertEqual(page.text_content(".card h2"), "Story 1")
        self.assertEqual(page.locator("button:has-text('Newer')").count(), 0)
        page.click("button:has-text('Older')")
        page.wait_for_function("document.querySelector('.card h2').textContent === 'Story 2'")
        self.assertEqual(page.locator("button:has-text('Newer')").count(), 1)
        page.evaluate("window.__reply.getArticle = { id: 20, title: 'Detail', author: 'Jo', category: 'c', published_at: 'x', body: 'Line 1\\nLine 2', correction_note: 'Name fixed' }")
        page.click(".card")
        page.wait_for_selector("article")
        self.assertIn("Correction: Name fixed", page.text_content("article"))
        self.assertTrue(page.is_visible("#back"))
        page.click("#back")
        page.wait_for_selector(".card")
        self.assertEqual(page.text_content(".card h2"), "Story 2")  # back returns to the page you were on
        calls = page.evaluate("window.__calls")
        self.assertEqual([(c["name"], c["data"]) for c in calls], [("getFeed", {"page": 1}), ("getFeed", {"page": 2}), ("getArticle", {"id": 20}), ("getFeed", {"page": 2})])

    def test_error_and_empty_states_are_explained(self):
        for reply, expected in (({"error": "timeout"}, "did not answer"), ({"error": "not_configured"}, "not available on this server"), ({"error": "weird"}, "unavailable"),
                                ({"items": [], "page": 1, "total": 0}, "No stories yet")):
            page = self.open(getFeed=reply)
            page.wait_for_selector("[role=status]")
            page.wait_for_function("document.querySelector('[role=status]').textContent !== 'Loading…'")
            self.assertIn(expected, page.text_content("[role=status]"))
            page.close()
        page = self.open()  # fetchNui resolves undefined: still no crash
        page.wait_for_function("document.querySelector('[role=status]').textContent !== 'Loading…'")
        self.assertEqual(self.errors, [])

    def test_page_never_uses_html_injection_apis(self):
        src = "\n".join(re.sub(r"//.*$", "", ln) for ln in open(os.path.join(ROOT, "app.js"), encoding="utf-8").read().splitlines())  # code only, not comments
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "setTimeout(\"", "srcdoc"):
            self.assertNotIn(banned, src)
        self.assertIsNone(re.search(r"https?://", src))  # the page contacts nothing itself; all data comes through the phone


if __name__ == "__main__":
    unittest.main()
