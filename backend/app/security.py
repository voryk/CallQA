from typing import Annotated

from argon2 import PasswordHasher
from fastapi import Depends, Header, HTTPException
from redis import Redis

from app.config import REDIS_URL
from app.db import Session
from app.models import User

password_hasher = PasswordHasher()


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
