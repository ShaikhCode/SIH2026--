"""Isolated local-model verification for the final BhashaSaathi build.

Run from the repository root after activating apps/api/.venv.
This is intentionally independent from the UI so each model stage can be proven
before the product is blamed for a model/runtime issue.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'apps' / 'api'
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from app.adapters.stt import FasterWhisperAdapter, LANGUAGE_TO_WHISPER  # noqa: E402
from app.adapters.translation import IndicTrans2Adapter  # noqa: E402
from app.adapters.tts import IndicParlerTTSAdapter  # noqa: E402
from app.core.config import MODELS_ROOT, settings  # noqa: E402


def translation_test(adapter: IndicTrans2Adapter, src: str, tgt: str, text: str) -> bool:
    print(f'\n[TRANSLATION] {src} -> {tgt}')
    print('Source:', text)
    try:
        output = adapter.translate(text, src, tgt)
    except Exception as exc:
        print('FAIL:', type(exc).__name__, exc)
        return False
    print('Target:', output)
    return bool(output.strip())


def whisper_test(adapter: FasterWhisperAdapter, audio: Path, lang: str | None) -> bool:
    print(f'\n[WHISPER] {audio}')
    selected = LANGUAGE_TO_WHISPER.get(lang) if lang else None
    print('Language override:', selected or 'auto')
    try:
        result = adapter.transcribe(audio, selected)
    except Exception as exc:
        print('FAIL:', type(exc).__name__, exc)
        return False
    print('Detected:', result['language'], 'probability:', result['probability'])
    print('Text:', result['text'])
    return bool(result['text'].strip())


def tts_test(adapter: IndicParlerTTSAdapter, text: str, language: str) -> bool:
    print(f'\n[TTS] {language}')
    out = ROOT / 'data' / 'diagnostics' / f'tts_{language}.wav'
    try:
        result = adapter.synthesize(text, out, language, 'classroom_teacher')
    except Exception as exc:
        print('FAIL:', type(exc).__name__, exc)
        print('TTS health:', adapter.health())
        return False
    print('WAV:', result['path'])
    print('Duration:', result['duration_seconds'], 'seconds')
    return out.is_file() and out.stat().st_size > 44


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-tts', action='store_true')
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--stt-language', choices=['eng_Latn', 'hin_Deva', 'mar_Deva'])
    args = parser.parse_args()

    print('BhashaSaathi local-model laboratory')
    print('Model root:', MODELS_ROOT)
    print('CPU only:', settings.cpu_only)

    translation = IndicTrans2Adapter(MODELS_ROOT, settings.cpu_only, settings.max_translation_chars)
    stt = FasterWhisperAdapter(MODELS_ROOT, settings.cpu_only)
    tts = IndicParlerTTSAdapter(MODELS_ROOT, settings.cpu_only, settings.parler_description_tokenizer)

    results = []
    results.append(translation_test(translation, 'eng_Latn', 'hin_Deva', 'Welcome to our classroom.'))
    results.append(translation_test(translation, 'hin_Deva', 'eng_Latn', 'हमारी कक्षा में आपका स्वागत है।'))
    results.append(translation_test(translation, 'hin_Deva', 'mar_Deva', 'पौधों को पानी की आवश्यकता होती है।'))

    if args.audio:
        results.append(whisper_test(stt, args.audio, args.stt_language))
    else:
        print('\n[WHISPER] skipped — pass --audio path\\to\\recording.wav to run a real recording test.')

    if not args.skip_tts:
        results.append(tts_test(tts, 'Welcome to our classroom.', 'eng_Latn'))
    else:
        print('\n[TTS] skipped')

    print('\nRESULT:', 'PASS' if all(results) else 'CHECK FAILED STAGE(S)')
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
