import os
import uuid
from datetime import datetime, timezone, timedelta
from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
import csv
import io
import json
import av
import secrets
from argon2 import PasswordHasher
from fastapi import Depends, Header
from pydantic import BaseModel
from redis import Redis
from rq import Queue, Retry
from sqlalchemy import DateTime, Integer, String, Text, JSON, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://callguard:callguard@localhost:5432/callguard')
STORAGE = Path(os.getenv('STORAGE_DIR', './storage')).resolve()
STORAGE.mkdir(parents=True, exist_ok=True)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
MAX_BYTES = 100 * 1024 * 1024

class Base(DeclarativeBase):
    pass

class Call(Base):
    __tablename__ = 'calls'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default='queued')
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    storage_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assessment_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
app = FastAPI(title='CallGuard AI API', version='0.1.0')
password_hasher = PasswordHasher()


def audit(actor: str, action: str, target_id: str | None = None):
    with Session.begin() as db:
        db.add(AuditEvent(id=str(uuid.uuid4()), actor=actor, action=action, target_id=target_id))


def require_user(authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required')
    token = authorization[7:]
    if len(token) < 32:
        raise HTTPException(401, 'Invalid session')
    username = Redis.from_url(REDIS_URL).get('session:' + token)
    if not username:
        raise HTTPException(401, 'Session expired')
    with Session() as db:
        user = db.get(User, username.decode())
        if user is None or not user.active:
            raise HTTPException(403, 'Access denied')
        return user


def require_editor(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role not in {'admin', 'analyst'}:
        raise HTTPException(403, 'Editor role required')
    return user


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role != 'admin':
        raise HTTPException(403, 'Admin role required')
    return user


class LoginIn(BaseModel):
    username: str
    password: str


class ReviewIn(BaseModel):
    decision: str


@app.post('/api/login')
def login(credentials: LoginIn):
    redis = Redis.from_url(REDIS_URL)
    attempt_key = 'login_attempts:' + credentials.username.lower()
    attempts = redis.get(attempt_key)
    if attempts and int(attempts) >= 5:
        raise HTTPException(429, 'Too many login attempts')
    with Session() as db:
        user = db.get(User, credentials.username)
        try:
            valid = bool(user and user.active and password_hasher.verify(user.password_hash, credentials.password))
        except Exception:
            valid = False
        if not valid:
            count = redis.incr(attempt_key)
            if count == 1:
                redis.expire(attempt_key, 900)
            raise HTTPException(401, 'Invalid credentials')
    token = secrets.token_urlsafe(32)
    redis.delete(attempt_key)
    redis.setex('session:' + token, 8 * 3600, user.username)
    audit(user.username, 'login')
    return {'token': token, 'role': user.role, 'username': user.username}


@app.get('/api/me')
def me(user: Annotated[User, Depends(require_user)]):
    return {'username': user.username, 'role': user.role}


@app.get('/api/audit')
def list_audit(user: Annotated[User, Depends(require_admin)]):
    with Session() as db:
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100)).all()
        return [{'id': event.id, 'actor': event.actor, 'action': event.action,
                 'target_id': event.target_id, 'created_at': event.created_at}
                for event in events]


@app.post('/api/logout')
def logout(user: Annotated[User, Depends(require_user)],
           authorization: Annotated[str, Header()]):
    Redis.from_url(REDIS_URL).delete('session:' + authorization[7:])
    audit(user.username, 'logout')
    return {'status': 'ok'}

class CallOut(BaseModel):
    id: str
    original_name: str
    status: str
    size_bytes: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    transcript: str | None
    segments: list | None
    language: str | None
    error: str | None
    operator_id: str | None
    assessment: dict | None
    assessment_status: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    model_config = {'from_attributes': True}

def get_queue():
    return Queue('transcription', connection=Redis.from_url(REDIS_URL), default_timeout=1800)

@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/health/ready')
def ready():
    try:
        with Session() as db:
            db.execute(select(1))
        Redis.from_url(REDIS_URL).ping()
        model_path = Path(os.getenv('WHISPER_MODEL_PATH', './models/whisper'))
        model_ready = (model_path / 'model.bin').is_file() and (model_path / 'config.json').is_file()
    except Exception:
        raise HTTPException(503, 'Database or queue unavailable')
    if not model_ready:
        raise HTTPException(503, 'Whisper model unavailable')
    return {'status': 'ready'}

