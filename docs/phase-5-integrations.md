# Phase 5 — FiveM bridge, staff sync (Discord outbox: REMOVED, see `in-game-news.md`)

> **Superseded:** Discord publishing, the outbox worker and `WEAZEL_DISCORD_*` settings were removed in Phase 6. News is delivered in game by polling. Section 4 and the Discord test rows below describe code that no longer exists.

Status: implemented and tested locally. **Never run inside a real FiveM server or against real Discord.** LB Phone is **not implemented** (see the end). Not pushed.

## 1. How in-game sign-in works

1. The player types `/newsroom` in the game. The **server** (`server/bridge.lua`) looks up that player's `source` in QBCore to get their citizen id. Nothing the client sends is used as identity.
2. `server/bridge.js` calls the API (`POST /api/v1/bridge/session`) with a signed request. The API answers with a one-time ticket and a URL.
3. The server sends that URL to that player only, in chat. They open it in a browser on the same PC (valid ~60 seconds, single use).
4. The web page exchanges the ticket for a normal session token (`POST /api/v1/auth/fivem-exchange`) and removes the ticket from the address bar.

Why a link and not an in-game page: FiveM's NUI cannot hand a session to the PC's browser, and the web app is a separate site. This keeps the secret on the server and puts only a short-lived single-use ticket in front of the player.

## 2. Request signing (game server → API)

`HMAC-SHA256(secret, METHOD \n PATH \n TIMESTAMP \n NONCE \n SHA256(body))`, sent as `X-Weazel-Timestamp`, `X-Weazel-Nonce`, `X-Weazel-Signature`.

| Threat | Defence | Test |
|---|---|---|
| Forged request / wrong secret | signature compared in constant time | yes |
| Body tampering | body hash is signed | yes |
| Request re-aimed at another endpoint | the path is signed | yes |
| Replay of a captured request | nonce stored; second use refused. Old nonces purged | yes |
| Stale or future-dated capture | timestamp must be within `WEAZEL_BRIDGE_MAX_SKEW_SECONDS` (60) | yes |
| Attacker fills the nonce table | only a correctly signed request can consume a nonce | yes |
| Learning from error messages | every rejection is the same 401 | yes |
| Player asks for someone else's ticket | citizen id is supplied by the server, never by a client; the endpoint needs a valid signature | by design; client cannot reach the secret |
| Ticket theft/reuse | only its hash is stored; single atomic claim; 60 s expiry; revoked if the account is deactivated in between; ticket-exchange attempts are rate limited | yes |
| Secret exposure | read from `weazel_bridge_secret` convar on the server only; never sent to clients or NUI; never returned by any endpoint or shown in the admin page | yes (no secret in API output / page) |
| Remote kill switch | none exists | — |

The Node client and the Python API were tested against each other (a real API process, the real `bridge.js` under Node): signatures match byte for byte.

## 3. Staff sync (QBCore → platform)

* QBCore is authoritative for **employment**. Employment maps to an **application role** through the configurable job/grade table. Individual permissions are separate.
* On `/newsroom` setup, on every hire/promotion/dismissal of an online player (`QBCore:Server:OnJobUpdate`) and every 10 minutes, the server reports staff. The 10-minute report also includes everyone the platform already manages (`GET /bridge/staff-ids`), so a dismissal made while the player was offline is still noticed.
* Rules: a player with a mapped job gets an account (no password, ticket login only) or an updated one; a role change ends their old sessions at once; a player reported with an unmapped job is deactivated and their sessions end; if they are hired again they are reactivated, but **only** if a previous sync (not a person) deactivated them. Players missing from a report are left alone. Accounts created locally (administrators) are never touched. A role set by hand by an administrator is locked and the sync stops changing it (it still updates the employment mirror). Legacy-import stubs are matched by citizen id and adopted, not duplicated.

## 4. Discord

