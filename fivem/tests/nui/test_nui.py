"""Loads html/index.html in headless Chrome (served over http so the CSP 'self' rule behaves like NUI's
https://cfx-nui-<resource>/ origin) and sends it messages exactly as client/main.lua would, including hostile ones.

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
XSS = ['<img src=x onerror="window.__pwned++">', '<svg onload="window.__pwned++">', "<script>window.__pwned++</script>"]
CLOCK = {"h": 21, "m": 7, "dow": 1, "d": 9, "mo": 10}
URL = "http://127.0.0.1:1/fivem-login?ticket=T"


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
        self.page.add_init_script(INIT)
        self.page.goto(self.url)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def post(self, **msg):
        self.page.evaluate("m => window.postMessage(m, '*')", msg)
        self.page.wait_for_timeout(100)

    def calls(self):
        return self.page.evaluate("window.__calls")

    def events(self):
        return [c["event"] for c in self.calls()]

    def pwned(self):
        return self.page.evaluate("window.__pwned")

    def open_and_unlock(self, url=URL):
        self.post(action="open", clock=CLOCK)
        self.page.click("#lock")
        self.post(action="loadWeb", url=url)

    # ------------------------------------------------------------------------------------------ lock screen
    def test_nothing_shows_until_the_game_opens_it_and_it_opens_on_the_lock_screen_with_the_game_time(self):
        self.assertTrue(self.page.is_hidden("#tablet"))
        self.post(action="open", clock=CLOCK)
        self.assertTrue(self.page.is_visible("#lock"))
        self.assertEqual(self.page.text_content("#lockTime"), "21:07")
        self.assertEqual(self.page.text_content("#lockDay"), "Monday, 9 November")
        self.post(action="clock", clock={**CLOCK, "m": 8})
        self.assertEqual(self.page.text_content("#lockTime"), "21:08")

    def test_the_old_panel_is_gone(self):
        self.assertEqual(self.page.locator("#app, .header, #createTitle").count(), 0)

    def test_hostile_clock_values_are_shown_as_text_or_ignored(self):
        self.post(action="open", clock={"h": XSS[0], "m": XSS[1], "dow": XSS[2], "d": "x", "mo": {}})
        self.assertEqual(self.pwned(), 0)
        self.assertRegex(self.page.text_content("#lockTime"), r"^\d\d:\d\d$")

    def test_tapping_the_lock_screen_only_asks_to_unlock_and_enter_works_too(self):
        self.post(action="open", clock=CLOCK)
        self.page.click("#lock")
        self.assertEqual(self.calls(), [{"event": "unlock", "body": {}}])   # no URL, no id, nothing the page could choose
        self.page.click("#lock")
        self.assertEqual(self.events(), ["unlock"])   # waiting for the answer: tapping again does not ask twice
        self.assertEqual(self.page.text_content("#lockHint"), "Opening\u2026")

    # ------------------------------------------------------------------------------------------ the web newsroom
    def test_the_signed_in_link_loads_in_a_frame_and_closing_clears_it(self):
        self.open_and_unlock()
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.assertIn("fivem-login?ticket=T", self.page.get_attribute("#webFrame", "src"))
        self.page.click("#homeBar")   # relock keeps the page, so unlocking again needs no new ticket
        self.page.wait_for_selector("#tablet.locked")
        self.page.click("#lock")
        self.page.wait_for_selector("#tablet:not(.locked)")
        self.assertEqual(self.events(), ["unlock"])
        self.post(action="close")
        self.assertEqual(self.page.get_attribute("#webFrame", "src"), "about:blank")
        self.assertTrue(self.page.is_hidden("#tablet"))

    def test_only_http_urls_are_framed(self):
        for bad in ("javascript:window.__pwned=1", "data:text/html,x", "file:///etc/passwd", None, 5):
            self.open_and_unlock(bad)
            self.assertFalse(self.page.is_visible("#webFrame"))
            self.assertTrue(self.page.is_visible("#lock"))
            self.post(action="close")
        self.assertEqual(self.pwned(), 0)

    def test_a_failed_sign_in_stays_on_the_lock_screen_and_says_why_in_plain_text(self):
        self.post(action="open", clock=CLOCK)
        self.page.click("#lock")
        self.post(action="loadWeb", url=None, reason="noaccount")
        self.assertIn("no newsroom account", self.page.text_content("#lockMsg"))
        self.assertEqual(self.page.text_content("#lockHint"), "Click to try again")
        self.page.click("#lock")   # and it can be tried again
        self.assertEqual(self.events(), ["unlock", "unlock"])
        self.post(action="loadWeb", url=None, reason=XSS[0])   # an unknown reason never reaches the page as HTML
        self.assertEqual(self.pwned(), 0)
        self.assertNotIn("<img", self.page.inner_html("#lockMsg"))

    def test_a_web_page_that_never_starts_returns_to_the_lock_screen_and_is_reported(self):
        self.page.evaluate("window.WEAZEL_WEB_TIMEOUT_MS = 300")
        self.open_and_unlock()
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.page.wait_for_selector("#webFrame", state="hidden")
        self.assertTrue(self.page.is_visible("#lock"))
        self.assertIn("could not be loaded", self.page.text_content("#lockMsg"))
        self.assertIn("webFailed", self.events())

    def test_the_ready_message_cancels_the_timeout(self):
        self.page.evaluate("window.WEAZEL_WEB_TIMEOUT_MS = 300")
        self.open_and_unlock()
        self.post(type="weazel-ready")
        self.page.wait_for_timeout(600)
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.assertNotIn("webFailed", self.events())

    # ------------------------------------------------------------------------------------------ a role can change at any time
    def test_a_job_change_in_game_signs_in_again_in_place_without_flashing_the_lock_screen(self):
        self.open_and_unlock()
        self.assertEqual(self.events(), ["unlock"])
        self.post(action="refresh")
        self.assertEqual(self.events(), ["unlock", "unlock"])   # a fresh ticket is requested: the API re-reads the job
        self.assertTrue(self.page.is_visible("#webFrame"))
        self.assertTrue(self.page.evaluate("!document.getElementById('tablet').classList.contains('locked')"))
        self.post(action="loadWeb", url="http://127.0.0.1:1/fivem-login?ticket=NEW")
        self.assertIn("ticket=NEW", self.page.get_attribute("#webFrame", "src"))
        self.assertTrue(self.page.evaluate("!document.getElementById('tablet').classList.contains('locked')"))

    def test_the_web_page_reporting_an_ended_session_does_the_same_and_can_never_loop(self):
        self.open_and_unlock()
        self.post(type="weazel-relogin")
        self.post(type="weazel-relogin")
        self.post(action="refresh")
        self.assertEqual(self.events(), ["unlock", "unlock"])   # three requests close together: one new ticket

    def test_a_job_change_while_locked_or_with_nothing_loaded_costs_nothing_until_the_next_tap(self):
        self.post(action="open", clock=CLOCK)
        self.post(action="refresh")
        self.assertEqual(self.events(), [])
        self.open_and_unlock()
        self.page.click("#homeBar")
        self.post(action="refresh")                 # locked: drop the old page, ask nothing yet
        self.assertEqual(self.events(), ["unlock"])
        self.page.click("#lock")                    # the next tap gets a fresh ticket
        self.assertEqual(self.events(), ["unlock", "unlock"])

    # ------------------------------------------------------------------------------------------ closing
    def test_escape_on_the_page_and_escape_inside_the_web_page_both_close(self):
        self.post(action="open", clock=CLOCK)
        self.page.keyboard.press("Escape")
        self.assertEqual(self.events(), ["close"])
        self.post(type="weazel-tablet-close")
        self.assertEqual(self.events(), ["close", "close"])

    def test_closed_means_closed_escape_does_nothing_and_the_frame_is_blank(self):
        self.post(action="open", clock=CLOCK)
        self.post(action="close")
        self.page.keyboard.press("Escape")
        self.assertEqual(self.events(), [])


if __name__ == "__main__":
    unittest.main()
