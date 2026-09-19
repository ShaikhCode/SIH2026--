# BhashaSaathi — Final Local No-Docker Build

> **Translate the classroom, not just the words.**
>
> **AI prepares. The educator decides. The learner learns.**

BhashaSaathi is a teacher-first multilingual classroom platform for SIH26042. The final local build is designed around a real classroom loop: teacher input → speech/text understanding → concepts → multilingual translation → Translation Guard → teacher approval → audio/worksheet/flashcards → publish → student learning → offline practice → sync.

## Locked demo path

- Source language can be Hindi, English, or Marathi
- Marathi showcase in **Devanagari**
- English + Hindi available as additional translation targets
- IndicTrans2 for local translation
- faster-whisper Small for Hindi/English teacher speech
- Indic Parler-TTS for local/server-side audio generation and caching
- SQLite + local artifacts
- IndexedDB + Service Worker for offline student learning
- No paid API is required at runtime

### Product language decision

The current prototype intentionally uses **Marathi** instead of Santhali because the team has chosen a language stack they can demonstrate reliably end-to-end with the local IndicTrans2 and Indic Parler-TTS models. IndicTrans2 officially lists `mar_Deva`, and AI4Bharat's Indic Parler-TTS model lists Marathi as an officially supported language.

**SIH26042 compliance note:** the problem statement explicitly asks for Ho, Mundari and Santhali and accepts a minimum of one tribal language at prototype stage. Marathi is therefore a deliberate prototype substitution, not a claim of full SIH language compliance. A tribal-language adapter and qualified native-language review remain required before presenting Marathi as the final deployment language.

## What is included

### Educator

Authentication, flexible teach + learn accounts, classroom groups, join codes, lesson creation, voice recording/upload, editable STT transcript, learning outcome metadata, concept extraction, deterministic classroom suggestions, Hindi/English/Marathi translation, Translation Guard, teacher editing/approval, cached TTS, worksheet preview, concept flashcards, practice generation, publish, version history and rollback, model/API diagnostics.

### Student

Group lessons, language selection, published lesson player, cached audio, worksheet and concept cards, practice, offline attempts, pending sync queue, reconnect synchronization.

### Trust rules

Original lesson text is preserved. AI output is reviewable. Marathi is never presented as native-verified merely because a model generated it. Publish requires teacher approval and required review flags to be clear. The product never claims zero translation errors.

## Folder layout

```text
BhashaSaathi_Local_NoDocker/
├─ apps/
│  ├─ api/
│  │  ├─ app/
│  │  │  └─ layer2/        # runtime Layer 2 used by FastAPI
│  │  ├─ alembic/
│  │  ├─ data/
│  │  ├─ models/              # YOUR MODEL WEIGHTS STAY HERE
│  │  │  ├─ translation/
│  │  │  ├─ stt/
│  │  │  └─ tts/
│  │  └─ requirements.txt
│  └─ web/
├─ core/
│  └─ layer2/              # reference copy

├─ scripts/
└─ .env.example
```

## IMPORTANT when copying the final ZIP

This ZIP **does not contain your model weights or `.venv`**. Copy/replace the code files and leave your existing `apps/api/models/` folder and `apps/api/.venv/` untouched.

Also keep your existing `apps/api/.env` file. The ZIP contains `.env.example`, not your private local `.env`.

## Windows first run

### 1. Backend

```powershell
D:
cd \git\BhashaSaathi_Local_NoDocker\apps\api
.\.venv\Scripts\activate
# Keep the already-validated local model environment; do not blindly reinstall it on Python 3.13.
# If dependencies are missing, use the pinned versions documented in MODEL_INTEGRATION_HANDOFF.md.
```

Your model folders should already pass:

```powershell
python ..\..\scripts\check_environment.py
python ..\..\scripts\verify_models.py
```

Then reset only the local database once after installing the final code:

```powershell
python ..\..\scripts\reset_local_db.py
alembic upgrade head
python ..\..\scripts\seed_demo.py
```

### 2. TTS support tokenizer

The verified Parler checkpoint depends on a local FLAN-T5 *description tokenizer*. The main Parler weights are already in your TTS model folder.

Run once if `apps/api/models/tts/flan-t5-large` is not present:

```powershell
python ..\..\scripts\download_tts_support.py
```

Then verify it through:

```powershell
python ..\..\scripts\model_lab.py --skip-tts
```

This downloads tokenizer/config support only. It does **not** download another large TTS model.

### 3. Start FastAPI

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health:

```text
http://127.0.0.1:8000/api/v1/health
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

### 4. Frontend — second PowerShell

```powershell
D:
cd \git\BhashaSaathi_Local_NoDocker\apps\web
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Demo accounts

```text
Teacher
teacher@bhashasaathi.local
Demo@1234

Student
student@bhashasaathi.local
Demo@1234
```

The demo uses `.local` addresses intentionally. The backend accepts these local-only demo identifiers without requiring public-domain email validation.

## Recommended SIH demo flow

1. Sign in.
2. Open **Demo Primary Classroom**.
3. Create/open **Why Plants Need Water**.
4. Enter or record Hindi.
5. Run Whisper and edit the transcript.
6. Run Understand to get concepts + learning outcome.
7. Choose any supported target language (for example Marathi) and generate the translation.
8. Show Translation Guard flags/confidence.
9. Review/edit and teacher-approve.
10. Generate practice, worksheet, flashcards and audio.
11. Publish.
12. Open **My Learning** and select Marathi, Hindi, or English.
13. Download the lesson.
14. Open the lesson and play cached audio.
15. Disconnect network.
16. Continue reading/practice offline.
17. Submit an offline attempt.
18. Restore network and press **Sync now**.

## AI settings

Use real local AI for the final demo:

```text
DEMO_MODE=false
TRANSLATION_ENABLED=true
STT_ENABLED=true
TTS_ENABLED=true
LLM_ENABLED=false
```

No model weights are bundled in Git/ZIP. Your verified local model folders are reused.

## Low-resource behavior

The app loads heavy models lazily. Student offline learning does not require generative AI on the Android/device side. TTS is intended to be generated/cached during lesson preparation and synchronized to learners.

## Testing

Backend syntax/import and clean SQLite migration/seed paths are checked in the build workspace. Frontend source is transpile-validated here. A full `npm install` was not completed in the sandbox because the npm registry was not reachable for dependency installation, so run `npm install` + `npm run build` on your Windows machine before the demo.

The local Windows model directories are **not accessible from this sandbox**, so final model inference must be run on your machine; your `verify_models.py` output already confirms the required model folders are populated.

## Product boundaries

The MVP intentionally does not add social networking, parent portals, leaderboards, blockchain, huge analytics, ERP, dozens of autonomous agents, all Indian languages, foundation-model training, or full generative AI on low-end Android.

## FinalV14 performance/live release notes

This archive is **FinalV14** (13 prior ZIP builds were present in the working build directory).

The major additions are the homepage **Live Translate** tool (English/Hindi/Marathi only), bounded pipelining, warm-model runtime, translation/TTS caches, runtime prewarm, browser 16 kHz capture, streamed Parler-TTS PCM playback, and 24-hour temporary device-local Live Translate history.

See `FINALV14_README.md`, `FINALV14_AUDIT_REPORT.md`, and `VERSION_HISTORY.md` for the exact file map and audit details.
