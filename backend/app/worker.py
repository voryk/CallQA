import os
import logging
from datetime import datetime, timezone

from redis import Redis
from rq import Worker

from app.config import REDIS_URL, STORAGE
from app.db import Session
from app.models import Call
from app.dialog import infer_roles
from app.assessment import assess_dialog as assess
from rq import get_current_job

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
            cpu_threads=int(os.getenv("WHISPER_THREADS", "4")),
        )
    return _model


def transcribe(path):
    beam = int(os.getenv('WHISPER_BEAM_SIZE', '1'))
    operator_channel = os.getenv('OPERATOR_CHANNEL', '')
    model = get_model()
    if operator_channel in {'left', 'right'}:
        import av
        import numpy as np
        with av.open(str(path)) as source:
            if source.streams.audio[0].codec_context.channels == 2:
                resampler = av.AudioResampler(format='fltp', layout='stereo', rate=16000)
                frames = [f.to_ndarray() for frame in source.decode(audio=0) for f in resampler.resample(frame)]
                frames.extend(f.to_ndarray() for f in resampler.resample(None))
                audio = np.concatenate(frames, axis=1)
                result = []
                for i, channel in enumerate(('left', 'right')):
                    iterator, info = model.transcribe(np.ascontiguousarray(audio[i]), beam_size=beam, vad_filter=True)
                    result.extend({'start': round(s.start,3), 'end': round(s.end,3), 'text': s.text.strip(),
                                   'role': 'operator' if channel == operator_channel else 'client'} for s in iterator)
                return sorted(result, key=lambda s:s['start']), info
    iterator, info = model.transcribe(str(path), beam_size=beam, vad_filter=True)
    return [{'start': round(s.start,3), 'end': round(s.end,3), 'text': s.text.strip()} for s in iterator], info


def process_call(call_id: str):
    with Session.begin() as db:
        call = db.get(Call, call_id)
        if call is None:
            raise ValueError('Call not found')
        job = get_current_job()
        if job and call.job_id != job.id:
            return
        call.status = 'processing'
        call.started_at = datetime.now(timezone.utc)
        call.finished_at = None
        call.error = None
        storage_name = call.storage_name
    try:
        path = (STORAGE / storage_name).resolve()
        if path.parent != STORAGE:
            raise ValueError('Invalid storage path')
        segments, info = transcribe(path)
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
            job = get_current_job()
            call.status = 'queued' if job and job.retries_left else 'failed'
            call.error = 'Transcription failed; inspect local worker logs'
            call.finished_at = datetime.now(timezone.utc)
        raise


def assess_call(call_id: str):
    with Session.begin() as db:
        call = db.get(Call, call_id)
        if call is None or call.status != 'completed' or call.transcript is None:
            raise ValueError('Completed transcription not found')
        transcript = call.transcript
        segments = call.segments or []
        call.assessment_status = 'processing'
    try:
        segments = infer_roles(segments)
        assessment = assess(transcript, segments)
        with Session.begin() as db:
            call = db.get(Call, call_id)
            call.segments = segments
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
