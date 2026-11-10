# Final report

Built locally in 7 stacked branches (phase 1 hotfix to phase 6). Nothing pushed: the GitHub App is not installed, so push from your PC (bundle provided).

## Delivered
Phase 1 security hotfix of the NUI. Phase 2 FastAPI/Postgres core: RBAC, editorial workflow with independent review, investigations with confidentiality, legacy importer, web UI (EN/FR). Phase 3 evidence library and notifications. Phase 4 AI workspace (suggestions only, scoped context). Phase 5 signed FiveM bridge, ticket sign-in, staff sync, Discord outbox. Phase 5b LB Phone read-only news app. Phase 6 review fixes and docs; Discord publishing replaced by in-game delivery (game server polls the API, like the DOJ tablet).

## Tested (sandbox)
Backend 134 passed (real Postgres, real migrations, MariaDB for importer), Lua 53, NUI 13, Node-to-API signing, browser smoke test. Protections were mutation-checked. Lua, NUI and smoke tests were not re-run after the Phase 6 edits.

## NOT tested
Real FiveM server, real LB Phone 2.8.1 (AddCustomApp signature, fetchNui, ui path unverified), real AI model, real MySQL 8, Windows.

## Known gaps
No corrections UI, investigation participants UI or evidence preview (their API routes exist). Admin screens for staff, roles, job grades, workflow and the audit log were added in Phase 7. No antivirus/EXIF handling. In-memory rate limiters (one process). No refresh tokens (30 min). Password change disabled in fivem mode. The old NUI still writes to MySQL (re-run the importer); running both webhook systems double-posts. Independent security review not done (self-review only).

## Do next
Install the GitHub App or push the bundle. Delete the 3 old Discord webhooks (still public in old history). Run the in-game checklist. Provide a real MySQL export for the importer.

## Update: the old panel is gone, every character gets an account

- The old in-game panel and everything that only served it were deleted (NUI pages, `server/main.lua`, the phone news reader, the MySQL schema files). The FiveM resource is a tablet around the web app. Old MySQL data is untouched and still importable.
- Any character can open the newsroom. Reporter grades 0-4 map to journalist, senior journalist, editor, editor-in-chief, system administrator (defaults, editable under Admin, Job mapping; edited rows are never overwritten). Everyone else is a **Citizen** (read only). `WEAZEL_FIVEM_DEFAULT_ROLE` changes or disables that.
- The API applies its defaults at every start, so the new role and job table appear on upgrade without a manual step.
- Tested: 142 API tests, 25 Lua, 11 tablet-page tests, browser run as seven different characters (unemployed, taxi driver, reporter grades 0-4).
- Not tested: a real FiveM client, real LB Phone 2.8.1.

Repository layout: `core-api/`, `web/`, `fivem/` (the in-game resource and its tests), `docs/`. Older phase notes keep the paths they had when written.
