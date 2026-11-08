from sqlalchemy.orm import Session

from app import models as m


def record(db: Session, actor: m.User | None, action: str, entity_type: str, entity_id=None, *,
           detail: dict | None = None, investigation_id: int | None = None) -> None:
    """Appends an audit row in the caller's transaction. Never put source identities, evidence contents or
    article/AI prompt text in `detail`: log identifiers and field names only."""
    db.add(m.AuditLog(
        actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None, detail=detail or {}, investigation_id=investigation_id,
    ))
