import os
import pytest

@pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1', reason='Requires PostgreSQL and Redis')
def test_actual_services():
    from app.db import Session
    from app.models import Call
    from app.queue import get_queue
    from sqlalchemy import select
    with Session() as db:
        assert db.bind.dialect.name == 'postgresql'
        db.execute(select(Call).limit(1)).all()
    assert get_queue().connection.ping()
