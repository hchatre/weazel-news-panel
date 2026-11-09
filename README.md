# qb-weazel-ui

**Weazel News tablet for QBCore.** The newsroom itself is the web app (articles, investigations, evidence, staff, AI workspace).
This FiveM resource only puts that web app on a tablet inside the game, signed in as the character you are playing.

- `/weazel`, or the **Weazel News** icon on the LB Phone, opens a tablet on a lock screen. Tap it and the web newsroom loads inside the tablet.
- You are signed in as your **character**. The game server reads who you are and what job you have from QBCore; your own client never says who it is.
- **Every character gets an account**, whatever their job:
  - job `reporter`, by grade: 0 journalist, 1 reporter, 2 director, 3 chief, 4 administrator (editable in the web app under Admin, Job mapping);
  - anyone else (unemployed, another job, a dismissed reporter): **Freelancer**, who can write and submit articles and nothing else.
  - The role follows the job: a promotion or dismissal in game takes effect the next time the tablet is opened (or immediately for online players).
- Escape (or the bar at the bottom of the tablet) closes it. News published on the platform reaches online players as an LB Phone notification, or an on-screen notice.

## Requirements

- `qb-core`, `oxmysql` (only to read the QBCore `players` table for the staff sync). `lb-phone` is optional.
- The Weazel API and web app running and reachable (see `docs/DEPLOYMENT.md` and `docs/WINDOWS-FIRST-RUN.md`).
- The web app must be reachable **from the players' PCs** at `WEAZEL_PUBLIC_BASE_URL` (the tablet loads it from the player's own game client).

## Install

1. Put the folder in `resources/`, then `ensure` it after `oxmysql`, `qb-core` and `lb-phone`.
2. Copy the convars from `server.cfg.example` into your `server.cfg`. `weazel_bridge_secret` must equal `WEAZEL_BRIDGE_SECRET` on the API.
3. Nothing to import: this resource has no database tables. The old panel's tables are not used and are never dropped.
   Old articles and dossiers come across with the one-time importer in `core-api` (see `docs/phase-2-core-platform.md`).

## Tests

```
pip install lupa playwright
python3 -m unittest discover -s tests/lua    # server and client logic with stubbed QBCore / LB Phone
CHROME_PATH=/path/to/chrome python3 -m unittest discover -s tests/nui   # the tablet page in headless Chrome
```
These do not replace testing in a real FiveM server.
