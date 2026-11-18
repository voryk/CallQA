import csv
import io
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.audit import audit
from app.db import Session
from app.models import Call, User
from app.security import require_editor, require_user

from app.period import date_filter
from app.trend import trend_buckets, utc

router = APIRouter()


def csv_safe(value):
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
        return "'" + value
    return value



@router.get('/api/dashboard')
def dashboard(user: Annotated[User, Depends(require_user)], date_from: date | None = None, date_to: date | None = None):
    with Session() as db:
        calls = db.scalars(date_filter(select(Call), date_from, date_to)).all()
        completed = [c for c in calls if c.status == 'completed']
        assessed = [c for c in completed if c.assessment and c.assessment_status == 'approved']
        scores = [c.assessment['overall_score'] for c in assessed
                  if isinstance(c.assessment.get('overall_score'), (int, float))]
        def avg(items):
            values = [c.assessment.get('overall_score') for c in items if c.assessment and isinstance(c.assessment.get('overall_score'), (int, float))]
            return round(sum(values)/len(values), 1) if values else None
        today = datetime.now(timezone.utc).date()
        first = date_from or min((utc(c.created_at).date() for c in calls), default=date_to or today)
        last = date_to or max(today, first, max((utc(c.created_at).date() for c in calls), default=today))
        hourly = date_from is not None and date_from == date_to
        keys, bucket, step = trend_buckets(first, last, hourly)
        counts = Counter(bucket(c.created_at) for c in calls)
        grouped = {}
        for c in assessed:
            grouped.setdefault(bucket(c.created_at), []).append(c)
        sentiments = Counter((c.assessment or {}).get('sentiment', 'unknown') for c in completed if c.assessment)
        return {
            'total': len(calls),
            'queued': sum(c.status == 'queued' for c in calls),
            'processing': sum(c.status == 'processing' for c in calls),
            'completed': len(completed),
            'failed': sum(c.status == 'failed' for c in calls),
            'assessed': len(assessed),
            'average_score': round(sum(scores) / len(scores), 1) if scores else None,
            'operators': sorted([{'operator_id': op, 'average_score': avg([c for c in assessed if c.operator_id == op])} for op in {c.operator_id for c in assessed if c.operator_id}], key=lambda x: x['average_score'] or 0, reverse=True),
            'sentiments': dict(sentiments), 'bucket_days': step, 'bucket_unit': 'hour' if hourly else 'day',
            'trends': [{'date': day.isoformat(), 'count': counts[day], 'average_score': avg(grouped.get(day, []))}
                       for day in keys],
        }


@router.get('/api/reports/{format}')
def export_report(format: str, user: Annotated[User, Depends(require_editor)], date_from: date | None = None, date_to: date | None = None):
    if format not in {'json', 'csv'}:
        raise HTTPException(404, 'Unsupported format')
    audit(user.username, 'export_' + format)
    with Session() as db:
        calls = db.scalars(date_filter(select(Call), date_from, date_to).order_by(Call.created_at.desc())).all()
        rows = [{
            'id': c.id, 'date': c.created_at.isoformat(), 'operator_id': c.operator_id,
            'status': c.status, 'language': c.language,
            'overall_score': (c.assessment or {}).get('overall_score') if c.assessment_status == 'approved' else None,
            'violations_percent': (c.assessment or {}).get('violations_percent') if c.assessment_status == 'approved' else None,
            'sentiment': (c.assessment or {}).get('sentiment') if c.assessment_status == 'approved' else None,
            'average_response_seconds': (c.assessment or {}).get('average_response_seconds') if c.assessment_status == 'approved' else None,
            'response_method': (c.assessment or {}).get('response_method') if c.assessment_status == 'approved' else None,
            'assessment_status': c.assessment_status,
        } for c in calls]
    if format == 'json':
        return Response(json.dumps(rows, ensure_ascii=False), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="report.json"'})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=['id', 'date', 'operator_id', 'status', 'language',
                                               'overall_score', 'violations_percent', 'sentiment',
                                               'average_response_seconds', 'response_method', 'assessment_status'])
    writer.writeheader()
    writer.writerows({k: csv_safe(v) for k, v in row.items()} for row in rows)
    return Response('\ufeff' + out.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="report.csv"'})
