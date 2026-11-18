from datetime import datetime

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class ReviewIn(BaseModel):
    decision: str


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
