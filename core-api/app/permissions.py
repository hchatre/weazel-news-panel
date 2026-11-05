"""Permission catalogue and default roles. These are seed data: administrators can change role names, ranks and
permission sets from the admin API without touching code. Permission KEYS are stable identifiers."""

PERMISSIONS: dict[str, str] = {
    "article.create": "Create articles",
    "article.read": "Read all articles in the newsroom (published ones are always readable)",
    "article.edit.own": "Edit own articles while editable",
    "article.edit.assigned": "Edit articles assigned to you",
    "article.edit.any": "Edit any article while editable",
    "article.submit": "Submit an article for review",
    "article.review": "Start a review and request changes",
    "article.approve": "Approve an article (independent of its author)",
    "article.publish": "Publish an approved article",
    "article.schedule": "Schedule publication",
    "article.correct": "Correct a published article through the correction process",
    "article.archive": "Archive articles",
    "article.notes.read": "Read internal notes on articles",
    "investigation.create": "Open investigations",
    "investigation.read": "Read standard-classification investigations",
    "investigation.read_restricted": "Read restricted-classification investigations without being a participant",
    "investigation.contribute": "Add unverified timeline entries, tasks and leads",
    "investigation.verify": "Set verification status other than rumour / unverified claim",
    "investigation.edit": "Edit investigation records, status and findings",
    "investigation.manage_access": "Change classification and participants",
    "investigation.archive": "Archive investigations",
    "evidence.upload": "Upload evidence (Phase 3)",
    "evidence.read": "Read evidence (Phase 3)",
    "evidence.download": "Download evidence (Phase 3)",
    "evidence.restrict": "Restrict evidence items (Phase 3)",
    "source.read": "See source records (pseudonymous codes and assessments)",
    "source.manage": "Create and assess sources",
    "source.read_identity": "Read the real identity behind a source (audited)",
    "staff.view": "View the staff directory and workload",
    "staff.recruit": "Recruit staff",
    "staff.promote": "Promote or demote staff",
    "staff.dismiss": "Dismiss staff",
    "settings.manage": "Change roles, workflow and configuration",
    "audit.read": "Read the audit log",
    "audit.export": "Export the audit log",
}

_INTERN = {"article.create", "article.edit.own", "article.submit", "investigation.read", "investigation.contribute", "source.read"}
_JOURNALIST = _INTERN | {"article.read", "investigation.create", "investigation.verify", "evidence.upload", "evidence.read", "source.manage"}
_SENIOR = _JOURNALIST | {"article.edit.assigned", "investigation.edit", "evidence.download", "article.notes.read"}
_EDITOR = _SENIOR | {
    "article.edit.any", "article.review", "article.approve", "article.publish", "article.schedule", "article.correct",
    "article.archive", "investigation.archive", "staff.view",
}
_INV_EDITOR = _SENIOR | {
    "article.review", "investigation.read_restricted", "investigation.manage_access", "investigation.archive",
    "evidence.restrict", "source.read_identity", "staff.view",
}
_EIC = _EDITOR | {
    "investigation.read_restricted", "investigation.manage_access", "source.read_identity", "staff.recruit",
    "staff.promote", "staff.dismiss", "audit.read", "evidence.restrict",
}
_ADMIN = set(PERMISSIONS)

# key, name, rank, permissions
DEFAULT_ROLES: list[tuple[str, str, int, set[str]]] = [
    ("intern", "Intern", 10, _INTERN),
    ("journalist", "Journalist", 20, _JOURNALIST),
    ("senior_journalist", "Senior Journalist", 30, _SENIOR),
    ("editor", "Editor", 40, _EDITOR),
    ("investigative_editor", "Investigative Editor", 40, _INV_EDITOR),
    ("editor_in_chief", "Editor-in-Chief / CEO", 50, _EIC),
    ("system_admin", "System Administrator", 100, _ADMIN),
]

# Legacy panel grades (job "reporter"): 0 Intern, 1 Journalist, 2 Editor, 3 CEO
DEFAULT_JOB_MAPPINGS = [("reporter", 0, "intern"), ("reporter", 1, "journalist"), ("reporter", 2, "editor"), ("reporter", 3, "editor_in_chief")]

# from, to, permission, independent, requires_note
DEFAULT_TRANSITIONS = [
    ("idea", "draft", "article.edit.own", False, False),
    ("draft", "submitted", "article.submit", False, False),
    ("revision_requested", "submitted", "article.submit", False, False),
    ("submitted", "in_review", "article.review", True, False),
    ("in_review", "revision_requested", "article.review", True, True),
    ("in_review", "approved", "article.approve", True, False),
    ("approved", "scheduled", "article.schedule", False, False),
    ("approved", "published", "article.publish", False, False),
    ("scheduled", "published", "article.publish", False, False),
    ("published", "corrected", "article.correct", False, True),
    ("draft", "archived", "article.archive", False, False),
    ("published", "archived", "article.archive", False, False),
    ("corrected", "archived", "article.archive", False, False),
]

ARTICLE_STATUSES = ["idea", "draft", "submitted", "in_review", "revision_requested", "approved", "scheduled", "published", "corrected", "archived"]
EDITABLE_BY_AUTHOR = {"idea", "draft", "revision_requested"}
EDITABLE_BY_EDITOR = EDITABLE_BY_AUTHOR | {"submitted", "in_review"}
PUBLIC_STATUSES = {"published", "corrected"}

DEFAULT_CATEGORIES = [
    ("breaking", "Breaking", "À la une"), ("crime", "Crime", "Faits divers"), ("politics", "Politics", "Politique"),
    ("economy", "Economy", "Économie"), ("events", "Events", "Événements"),
]
DEFAULT_LOOKUPS = {
    "investigation_status": [("open", "Open", "Ouverte", False), ("active", "Active", "Active", False),
                             ("awaiting_information", "Awaiting information", "En attente d'informations", False),
                             ("under_review", "Under review", "En révision", False), ("concluded", "Concluded", "Conclue", True),
                             ("archived", "Archived", "Archivée", True)],
    "investigation_type": [("general", "General", "Général", False), ("corruption", "Corruption", "Corruption", False),
                           ("crime", "Crime", "Crime", False), ("public_interest", "Public interest", "Intérêt public", False)],
}
VERIFICATION_STATES = ["rumour", "unverified_claim", "confirmed", "denial", "disputed", "hypothesis"]
LOW_TRUST_STATES = {"rumour", "unverified_claim", "hypothesis"}  # what `investigation.contribute` alone may set
