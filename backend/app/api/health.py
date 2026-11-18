import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from redis import Redis
from sqlalchemy import select

from app.config import REDIS_URL
from app.db import Session

router = APIRouter()


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.get('/health/ready')
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
