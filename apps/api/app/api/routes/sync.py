
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models import SyncRecord, Attempt, Lesson, LessonVersion, Membership
from ...schemas import SyncPushIn
from ...core.security import current_user

router=APIRouter(prefix='/sync',tags=['sync'])

@router.post('/push')
def push(x:SyncPushIn,db:Session=Depends(get_db),u=Depends(current_user)):
    accepted=0; processed=0
    for op in x.operations:
        kind=str(op.get('operation','UNKNOWN'))
        payload=op.get('payload') or {}
        row=SyncRecord(device_id=x.device_id,operation=kind,entity_type=str(op.get('entity_type','unknown')),entity_id=str(op.get('entity_id','')),payload_json=json.dumps(payload,ensure_ascii=False),created_at=datetime.now(timezone.utc),attempt_count=0)
        db.add(row); accepted+=1
        if kind=='ATTEMPT_UPSERT' and u.account_role=='student':
            try:
                lesson_id=int(payload.get('lessonId') or payload.get('lesson_id') or 0)
                version_id=int(payload.get('lessonVersionId') or payload.get('lesson_version_id') or 0)
                answers=payload.get('answers') or {}
                lesson=db.get(Lesson,lesson_id); version=db.get(LessonVersion,version_id)
                member=lesson and db.query(Membership).filter_by(group_id=lesson.group_id,user_id=u.id).first()
                if lesson and version and version.lesson_id==lesson.id and member:
                    answers_clean={k:v for k,v in answers.items() if not str(k).startswith('__')}
                    from ...services.content import ensure_practice,evaluate_attempt
                    lang=str(answers.get('__language','hin_Deva'))
                    questions=ensure_practice(db,version,lang,4,True)
                    score,results=evaluate_attempt(version,answers_clean,questions)
                    stamp=datetime.now(timezone.utc)
                    db.add(Attempt(lesson_id=lesson.id,lesson_version_id=version.id,student_id=u.id,answers_json=json.dumps(answers_clean,ensure_ascii=False),score=score,concept_results_json=json.dumps(results,ensure_ascii=False),created_at=stamp,synced_at=stamp))
                    row.processed_at=stamp; processed+=1
            except Exception as exc:
                row.last_error=str(exc)[:500]; row.attempt_count=1
    db.commit()
    return {'accepted':accepted,'processed':processed,'status':'ok','message':'Offline work accepted without overwriting existing attempts.'}

@router.post('/pull')
def pull(db:Session=Depends(get_db),u=Depends(current_user)):
    rows=db.query(SyncRecord).filter(SyncRecord.processed_at.is_(None)).order_by(SyncRecord.id.asc()).limit(100).all()
    return {'changes':[{'id':r.id,'operation':r.operation,'entity_type':r.entity_type,'entity_id':r.entity_id,'payload':json.loads(r.payload_json or '{}')} for r in rows]}
