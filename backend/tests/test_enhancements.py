from datetime import date, datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import numpy as np
import pytest
from fastapi import HTTPException
from app.models import Call
from app.db import Base
from app.period import date_filter
from app.trend import trend_buckets
from app.roles import classify_segments, classify_role, average_response
from app.acoustic import describe, propagate
from app.dialog import sentiment


def test_roles_bank_and_customer():
    assert classify_role('Здравствуйте! Меня зовут Анна, сотрудник банка «Центр-инвест»') == 'operator'
    assert classify_role('Меня зовут Анна, сотрудник Цетнр инвест банка') == 'operator'
    assert classify_role('У меня не работает карта, подскажите') == 'customer'
    assert classify_role('Меня зовут Иван') == 'unknown'
    assert classify_role('Да, конечно') == 'unknown'


def test_acoustic_anchors():
    def segment(text, profile, pitch, level):
        return dict(text=text, start=0, end=1, voice_profile=profile, pitch_hz=pitch, dbfs=level)
    data = [segment('Меня зовут Анна, сотрудник банка Центр-инвест', [1, -1]*4, 180, -22),
            segment('У меня проблема', [-1, 1]*4, 100, -30),
            segment('Да, конечно', [1.02, -1.02]*4, 178, -25),
            segment('Понятно', [0]*8, 140, -26)]
    out = classify_segments(data)
    assert [s['role'] for s in out] == ['operator', 'customer', 'operator', 'unknown']
    assert out[2]['role_source'] == 'acoustic'


def test_acoustic_measurement_and_silence():
    t = np.arange(16000)/16000
    sig = .1*np.sin(2*np.pi*180*t)
    obj = describe(sig)
    assert obj and -25 < obj['dbfs'] < -21
    assert abs(obj['pitch_hz']-180) < 5
    assert describe(np.zeros(16000)) is None
    assert describe(np.full(16000, np.nan)) is None


def test_no_acoustic_role_without_both_anchors():
    a = {'role':'operator','role_source':'text','voice_profile':[0]*8}
    b = {'role':'unknown','voice_profile':[0]*8}
    assert propagate([a,b])[1]['role'] == 'unknown'


def test_response_time():
    data = [{'role':'customer','start':0,'end':3},{'role':'operator','start':4,'end':7},
            {'role':'customer','start':8,'end':9},{'role':'operator','start':11,'end':12}]
    assert average_response(data) == 1.5
    assert average_response(data[:1]) is None


def test_sentiment_negation():
    assert sentiment([{'text':'Спасибо, вы мне совсем не помогли. Хорошо, до свидания.'}])['label'] == 'negative'
    assert sentiment([{'text':'Спасибо большое, всё получилось'}])['label'] == 'positive'
    assert sentiment([{'text':'Уточните номер заявки'}])['label'] == 'neutral'
    assert sentiment([])['label'] == 'unknown'


def test_hour_buckets():
    first = date(2026,11,20)
    keys, bucket, _ = trend_buckets(first, first, True)
    assert len(keys)==24 and keys[0].hour==0 and keys[-1].hour==23
    assert bucket(datetime(2026,11,20,23,59,tzinfo=timezone.utc)) == keys[-1]


def test_long_period_buckets():
    first,last=date(2026,1,1),date(2026,12,31)
    keys,bucket,step=trend_buckets(first,last)
    assert len(keys)<=60 and bucket(datetime(2026,12,31,tzinfo=timezone.utc))==keys[-1]
    assert step>1


def test_actual_date_filter_sqlite():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i,when in enumerate([datetime(2026,11,19,23,59),datetime(2026,11,20),datetime(2026,11,20,23,59),datetime(2026,11,21)]):
            db.add(Call(id=str(i),original_name='x.wav',size_bytes=1,status='queued',created_at=when))
        db.commit()
        query=date_filter(select(Call),date(2026,11,20),date(2026,11,20))
        assert [c.id for c in db.scalars(query).all()]==['1','2']
        with pytest.raises(HTTPException):
            date_filter(select(Call),date(2026,11,21),date(2026,11,20))


def test_assessment_receives_roles_and_validates_quotes(monkeypatch):
    import io, json
    from app import assessment
    result = dict(overall_score=80, politeness=80, completeness=80, script_compliance=80,
                  resolution=80, violations_percent=10, sentiment='neutral', recommendations=[],
                  findings=[dict(quote='У меня проблема', issue='Проблема', reason='Контекст', score_impact='Проверить')])
    def fake(request, timeout):
        payload=json.loads(request.data)
        assert 'customer: У меня проблема' in payload['prompt']
        return io.BytesIO(json.dumps({'response':json.dumps(result)}).encode())
    monkeypatch.setattr(assessment,'urlopen',fake)
    monkeypatch.setenv('OLLAMA_URL','http://ollama:11434')
    assert assessment.assess('У меня проблема',segments=[{'role':'customer','text':'У меня проблема'}])['violations_percent']==10
    result['findings'][0]['quote']='Не существующая цитата'
    with pytest.raises(ValueError):
        assessment.assess('У меня проблема',segments=[{'role':'customer','text':'У меня проблема'}])


def test_password_connection_url_encoded(tmp_path):
    import os, subprocess, sys
    env=dict(os.environ, POSTGRES_HOST='postgres', POSTGRES_PASSWORD='A@b:/#c', STORAGE_DIR=str(tmp_path))
    subprocess.run([sys.executable,'-c', 'from app.config import DATABASE_URL; from sqlalchemy.engine import make_url; assert make_url(DATABASE_URL).password == "A@b:/#c"'],env=env,check=True)
