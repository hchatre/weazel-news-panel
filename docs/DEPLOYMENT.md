# Deployment and operations (local PC, FiveM on the same machine)

Untested on a real FiveM server; the commands below were exercised only in a Linux sandbox. Verify on your PC.

## Services
- PostgreSQL 16 (authoritative store). API: `uvicorn app.main:app --host 127.0.0.1 --port 8000` from `core-api`.
- Web: `npm run build && npm run start` in `web`. There is no worker: news reaches players in game because the game server polls the API (see `docs/in-game-news.md`).
- Keep the API bound to 127.0.0.1. The FiveM resource and the web app are the only clients.

## First run
1. Create the database and user. Copy `core-api/.env.example` to `core-api/.env`, fill the secrets (`WEAZEL_JWT_SECRET`, `WEAZEL_BRIDGE_SECRET`, at least 32 random characters each).
2. `pip install -r requirements.txt`, then `alembic upgrade head`.
3. `python -m app.create_admin` for the first administrator.
4. Legacy data: `python -m app.legacy --dry-run`, then run it for real, then `--verify`. The old MySQL stays read-only. Re-run after any use of the old NUI.
5. In `server.cfg` set the same bridge secret as a convar (see `server.cfg.example`). Never put it in committed files.

## Backups (both parts are needed)
- Database: `pg_dump -Fc weazel > weazel-YYYYMMDD.dump`.
- Evidence files: copy the whole `WEAZEL_STORAGE_DIR`. A database restore without the files breaks evidence integrity checks.
- Restore: `pg_restore -d weazel_new weazel.dump`, restore the storage folder, then use the evidence "verify" action on a sample.
- Test a restore before you rely on it.

## Upgrade and rollback
Back up first. `git pull` equivalent, `pip install -r requirements.txt`, `alembic upgrade head`, restart. Roll back by restoring the backup; `alembic downgrade` exists but can drop new data.

## Secrets and rotation
- Rotate `WEAZEL_JWT_SECRET` (logs everyone out) and `WEAZEL_BRIDGE_SECRET` (change API and `server.cfg` together).
- The three Discord webhook URLs in the old `main` history of the GitHub repo are public: delete them in Discord and create new ones.
- Production refuses local auth mode, the mock AI provider and placeholder secrets.

## Health, logs, limits
- The admin Integrations screen shows whether the bridge, in-game news and AI are configured.
- Rate limiters are per process; run one API process.
- Not covered: antivirus or EXIF stripping on uploads, refresh tokens (sessions last 30 minutes), TLS (use a reverse proxy if exposed beyond localhost).
