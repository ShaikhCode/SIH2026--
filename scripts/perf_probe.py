from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'apps' / 'api'
sys.path.insert(0, str(API))

from app.services.model_manager import manager  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='BhashaSaathi local translation/TTS warm-path benchmark.')
    parser.add_argument('--source', default='hin_Deva')
    parser.add_argument('--target', default='eng_Latn')
    parser.add_argument('--text', default='हमारी कक्षा में पौधों के बारे में सीखते हैं।')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--tts', action='store_true')
    args = parser.parse_args()

    print('BhashaSaathi Performance Probe V17')
    print(f'source={args.source} target={args.target} repeats={args.repeat}')
    print(f'torch_threads={manager.status()["performance"]["torch_threads"]}')

    warm_start = time.perf_counter()
    manager.warm_translation(args.source, args.target, fast=True)
    print(f'warm_ms={1000*(time.perf_counter()-warm_start):.1f}')

    samples = []
    for i in range(max(1, args.repeat)):
        t0 = time.perf_counter()
        out = manager.translate(args.text, args.source, args.target, fast=True)
        elapsed = 1000*(time.perf_counter()-t0)
        samples.append(elapsed)
        print(f'run={i+1} ms={elapsed:.1f} text={out}')

    print(f'mean_ms={statistics.mean(samples):.1f}')
    print(f'min_ms={min(samples):.1f}')
    print(f'max_ms={max(samples):.1f}')

    if args.tts:
        speaker = manager.tts.speaker_for(args.target)
        t0 = time.perf_counter()
        manager.synthesize_bytes(out, args.target, speaker)
        print(f'tts_first_generation_ms={1000*(time.perf_counter()-t0):.1f}')
        t0 = time.perf_counter()
        manager.synthesize_bytes(out, args.target, speaker)
        print(f'tts_cached_generation_ms={1000*(time.perf_counter()-t0):.1f}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
