import json
import os
from urllib.request import Request, urlopen


def assess(transcript: str) -> dict:
    prompt = (
        'Оцени банковский разговор по тексту. Верни только JSON с полями '
        'overall_score (целое 0..100), politeness (0..100), completeness (0..100), '
        'script_compliance (0..100), resolution (0..100), violations_percent (0..100), '
        'sentiment (positive|neutral|negative), recommendations (массив коротких строк). '
        'Если роли говорящих неизвестны, не приписывай реплики оператору. '
        'Отсутствие доказательств нарушения не означает нарушение. Текст:\n' + transcript[:30000]
    )
    payload = json.dumps({
        'model': os.getenv('OLLAMA_MODEL', 'qwen2.5:3b'),
        'prompt': prompt, 'stream': False, 'format': 'json',
        'options': {'temperature': 0},
    }).encode('utf-8')
    host = os.getenv('OLLAMA_URL', 'http://ollama:11434').rstrip('/')
    if host not in {'http://ollama:11434', 'http://localhost:11434', 'http://127.0.0.1:11434'}:
        raise ValueError('Ollama must be local')
    request = Request(host + '/api/generate', data=payload,
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=15) as response:
        result = json.loads(json.load(response)['response'])
    fields = ('overall_score', 'politeness', 'completeness', 'script_compliance',
              'resolution', 'violations_percent')
    for key in fields:
        value = result.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError('Invalid assessment score')
        result[key] = round(value)
    if result.get('sentiment') not in {'positive', 'neutral', 'negative'}:
        raise ValueError('Invalid sentiment')
    recommendations = result.get('recommendations')
    if not isinstance(recommendations, list):
        raise ValueError('Invalid recommendations')
    result['recommendations'] = [str(item)[:300] for item in recommendations[:5]]
    return {key: result[key] for key in (*fields, 'sentiment', 'recommendations')}


def assess_dialog(transcript: str, segments: list) -> dict:
    """Transparent conversation-level heuristics, not verified operator attribution."""
    import re
    from app.dialog import infer_roles, sentiment
    segments = infer_roles(segments)
    has_roles = any(s.get("role") in {"operator", "client"} for s in segments)
    checks = {
        'Приветствие': r'\b(здравствуйте|добрый день|доброе утро|добрый вечер|приветствую)\b',
        'Представление': r'\b(меня зовут|вас приветствует|на связи)\b',
        'Прощание': r'\b(до свидания|всего доброго|хорошего дня|до встречи)\b',
    }
    evidence = []
    relevant = [s for s in segments if s.get('role') == 'operator'] if has_roles else segments
    for criterion, pattern in checks.items():
        hit = next((s for s in relevant if re.search(pattern, s['text'], re.I)), None)
        evidence.append({'criterion': criterion, 'status': 'found' if hit else 'not_observed',
                         'quote': hit['text'] if hit else None, 'start': hit['start'] if hit else None,
                         'end': hit['end'] if hit else None})
    for s in relevant:
        if re.search(r'\b(идиот|дурак|заткнись)\b', s['text'], re.I):
            evidence.append({'criterion': 'Стоп-слово', 'status': 'candidate_violation',
                             'quote': s['text'], 'start': s['start'], 'end': s['end']})
    found = sum(e['status'] == 'found' for e in evidence)
    flagged = any(e['status'] == 'candidate_violation' for e in evidence)
    score = round(100 * (found + int(not flagged)) / 4) if relevant else None
    gaps = [b['start'] - a['end'] for a, b in zip(segments, segments[1:])
            if 0 <= b['start'] - a['end'] <= 30]
    tone = sentiment(segments, transcript)
    result = {'engine': 'rules', 'overall_score': score, 'politeness': None,
              'completeness': None, 'resolution': None, 'script_compliance': round(found / 3 * 100) if relevant else None,
              'violations_percent': round(100 * int(flagged) / 4) if relevant else None, 'sentiment': tone['label'], 'evidence': evidence,
              'average_response_seconds': None,
              'estimated_pause_seconds': round(sum(gaps)/len(gaps), 2) if gaps else None,
              'response_method': 'Роли не установлены; пауза между сегментами не равна времени ответа',
              'recommendations': ['Проверить вручную: ' + e['criterion'] for e in evidence if e['status'] != 'found']}
    responses = [b['start'] - a['end'] for a, b in zip(segments, segments[1:])
                 if a.get('role') == 'client' and b.get('role') == 'operator' and 0 <= b['start'] - a['end'] <= 30]
    if responses:
        result['average_response_seconds'] = round(sum(responses)/len(responses), 2)
        result['response_method'] = 'Переход клиент → оператор; оценочно по текстовым признакам' if any(s.get('role_source') == 'text' for s in segments) else 'Стерео: переход клиент → оператор; приближённо по сегментам'
    elif not has_roles and gaps:
        result['average_response_seconds'] = result['estimated_pause_seconds']
        result['response_method'] = 'Оценочно: средняя пауза между сегментами, роли неизвестны'
    result['sentiment_details'] = tone
    result['role_method'] = 'Каналы или текстовые признаки; неизвестные реплики не назначаются автоматически'
    result['role_counts'] = {r: sum(s.get('role') == r for s in segments) for r in ('operator', 'client', 'unknown')}
    result['client_sentiment'] = sentiment([s for s in segments if s.get('role') == 'client'])['label']
    result['operator_sentiment'] = sentiment([s for s in segments if s.get('role') == 'operator'])['label']
    if os.getenv('ENABLE_LLM', '0') == '1':
        try:
            result['llm_suggestion'] = assess(transcript)
        except Exception:
            result['llm_status'] = 'unavailable'
    return result
