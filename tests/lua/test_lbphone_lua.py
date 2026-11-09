"""Runs the real client/lbphone.lua in an embedded Lua runtime with FiveM and LB Phone stubbed.
It tests our decisions (what is registered, what the icon does). It does NOT prove LB Phone accepts the app."""
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
EVENTS = {}
function TriggerEvent(n) EVENTS[#EVENTS + 1] = 'event:' .. n end
exports = setmetatable({}, { __index = function(_, res)
  return { AddCustomApp = function(self, def) LAST_DEF = def; return py.addapp(def) end,
           ToggleOpen = function(self, open) EVENTS[#EVENTS + 1] = 'phone:' .. tostring(open) end }
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
        if not hasattr(x, "keys"):
            return "<function>"
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


class ClientTest(unittest.TestCase):
    def test_registers_with_the_documented_fields_when_lb_phone_is_running(self):
        e = Env("client/lbphone.lua")
        e.fire("onResourceStart", 0, "lb-phone")
        (d,) = e.addapp_calls
        self.assertEqual((d["identifier"], d["name"], d["defaultApp"], d["keepOpen"]), ("weazel_news", "Weazel News", True, True))
        self.assertNotIn("ui", d)   # no page inside the phone: the icon opens the tablet
        self.assertEqual(d["icon"], "https://cfx-nui-weazel-test/html/logo.png")
        self.assertIn("registered", e.prints[-1])
        e.fire("onResourceStart", 0, "lb-phone")
        self.assertEqual(len(e.addapp_calls), 1)  # not registered twice
        e.fire("onResourceStop", 0, "lb-phone")
        e.fire("onResourceStart", 0, "lb-phone")
        self.assertEqual(len(e.addapp_calls), 2)  # lb-phone restarted: register again

    def test_the_icon_closes_the_phone_then_asks_the_tablet_to_open(self):
        e = Env("client/lbphone.lua")
        e.fire("onResourceStart", 0, "lb-phone")
        e.lua.execute("LAST_DEF.onUse()")
        self.assertEqual(list(e.lua.globals().EVENTS.values()), ["phone:false", "event:weazel:client:requestOpen"])  # phone first, so they never fight over focus

    def test_registration_failure_is_reported_not_thrown(self):
        e = Env("client/lbphone.lua")
        e.addapp_result = RuntimeError("no such export")
        e.fire("onResourceStart", 0, "weazel-test")
        self.assertIn("NOT registered", e.prints[-1])
        e2 = Env("client/lbphone.lua")
        e2.lua.globals().resourceStates["lb-phone"] = None  # not installed / not started
        e2.fire("onResourceStart", 0, "weazel-test")
        self.assertEqual(e2.addapp_calls, [])


if __name__ == "__main__":
    unittest.main()
