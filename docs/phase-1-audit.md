# Weazel News: Phase 1 audit and plan

Method: static read of every file in `hchatre/weazel-news-panel` (HEAD `5e790bf`, shallow clone) and of the DOJ reference architecture (`hchatre/doj-intelligence-system`, HEAD `239b9d0`). **Nothing was executed.** No FiveM server, MySQL, or game client was available, so every finding below is from reading code, not from reproducing it. Findings marked "chain" are inferred from how NUI and server code interact and should be confirmed in-game.

## 1. What exists

| Path | Lines | Role |
|---|---|---|
| `server/main.lua` | 1017 | All server logic: 30 `RegisterNetEvent` handlers, Discord, notifications |
| `client/main.lua` | 234 | `/weazel` command, NUI focus, thin NUI-callback-to-server-event relay |
| `html/index.html`, `script.js`, `style.css` | 224 / 654 / 586 | Panel UI (home, drafts, pending, create, dossiers, admin) |
| `client/phone.lua`, `html/phone.*` | 95 / 240+ | Phone feed app, **disabled** in `fxmanifest.lua` |
| `install.sql`, `qb-weazel.sql` | 72 / 113 | Schema (clean version, and a HeidiSQL dump with `CREATE DATABASE qbcore`) |
| `uploads/1_1770660270.png` | 0 bytes | Stray empty file, unused |

Tables: `rp_articles`, `article_likes`, `article_comments`, `rp_dossiers`, `rp_dossier_entries`. Dump counters (`AUTO_INCREMENT`) imply roughly 18 articles, 18 dossiers, 14 entries, 4 comments, 4 likes have existed. Real data volume is small, so migration risk is about correctness, not scale. The dump has no rows; migration must be rehearsed on a real export.

### Feature reality check

| Feature | Status |
|---|---|
| Articles: draft, pending, published, delete | Works in code. No edit after submit, no revisions, no corrections |
| Likes, comments (150 chars) | Works, but 150-char limit is client-side only |
| Dossiers + timeline (rumour/confirmed/denied) | Works. Most schema columns unused (see 4) |
| Recruit / grade / fire | Works, with serious validation gaps (see 2) |
| Published-article notification, Discord post | Works. Webhooks hard-coded |
| Image upload | **Does not exist.** README describes lb-upload config that is not in the code. Only a manual URL field |
| Phone app | **Does not work.** Disabled in manifest. `client/phone.lua` triggers `weazel:server:getPhoneFeed`, which no server handler registers. It also does not use an LB Phone export, so the target phone is unknown |
| Permissions | Four grades (0-3) hard-coded in `getGradeName`, NUI, and server checks. Job name `reporter` only; NUI also checks `"weazel"`, which the server never sends |

## 2. Security findings

### Critical

1. **Three Discord webhook URLs are hard-coded in `server/main.lua` (lines 6-8) in a public repository.** Treat them as compromised. Anyone can post to those channels now. Deleting them from the file does not help; they must be **deleted and re-created in Discord**. My clone is depth 1, so I cannot see whether older commits held others.
2. **Stored XSS in the NUI, with a plausible privilege-escalation chain.** `script.js` writes server data into `innerHTML` unescaped: article title and content (`createArticleCard`), notification title/content/author/image (`showArticleNotification`), comment text and author (`renderComments`), timeline content, admin names. The notification image is also interpolated into a CSS `url('...')`. Chain: `addComment` has no job check and the panel opens for any player, so any player can post a comment containing HTML. When a grade-3 CEO opens that article, the payload runs inside the CEO's NUI and can call the CEO's NUI callbacks (`fire`, `setGrade`, `recruit`, `deleteArticle`, `approvePending`). The server then sees the CEO as `source`, so its checks pass. The 150-character limit is not a barrier for a short payload. `index.html` sets no CSP.
3. **`setGrade` and `fire` act on any citizen id, not just journalists.** Online: `SetJob("reporter", n)` converts any player into a reporter. Offline: the code rewrites the `job` JSON in `players` for any `citizenid` without checking their current job, so a CEO can demote, fire, or change the grade of a police chief or anyone else. `newGrade` is not validated (any number or string). Nothing stops self-promotion, demoting another CEO, or firing yourself.

### High

