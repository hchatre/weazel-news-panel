# Phase 2 — Core platform: architecture, data ownership, local testing

Status: backend and a first frontend are built and tested locally. **Not yet run against a real FiveM server.**
Nothing here has been pushed to GitHub.

## 1. Components

| Part | Path | Role |
|---|---|---|
| Legacy FiveM resource | `server/`, `client/`, `html/` | Hardened in Phase 1. Still the in-game NUI. Untouched by Phase 2 data model. |
| Core API | `core-api/` | FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL. Authoritative store after import. |
| Web app | `web/` | Next.js 14 / React / TypeScript / Tailwind / Lucide. Talks only to the Core API. |
| Legacy importer | `core-api/app/legacy/` | Read-only copy from the old MySQL tables into PostgreSQL. |

## 2. Data ownership

* After a successful import PostgreSQL is the **only** place new data is written. The legacy MySQL tables become a read-only import source and are never modified or dropped by the importer (its connection only needs `SELECT`).
* Until the FiveM bridge exists (Phase 5), the in-game NUI still writes to MySQL. Re-running the importer picks up new legacy rows and refreshes rows that were not edited on the platform. Rows edited on the platform are flagged `platform_modified` and never overwritten (reported instead).
* Imports keep legacy ids, so existing references stay valid; a native row that would collide with a legacy id aborts the whole import with nothing written.
* Authorship: legacy `author` is a display name. It is linked to a platform user only if exactly one user has that name; otherwise it is kept as text (`legacy_author_name`) and never guessed.
* Legacy dossier mapping: `private` → `confidential` (strictest), `public` → `standard`, `police` entry visibility → restricted entry, unknown entry type → `unverified_claim` (never upgraded to a trusted state). Every fallback is listed in the import report.

## 3. Identity and authorisation

Three separate things, deliberately not conflated: **employment grade** (QBCore job/grade) → mapped to **application role** through the configurable `job_grade_mappings` table → plus **per-user permission grants/denies** (deny wins).

* Admins cannot change their own role, cannot act on equal or higher rank, and cannot grant a permission they do not hold.
* Role/permission changes and deactivation bump `token_version`, which invalidates existing tokens immediately.
* Records the user may not see answer **404**, not 403. One shared visibility predicate drives lists, counts, search, dashboard, staff workload and audit, so nothing leaks through an aggregate.
* Investigations: `standard` (permission-based), `restricted` (read-only for non-participants holding `investigation.read_restricted`), `confidential` (participants only — not even administrators). Participant level `read` / `write` / `lead`.
* Sources use pseudonyms. Real identities live in a separate table behind `source.read_identity`; every read is audited; identities never appear in logs, search or lists.
* Editorial review is independent: the author and assignees cannot review or approve their own article. Workflow transitions are data (`workflow_transitions`), so an organisation can change who may do what without code changes (changes are audited).

## 4. Auth modes (`WEAZEL_AUTH_MODE`)

| Mode | Use |
|---|---|
| `local` | One implicit administrator, no login. **Refused when `WEAZEL_ENVIRONMENT=production`.** |
| `password` | Email + password accounts created by an administrator. Rate-limited, indistinguishable failures, bcrypt. |
| `fivem` | Reserved for Phase 5. The API refuses to start with it today. |

## 4b. Environment variables

| Variable | Default | Notes |
|---|---|---|
| `WEAZEL_DATABASE_URL` | local dev URL | PostgreSQL, `postgresql+psycopg2://…` |
| `WEAZEL_ENVIRONMENT` | `development` | `production` enforces a real JWT secret and forbids `local` auth |
| `WEAZEL_AUTH_MODE` | `password` | see above |
| `WEAZEL_JWT_SECRET` | none usable | ≥ 32 random characters. Never commit. |
| `WEAZEL_ACCESS_TOKEN_MINUTES` | 30 | no refresh tokens yet |
| `WEAZEL_CORS_ORIGINS` | `http://localhost:3000` | comma separated |
| `WEAZEL_PUBLIC_READ_ENABLED` | true | `/public/articles`, published only, no internal notes |
| `WEAZEL_LOGIN_MAX_ATTEMPTS` / `_WINDOW_SECONDS` | 5 / 300 | in-memory, single process |
| `NEXT_PUBLIC_API_URL` (web) | `http://127.0.0.1:8000` | API base URL as seen by the browser |

## 5. Local testing on Windows / VS Code (FiveM on the same PC)

1. Install PostgreSQL 16 (keep the default port 5432), Python 3.11+, Node 20+ and Git.
2. In pgAdmin or `psql`: `CREATE USER weazel WITH PASSWORD '<pick one>'; CREATE DATABASE weazel OWNER weazel;`
3. API, in a VS Code terminal:
   ```powershell
   cd core-api
   python -m venv .venv ; .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   $env:WEAZEL_DATABASE_URL = "postgresql+psycopg2://weazel:<password>@127.0.0.1:5432/weazel"
   $env:WEAZEL_AUTH_MODE = "password"
   $env:WEAZEL_JWT_SECRET = "<32+ random characters>"
   alembic upgrade head
   python -m app.seed
   uvicorn app.main:app --port 8000
   ```
4. Create the first administrator (no default account exists):
   ```powershell
   python -m app.create_admin --email you@example.com --name "Your Name"   # prompts for a password, min 12 chars
   ```
   Running it again for the same email resets the password, sets the role to `system_admin` and invalidates existing sessions.
