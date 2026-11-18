from types import SimpleNamespace
import io
import wave
import json
import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main, worker, assessment, retention, db as database, models, security, audit
from app.api import auth, calls, reports


def test_upload_and_transcription(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'test.db'))
    database.Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(calls, 'Session', session)
    monkeypatch.setattr(reports, 'Session', session)
    monkeypatch.setattr(audit, 'Session', session)
    monkeypatch.setattr(calls, 'STORAGE', tmp_path)
    monkeypatch.setattr(worker, 'Session', session)
    monkeypatch.setattr(worker, 'STORAGE', tmp_path)
    queued = []

    class Queue:
        def enqueue(self, func, call_id, **kwargs):
            queued.append(call_id)

    monkeypatch.setattr(calls, 'get_queue', lambda: Queue())
    main.app.dependency_overrides[security.require_user] = lambda: SimpleNamespace(username='tester', role='analyst')
    main.app.dependency_overrides[security.require_editor] = lambda: SimpleNamespace(username='tester', role='analyst')
    client = TestClient(main.app)
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\x00\x00' * 160)
    response = client.post('/api/calls', files={'file': ('sample.wav', audio.getvalue(), 'audio/wav')})
    assert response.status_code == 201
    call_id = response.json()['id']
    assert queued == [call_id]
    assert client.get(f'/api/calls/{call_id}').json()['status'] == 'queued'

    class Model:
        def transcribe(self, path, **kwargs):
            assert path.endswith('.wav')
            return iter([SimpleNamespace(start=0.0, end=1.2, text=' Привет ')]), SimpleNamespace(language='ru')

    monkeypatch.setattr(worker, 'get_model', lambda: Model())
    monkeypatch.setattr(worker, 'assess', lambda text, segments: {
        'overall_score': 85, 'violations_percent': 0, 'sentiment': 'neutral',
        'recommendations': ['Уточнить запрос клиента'],
    })
    worker.process_call(call_id)
    result = client.get(f'/api/calls/{call_id}').json()
    assert result['status'] == 'completed'
    assert result['transcript'] == 'Привет'
    assert result['segments'] == [{'start': 0.0, 'end': 1.2, 'text': 'Привет', 'role': 'unknown', 'role_source': 'unknown'}]
    assert result['language'] == 'ru'
    assert result['assessment_status'] == 'pending_review'
    assert result['assessment']['overall_score'] == 85
    assert client.get('/api/dashboard').json()['completed'] == 1
    assert client.get('/api/dashboard?date_from=2000-01-01&date_to=2000-01-02').json()['total'] == 0
    assert client.get('/api/calls?date_from=2000-01-01&date_to=2000-01-02').json() == []
    assert client.get('/api/reports/json?date_from=2000-01-01&date_to=2000-01-02').json() == []
    assert client.get('/api/dashboard?date_from=2026-02-01&date_to=2026-01-01').status_code == 422
    assert client.get('/api/dashboard').json()['average_score'] is None
    assert client.get('/api/reports/json').json()[0]['overall_score'] is None
    reviewed = client.post(f'/api/calls/{call_id}/review', json={'decision': 'approved'})
    assert reviewed.status_code == 200
    assert reviewed.json()['reviewed_by'] == 'tester'
    assert call_id in client.get('/api/reports/csv').text
    assert client.get('/api/reports/json').json()[0]['overall_score'] == 85
    main.app.dependency_overrides.clear()


def test_rejects_invalid_audio_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(calls, 'STORAGE', tmp_path)
    main.app.dependency_overrides[security.require_editor] = lambda: SimpleNamespace(username='tester', role='analyst')
    response = TestClient(main.app).post('/api/calls', files={'file': ('bad.txt', b'x')})
    assert response.status_code == 415
    main.app.dependency_overrides.clear()


def test_api_requires_authentication():
    main.app.dependency_overrides.clear()
    assert TestClient(main.app).get('/api/calls').status_code == 401
    assert TestClient(main.app).get('/api/reports/json').status_code == 401


