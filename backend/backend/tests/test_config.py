"""Тесты настроек: обязательные секреты, разбор списков, защита production."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_SECRET = "x" * 40
BASE = {
    "SECRET_KEY": GOOD_SECRET,
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
}


def make(monkeypatch, **extra):
    for k in list(BASE) + ["APP_ENV", "OFFLINE_MODE", "ALLOWED_FORMATS", "MAX_UPLOAD_MB"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in {**BASE, **extra}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


def test_defaults_and_helpers(monkeypatch):
    s = make(monkeypatch)
    assert s.app_env == "local"
    assert s.worker_concurrency == 1
    assert s.allowed_format_list == ["wav", "mp3", "ogg"]
    assert s.max_upload_bytes == 200 * 1024 * 1024


def test_allowed_formats_parsing(monkeypatch):
    s = make(monkeypatch, ALLOWED_FORMATS=" WAV , ogg ,")
    assert s.allowed_format_list == ["wav", "ogg"]


def test_secrets_are_required(monkeypatch):
    for k in BASE:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_short_secret_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        make(monkeypatch, SECRET_KEY="short")


def test_production_rejects_placeholder_secret(monkeypatch):
    with pytest.raises(ValidationError):
        make(monkeypatch, APP_ENV="production", SECRET_KEY="change-me-" + "x" * 30)


def test_production_requires_offline_mode(monkeypatch):
    with pytest.raises(ValidationError):
        make(monkeypatch, APP_ENV="production", OFFLINE_MODE="false")


def test_production_ok_with_real_values(monkeypatch):
    s = make(monkeypatch, APP_ENV="production")
    assert s.is_production
