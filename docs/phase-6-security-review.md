# Phase 6 security review (self-review, not independent)

An independent review agent was cut off by a rate limit and then stopped by the user, so this was done by the author. Treat it as a first pass.

Fixed, each with a test that fails on the old code (timing test and secret test verified by reverting):
1. Unknown-account login ran a cost-4 bcrypt, so response time revealed whether an email exists. Now same cost as a real check.
2. Login limit was per IP+email only, so password spraying across accounts was unlimited. Added a per-IP limit (5x).
3. `fivem` auth mode accepted the placeholder JWT secret in production, allowing forged tokens. Now refused.
4. Audit CSV export: guard added for tab/CR leading characters and no longer prefixes empty fields.
5. `core-api/.env` was not gitignored. Now ignored (`.env.example` stays tracked).

Known gaps, not fixed: `change-password` is disabled in `fivem` mode; rate limiters are in memory; no refresh tokens; no AV/EXIF handling; routes were reviewed by reading plus the existing 134 tests, not by fuzzing.
