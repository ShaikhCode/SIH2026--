import hashlib
import json
import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ...adapters.translation import IndicTrans2Adapter
from ...core.config import STORAGE_ROOT, settings
from ...core.security import current_user, require_admin
from ...db import get_db
from ...layer2.service import Layer2Engine
from ...models import Artifact, Group, Lesson, LessonVersion, Membership, PracticeQuestion, Translation
from ...schemas import (
    FlashcardIn,
    LessonCreateIn,
    LessonPatchIn,
    PracticeApprovalIn,
    PracticeGenerateIn,
    TTSIn,
    TranslateIn,
    VerifyIn,
    VersionCreateIn,
)
from ...services.artifacts import register_file, sha256_file
from ...services.content import analyze_source, ensure_practice
from ...services.model_manager import manager
from ...services.publish import publish
from ...services.worksheet import make_flashcards, make_worksheet

router = APIRouter(tags=['lessons'])
logger = logging.getLogger('bhashasaathi.lessons')


def db_lesson(db: Session, lesson_id: int) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, detail={'code': 'LESSON_NOT_FOUND', 'message': 'Lesson not found.'})
    return lesson


def current_version(db: Session, lesson: Lesson) -> LessonVersion:
    if not lesson.current_version_id:
        raise HTTPException(400, detail={'code': 'NO_VERSION', 'message': 'This lesson has no active version yet.'})
    version = db.get(LessonVersion, lesson.current_version_id)
    if not version:
        raise HTTPException(500, detail={'code': 'VERSION_MISSING', 'message': 'The active lesson version is missing.'})
    return version


