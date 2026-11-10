# Weazel News Intelligence System

A newsroom platform for a FiveM QBCore roleplay server: articles with an editorial workflow, investigations, evidence, staff and roles, an AI workspace (suggestions only), and a tablet inside the game that shows the web app signed in as the character you play.

| Folder | What it is |
|---|---|
| `core-api/` | FastAPI + PostgreSQL API: accounts, roles, workflow, evidence, audit, the signed FiveM bridge, the one-time importer for the old panel's data. |
| `web/` | Next.js web app (English / French). |
| `fivem/` | The FiveM resource: only the tablet (lock screen, then the web app in a frame), the LB Phone icon, and the bridge to the API. Copy this folder into your server's `resources`. |
| `docs/` | Deployment, Windows first run, security review, phase notes, tablet and in-game news. Start with `docs/WINDOWS-FIRST-RUN.md` and `docs/DEPLOYMENT.md`. |

Characters: any character can open the newsroom. Reporter grades map to newsroom roles (editable in the web app); everyone else is a Citizen. Details in `fivem/README.md` and `docs/tablet-ui.md`.

Tests: `core-api` (`pytest`), `fivem/tests` (Lua and tablet page), `web/e2e` (browser). None of them replaces testing in a real FiveM server.
