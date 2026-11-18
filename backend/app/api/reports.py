import csv
import io
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.audit import audit
from app.db import Session
from app.models import Call, User
from app.security import require_editor, require_user

router = APIRouter()


@router.get('/api/dashboard')
def dashboard(user: Annotated[User, Depends(require_user)]):
    with Session() as db:
        calls = db.scalars(select(Call)).all()
        completed = [c for c in calls if c.status == 'completed']
        assessed = [c for c in completed if c.assessment and c.assessment_status == 'approved']
        scores = [c.assessment['overall_score'] for c in assessed
                  if isinstance(c.assessment.get('overall_score'), (int, float))]
        counts = Counter(c.created_at.date() for c in calls)
        today = datetime.now(timezone.utc).date()
        return {
            'total': len(calls),
            'queued': sum(c.status == 'queued' for c in calls),
            'processing': sum(c.status == 'processing' for c in calls),
            'completed': len(completed),
            'failed': sum(c.status == 'failed' for c in calls),
            'assessed': len(assessed),
            'average_score': round(sum(scores) / len(scores), 1) if scores else None,
            'trends': [{'date': day.isoformat(), 'count': counts[day]}
                       for day in (today - timedelta(days=offset) for offset in range(13, -1, -1))],
        }


@router.get('/api/reports/{format}')
def export_report(format: str, user: Annotated[User, Depends(require_editor)]):
    if format not in {'json', 'csv'}:
        raise HTTPException(404, 'Unsupported format')
    audit(user.username, 'export_' + format)
    with Session() as db:
        calls = db.scalars(select(Call).order_by(Call.created_at.desc())).all()
        rows = [{
            'id': c.id, 'date': c.created_at.isoformat(), 'operator_id': c.operator_id,
            'status': c.status, 'language': c.language,
            'overall_score': (c.assessment or {}).get('overall_score') if c.assessment_status == 'approved' else None,
            'violations_percent': (c.assessment or {}).get('violations_percent') if c.assessment_status == 'approved' else None,
            'sentiment': (c.assessment or {}).get('sentiment') if c.assessment_status == 'approved' else None,
            'average_response_seconds': None,
        } for c in calls]
    if format == 'json':
        return Response(json.dumps(rows, ensure_ascii=False), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="report.json"'})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=['id', 'date', 'operator_id', 'status', 'language',
                                               'overall_score', 'violations_percent', 'sentiment',
                                               'average_response_seconds'])
    writer.writeheader()
    writer.writerows(rows)
    return Response('\ufeff' + out.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="report.csv"'})
