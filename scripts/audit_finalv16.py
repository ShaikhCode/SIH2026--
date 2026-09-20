from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
texts = {
    'lessons': (ROOT/'apps/api/app/api/routes/lessons.py').read_text(encoding='utf-8'),
    'live_service': (ROOT/'apps/api/app/services/live_translation.py').read_text(encoding='utf-8'),
    'live_web': (ROOT/'apps/web/src/pages/LiveTranslatePage.tsx').read_text(encoding='utf-8'),
    'builder': (ROOT/'apps/web/src/pages/LessonBuilderPage.tsx').read_text(encoding='utf-8'),
}
checks = {
    'lesson_fast_translation': "manager.translate(text, src, tgt, fast=True)" in texts['lessons'],
    'audio_invalidation_on_translation_change': "type='audio', language=x.target_language" in texts['lessons'],
    'live_explicit_audio_play': 'await audio.play()' in texts['live_web'],
    'live_audio_ready_status': "'type': 'audio_ready'" in texts['live_service'],
    'background_audio_ui': 'audio-prep-list' in texts['builder'],
    'audio_no_second_approval_copy': 'Audio generation will continue in the background.' in texts['builder'],
    'demo_languages_only': "'eng_Latn', 'hin_Deva', 'mar_Deva'" in texts['live_web'],
}
for name, ok in checks.items():
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
if not all(checks.values()):
    raise SystemExit(1)
print('FINALV16 AUDIT: PASS')
