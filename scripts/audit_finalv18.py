from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = []

def check(name, ok, detail=''):
    checks.append((name, bool(ok), detail))

lesson = (ROOT / 'apps/web/src/pages/LessonBuilderPage.tsx').read_text(encoding='utf-8')
publish = (ROOT / 'apps/api/app/services/publish.py').read_text(encoding='utf-8')
student = (ROOT / 'apps/web/src/pages/StudentLessonPage.tsx').read_text(encoding='utf-8')
lessons = (ROOT / 'apps/api/app/api/routes/lessons.py').read_text(encoding='utf-8')
bg = (ROOT / 'apps/api/app/services/background_prep.py').read_text(encoding='utf-8')

check('No learning-outcome wizard step', 'Understand' not in lesson and 'learning outcome' not in lesson.lower())
check('Publish no longer requires learning outcome', 'LEARNING_OUTCOME_MISSING' not in publish)
check('Translation has explicit teacher approval', 'Approve {label(target)}' in lesson)
check('Meaning Check exists for teacher review', 'api.backTranslate' in lesson and 'Meaning Check' in lesson)
check('Approval response is backgrounded', 'background_tasks.add_task(enqueue_translation_approved' in lessons)
check('Persistent preparation jobs exist', 'class PreparationJob' in (ROOT / 'apps/api/app/models/entities.py').read_text(encoding='utf-8'))
check('Audio generation is background worker', "job.kind == 'tts'" in bg and 'manager.synthesize' in bg)
check('Practice generation is background worker', "job.kind == 'practice'" in bg and 'ensure_practice' in bg)
check('Student can confirm/report translation', 'translationFeedback' in (ROOT / 'apps/web/src/lib/api.ts').read_text(encoding='utf-8') and 'Looks correct' in student and 'Report an issue' in student)
check('Student feedback does not replace teacher publish gate', 'verification_status' in publish and 'PRACTICE_NOT_APPROVED' in publish)
check('Server warms classroom translation routes', 'warm_translation_routes' in (ROOT / 'apps/api/app/services/model_manager.py').read_text(encoding='utf-8'))
check('Adaptive token ceiling enabled', 'adaptive_limit' in (ROOT / 'apps/api/app/adapters/translation.py').read_text(encoding='utf-8'))

failed = 0
for name, ok, detail in checks:
    print(('PASS' if ok else 'FAIL').ljust(5), name, detail)
    if not ok: failed += 1
print(f'\nRESULT: {len(checks)-failed}/{len(checks)} checks passed')
raise SystemExit(1 if failed else 0)
