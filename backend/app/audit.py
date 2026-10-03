"""审计日志辅助：所有状态变化统一走这里，保证可追查。"""
from sqlalchemy.orm import Session

from . import models


def log(db: Session, entity_type: str, entity_id: int, action: str,
        actor: models.User | None = None, from_status: str | None = None,
        to_status: str | None = None, detail: str | None = None):
    entry = models.AuditLog(
        entity_type=entity_type, entity_id=entity_id, action=action,
        actor_id=actor.id if actor else None,
        actor_name=actor.name if actor else None,
        from_status=from_status, to_status=to_status, detail=detail,
    )
    db.add(entry)
    return entry
