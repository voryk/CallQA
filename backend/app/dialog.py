"""Offline, explainable Russian text heuristics; not acoustic diarization."""
import re

NEG = r'\b(?:(?:совсем )?не (?:совсем )?(?:работает|получается|помогли|решили|устраивает|доволен|довольна)|ужас\w*|кошмар\w*|возмущ\w*|недовол\w*|жалоб\w*|обман\w*|идиот\w*|дурак\w*|отвратитель\w*|безобраз\w*|разочарован\w*)\b'
POS = r'\b(?:спасибо(?: большое)?|благодарю|отлично|прекрасно|замечательно|(?:очень )?довол[еь]н\w*|вс[её] получилось|вопрос реш[её]н|вы мне помогли|супер)\b'


def sentiment(segments, transcript=''):
    evidence = []
    counts = {'positive': 0, 'negative': 0}
    source = segments or ([{'text': transcript}] if transcript.strip() else [])
    for s in source:
        t = s.get('text', '').lower()
        for label, pattern in [('negative', NEG), ('positive', POS)]:
            # Avoid counting a positive word inside an explicit negation.
            matches = [m for m in re.finditer(pattern, t) if label != 'positive' or not re.search(r'\bне\s+(?:очень\s+|совсем\s+)?$', t[:m.start()])]
            if matches:
                counts[label] += len(matches)
                evidence.append({'sentiment': label, 'quote': s['text'], 'start': s.get('start'), 'end': s.get('end'), 'role': s.get('role', 'unknown')})
    p, n = counts['positive'], counts['negative']
    # A polite thank-you does not erase an explicit complaint.
    label = 'unknown' if not any(s.get('text', '').strip() for s in source) else 'negative' if n and (n >= p or any(re.search(r'\bне\s+(?:совсем\s+)?(?:помогли|решили|работает)', s.get('text',''), re.I) for s in source)) else 'positive' if p > n else 'neutral'
    return {'label': label, 'counts': counts, 'evidence': evidence}