5. Web: `cd web ; copy .env.example .env.local ; npm install ; npm run dev` → http://localhost:3000
6. Legacy import (dry run first, read-only MySQL account):
   ```powershell
   python -m app.legacy --mysql-url "mysql+pymysql://weazel_ro:<pw>@127.0.0.1:3306/<qbcore db>" --dry-run
   python -m app.legacy --mysql-url "mysql+pymysql://weazel_ro:<pw>@127.0.0.1:3306/<qbcore db>"
   python -m app.legacy --mysql-url "…" --verify
   ```
   Create the read-only account with `GRANT SELECT ON <db>.* TO 'weazel_ro'@'127.0.0.1' IDENTIFIED BY '…';`. Back up the database first.
7. Tests: `pytest` in `core-api` (needs a separate empty PostgreSQL database, `WEAZEL_TEST_DATABASE_URL`; optional MariaDB/MySQL for the importer tests, they skip if absent).

## 6. What was tested, and how

| Check | Result |
|---|---|
| API test suite (auth/RBAC 10, articles 18, investigations 19, admin 14, legacy import 10) | 71 passed, real PostgreSQL 16 built by the real Alembic migration |
| Importer against a real MariaDB with the original `install.sql` schema | passed (accents/emoji intact after fixing the connection charset) |
| Mutation check: confidential filter deliberately broken | 3 leakage tests failed as intended, then passed after restoring |
| Browser smoke test of the built web app against the live API (`web/e2e/smoke.py`) | passed |

**Not tested / known limits:** MySQL 8 itself (MariaDB used), a real FiveM server, LB Phone, load/concurrency beyond optimistic-version tests, accessibility audit with a screen reader, RTL layout. Login rate limiting is per process memory. No refresh tokens. The frontend covers dashboard, articles (edit, workflow, revisions, history, comments), investigations (timeline, verification, tasks, sources) and search; staff/role administration, corrections UI, participants UI and evidence are API-only or not built yet and are **not shown** in the UI.

## 7. Permission matrix (generated from `app/permissions.py`)

| Permission | Intern | Journalist | Senior Journalist | Editor | Investigative Editor | Editor-in-Chief / CEO | System Administrator |
|---|---|---|---|---|---|---|---|
| `article.approve` |  |  |  | ✔ |  | ✔ | ✔ |
| `article.archive` |  |  |  | ✔ |  | ✔ | ✔ |
| `article.correct` |  |  |  | ✔ |  | ✔ | ✔ |
| `article.create` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `article.edit.any` |  |  |  | ✔ |  | ✔ | ✔ |
| `article.edit.assigned` |  |  | ✔ | ✔ | ✔ | ✔ | ✔ |
| `article.edit.own` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `article.notes.read` |  |  | ✔ | ✔ | ✔ | ✔ | ✔ |
| `article.publish` |  |  |  | ✔ |  | ✔ | ✔ |
| `article.read` |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `article.review` |  |  |  | ✔ | ✔ | ✔ | ✔ |
| `article.schedule` |  |  |  | ✔ |  | ✔ | ✔ |
| `article.submit` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `audit.export` |  |  |  |  |  |  | ✔ |
| `audit.read` |  |  |  |  |  | ✔ | ✔ |
| `evidence.download` |  |  | ✔ | ✔ | ✔ | ✔ | ✔ |
| `evidence.read` |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `evidence.restrict` |  |  |  |  | ✔ | ✔ | ✔ |
| `evidence.upload` |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `investigation.archive` |  |  |  | ✔ | ✔ | ✔ | ✔ |
| `investigation.contribute` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `investigation.create` |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `investigation.edit` |  |  | ✔ | ✔ | ✔ | ✔ | ✔ |
| `investigation.manage_access` |  |  |  |  | ✔ | ✔ | ✔ |
| `investigation.read` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `investigation.read_restricted` |  |  |  |  | ✔ | ✔ | ✔ |
| `investigation.verify` |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `settings.manage` |  |  |  |  |  |  | ✔ |
| `source.manage` |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `source.read` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `source.read_identity` |  |  |  |  | ✔ | ✔ | ✔ |
| `staff.dismiss` |  |  |  |  |  | ✔ | ✔ |
| `staff.promote` |  |  |  |  |  | ✔ | ✔ |
| `staff.recruit` |  |  |  |  |  | ✔ | ✔ |
| `staff.view` |  |  |  | ✔ | ✔ | ✔ | ✔ |

**Default workflow transitions**

| From | To | Permission | Independent reviewer | Note required |
|---|---|---|---|---|
| idea | draft | `article.edit.own` |  |  |
| draft | submitted | `article.submit` |  |  |
| revision_requested | submitted | `article.submit` |  |  |
| submitted | in_review | `article.review` | yes |  |
| in_review | revision_requested | `article.review` | yes | yes |
| in_review | approved | `article.approve` | yes |  |
| approved | scheduled | `article.schedule` |  |  |
| approved | published | `article.publish` |  |  |
| scheduled | published | `article.publish` |  |  |
| published | corrected | `article.correct` |  | yes |
| draft | archived | `article.archive` |  |  |
| published | archived | `article.archive` |  |  |
| corrected | archived | `article.archive` |  |  |
