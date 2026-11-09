# In-game tablet and lock screen

`/weazel` now opens a tablet: it slides up on a **lock screen** (in-game time and date, the three newest headlines as notification cards, "Click to open"). Click it, or press Enter or Space, and the lock slides away and the existing newsroom panel opens inside the tablet. The bar at the bottom of the screen locks it again. Esc or the X closes the tablet, and it always reopens locked.

- The clock comes from the game (`GetClock*` natives, refreshed every 2 s while open), so it matches the in-game day and night. In a plain browser it falls back to the computer's clock.
- Headlines are set as text only (never HTML) and come from the same data the Latest page already loads.
- The panel behind the lock screen is hidden from sight, clicks and keyboard until unlocked. Animations are switched off for players with reduced motion.
- Only `html/` (index.html, style.css, script.js) and `client/main.lua` changed. No new permissions, no new server events.

**Tested:** 14 browser-driven NUI tests (5 new: lock first, keyboard unlock and re-lock, text-only headlines, clock updates and reopening locked, Esc on the lock screen) and the existing 58 Lua tests. **Not tested:** on a real FiveM client (CEF), including the in-game clock natives and how the blur and animations perform there.

**Not included:** the new web platform (`web/`) is not shown inside the tablet. It runs on your PC, so other players' game clients cannot reach it. The tablet shows the existing in-game panel; the web platform stays a desk tool.

## The tablet (current design)

The old built-in panel (its NUI pages, `server/main.lua`, its MySQL tables' schema, the in-phone news reader) was **removed**. The resource is now only a tablet around the web app. Existing MySQL tables are untouched; only the importer still reads them.

- **Open.** `/weazel`, or the LB Phone app icon: `onUse` closes the phone (`ToggleOpen(false, true)`), then opens the tablet. Anyone alive with a character can open it; what they may do is decided by the web app's role for their character.
- **Unlock = sign in.** Tapping the lock screen makes the client send `unlock`. The server looks up the character itself (citizen id, name, job and grade from QBCore, never from the client), the API brings that character's account up to date (creating it on first use) and mints a single-use ticket, and the tablet loads `…/fivem-login?ticket=…` in a frame. The ticket is requested on tap, not on open, so it cannot expire while the lock screen is showing. Re-locking and unlocking again reuses the loaded page.
- **Role from job.** Mapped job and grade give the mapped role (default: `reporter` 0 journalist, 1 senior journalist, 2 editor, 3 editor-in-chief, 4 system administrator). Everyone else gets the **freelancer** role. `WEAZEL_FIVEM_DEFAULT_ROLE=` (empty) restores the strict behaviour: unmapped characters get no account.
- **Failures** stay on the lock screen with a plain message ("not reachable", "no newsroom account", "could not be loaded") and a retry on the next tap. The page inside the frame says "ready" when it starts; if it never does within 10 s, the tablet returns to the lock screen and the client logs it.
- **Escape / close.** Inside the frame, Escape is sent to the tablet with `postMessage`, which closes it.
- **Players must be able to reach the web app.** The frame is loaded by each player's own game client, so `WEAZEL_PUBLIC_BASE_URL` and the API must be reachable from their PCs (a public HTTPS address on a real server). `http://127.0.0.1:3000` only works for the player on the same PC as the web app.
- **Web look.** The web panel uses the tablet's look: navy night with a blue glow and a red band, frosted rounded panels with a red edge, Montserrat, pill tags, rounded buttons.

Tested: the tablet page in Chrome, client and server Lua with stubs, the API's account rules (pytest), and a real run where the tablet page loaded a real one-time ticket in its frame. **Not tested:** real FiveM/CEF (an `http` frame inside the `https` NUI page), real LB Phone 2.8.1 (`onUse`, `keepOpen`, `ToggleOpen` follow the published docs only; an error from inside lb-phone's own `custom.lua` was reported on the first try and is still open).
