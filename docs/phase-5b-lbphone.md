# Phase 5b — LB Phone app (read-only news reader)

Status: written and unit-tested in isolation. **Never loaded into LB Phone (2.8.1 or any version).** Treat it as untested in-game until you run the checklist below.

## What it is
A custom LB Phone app, "Weazel News": a feed of published stories and a story reader. **Read-only**: no likes, comments or posting (the old comment/like features lived in the legacy MySQL tables and are not part of this app).

Data path: the phone page asks the game client (`fetchNui`) → client asks the server → the **server** reads `GET /api/v1/public/articles` (and `/{id}`) from the Weazel API → the server forwards only a fixed list of fields to that one player. The player's client never supplies a URL; it can only ask for "page N" or "story N".

Files: `client/lbphone.lua`, `server/lbphone.lua`, `html/lbphone/{index.html,app.js,app.css}`; entries added to `fxmanifest.lua`. The old `client/phone.lua` / `html/phone.*` are untouched and still disabled: they were not a real LB Phone custom app (they took over the main NUI), so I did not reuse them.

## Safety properties (tested)
* Article text is shown with `textContent` only; hostile titles, authors, bodies and correction notes (`<img onerror>`, `<script>`, `<svg onload>`, iframes) stay literal text. The page contains no `innerHTML`/`eval`/URLs (a test fails if one appears).
* The server forwards an allow-list of fields; anything else the API returns (images, internal fields, future additions) is dropped; text is length-capped.
* Story ids and page numbers are validated as numbers; a client cannot alter the request path.
* 1.5 s cooldown per player; unanswered requests close after 8 s; API errors become short messages, never details.
* Needs no secret (public endpoint) and writes nothing. It shows only what the API already publishes to anyone: `WEAZEL_PUBLIC_READ_ENABLED=false` turns the phone feed (and the public API) off.

## What is UNVERIFIED (read this)
I could only reach LB Phone's public "Custom Apps" documentation page. It does not give the `AddCustomApp` export's exact signature, the `fxmanifest` requirements, or anything specific to 2.8.1.
1. **The registration call.** `client/lbphone.lua` calls `exports['lb-phone']:AddCustomApp({ identifier, name, description, developer, defaultApp, ui, icon })`, using the field names from the documentation's `Config.CustomApps` table plus `identifier`. If 2.8.1 expects different fields, registration fails; the script catches that and prints `[weazel] LB Phone app NOT registered: <reason>` in the server/client console instead of crashing.
2. **How the page gets `fetchNui`.** The docs say the phone provides `fetchNui` (and others) to app pages. The page uses it as a plain global. If your version injects it differently, the feed will show "News is unavailable".
3. **The `ui` path and icon URL** (`<resource>/html/lbphone/index.html`, `https://cfx-nui-<resource>/html/logo.png`) follow the documentation's example format.
4. **Theme/size.** The page follows the documented `data-theme` light/dark attribute; layout was only tested in a desktop browser, not in the phone frame.
Alternative if registration fails: add the app to `Config.CustomApps` in `lb-phone/config/config.lua` with the same fields (the documentation's other registration route) and point `ui` at this page.

## In-game checklist (please run and tell me what you see)
1. API and `server.cfg` convars set (`weazel_api_url`), `lb-phone` started before this resource or restart both.
2. Server console should print `[weazel] LB Phone app registered`. If it prints `NOT registered`, send me that line.
3. Open the phone: "Weazel News" should be listed (defaultApp, no download).
4. Open it: feed of published stories appears; open one; Back returns to the same page; "Older/Newer" work.
5. Stop the API: the app should say the newsroom is unavailable, not hang.
6. Publish a new story on the web app: it appears after reopening the app (no live push in this version).

## Not built
Likes/comments, notifications on the phone, live updates, images, in-phone writing or editing, opening a story from a notification.