def require_group_owner(db: Session, lesson: Lesson, user) -> Group:
    group = db.get(Group, lesson.group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(403, detail={'code': 'LESSON_EDIT_DENIED', 'message': 'You do not have permission to edit this lesson.'})
    return group


def can_read_lesson(db: Session, lesson: Lesson, user) -> bool:
    group = db.get(Group, lesson.group_id)
    if not group:
        return False
    if user.account_role == 'admin' and group.owner_id == user.id:
        return True
    return bool(db.query(Membership).filter_by(group_id=lesson.group_id, user_id=user.id).first()) and lesson.status == 'PUBLISHED'


def lesson_summary(db: Session, lesson: Lesson) -> dict:
    version = db.get(LessonVersion, lesson.current_version_id) if lesson.current_version_id else None
    return {
        'id': lesson.id,
        'group_id': lesson.group_id,
        'title': lesson.title,
        'grade': lesson.grade,
        'subject': lesson.subject,
        'topic': lesson.topic,
        'source_language': lesson.source_language,
        'status': lesson.status,
        'current_version_id': lesson.current_version_id,
        'version_number': version.version_number if version else None,
        'updated_at': lesson.updated_at.isoformat() if lesson.updated_at else None,
    }


def version_view(version: LessonVersion) -> dict:
    return {
        'id': version.id,
        'version_number': version.version_number,
        'source_text': version.source_text,
        'clean_transcript': version.clean_transcript,
        'learning_objectives': json.loads(version.learning_objectives_json or '[]'),
        'concepts': json.loads(version.concepts_json or '[]'),
        'ai_explanation': json.loads(version.ai_explanation_json or '{}'),
        'activities': json.loads(version.activities_json or '[]'),
        'approved_at': version.approved_at.isoformat() if version.approved_at else None,
        'published_at': version.published_at.isoformat() if version.published_at else None,
    }


def _practice_view(question: PracticeQuestion) -> dict:
    return {
        'id': question.id,
        'concept_id': question.concept_id,
        'prompt': question.prompt,
        'options': json.loads(question.options_json or '[]'),
        'correct_answer': question.correct_answer,
        'explanation': question.explanation,
        'language': question.language,
        'question_type': question.question_type,
        'approved': bool(question.approved),
    }


def pack(db: Session, lesson: Lesson, *, include_pending: bool = False) -> dict:
    version = current_version(db, lesson)
    translations = db.query(Translation).filter_by(lesson_version_id=version.id).order_by(Translation.target_language).all()
    artifacts = db.query(Artifact).filter_by(lesson_version_id=version.id).order_by(Artifact.id.desc()).all()
    all_questions = db.query(PracticeQuestion).filter_by(lesson_version_id=version.id).order_by(PracticeQuestion.id.asc()).all()
    visible_questions = all_questions if include_pending else [q for q in all_questions if q.approved]
    worksheet = make_worksheet(lesson, version, translations)
    flashcards = make_flashcards(lesson, version, translations)
    translations_view = [
        {
            'id': item.id,
            'language': item.target_language,
            'text': item.translated_text,
            'confidence': item.confidence,
            'flags': json.loads(item.flags_json or '[]'),
            'validation': json.loads(item.validation_json or '{}'),
            'verification_status': item.verification_status,
            'teacher_edited': item.teacher_edited,
            'native_review_status': item.native_review_status,
        }
        for item in translations
    ]
    return {
        'lesson': lesson_summary(db, lesson),
        'version': version_view(version),
        'worksheet_html': worksheet['html'],
        'worksheet_meta': {k: worksheet[k] for k in ('learning_outcome', 'concepts', 'language_a', 'language_b')},
        'flashcards': flashcards,
        'translations': translations_view,
        'artifacts': [
            {
                'id': artifact.id,
                'type': artifact.type,
                'language': artifact.language,
                'mime_type': artifact.mime_type,
                'size_bytes': artifact.size_bytes,
                'sha256': artifact.sha256,
                'url': f'/api/v1/artifacts/{artifact.id}',
            }
            for artifact in artifacts
        ],
        'practice': [_practice_view(q) for q in visible_questions if q.approved],
        'practice_all': [_practice_view(q) for q in all_questions] if include_pending else [],
    }


def concept_rows(values: list[str]) -> list[dict]:
    result = []
    for value in values:
        label = value.strip()
        if not label:
            continue
        result.append({'concept_id': label.lower().replace(' ', '_'), 'label': label, 'keywords': [label], 'importance': 'core'})
    return result


@router.post('/groups/{group_id}/lessons')
def create_lesson(group_id: int, x: LessonCreateIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, detail={'code': 'GROUP_NOT_FOUND', 'message': 'Classroom not found.'})
    if group.owner_id != user.id:
        raise HTTPException(403, detail={'code': 'GROUP_EDIT_DENIED', 'message': 'You do not own this classroom.'})
    title = x.title.strip()
    source = x.source_text.strip()
    lesson = Lesson(
        group_id=group_id,
        title=title,
        grade=x.grade.strip(),
        subject=x.subject.strip(),
        topic=x.topic.strip(),
        source_language=x.source_language,
        status='DRAFT',
        created_by=user.id,
    )
    db.add(lesson)
    db.flush()
    version = LessonVersion(
        lesson_id=lesson.id,
        version_number=1,
        source_text=source,
        clean_transcript=source,
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    lesson.current_version_id = version.id
    db.commit()
    db.refresh(lesson)
    return lesson_summary(db, lesson)


@router.get('/groups/{group_id}/lessons')
def list_lessons(group_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, detail={'code': 'GROUP_NOT_FOUND', 'message': 'Classroom not found.'})
    is_owner = group.owner_id == user.id
    is_member = bool(db.query(Membership).filter_by(group_id=group_id, user_id=user.id).first())
    if not (is_owner or is_member):
        raise HTTPException(403, detail={'code': 'GROUP_ACCESS_DENIED', 'message': 'You are not a member of this classroom.'})
    query = db.query(Lesson).filter(Lesson.group_id == group_id)
    # Classroom drafts are private to the classroom owner. Membership—regardless
    # of the member's global account role—only grants access to published lessons.
    if not is_owner:
        query = query.filter(Lesson.status == 'PUBLISHED')
    return [lesson_summary(db, lesson) for lesson in query.order_by(Lesson.updated_at.desc()).all()]


@router.get('/lessons/{lesson_id}')
def get_lesson(lesson_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    lesson = db_lesson(db, lesson_id)
    if not can_read_lesson(db, lesson, user):
        raise HTTPException(403, detail={'code': 'LESSON_ACCESS_DENIED', 'message': 'This lesson is not available to your account.'})
    include_pending = user.account_role == 'admin'
    return pack(db, lesson, include_pending=include_pending)


@router.patch('/lessons/{lesson_id}')
def patch_lesson(lesson_id: int, x: LessonPatchIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    changes_requested = any(value is not None for value in (x.source_text, x.clean_transcript, x.learning_outcome, x.concepts)) or x.title is not None or x.topic is not None

    if lesson.status == 'PUBLISHED' and changes_requested:
        outcome = [x.learning_outcome] if x.learning_outcome is not None else json.loads(version.learning_objectives_json or '[]')
        concepts = concept_rows(x.concepts) if x.concepts is not None else json.loads(version.concepts_json or '[]')
        new_version = LessonVersion(
            lesson_id=lesson.id,
            version_number=version.version_number + 1,
            source_text=x.source_text if x.source_text is not None else version.source_text,
            clean_transcript=x.clean_transcript if x.clean_transcript is not None else version.clean_transcript,
            learning_objectives_json=json.dumps(outcome, ensure_ascii=False),
            concepts_json=json.dumps(concepts, ensure_ascii=False),
            created_by=user.id,
        )
        db.add(new_version)
        db.flush()
        lesson.current_version_id = new_version.id
        lesson.status = 'DRAFT'
        if x.title is not None:
            lesson.title = x.title.strip()
        if x.topic is not None:
            lesson.topic = x.topic.strip()
        db.commit()
        return pack(db, lesson, include_pending=True)

    if x.title is not None:
        lesson.title = x.title.strip()
    if x.topic is not None:
        lesson.topic = x.topic.strip()
    if x.source_text is not None:
        version.source_text = x.source_text
    if x.clean_transcript is not None:
        version.clean_transcript = x.clean_transcript
    if x.learning_outcome is not None:
        version.learning_objectives_json = json.dumps([x.learning_outcome.strip()] if x.learning_outcome.strip() else [], ensure_ascii=False)
    if x.concepts is not None:
        version.concepts_json = json.dumps(concept_rows(x.concepts), ensure_ascii=False)
    if lesson.status not in {'PUBLISHED'}:
        lesson.status = 'DRAFT'
    db.commit()
    return pack(db, lesson, include_pending=True)


@router.delete('/lessons/{lesson_id}')
def delete_lesson(lesson_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    versions = db.query(LessonVersion).filter_by(lesson_id=lesson.id).all()
    lesson.current_version_id = None
    db.flush()
    for version in versions:
        db.query(Translation).filter_by(lesson_version_id=version.id).delete(synchronize_session=False)
        db.query(Artifact).filter_by(lesson_version_id=version.id).delete(synchronize_session=False)
        db.query(PracticeQuestion).filter_by(lesson_version_id=version.id).delete(synchronize_session=False)
        db.delete(version)
    db.delete(lesson)
    db.commit()
    return {'ok': True}


@router.post('/lessons/{lesson_id}/versions')
def new_version(lesson_id: int, x: VersionCreateIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    previous = current_version(db, lesson)
    outcome = [x.learning_outcome] if x.learning_outcome else json.loads(previous.learning_objectives_json or '[]')
    concepts = concept_rows(x.concepts) if x.concepts is not None else json.loads(previous.concepts_json or '[]')
    version = LessonVersion(
        lesson_id=lesson.id,
        version_number=previous.version_number + 1,
        source_text=x.source_text if x.source_text is not None else previous.source_text,
        clean_transcript=x.clean_transcript if x.clean_transcript is not None else previous.clean_transcript,
        learning_objectives_json=json.dumps(outcome, ensure_ascii=False),
        concepts_json=json.dumps(concepts, ensure_ascii=False),
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    lesson.current_version_id = version.id
    lesson.status = 'DRAFT'
    db.commit()
    return pack(db, lesson, include_pending=True)


@router.get('/lessons/{lesson_id}/versions')
def versions(lesson_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    rows = db.query(LessonVersion).filter_by(lesson_id=lesson.id).order_by(LessonVersion.version_number.desc()).all()
    return [
        {
            'id': version.id,
            'version_number': version.version_number,
            'created_at': version.created_at.isoformat(),
            'published_at': version.published_at.isoformat() if version.published_at else None,
            'approved_at': version.approved_at.isoformat() if version.approved_at else None,
        }
        for version in rows
    ]


@router.post('/lessons/{lesson_id}/rollback')
def rollback(lesson_id: int, version_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = db.get(LessonVersion, version_id)
    if not version or version.lesson_id != lesson.id or not version.published_at:
        raise HTTPException(400, detail={'code': 'VERSION_NOT_PUBLISHED', 'message': 'Only a published version of this lesson can be restored.'})
    lesson.current_version_id = version.id
    lesson.status = 'PUBLISHED'
    db.commit()
    return pack(db, lesson, include_pending=True)


@router.post('/lessons/{lesson_id}/analyze')
def analyze(lesson_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    text = (version.clean_transcript or version.source_text).strip()
    if not text:
        raise HTTPException(400, detail={'code': 'SOURCE_REQUIRED', 'message': 'Add or record the lesson source before analysis.'})
    result = analyze_source(text, lesson.grade, lesson.subject, lesson.topic)
    version.concepts_json = json.dumps(result['concepts'], ensure_ascii=False)
    version.learning_objectives_json = json.dumps([result['learning_objective']], ensure_ascii=False)
    version.ai_explanation_json = json.dumps({'explanation': result['explanation']}, ensure_ascii=False)
    version.activities_json = json.dumps(result['activities'], ensure_ascii=False)
    lesson.topic = result['topic']
    lesson.status = 'AI_SUGGESTED'
    db.commit()
    return result


@router.post('/lessons/{lesson_id}/translate')
def translate(lesson_id: int, x: TranslateIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    if x.target_language == lesson.source_language:
        raise HTTPException(400, detail={'code': 'SAME_LANGUAGE', 'message': 'Choose a language different from the source language.'})
    if not settings.translation_enabled:
        raise HTTPException(503, detail={'code': 'TRANSLATION_DISABLED', 'message': 'Translation is disabled in this local profile.'})
    source = (version.clean_transcript or version.source_text).strip()
    if not source:
        raise HTTPException(400, detail={'code': 'SOURCE_REQUIRED', 'message': 'Add lesson text before translation.'})
    engine = Layer2Engine(manager.translate)
    concepts = json.loads(version.concepts_json or '[]')
    context = {'concepts': concepts, 'grade': lesson.grade, 'subject': lesson.subject, 'topic': lesson.topic}
    try:
        text = engine.translate_text(source, lesson.source_language, x.target_language, context)
        validation = engine.validate_translation(source, text, lesson.source_language, x.target_language, context)
    except Exception as exc:
        logger.exception('Local IndicTrans2 translation failed lesson_id=%s src=%s tgt=%s', lesson_id, lesson.source_language, x.target_language)
        raise HTTPException(
            503,
            detail={
                'code': 'TRANSLATION_FAILED',
                'message': 'The local translation model could not prepare this translation. Your original lesson is safe.',
                'details': {'runtime_error': str(exc)[:600]},
                'retryable': True,
            },
        ) from exc

    row = db.query(Translation).filter_by(lesson_version_id=version.id, target_language=x.target_language).first()
    if not row:
        row = Translation(
            lesson_version_id=version.id,
            source_language=lesson.source_language,
            target_language=x.target_language,
            translated_text=text,
        )
        db.add(row)
    row.translated_text = text
    row.confidence = validation['confidence']
    row.flags_json = json.dumps(validation['flags'], ensure_ascii=False)
    row.validation_json = json.dumps(validation, ensure_ascii=False)
    row.verification_status = 'UNVERIFIED'
    row.teacher_edited = False
    row.native_review_status = 'PENDING' if x.target_language == 'sat_Olck' else 'NOT_REVIEWED'
    lesson.status = 'FLAGGED' if validation['flags'] else 'TRANSLATED'
    db.commit()
    db.refresh(row)
    return {
        'translation_id': row.id,
        'text': row.translated_text,
        'confidence': row.confidence,
        'flags': json.loads(row.flags_json),
        'validation': validation,
        'verification_status': row.verification_status,
        'native_review_status': row.native_review_status,
    }


@router.post('/lessons/{lesson_id}/verify-translation')
def verify_translation(lesson_id: int, x: VerifyIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    translation = db.get(Translation, x.translation_id)
    if not translation or translation.lesson_version_id != version.id:
        raise HTTPException(404, detail={'code': 'TRANSLATION_NOT_FOUND', 'message': 'Translation not found.'})
    if x.native_review_status == 'VERIFIED':
        raise HTTPException(400, detail={'code': 'NATIVE_REVIEW_REQUIRES_REVIEWER', 'message': 'Native-language verification is reserved for a qualified language reviewer. Teacher approval can remain separate.'})
    if x.edited_text is not None:
        text = x.edited_text.strip()
        if not text:
            raise HTTPException(400, detail={'code': 'TRANSLATION_EMPTY', 'message': 'Approved translation cannot be empty.'})
        translation.translated_text = text
        translation.teacher_edited = True
        engine = Layer2Engine(manager.translate)
        validation = engine.validate_translation(
            version.clean_transcript or version.source_text,
            text,
            translation.source_language,
            translation.target_language,
            {'concepts': json.loads(version.concepts_json or '[]')},
        )
        translation.confidence = validation['confidence']
        translation.flags_json = json.dumps(validation['flags'], ensure_ascii=False)
        translation.validation_json = json.dumps(validation, ensure_ascii=False)
    if x.native_review_status is not None:
        translation.native_review_status = x.native_review_status
    elif translation.target_language == 'sat_Olck' and translation.native_review_status == 'NOT_REVIEWED':
        translation.native_review_status = 'PENDING'
    translation.verification_status = 'TEACHER_APPROVED' if x.approved else 'REVIEW_REQUIRED'
    lesson.status = 'TEACHER_APPROVED' if x.approved else 'FLAGGED'
    db.commit()
    return pack(db, lesson, include_pending=True)


@router.post('/lessons/{lesson_id}/generate-practice')
def generate_practice(lesson_id: int, x: PracticeGenerateIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    rows = ensure_practice(db, version, x.language, x.count, approved=False, translate_fn=manager.translate)
    return [_practice_view(q) for q in rows]


@router.post('/lessons/{lesson_id}/practice/{question_id}/approve')
def approve_practice(lesson_id: int, question_id: int, x: PracticeApprovalIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    question = db.get(PracticeQuestion, question_id)
    if not question or question.lesson_version_id != version.id:
        raise HTTPException(404, detail={'code': 'PRACTICE_NOT_FOUND', 'message': 'Practice question not found.'})
    question.approved = x.approved
    db.commit()
    return _practice_view(question)


@router.post('/lessons/{lesson_id}/generate-worksheet')
def generate_worksheet(lesson_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    translations = db.query(Translation).filter_by(lesson_version_id=version.id).all()
    return make_worksheet(lesson, version, translations)


@router.post('/lessons/{lesson_id}/generate-flashcards')
def generate_flashcards(lesson_id: int, x: FlashcardIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    translations = db.query(Translation).filter_by(lesson_version_id=version.id).all()
    return make_flashcards(lesson, version, translations, (x.language, 'eng_Latn', 'sat_Olck'))


@router.post('/lessons/{lesson_id}/transcribe')
async def transcribe(lesson_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    if not settings.stt_enabled:
        raise HTTPException(503, detail={'code': 'STT_DISABLED', 'message': 'Speech-to-text is disabled in this local profile.'})
    suffix = Path(file.filename or 'audio.webm').suffix.lower() or '.webm'
    allowed = {'.webm', '.wav', '.mp3', '.m4a', '.mp4', '.ogg', '.flac'}
    if suffix not in allowed:
        raise HTTPException(400, detail={'code': 'AUDIO_FORMAT_UNSUPPORTED', 'message': 'Use WAV, MP3, M4A, OGG, FLAC, or WebM audio.'})
    data = await file.read()
    if len(data) > settings.max_audio_mb * 1024 * 1024:
        raise HTTPException(413, detail={'code': 'AUDIO_TOO_LARGE', 'message': f'Audio must be under {settings.max_audio_mb} MB.'})
    folder = STORAGE_ROOT / 'uploads'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (secrets.token_hex(12) + suffix)
    path.write_bytes(data)
    try:
        stt_language = {'hin_Deva': 'hi', 'eng_Latn': 'en', 'sat_Olck': None}.get(lesson.source_language)
        result = manager.transcribe(path, stt_language)
    except Exception as exc:
        logger.exception('STT failed lesson_id=%s', lesson_id)
        raise HTTPException(503, detail={'code': 'STT_FAILED', 'message': 'Speech recognition failed. You can edit the transcript manually or retry.', 'details': {'runtime_error': str(exc)[:600]}, 'retryable': True}) from exc
    version = current_version(db, lesson)
    version.clean_transcript = result['text']
    db.commit()
    return result


@router.post('/lessons/{lesson_id}/tts')
def tts(lesson_id: int, x: TTSIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    if not settings.tts_enabled:
        raise HTTPException(503, detail={'code': 'TTS_DISABLED', 'message': 'Text-to-speech is disabled in this local profile.'})
    version = current_version(db, lesson)
    translation = db.query(Translation).filter_by(lesson_version_id=version.id, target_language=x.target_language).first()
    if x.target_language == lesson.source_language:
        text = version.clean_transcript or version.source_text
    else:
        if not translation:
            raise HTTPException(400, detail={'code': 'TTS_SOURCE_MISSING', 'message': 'Prepare this language translation before generating audio.'})
        if translation.verification_status != 'TEACHER_APPROVED':
            raise HTTPException(400, detail={'code': 'TTS_REVIEW_REQUIRED', 'message': 'Approve the translation before generating student-facing audio.'})
        text = translation.translated_text
    if not text.strip():
        raise HTTPException(400, detail={'code': 'TTS_SOURCE_MISSING', 'message': 'There is no text available for audio generation.'})

    cache = STORAGE_ROOT / 'tts_cache'
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((text + '|' + x.target_language + '|' + x.speaker + '|v2').encode('utf-8')).hexdigest()
    path = cache / f'{key}.wav'
    created = False
    if not path.exists():
        try:
            manager.synthesize(text, path, x.target_language, x.speaker)
            created = True
        except Exception as exc:
            logger.exception('TTS failed lesson_id=%s language=%s', lesson_id, x.target_language)
            raise HTTPException(503, detail={'code': 'TTS_FAILED', 'message': 'Audio generation failed. The lesson text is still safe and available.', 'details': {'runtime_error': str(exc)[:600]}, 'retryable': True}) from exc
    digest = sha256_file(path)
    artifact = db.query(Artifact).filter_by(lesson_version_id=version.id, type='audio', language=x.target_language, sha256=digest).first()
    if not artifact:
        artifact = register_file(db, version.id, 'audio', x.target_language, path, 'audio/wav', {'cache_key': key, 'speaker': x.speaker})
    return {'artifact_id': artifact.id, 'url': f'/api/v1/artifacts/{artifact.id}', 'language': x.target_language, 'cached': not created}


@router.post('/lessons/{lesson_id}/publish')
def do_publish(lesson_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    lesson = db_lesson(db, lesson_id)
    require_group_owner(db, lesson, user)
    version = current_version(db, lesson)
    ok, problems = publish(db, lesson, version)
    if not ok:
        raise HTTPException(400, detail={'code': 'PUBLISH_BLOCKED', 'message': 'Publish is blocked until the lesson package is complete and approved.', 'details': {'problems': problems}})
    return pack(db, lesson, include_pending=True)


@router.get('/artifacts/{artifact_id}')
def artifact(artifact_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    item = db.get(Artifact, artifact_id)
    if not item or not Path(item.path).is_file():
        raise HTTPException(404, detail={'code': 'ARTIFACT_NOT_FOUND', 'message': 'Artifact not found.'})
    version = db.get(LessonVersion, item.lesson_version_id)
    lesson = db.get(Lesson, version.lesson_id) if version else None
    if not lesson or not can_read_lesson(db, lesson, user):
        raise HTTPException(403, detail={'code': 'ARTIFACT_ACCESS_DENIED', 'message': 'You do not have access to this lesson artifact.'})
    return FileResponse(item.path, media_type=item.mime_type, filename=Path(item.path).name)
