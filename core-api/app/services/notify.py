"""In-app notifications. Idempotent: the same (user, dedupe_key) is stored once, so retries and double clicks never spam.
A notification is only created for a user who can already see the record, and carries a link, never record content."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models as m


def notify(db: Session, user_ids, kind: str, *, title: str, link: str, dedupe_key: str, exclude: int | None = None) -> int:
    ids = {int(u) for u in user_ids if u is not None and u != exclude}
    if not ids:
        return 0
    active = set(db.scalars(select(m.User.id).where(m.User.id.in_(ids), m.User.is_active.is_(True))))
    n = 0
    for uid in active:
        res = db.execute(insert(m.Notification).values(user_id=uid, kind=kind, title=title[:255], link=link[:200], dedupe_key=dedupe_key[:120])
                         .on_conflict_do_nothing(constraint="uq_notification_dedupe"))
        n += res.rowcount or 0
    return n


def users_with_permission(db: Session, perm: str) -> list[m.User]:
    from app.services.access import permissions_of
    return [u for u in db.scalars(select(m.User).where(m.User.is_active.is_(True))) if perm in permissions_of(db, u)]
