# In-game tablet and lock screen

`/weazel` now opens a tablet: it slides up on a **lock screen** (in-game time and date, the three newest headlines as notification cards, "Click to open"). Click it, or press Enter or Space, and the lock slides away and the existing newsroom panel opens inside the tablet. The bar at the bottom of the screen locks it again. Esc or the X closes the tablet, and it always reopens locked.

- The clock comes from the game (`GetClock*` natives, refreshed every 2 s while open), so it matches the in-game day and night. In a plain browser it falls back to the computer's clock.
- Headlines are set as text only (never HTML) and come from the same data the Latest page already loads.
- The panel behind the lock screen is hidden from sight, clicks and keyboard until unlocked. Animations are switched off for players with reduced motion.
- Only `html/` (index.html, style.css, script.js) and `client/main.lua` changed. No new permissions, no new server events.

**Tested:** 14 browser-driven NUI tests (5 new: lock first, keyboard unlock and re-lock, text-only headlines, clock updates and reopening locked, Esc on the lock screen) and the existing 58 Lua tests. **Not tested:** on a real FiveM client (CEF), including the in-game clock natives and how the blur and animations perform there.

**Not included:** the new web platform (`web/`) is not shown inside the tablet. It runs on your PC, so other players' game clients cannot reach it. The tablet shows the existing in-game panel; the web platform stays a desk tool.

## Phase 8b: the tablet shows the web newsroom (same logic as the DOJ tablet)

- **Phone icon.** The LB Phone app no longer has a page inside the phone. Its `onUse` closes the phone (`ToggleOpen(false, true)`), then asks the tablet to open. `/weazel` does the same. Both go through `weazel:server:openPanel`, so the server still decides who may open it.
- **Unlock = sign in.** Tapping the lock screen makes the client send `unlock`. The server looks up the character itself (never a value from the client), mints a one-time ticket, and returns `…/fivem-login?ticket=…`. The tablet loads that page in a frame. The ticket is requested on tap, not on open, so it cannot expire while the lock screen is showing. Re-locking and unlocking again reuses the loaded page.
- **Fallback.** If the web app is not set up, the character has no newsroom account, or the API is down, the tablet shows the older built-in panel instead of a dead end.
- **Escape / close.** Inside the frame, Escape is sent to the tablet with `postMessage`, which closes it.
- **Size.** The tablet now fills about 98% of the screen width / 95% of the height at 16:10.
- **Players must be able to reach the web app.** The frame is loaded by each player's own game client, so `WEAZEL_PUBLIC_BASE_URL` and the API must be reachable from their PCs (a public HTTPS address on a real server). `http://127.0.0.1:3000` only works for the player on the same PC as the web app.
- **Web look.** The web panel now uses the tablet's look: navy night with a blue glow and a red band, frosted rounded panels with a red edge, Montserrat, pill tags, rounded buttons.

Tested: NUI page in Chrome (frame loads only http(s) URLs, falls back, closes, Escape message), Lua with stubs (ticket goes to the asking player only, cooldown, fallbacks, phone closes before the tablet opens), and a real run where the tablet page loaded a real one-time ticket in its frame and landed on the dashboard. **Not tested:** real FiveM/CEF (mixed `https` NUI page with an `http` frame), real LB Phone 2.8.1 (`onUse`, `keepOpen`, `ToggleOpen` follow the published docs only).
