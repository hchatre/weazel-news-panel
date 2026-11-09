"""Runs the real client/main.lua with the FiveM natives stubbed: what /weazel, the phone, the lock screen and Escape do.
It is NOT a FiveM client: no real NUI focus, no real game clock."""
import os
import unittest

from lupa import LuaRuntime

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

PRELUDE = r"""
local py = ...
CMD, H, NUI, SENT, SERVER, FOCUS, CONTROL = {}, {}, {}, {}, {}, {}, {}
dead, escape, threads = false, false, {}
function RegisterCommand(n, fn) CMD[n] = fn end
function AddEventHandler(n, fn) H[n] = fn end
function RegisterNetEvent(n, fn) if fn then H[n] = fn end end
function RegisterNUICallback(n, fn) NUI[n] = fn end
function SendNUIMessage(t) SENT[#SENT + 1] = t end
function TriggerServerEvent(n, ...) SERVER[#SERVER + 1] = n end
function TriggerEvent(n, ...) if H[n] then H[n](...) end end
function SetNuiFocus(a, b) FOCUS[#FOCUS + 1] = tostring(a) end
function SetPlayerControl(p, on) CONTROL[#CONTROL + 1] = tostring(on) end
function PlayerId() return 1 end
function PlayerPedId() return 1 end
function IsEntityDead() return dead end
function IsControlJustPressed() return escape end
function GetClockHours() return 21 end
function GetClockMinutes() return 47 end
function GetClockDayOfWeek() return 1 end
function GetClockDayOfMonth() return 9 end
function GetClockMonth() return 10 end
function GetCurrentResourceName() return 'weazel-test' end
function exports(...) end
function print(...) py.print(...) end
function CreateThread(fn) threads[#threads + 1] = fn end   -- threads only run when a test runs them
function Wait() end
"""


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.prints = []
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(PRELUDE, self.lua.table_from({"print": lambda *a: self.prints.append(" ".join(map(str, a)))}))
        with open(os.path.join(ROOT, "client", "main.lua"), encoding="utf-8") as f:
            self.lua.execute(f.read())
        self.g = self.lua.globals()

    def sent(self):
        return [dict(t.items()) for t in self.g.SENT.values()]

    def server(self):
        return list(self.g.SERVER.values())

    def run_escape_thread(self):
        # the Escape thread is the second one created by open; make IsControlJustPressed true for one pass then let it end
        self.lua.execute("""
            escape = true
            for i = 1, #threads do
                local waits = 0
                Wait = function() waits = waits + 1; if waits > 1 then error('stop') end end   -- one pass of each loop, then stop it
                pcall(threads[i])
            end
            escape = false""")

    def test_weazel_opens_the_tablet_with_the_game_clock_and_takes_focus(self):
        self.g.CMD["weazel"]()
        s = self.sent()
        self.assertEqual(s[0]["action"], "open")
        self.assertEqual(dict(s[0]["clock"].items()), {"h": 21, "m": 47, "dow": 1, "d": 9, "mo": 10})
        self.assertEqual((list(self.g.FOCUS.values()), list(self.g.CONTROL.values())), (["true"], ["false"]))
        self.g.CMD["weazel"]()   # already open: nothing happens twice
        self.assertEqual(len(self.sent()), 1)

    def test_nobody_dead_can_open_it_and_the_phone_event_opens_it_the_same_way(self):
        self.lua.execute("dead = true")
        self.g.H["weazel:client:requestOpen"]()
        self.assertEqual(self.sent(), [])
        self.lua.execute("dead = false")
        self.g.H["weazel:client:requestOpen"]()
        self.assertEqual(self.sent()[0]["action"], "open")

    def test_unlock_asks_the_server_for_a_ticket_only_while_open_and_sends_no_identity(self):
        self.g.NUI["unlock"]({}, lambda r: None)
        self.assertEqual(self.server(), [])   # closed: ignored
        self.g.CMD["weazel"]()
        self.g.NUI["unlock"]({"citizenid": "SOMEONEELSE", "job": "reporter"}, lambda r: None)
        self.assertEqual(self.server(), ["weazel:server:ticket"])   # the event carries no arguments at all

    def test_the_server_answer_reaches_the_page_only_while_open(self):
        self.g.H["weazel:client:loadWeb"]("http://x/fivem-login?ticket=T")
        self.assertEqual(self.sent(), [])
        self.g.CMD["weazel"]()
        self.g.H["weazel:client:loadWeb"](None, "noaccount")
        last = self.sent()[-1]
        self.assertEqual((last["action"], last.get("url"), last["reason"]), ("loadWeb", None, "noaccount"))

    def test_close_releases_focus_and_controls_and_escape_closes(self):
        self.g.CMD["weazel"]()
        self.g.NUI["close"]({}, lambda r: None)
        self.assertEqual((list(self.g.FOCUS.values()), list(self.g.CONTROL.values())), (["true", "false"], ["false", "true"]))
        self.assertEqual(self.sent()[-1]["action"], "close")
        self.g.NUI["close"]({}, lambda r: None)   # closing twice does nothing more
        self.assertEqual(len(self.sent()), 2)
        self.g.CMD["weazel"]()
        self.run_escape_thread()
        self.assertEqual(self.sent()[-1]["action"], "close")

    def test_stopping_the_resource_gives_the_player_back_control(self):
        self.g.CMD["weazel"]()
        self.g.H["onResourceStop"]("weazel-test")
        self.assertEqual((list(self.g.FOCUS.values())[-1], list(self.g.CONTROL.values())[-1]), ("false", "true"))

    def test_a_page_that_never_starts_is_only_logged(self):
        self.g.NUI["webFailed"]({}, lambda r: None)
        self.assertIn("did not load", self.prints[-1])


if __name__ == "__main__":
    unittest.main()
