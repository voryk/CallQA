"""Reconcile orphaned transcription jobs. Run periodically alongside retention."""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from rq import Retry
from app.db import Session
from app.models import Call
from app.queue import get_queue
from app.config import STORAGE


def recover():
    queue = get_queue()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=40)
    with Session.begin() as db:
        rows = db.scalars(select(Call).where(Call.status.in_(['processing','queued']), Call.created_at < cutoff).with_for_update(skip_locked=True)).all()
        for call in rows:
            if call.started_at and call.started_at.replace(tzinfo=timezone.utc) > cutoff:
                continue
            job = queue.fetch_job(call.job_id) if call.job_id else None
            if job and job.get_status(refresh=True) in {'queued','started','scheduled','deferred'}:
                continue
            if not call.storage_name or not (STORAGE / call.storage_name).is_file():
                call.status = 'failed'
                call.error = 'Audio unavailable'
                continue
            # RQ may already have exhausted retries. Do not loop on explicit terminal failures.
            if job and job.get_status(refresh=True) == 'failed':
                info = job.exc_info or ''
                if 'AbandonedJobError' not in info and 'WorkHorseKilledError' not in info:
                    call.status = 'failed'
                    call.error = 'Retry limit reached'
                    continue
            new_id = str(uuid.uuid4())
            queue.enqueue('app.worker.process_call', call.id, job_id=new_id, retry=Retry(max=2, interval=[30,120]))
            call.job_id = new_id
            call.status = 'queued'
            call.started_at = None
            call.error = None

if __name__ == '__main__':
    recover()
