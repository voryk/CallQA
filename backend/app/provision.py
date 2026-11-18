"""Download a Whisper model during installation, before processing private audio."""

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    'tiny': 'Systran/faster-whisper-tiny',
    'base': 'Systran/faster-whisper-base',
    'small': 'Systran/faster-whisper-small',
    'medium': 'Systran/faster-whisper-medium',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('size', choices=MODELS)
    parser.add_argument('--output', type=Path, default=Path('/srv/models/whisper'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=MODELS[args.size], local_dir=str(args.output))
    for name in ('model.bin', 'config.json'):
        if not (args.output / name).is_file():
            raise RuntimeError(f'Missing model file: {name}')
    print(f'Model ready: {args.output}')


if __name__ == '__main__':
    main()
