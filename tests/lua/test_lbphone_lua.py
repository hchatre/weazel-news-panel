"""Runs the real client/lbphone.lua and server/lbphone.lua in an embedded Lua runtime with FiveM and LB Phone stubbed.
It tests our decisions (what is fetched, what is forwarded, request bookkeeping). It does NOT prove LB Phone accepts the app."""
import json as pyjson
import os
import unittest

from lupa import LuaRuntime

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

PRELUDE = r"""
local py = ...
H, NUI, TIMEOUTS, SERVER_EVENTS = {}, {}, {}, {}
source = 0
resourceStates = { ['lb-phone'] = 'started' }
addAppCalls = {}
function GetConvar(n, d) return py.convar(n, d) end
function GetGameTimer() return py.now() end
function GetCurrentResourceName() return 'weazel-test' end
function GetResourceState(n) return resourceStates[n] or 'missing' end
function Wait() end
function CreateThread(fn) fn() end
function SetTimeout(ms, fn) TIMEOUTS[#TIMEOUTS + 1] = { ms = ms, fn = fn } end
function RegisterNetEvent(name, fn) if fn then H[name] = fn end end
function AddEventHandler(name, fn) H[name] = fn end
function RegisterNUICallback(name, fn) NUI[name] = fn end
function TriggerClientEvent(ev, target, ...) py.client(ev, target, ...) end
function TriggerServerEvent(ev, ...) py.server(ev, ...) end
function PerformHttpRequest(url, cb, method, data, headers) local status, body = py.http(url, method); cb(status, body) end
function print(...) py.print(...) end
json = { decode = function(s) return py.decode(s) end }
exports = setmetatable({}, { __index = function(_, res)
  return { AddCustomApp = function(self, def) return py.addapp(def) end }
end })
function fire(name, src, ...) source = src; H[name](...) end
function nui(name, data, cb) NUI[name](data, cb) end
"""


