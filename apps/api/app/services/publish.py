from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Artifact, Lesson, LessonVersion, PracticeQuestion, Translation


def now():
    return datetime.now(timezone.utc)


def can_publish(db: Session, lesson: Lesson, version: LessonVersion) -> tuple[bool, list[str]]:
    problems: list[str] = []
    translations = {
        row.target_language: row
        for row in db.query(Translation).filter_by(lesson_version_id=version.id).all()
    }
    required = ('eng_Latn', 'sat_Olck')
    for lang in required:
        row = translations.get(lang)
        if not row:
            problems.append(f'MISSING_TRANSLATION:{lang}')
            continue
        if not row.translated_text.strip():
            problems.append(f'EMPTY_TRANSLATION:{lang}')
        if row.verification_status != 'TEACHER_APPROVED':
            problems.append(f'TRANSLATION_NOT_APPROVED:{lang}')
        flags = set(json.loads(row.flags_json or '[]'))
        blocking = {
            'EMPTY_OUTPUT',
            'TARGET_SCRIPT_ANOMALY',
            'NUMBER_MISMATCH',
            'SOURCE_LANGUAGE_LEAKAGE',
            'LENGTH_ANOMALY',
        }
        if flags & blocking:
            problems.append(f'TRANSLATION_FLAGS:{lang}')
        if row.confidence < 0.60:
            problems.append(f'LOW_TRANSLATION_CONFIDENCE:{lang}')

    if not version.source_text.strip() and not version.clean_transcript.strip():
        problems.append('SOURCE_TEXT_MISSING')
    if not json.loads(version.learning_objectives_json or '[]'):
        problems.append('LEARNING_OUTCOME_MISSING')
    if not json.loads(version.concepts_json or '[]'):
        problems.append('CONCEPTS_MISSING')

    approved_questions = db.query(PracticeQuestion).filter_by(
        lesson_version_id=version.id,
        approved=True,
    ).count()
    approved_santhali = db.query(PracticeQuestion).filter_by(
        lesson_version_id=version.id,
        language='sat_Olck',
        approved=True,
    ).count()
    if approved_questions == 0:
        problems.append('PRACTICE_NOT_APPROVED')
    if approved_santhali == 0:
        problems.append('SANTHALI_PRACTICE_NOT_APPROVED')

    # The SIH demo promise includes target-language synthesized audio. Require the
    # approved Santhali artifact before a lesson can become learner-facing.
    santhali_audio = db.query(Artifact).filter_by(
        lesson_version_id=version.id,
        type='audio',
        language='sat_Olck',
    ).count()
    if santhali_audio == 0:
        problems.append('SANTHALI_AUDIO_NOT_PREPARED')

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
