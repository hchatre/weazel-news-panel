# Phase 7: new look and admin screens

**Look.** A broadcast-studio identity instead of a generic dashboard: navy "set" bars and rail, Weazel red, condensed Barlow headlines with Source Serif/Barlow for reading, tags drawn as lower-thirds (parallelograms), cut corners instead of rounded cards, a front-page layout for the article list, and a ticker of the latest published headlines (the one moving element; it pauses on hover or focus and is static with reduced motion). Light and dark themes both work.

**Admin screens** (menu items appear only if you hold the permission; the API enforces it again):
- Staff (`staff.view`): list, add (`staff.recruit`), change role (`staff.promote`), deactivate (`staff.dismiss`), per-person permission grant/deny with a reason (`settings.manage`).
- Roles, Job grades, Workflow (`settings.manage`): edit roles and their permissions, map game job and grade to a role, change workflow steps.
- Audit log (`audit.read`): filters, paging, CSV export (`audit.export`).

**API addition.** `GET /staff/assignable-roles`: roles below the caller's rank, for anyone who can recruit or promote (a chief has no `settings.manage`, so they could not read `/admin/roles`). Tested.

**Checked.** Type-check and production build pass. The browser smoke test now drives every admin action (add, change role, deactivate, edit role, save job grade, save workflow step, filter and export audit) against a real API: it passes. Screenshots reviewed at desktop and phone width in both themes.

**Not done / known.** Fonts are bundled from npm, not loaded from Google. The staff list has no search or paging (fine for a newsroom, not for hundreds). Arabic/RTL is not covered. I did not review every old page (article editor, investigations) beyond the shared styling, so check those and tell me what feels off.
