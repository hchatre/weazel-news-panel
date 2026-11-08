# Phase 3 — Evidence library and notifications

Status: implemented and tested locally (backend suite 92 passed; browser smoke test passed). Not pushed. Not run against a real FiveM server.

## Evidence library

Endpoints live under `/api/v1/investigations/{id}/evidence`. Evidence always belongs to one investigation and inherits its visibility.

| Rule | How it is enforced |
|---|---|
| Who may upload | `evidence.upload` **and** write access to the investigation; archived investigations refuse uploads |
| Who may list / see custody | `evidence.read` and read access; restricted items only for the uploader, the case lead, or holders of `evidence.restrict` |
| Who may download / verify | `evidence.download` (granted to Senior Journalist and above by default; configurable) |
| Who may restrict, un-restrict, archive | `evidence.restrict` (Investigative Editor, Editor-in-Chief, admin) **and** write access; archiving needs a reason |
| Confidential cases | evidence is invisible to everyone who is not a participant, administrators included (404) |
| File types | allow-list: png, jpg, jpeg, gif, webp, pdf, txt, mp3, wav, mp4, webm. Content is checked against the extension (magic bytes); html, svg, exe and unknown types are refused |
| Size | `WEAZEL_MAX_UPLOAD_MB` (default 25), enforced while streaming; a rejected upload is deleted from disk |
| Storage | `WEAZEL_STORAGE_DIR/evidence/<random 32-hex name>`; the original filename is sanitised and kept only as metadata; never a web-served folder |
| Integrity | SHA-256 computed on upload; `verify` recomputes it and logs `integrity_ok` / `integrity_failed`; a missing file answers 410 |
| Serving | always `Content-Disposition: attachment`, `application/octet-stream`, `nosniff` |
| Deletion | there is no delete route. Items are archived with a reason and stay in the custody log |
| Custody log | append-only per item: uploaded, downloaded, restricted, unrestricted, archived, restored, integrity_ok, integrity_failed (also mirrored in the audit log, which never stores file contents) |

## Notifications (in-app)

* Triggers: article submitted (to reviewers other than the author/assignees), article decisions (to author and assignees), article assignment, task assignment, being added to an investigation.
* Recipients are filtered through the normal read rule, deactivated users get nothing, the actor is never notified of their own action.
* Idempotent: one row per `(user, dedupe_key)`, so retries never duplicate.
* Privacy: the "added to investigation" notice carries the **reference only**, never the title, so a confidential case name cannot leak. Other notices carry a title snapshot taken only for recipients who could already open the record.
* Users can only list or mark their own notifications. The web app polls the unread count every 30 s.

## Migration

`0002_evidence_and_notifications` is purely additive (3 new tables, no changes to existing ones). Verified: upgrade, downgrade to 0001, upgrade again on a database holding data; existing rows survived.

## New settings

| Variable | Default | Notes |
|---|---|---|
| `WEAZEL_STORAGE_DIR` | `./storage` | back this folder up together with PostgreSQL, otherwise evidence rows point at missing files |
| `WEAZEL_MAX_UPLOAD_MB` | 25 | |

## Not done / limits

* No antivirus scanning, no image metadata (EXIF) stripping, no thumbnails or in-browser preview (files download only).
* No retention or purge policy, and no encryption at rest beyond what the PC's disk provides.
* Notifications are in-app only. Discord delivery with retry and de-duplication belongs to Phase 5 and does not exist yet; there is no Discord code or webhook configuration in this phase.
* Notification wording is built in the web app for English and French only.
* Staff assignment screens (roster, workload views) are API-only; no UI yet.
* Evidence from the legacy tables: the legacy schema stored only an image path in dossier entries (kept in `legacy_meta`); those files are not copied into the evidence library.
