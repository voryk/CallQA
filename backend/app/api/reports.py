import csv
import html
import io
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select

from app.audit import audit
from app.db import Session
from app.models import Call, User
from app.period import date_filter
from app.trend import trend_buckets, utc
from app.roles import average_response
from app.security import require_editor, require_user

router = APIRouter()


def _register_pdf_font() -> str:
    candidates = (
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        Path(os.getenv('WINDIR', r'C:\Windows')) / 'Fonts' / 'arial.ttf',
    )
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        raise HTTPException(503, 'Unicode font for PDF report is unavailable')
    font_name = 'CallGuardDejaVu'
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    return font_name


def _pdf_paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(str(value)).replace('\n', '<br/>'), style)


@router.get('/api/reports/pdf')
def export_pdf_report(user: Annotated[User, Depends(require_editor)], date_from: date | None = None, date_to: date | None = None):
    audit(user.username, 'export_pdf')
    with Session() as db:
        calls = db.scalars(date_filter(select(Call), date_from, date_to).order_by(Call.created_at.desc())).all()

    font_name = _register_pdf_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CallGuardTitle', parent=styles['Title'], fontName=font_name,
        fontSize=18, leading=24, alignment=TA_LEFT, textColor=colors.HexColor('#173b31'),
    )
    heading_style = ParagraphStyle(
        'CallGuardHeading', parent=styles['Heading2'], fontName=font_name,
        fontSize=12, leading=16, textColor=colors.HexColor('#087d49'),
    )
    body_style = ParagraphStyle(
        'CallGuardBody', parent=styles['BodyText'], fontName=font_name,
        fontSize=9, leading=13, spaceAfter=4,
    )
    story = [
        _pdf_paragraph('Отчёт по качеству звонков', title_style),
        Spacer(1, 10),
        _pdf_paragraph(f'Сформирован: {datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")}', body_style),
        _pdf_paragraph(f'Записей: {len(calls)} · Период (UTC): {date_from or "с начала"} — {date_to or "по настоящее время"}', body_style),
        Spacer(1, 12),
    ]
    for call in calls:
        assessment_data = call.assessment or {}
        approved = call.assessment_status == 'approved'
        score = assessment_data.get('overall_score') if approved else None
        violations = assessment_data.get('violations_percent') if approved else None
        call_lines = [
            _pdf_paragraph(f'Звонок: {call.original_name}', heading_style),
            _pdf_paragraph(
                f'Дата: {call.created_at.isoformat()} · Статус: {call.status} · '
                f'Оценка: {score if score is not None else "не подтверждена"} · '
                f'Нарушения: {str(violations) + "%" if violations is not None else "не подтверждены"}',
                body_style,
            ),
        ]
        if call.processing_seconds is not None:
            call_lines.append(_pdf_paragraph(
                f'Время транскрипции: {call.processing_seconds:.2f} с', body_style,
            ))
        if approved and assessment_data.get('average_response_seconds') is not None:
            call_lines.append(_pdf_paragraph(f"Среднее время ответа (оценочно): {assessment_data['average_response_seconds']} с", body_style))
        if assessment_data.get('assessment_seconds') is not None:
            call_lines.append(_pdf_paragraph(f"Время оценки: {assessment_data['assessment_seconds']} с", body_style))
        for finding in assessment_data.get('findings') or []:
            if not isinstance(finding, dict):
                continue
            call_lines.extend([
                _pdf_paragraph(f'Проблема: {finding.get("issue", "не указана")}', body_style),
                _pdf_paragraph(f'Фрагмент: «{finding.get("quote", "")}»' + (f' (с {finding["start"]:.1f} с)' if finding.get("start") is not None else ""), body_style),
                _pdf_paragraph(f'Почему снижена оценка: {finding.get("reason", "не указано")}', body_style),
                _pdf_paragraph(f'Влияние: {finding.get("score_impact", "не указано")}', body_style),
            ])
        for recommendation in assessment_data.get('recommendations') or []:
            call_lines.append(_pdf_paragraph(f'Рекомендация: {recommendation}', body_style))
        story.extend([KeepTogether(call_lines), Spacer(1, 10)])

    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=A4, title='CallGuard call quality report').build(story)
    return Response(
        output.getvalue(),
        media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="callguard-report.pdf"'},
    )


@router.get('/api/dashboard')
def dashboard(user: Annotated[User, Depends(require_user)], date_from: date | None = None, date_to: date | None = None):
    with Session() as db:
        calls = db.scalars(date_filter(select(Call), date_from, date_to)).all()
        completed = [c for c in calls if c.status == 'completed']
        assessed = [c for c in completed if c.assessment and c.assessment_status == 'approved']
        scores = [c.assessment['overall_score'] for c in assessed
                  if isinstance(c.assessment.get('overall_score'), (int, float))]
        today = datetime.now(timezone.utc).date()
        first = date_from or min((utc(c.created_at).date() for c in calls), default=today)
        last = date_to or max(today, max((utc(c.created_at).date() for c in calls), default=today))
        if first > last:
            first = last
        keys, bucket, step = trend_buckets(first, last, first == last)
        counts = Counter(bucket(c.created_at) for c in calls if first <= utc(c.created_at).date() <= last)
        return {
            'total': len(calls),
            'queued': sum(c.status == 'queued' for c in calls),
            'processing': sum(c.status == 'processing' for c in calls),
            'completed': len(completed),
            'failed': sum(c.status == 'failed' for c in calls),
            'assessed': len(assessed),
            'average_score': round(sum(scores) / len(scores), 1) if scores else None,
            'trends': [{'date': day.strftime('%H:%M') if first == last else day.isoformat(), 'count': counts[day]} for day in keys],
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
            'processing_seconds': c.processing_seconds,
            'overall_score': (c.assessment or {}).get('overall_score') if c.assessment_status == 'approved' else None,
            'violations_percent': (c.assessment or {}).get('violations_percent') if c.assessment_status == 'approved' else None,
            'sentiment': (c.assessment or {}).get('sentiment') if c.assessment_status == 'approved' else None,
            'average_response_seconds': (c.assessment or {}).get('average_response_seconds', average_response(c.segments or [])) if c.assessment_status == 'approved' else None,
        } for c in calls]
    if format == 'json':
        return Response(json.dumps(rows, ensure_ascii=False), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="report.json"'})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=['id', 'date', 'operator_id', 'status', 'language',
                                               'processing_seconds', 'overall_score', 'violations_percent', 'sentiment',
                                               'average_response_seconds'])
    writer.writeheader()
    for row in rows:
        for key, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                row[key] = "'" + value
    writer.writerows(rows)
    return Response('\ufeff' + out.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="report.csv"'})
