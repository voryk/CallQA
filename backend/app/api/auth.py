import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from redis import Redis
from sqlalchemy import select

from app.audit import audit
from app.config import REDIS_URL
from app.db import Session
from app.models import AuditEvent, User
from app.schemas import LoginIn
from app.security import password_hasher, require_admin, require_user

router = APIRouter()


@router.post('/api/login')
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


@router.get('/api/me')
def me(user: Annotated[User, Depends(require_user)]):
    return {'username': user.username, 'role': user.role}


@router.get('/api/audit')
def list_audit(user: Annotated[User, Depends(require_admin)]):
    with Session() as db:
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100)).all()
        return [{'id': event.id, 'actor': event.actor, 'action': event.action,
                 'target_id': event.target_id, 'created_at': event.created_at}
                for event in events]


@router.post('/api/logout')
def logout(user: Annotated[User, Depends(require_user)], authorization: Annotated[str, Header()]):
    Redis.from_url(REDIS_URL).delete('session:' + authorization[7:])
    audit(user.username, 'logout')
    return {'status': 'ok'}
