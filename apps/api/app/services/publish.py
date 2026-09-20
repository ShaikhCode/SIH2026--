from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Lesson, LessonVersion, Translation


def now():
    return datetime.now(timezone.utc)


def can_publish(db: Session, lesson: Lesson, version: LessonVersion) -> tuple[bool, list[str]]:
    """Only the human-approved translated text is publication-critical.

    Audio and practice are downstream background deliverables. They may still be
    running when the lesson is published and can complete against the same exact
    lesson version afterwards. Validation flags remain visible as warnings, but an
    explicit teacher approval is the human override for a flagged translation.
    """
    problems: list[str] = []
    translations = {
        row.target_language: row
        for row in db.query(Translation).filter_by(lesson_version_id=version.id).all()
    }
    all_languages = ('eng_Latn', 'hin_Deva', 'mar_Deva')
    required = tuple(language for language in all_languages if language != lesson.source_language)

    if not version.source_text.strip() and not version.clean_transcript.strip():
        problems.append('SOURCE_TEXT_MISSING')

    for lang in required:
        row = translations.get(lang)
        if not row:
            problems.append(f'MISSING_TRANSLATION:{lang}')
            continue
        if not row.translated_text.strip():
            problems.append(f'EMPTY_TRANSLATION:{lang}')
            continue
        if row.verification_status != 'TEACHER_APPROVED':
            problems.append(f'TRANSLATION_NOT_APPROVED:{lang}')

    return not problems, problems


def publish(db: Session, lesson: Lesson, version: LessonVersion):
    ok, problems = can_publish(db, lesson, version)
    if not ok:
        return False, problems
    stamp = now()
    version.approved_at = version.approved_at or stamp
    version.published_at = stamp
    lesson.status = 'PUBLISHED'
    db.commit()
    return True, []
