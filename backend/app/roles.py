"""Role hypotheses from speech patterns and local acoustic similarity."""
import logging
import re

logger = logging.getLogger(__name__)

OPERATOR_CUES = (
    'чем могу помочь', 'чем вам помочь', 'чем я могу помочь', 'вас беспокоит',
    'представляю банк', 'по вашему обращению', 'для подтверждения',
    'назовите', 'уточните пожалуйста', 'звоню вам', 'специалист банка',
    'сотрудник банка', 'я проверю', 'сейчас проверю', 'проверю информацию',
    'я уточню', 'благодарю за ожидание', 'спасибо за обращение',
    'вас приветствует', 'хорошего вам дня',
)
CUSTOMER_CUES = (
    'у меня вопрос', 'у меня проблема', 'у меня возникла', 'у меня не',
    'мне нужно', 'мне нужна', 'я хотел', 'я хотела', 'мне сказали',
    'хочу узнать', 'хочу оформить', 'хочу уточнить', 'не могу',
    'моя карта', 'мой счет', 'я звоню', 'подскажите', 'как мне',
    'почему мне', 'мне не приходит', 'у меня заблокирована',
)
BANK = re.compile(r'(?:центр|цетнр)[\s‑–—-]*инвест')
INTRO = re.compile(r'меня зовут|сотрудник|специалист|вас приветствует|представляю|чем могу помочь')


def classify_role(text: str) -> str:
    normalized = re.sub(r'[^\w\s-]', ' ', text.casefold().replace('ё', 'е'))
    normalized = ' '.join(normalized.split())
    op = sum(cue in normalized for cue in OPERATOR_CUES)
    customer = sum(cue in normalized for cue in CUSTOMER_CUES)
    if BANK.search(normalized) and INTRO.search(normalized):
        op += 3
    # A standalone name introduction and ambiguous mixed turns do not identify a speaker.
    if op and not customer:
        return 'operator'
    if customer and not op:
        return 'customer'
    return 'unknown'


def classify_segments(segments: list[dict], audio=None) -> list[dict]:
    result = []
    for item in segments:
        s = dict(item)
        role = classify_role(s.get('text', ''))
        s['role'] = role
        s.pop('role_source', None)
        if role != 'unknown':
            s['role_source'] = 'text'
        result.append(s)
    try:
        if audio is not None:
            from app.acoustic import enrich
            result = enrich(result, audio)
        if any(s.get('voice_profile') for s in result):
            from app.acoustic import propagate
            result = propagate(result)
    except Exception:
        logger.warning('Acoustic role enrichment failed; keeping text-based roles', exc_info=True)
    from app.dialog import sentiment
    for s in result:
        if s.get('text', '').strip():
            s['sentiment'] = sentiment([s])['label']
    return result


def average_response(segments):
    gaps = [max(0, b['start'] - a['end']) for a, b in zip(segments, segments[1:])
            if a.get('role') == 'customer' and b.get('role') == 'operator']
    return round(sum(gaps)/len(gaps), 2) if gaps else None
