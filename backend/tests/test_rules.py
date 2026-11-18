from app.assessment import assess_dialog


def test_rules_offline(monkeypatch):
    monkeypatch.setenv('ENABLE_LLM', '0')
    s = [{'start':0,'end':2,'text':'Здравствуйте, меня зовут Анна'}, {'start':3,'end':4,'text':'До свидания'}]
    r = assess_dialog('', s)
    assert r['overall_score'] == 100
    assert r['evidence'][0]['quote'] == s[0]['text']
    assert r['estimated_pause_seconds'] == 1
    assert r['average_response_seconds'] == 1
    assert 'Оценочно' in r['response_method']


def test_no_invented_evidence(monkeypatch):
    monkeypatch.setenv('ENABLE_LLM', '0')
    r = assess_dialog('', [])
    assert r['overall_score'] is None
    assert all(e['quote'] is None for e in r['evidence'])


def test_stop_word(monkeypatch):
    monkeypatch.setenv('ENABLE_LLM', '0')
    r = assess_dialog('', [{'start':4,'end':6,'text':'идиот'}])
    assert r['evidence'][-1]['start'] == 4
    assert r['evidence'][-1]['status'] == 'candidate_violation'