def test_login_role_and_logout(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'auth.db'))
    database.Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth, 'Session', session)
    monkeypatch.setattr(calls, 'Session', session)
    monkeypatch.setattr(security, 'Session', session)
    monkeypatch.setattr(audit, 'Session', session)
    with session.begin() as db:
        db.add(models.User(username='reader', password_hash=security.password_hasher.hash('long-test-password'),
                         role='viewer', active=True))

    class FakeRedis:
        values = {}

        def setex(self, key, ttl, value):
            self.values[key] = value.encode()

        def get(self, key):
            return self.values.get(key)

        def delete(self, key):
            self.values.pop(key, None)

        def incr(self, key):
            self.values[key] = str(int(self.values.get(key, b'0')) + 1).encode()
            return int(self.values[key])

        def expire(self, key, seconds):
            return True

    fake = FakeRedis()
    monkeypatch.setattr(auth, 'Redis', SimpleNamespace(from_url=lambda _: fake))
    monkeypatch.setattr(security, 'Redis', SimpleNamespace(from_url=lambda _: fake))
    client = TestClient(main.app)
    assert client.post('/api/login', json={'username': 'reader', 'password': 'wrong'}).status_code == 401
    response = client.post('/api/login', json={'username': 'reader', 'password': 'long-test-password'})
    assert response.status_code == 200
    headers = {'Authorization': 'Bearer ' + response.json()['token']}
    assert client.get('/api/me', headers=headers).json()['role'] == 'viewer'
    assert client.get('/api/calls', headers=headers).status_code == 200
    assert client.get('/api/reports/json', headers=headers).status_code == 403
    assert client.get('/api/audit', headers=headers).status_code == 403
    assert client.post('/api/logout', headers=headers).status_code == 200
    assert client.get('/api/me', headers=headers).status_code == 401
    for _ in range(5):
        assert client.post('/api/login', json={'username': 'reader', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/login', json={'username': 'reader', 'password': 'wrong'}).status_code == 429


def test_retention_removes_only_expired_calls(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'retention.db'))
    database.Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(retention, 'Session', session)
    monkeypatch.setattr(retention, 'STORAGE', tmp_path)
    monkeypatch.setenv('RETENTION_DAYS', '30')
    now = datetime.now(timezone.utc)
    (tmp_path / 'old.wav').write_bytes(b'old')
    (tmp_path / 'new.wav').write_bytes(b'new')
    with session.begin() as db:
        db.add(models.Call(id='old', original_name='old.wav', size_bytes=3,
                         storage_name='old.wav', status='completed', transcript='private', assessment={'overall_score': 80}, created_at=now - timedelta(days=31)))
        db.add(models.Call(id='new', original_name='new.wav', size_bytes=3,
                         storage_name='new.wav', created_at=now - timedelta(days=1)))
    assert retention.purge_expired(now) == 1
    assert not (tmp_path / 'old.wav').exists()
    assert (tmp_path / 'new.wav').exists()
    with session() as db:
        assert db.get(models.Call, 'old').storage_name is None
        assert db.get(models.Call, 'old').transcript is None
        assert db.get(models.Call, 'old').assessment['overall_score'] == 80
        assert db.get(models.Call, 'new') is not None


def test_retry_failed_call(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'retry.db'))
    database.Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(calls, 'Session', session)
    monkeypatch.setattr(calls, 'STORAGE', tmp_path)
    monkeypatch.setattr(audit, 'Session', session)
    (tmp_path / 'failed.wav').write_bytes(b'audio')
    with session.begin() as db:
        db.add(models.Call(id='failed', original_name='failed.wav', size_bytes=5,
                         storage_name='failed.wav', status='failed'))
    queued = []
    class Queue:
        def fetch_job(self, job_id): return None
        def enqueue(self, func, call_id, **kwargs): queued.append(call_id)
    monkeypatch.setattr(calls, 'get_queue', lambda: Queue())
    main.app.dependency_overrides[security.require_editor] = lambda: SimpleNamespace(username='tester', role='analyst')
    response = TestClient(main.app).post('/api/calls/failed/retry')
    assert response.status_code == 200
    assert response.json()['status'] == 'queued'
    assert queued == ['failed']
    main.app.dependency_overrides.clear()


def test_assessment_uses_local_ollama(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(json.dumps({'response': json.dumps({
            'overall_score': 80, 'politeness': 90, 'completeness': 70,
            'script_compliance': 75, 'resolution': 85, 'violations_percent': 10,
            'sentiment': 'neutral', 'recommendations': ['Уточнить вопрос'],
        })}).encode())

    monkeypatch.setenv('OLLAMA_URL', 'http://ollama:11434')
    monkeypatch.setattr(assessment, 'urlopen', fake_urlopen)
    assert assessment.assess('Тестовый разговор')['overall_score'] == 80
    assert seen == ['http://ollama:11434/api/generate']
    monkeypatch.setenv('OLLAMA_URL', 'https://example.com')
    with pytest.raises(ValueError):
        assessment.assess('Тестовый разговор')


def test_reassess_saved_transcript(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'assess.db'))
    database.Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(calls, 'Session', session)
    monkeypatch.setattr(audit, 'Session', session)
    with session.begin() as db:
        db.add(models.Call(id='done', original_name='done.wav', size_bytes=1,
                         status='completed', transcript='Здравствуйте',
                         assessment_status='failed'))
    queued = []
    class Queue:
        def enqueue(self, func, call_id, **kwargs): queued.append((func, call_id))
    monkeypatch.setattr(calls, 'get_queue', lambda: Queue())
    main.app.dependency_overrides[security.require_editor] = lambda: SimpleNamespace(username='tester', role='analyst')
    client = TestClient(main.app)
    assert client.post('/api/calls/done/assess').status_code == 200
    assert queued == [('app.worker.assess_call', 'done')]
    assert client.post('/api/calls/done/assess').status_code == 409
    main.app.dependency_overrides.clear()
