"""Настройки приложения из переменных окружения и .env (pydantic-settings).

Секреты (SECRET_KEY, DATABASE_URL, REDIS_URL) не имеют значений по умолчанию:
без них приложение не запустится. Подробности: .env.example.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Значения из .env.example, которые нельзя использовать вне локальной разработки.
_PLACEHOLDER_MARKERS = ("change-me", "changeme")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---
    app_env: Literal["local", "test", "production"] = "local"
    secret_key: str = Field(min_length=32)
    access_token_ttl_min: int = Field(default=60, gt=0)

    # --- Инфраструктура ---
    database_url: str
    redis_url: str

    # --- Хранилище и модели ---
    storage_dir: Path = Path("/data/storage")
    temp_dir: Path = Path("/data/tmp")
    models_dir: Path = Path("/models")

    # --- Загрузка ---
    max_upload_mb: int = Field(default=200, gt=0)
    max_call_minutes: int = Field(default=60, gt=0)
    allowed_formats: str = "wav,mp3,ogg"

    # --- Распознавание речи ---
    whisper_model: str = "small"
    whisper_device: Literal["cpu", "cuda", "auto"] = "cpu"
    whisper_compute_type: str = "int8"
    stt_language: str = "ru"

    # --- Оценка качества ---
    evaluation_engine: Literal["rules", "ollama"] = "rules"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_timeout_sec: int = Field(default=120, gt=0)

    # --- Очередь ---
    worker_concurrency: int = Field(default=1, ge=1)
    job_timeout_sec: int = Field(default=1800, gt=0)
    job_max_retries: int = Field(default=2, ge=0)
    stale_job_after_sec: int = Field(default=1800, gt=0)

    # --- Хранение данных ---
    retention_audio_days: int = Field(default=30, ge=1)
    retention_transcript_days: int = Field(default=90, ge=1)

    # --- Офлайн-режим ---
    offline_mode: bool = True

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def allowed_format_list(self) -> list[str]:
        return [x.strip().lower() for x in self.allowed_formats.split(",") if x.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_production(self) -> "Settings":
        if self.is_production:
            values = (self.secret_key, self.database_url)
            if any(m in v.lower() for v in values for m in _PLACEHOLDER_MARKERS):
                raise ValueError(
                    "В production нельзя использовать шаблонные значения "
                    "SECRET_KEY/DATABASE_URL из .env.example"
                )
            if not self.offline_mode:
                raise ValueError("В production OFFLINE_MODE должен быть true")
        return self


@lru_cache
def get_settings() -> Settings:
    """Единый экземпляр настроек (кэшируется). В тестах: get_settings.cache_clear()."""
    return Settings()  # type: ignore[call-arg]