4. **`getArticle` has no status or role check.** Any player can fetch any article id, including drafts and pending, and the response includes comment `citizenid`s.
5. **`approvePending` re-broadcasts non-pending articles.** The `UPDATE` is conditional on `status='pending'`, but the following `SELECT`, in-game notification to all players, and Discord post run for any id. Calling it with a draft id leaks that draft to every player and to Discord.
6. **Ownership is by author display name, not citizenid.** `updateDraft`, `deleteDraft`, `publishDraft` compare `author` to the character name. Names can collide or change. `rp_articles` has no author citizenid.
7. **No server-side validation on most handlers.** Missing or non-string `title`, `content`, `comment`, `data.status`, `newType`, `id` cause SQL errors or Lua errors (`data.content:sub(...)`). `addEntry` and `changeEntryType` accept arbitrary type strings (`entry_type` is `varchar(50)`). No length caps except client-side comments. No rate limiting on likes, comments, drafts.
8. **`recruit` takes a client-supplied server id** and overwrites the target's job without consent or a check of their current job.
9. **Self-approval is allowed.** A grade 2+ author's `publishArticle` publishes directly; grade 3 can approve their own pending article.

18. **Any player could add timeline entries.** `addEntry` checked `rank < 0`, which never fails (non-reporters have rank 0). Found while writing tests.

### Medium

