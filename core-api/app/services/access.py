"""Authorization rules. Every query that can return investigation data goes through these helpers so that
lists, counts, search results and detail views apply exactly the same record-level rule."""
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, aliased

from app import models as m


def permissions_of(db: Session, user: m.User) -> set[str]:
    if not user.is_active or user.role_id is None:
        base: set[str] = set()
    else:
        base = set(db.scalars(select(m.RolePermission.permission_key).where(m.RolePermission.role_id == user.role_id)))
    for ov in db.scalars(select(m.UserPermission).where(m.UserPermission.user_id == user.id)):
        if ov.effect == "grant" and user.is_active and user.role_id is not None:
            base.add(ov.permission_key)
    for ov in db.scalars(select(m.UserPermission).where(m.UserPermission.user_id == user.id, m.UserPermission.effect == "deny")):
        base.discard(ov.permission_key)  # a deny always wins
    return base


class Ctx:
    """The authenticated user with its resolved permissions for the current request."""

    def __init__(self, db: Session, user: m.User):
        self.db, self.user, self.perms = db, user, permissions_of(db, user)

    def can(self, perm: str) -> bool:
        return perm in self.perms

    @property
    def rank(self) -> int:
        return self.user.role.rank if self.user.role else 0


# ----------------------------------------------------------------------------------------------- investigations
ACCESS_ORDER = {"read": 1, "write": 2, "lead": 3}


def participant_access(db: Session, user_id: int, inv_id: int) -> str | None:
    return db.scalar(select(m.InvestigationParticipant.access).where(
        m.InvestigationParticipant.investigation_id == inv_id, m.InvestigationParticipant.user_id == user_id))


def visible_investigation_filter(ctx: Ctx):
    """SQL predicate: which investigations this user may know EXIST. Used by lists, counts, search, dashboard."""
    if not ctx.user.is_active:
        return m.Investigation.id < 0
    # aliased so the subquery never auto-correlates with an outer query that also uses the participants table
    pa = aliased(m.InvestigationParticipant)
    is_participant = exists().where(pa.investigation_id == m.Investigation.id, pa.user_id == ctx.user.id)
    clauses = [is_participant]
    if ctx.can("investigation.read"):
        clauses.append(m.Investigation.classification == "standard")
    if ctx.can("investigation.read_restricted"):
        clauses.append(m.Investigation.classification.in_(["standard", "restricted"]))
    # confidential: participants only, for everybody including administrators
    return or_(*clauses)


def investigation_level(ctx: Ctx, inv: m.Investigation) -> str | None:
    """None = no access (callers answer 404, not 403, so existence does not leak). Else read | write | lead.

    Participants get the level they were given. Non-participants get:
      standard     -> read with investigation.read, write with investigation.edit
      restricted   -> read only, with investigation.read_restricted (editing needs explicit participation)
      confidential -> nothing, whatever their role
    """
    if not ctx.user.is_active:
        return None
    part = participant_access(ctx.db, ctx.user.id, inv.id)
    general = None
    if inv.classification == "standard" and ctx.can("investigation.read"):
        general = "write" if ctx.can("investigation.edit") else "read"
    elif inv.classification == "restricted" and ctx.can("investigation.read_restricted"):
        general = "read"
    candidates = [lvl for lvl in (part, general) if lvl]
    return max(candidates, key=ACCESS_ORDER.__getitem__) if candidates else None


def can_manage_access(ctx: Ctx, inv: m.Investigation) -> bool:
    lvl = investigation_level(ctx, inv)
    if lvl is None:
        return False
    part = participant_access(ctx.db, ctx.user.id, inv.id)
    if part == "lead":
        return True
    return ctx.can("investigation.manage_access") and inv.classification != "confidential"


def entry_visible_filter(ctx: Ctx, inv_level: str):
    """Entries marked restricted are only for leads, the investigative editor role and the entry's author."""
    if inv_level == "lead" or ctx.can("evidence.restrict"):
        return m.InvestigationEntry.id > 0
    return or_(m.InvestigationEntry.restricted.is_(False), m.InvestigationEntry.author_id == ctx.user.id)


# ----------------------------------------------------------------------------------------------- articles
def article_readable(ctx: Ctx, art: m.Article) -> bool:
    from app.permissions import PUBLIC_STATUSES

    if art.status in PUBLIC_STATUSES:
        return True
    if ctx.can("article.read") or ctx.can("article.edit.any") or ctx.can("article.review") or ctx.can("article.approve"):
        return True
    if art.author_id == ctx.user.id:
        return True
    return bool(ctx.db.scalar(select(exists().where(m.ArticleAssignee.article_id == art.id, m.ArticleAssignee.user_id == ctx.user.id))))


def visible_article_filter(ctx: Ctx):
    from app.permissions import PUBLIC_STATUSES

    if ctx.can("article.read") or ctx.can("article.edit.any") or ctx.can("article.review") or ctx.can("article.approve"):
        return m.Article.id > 0
    assigned = exists().where(m.ArticleAssignee.article_id == m.Article.id, m.ArticleAssignee.user_id == ctx.user.id)
    return or_(m.Article.status.in_(PUBLIC_STATUSES), m.Article.author_id == ctx.user.id, assigned)
