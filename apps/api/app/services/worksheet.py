import html, json


def _translation_map(translations):
    return {t.target_language: t.translated_text for t in (translations or [])}


def make_worksheet(lesson, version, translations=None, language_a='hin_Deva', language_b='sat_Olck'):
    concepts = json.loads(version.concepts_json or '[]')
    outcome_list = json.loads(version.learning_objectives_json or '[]')
    outcome = outcome_list[0] if outcome_list else ''
    texts = _translation_map(translations)
    source = version.clean_transcript or version.source_text
    target = texts.get(language_b, 'Translation not prepared yet.')
    english = texts.get('eng_Latn', 'Translation not prepared yet.')
    title = html.escape(lesson.title)

    vocab = ''.join(
        f'<li><strong>{html.escape(c.get("label", c.get("concept_id", "Concept")))}</strong></li>'
        for c in concepts[:8]
    ) or '<li>No approved concepts yet.</li>'
    body = f'''<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
    <style>body{{font-family:Arial,sans-serif;max-width:820px;margin:32px auto;padding:0 24px;color:#17352f}}
    h1{{margin-bottom:6px}}h2{{font-size:17px;margin-bottom:8px}}.box{{border:1px solid #d7dedb;border-radius:16px;padding:18px;margin:18px 0}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.label{{font-weight:700;color:#0b6759;margin-bottom:6px}}
    li{{margin:8px 0}}.line{{border-bottom:1px solid #b9c5c1;height:28px;margin:4px 0}}
    @media print{{body{{margin:10mm auto}}.box{{break-inside:avoid}}}}</style></head><body>
    <h1>{title}</h1><p><strong>Learning outcome:</strong> {html.escape(outcome)}</p>
    <div class="box"><h2>Vocabulary / शब्दावली</h2><ul>{vocab}</ul></div>
    <div class="box"><h2>Read & understand</h2><div class="grid">
      <div><div class="label">Hindi</div><p>{html.escape(source)}</p></div>
      <div><div class="label">Santhali</div><p>{html.escape(target)}</p></div>
    </div></div>
    <div class="box"><h2>English support</h2><p>{html.escape(english)}</p></div>
    <div class="box"><h2>Practice / अभ्यास</h2><ol>
      {''.join(f'<li>Explain <strong>{html.escape(c.get("label", "this concept"))}</strong> in your own words.<div class="line"></div><div class="line"></div></li>' for c in concepts[:4])}
    </ol></div>
    <div class="box"><h2>Student</h2><p>Name: ____________________________ &nbsp;&nbsp; Date: ______________</p></div>
    </body></html>'''
    return {
        'title': lesson.title,
        'learning_outcome': outcome,
        'concepts': concepts,
        'language_a': language_a,
        'language_b': language_b,
        'html': body,
    }


def make_flashcards(lesson, version, translations=None, languages=('hin_Deva', 'eng_Latn', 'sat_Olck')):
    concepts = json.loads(version.concepts_json or '[]')
    texts = _translation_map(translations)
    return [
        {
            'concept_id': c.get('concept_id'),
            'front': c.get('label'),
            'definition': c.get('definition') or f'Key idea from {lesson.title}: {c.get("label")}.',
            'example': c.get('source_span') or c.get('label'),
            'language_labels': {
                'hin_Deva': c.get('label') if 'hin_Deva' in languages else None,
                'eng_Latn': c.get('label') if 'eng_Latn' in languages else None,
                'sat_Olck': texts.get('sat_Olck') if 'sat_Olck' in languages else None,
            },
            'languages': list(languages),
        }
        for c in concepts[:8]
    ]
