"""Offline, explainable Russian text heuristics; not acoustic diarization."""
import re

BANK = r'центр[\s-]*инвест|сотрудник(?:ом)? банка|(?:из|от) банка|вас приветствует банк|банк\s+[«"]?центр'
OPERATOR = r'чем (?:могу|вам) помочь|(?:уточните|назовите|подскажите),? пожалуйста|(?:я|мы) (?:проверю|проверим|оформим|уточню|помогу)|благодарю за (?:звонок|ожидание)|(?:спасибо|благодарим) за обращение|хорошего вам дня'
CLIENT = r'у меня (?:вопрос|проблема|не получается|не работает)|я (?:хочу|хотел[а]? бы|не могу|обращался|обращалась)|мне (?:нужно|не приходит|не приш[её]л)|почему (?:у меня|мне|вы)|не могу (?:войти|оплатить|снять)|(?:у меня|на мо[её]й карте) (?:не|заблокирован)|(?:как мне|где мне)'
NEG = r'\b(?:не (?:работает|получается|помогли|решили|устраивает|доволен|довольна)|ужас\w*|кошмар\w*|возмущ\w*|недовол\w*|жалоб\w*|обман\w*|идиот\w*|дурак\w*|отвратитель\w*|безобраз\w*|разочарован\w*)\b'
POS = r'\b(?:спасибо(?: большое)?|благодарю|отлично|прекрасно|замечательно|(?:очень )?довол[еь]н\w*|вс[её] получилось|вопрос реш[её]н|вы мне помогли|супер)\b'


def infer_roles(segments):
    result = []
    for item in segments:
        s = dict(item)
        if s.get('role') in {'operator', 'client'} and s.get('role_source') != 'text':
            s.setdefault('role_source', 'channel')
        else:
            text = s.get('text', '').lower()
            op = bool(re.search(OPERATOR, text) or (s['start'] <= 45 and re.search(BANK, text) and re.search(r'меня зовут|здравствуйте|добрый день|сотрудник банка|вас приветствует', text)))
            cl = bool(re.search(CLIENT, text))
            s['role'] = ('operator' if op else 'client') if op != cl else 'unknown'
            s['role_source'] = 'text' if op != cl else 'unknown'
        result.append(s)
    return result


def sentiment(segments, transcript=''):
    evidence = []
    counts = {'positive': 0, 'negative': 0}
    source = segments or ([{'text': transcript}] if transcript.strip() else [])
    for s in source:
        t = s.get('text', '').lower()
        for label, pattern in [('negative', NEG), ('positive', POS)]:
            # Avoid counting a positive word inside an explicit negation.
            matches = [m for m in re.finditer(pattern, t) if label != 'positive' or not re.search(r'\bне\s+$', t[:m.start()])]
            if matches:
                counts[label] += len(matches)
                evidence.append({'sentiment': label, 'quote': s['text'], 'start': s.get('start'), 'end': s.get('end'), 'role': s.get('role', 'unknown')})
    p, n = counts['positive'], counts['negative']
    # A polite thank-you does not erase an explicit complaint.
    label = 'unknown' if not any(s.get('text', '').strip() for s in source) else 'negative' if n >= p and n else 'positive' if p > n else 'neutral'
    return {'label': label, 'counts': counts, 'evidence': evidence}
