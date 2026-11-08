"""Runs the real server/main.lua inside an embedded Lua runtime (lupa) with FiveM/QBCore/oxmysql stubbed.

This tests the resource's decision logic (who may do what, what SQL runs, what is sent to Discord/clients).
It is NOT a FiveM server: it cannot test NUI, game natives, real oxmysql behaviour or real QBCore internals.
The embedded Lua is 5.4/5.5; FiveM runs 5.3 by default, so avoid 5.4-only syntax in the resource.
"""
import json as pyjson
import os

from lupa import LuaRuntime

SERVER_LUA = os.environ.get("WEAZEL_SERVER_LUA") or os.path.join(os.path.dirname(__file__), "..", "..", "server", "main.lua")

PRELUDE = r"""
local py = ...
H = {}
P = {}
setjobs = {}
QBCore = {
  Shared = { Jobs = {} },
  Functions = {
    GetPlayer = function(src) return P[src] end,
    GetPlayers = function() local t = {} for s in pairs(P) do t[#t+1] = s end return t end,
    GetPlayerByCitizenId = function(cid) for _, p in pairs(P) do if p.PlayerData.citizenid == cid then return p end end end,
  },
}
exports = setmetatable({}, { __index = function() return { GetCoreObject = function() return QBCore end } end })
local function mk(kind) return { await = function(sql, params) return py.sql(kind, sql, params) end } end
MySQL = { query = mk('query'), update = mk('update'), insert = mk('insert'), scalar = mk('scalar') }
function RegisterNetEvent(name, fn) if fn then H[name] = fn end end
function AddEventHandler(name, fn) H[name] = fn end
function RegisterCommand() end
function CreateThread(fn) fn() end
function SetTimeout(ms, fn) py.timeout(ms) end
function Wait() end
function GetGameTimer() return py.now() end
function GetConvar(n, d) return py.convar(n, d) end
function GetConvarInt(n, d) return tonumber(py.convar(n, d)) or d end
function TriggerClientEvent(ev, target, payload) py.event(ev, target, payload) end
function PerformHttpRequest(url, cb, method, body) py.http(url, body) end
json = { encode = function(t) return py.encode(t) end, decode = function(s) return py.decode(s) end }
function addPlayer(src, cid, first, last, job, level)
  local p = { PlayerData = { source = src, citizenid = cid, charinfo = { firstname = first, lastname = last },
                             job = { name = job, grade = { level = level } } } }
  p.Functions = { SetJob = function(name, grade)
    setjobs[#setjobs+1] = { src = src, name = name, grade = grade }
    p.PlayerData.job = { name = name, grade = { level = grade } }
  end }
  P[src] = p
end
function fire(name, src, arg) source = src; H[name](arg) end
"""


class Env:
    def __init__(self, convars=None, has_author_cid=False):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.convars = convars or {}
        self.has_author_cid = has_author_cid
        self.sql, self.events, self.http, self.timeouts = [], [], [], []
        self.responders = []
        self.clock = 0
        py = self.lua.table_from({
            "sql": self._sql, "event": self._event, "http": self._http, "timeout": lambda ms: self.timeouts.append(ms),
            "now": lambda: self.clock, "convar": lambda n, d: self.convars.get(n, d),
            "encode": lambda t: pyjson.dumps(self.to_py(t)), "decode": lambda s: self.to_lua(pyjson.loads(s)),
        })
        self.lua.execute(PRELUDE, py)
        self.respond("scalar", "information_schema", 1 if has_author_cid else 0)
        with open(SERVER_LUA, encoding="utf-8") as f:
            self.lua.execute(f.read())

    # --- conversion -------------------------------------------------------------------------
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

    # --- stubs ------------------------------------------------------------------------------
    def respond(self, kind, substr, response):
        self.responders.insert(0, (kind, substr, response))

    def _sql(self, kind, sql, params):
        sql = " ".join(sql.split())
        p = self.to_py(params) if params is not None else []
        self.sql.append((kind, sql, p))
        for k, sub, resp in self.responders:
            if k == kind and sub in sql:
                return self.to_lua(resp(p) if callable(resp) else resp)
        return {"query": self.lua.table_from([]), "update": 1, "insert": 100, "scalar": 0}[kind]

    def _event(self, ev, target, payload):
        self.events.append((ev, target, self.to_py(payload) if payload is not None and not isinstance(payload, (str, int, float, bool)) else payload))

    def _http(self, url, body):
        self.http.append((url, pyjson.loads(body)))

    # --- helpers ----------------------------------------------------------------------------
    def player(self, src, cid, first, last, job, level=0):
        self.lua.globals().addPlayer(src, cid, first, last, job, level)

    def fire(self, event, src, arg=None):
        self.lua.globals().fire(event, src, self.to_lua(arg) if isinstance(arg, (dict, list)) else arg)

    def writes(self, table=None):
        out = [s for k, s, _ in self.sql if k in ("update", "insert") ]
        return [s for s in out if table is None or table in s]

    def sent(self, event, target=None):
        return [(t, p) for e, t, p in self.events if e == event and (target is None or t == target)]

    def setjobs(self):
        g = self.lua.globals().setjobs
        return [(g[i]["src"], g[i]["name"], g[i]["grade"]) for i in range(1, len(g) + 1)]


def standard_players(env):
    env.player(1, "CIT1", "Pat", "Citizen", "unemployed", 0)
    env.player(2, "REP0", "Ivy", "Intern", "reporter", 0)
    env.player(3, "REP1", "Jo", "Journalist", "reporter", 1)
    env.player(4, "REP2", "Ed", "Editor", "reporter", 2)
    env.player(5, "CEO1", "Chief", "One", "reporter", 3)
    env.player(6, "CEO2", "Chief", "Two", "reporter", 3)
    env.player(7, "POL1", "Cop", "Officer", "police", 4)
    env.player(8, "UNE1", "Una", "Employed", "unemployed", 0)
