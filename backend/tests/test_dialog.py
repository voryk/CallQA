from app.dialog import infer_roles, sentiment
from app.assessment import assess_dialog

def seg(text, start=0):
    return {'text': text, 'start': start, 'end': start+1}

def test_bank_roles(monkeypatch):
    monkeypatch.setenv('ENABLE_LLM', '0')
    items = [seg('Здравствуйте, меня зовут Анна, я сотрудник банка Центр-инвест'), seg('У меня проблема, карта не работает', 2), seg('Я проверю', 4), seg('Да', 6)]
    roles = infer_roles(items)
    assert [s['role'] for s in roles] == ['operator','client','operator','unknown']
    result = assess_dialog('', items)
    assert result['average_response_seconds'] == 1
    assert result['client_sentiment'] == 'negative'
    assert result['sentiment'] == 'negative'
    assert 'оценочно' in result['response_method']

def test_tones():
    assert sentiment([seg('Спасибо большое, отлично')])['label'] == 'positive'
    assert sentiment([seg('Сколько стоит перевод?')])['label'] == 'neutral'
    assert sentiment([seg('Я не доволен')])['label'] == 'negative'
    assert sentiment([])['label'] == 'unknown'
    assert sentiment([], 'Спасибо')['label'] == 'positive'

def test_channel_preserved():
    assert infer_roles([{**seg('Я проверю'), 'role':'client'}])[0]['role'] == 'client'

def test_conflicting_cues():
    assert infer_roles([seg('Чем могу помочь? У меня проблема')])[0]['role'] == 'unknown'

def test_reanalysis_idempotent():
    original = [seg('Здравствуйте, я сотрудник банка Центр инвест'),seg('Да',3)]
    assert infer_roles(infer_roles(original)) == infer_roles(original)
