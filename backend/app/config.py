import os
from pathlib import Path

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://callguard:callguard@localhost:5432/callguard')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
STORAGE = Path(os.getenv('STORAGE_DIR', './storage')).resolve()
STORAGE.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 100 * 1024 * 1024
