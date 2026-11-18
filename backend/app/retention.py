import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import STORAGE
from app.db import Session
from app.models import AuditEvent, Call


def purge_expired(now: datetime | None = None) -> int:
    days = int(os.getenv('RETENTION_DAYS', '30'))
    if days < 1:
        raise ValueError('RETENTION_DAYS must be positive')
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    removed = 0
    with Session.begin() as db:
        for call in db.scalars(select(Call).where(Call.created_at < cutoff, Call.status.in_(['completed', 'failed']), Call.storage_name.is_not(None), Call.assessment_status.not_in(['processing', 'queued']) | Call.assessment_status.is_(None))).all():
            if call.storage_name:
                path = (STORAGE / call.storage_name).resolve()
                if path.parent != STORAGE:
                    raise ValueError('Invalid storage path')
                path.unlink(missing_ok=True)
            db.add(AuditEvent(id=str(uuid.uuid4()), actor='system', action='retention_delete',
                              target_id=call.id))
            call.storage_name = None
            call.transcript = None
            call.segments = None
            call.original_name = 'Удалено по сроку хранения'
            if call.assessment:
                call.assessment = {k: v for k, v in call.assessment.items() if k in {
                    'overall_score', 'politeness', 'completeness', 'script_compliance',
                    'resolution', 'violations_percent', 'sentiment', 'average_response_seconds',
                    'response_method', 'processing_seconds', 'engine', 'estimated_pause_seconds'}}
            removed += 1
    return removed


if __name__ == '__main__':
    print(f'Purged {purge_expired()} expired calls')
