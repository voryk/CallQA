OPERATOR_CUES = (
    'чем могу помочь',
    'чем вам помочь',
    'меня зовут',
    'вас беспокоит',
    'представляю банк',
    'по вашему обращению',
    'для подтверждения',
    'назовите',
    'уточните, пожалуйста',
    'звоню вам',
    'специалист банка',
)

CUSTOMER_CUES = (
    'у меня',
    'мне нужно',
    'мне нужна',
    'я хотел',
    'я хотела',
    'мне сказали',
    'хочу узнать',
    'хочу оформить',
    'хочу уточнить',
    'не могу',
    'моя карта',
    'мой счет',
    'мой счёт',
    'я звоню',
    'подскажите',
)


def classify_role(text: str) -> str:
    normalized = text.casefold()
    operator_score = sum(cue in normalized for cue in OPERATOR_CUES)
    customer_score = sum(cue in normalized for cue in CUSTOMER_CUES)
    if operator_score and operator_score > customer_score:
        return 'operator'
    if customer_score and customer_score > operator_score:
        return 'customer'
    return 'unknown'


def classify_segments(segments: list[dict]) -> list[dict]:
    return [{**segment, 'role': classify_role(segment['text'])} for segment in segments]
