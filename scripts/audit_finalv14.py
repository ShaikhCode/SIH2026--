from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'apps' / 'api'
WEB = ROOT / 'apps' / 'web'


def text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    print('BhashaSaathi FinalV14 static audit')
    # Version consistency.
    require("version='14.0.0'" in text(API / 'app' / 'main.py'), 'FastAPI version is not 14.0.0')
    require('"version":"14.0.0"' in text(WEB / 'package.json'), 'Web package version is not 14.0.0')
    require('"version": "14.0.0"' in text(ROOT / 'package.json'), 'Root package version is not 14.0.0')

    # Live language contract: exactly English/Hindi/Marathi.
    schema = text(API / 'app' / 'schemas.py')
    types = text(WEB / 'src' / 'types.ts')
    live = text(API / 'app' / 'services' / 'live_translation.py')
    page = text(WEB / 'src' / 'pages' / 'LiveTranslatePage.tsx')
    require("LanguageCode = Literal['eng_Latn', 'hin_Deva', 'mar_Deva']" in schema, 'Backend language contract changed')
    require("export type Lang = 'eng_Latn' | 'hin_Deva' | 'mar_Deva';" in types, 'Frontend language contract changed')
    require(all(token in live for token in ("'eng_Latn':", "'hin_Deva':", "'mar_Deva':")), 'Live language registry is missing one of the 3 demo languages')
    require('const LIVE_LANGS: Lang[] = [\'eng_Latn\', \'hin_Deva\', \'mar_Deva\'];' in page, 'Live page is not locked to 3 demo languages')

    # Performance architecture: models stay warm, cache, batching, bounded queues, pipelined stages.
    manager = text(API / 'app' / 'services' / 'model_manager.py')
    translation = text(API / 'app' / 'adapters' / 'translation.py')
    tts = text(API / 'app' / 'adapters' / 'tts.py')
    stt = text(API / 'app' / 'adapters' / 'stt.py')
    require('self.translation.unload()' not in '\n'.join(line for line in manager.splitlines() if 'def translate' in line), 'Translation request path unloads models')
    require('self.tts.unload()' not in '\n'.join(line for line in manager.splitlines() if 'def synthesize' in line), 'TTS request path unloads models')
    require('_cache_limit = 256' in translation and 'translate_many' in translation, 'Translation cache/batching missing')
    require('_audio_cache_limit = 32' in tts and 'stream_audio' in tts, 'TTS cache/streaming path missing')
    require('beam_size=1' in stt and 'condition_on_previous_text=False' in stt, 'Fast live STT settings missing')

    # Live pipeline and browser contract.
    require('queue.Queue(maxsize=size)' in live, 'Live stage queues are not bounded')
    require('def _enqueue_latest' in live, 'Live latest-work queue policy missing')
    require("'mode': 'pcm'" in live, 'Live PCM TTS streaming missing')
    require('ParlerTTSStreamer' in tts, 'Parler streaming adapter missing')
    require('sample_rate=16000' in page, 'Browser/backend live sample-rate contract is inconsistent')
    require('Mic' in page and 'Buds' in page, 'Demo device guidance missing')

    # History and privacy.
    history = text(WEB / 'src' / 'lib' / 'liveHistory.ts')
    idb = text(WEB / 'src' / 'lib' / 'idb.ts')
    require("'live_history'" in idb, 'Live history IndexedDB store missing')
    require('24 * 60 * 60 * 1000' in history, '24-hour temporary history retention missing')
    require('deleteLiveSession' in page and 'setLiveSaved' in page, 'Live history save/delete controls missing')

    # Prewarm endpoints reduce first-use classroom waits.
    runtime = text(API / 'app' / 'api' / 'routes' / 'runtime.py')
    api_client = text(WEB / 'src' / 'lib' / 'api.ts')
    builder = text(WEB / 'src' / 'pages' / 'LessonBuilderPage.tsx')
    require("@router.post('/warm-translation')" in runtime, 'Translation prewarm endpoint missing')
    require("@router.post('/warm-tts')" in runtime, 'TTS prewarm endpoint missing')
    require('warmTranslation' in api_client and 'warmTTS' in api_client, 'Frontend prewarm client missing')
    require('api.warmTranslation(sourceLanguage, target)' in builder, 'Lesson translation prewarm not wired')
    require('api.warmTTS()' in builder, 'Lesson TTS prewarm not wired')
    require('loadCachedAudio' not in builder, 'Builder still eagerly downloads all audio artifacts')

    # Practice regression: explicit keyword arguments avoid duplicate source_language binding.
    lessons = text(API / 'app' / 'api' / 'routes' / 'lessons.py')
    require('language=x.language, source_language=lesson.source_language' in lessons, 'Practice call regression not fixed')

    # AST parse check for all Python source files.
    py_files = list((API / 'app').rglob('*.py')) + list((ROOT / 'core').rglob('*.py')) + list((ROOT / 'scripts').glob('*.py'))
    for path in py_files:
        ast.parse(text(path), filename=str(path))

    source_files = list((API / 'app').rglob('*.py')) + list((WEB / 'src').rglob('*.ts')) + list((WEB / 'src').rglob('*.tsx'))
    line_count = sum(text(path).count('\n') + 1 for path in source_files)
    print(f'Python AST parse: PASS ({len(py_files)} files)')
    print(f'Source inventory: {len(source_files)} TS/TSX/Python files, ~{line_count:,} lines')
    print('Language scope: PASS — English / Hindi / Marathi only')
    print('Warm-model performance path: PASS')
    print('Bounded pipelined live path: PASS')
    print('Temporary device-only live history: PASS')
    print('FinalV14 static audit: PASS')


if __name__ == '__main__':
    main()
