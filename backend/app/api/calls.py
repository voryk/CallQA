import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

import av
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from rq import Retry
from sqlalchemy import select

from app.audit import audit
from app.config import MAX_BYTES, STORAGE
from app.db import Session
from app.models import Call, User
from app.queue import get_queue
from app.schemas import CallOut, ReviewIn
from app.security import require_editor, require_user

from app.period import date_filter

router = APIRouter()

@router.post('/api/calls', response_model=CallOut, status_code=201)
async def upload_call(file: Annotated[UploadFile, File()],
                      user: Annotated[User, Depends(require_editor)],
                      operator_id: Annotated[str | None, Form()] = None):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.wav', '.mp3', '.ogg'}:
        raise HTTPException(415, 'Only WAV, MP3, OGG are supported')
    call_id = str(uuid.uuid4())
    destination = STORAGE / f'{call_id}{suffix}'
    size = 0
    persisted = False
    try:
        with destination.open('xb') as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'File exceeds 100 MB limit')
                out.write(chunk)
        if not size:
            raise HTTPException(400, 'Empty file')
        try:
            with av.open(str(destination)) as audio:
                if not audio.streams.audio:
                    raise ValueError('No audio stream')
                if audio.duration is not None and audio.duration / 1_000_000 > 600:
                    raise HTTPException(413, 'Audio exceeds 10 minute limit')
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(415, 'Invalid audio file')
        with Session.begin() as db:
            call = Call(id=call_id, original_name=Path(file.filename or 'audio').name[:255],
                        size_bytes=size, storage_name=destination.name, job_id=call_id,
                        operator_id=(operator_id or '').strip()[:64] or None,
                        assessment_status='pending')
            db.add(call)
            db.flush()
            result = CallOut.model_validate(call)
        persisted = True
        audit(user.username, 'upload', call_id)
        try:
            get_queue().enqueue('app.worker.process_call', call_id, job_id=call_id,
                                retry=Retry(max=2, interval=[30, 120]))
        except Exception:
            with Session.begin() as db:
                call = db.get(Call, call_id)
                call.status = 'failed'
                call.error = 'Queue unavailable'
                call.finished_at = datetime.now(timezone.utc)
            raise HTTPException(503, 'Queue unavailable; upload saved with failed status')
        return result
    except Exception:
        if not persisted:
            destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

@router.get('/api/calls', response_model=list[CallOut])
def list_calls(user: Annotated[User, Depends(require_user)], offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), search: str = Query("", max_length=100), status: str = "", date_from: date | None = None, date_to: date | None = None):
    with Session() as db:
        query = date_filter(select(Call), date_from, date_to)
        if search:
            query = query.where(Call.original_name.icontains(search, autoescape=True) | Call.operator_id.icontains(search, autoescape=True))
        if status:
            query = query.where(Call.status == status)
        return db.scalars(query.order_by(Call.created_at.desc(), Call.id).offset(offset).limit(limit)).all()

@router.get('/api/calls/{call_id}', response_model=CallOut)
def get_call(call_id: str, user: Annotated[User, Depends(require_user)]):
    with Session() as db:
        call = db.get(Call, call_id)
        if not call:
            raise HTTPException(404, 'Call not found')
    audit(user.username, 'view_call', call_id)
    return call


@router.post('/api/calls/{call_id}/review', response_model=CallOut)
def review_call(call_id: str, review: ReviewIn, user: Annotated[User, Depends(require_editor)]):
    if review.decision not in {'approved', 'rejected'}:
        raise HTTPException(422, 'Decision must be approved or rejected')
    with Session.begin() as db:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(404, 'Call not found')
        if call.assessment is None or call.assessment_status in {'queued', 'processing'}:
            raise HTTPException(409, 'No assessment to review')
        call.assessment_status = review.decision
        call.reviewed_by = user.username
        call.reviewed_at = datetime.now(timezone.utc)
        result = CallOut.model_validate(call)
    audit(user.username, 'review_' + review.decision, call_id)
    return result


@router.post('/api/calls/{call_id}/retry', response_model=CallOut)
def retry_call(call_id: str, user: Annotated[User, Depends(require_editor)]):
    queue = get_queue()
    with Session.begin() as db:
        call = db.get(Call, call_id, with_for_update=True)
        if call is None:
            raise HTTPException(404, 'Call not found')
        if call.status != 'failed':
            raise HTTPException(409, 'Only failed calls can be retried')
        path = (STORAGE / call.storage_name).resolve() if call.storage_name else None
        if path is None or path.parent != STORAGE or not path.is_file():
            raise HTTPException(409, 'Audio file unavailable')
        old_job = queue.fetch_job(call.job_id) if call.job_id else None
        if old_job and old_job.get_status(refresh=True) in {'queued', 'started', 'scheduled', 'deferred'}:
            raise HTTPException(409, 'Retry already scheduled')
        call.job_id = str(uuid.uuid4())
        call.status = 'queued'
        call.error = None
        call.started_at = None
        call.finished_at = None
        result = CallOut.model_validate(call)
        new_job_id = call.job_id
    try:
        queue.enqueue('app.worker.process_call', call_id, job_id=new_job_id,
                      retry=Retry(max=2, interval=[30, 120]))
    except Exception:
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.status = 'failed'
            call.error = 'Queue unavailable'
            call.finished_at = datetime.now(timezone.utc)
        raise HTTPException(503, 'Queue unavailable')
    audit(user.username, 'retry', call_id)
    return result


@router.post('/api/calls/{call_id}/assess', response_model=CallOut)
def reassess_call(call_id: str, user: Annotated[User, Depends(require_editor)]):
    with Session.begin() as db:
        call = db.get(Call, call_id, with_for_update=True)
        if call is None:
            raise HTTPException(404, 'Call not found')
        if call.status != 'completed' or call.transcript is None:
            raise HTTPException(409, 'Transcription unavailable')
        if call.assessment_status not in {'failed', None, 'pending_review', 'approved', 'rejected'}:
            raise HTTPException(409, 'Assessment already queued or available')
        call.assessment_status = 'queued'
        result = CallOut.model_validate(call)
    try:
        get_queue().enqueue('app.worker.assess_call', call_id, job_id=str(uuid.uuid4()),
                            retry=Retry(max=1, interval=30))
    except Exception:
        with Session.begin() as db:
            db.get(Call, call_id).assessment_status = 'failed'
        raise HTTPException(503, 'Queue unavailable')
    audit(user.username, 'reassess', call_id)
    return result




@router.get('/api/calls/{call_id}/audio')
def get_audio(call_id: str, user: Annotated[User, Depends(require_user)]):
    with Session() as db:
        call = db.get(Call, call_id)
        path = (STORAGE / call.storage_name).resolve() if call and call.storage_name else None
        if not path or path.parent != STORAGE or not path.is_file():
            raise HTTPException(404, 'Audio unavailable')
    audit(user.username, 'listen', call_id)
    return FileResponse(path, media_type={'.wav':'audio/wav','.mp3':'audio/mpeg','.ogg':'audio/ogg'}.get(path.suffix, 'application/octet-stream'))
