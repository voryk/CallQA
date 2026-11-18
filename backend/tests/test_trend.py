from datetime import date, datetime, timedelta, timezone
from app.trend import trend_buckets


def test_hourly():
    day = date(2026, 11, 18)
    keys, bucket, step = trend_buckets(day, day, True)
    assert len(keys) == 24 and step == 0
    assert [k.strftime('%H:%M') for k in keys] == [f'{h:02}:00' for h in range(24)]
    assert bucket(datetime(2026, 11, 18, 23, 59)) == keys[-1]
    assert bucket(datetime(2026, 11, 19, 1, 30, tzinfo=timezone(timedelta(hours=3)))) == keys[22]


def test_multi_day():
    first = date(2026, 11, 1)
    keys, bucket, step = trend_buckets(first, date(2026, 11, 7))
    assert len(keys) == 7 and step == 1
    assert bucket(datetime(2026, 11, 3, 15)) == keys[2]


def test_long_period():
    first = date(2026, 1, 1)
    keys, bucket, step = trend_buckets(first, date(2026, 12, 31))
    assert len(keys) <= 60 and step > 1
    assert bucket(datetime(2026, 12, 31, 23)) == keys[-1]
