import html, json

def make_worksheet(lesson, version, language_a='hin_Deva', language_b='sat_Olck'):
    concepts=json.loads(version.concepts_json or '[]')
    outcome=(json.loads(version.learning_objectives_json or '[]') or [''])[0]
    title=html.escape(lesson.title)
    vocab=''.join(f'<li>{html.escape(c.get("label",c.get("concept_id","Concept")))}</li>' for c in concepts[:8])
    questions=''.join(f'<li>{html.escape(c.get("label",c.get("concept_id","Concept")))}: ____________________________________</li>' for c in concepts[:4])
    body=f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>body{{font-family:Arial,sans-serif;max-width:780px;margin:40px auto;padding:0 24px;color:#17352f}}h1{{margin-bottom:6px}}.box{{border:1px solid #d7dedb;border-radius:16px;padding:18px;margin:18px 0}}li{{margin:10px 0}}.lang{{font-weight:700}}</style></head><body><h1>{title}</h1><p><strong>Learning outcome:</strong> {html.escape(outcome)}</p><div class="box"><div class="lang">Vocabulary / शब्द</div><ul>{vocab}</ul></div><div class="box"><div class="lang">Practice / अभ्यास</div><ol>{questions}</ol></div><div class="box"><div class="lang">Explain / समझाइए</div><p>Explain the lesson in your own words:</p><p>____________________________________________________________</p><p>____________________________________________________________</p></div></body></html>"""
    return {'title':lesson.title,'learning_outcome':outcome,'concepts':concepts,'language_a':language_a,'language_b':language_b,'html':body}

def make_flashcards(lesson, version, languages=('hin_Deva','eng_Latn','sat_Olck')):
    concepts=json.loads(version.concepts_json or '[]')
    return [{'concept_id':c.get('concept_id'), 'front':c.get('label'), 'definition':c.get('definition') or f'Key idea: {c.get("label")}', 'example':f'Use the lesson context to explain {c.get("label")}.', 'languages':list(languages)} for c in concepts[:8]]