class Env:
    def __init__(self, lua_file, convars=None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.convars = convars if convars is not None else {"weazel_api_url": "http://127.0.0.1:8000/"}
        self.clock, self.http, self.client_events, self.server_events, self.prints, self.addapp_calls = 0, [], [], [], [], []
        self.http_reply, self.addapp_result = (200, "{}"), True
        py = self.lua.table_from({
            "convar": lambda n, d: self.convars.get(n, d), "now": lambda: self.clock,
            "http": self._http, "decode": self._decode, "print": lambda *a: self.prints.append(" ".join(str(x) for x in a)),
            "client": lambda ev, tgt, *a: self.client_events.append((ev, tgt, [self.to_py(x) for x in a])),
            "server": lambda ev, *a: self.server_events.append((ev, [self.to_py(x) for x in a])),
            "addapp": self._addapp,
        })
        self.lua.execute(PRELUDE, py)
        with open(os.path.join(ROOT, lua_file), encoding="utf-8") as f:
            self.lua.execute(f.read())

    def _http(self, url, method):
        self.http.append((url, method))
        status, body = self.http_reply() if callable(self.http_reply) else self.http_reply
        return status, body

    def _decode(self, s):
        return self.to_lua(pyjson.loads(s))  # raises on invalid JSON; the Lua code must survive that

    def _addapp(self, d):
        self.addapp_calls.append(self.to_py(d))
        if isinstance(self.addapp_result, Exception):
            raise self.addapp_result
        return self.addapp_result

    def to_py(self, x):
        if x is None or isinstance(x, (str, int, float, bool)):
            return x
        keys = list(x.keys())
        if not keys:
            return []
        if keys == list(range(1, len(keys) + 1)):
            return [self.to_py(x[k]) for k in keys]
        return {str(k): self.to_py(x[k]) for k in keys}

    def to_lua(self, x):
        if isinstance(x, dict):
            return self.lua.table_from({k: self.to_lua(v) for k, v in x.items()})
        if isinstance(x, list):
            return self.lua.table_from([self.to_lua(v) for v in x])
        return x

    def fire(self, name, src, *args):
        self.lua.globals().fire(name, src, *[self.to_lua(a) if isinstance(a, (dict, list)) else a for a in args])

    def nui(self, name, data):
        got = []
        self.lua.globals().nui(name, self.to_lua(data) if isinstance(data, (dict, list)) else data, lambda r: got.append(self.to_py(r)))
        return got


def api(items=None, **extra):
    return (200, pyjson.dumps({"items": items if items is not None else [], "total": len(items or []), **extra}))


ART = {"id": 7, "title": "Port scandal", "subtitle": "s", "summary": "sum", "category": "crime", "author": "Jo", "published_at": "2026-01-10T09:30:00Z",
       "is_breaking": True, "cover_image_url": "https://evil.test/x.png", "internal_notes": "INTERNAL", "body": "FULL BODY", "token": "T"}


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.e = Env("server/lbphone.lua")

    def results(self):
        # (event, target, (request id, data, error)); a success carries only (id, data)
        return [(ev, tgt, (a + [None])[:3] if len(a) < 3 else a) for ev, tgt, a in self.e.client_events if ev == "weazel:phone:result"]

    def test_feed_forwards_only_allow_listed_fields_to_the_asking_player(self):
        self.e.http_reply = api([ART])
        self.e.fire("weazel:phone:feed", 5, 11, 2)
        self.assertEqual(self.e.http, [("http://127.0.0.1:8000/api/v1/public/articles?page=2&page_size=15", "GET")])  # trailing slash handled
        (ev, tgt, (req, data, err)), = self.results()
        self.assertEqual((tgt, req, err), (5, 11, None))
        item = data["items"][0]
        self.assertEqual(item["title"], "Port scandal")
        for leaked in ("cover_image_url", "internal_notes", "body", "token"):
            self.assertNotIn(leaked, item)  # anything not on the list is dropped, even if the API adds fields later

    def test_clients_cannot_choose_the_url_or_escape_the_path(self):
        self.e.http_reply = api([])
        for bad in ("../../admin", "1/../../x", "abc", None, -4, 0, 1e12 * 0):
            self.e.clock += 5000
            self.e.fire("weazel:phone:article", 5, 1, bad)
        self.assertEqual(self.e.http, [])  # nothing ever reached the network
        self.assertTrue(all(a[2] == "not_found" for _, _, a in self.results()))
        self.e.clock += 5000
        self.e.fire("weazel:phone:feed", 5, 1, "9999999")
        self.e.clock += 5000
        self.e.fire("weazel:phone:feed", 5, 2, "x")
        self.assertEqual([u.split("page=")[1] for u, _ in self.e.http], ["1&page_size=15", "1&page_size=15"])  # out-of-range / non-numeric pages become 1

    def test_article_detail_includes_body_and_correction_and_truncates(self):
        self.e.http_reply = (200, pyjson.dumps({**ART, "body": "x" * 50000, "correction_note": "fixed a name", "corrected_at": "2026-02-01T00:00:00Z"}))
        self.e.fire("weazel:phone:article", 5, 3, 7)
        self.assertEqual(self.e.http[0][0], "http://127.0.0.1:8000/api/v1/public/articles/7")
        (_, _, (req, data, err)), = self.results()
        self.assertEqual(len(data["body"]), 20000)
        self.assertEqual(data["correction_note"], "fixed a name")
        self.assertNotIn("internal_notes", data)

    def test_api_trouble_never_crashes_or_leaks(self):
        cases = [((500, "boom secret"), "unavailable"), ((200, "not json"), "unavailable"), ((200, "[1,2]"), "unavailable"), ((404, ""), "not_found"), ((0, None), "unavailable")]
        for reply, expected in cases:
            self.e.clock += 5000
            self.e.client_events.clear()
            self.e.http_reply = reply
            self.e.fire("weazel:phone:article", 5, 9, 7)
            (_, _, (req, data, err)), = self.results()
            self.assertEqual((data, err), (None, expected), reply)

    def test_oversized_text_and_bad_items_are_cut_or_skipped(self):
        self.e.http_reply = api([{**ART, "title": "T" * 999, "summary": "S" * 999}, {"id": "nope", "title": "bad"}, "junk", {"title": "no id"}])
        self.e.fire("weazel:phone:feed", 5, 1, 1)
        (_, _, (_, data, _)), = self.results()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual((len(data["items"][0]["title"]), len(data["items"][0]["summary"])), (200, 400))

    def test_cooldown_is_per_player_and_not_configured_makes_no_request(self):
        self.e.http_reply = api([ART])
        self.e.fire("weazel:phone:feed", 5, 1, 1)
        self.e.fire("weazel:phone:feed", 5, 2, 1)
        self.e.fire("weazel:phone:feed", 6, 3, 1)  # a different player is not throttled by the first
        self.assertEqual([a[2] for _, _, a in self.results()], [None, "slow_down", None])
        self.assertEqual(len(self.e.http), 2)
        off = Env("server/lbphone.lua", convars={})
        off.fire("weazel:phone:feed", 5, 1, 1)
        self.assertEqual((off.http, [a[2] for _, _, a in off.client_events]), ([], ["not_configured"]))


class ClientTest(unittest.TestCase):
    def test_registers_with_the_documented_fields_when_lb_phone_is_running(self):
        e = Env("client/lbphone.lua")
        e.fire("onResourceStart", 0, "lb-phone")
        (d,) = e.addapp_calls
        self.assertEqual((d["identifier"], d["name"], d["ui"], d["defaultApp"]), ("weazel_news", "Weazel News", "weazel-test/html/lbphone/index.html", True))
        self.assertEqual(d["icon"], "https://cfx-nui-weazel-test/html/logo.png")
        self.assertIn("registered", e.prints[-1])
        e.fire("onResourceStart", 0, "lb-phone")
        self.assertEqual(len(e.addapp_calls), 1)  # not registered twice
        e.fire("onResourceStop", 0, "lb-phone")
        e.fire("onResourceStart", 0, "lb-phone")
        self.assertEqual(len(e.addapp_calls), 2)  # lb-phone restarted: register again

    def test_registration_failure_is_reported_not_thrown(self):
        e = Env("client/lbphone.lua")
        e.addapp_result = RuntimeError("no such export")
        e.fire("onResourceStart", 0, "weazel-test")
        self.assertIn("NOT registered", e.prints[-1])
        e2 = Env("client/lbphone.lua")
        e2.lua.globals().resourceStates["lb-phone"] = None  # not installed / not started
        e2.fire("onResourceStart", 0, "weazel-test")
        self.assertEqual(e2.addapp_calls, [])

    def test_requests_are_matched_answered_once_and_time_out(self):
        e = Env("client/lbphone.lua")
        got = e.nui("getFeed", {"page": 3})
        (ev, (rid, page)), = e.server_events
        self.assertEqual((ev, page), ("weazel:phone:feed", 3))
        e.fire("weazel:phone:result", 0, rid + 99, {"x": 1})  # an answer for a request nobody made is ignored
        self.assertEqual(got, [])
        e.fire("weazel:phone:result", 0, rid, {"items": []})
        e.fire("weazel:phone:result", 0, rid, {"items": ["again"]})
        self.assertEqual(got, [{"items": []}])  # one answer only
        late = e.nui("getArticle", {"id": 5})
        t = e.lua.globals().TIMEOUTS
        e.lua.eval("function() for _, t in ipairs(TIMEOUTS) do t.fn() end end")()
        self.assertEqual(late, [{"error": "timeout"}])
        rid2 = e.server_events[-1][1][0]
        e.fire("weazel:phone:result", 0, rid2, {"title": "too late"})
        self.assertEqual(late, [{"error": "timeout"}])
        err = e.nui("getFeed", "not a table")  # malformed UI data cannot break the callback
        self.assertEqual(e.server_events[-1][1][1], 1)
        e.fire("weazel:phone:result", 0, e.server_events[-1][1][0], None, "slow_down")
        self.assertEqual(err, [{"error": "slow_down"}])


if __name__ == "__main__":
    unittest.main()
