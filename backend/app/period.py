from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from app.models import Call


def date_filter(query, date_from: date | None, date_to: date | None):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'Invalid date range')
    if date_to == date.max:
        raise HTTPException(422, 'End date too large')
    if date_from:
        query = query.where(Call.created_at >= datetime.combine(date_from, datetime.min.time(), timezone.utc))
    if date_to:
        query = query.where(Call.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), timezone.utc))
    return query
