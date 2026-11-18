import uuid

from app.db import Session
from app.models import AuditEvent


def audit(actor: str, action: str, target_id: str | None = None):
    with Session.begin() as db:
        db.add(AuditEvent(id=str(uuid.uuid4()), actor=actor, action=action, target_id=target_id))
