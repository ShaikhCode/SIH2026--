import json, re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import Lesson, LessonVersion, Translation, PracticeQuestion
from core.layer2.concepts import extract_concepts


def now(): return datetime.now(timezone.utc)

def concepts_as_json(concepts):
    return json.dumps([{'concept_id':c.concept_id,'label':c.label,'source_span':c.source_span,'definition':c.definition,'keywords':list(c.keywords),'importance':c.importance} for c in concepts],ensure_ascii=False)

def analyze_source(text: str, grade: str, subject: str, topic: str='') -> dict:
    concepts = extract_concepts(text)
    inferred_topic = topic or next((c.label for c in concepts if c.concept_id != 'main_idea'),'New Lesson')
    outcome = f'Learner can explain the main idea of {inferred_topic.lower()} using the key concepts.'
    low = text.lower()
    if 'water' in low or 'पानी' in text:
        outcome = 'Learner can explain that plants need water to live and grow.' if ('plant' in low or 'पौध' in text) else f'Learner can explain why water matters in this lesson.'
    explanation = f'For {grade} {subject}: explain the teacher lesson using the approved source text and these concepts: {", ".join(c.label for c in concepts)}.'
    activities = ['Ask the learner to explain the main idea in their own words.', 'Ask for one real-world example from the learner’s surroundings.']
    return {'topic': inferred_topic, 'concepts': [c.__dict__ for c in concepts], 'learning_objective': outcome, 'explanation': explanation, 'activities': activities}

def ensure_practice(db: Session, version: LessonVersion, language: str='hin_Deva', count: int=4, approved: bool=True):
    concepts = json.loads(version.concepts_json or '[]')
    existing = db.query(PracticeQuestion).filter_by(lesson_version_id=version.id, language=language).all()
    if existing: return existing
    rows=[]
    for concept in concepts[:count]:
        cid=concept.get('concept_id',concept.get('label','main_idea'))
        label=concept.get('label',cid)
        if language=='hin_Deva': prompt=f'इस पाठ में “{label}” का क्या महत्व है?'
        elif language=='sat_Olck': prompt=f'ᱱᱚᱣᱟ ᱯᱟᱴᱷ ᱨᱮ {label} ᱪᱮᱫ ᱥᱟᱭᱛᱟ?'
        else: prompt=f'Why is “{label}” important in this lesson?'
        options=[label, 'Something unrelated','I am not sure']
        rows.append(PracticeQuestion(lesson_version_id=version.id,concept_id=cid,prompt=prompt,options_json=json.dumps(options,ensure_ascii=False),correct_answer=label,explanation=f'This question checks understanding of the concept “{label}”.',language=language,question_type='mcq',approved=approved))
    db.add_all(rows); db.commit()
    return rows

def evaluate_attempt(version: LessonVersion, answers: dict, questions):
    results={}; hits=0; total=max(1,len(questions))
    for q in questions:
        answer=str(answers.get(str(q.id),answers.get(q.concept_id,''))).strip().lower()
        expected=q.correct_answer.strip().lower()
        ok = answer == expected
        results[q.concept_id] = {'understood':ok,'answer':answers.get(str(q.id),answers.get(q.concept_id,''))}
        hits += 1 if ok else 0
    return round(hits*100/total,1), results
