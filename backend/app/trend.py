"""UTC buckets for the selected upload-date range."""
from datetime import datetime, timedelta, timezone


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def trend_buckets(first, last, hourly=False):
    start = datetime.combine(first, datetime.min.time(), timezone.utc)
    span = (last - first).days + 1
    step = 0 if hourly else max(1, (span + 59) // 60)
    if hourly:
        keys = [start + timedelta(hours=h) for h in range(24)]
        def bucket(value):
            return utc(value).replace(minute=0, second=0, microsecond=0)
    else:
        keys = [first + timedelta(days=d) for d in range(0, span, step)]
        def bucket(value):
            return first + timedelta(days=((utc(value).date()-first).days//step)*step)
    return keys, bucket, step
