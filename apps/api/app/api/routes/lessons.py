import logging
import hashlib
import json
import secrets
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ...db import get_db
from ...models import Lesson, LessonVersion, Translation, Artifact, PracticeQuestion, Membership, Group
from ...schemas import LessonCreateIn, LessonPatchIn, VersionCreateIn, TranslateIn, VerifyIn, PracticeGenerateIn, TTSIn, FlashcardIn
from ...core.security import current_user, require_admin
from ...core.config import STORAGE_ROOT, settings
from ...services.model_manager import manager
from ...services.content import analyze_source, ensure_practice
from ...services.publish import publish
from ...services.worksheet import make_worksheet, make_flashcards
from ...services.artifacts import register_file, sha256_file
from core.layer2.service import Layer2Engine

router = APIRouter(tags=['lessons'])

def db_lesson(db, lesson_id: int):
    l = db.get(Lesson, lesson_id)
    if not l:
        raise HTTPException(404, detail={'code':'LESSON_NOT_FOUND','message':'Lesson not found.'})
    return l

def current_version(db, lesson):
    if not lesson.current_version_id:
        raise HTTPException(400, detail={'code':'NO_VERSION','message':'This lesson has no active version yet.'})
    v = db.get(LessonVersion, lesson.current_version_id)
    if not v:
        raise HTTPException(500, detail={'code':'VERSION_MISSING','message':'The active lesson version is missing.'})
    return v

