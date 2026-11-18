from datetime import date, datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import Call
from app.db import Base
from app.period import date_filter


def test_inclusive_dates():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i, day, hour in [(1, 1, 23), (2, 2, 0), (3, 2, 23), (4, 3, 0)]:
            db.add(Call(id=str(i), original_name='test', size_bytes=1, status='completed', created_at=datetime(2026, 11, day, hour, tzinfo=timezone.utc)))
        db.commit()
        query = date_filter(select(Call.id), date(2026,11,2), date(2026,11,2))
        assert set(db.scalars(query)) == {'2','3'}
        assert len(list(db.scalars(date_filter(select(Call.id), None, None)))) == 4


def test_invalid_dates():
    with pytest.raises(HTTPException) as error:
        date_filter(select(Call), date(2026,11,3), date(2026,11,2))
    assert error.value.status_code == 422
