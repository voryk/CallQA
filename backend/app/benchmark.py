"""Run offline against a real local audio file; never invent timings."""
import argparse
import json
import time
import os
from app.worker import get_model

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('audio')
    args = p.parse_args()
    start = time.perf_counter()
    model = get_model()
    loaded = time.perf_counter()
    segments, info = model.transcribe(args.audio, beam_size=int(os.getenv('WHISPER_BEAM_SIZE','1')), vad_filter=True)
    count = sum(1 for _ in segments)
    elapsed = time.perf_counter() - start
    print(json.dumps({'audio_seconds': info.duration, 'cold_total_seconds': round(elapsed,2), 'model_load_seconds': round(loaded-start,2), 'segments': count, 'meets_300_seconds': elapsed <= 300, 'threads': os.getenv('WHISPER_THREADS','4'), 'beam_size': os.getenv('WHISPER_BEAM_SIZE','1')}, ensure_ascii=False))
