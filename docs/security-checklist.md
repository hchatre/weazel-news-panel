# Security checklist (legacy resource, hotfix branch)

Legend: DONE = changed and covered by an automated test. DONE* = changed, not testable here (needs a real server). OPEN = not done.

| Item | State | Notes |
|---|---|---|
| Discord webhooks out of source, read from convars | DONE | test scans the repo for webhook URLs. **You must still delete the exposed webhooks in Discord** |
| Discord posts cannot ping @everyone / roles | DONE | `allowed_mentions` empty on every payload |
| Stored XSS in NUI (titles, content, comments, names, timeline, admin rows, image URLs) | DONE | headless-Chrome tests with 5 payloads; fail on the original code |
| CSP on the NUI page, no inline handlers | DONE* | works in Chrome; **verify in the real FiveM client** (fonts hosts are allowed) |
| Image URLs limited to plain http(s) without quotes/markup (client and server) | DONE | |
| Any player could read drafts/pending via `getArticle` | DONE | |
| `approvePending` leaked non-pending articles to all players and Discord | DONE | |
| `setGrade` / `fire` on non-journalists (online and offline), self-edit, equal/higher rank, invalid grades | DONE | |
| `recruit` of players with another job, self, offline | DONE | |
| Any player could add timeline entries (`rank < 0` never failed) | DONE | reporters only |
| Server-side input validation (type, length, whitelist) on every event | DONE | |
| Rate limits (drafts, comments, likes, dossiers, entries, staff, open) | DONE | per player, in memory |
| Like toggle race and liker's state broadcast to everyone | DONE | |
| Counter broadcast storm on every like/comment | DONE | coalesced to one per 3 s |
| Panel opening decided by the server; focus cleanup on resource stop | DONE* | |
| Blocked privileged attempts logged to console and Discord | DONE | |
| Ownership by citizenid instead of character name | DONE (opt-in) | needs `sql/001_author_citizenid.sql`; legacy rows stay name-matched |
| Publish-while-editing lost the edits | DONE | |
| Self-approval / independent review | OPEN | convar `weazel_block_self_approval` blocks it for `approvePending` only. Direct publish by editors is unchanged. Proper workflow comes with the configurable editorial workflow (Phase 2) |
| Hard deletes of articles; orphaned likes/comments; no revision history | OPEN | Phase 2 (soft delete, revisions) |
| Authorization lives in one resource; no web API yet | OPEN | Phase 2+ |
| Phone app | OPEN | disabled; needs LB Phone version and a real design |
| Discord retry / dedup | OPEN | Phase 5 |

## Rotate secrets
1. Discord: delete the three exposed webhooks and create new ones.
2. Put the new URLs only in `server.cfg` (not in the repo).
3. Search your own history/forks for the old URLs; deleting a webhook is the only real fix.

## Phase 5 additions (bridge, sync, Discord)
- [x] Bridge requests are HMAC-signed with timestamp + nonce; replay, tamper, stale and wrong-path requests are refused (tests, incl. Node↔API)
- [x] Identity for in-game sign-in is taken from the server-side player, never from a client value
- [x] Login tickets: hashed at rest, single use (atomic), 60 s, bound to an active account
- [x] Bridge secret and Discord webhook live only in the environment / server.cfg convars; never returned, logged or rendered
- [x] Staff sync never touches locally created accounts or hand-assigned roles; sessions end on role change or dismissal
- [x] Discord messages: public facts only, no mentions, queued transactionally, de-duplicated, retried with backoff
- [ ] Verify inside a real FiveM server (exports, job events, oxmysql schema) — **not done**
- [ ] Reverse-proxy path check if you ever put the API behind a proxy — **not done**
- [ ] Rotate `WEAZEL_BRIDGE_SECRET` procedure (change both sides, restart) — documented here, not automated
