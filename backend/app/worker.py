import os
from datetime import datetime, timezone

from redis import Redis
from rq import Worker

from app.main import Call, REDIS_URL, STORAGE, Session
from app.assessment import assess

_model = None


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
            assessment = assess(transcript)
        except Exception:
            with Session.begin() as db:
                call = db.get(Call, call_id)
                call.assessment_status = 'failed'
        else:
            with Session.begin() as db:
                call = db.get(Call, call_id)
                call.assessment = assessment
                call.assessment_status = 'pending_review'
    except Exception:
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.status = 'failed'
            call.error = 'Transcription failed; inspect local worker logs'
            call.finished_at = datetime.now(timezone.utc)
        raise


if __name__ == '__main__':
    Worker(['transcription'], connection=Redis.from_url(REDIS_URL)).work(with_scheduler=True)