* Off unless `WEAZEL_DISCORD_WEBHOOK_PUBLISH` is set (environment only; the API refuses anything that is not a Discord webhook URL, and never returns it).
* Publishing an article (or correcting one) queues a message **in the same transaction**; a worker (`python -m app.worker`) delivers it. Discord being down never blocks or fails publication.
* Only public facts are sent: title, short summary, author name, link. Never article body, internal notes, sources, evidence or anything from investigations.
* `@everyone`, `@here` and user mentions cannot ping (`allowed_mentions: none` plus escaping).
* One message per event (unique key). Retry with exponential backoff (30 s, 60 s, … up to 1 h), Discord's own `retry_after` is honoured, network errors retry, 4xx (bad webhook) stop immediately, and after `WEAZEL_DISCORD_MAX_ATTEMPTS` (6) the message is marked failed. Failed messages show in **Integrations** (administrators) with a Retry button. A delivered message is never resent, even after a crash (committed per message). Two workers cannot take the same message (row locking).
* **Do not enable both** this and the old in-game webhooks (`weazel_webhook_publish_*` in `server.cfg`) for the same channel, or every article is posted twice. The old convars keep working for the legacy NUI.

## 5. Setup (same Windows PC)

1. API environment: `WEAZEL_AUTH_MODE=fivem`, `WEAZEL_BRIDGE_SECRET=<32+ random characters>`, `WEAZEL_PUBLIC_BASE_URL=http://localhost:3000`, plus the earlier variables. Optional: `WEAZEL_DISCORD_WEBHOOK_PUBLISH`.
2. `server.cfg`: `set weazel_api_url "http://127.0.0.1:8000"` and `set weazel_bridge_secret "<same value>"`. Keep `server.cfg` out of git.
3. Check **Settings → job mappings** (defaults: reporter 0–3 → Intern, Journalist, Editor, Editor-in-Chief; adjust to your grades).
4. Run `alembic upgrade head`, start the API, the web app and, if you use Discord, `python -m app.worker` in its own terminal.
5. In game: `/newsroom`.
`AUTH_MODE=fivem` still allows password login for administrators created with `python -m app.create_admin`.

## 6. Tested / not tested

| Tested | How |
|---|---|
| Signature, replay, skew, tamper, path binding, ticket lifecycle, staff-sync rules, role lock, dismissal, reactivation, payload validation | 20 API tests |
| Node client ↔ real API process | 4 tests |
| Lua command/event logic (ticket goes to that player only, cooldown, batching of 500, dismissal while offline, bare-number grade) | 6 tests in the embedded-Lua harness (found and fixed a crash on bare-number grades) |
| Outbox retry/backoff/dead/dedupe, Discord response handling, no mentions, no secrets | tests with a simulated Discord |
| Browser: ticket sign-in, single use, URL stripped, hidden menu, admin page without secrets | Playwright |
| Deliberately broken checks all caught | signature, timestamp, nonce, single-use, role lock, local-account protection, mentions, retry policy, Node canonical form |

**Not tested:** a real FiveM server (real `exports` between Lua and JS, `QBCore:Server:OnJobUpdate` payload shape, oxmysql behaviour with your `players` table, FiveM's Node runtime), real Discord, a reverse proxy changing the request path (the signed path must equal the path the API sees), clock drift between game server and API beyond 60 s (same PC: none).

## 7. Known limits
* The ticket link is shown in chat; anyone who can read that player's screen within 60 s could use it. It is single-use and short-lived, not secret from the person it is for.
* Sessions last `WEAZEL_ACCESS_TOKEN_MINUTES` (30); there are no refresh tokens, so a player runs `/newsroom` again after expiry.
* The in-memory rate limiters are per API process.
* Only a `publish` Discord channel exists. No Discord login, no Discord role sync, no moderation/log channel.
* The old in-game NUI still writes to the legacy MySQL tables; re-run the importer to bring that data across (until the NUI is moved onto the API, which is not built).

## 8. LB Phone
A read-only LB Phone app was added afterwards: see `docs/phase-5b-lbphone.md`. It has **not** been loaded into LB Phone; its registration call is unverified against 2.8.1 and the document lists exactly what to check in game.
