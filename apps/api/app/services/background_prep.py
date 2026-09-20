from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from ..core.config import STORAGE_ROOT
from ..db.session import SessionLocal
from ..models import Artifact, Lesson, LessonVersion, PreparationJob, PracticeQuestion, Translation
from ..services.artifacts import register_file, sha256_file
from ..services.content import ensure_practice
from ..services.model_manager import manager

logger = logging.getLogger('bhashasaathi.background')

# Audio is the long pole, so it gets its own ordered worker. Practice is separate
# so a slow TTS job never makes practice appear "stuck" behind it.
_tts_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='bhashasaathi-tts')
_practice_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='bhashasaathi-practice')


def _now():
    return datetime.now(timezone.utc)


def _ensure_job(db, version_id: int, kind: str, language: str = '') -> PreparationJob:
    job = db.query(PreparationJob).filter_by(
        lesson_version_id=version_id, kind=kind, language=language,
    ).first()
    if job:
        if job.status == 'FAILED':
            job.status = 'QUEUED'
            job.error = None
            job.finished_at = None
            db.commit()
        return job
    job = PreparationJob(
        lesson_version_id=version_id,
        kind=kind,
        language=language,
        status='QUEUED',
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
        return job
    except IntegrityError:
        db.rollback()
        job = db.query(PreparationJob).filter_by(
            lesson_version_id=version_id, kind=kind, language=language,
        ).first()
        if not job:
            raise
        return job


def _submit(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(PreparationJob, job_id)
        if not job:
            return
        executor = _tts_executor if job.kind == 'tts' else _practice_executor
    finally:
        db.close()
    executor.submit(_run_job, job_id)


def enqueue_translation_approved(lesson_id: int, version_id: int, target_language: str) -> None:
    """Queue downstream work after the human approves translated text.

    Approval itself remains a tiny foreground operation. Audio/practice are
    independent downstream jobs and are never required before publishing.
    """
    db = SessionLocal()
    try:
        lesson = db.get(Lesson, lesson_id)
        version = db.get(LessonVersion, version_id)
        if not lesson or not version:
            return
        created: list[int] = []

        for kind, language in (('tts', target_language), ('practice', target_language)):
            job = _ensure_job(db, version.id, kind, language)
            if job.status in {'QUEUED', 'FAILED'}:
                created.append(job.id)

        required = [lang for lang in ('eng_Latn', 'hin_Deva', 'mar_Deva') if lang != lesson.source_language]
        approved = {
            row.target_language
            for row in db.query(Translation).filter_by(lesson_version_id=version.id).all()
            if row.verification_status == 'TEACHER_APPROVED' and row.translated_text.strip()
        }
        if required and set(required).issubset(approved):
            for lang in required:
                job = _ensure_job(db, version.id, 'practice', lang)
                if job.status in {'QUEUED', 'FAILED'}:
                    created.append(job.id)
        db.commit()
    finally:
        db.close()

    for job_id in dict.fromkeys(created):
        _submit(job_id)


def enqueue_retry(version_id: int, kind: str, language: str = '') -> int:
    db = SessionLocal()
    try:
        job = _ensure_job(db, version_id, kind, language)
        job.status = 'QUEUED'
        job.error = None
        job.finished_at = None
        db.commit()
        job_id = job.id
    finally:
        db.close()
    _submit(job_id)
    return job_id


def _set_status(db, job: PreparationJob, status: str, error: str | None = None):
    job.status = status
    job.error = error
    if status == 'RUNNING':
        job.started_at = _now()
    if status in {'READY', 'FAILED'}:
        job.finished_at = _now()
    db.commit()


def _run_tts(db: SessionLocal, job: PreparationJob, lesson: Lesson, version: LessonVersion) -> None:
    lang = job.language
    translation = db.query(Translation).filter_by(
        lesson_version_id=version.id, target_language=lang,
    ).first()
    if not translation or translation.verification_status != 'TEACHER_APPROVED' or not translation.translated_text.strip():
        return

    # Re-check the exact version immediately before generating so an edited source
    # cannot produce stale audio. The translation approval endpoint invalidates old
    # artifacts when text changes.
    cache = STORAGE_ROOT / 'tts_cache'
    cache.mkdir(parents=True, exist_ok=True)
    speaker = 'classroom_teacher'
    key = hashlib.sha256((translation.translated_text.strip() + '|' + lang + '|' + speaker + '|v4').encode('utf-8')).hexdigest()
    path = cache / f'{key}.wav'

    if not path.exists():
        manager.synthesize(translation.translated_text, path, lang, speaker)

    # The lesson may have been edited while a long local TTS generation was
    # running. Re-read the authoritative translation before publishing the audio
    # artifact so stale speech can never attach to the new lesson version.
    current_translation = db.query(Translation).filter_by(
        lesson_version_id=version.id, target_language=lang,
    ).first()
    if (
        not current_translation
        or current_translation.verification_status != 'TEACHER_APPROVED'
        or current_translation.translated_text.strip() != translation.translated_text.strip()
    ):
        return

    digest = sha256_file(path)
    existing = db.query(Artifact).filter_by(
        lesson_version_id=version.id, type='audio', language=lang,
    ).first()
    if existing and existing.sha256 == digest:
        return
    if existing:
        db.delete(existing)
        db.flush()
    register_file(db, version.id, 'audio', lang, path, 'audio/wav', {'cache_key': key, 'speaker': speaker})
    db.commit()


def _run_practice(db: SessionLocal, job: PreparationJob, lesson: Lesson, version: LessonVersion) -> None:
    lang = job.language
    ensure_practice(
        db=db,
        version=version,
        language=lang,
        source_language=lesson.source_language,
        count=4,
        approved=False,
        translate_fn=manager.translate,
        translate_many_fn=manager.translate_many,
    )


def _run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(PreparationJob, job_id)
        if not job or job.status == 'READY':
            return
        lesson_version = db.get(LessonVersion, job.lesson_version_id)
        lesson = db.get(Lesson, lesson_version.lesson_id) if lesson_version else None
        if not lesson_version or not lesson:
            if job:
                _set_status(db, job, 'FAILED', 'Lesson version no longer exists.')
            return
        _set_status(db, job, 'RUNNING')
        if job.kind == 'tts':
            _run_tts(db, job, lesson, lesson_version)
        elif job.kind == 'practice':
            _run_practice(db, job, lesson, lesson_version)
        else:
            raise ValueError(f'Unsupported preparation job: {job.kind}')
        _set_status(db, job, 'READY')
    except Exception as exc:
        logger.exception('Background preparation failed job_id=%s', job_id)
        try:
            job = db.get(PreparationJob, job_id)
            if job:
                _set_status(db, job, 'FAILED', str(exc)[:1000])
        except Exception:
            logger.exception('Could not persist background failure job_id=%s', job_id)
    finally:
        db.close()


def preparation_views(db, version_id: int) -> list[dict]:
    rows = db.query(PreparationJob).filter_by(lesson_version_id=version_id).order_by(PreparationJob.id.asc()).all()
    return [
        {
            'id': row.id,
            'kind': row.kind,
            'language': row.language,
            'status': row.status,
            'error': row.error,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'started_at': row.started_at.isoformat() if row.started_at else None,
            'finished_at': row.finished_at.isoformat() if row.finished_at else None,
        }
        for row in rows
    ]


def resume_pending_preparations() -> None:
    db = SessionLocal()
    try:
        rows = db.query(PreparationJob).filter(PreparationJob.status.in_(['QUEUED', 'RUNNING'])).all()
        ids = []
        for row in rows:
            row.status = 'QUEUED'
            row.started_at = None
            row.finished_at = None
            ids.append(row.id)
        db.commit()
    finally:
        db.close()
    for job_id in ids:
        _submit(job_id)
