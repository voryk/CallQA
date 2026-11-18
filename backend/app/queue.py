from redis import Redis
from rq import Queue

from app.config import REDIS_URL


def get_queue():
    return Queue('transcription', connection=Redis.from_url(REDIS_URL), default_timeout=1800)
