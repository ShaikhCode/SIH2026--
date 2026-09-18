from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import Lesson, LessonVersion, Translation

def now(): return datetime.now(timezone.utc)

def can_publish(db: Session, lesson: Lesson, version: LessonVersion) -> tuple[bool,list[str]]:
    problems=[]
    translations=db.query(Translation).filter_by(lesson_version_id=version.id).all()
    if not translations: problems.append('NO_TRANSLATIONS')
    for t in translations:
        if t.verification_status!='TEACHER_APPROVED': problems.append(f'TRANSLATION_NOT_APPROVED:{t.target_language}')
        if any(flag in {'EMPTY_OUTPUT','TARGET_SCRIPT_ANOMALY','NUMBER_MISMATCH','SOURCE_LANGUAGE_LEAKAGE'} for flag in __import__('json').loads(t.flags_json or '[]')):
            problems.append(f'TRANSLATION_FLAGS:{t.target_language}')
    if lesson.source_language!='sat_Olck' and not any(t.target_language=='sat_Olck' and t.verification_status=='TEACHER_APPROVED' for t in translations):
        problems.append('SANTHALI_APPROVAL_REQUIRED_FOR_SHOWCASE')
    return not problems, problems

def publish(db: Session, lesson: Lesson, version: LessonVersion):
    ok,problems=can_publish(db,lesson,version)
    if not ok: return False,problems
    version.approved_at=version.approved_at or now(); version.published_at=now(); lesson.status='PUBLISHED'; db.commit()
    return True,[]