@app.post('/api/calls', response_model=CallOut, status_code=201)
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

@app.get('/api/calls', response_model=list[CallOut])
def list_calls(user: Annotated[User, Depends(require_user)]):
    with Session() as db:
        return db.scalars(select(Call).order_by(Call.created_at.desc()).limit(100)).all()

@app.get('/api/calls/{call_id}', response_model=CallOut)
def get_call(call_id: str, user: Annotated[User, Depends(require_user)]):
    with Session() as db:
        call = db.get(Call, call_id)
        if not call:
            raise HTTPException(404, 'Call not found')
    audit(user.username, 'view_call', call_id)
    return call


@app.post('/api/calls/{call_id}/review', response_model=CallOut)
def review_call(call_id: str, review: ReviewIn, user: Annotated[User, Depends(require_editor)]):
    if review.decision not in {'approved', 'rejected'}:
        raise HTTPException(422, 'Decision must be approved or rejected')
    with Session.begin() as db:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(404, 'Call not found')
        if call.assessment is None:
            raise HTTPException(409, 'No assessment to review')
        call.assessment_status = review.decision
        call.reviewed_by = user.username
        call.reviewed_at = datetime.now(timezone.utc)
        result = CallOut.model_validate(call)
    audit(user.username, 'review_' + review.decision, call_id)
    return result


@app.post('/api/calls/{call_id}/retry', response_model=CallOut)
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


@app.post('/api/calls/{call_id}/assess', response_model=CallOut)
def reassess_call(call_id: str, user: Annotated[User, Depends(require_editor)]):
    with Session.begin() as db:
        call = db.get(Call, call_id, with_for_update=True)
        if call is None:
            raise HTTPException(404, 'Call not found')
        if call.status != 'completed' or call.transcript is None:
            raise HTTPException(409, 'Transcription unavailable')
        if call.assessment_status not in {'failed', None}:
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


@app.get('/api/dashboard')
def dashboard(user: Annotated[User, Depends(require_user)]):
    with Session() as db:
        calls = db.scalars(select(Call)).all()
        completed = [c for c in calls if c.status == 'completed']
        assessed = [c for c in completed if c.assessment and c.assessment_status == 'approved']
        scores = [c.assessment['overall_score'] for c in assessed
                  if isinstance(c.assessment.get('overall_score'), (int, float))]
        counts = Counter(c.created_at.date() for c in calls)
        today = datetime.now(timezone.utc).date()
        return {
            'total': len(calls),
            'queued': sum(c.status == 'queued' for c in calls),
            'processing': sum(c.status == 'processing' for c in calls),
            'completed': len(completed),
            'failed': sum(c.status == 'failed' for c in calls),
            'assessed': len(assessed),
            'average_score': round(sum(scores) / len(scores), 1) if scores else None,
            'trends': [{'date': day.isoformat(), 'count': counts[day]}
                       for day in (today - timedelta(days=offset) for offset in range(13, -1, -1))],
        }


@app.get('/api/reports/{format}')
def export_report(format: str, user: Annotated[User, Depends(require_editor)]):
    if format not in {'json', 'csv'}:
        raise HTTPException(404, 'Unsupported format')
    audit(user.username, 'export_' + format)
    with Session() as db:
        calls = db.scalars(select(Call).order_by(Call.created_at.desc())).all()
        rows = [{
            'id': c.id, 'date': c.created_at.isoformat(), 'operator_id': c.operator_id,
            'status': c.status, 'language': c.language,
            'overall_score': (c.assessment or {}).get('overall_score') if c.assessment_status == 'approved' else None,
            'violations_percent': (c.assessment or {}).get('violations_percent') if c.assessment_status == 'approved' else None,
            'sentiment': (c.assessment or {}).get('sentiment') if c.assessment_status == 'approved' else None,
            'average_response_seconds': None,
        } for c in calls]
    if format == 'json':
        return Response(json.dumps(rows, ensure_ascii=False), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="report.json"'})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=['id', 'date', 'operator_id', 'status', 'language',
                                               'overall_score', 'violations_percent', 'sentiment',
                                               'average_response_seconds'])
    writer.writeheader()
    writer.writerows(rows)
    return Response('\ufeff' + out.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="report.csv"'})
