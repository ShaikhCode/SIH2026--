# BhashaSaathi FinalV14 — What to copy and why

This is the final performance-focused local build for the current prototype.

## Keep your existing model weights and `.venv`

The ZIP does **not** contain model weights, the Python virtual environment, or your private `.env`.

Keep these existing folders/files from your Windows project:

```text
apps/api/.venv/
apps/api/models/
apps/api/.env
```

Expected model folders:

```text
apps/api/models/translation/indic-indic/
apps/api/models/translation/en-indic/
apps/api/models/translation/indic-en/
apps/api/models/stt/whisper-small/
apps/api/models/tts/indic-parler-tts/
apps/api/models/tts/flan-t5-large/
```

## Key files in FinalV14

### Live Translate

```text
apps/api/app/services/live_translation.py
apps/api/app/api/routes/live.py
apps/web/src/pages/LiveTranslatePage.tsx
apps/web/src/lib/liveHistory.ts
```

These files implement the free homepage live-translation feature, bounded pipeline, WebSocket transport, streaming PCM playback, Buds/device selection, and temporary/saved local history.

### Fast model path

```text
apps/api/app/services/model_manager.py
apps/api/app/adapters/translation.py
apps/api/app/adapters/stt.py
apps/api/app/adapters/tts.py
apps/api/app/api/routes/runtime.py
```

These are the performance-critical changes. Models remain warm; translation/TTS caches remove repeated work; runtime warm-up avoids first-click model loading.

### Classroom product

```text
apps/web/src/pages/LessonBuilderPage.tsx
apps/api/app/api/routes/lessons.py
apps/api/app/services/content.py
apps/api/app/services/publish.py
```

The classroom lifecycle remains teacher-controlled: source → understand → concepts → translate → review → learning kit → publish.

### Product shell

```text
apps/web/src/pages/LandingPage.tsx
apps/web/src/components/Shell.tsx
apps/web/src/App.tsx
apps/web/src/types.ts
```

The landing page exposes Live Translate without account. The normal authenticated workspace remains available for teaching and learning.

### Offline/local history

```text
apps/web/src/lib/idb.ts
apps/web/src/lib/liveHistory.ts
apps/web/public/sw.js
```

Student offline content and Live Translate device history stay in browser-managed local storage.

## First run after copying

### Terminal 1 — API

```powershell
D:
cd \git\BhashaSaathi_Local_NoDocker\apps\api
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2 — Web

```powershell
D:
cd \git\BhashaSaathi_Local_NoDocker\apps\web
npm install
npm run build
npm run dev
```

Open:

```text
http://localhost:5173
```

## Validate the local models

Do not blindly reinstall the Python environment on Python 3.13. Your previously verified environment uses:

```text
transformers 4.46.1
huggingface_hub 0.36.0
parler-tts 0.2.2
IndicTransToolkit 1.1.1
faster-whisper 1.2.1
torch 2.14.0+cpu
```

Run:

```powershell
python scripts\verify_models.py
python scripts\model_lab.py
```

Then run the browser build:

```powershell
npm run build
```

## Live demo setup

Use:

```text
Speaking language: any of English / Hindi / Marathi
Listener language: a different one of English / Hindi / Marathi
Microphone: Laptop built-in mic
Output: Buds / headphones
```

Keep the Buds microphone disabled for this demo setup. The goal is to send the speaker output directly to the listener's ears and avoid acoustic feedback into the laptop microphone.

## History behavior

Live Translate history is device-local:

```text
new session
  ↓
temporary history
  ↓ 24 hours
auto-delete

or

Save session
  ↓
kept until user deletes it
```

Generated TTS audio can be stored with the local history entry; the microphone input itself is never persisted by the live backend.

## Important limitation

FinalV14 is optimized for the current validated prototype language set: **English, Hindi and Marathi**. This is a deliberate engineering/demo scope and should not be presented as full SIH26042 tribal-language coverage.
