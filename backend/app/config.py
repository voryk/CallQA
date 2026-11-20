import os
from pathlib import Path
from urllib.parse import quote

DATABASE_URL = os.getenv('DATABASE_URL')
if os.getenv('POSTGRES_HOST'):
    password = quote(os.environ['POSTGRES_PASSWORD'], safe='')
    DATABASE_URL = f"postgresql+psycopg://callguard:{password}@{os.environ['POSTGRES_HOST']}:5432/callguard"
DATABASE_URL = DATABASE_URL or 'postgresql+psycopg://callguard:callguard@localhost:5432/callguard'
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
STORAGE = Path(os.getenv('STORAGE_DIR', './storage')).resolve()
STORAGE.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 100 * 1024 * 1024