10. **Real bug:** `likeArticle` broadcasts `liked = likedByMe` (the liker's state) to all players, so everyone viewing that article sees it as liked or unliked by them.
11. Every like or comment calls `broadcastLatestNews()`, which queries and sends 15 full articles to every connected player.
12. `/weazel` has no job check on the client, and `openPanel` has no server gate. README says the command is "reporter only"; it is not.
13. Hard deletes: `DELETE FROM rp_articles` with no soft delete. Likes and comments are orphaned (no foreign keys).
14. `publishDraft` while editing a draft in the form sends only the id, so edits made in the form since the last save are **silently lost** (`script.js` 630-632). Also, an Editor publishing a draft sends it to `pending`, but publishing directly makes it `published`. Inconsistent.
15. No `onResourceStop` cleanup: restarting the resource with the panel open can leave NUI focus stuck. A `Wait(0)` thread polls Escape every frame permanently, and `script.js` also handles Escape (double close).
16. Discord logs include every like, comment excerpt, and draft event with character names. Acceptable now; incompatible with source-confidentiality goals for investigations.
17. Duplicate event handlers: `phone.lua` re-registers `weazel:client:updateLikes/updateComments/showArticle`, which would fire twice if enabled.

### Documentation errors

README says import `sql/install.sql` (file is at the repo root), says upload is configured in `server/main.lua` (it is not), and says the resource is named `qb-weazel-ui`. Confirm your actual `ensure` name.

## 3. Reusable vs rewrite

**Reuse as-is or nearly:** the five table definitions (as the migration source of truth), the `rumour/confirmed/denied` timeline concept, the grade-to-capability intent, the Discord embed format, the list of audit events already logged, the QBCore job/grade as the employment source.

**Refactor:** all server handlers (centralize authz and validation), `rp_dossier_entries` semantics, notification fan-out.

**Replace:** NUI rendering (escape everything, use `textContent`), the hard-coded grade model, the broken phone integration, README.

## 4. Schema notes for migration

- `rp_dossier_entries.entry_type` holds the verification state the code actually uses (`rumour`/`confirmed`/`denied`). The `status` enum column is **always the default `'rumour'`**, so do not migrate it as truth. The server aliases `entry_type AS status`.
- Unused by code: `rp_dossiers.type`, `visibility`, `source_event_id`, `closed_at`; `rp_dossier_entries.image_path`, `caption`, `source`, `visibility` (`public|police`), `escalated`. The `police`/`escalated` columns hint at a planned police link. Need your intent before mapping.
- `rp_dossiers.citizenid` is the **creator** (duplicated in `created_by` as a name). It does not identify a subject.
- Authors everywhere are display names, not citizenids. Where a name cannot be matched to a `players.charinfo`, the migration must keep the name as a legacy string and flag the row. IDs, timestamps, comments, likes are preserved 1:1.
- Timestamps are `timestamp` (UTC per the dump's `TIME_ZONE='+00:00'`).

## 5. DOJ reference architecture (what I will reuse)

Stack: FastAPI 0.139 + SQLAlchemy 2 + Alembic + PostgreSQL (pgvector for RAG), Next.js 16 / React 19 / TypeScript / Tailwind 4 / Radix / Lucide / Recharts. Auth: local single-user bypass by default, optional Discord login, and a FiveM ticket flow. Roles are a global enum plus a separate per-object access service. Audit log, chain of custody, visibility states, evidence sealing, structured AI findings (fact/claim/inference/unverified), and contradiction detection already exist there as patterns.

**FiveM bridge pattern (reuse):** the game *server* (never the client) calls `POST /fivem/session` with a secret from a server convar, sending Discord id, character name, citizenid and a job-derived role. The API returns a one-time URL with a 60-second hashed ticket; the page exchanges it for tokens. `admin` can never come from the game.

**Gaps in that pattern I will close for Weazel** (your spec requires it): the shared key is a static header, so there is no replay protection. I will sign each bridge request (HMAC over method, path, body hash, timestamp, nonce), reject stale timestamps and repeated nonces, and bind tickets to the player's session and expiry. I did not read the rest of `fivem.py` beyond the session endpoint, so I will review its exchange step before copying it.

## 6. Proposed architecture

Standalone repo layout (this repo evolves; the legacy resource stays untouched at the root until the replacement is tested):

```
core-api/         FastAPI, SQLAlchemy, Alembic, tests
frontend/         Next.js app (en/fr, Arabic RTL)
fivem/weazel-news/  new resource: bridge, tablet opener, notifications, QBCore sync
docs/
(legacy root)     fxmanifest.lua, server/, client/, html/  (kept working, hardened)
```

**Data ownership**

| Data | Owner after cutover | Notes |
|---|---|---|
| Employment (job, grade) | QBCore `players` | Postgres `staff` is a mirror, refreshed on login and job events. Promotions write to QBCore through the game server, never directly from the API |
| Identity (citizenid, name) | QBCore | Sent by game server only |
| Articles, revisions, investigations, evidence, sources, tasks, audit, AI usage | Postgres | New, authoritative |
| Legacy five tables | MySQL, **read-only** | Idempotent import preserving ids; never dropped or modified |

Conflict rule: one writer per datum. There is no two-way sync of articles between MySQL and Postgres. During migration the legacy panel keeps working against MySQL until you choose a cutover date; articles published on either side after the import are re-imported by the repeatable script (safe to re-run, keyed on legacy id).

**Auth modes (configurable):** `fivem` (ticket exchange, default for production), `local` (single local admin, as DOJ), optional `discord`.

**RBAC:** the permission list in your spec, stored in tables (`roles`, `role_permissions`, `job_grade_mappings`), editable in the admin UI. Employment grade, app role, and per-user grants stay three separate things. Defaults seeded from your suggested roles. The legacy four grades map to Intern, Journalist, Editor, Editor-in-Chief.

## 7. Phase plan

1. **Phase 1 (this document) + hotfix of the legacy resource:** webhooks to server convars, server-side authz/validation layer, XSS fix (escape everything, no `innerHTML` with data), `getArticle` gating, `approvePending` fix, `setGrade`/`fire`/`recruit` target and range validation, like-broadcast fix, `onResourceStop` cleanup, job gate on `/weazel`, README corrections. Tests: Lua logic cannot be run without a server, so I will add a small Lua test harness with a stubbed QBCore/oxmysql for the authorization rules and state exactly what it does and does not cover.
2. Core platform: design system, shell, auth, RBAC, dashboard, articles, investigations, timelines. Alembic migrations + legacy import with verification report.
3. Editorial ops: review workflow, revisions, assignments, notifications, evidence and media.
4. AI workspace, reusing DOJ's structured-findings and contradiction code.
5. FiveM bridge, QBCore sync, Discord delivery with retry/dedup, phone integration (only if a phone resource is specified), admin.
6. Validation: security tests, migration rehearsal, accessibility, deployment and Windows/VS Code guide.

## 8. Known limits of this audit

- No code was run. No runtime behavior was reproduced.
- The chain in 2.2 and the offline-job overwrite in 2.3 follow directly from the code but have not been exercised.
- Real production data was not available. Migration rehearsal requires a MySQL export.
- LB Phone version and any existing Weazel phone setup are unknown.
- `qb-core` job definition for `reporter` (grade names/count) was not available.

## 9. Hotfix status (branch `hotfix/phase1-security`)

Done: findings 1 (code side), 2, 3, 4, 5, 6 (opt-in), 7, 8, 10, 11, 12, 14, 15, 16 (partially), 17 (unchanged, phone off), 18. Not done: 9 (workflow), 13 (hard deletes). See `docs/security-checklist.md`.
Tests: 37 Lua-logic tests and 9 headless-Chrome NUI tests pass. Against the original code 28 of the 37 Lua tests and 4 of the NUI XSS tests fail, which is the evidence the tests detect the original bugs. **Not tested:** a real FiveM server, real oxmysql/QBCore, the in-game NUI (CEF), the CSP inside CEF.