def require_group_editor(db, lesson, user):
    group = db.get(Group, lesson.group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(403, detail={'code':'LESSON_EDIT_DENIED','message':'You do not have permission to edit this lesson.'})

def lesson_summary(db, lesson):
    version = db.get(LessonVersion, lesson.current_version_id) if lesson.current_version_id else None
    return {
        'id': lesson.id, 'group_id': lesson.group_id, 'title': lesson.title, 'grade': lesson.grade,
        'subject': lesson.subject, 'topic': lesson.topic, 'source_language': lesson.source_language,
        'status': lesson.status, 'current_version_id': lesson.current_version_id,
        'version_number': version.version_number if version else None,
        'updated_at': lesson.updated_at.isoformat() if lesson.updated_at else None,
    }

def version_view(v):
    return {
        'id': v.id, 'version_number': v.version_number, 'source_text': v.source_text,
        'clean_transcript': v.clean_transcript,
        'learning_objectives': json.loads(v.learning_objectives_json or '[]'),
        'concepts': json.loads(v.concepts_json or '[]'),
        'ai_explanation': json.loads(v.ai_explanation_json or '{}'),
        'activities': json.loads(v.activities_json or '[]'),
        'approved_at': v.approved_at.isoformat() if v.approved_at else None,
        'published_at': v.published_at.isoformat() if v.published_at else None,
    }

def pack(db, lesson):
    v = current_version(db, lesson)
    translations = db.query(Translation).filter_by(lesson_version_id=v.id).order_by(Translation.target_language).all()
    artifacts = db.query(Artifact).filter_by(lesson_version_id=v.id).order_by(Artifact.id.desc()).all()
    questions = db.query(PracticeQuestion).filter_by(lesson_version_id=v.id, approved=True).all()
    worksheet = make_worksheet(lesson, v)
    flashcards = make_flashcards(lesson, v, ('hin_Deva','eng_Latn','sat_Olck'))
    return {
        'lesson': lesson_summary(db, lesson),
        'version': version_view(v),
        'worksheet_html': worksheet.get('html',''),
        'worksheet_meta': {k: worksheet[k] for k in ('learning_outcome','concepts','language_a','language_b') if k in worksheet},
        'flashcards': flashcards,
        'translations': [
            {'id': t.id, 'language': t.target_language, 'text': t.translated_text, 'confidence': t.confidence,
             'flags': json.loads(t.flags_json or '[]'), 'validation': json.loads(t.validation_json or '{}'),
             'verification_status': t.verification_status, 'teacher_edited': t.teacher_edited,
             'native_review_status': t.native_review_status}
            for t in translations
        ],
        'artifacts': [
            {'id': a.id, 'type': a.type, 'language': a.language, 'mime_type': a.mime_type,
             'size_bytes': a.size_bytes, 'sha256': a.sha256, 'url': f'/api/v1/artifacts/{a.id}'}
            for a in artifacts
        ],
        'practice': [
            {'id': q.id, 'concept_id': q.concept_id, 'prompt': q.prompt,
             'options': json.loads(q.options_json or '[]'), 'correct_answer': q.correct_answer,
             'explanation': q.explanation, 'language': q.language, 'question_type': q.question_type}
            for q in questions
        ],
    }

@router.post('/groups/{group_id}/lessons')
def create_lesson(group_id: int, x: LessonCreateIn, db: Session = Depends(get_db), u=Depends(require_admin)):
    g = db.get(Group, group_id)
    if not g or g.owner_id != u.id:
        raise HTTPException(403, detail={'code':'GROUP_EDIT_DENIED','message':'You do not own this group.'})
    l = Lesson(group_id=group_id, title=x.title.strip(), grade=x.grade.strip(), subject=x.subject.strip(),
               topic=x.topic.strip(), source_language=x.source_language, status='DRAFT', created_by=u.id)
    db.add(l); db.flush()
    v = LessonVersion(lesson_id=l.id, version_number=1, source_text=x.source_text, clean_transcript=x.source_text, created_by=u.id)
    db.add(v); db.flush(); l.current_version_id = v.id
    db.commit(); db.refresh(l)
    return lesson_summary(db, l)

@router.get('/groups/{group_id}/lessons')
def list_lessons(group_id: int, db: Session = Depends(get_db), u=Depends(current_user)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, detail={'code':'GROUP_NOT_FOUND','message':'Group not found.'})
    allowed = g.owner_id == u.id or bool(db.query(Membership).filter_by(group_id=group_id, user_id=u.id).first())
    if not allowed:
        raise HTTPException(403, detail={'code':'GROUP_ACCESS_DENIED','message':'You are not a member of this group.'})
    return [lesson_summary(db, l) for l in db.query(Lesson).filter_by(group_id=group_id).order_by(Lesson.updated_at.desc()).all()]

@router.get('/lessons/{lesson_id}')
def get_lesson(lesson_id: int, db: Session = Depends(get_db), u=Depends(current_user)):
    l = db_lesson(db, lesson_id)
    allowed = u.account_role == 'admin' and db.get(Group, l.group_id).owner_id == u.id or bool(db.query(Membership).filter_by(group_id=l.group_id, user_id=u.id).first())
    if not allowed:
        raise HTTPException(403, detail={'code':'LESSON_ACCESS_DENIED','message':'You do not have access to this lesson.'})
    return pack(db, l)

@router.patch('/lessons/{lesson_id}')
def patch_lesson(lesson_id: int, x: LessonPatchIn, db: Session = Depends(get_db), u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u); v=current_version(db,l)
    changes_requested=any(vv is not None for vv in (x.source_text,x.clean_transcript,x.learning_outcome,x.concepts)) or x.title is not None or x.topic is not None
    if l.status=='PUBLISHED' and changes_requested:
        outcome=[x.learning_outcome] if x.learning_outcome is not None else json.loads(v.learning_objectives_json or '[]')
        concepts=([{'concept_id':c.strip().lower().replace(' ','_'),'label':c.strip(),'keywords':[c.strip()]} for c in x.concepts or [] if c.strip()]
                  if x.concepts is not None else json.loads(v.concepts_json or '[]'))
        newv=LessonVersion(lesson_id=l.id,version_number=v.version_number+1,
            source_text=x.source_text if x.source_text is not None else v.source_text,
            clean_transcript=x.clean_transcript if x.clean_transcript is not None else v.clean_transcript,
            learning_objectives_json=json.dumps(outcome,ensure_ascii=False),concepts_json=json.dumps(concepts,ensure_ascii=False),
            ai_explanation_json='{}',activities_json='[]',created_by=u.id)
        db.add(newv); db.flush(); l.current_version_id=newv.id; l.status='DRAFT'
        if x.title is not None: l.title=x.title.strip()
        if x.topic is not None: l.topic=x.topic.strip()
        db.commit(); return pack(db,l)
    if x.title is not None: l.title=x.title.strip()
    if x.topic is not None: l.topic=x.topic.strip()
    if x.source_text is not None: v.source_text=x.source_text
    if x.clean_transcript is not None: v.clean_transcript=x.clean_transcript
    if x.learning_outcome is not None: v.learning_objectives_json=json.dumps([x.learning_outcome],ensure_ascii=False)
    if x.concepts is not None: v.concepts_json=json.dumps([{'concept_id':c.strip().lower().replace(' ','_'),'label':c.strip(),'keywords':[c.strip()]} for c in x.concepts if c.strip()],ensure_ascii=False)
    db.commit(); return pack(db,l)

@router.delete('/lessons/{lesson_id}')
def delete_lesson(lesson_id: int, db: Session = Depends(get_db), u=Depends(require_admin)):
    l = db_lesson(db, lesson_id); require_group_editor(db, l, u)
    versions = db.query(LessonVersion).filter_by(lesson_id=l.id).all()
    for v in versions:
        db.query(Translation).filter_by(lesson_version_id=v.id).delete(synchronize_session=False)
        db.query(Artifact).filter_by(lesson_version_id=v.id).delete(synchronize_session=False)
        db.query(PracticeQuestion).filter_by(lesson_version_id=v.id).delete(synchronize_session=False)
        db.delete(v)
    db.delete(l); db.commit()
    return {'ok': True}

@router.post('/lessons/{lesson_id}/versions')
def new_version(lesson_id: int, x: VersionCreateIn, db: Session = Depends(get_db), u=Depends(require_admin)):
    l = db_lesson(db, lesson_id); require_group_editor(db, l, u); prev = current_version(db, l)
    outcome = [x.learning_outcome] if x.learning_outcome else json.loads(prev.learning_objectives_json or '[]')
    concepts = ([{'concept_id': c.strip().lower().replace(' ','_'), 'label': c.strip(), 'keywords':[c.strip()]} for c in x.concepts if c.strip()]
                if x.concepts is not None else json.loads(prev.concepts_json or '[]'))
    v = LessonVersion(lesson_id=l.id, version_number=prev.version_number+1,
                      source_text=x.source_text if x.source_text is not None else prev.source_text,
                      clean_transcript=x.clean_transcript if x.clean_transcript is not None else prev.clean_transcript,
                      learning_objectives_json=json.dumps(outcome, ensure_ascii=False),
                      concepts_json=json.dumps(concepts, ensure_ascii=False), created_by=u.id)
    db.add(v); db.flush(); l.current_version_id=v.id; l.status='DRAFT'; db.commit()
    return pack(db, l)

@router.get('/lessons/{lesson_id}/versions')
def versions(lesson_id: int, db: Session = Depends(get_db), u=Depends(current_user)):
    l = db_lesson(db, lesson_id)
    rows = db.query(LessonVersion).filter_by(lesson_id=l.id).order_by(LessonVersion.version_number.desc()).all()
    return [{'id':v.id,'version_number':v.version_number,'created_at':v.created_at.isoformat(),
             'published_at':v.published_at.isoformat() if v.published_at else None,
             'approved_at':v.approved_at.isoformat() if v.approved_at else None} for v in rows]

@router.post('/lessons/{lesson_id}/rollback')
def rollback(lesson_id: int, version_id: int = Query(...), db: Session = Depends(get_db), u=Depends(require_admin)):
    l = db_lesson(db, lesson_id); require_group_editor(db, l, u); v = db.get(LessonVersion, version_id)
    if not v or v.lesson_id != l.id:
        raise HTTPException(404, detail={'code':'VERSION_NOT_FOUND','message':'Version not found.'})
    if not v.published_at:
        raise HTTPException(400, detail={'code':'VERSION_NOT_PUBLISHED','message':'Only a published version can be restored.'})
    l.current_version_id=v.id; l.status='PUBLISHED'; db.commit()
    return pack(db, l)

@router.post('/lessons/{lesson_id}/analyze')
def analyze(lesson_id: int, db: Session = Depends(get_db), u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u); v=current_version(db,l)
    text=v.clean_transcript or v.source_text
    result=analyze_source(text,l.grade,l.subject,l.topic)
    v.concepts_json=json.dumps(result['concepts'],ensure_ascii=False)
    v.learning_objectives_json=json.dumps([result['learning_objective']],ensure_ascii=False)
    v.ai_explanation_json=json.dumps({'explanation':result['explanation']},ensure_ascii=False)
    v.activities_json=json.dumps(result['activities'],ensure_ascii=False)
    l.topic=result['topic']; l.status='AI_SUGGESTED'; db.commit()
    return result

logger = logging.getLogger("bhashasaathi.translation")

@router.post('/lessons/{lesson_id}/translate')
def translate(lesson_id: int, x: TranslateIn, db: Session = Depends(get_db), u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u); v=current_version(db,l)
    if x.target_language == l.source_language:
        raise HTTPException(400, detail={'code':'SAME_LANGUAGE','message':'Choose a language different from the source language.'})
    if not settings.translation_enabled:
        raise HTTPException(503, detail={'code':'TRANSLATION_DISABLED','message':'Translation is disabled in this local profile.'})
    if settings.demo_mode:
        raise HTTPException(400, detail={'code':'DEMO_MODE_AI_DISABLED','message':'Set DEMO_MODE=false to use the local translation models.'})
    source=v.clean_transcript or v.source_text
    concepts=json.loads(v.concepts_json or '[]')
    engine=Layer2Engine(manager.translation.translate)
    try:
        text=engine.translate_text(source,l.source_language,x.target_language,{'concepts':concepts,'grade':l.grade,'subject':l.subject,'topic':l.topic})
        validation=engine.validate_translation(source,text,l.source_language,x.target_language,{'concepts':concepts})
    except Exception as exc:
        logger.exception("Local IndicTrans2 translation failed for lesson_id=%s src=%s tgt=%s", lesson_id, l.source_language, x.target_language)
        raise HTTPException(503, detail={'code':'TRANSLATION_FAILED','message':'The local translation model could not prepare this translation. Your original lesson is safe.','details':str(exc)})
    row=db.query(Translation).filter_by(lesson_version_id=v.id,target_language=x.target_language).first()
    if not row:
        row=Translation(lesson_version_id=v.id,source_language=l.source_language,target_language=x.target_language,translated_text=text)
        db.add(row)
    row.translated_text=text; row.confidence=validation['confidence']; row.flags_json=json.dumps(validation['flags'],ensure_ascii=False)
    row.validation_json=json.dumps(validation,ensure_ascii=False); row.verification_status='UNVERIFIED'; row.teacher_edited=False
    row.native_review_status='PENDING' if x.target_language=='sat_Olck' else 'NOT_REVIEWED'
    l.status='FLAGGED' if validation['flags'] else 'TRANSLATED'
    db.commit(); db.refresh(row)
    return {'translation_id':row.id,'text':row.translated_text,'confidence':row.confidence,'flags':json.loads(row.flags_json),'validation':validation,'verification_status':row.verification_status,'native_review_status':row.native_review_status}

@router.post('/lessons/{lesson_id}/verify-translation')
def verify_translation(lesson_id: int, x: VerifyIn, db: Session = Depends(get_db), u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u); v=current_version(db,l)
    t=db.get(Translation,x.translation_id)
    if not t or t.lesson_version_id!=v.id:
        raise HTTPException(404,detail={'code':'TRANSLATION_NOT_FOUND','message':'Translation not found.'})
    if x.edited_text is not None:
        t.translated_text=x.edited_text.strip(); t.teacher_edited=True
        engine=Layer2Engine(manager.translation.translate)
        validation=engine.validate_translation(v.source_text,t.translated_text,t.source_language,t.target_language,{'concepts':json.loads(v.concepts_json or '[]')})
        t.confidence=validation['confidence']; t.flags_json=json.dumps(validation['flags'],ensure_ascii=False); t.validation_json=json.dumps(validation,ensure_ascii=False)
    if x.native_review_status is not None: t.native_review_status=x.native_review_status
    if x.approved and t.target_language=='sat_Olck' and t.native_review_status!='VERIFIED':
        # Teacher approval is explicit; native review remains a visible review state rather than a fabricated claim.
        t.native_review_status='PENDING'
    t.verification_status='TEACHER_APPROVED' if x.approved else 'REVIEW_REQUIRED'
    l.status='TEACHER_APPROVED' if x.approved else 'FLAGGED'
    db.commit(); return pack(db,l)

@router.post('/lessons/{lesson_id}/generate-practice')
def generate_practice(lesson_id:int,x:PracticeGenerateIn,db:Session=Depends(get_db),u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u); v=current_version(db,l)
    rows=ensure_practice(db,v,x.language,x.count,approved=True)
    return [{'id':q.id,'concept_id':q.concept_id,'prompt':q.prompt,'options':json.loads(q.options_json),'correct_answer':q.correct_answer,'explanation':q.explanation,'language':q.language} for q in rows]

@router.post('/lessons/{lesson_id}/generate-worksheet')
def generate_worksheet(lesson_id:int,db:Session=Depends(get_db),u=Depends(current_user)):
    l=db_lesson(db,lesson_id); v=current_version(db,l); return make_worksheet(l,v)

@router.post('/lessons/{lesson_id}/generate-flashcards')
def generate_flashcards(lesson_id:int,x:FlashcardIn,db:Session=Depends(get_db),u=Depends(current_user)):
    l=db_lesson(db,lesson_id); v=current_version(db,l); return make_flashcards(l,v,(x.language,'eng_Latn','sat_Olck'))

@router.post('/lessons/{lesson_id}/transcribe')
async def transcribe(lesson_id:int,file:UploadFile=File(...),db:Session=Depends(get_db),u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u)
    if not settings.stt_enabled: raise HTTPException(503,detail={'code':'STT_DISABLED','message':'Speech-to-text is disabled in this local profile.'})
    suffix=Path(file.filename or 'audio.webm').suffix.lower() or '.webm'
    if suffix not in {'.webm','.wav','.mp3','.m4a','.mp4','.ogg','.flac'}:
        raise HTTPException(400,detail={'code':'AUDIO_FORMAT_UNSUPPORTED','message':'Use WAV, MP3, M4A, OGG, FLAC, or WebM audio.'})
    data=await file.read()
    if len(data)>settings.max_audio_mb*1024*1024:
        raise HTTPException(413,detail={'code':'AUDIO_TOO_LARGE','message':f'Audio must be under {settings.max_audio_mb} MB.'})
    folder=STORAGE_ROOT/'uploads'; folder.mkdir(parents=True,exist_ok=True)
    path=folder/(secrets.token_hex(12)+suffix); path.write_bytes(data)
    try:
        result=manager.stt.transcribe(path,'hi' if l.source_language=='hin_Deva' else 'en')
    except Exception as exc:
        raise HTTPException(503,detail={'code':'STT_FAILED','message':'Speech recognition failed. Edit the transcript manually or retry.','details':str(exc)})
    v=current_version(db,l); v.clean_transcript=result['text']; db.commit()
    return result

@router.post('/lessons/{lesson_id}/tts')
def tts(lesson_id:int,x:TTSIn,db:Session=Depends(get_db),u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u)
    if not settings.tts_enabled: raise HTTPException(503,detail={'code':'TTS_DISABLED','message':'Text-to-speech is disabled in this local profile.'})
    v=current_version(db,l)
    t=db.query(Translation).filter_by(lesson_version_id=v.id,target_language=x.target_language).first()
    text=t.translated_text if t else ((v.clean_transcript or v.source_text) if x.target_language==l.source_language else None)
    if not text: raise HTTPException(400,detail={'code':'TTS_SOURCE_MISSING','message':'Create target-language text before generating audio.'})
    cache=STORAGE_ROOT/'tts_cache'; cache.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((text+'|'+x.target_language+'|'+x.speaker+'|v1').encode('utf-8')).hexdigest()
    path=cache/(key+'.wav')
    created=False
    if not path.exists():
        try:
            manager.tts.synthesize(text,path,x.target_language,x.speaker); created=True
        except Exception as exc:
            raise HTTPException(503,detail={'code':'TTS_FAILED','message':'Audio generation failed. The text is still safe and available.','details':str(exc)})
    digest=sha256_file(path)
    existing=db.query(Artifact).filter_by(lesson_version_id=v.id,type='audio',language=x.target_language,sha256=digest).first()
    if not existing:
        existing=register_file(db,v.id,'audio',x.target_language,path,'audio/wav',{'cache_key':key,'speaker':x.speaker})
    return {'artifact_id':existing.id,'url':f'/api/v1/artifacts/{existing.id}','language':x.target_language,'cached':not created}

@router.post('/lessons/{lesson_id}/publish')
def do_publish(lesson_id:int,db:Session=Depends(get_db),u=Depends(require_admin)):
    l=db_lesson(db,lesson_id); require_group_editor(db,l,u); v=current_version(db,l)
    ok,problems=publish(db,l,v)
    if not ok:
        raise HTTPException(400,detail={'code':'PUBLISH_BLOCKED','message':'Publish is blocked until required teacher approvals are complete.','details':{'problems':problems}})
    return pack(db,l)

@router.get('/artifacts/{artifact_id}')
def artifact(artifact_id:int,db:Session=Depends(get_db),u=Depends(current_user)):
    a=db.get(Artifact,artifact_id)
    if not a or not Path(a.path).exists(): raise HTTPException(404,detail={'code':'ARTIFACT_NOT_FOUND','message':'Artifact not found.'})
    return FileResponse(a.path,media_type=a.mime_type,filename=Path(a.path).name)
