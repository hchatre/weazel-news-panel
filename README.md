# qb-weazel-ui

**Weazel News Panel for QBCore.** Articles (draft, pending, published), likes and comments, investigation
dossiers with a rumour / confirmed / denied timeline, published-article notifications, and staff administration
(recruit, change grade, fire) for the `reporter` job.

> This branch (`hotfix/phase1-security`) is a security hardening of the original resource. The larger
> Weazel News Intelligence System (web app, API, FiveM bridge) is planned in `docs/phase-1-audit.md`.

## Requirements

- `qb-core`, `oxmysql`
- No upload service is used. Article images are plain `https://` URLs. (Older READMEs mentioned `lb-upload`; that code never existed.)
- The phone app (`client/phone.lua`, `html/phone.*`) is **disabled** and incomplete: it needs a server feed event that does not exist. It is not part of this release.

## Install

1. Put the folder in `resources/` and import `install.sql` (tables are `CREATE TABLE IF NOT EXISTS`, safe on an existing database).
2. **Existing servers:** back up, then run `sql/001_author_citizenid.sql` once. Without it everything works, but draft ownership is checked by character name (old behaviour).
3. Copy the convars from `server.cfg.example` into your `server.cfg` (no Discord webhooks are used any more), then `ensure` the resource.

## Use

- `/weazel` opens the panel. The **server** decides who may open it (`weazel_public_access`).
- Permissions follow the `reporter` job grade: 0 Intern, 1 Journalist, 2 Editor, 3 CEO.
  Grade 3 can recruit, change grades and fire, but only journalists of a **lower** rank, never themselves,
  never above their own grade, and never players with another job.

## Tests

```
pip install lupa playwright
python3 -m unittest discover -s tests/lua        # server logic with stubbed QBCore/oxmysql/LB Phone
CHROME_PATH=/path/to/chrome python3 -m unittest discover -s tests/nui   # NUI in headless Chrome
```
These do not replace testing in a real FiveM server. See `docs/security-checklist.md`.
