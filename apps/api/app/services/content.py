from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from collections.abc import Callable

from sqlalchemy.orm import Session

from ..layer2.concepts import extract_concepts
from ..models import LessonVersion, PracticeQuestion


def now():
    return datetime.now(timezone.utc)


def concepts_as_json(concepts):
    return json.dumps([
        {
            'concept_id': c.concept_id,
            'label': c.label,
            'source_span': c.source_span,
            'definition': c.definition,
            'keywords': list(c.keywords),
            'importance': c.importance,
        }
        for c in concepts
    ], ensure_ascii=False)


def analyze_source(text: str, grade: str, subject: str, topic: str = '') -> dict:
    concepts = extract_concepts(text)
    inferred_topic = topic or next((c.label for c in concepts if c.concept_id != 'main_idea'), 'New Lesson')
    low = text.lower()
    outcome = f'Learner can explain the main idea of {inferred_topic.lower()} using the key concepts.'
    if ('water' in low or 'पानी' in text) and ('plant' in low or 'पौध' in text):
        outcome = 'Learner can explain that plants need water to live and grow.'
    explanation = (
        f'For {grade} {subject}: explain the teacher lesson using the approved source '
        f'and these concepts: {", ".join(c.label for c in concepts)}.'
    )
    activities = [
        'Ask the learner to explain the main idea in their own words.',
        'Ask for one real-world example from the learner’s surroundings.',
    ]
    return {
        'topic': inferred_topic,
        'concepts': [c.__dict__ for c in concepts],
        'learning_objective': outcome,
        'explanation': explanation,
        'activities': activities,
    }


def _base_question(concept_label: str, language: str) -> tuple[str, list[str], str, str]:
    """Return a deterministic source-language question template.

    Santhali is deliberately NOT hard-coded here. When target language is
    Santhali, the route translates this template with the local model before
    saving it as a draft, so unverified AI output never becomes an approved
    translation automatically.
    """
    if language == 'hin_Deva':
        prompt = f'इस पाठ में “{concept_label}” का क्या महत्व है?'
        options = [concept_label, 'यह इस पाठ से संबंधित नहीं है', 'मुझे नहीं पता']
    else:
        prompt = f'Why is “{concept_label}” important in this lesson?'
        options = [concept_label, 'It is unrelated to the lesson', 'I am not sure']
    return prompt, options, concept_label, f'This question checks understanding of the concept “{concept_label}”.'


def ensure_practice(
    db: Session,
    version: LessonVersion,
    language: str = 'hin_Deva',
    count: int = 4,
    approved: bool = False,
    translate_fn: Callable[[str, str, str], str] | None = None,
):
    concepts = json.loads(version.concepts_json or '[]')
    existing = db.query(PracticeQuestion).filter_by(lesson_version_id=version.id, language=language).all()
    if existing:
        return existing

    rows = []
    for concept in concepts[:count]:
        cid = concept.get('concept_id', concept.get('label', 'main_idea'))
        label = concept.get('label', cid)
        source_prompt, options, correct, explanation = _base_question(label, 'hin_Deva' if language == 'hin_Deva' else 'eng_Latn')
        prompt = source_prompt
        translated_options = options
        translated_explanation = explanation

        if language == 'sat_Olck':
            if translate_fn is None:
                raise RuntimeError('A local translation function is required to draft Santhali practice.')
            prompt = translate_fn(source_prompt, 'eng_Latn', 'sat_Olck')
            target_label = translate_fn(label, 'eng_Latn', 'sat_Olck')
            translated_options = [
                target_label,
                translate_fn(options[1], 'eng_Latn', 'sat_Olck'),
                translate_fn(options[2], 'eng_Latn', 'sat_Olck'),
            ]
            correct = target_label
            translated_explanation = translate_fn(explanation, 'eng_Latn', 'sat_Olck')

        rows.append(PracticeQuestion(
            lesson_version_id=version.id,
            concept_id=cid,
            prompt=prompt,
            options_json=json.dumps(translated_options, ensure_ascii=False),
            correct_answer=correct,
            explanation=translated_explanation,
            language=language,
            question_type='mcq',
            approved=approved,
        ))

    if rows:
        db.add_all(rows)
        db.commit()
        for row in rows:
            db.refresh(row)
    return rows


def evaluate_attempt(version: LessonVersion, answers: dict, questions):
    results = {}
    hits = 0
    total = max(1, len(questions))
    for question in questions:
        answer = str(answers.get(str(question.id), '')).strip().lower()
        expected = question.correct_answer.strip().lower()
        # Prepared MCQs use a canonical correct-answer value. The concept result
        # remains attached to the question concept so progress can be aggregated.
        ok = answer == expected
        results[question.concept_id] = {
            'understood': ok,
            'answer': answers.get(str(question.id)),
        }
        hits += 1 if ok else 0
    return round(hits * 100 / total, 1), results
