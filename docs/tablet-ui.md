# In-game tablet and lock screen

`/weazel` now opens a tablet: it slides up on a **lock screen** (in-game time and date, the three newest headlines as notification cards, "Click to open"). Click it, or press Enter or Space, and the lock slides away and the existing newsroom panel opens inside the tablet. The bar at the bottom of the screen locks it again. Esc or the X closes the tablet, and it always reopens locked.

- The clock comes from the game (`GetClock*` natives, refreshed every 2 s while open), so it matches the in-game day and night. In a plain browser it falls back to the computer's clock.
- Headlines are set as text only (never HTML) and come from the same data the Latest page already loads.
- The panel behind the lock screen is hidden from sight, clicks and keyboard until unlocked. Animations are switched off for players with reduced motion.
- Only `html/` (index.html, style.css, script.js) and `client/main.lua` changed. No new permissions, no new server events.

**Tested:** 14 browser-driven NUI tests (5 new: lock first, keyboard unlock and re-lock, text-only headlines, clock updates and reopening locked, Esc on the lock screen) and the existing 58 Lua tests. **Not tested:** on a real FiveM client (CEF), including the in-game clock natives and how the blur and animations perform there.

**Not included:** the new web platform (`web/`) is not shown inside the tablet. It runs on your PC, so other players' game clients cannot reach it. The tablet shows the existing in-game panel; the web platform stays a desk tool.
