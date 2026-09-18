import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models import Lesson, LessonVersion, Membership, PracticeQuestion, Attempt
from ...schemas import AttemptIn
from ...core.security import current_user
from .lessons import pack
from ...services.content import ensure_practice, evaluate_attempt

router=APIRouter(prefix='/student',tags=['student'])

@router.get('/lessons')
def student_lessons(db:Session=Depends(get_db),u=Depends(current_user)):
    ids=[m.group_id for m in db.query(Membership).filter_by(user_id=u.id).all()]
    rows=db.query(Lesson).filter(Lesson.group_id.in_(ids or [-1]),Lesson.status=='PUBLISHED').order_by(Lesson.updated_at.desc()).all()
    return [pack(db,l) for l in rows]

@router.get('/lessons/{lesson_id}/package')
def package(lesson_id:int,db:Session=Depends(get_db),u=Depends(current_user)):
    l=db.get(Lesson,lesson_id)
    if not l or l.status!='PUBLISHED': raise HTTPException(404,detail={'code':'PUBLISHED_LESSON_NOT_FOUND','message':'This lesson is not published.'})
    allowed=u.account_role=='admin' or bool(db.query(Membership).filter_by(group_id=l.group_id,user_id=u.id).first())
    if not allowed: raise HTTPException(403,detail={'code':'LESSON_ACCESS_DENIED','message':'Join the classroom before opening this lesson.'})
    return pack(db,l)

@router.post('/attempts')
def attempt(x:AttemptIn,db:Session=Depends(get_db),u=Depends(current_user)):
    if u.account_role=='admin': raise HTTPException(403,detail={'code':'STUDENT_ONLY','message':'Practice submissions are for student accounts.'})
    lesson_id=int(x.answers.get('__lesson_id',0) or 0)
    if not lesson_id: raise HTTPException(400,detail={'code':'LESSON_ID_REQUIRED','message':'Lesson id is required in the attempt payload.'})
    l=db.get(Lesson,lesson_id)
    if not l: raise HTTPException(404,detail={'code':'LESSON_NOT_FOUND','message':'Lesson not found.'})
    version_id=x.lesson_version_id or l.current_version_id
    v=db.get(LessonVersion,version_id) if version_id else None
    if not v or v.lesson_id!=l.id: raise HTTPException(404,detail={'code':'VERSION_NOT_FOUND','message':'Lesson version not found.'})
    if not db.query(Membership).filter_by(group_id=l.group_id,user_id=u.id).first():
        raise HTTPException(403,detail={'code':'GROUP_ACCESS_DENIED','message':'You are not a member of this classroom.'})
    lang=str(x.answers.get('__language','hin_Deva'))
    questions=db.query(PracticeQuestion).filter_by(lesson_version_id=v.id,language=lang,approved=True).all()
    if not questions: questions=ensure_practice(db,v,lang,4,True)
    answers={k:v2 for k,v2 in x.answers.items() if not k.startswith('__')}
    score,results=evaluate_attempt(v,answers,questions)
    created=datetime.now(timezone.utc)
    a=Attempt(lesson_id=l.id,lesson_version_id=v.id,student_id=u.id,answers_json=json.dumps(answers,ensure_ascii=False),score=score,concept_results_json=json.dumps(results,ensure_ascii=False),created_at=created,synced_at=created)
    db.add(a); db.commit(); db.refresh(a)
    return {'attempt_id':a.id,'score':score,'concept_results':results,'synced':True}

@router.get('/progress')
def progress(db:Session=Depends(get_db),u=Depends(current_user)):
    attempts=db.query(Attempt).filter_by(student_id=u.id).order_by(Attempt.created_at.desc()).all()
    avg=round(sum(a.score for a in attempts)/len(attempts),1) if attempts else 0
    return {'lessons_completed':len(attempts),'overall_understanding':avg,'needs_practice':sum(1 for a in attempts if a.score<70),'recent_attempts':[{'id':a.id,'lesson_id':a.lesson_id,'score':a.score,'created_at':a.created_at.isoformat()} for a in attempts[:8]]}
