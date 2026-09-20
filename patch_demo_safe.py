from pathlib import Path

root = Path('/mnt/data/v19inspect')

# 1) Background preparation: stop auto-starting heavyweight TTS on translation approval.
p = root/'apps/api/app/services/background_prep.py'
s = p.read_text(encoding='utf-8')
old = '''    for kind, language in ((\'tts\', target_language), (\'practice\', target_language)):\n            job = _ensure_job(db, version.id, kind, language)\n            if job.status in {\'QUEUED\', \'FAILED\'}:\n                created.append(job.id)\n'''
new = '''        # PRACTICE is cheap enough for the teacher workflow and can prepare in\n        # the background immediately after approval.\n        #\n        # TTS is intentionally NOT auto-started here. Indic Parler-TTS can\n        # monopolize a laptop CPU for a long time and starve translation/practice.\n        # Audio is queued explicitly from the Activities screen instead.\n        kind, language = (\'practice\', target_language)\n        job = _ensure_job(db, version.id, kind, language)\n        if job.status in {\'QUEUED\', \'FAILED\'}:\n            created.append(job.id)\n'''
if old not in s:
    raise SystemExit('background block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# 2) Lesson route: add explicit TTS queue endpoint, and remove warm-on-every-refresh.
p = root/'apps/api/app/api/routes/lessons.py'
s = p.read_text(encoding='utf-8')
old = """def get_lesson(lesson_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), user=Depends(current_user)):\n    lesson = db_lesson(db, lesson_id)\n    if not can_read_lesson(db, lesson, user):\n        raise HTTPException(403, detail={'code': 'LESSON_ACCESS_DENIED', 'message': 'This lesson is not available to your account.'})\n    include_pending = bool(db.query(Group).filter_by(id=lesson.group_id, owner_id=user.id).first())\n    payload = pack(db, lesson, include_pending=include_pending, viewer_id=user.id)\n    required = [lang for lang in ('eng_Latn', 'hin_Deva', 'mar_Deva') if lang != lesson.source_language]\n    background_tasks.add_task(manager.warm_translation_routes, lesson.source_language, required)\n    return payload\n"""
new = """def get_lesson(lesson_id: int, db: Session = Depends(get_db), user=Depends(current_user)):\n    lesson = db_lesson(db, lesson_id)\n    if not can_read_lesson(db, lesson, user):\n        raise HTTPException(403, detail={'code': 'LESSON_ACCESS_DENIED', 'message': 'This lesson is not available to your account.'})\n    include_pending = bool(db.query(Group).filter_by(id=lesson.group_id, owner_id=user.id).first())\n    return pack(db, lesson, include_pending=include_pending, viewer_id=user.id)\n"""
if old not in s:
    raise SystemExit('get_lesson block not found')
s = s.replace(old, new, 1)
needle = """@router.post('/lessons/{lesson_id}/preparations/{job_id}/retry')\ndef retry_preparation(lesson_id: int, job_id: int, db: Session = Depends(get_db), user=Depends(current_user)):\n"""
insert = """@router.post('/lessons/{lesson_id}/preparations/tts/{language}')\ndef queue_tts_preparation(lesson_id: int, language: str, db: Session = Depends(get_db), user=Depends(current_user)):\n    \"\"\"Explicitly queue heavyweight lesson audio. It never starts automatically on approval.\"\"\"\n    lesson = db_lesson(db, lesson_id)\n    require_group_owner(db, lesson, user)\n    version = current_version(db, lesson)\n    allowed = {'eng_Latn', 'hin_Deva', 'mar_Deva'}\n    if language not in allowed:\n        raise HTTPException(400, detail={'code': 'LANGUAGE_UNSUPPORTED', 'message': 'Unsupported lesson language.'})\n    if language == lesson.source_language:\n        text = (version.clean_transcript or version.source_text).strip()\n        if not text:\n            raise HTTPException(400, detail={'code': 'TTS_SOURCE_MISSING', 'message': 'There is no source text for audio generation.'})\n    else:\n        translation = db.query(Translation).filter_by(lesson_version_id=version.id, target_language=language).first()\n        if not translation or not translation.translated_text.strip():\n            raise HTTPException(400, detail={'code': 'TTS_SOURCE_MISSING', 'message': 'Prepare the language translation first.'})\n        if translation.verification_status != 'TEACHER_APPROVED':\n            raise HTTPException(400, detail={'code': 'TTS_REVIEW_REQUIRED', 'message': 'Approve the translation before generating student-facing audio.'})\n    job_id = enqueue_retry(version.id, 'tts', language)\n    return {'job_id': job_id, 'status': 'QUEUED', 'kind': 'tts', 'language': language}\n\n\n@router.post('/lessons/{lesson_id}/preparations/{job_id}/retry')\ndef retry_preparation(lesson_id: int, job_id: int, db: Session = Depends(get_db), user=Depends(current_user)):\n"""
if needle not in s:
    raise SystemExit('retry needle not found')
s = s.replace(needle, insert, 1)
p.write_text(s, encoding='utf-8')

# 3) Frontend: expose explicit audio generation and make Publish race-safe.
p = root/'apps/web/src/lib/api.ts'
s = p.read_text(encoding='utf-8')
old = "  retryPreparation: (id: number, jobId: number) => request<any>(`/lessons/${id}/preparations/${jobId}/retry`, { method: 'POST' }),\n"
new = "  retryPreparation: (id: number, jobId: number) => request<any>(`/lessons/${id}/preparations/${jobId}/retry`, { method: 'POST' }),\n  queueTTSPreparation: (id: number, language: Lang) => request<any>(`/lessons/${id}/preparations/tts/${language}`, { method: 'POST' }),\n"
if old not in s:
    raise SystemExit('api insertion point not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

p = root/'apps/web/src/pages/LessonBuilderPage.tsx'
s = p.read_text(encoding='utf-8')
# add publish lock ref
old = "  const preparationSignature = useRef('');\n"
new = "  const preparationSignature = useRef('');\n  const publishLock = useRef(false);\n"
if old not in s:
    raise SystemExit('publish ref point not found')
s = s.replace(old, new, 1)
# saveDraft guard
old = "  const saveDraft = useCallback(async (silent = false) => {\n    if (!hydrated.current) return;\n"
new = "  const saveDraft = useCallback(async (silent = false) => {\n    if (!hydrated.current || publishLock.current) return;\n"
if old not in s:
    raise SystemExit('save guard not found')
s = s.replace(old, new, 1)
# add explicit queueAudio before playArtifact
needle = "  const playArtifact = useCallback(async (language: Lang) => {\n"
insert = """  const queueAudio = (language: Lang) => run(`Queueing ${label(language)} audio…`, async () => {\n    await api.queueTTSPreparation(lessonId, language);\n    setAudioStatus((old) => ({ ...old, [language]: 'queued' }));\n    push(`${label(language)} audio queued. It is separate from publishing and practice.`);\n  });\n\n"""
if needle not in s:
    raise SystemExit('queueAudio insertion point not found')
s = s.replace(needle, insert + needle, 1)
# replace publish fn
old = """  const publish = () => run('Publishing lesson…', async () => {\n    if (!readiness.publish) throw new Error(`Publish is blocked: ${readiness.problems.join(' • ')}`);\n    const updated = await api.publish(lessonId);\n    setPack(updated);\n    await loadVersions();\n    push('Lesson published. Students can now download it for offline learning.');\n  });\n"""
new = """  const publish = () => run('Publishing lesson…', async () => {\n    if (!readiness.publish) throw new Error(`Publish is blocked: ${readiness.problems.join(' • ')}`);\n    publishLock.current = true;\n    if (autosaveTimer.current) {\n      window.clearTimeout(autosaveTimer.current);\n      autosaveTimer.current = null;\n    }\n    try {\n      const updated = await api.publish(lessonId);\n      setPack(updated);\n      await loadVersions();\n      push('Lesson published. Students can now download it for offline learning.');\n    } catch (err) {\n      publishLock.current = false;\n      throw err;\n    }\n  });\n"""
if old not in s:
    raise SystemExit('publish fn not found')
s = s.replace(old, new, 1)
# replace audio UI state block with explicit Generate on idle
old_fragment = """ : state === 'error' ? <Button variant=\"secondary\" onClick={() => { const job = pack.preparations?.find((item) => item.kind === 'tts' && item.language === lang); if (job) void run('Retrying audio…', async () => { await api.retryPreparation(lessonId, job.id); }); }}>Retry</Button> : <Status tone=\"info\">Background</Status>}"""
new_fragment = """ : state === 'error' ? <Button variant=\"secondary\" onClick={() => { const job = pack.preparations?.find((item) => item.kind === 'tts' && item.language === lang); if (job) void run('Retrying audio…', async () => { await api.retryPreparation(lessonId, job.id); }); else void queueAudio(lang); }}>Retry</Button> : state === 'idle' ? <Button variant=\"secondary\" onClick={() => void queueAudio(lang)}>Generate</Button> : <Status tone=\"info\">Background</Status>}"""
if old_fragment not in s:
    raise SystemExit('audio UI fragment not found')
s = s.replace(old_fragment, new_fragment, 1)
p.write_text(s, encoding='utf-8')

# 4) Mark old queued/running TTS jobs failed on startup so an old V19 DB cannot immediately re-trigger heavy audio.
p = root/'apps/api/app/services/background_prep.py'
s = p.read_text(encoding='utf-8')
old = """        rows = db.query(PreparationJob).filter(PreparationJob.status.in_(['QUEUED', 'RUNNING'])).all()\n        ids = []\n        for row in rows:\n            row.status = 'QUEUED'\n            row.started_at = None\n            row.finished_at = None\n            ids.append(row.id)\n        db.commit()\n"""
new = """        rows = db.query(PreparationJob).filter(PreparationJob.status.in_(['QUEUED', 'RUNNING'])).all()\n        ids = []\n        for row in rows:\n            # TTS is now opt-in. Do not resurrect old heavy audio work when the\n            # API restarts for a viva/demo; the teacher can press Generate later.\n            if row.kind == 'tts':\n                row.status = 'FAILED'\n                row.error = 'Audio generation is manual in demo-safe mode.'\n                row.started_at = None\n                row.finished_at = _now()\n                continue\n            row.status = 'QUEUED'\n            row.started_at = None\n            row.finished_at = None\n            ids.append(row.id)\n        db.commit()\n"""
if old not in s:
    raise SystemExit('resume block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# Write a clear demo note.
(root/'DEMO_SAFE_V20_CHANGES.md').write_text('''# BhashaSaathi V20 — Demo-safe preparation fixes\n\n- Publishing never waits for TTS or practice.\n- Translation approval auto-starts practice only.\n- Heavy Parler-TTS is now explicit/opt-in from Activities → Audio → Generate.\n- Lesson GET no longer starts translation warm-up on every refresh/poll.\n- Old queued/running TTS jobs are not resurrected on API restart.\n- Publish cancels pending autosave and locks it after successful publish, preventing a published lesson from being immediately converted into a new draft by a stale autosave.\n- The live voice-translation TTS path is unchanged; this patch specifically fixes lesson-builder/demo stability.\n''', encoding='utf-8')

print('patched')
