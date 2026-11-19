import json
import os
from urllib.request import Request, urlopen


def assess(transcript: str) -> dict:
    prompt = (
        'Оцени банковский разговор по тексту. Верни только JSON с полями '
        'overall_score (целое 0..100), politeness (0..100), completeness (0..100), '
        'script_compliance (0..100), resolution (0..100), violations_percent (0..100), '
        'sentiment (positive|neutral|negative), recommendations (массив коротких строк), '
        'findings (массив объектов с полями quote, issue, reason, score_impact). '
        'В quote приводи дословный фрагмент из текста без исправлений; не выдумывай цитаты. '
        'Для каждого finding объясни проблему и почему она влияет на оценку. '
        'Если доказательств проблем нет, findings должен быть пустым, а violations_percent равен 0. '
        'Если роли говорящих неизвестны, не приписывай реплики оператору. '
        'Не считай отсутствие доказательств нарушением. Текст:\n' + transcript[:30000]
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
    with urlopen(request, timeout=180) as response:
        result = json.loads(json.load(response)['response'])
    fields = ('overall_score', 'politeness', 'completeness', 'script_compliance',
              'resolution', 'violations_percent')
    for key in fields:
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError('Invalid assessment score')
        result[key] = round(value)
    if result.get('sentiment') not in {'positive', 'neutral', 'negative'}:
        raise ValueError('Invalid sentiment')
    recommendations = result.get('recommendations')
    if not isinstance(recommendations, list):
        raise ValueError('Invalid recommendations')
    result['recommendations'] = [str(item)[:300] for item in recommendations[:5]]
    findings = result.get('findings')
    if not isinstance(findings, list):
        raise ValueError('Invalid assessment findings')
    validated_findings = []
    for finding in findings[:10]:
        if not isinstance(finding, dict):
            raise ValueError('Invalid assessment finding')
        quote, issue, reason, score_impact = (
            finding.get('quote'), finding.get('issue'),
            finding.get('reason'), finding.get('score_impact'),
        )
        if not all(isinstance(value, str) and value.strip()
                   for value in (quote, issue, reason, score_impact)):
            raise ValueError('Invalid assessment finding')
        if quote not in transcript:
            raise ValueError('Assessment finding quote is not in transcript')
        validated_findings.append({
            'quote': quote[:500],
            'issue': issue[:300],
            'reason': reason[:500],
            'score_impact': score_impact[:300],
        })
    return {key: result[key] for key in (*fields, 'sentiment', 'recommendations')} | {
        'findings': validated_findings,
    }
