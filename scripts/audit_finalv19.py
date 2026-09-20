from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'apps' / 'api' / 'app'
WEB = ROOT / 'apps' / 'web' / 'src'

checks: list[tuple[str, bool, str]] = []

def add(name: str, ok: bool, detail: str) -> None:
    checks.append((name, ok, detail))

translation = (API / 'adapters' / 'translation.py').read_text(encoding='utf-8')
config = (API / 'core' / 'config.py').read_text(encoding='utf-8')
lessons = (API / 'api' / 'routes' / 'lessons.py').read_text(encoding='utf-8')
publish = (API / 'services' / 'publish.py').read_text(encoding='utf-8')
web_builder = (WEB / 'pages' / 'LessonBuilderPage.tsx').read_text(encoding='utf-8')
web_api = (WEB / 'lib' / 'api.ts').read_text(encoding='utf-8')

add('No full-lesson tokenizer truncation', 'truncation=False' in translation and 'truncation=True' not in translation, 'translation adapter uses non-truncating tokenization')
add('Long-text token budget exists', '_token_safe_chunks' in translation and 'translation_input_token_budget' in config, 'token-safe chunking path present')
add('Adaptive output ceiling', 'adaptive_limit' in translation and 'retry_indexes' in translation, 'generation ceiling scales and retries affected outputs')
add('No SQLite transaction during inference', 'db.commit()\n        version = current_version(db, lesson)' in lessons, 'source edit is committed before model inference')
add('Publish ignores audio blocker', 'AUDIO_NOT_PREPARED' not in publish, 'audio is not a publication blocker')
add('Publish ignores practice blocker', 'PRACTICE_NOT_APPROVED' not in publish, 'practice is not a publication blocker')
add('Flashcards removed from active API', 'generate-flashcards' not in lessons and 'make_flashcards' not in lessons, 'flashcard route/import removed')
add('Flashcards removed from UI', 'flashcard' not in web_builder.lower() and 'flashcards' not in web_api.lower(), 'no active flashcard button/API call')
add('Parallel target requests', 'Promise.all(targets.map' in web_builder, 'target translation requests launched together')
add('Background publication language gate', 'TEACHER_APPROVED' in publish and 'readiness.publish' in web_builder, 'teacher approval remains the content gate')

print('FinalV19 audit')
print('===============')
for name, ok, detail in checks:
    print(('PASS' if ok else 'FAIL').ljust(5), '-', name, '-', detail)
failed = [name for name, ok, _ in checks if not ok]
print(f'\n{len(checks)-len(failed)}/{len(checks)} checks passed')
raise SystemExit(1 if failed else 0)
