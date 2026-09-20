# BhashaSaathi FinalV15 — Speed + Live Audio History

FinalV15 is the incremental release after FinalV14. This release intentionally focuses on the first requested change set: remove avoidable translation/TTS waiting and make temporary Live Translate history explicitly replayable with audio.

## What changed

### 1. Translation model residency
The product supports exactly three validated demo languages: English, Hindi and Marathi.
IndicTrans2 needs three route families:
- English → Indic
- Indic → English
- Indic → Indic

FinalV14 kept only two routes resident, which could evict a route when users switched among all three languages. FinalV15 defaults the route cache to three, so a route does not need to be reloaded after normal language switching.

Key file:
`apps/api/app/adapters/translation.py`

### 2. Faster lesson audio generation
Normal lesson text was previously split into fixed 18-word pieces. This could create unnecessary Parler-TTS generation calls. FinalV15 now uses sentence boundaries and only splits long sentences around 240 characters.

Key file:
`apps/api/app/adapters/tts.py`

The TTS voice-description prompt is also tokenized once per language/speaker and reused while the resident model is alive.

### 3. Background TTS warm-up
The Lesson Builder starts TTS warm-up without blocking the UI:
- when the lesson builder opens;
- after a translation is prepared.

The user can continue working while the model warms.

Key file:
`apps/web/src/pages/LessonBuilderPage.tsx`

### 4. Temporary Live Translate audio
Live sessions remain temporary by default and expire after 24 hours. Saved sessions remain until deleted.

Every completed turn keeps its generated audio Blob in device-local IndexedDB. The history UI now exposes:

`▶ Hear audio`

for a turn with captured audio.

Key files:
- `apps/web/src/pages/LiveTranslatePage.tsx`
- `apps/web/src/lib/liveHistory.ts`

## What was deliberately not changed

Translation Guard/validation remains in classroom mode. Teacher approval is still required before student-facing classroom TTS/publish. No fake latency, fake translations, or fake audio were introduced.

## Performance boundary

FinalV15 removes avoidable model reloads and unnecessary TTS fragmentation. It does **not** claim a fixed number of milliseconds because local latency depends on the user's CPU/GPU, model load state, text length, and browser audio path.

## Local run

Keep your existing local model folders and `.venv`.

Backend:
```powershell
cd D:\git\BhashaSaathi_Local_NoDocker\apps\api
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
cd D:\git\BhashaSaathi_Local_NoDocker\apps\web
npm install
npm run build
npm run dev
```

Open `http://localhost:5173`.
