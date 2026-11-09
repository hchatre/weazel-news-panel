"""Loads html/index.html in headless Chrome (served over http so the CSP 'self' rule behaves like NUI's
https://cfx-nui-<resource>/ origin) and sends it hostile data exactly as client/main.lua would.

Needs: pip install playwright, and a Chrome/Chromium binary (CHROME_PATH, default /usr/bin/google-chrome).
It cannot reproduce CEF quirks of the real FiveM client; treat it as a strong check, not proof in-game.
"""
import functools
import http.server
import os
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = os.environ.get("WEAZEL_HTML_DIR") or os.path.join(os.path.dirname(__file__), "..", "..", "html")
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")

INIT = """
window.__calls = [];
window.GetParentResourceName = () => 'weazel';
window.fetch = (url, opts) => {
  window.__calls.push({ event: String(url).split('/').pop(), body: opts && opts.body ? JSON.parse(opts.body) : null });
  return Promise.resolve({ ok: true, json: () => ({}) });
};
window.__pwned = 0;
"""

XSS = [
    '<img src=x onerror="window.__pwned++;fetch(`https://weazel/fire`,{method:`POST`,body:`{}`})">',
    '<svg onload="window.__pwned++">',
    '<script>window.__pwned++</script>',
    '"><img src=x onerror=window.__pwned++>',
    "<iframe srcdoc='<script>parent.__pwned++</script>'></iframe>",
]


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class NuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=ROOT))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/index.html"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()

    def setUp(self):
        self.page = self.browser.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.set_default_timeout(3000)
        self.page.add_init_script(INIT)
        self.page.goto(self.url)

    def tearDown(self):
        self.page.close()

    def post(self, **msg):
        self.page.evaluate("m => window.postMessage(m, '*')", msg)
        self.page.wait_for_timeout(50)

    def ceo(self):
        self.post(action="open")
        self.page.click("#lock")   # the tablet always opens on the lock screen
        self.post(action="loadWeb", url=None)   # no web newsroom available: the built-in panel is shown
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.post(action="setRole", role="reporter", grade=3, name="Chief One")

    def calls(self):
        return self.page.evaluate("window.__calls")

    def pwned(self):
        return self.page.evaluate("window.__pwned")

    def test_page_loads_without_csp_or_script_errors(self):
        self.ceo()
        self.assertEqual([e for e in self.errors if "Content Security Policy" in e or "Refused" in e], [])
        self.assertEqual([e for e in self.errors if "Error" in e and "favicon" not in e], [])

    def test_hostile_article_titles_content_and_authors_do_not_execute(self):
        self.ceo()
        entries = [{"id": i, "title": p, "content": p, "author": p, "date": p, "likes": p, "comments": p}
                   for i, p in enumerate(XSS, 1)]
        self.post(action="setLatestNews", entries=entries)
        self.post(action="setDrafts", drafts=entries)
        self.post(action="setPending", pending=entries)
        self.page.wait_for_timeout(300)
        self.assertEqual(self.pwned(), 0)
        titles = self.page.eval_on_selector_all("#latestNews h3", "els => els.map(e => e.textContent)")
        self.assertEqual(titles, XSS)  # shown as literal text
        self.assertEqual([c for c in self.calls() if c["event"] == "fire"], [])

    def test_hostile_comments_article_and_images(self):
        self.ceo()
        comments = [{"id": i, "author_name": p, "comment": p, "date": p} for i, p in enumerate(XSS, 1)]
        self.post(action="showArticle", article={"id": 1, "title": XSS[0], "content": XSS[2], "author": XSS[1],
                                                 "date": "d", "image": 'https://x.test/a.png" onerror="window.__pwned++',
                                                 "likes": 0, "liked": False, "comments": comments})
        self.page.wait_for_timeout(300)
        self.assertEqual(self.pwned(), 0)
        self.assertEqual(self.page.locator("#viewArticleContent img").count(), 0)  # unsafe URL refused, no <img> built
        texts = self.page.eval_on_selector_all("#commentsList .comment-text", "els => els.map(e => e.textContent)")
        self.assertEqual(texts, XSS)

    def test_hostile_notification_and_css_url_breakout(self):
        self.ceo()
        self.post(action="articleNotification", notification={
            "title": XSS[0], "content": XSS[1], "author": XSS[3],
            "image": 'https://x.test/a.png");background-image:url("https://evil.test/leak'})
        self.page.wait_for_timeout(300)
        self.assertEqual(self.pwned(), 0)
        self.assertEqual(self.page.locator(".notification-image").count(), 0)
        self.assertEqual(self.page.locator(".notification-title").text_content(), XSS[0])
        self.post(action="articleNotification", notification={"title": "ok", "content": "c", "author": "a", "image": "https://x.test/ok.png"})
        self.assertEqual(self.page.locator(".notification-image").count(), 1)

    def test_hostile_timeline_and_admin_rows(self):
        self.ceo()
        self.post(action="setTimeline", entries=[{"id": i, "status": p, "content": p, "author": p, "date": p} for i, p in enumerate(XSS, 1)])
        self.post(action="setAdmin", users=[{"citizenid": p, "name": p, "grade": 1, "online": True, "last_login": p} for p in XSS])
        self.page.wait_for_timeout(300)
        self.assertEqual(self.pwned(), 0)
        classes = self.page.eval_on_selector_all("#timeline .news-card", "els => els.map(e => e.className)")
        self.assertEqual(set(classes), {"news-card rumour"})  # unknown status never becomes a class/attribute injection

    def test_admin_buttons_still_send_the_right_callbacks(self):
        self.ceo()
        self.page.click("[data-page=admin]")
        self.post(action="setAdmin", users=[{"citizenid": "ABC123", "name": "Jo Journalist", "grade": 1, "online": False, "last_login": "x"}])
        self.page.click(".fire")
        self.page.click("#fireConfirm")
        self.assertIn({"event": "fire", "body": {"citizenid": "ABC123"}}, self.calls())

    def test_nav_and_editor_flow(self):
        self.ceo()
        self.page.click("[data-page=create]")
        self.assertTrue(self.page.is_visible("#page-create"))
        # editing a draft: Publish must send the form content, not only the id
        self.page.click("[data-page=drafts]")
        self.post(action="setDrafts", drafts=[{"id": 7, "title": "Mine", "author": "Chief One", "date": "d"}])
        self.page.click("#draftList .btn-rumour")  # Edit
        self.post(action="showArticle", article={"id": 7, "title": "Mine", "content": "Old", "category": "crime", "image": None})
        self.page.fill("#createContent", "New body")
        self.page.click("#publishArticleBtn")
        publish = [c for c in self.calls() if c["event"] == "publishDraft"]
        self.assertEqual(len(publish), 1)
        self.assertEqual((publish[0]["body"]["id"], publish[0]["body"]["content"]), (7, "New body"))

    # ---- tablet and lock screen ----
    def test_panel_opens_on_a_lock_screen_and_the_app_is_not_reachable_until_unlocked(self):
        self.post(action="open", clock={"h": 7, "m": 5, "dow": 1, "d": 3, "mo": 10})
        self.assertTrue(self.page.is_visible("#lock"))
        self.assertFalse(self.page.is_visible("#app"))   # hidden from sight, clicks and keyboard
        self.assertEqual(self.page.inner_text("#lockTime"), "07:05")
        self.assertEqual(self.page.inner_text("#lockDay"), "Monday, 3 November")
        self.page.click("#lock")
        self.assertEqual([c["event"] for c in self.calls()], ["unlock"])   # the page only asks; it never picks a URL itself
        self.post(action="loadWeb", url=None)
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.assertTrue(self.page.is_visible("#app"))
        self.page.wait_for_selector("#lock", state="hidden")

    def test_lock_screen_can_be_opened_with_the_keyboard_and_relocked_with_the_home_bar(self):
        self.post(action="open")
        self.page.focus("#lock")
        self.page.keyboard.press("Enter")
        self.post(action="loadWeb", url=None)
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.page.click("#homeBar")
        self.page.wait_for_selector("#tablet.locked")
        self.assertFalse(self.page.is_visible("#app"))

    def test_unlock_loads_the_web_newsroom_in_a_frame_and_closing_clears_it(self):
        self.post(action="open")
        self.page.click("#lock")
        self.post(action="loadWeb", url="http://127.0.0.1:1/fivem-login?ticket=T")
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.assertFalse(self.page.is_visible("#app"))
        self.assertIn("fivem-login?ticket=T", self.page.get_attribute("#webFrame", "src"))
        self.page.click("#homeBar")                      # relock keeps the page, so unlocking again needs no new ticket
        self.page.wait_for_selector("#tablet.locked")
        n = len(self.calls())
        self.page.click("#lock")
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.assertEqual(len(self.calls()), n)
        self.post(action="close")
        self.assertEqual(self.page.get_attribute("#webFrame", "src"), "about:blank")

    def test_a_web_page_that_never_starts_falls_back_to_the_built_in_panel_and_reports_it(self):
        self.page.evaluate("window.WEAZEL_WEB_TIMEOUT_MS = 300")
        self.post(action="open")
        self.post(action="loadWeb", url="http://127.0.0.1:1/fivem-login?ticket=T")
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.page.wait_for_selector("#webFrame", state="hidden")
        self.assertTrue(self.page.is_visible("#app"))
        self.assertIn("webFailed", [c["event"] for c in self.calls()])

    def test_the_ready_message_cancels_the_fallback(self):
        self.page.evaluate("window.WEAZEL_WEB_TIMEOUT_MS = 300")
        self.post(action="open")
        self.post(action="loadWeb", url="http://127.0.0.1:1/x")
        self.post(type="weazel-ready")
        self.page.wait_for_timeout(600)
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.assertNotIn("webFailed", [c["event"] for c in self.calls()])

    def test_only_http_urls_are_framed_and_a_failed_ticket_shows_the_built_in_panel(self):
        for bad in ("javascript:window.__pwned=1", "data:text/html,x", "file:///etc/passwd"):
            self.post(action="open")
            self.page.click("#lock")
            self.post(action="loadWeb", url=bad)
            self.assertFalse(self.page.is_visible("#webFrame"))
            self.assertTrue(self.page.is_visible("#app"))
            self.post(action="close")
        self.assertFalse(self.pwned())

    def test_escape_inside_the_web_panel_closes_the_tablet(self):
        self.post(action="open")
        self.post(type="weazel-tablet-close")
        self.assertIn("close", [c["event"] for c in self.calls()])

    def test_lock_screen_shows_the_latest_headlines_as_text_only(self):
        self.post(action="open")
        self.post(action="setLatestNews", entries=[
            {"id": 1, "title": 'Pier 4 blaze <img src=x onerror="window.__pwned=1">', "category": "Breaking", "likes": 0, "comments": 0},
            {"id": 2, "title": "Council approves curfew", "category": "Politics", "likes": 0, "comments": 0},
            {"id": 3, "title": "Third", "likes": 0, "comments": 0}, {"id": 4, "title": "Fourth is not shown", "likes": 0, "comments": 0}])
        cards = self.page.locator("#lockNews .lock-card")
        self.assertEqual(cards.count(), 3)
        self.assertIn("Pier 4 blaze", cards.first.inner_text())
        self.assertEqual(self.page.locator("#lockNews img").count(), 0)
        self.assertFalse(self.pwned())

    def test_clock_updates_while_open_and_close_hides_the_tablet_and_reopens_locked(self):
        self.post(action="open", clock={"h": 23, "m": 59, "dow": 6, "d": 31, "mo": 11})
        self.post(action="clock", clock={"h": 0, "m": 0, "dow": 0, "d": 1, "mo": 0})
        self.assertEqual(self.page.inner_text("#lockTime"), "00:00")
        self.assertEqual(self.page.inner_text("#lockDay"), "Sunday, 1 January")
        self.page.click("#lock")
        self.post(action="loadWeb", url=None)
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.post(action="close")
        self.assertFalse(self.page.is_visible("#tablet"))
        self.post(action="open")
        self.assertTrue(self.page.is_visible("#lock"))   # it never reopens already unlocked

    def test_escape_closes_from_the_lock_screen_too(self):
        self.post(action="open")
        self.page.keyboard.press("Escape")
        self.assertTrue(any(c["event"] == "close" for c in self.calls()))

    def test_timeline_buttons_without_inline_handlers(self):
        self.ceo()
        self.page.click("[data-page=dossiers]")
        self.post(action="setDossiers", dossiers=[{"id": 3, "title": "Case"}])
        self.page.click("#dossierList .dossier-item", position={"x": 5, "y": 5})  # the row centre can be a rename/delete button
        self.page.fill("#timelineInput", "a tip")
        self.page.click("[data-timeline=rumour]")
        self.assertIn({"event": "addEntry", "body": {"id": 3, "status": "rumour", "content": "a tip"}}, self.calls())

    def test_other_players_like_changes_counter_only(self):
        self.ceo()
        self.post(action="showArticle", article={"id": 1, "title": "t", "content": "c", "author": "a", "date": "d", "likes": 1, "liked": True, "comments": []})
        self.post(action="updateLikes", articleId=1, count=2)  # someone else liked: no `liked` field
        self.assertEqual(self.page.text_content("#likeCount"), "2")
        self.assertEqual(self.page.text_content("#likeIcon"), "❤️")  # my heart is unchanged
        self.post(action="updateLikes", articleId=1, count=1, liked=False)
        self.assertEqual(self.page.text_content("#likeIcon"), "\U0001F90D")


if __name__ == "__main__":
    unittest.main()
