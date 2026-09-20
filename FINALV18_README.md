# BhashaSaathi FinalV18 — Fast Teacher Review + Background Preparation

FinalV18 is the speed/flow release after FinalV17.

## Product changes in this release

### 1. Learning-outcome step removed
The educator workflow is now:

`Source → Concepts → Languages → Activities → Review`

The lesson builder no longer asks the teacher to generate or approve a learning outcome, and publishing no longer blocks on it. The legacy database field remains only for compatibility with older saved versions.

### 2. Teacher reviews the translation text
Translation remains a human approval gate. The target text appears first; audio is not a second approval step.

For a teacher who does not know the target language, the Languages step adds **Meaning Check**. It performs a source-language back-translation on demand and caches that result for later comparison. This is supporting evidence, not a claim of perfect semantic verification.

### 3. Post-approval work runs in the background
After a translation is approved:

- TTS generation is queued in the persistent preparation queue.
- Practice drafts are queued.
- The HTTP approval response is deliberately small and fast.
- Jobs are stored in SQLite so a restart can resume queued/running work.

The editor polls only the preparation status endpoint and refreshes the full lesson pack when a job state changes.

### 4. Audio is stored and replayable
Generated audio is registered as a normal lesson artifact. The educator can press **Hear** without regenerating TTS.

### 5. Student language feedback
On a published lesson, a student can:

- mark a translation **Looks correct**;
- **Report an issue**.

Teacher approval remains the publication gate. Student feedback is a later language-quality signal for the educator.

### 6. Translation warm-up
Opening the lesson background-warms only the routes required by the current source language. The web editor also begins the same warm-up path without blocking the UI.

### 7. Short-text decoding
IndicTrans2 interactive decoding uses an adaptive output ceiling for short classroom phrases, while preserving the existing greedy/fast configuration.

## Files added/changed

### Backend
- `apps/api/app/models/entities.py` — `PreparationJob`, `TranslationFeedback`.
- `apps/api/app/services/background_prep.py` — persistent low-contention background worker and restart recovery.
- `apps/api/app/api/routes/lessons.py` — fast approval response, Meaning Check, preparation status/retry, concept-only preparation, route warm-up.
- `apps/api/app/api/routes/student.py` — student translation feedback.
- `apps/api/app/schemas.py` — feedback schema.
- `apps/api/app/services/publish.py` — learning outcome removed as a publication requirement.
- `apps/api/app/services/worksheet.py` — learning-outcome display removed.
- `apps/api/app/services/model_manager.py` — background translation route warm-up.
- `apps/api/app/adapters/translation.py` — adaptive max-token ceiling for short text.

### Frontend
- `apps/web/src/pages/LessonBuilderPage.tsx` — five-step fast workflow, Meaning Check, background prep UX, no learning-outcome step, persisted preparation status.
- `apps/web/src/pages/StudentLessonPage.tsx` — student translation feedback.
- `apps/web/src/pages/StudentHomePage.tsx` — no learning-outcome card copy.
- `apps/web/src/lib/api.ts` — preparation, Meaning Check and feedback APIs.
- `apps/web/src/types.ts` — feedback/preparation state types.

## Verification performed

- Python compile check: PASS.
- FastAPI application import: PASS.
- New SQLite tables created: PASS.
- Teacher approval fast-path direct test: PASS; measured direct function response in test fixture: 5 ms, before background work.
- Student translation feedback fixture: PASS.
- Publication gate fixture confirms `LEARNING_OUTCOME_MISSING` is no longer produced: PASS.
- FinalV18 static speed/flow audit: 12/12 checks passed.

## Browser build note
The sandbox does not have a completed `node_modules` install for this release. `npm install --ignore-scripts` did not finish within the available build window, so a real Vite production build was not claimed as tested here. Run the browser build on the Windows machine with the project's normal Node environment.

## Runtime model note
The ZIP intentionally excludes large model weights and the local `.venv`. Keep the existing `apps/api/models` and working Python environment.
