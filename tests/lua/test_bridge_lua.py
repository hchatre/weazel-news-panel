"""Runs the real server/bridge.lua in an embedded Lua runtime with FiveM, QBCore, oxmysql and the JS bridge stubbed.
Tests WHAT the Lua sends and tells players. It cannot test real exports between Lua and JS, real QBCore events or oxmysql."""
import json as pyjson
import os
import unittest

from lupa import LuaRuntime

BRIDGE_LUA = os.path.join(os.path.dirname(__file__), "..", "..", "server", "bridge.lua")

PRELUDE = r"""
local py = ...
H, CMD, THREADS = {}, {}, {}
P = {}
QBCore = { Functions = { GetPlayer = function(src) return P[src] end } }
function GetCurrentResourceName() return 'weazel-test' end
function GetConvar(n, d) return py.convar(n, d) end
function GetGameTimer() return py.now() end
function Wait() end
function CreateThread(fn) THREADS[#THREADS+1] = fn end   -- not run: the loop is infinite; the work is reachable through the event below
function RegisterCommand(name, fn) CMD[name] = fn end
function AddEventHandler(name, fn) H[name] = fn end
function TriggerEvent(name, ...) if H[name] then H[name](...) end end
function TriggerClientEvent(ev, target, payload) py.client(ev, target, payload) end
json = { decode = function(s) return py.decode(s) end }
MySQL = { query = { await = function(sql, params) return py.query(sql, params) end } }
bridge = {}
local api = {}
for _, name in ipairs({ 'issueTicket', 'syncStaff', 'staffIds' }) do
  api[name] = function(self, cb, ...) py.bridge(name, cb, { ... }) end   -- exports[res]:name(cb, args...) passes self first
end
exports = setmetatable({ ['weazel-test'] = api }, { __index = function() return { GetCoreObject = function() return QBCore end } end })
function addPlayer(src, cid, first, last, job, level)
  P[src] = { PlayerData = { source = src, citizenid = cid, charinfo = { firstname = first, lastname = last }, job = { name = job, grade = { level = level } } } }
end
function callCmd(name, src, ...) CMD[name](src, ...) end
function fire(name, ...) H[name](...) end
function call(fn, ...) fn(...) end
"""


