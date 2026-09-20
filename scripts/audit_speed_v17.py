from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = {
    'interactive beams=1': "text_translation_beams: int = 1" in (ROOT/'apps/api/app/core/config.py').read_text(),
    'live beams=1': "live_translation_beams: int = 1" in (ROOT/'apps/api/app/core/config.py').read_text(),
    'live TTS 0.5s': "live_tts_stream_seconds: float = 0.5" in (ROOT/'apps/api/app/core/config.py').read_text(),
    'translation max tokens': "translation_max_new_tokens: int = 128" in (ROOT/'apps/api/app/core/config.py').read_text(),
    'single-request translate source payload': "source_text: str | None" in (ROOT/'apps/api/app/schemas.py').read_text(),
    'translation server cache': 'Database-level cache' in (ROOT/'apps/api/app/api/routes/lessons.py').read_text(),
    'translation timings': "'translation_ms'" in (ROOT/'apps/api/app/api/routes/lessons.py').read_text(),
    'TTS timings': "'tts_ms'" in (ROOT/'apps/api/app/api/routes/lessons.py').read_text(),
    'audio artifact returned inline': "'artifact': {" in (ROOT/'apps/api/app/api/routes/lessons.py').read_text(),
    'no lesson TTS warm on builder mount': 'api.warmTTS()' not in (ROOT/'apps/web/src/pages/LessonBuilderPage.tsx').read_text(),
    'no parallel generate-target CPU calls': 'Promise.allSettled(pendingTargets.map' not in (ROOT/'apps/web/src/pages/LessonBuilderPage.tsx').read_text(),
    'no post-TTS full lesson refetch': 'const fresh = await api.lesson(lessonId)' not in (ROOT/'apps/web/src/pages/LessonBuilderPage.tsx').read_text(),
    'live history persistence non-blocking': 'void persistCurrentSession();' in (ROOT/'apps/web/src/pages/LiveTranslatePage.tsx').read_text(),
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(('PASS ' if ok else 'FAIL ') + name)
print(f'CHECKS={len(checks)} FAILURES={len(failed)}')
raise SystemExit(1 if failed else 0)
