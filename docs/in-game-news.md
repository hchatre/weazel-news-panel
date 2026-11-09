# In-game news delivery (replaces Discord webhooks)

Modeled on the DOJ tablet: **pull, not push**. Nothing is posted to Discord and the API never connects to your game server.

## How it works
1. Every `weazel_news_poll_seconds` (default 20, minimum 5) the game server (`fivem/server/bridge.lua`) sends the API a signed request (`POST /api/v1/bridge/news/poll`, same HMAC bridge secret as staff sync) with the citizen ids of the players who are online (taken from QBCore, never from a client) and a cursor.
2. The API answers with:
   - `broadcast`: articles published since the cursor (status published/corrected only, same rule as the public API). Title and id only.
   - `personal`: notifications created since the cursor for online staff (assigned, approved, awaiting review...). Title only.
3. The game server shows each item as an **LB Phone notification** when the player has a phone equipped, otherwise as an **on-screen notice** (`QBCore:Notify`).

## Rules that are tested
- A bad or missing signature is rejected. The first poll only returns a cursor (a restart never replays old news).
- Offline players get nothing; malformed citizen ids are ignored; personal notices go only to their owner.
- Drafts and articles that are no longer public are never broadcast. No body, summary or internal notes leave the API.
- If the API is down the cursor is kept, so the next successful poll catches up (at most 20 items per poll).

## Limits (not done)
- There is **no Discord fallback**. The DOJ app has none either (Discord is only used there for login and roles). If you want a Discord message when nobody is online, say so: it would need a Discord bot token and is a separate feature.
- Notifications are not retried per player; a player who is offline when something is published does not see a popup (they see it in the web app or the LB Phone news app).
- Corrections do not trigger a new popup.
- The old in-game popup for articles published through the old NUI is unchanged.
- Not tested on a real FiveM server or LB Phone 2.8.1.

## Settings
`server.cfg`: `weazel_api_url`, `weazel_bridge_secret`, optional `weazel_news_poll_seconds`. API: `WEAZEL_NEWS_POLL_MAX_ITEMS` (default 20). The old `weazel_webhook_*` convars and `WEAZEL_DISCORD_*` variables are ignored.
