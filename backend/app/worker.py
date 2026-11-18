import os
import logging
from datetime import datetime, timezone

from redis import Redis
from rq import Worker

from app.config import REDIS_URL, STORAGE
from app.db import Session
from app.models import Call
from app.assessment import assess

_model = None
logger = logging.getLogger(__name__)


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_path = os.environ['WHISPER_MODEL_PATH']
        if not os.path.isfile(os.path.join(model_path, 'model.bin')):
            raise RuntimeError('Local Whisper model is missing')
        _model = WhisperModel(
            model_path,
            device=os.getenv('WHISPER_DEVICE', 'cpu'),
            compute_type=os.getenv('WHISPER_COMPUTE_TYPE', 'int8'),
            local_files_only=True,
        )
    return _model


def process_call(call_id: str):
    with Session.begin() as db:
        call = db.get(Call, call_id)
        if call is None:
            raise ValueError('Call not found')
        call.status = 'processing'
        call.started_at = datetime.now(timezone.utc)
        call.finished_at = None
        call.error = None
        storage_name = call.storage_name
    try:
        path = (STORAGE / storage_name).resolve()
        if path.parent != STORAGE:
            raise ValueError('Invalid storage path')
        segment_iter, info = get_model().transcribe(str(path), beam_size=5, vad_filter=True)
        segments = [{'start': round(s.start, 3), 'end': round(s.end, 3), 'text': s.text.strip()}
                    for s in segment_iter]
        transcript = ' '.join(s['text'] for s in segments).strip()
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.transcript = transcript
            call.segments = segments
            call.language = info.language
            call.status = 'completed'
            call.finished_at = datetime.now(timezone.utc)
        try:
            assess_call(call_id)
        except Exception:
            logger.exception('Assessment failed for call %s', call_id)
    except Exception:
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.status = 'failed'
            call.error = 'Transcription failed; inspect local worker logs'
            call.finished_at = datetime.now(timezone.utc)
        raise


def assess_call(call_id: str):
    with Session.begin() as db:
        call = db.get(Call, call_id)
        if call is None or call.status != 'completed' or call.transcript is None:
            raise ValueError('Completed transcription not found')
        transcript = call.transcript
        call.assessment_status = 'processing'
    try:
        assessment = assess(transcript)
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.assessment = assessment
            call.assessment_status = 'pending_review'
            call.reviewed_by = None
            call.reviewed_at = None
    except Exception:
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.assessment_status = 'failed'
        raise


if __name__ == '__main__':
    Worker(['transcription'], connection=Redis.from_url(REDIS_URL)).work(with_scheduler=True)
