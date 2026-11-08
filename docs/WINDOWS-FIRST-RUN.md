# Windows + VS Code first run (local PC, FiveM on the same machine)

Written from a Linux sandbox. Not run on Windows. Fix any command that differs and tell me.

## Install once
PostgreSQL 16, Python 3.12+, Node 20+, Git, VS Code. Optional: Ollama for local AI.

## 1. Database (PowerShell, in psql as postgres)
    CREATE USER weazel WITH PASSWORD 'choose-one';
    CREATE DATABASE weazel OWNER weazel;

## 2. API
    cd core-api
    py -m venv .venv ; .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env      # fill DATABASE_URL, JWT and BRIDGE secrets (>=32 chars), STORAGE_DIR
    alembic upgrade head
    python -m app.create_admin
    uvicorn app.main:app --host 127.0.0.1 --port 8000
For a dry local try-out only, set WEAZEL_ENVIRONMENT=development and WEAZEL_AUTH_MODE=password.

## 3. Import the old news (optional)
    python -m app.legacy --dry-run   # read the report, then run without the flag, then --verify
Needs read access to the old MySQL (see the importer's --help for connection settings).

## 4. Web
    cd web ; npm install ; npm run dev     # http://localhost:3000

## 5. FiveM
Copy the resource folder into `resources`, `ensure weazel-news-panel`, put the same bridge secret in server.cfg (see `server.cfg.example`), restart. Then walk through the in-game checklist in `docs/phase-5b-lbphone.md` (LB Phone 2.8.1, unverified).

## 6. In-game news
Nothing to run. Once the resource has the bridge secret, the game server polls the API every 20 s and shows new articles to online players (LB Phone notification, or an on-screen notice). See `docs/in-game-news.md`.

## 7. Tests
    pytest        # needs Postgres; the Lua and browser tests need extra tools, see docs/phase-1-audit.md