class Env:
    def __init__(self, convars=None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.convars = convars if convars is not None else {"weazel_bridge_secret": "s" * 40, "weazel_api_url": "http://127.0.0.1:8000"}
        self.clock, self.chats, self.bridge_calls, self.queries = 0, [], [], []
        self.bridge_reply = {"issueTicket": (True, 200, {"url": "http://localhost:3000/fivem-login?ticket=T1"}), "syncStaff": (True, 200, {}),
                             "staffIds": (True, 200, {"citizenids": []})}
        self.db_rows = {}
        py = self.lua.table_from({
            "convar": lambda n, d: self.convars.get(n, d), "now": lambda: self.clock,
            "client": lambda ev, tgt, payload: self.chats.append((ev, tgt, self.to_py(payload))),
            "decode": lambda s: self.to_lua(pyjson.loads(s)), "query": self._query, "bridge": self._bridge,
        })
        self.lua.execute(PRELUDE, py)
        with open(BRIDGE_LUA, encoding="utf-8") as f:
            self.lua.execute(f.read())

    def to_py(self, x):
        if x is None or isinstance(x, (str, int, float, bool)):
            return x
        keys = list(x.keys())
        if keys == list(range(1, len(keys) + 1)):
            return [self.to_py(x[k]) for k in keys]
        return {str(k): self.to_py(x[k]) for k in keys}

    def to_lua(self, x):
        if isinstance(x, dict):
            return self.lua.table_from({k: self.to_lua(v) for k, v in x.items()})
        if isinstance(x, list):
            return self.lua.table_from([self.to_lua(v) for v in x])
        return x

    def _query(self, sql, params):
        sql = " ".join(sql.split())
        self.queries.append((sql, self.to_py(params) if params is not None else None))
        if "WHERE citizenid = ?" in sql:
            cid = self.to_py(params)[0]
            return self.to_lua([self.db_rows[cid]] if cid in self.db_rows else [])
        return self.to_lua([r for r in self.db_rows.values() if pyjson.loads(r["job"])["name"] == "reporter"])

    def _bridge(self, name, cb, args):
        self.bridge_calls.append((name, self.to_py(args) if args is not None else []))
        ok, status, body = self.bridge_reply[name]
        cb(ok, status, self.to_lua(body))

    def player(self, src, cid, first, last, job, level):
        self.lua.globals().addPlayer(src, cid, first, last, job, level)

    def command(self, name, src):
        self.lua.globals().callCmd(name, src)

    def event(self, name, *args):
        self.lua.globals().fire(name, *args)

    def says(self, src):
        return [p["args"][1] for ev, t, p in self.chats if ev == "chat:addMessage" and t == src]


def row(cid, first, last, job, grade):
    return {"citizenid": cid, "charinfo": pyjson.dumps({"firstname": first, "lastname": last}), "job": pyjson.dumps({"name": job, "grade": {"level": grade}})}


class BridgeLuaTest(unittest.TestCase):
    def test_ticket_uses_the_servers_identity_and_goes_to_that_player_only(self):
        e = Env()
        e.player(3, "REP1", "Jo", "Journalist", "reporter", 1)
        e.player(4, "REP2", "Ed", "Editor", "reporter", 2)
        e.command("newsroom", 3)
        self.assertEqual(e.bridge_calls, [("issueTicket", ["REP1"])])  # citizenid comes from source 3's QBCore player
        self.assertEqual(len(e.says(3)), 1)
        self.assertIn("fivem-login?ticket=T1", e.says(3)[0])
        self.assertEqual(e.says(4), [])  # nobody else receives the link

    def test_cooldown_unknown_account_outage_and_console(self):
        e = Env()
        e.player(3, "REP1", "Jo", "Journalist", "reporter", 1)
        e.command("newsroom", 3)
        e.command("newsroom", 3)
        self.assertEqual(len(e.bridge_calls), 1)  # spamming does not hammer the API
        self.assertIn("wait", e.says(3)[-1].lower())
        e.clock = 20000
        e.bridge_reply["issueTicket"] = (True, 404, {})
        e.command("newsroom", 3)
        self.assertIn("do not have a newsroom account", e.says(3)[-1])
        e.clock = 40000
        e.bridge_reply["issueTicket"] = (False, 0, {})
        e.command("newsroom", 3)
        self.assertIn("unavailable", e.says(3)[-1])
        n = len(e.bridge_calls)
        e.command("newsroom", 0)  # server console
        self.assertEqual(len(e.bridge_calls), n)

    def test_nothing_is_sent_when_the_bridge_is_not_configured(self):
        e = Env(convars={})
        e.player(3, "REP1", "Jo", "Journalist", "reporter", 1)
        e.command("newsroom", 3)
        e.event("QBCore:Server:OnJobUpdate", 3, {"name": "reporter", "grade": {"level": 2}})
        e.event("weazel:bridge:fullSync")
        self.assertEqual(e.bridge_calls, [])
        self.assertIn("not set up", e.says(3)[0])

    def test_job_change_is_reported_immediately_with_server_data(self):
        e = Env()
        e.player(3, "REP1", "Jo", "Journalist", "reporter", 1)
        e.event("QBCore:Server:OnJobUpdate", 3, {"name": "unemployed", "grade": {"level": 0}})  # dismissed while online
        (name, args), = e.bridge_calls
        self.assertEqual((name, args[0]), ("syncStaff", [{"citizenid": "REP1", "name": "Jo Journalist", "job": "unemployed", "grade": 0}]))

    def test_full_sync_includes_reporters_and_known_staff_who_left(self):
        e = Env()
        e.db_rows = {"REP1": row("REP1", "Jo", "Journalist", "reporter", 1), "OLD1": row("OLD1", "Old", "Hand", "unemployed", 0), "COP1": row("COP1", "Cop", "X", "police", 3)}
        e.bridge_reply["staffIds"] = (True, 200, {"citizenids": ["REP1", "OLD1"]})
        e.event("weazel:bridge:fullSync")
        sync = [c for c in e.bridge_calls if c[0] == "syncStaff"]
        self.assertEqual(len(sync), 1)
        got = {p["citizenid"]: (p["job"], p["grade"]) for p in sync[0][1][0]}
        self.assertEqual(got, {"REP1": ("reporter", 1), "OLD1": ("unemployed", 0)})  # dismissed offline player is reported, unrelated police is not
        self.assertTrue(all("?" in q or "reporter" in q for q, _ in e.queries))
        self.assertEqual([p for q, p in e.queries if p], [["OLD1"]])  # values go through placeholders, never string-built

    def test_full_sync_still_reports_reporters_if_the_id_list_fails_and_batches_large_sets(self):
        e = Env()
        e.db_rows = {f"R{i:04d}": row(f"R{i:04d}", "N", str(i), "reporter", 1) for i in range(850)}
        e.bridge_reply["staffIds"] = (False, 0, {})
        e.event("weazel:bridge:fullSync")
        sizes = [len(c[1][0]) for c in e.bridge_calls if c[0] == "syncStaff"]
        self.assertEqual(sizes, [400, 400, 50])  # the API accepts at most 500 per request

    def test_missing_charinfo_falls_back_to_the_citizen_id(self):
        e = Env()
        e.db_rows = {"ZZZ999": {"citizenid": "ZZZ999", "charinfo": "{}", "job": pyjson.dumps({"name": "reporter", "grade": 2})}}
        e.event("weazel:bridge:fullSync")
        p = [c for c in e.bridge_calls if c[0] == "syncStaff"][0][1][0][0]
        self.assertEqual((p["name"], p["grade"]), ("ZZZ999", 2))  # grade given as a bare number is also understood


if __name__ == "__main__":
    unittest.main()
