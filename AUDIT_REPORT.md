# BhashaSaathi — Final Product + Local Model Audit

## Audit objective

This build was audited as one system: React web product, FastAPI orchestration, database/access control, Layer 2, offline flow, model adapters, model filesystem paths, and the actual local-model evidence supplied in the 18 Sep 2026 debugging handoff.

The product contract remains the SIH classroom workflow: teacher input → understanding → concepts → multilingual translation → verification → teacher approval → learning assets → publish → student learning → offline practice → synchronization.

## Critical findings resolved in this final build

### 1. Critical model path bug

The application configuration previously resolved the model root from `apps/api/app/core/config.py` using the wrong parent directory. That made the runtime look under:

```text
apps/api/app/models
```

while the real model folders are under:

```text
apps/api/models
```

The final build resolves `MODELS_ROOT` from the actual `apps/api` runtime root. This is the direct product-integration fix for the earlier “local translation model could not prepare this translation” symptom.

### 2. IndicTrans2 loading now matches the proven diagnostic flow

The adapter uses:

```text
IndicProcessor
  ↓
preprocess_batch
  ↓
local tokenizer
  ↓
model.generate
  ↓
batch_decode
  ↓
postprocess_batch
```

with `trust_remote_code=True` and `local_files_only=True`, matching the known-working diagnostic path.

### 3. Whisper loader matches the actual checkpoint format

The diagnostic handoff proved that the installed `whisper-small` folder contains a CTranslate2/faster-whisper style `model.bin`. The final product therefore uses `faster-whisper` and never tries to rename or reinterpret the file as a Transformers checkpoint.

### 4. Parler-TTS support now follows the actual two-tokenizer design

The final adapter uses:

- local Parler prompt tokenizer
- local FLAN-T5 description tokenizer
- local feature extractor
- `ParlerTTSForConditionalGeneration`
- local-only loading
- current generation output handling

The known remaining local dependency from the diagnostic handoff is the FLAN-T5 description tokenizer. The final code provides `scripts/download_tts_support.py` to download only those tokenizer/config assets, not the full FLAN-T5 model weights.

### 5. Web lesson workflow is state-driven

The Lesson Builder no longer treats the step number as proof that a module is finished. The review/readiness panel is derived from actual backend data.

Publishing now checks:

- source
- learning outcome
- concepts
- English translation + approval
- Santhali translation + approval
- approved practice
- approved Santhali practice
- Santhali audio artifact
- translation confidence/flags

### 6. Worksheet popup failure removed

Worksheet preview is rendered inside the application. Printing/saving as PDF uses the browser print dialog and does not depend on popup permissions.

### 7. Audio authentication fixed

Protected artifacts are fetched with the signed API session and converted to Blob URLs before playback. The UI no longer relies on a raw protected URL inside an `<audio>` element without authorization headers.

### 8. Practice is teacher-controlled

Generated practice starts unapproved. The educator explicitly approves the questions that are allowed into a published lesson.

### 9. Santhali trust state is protected

Teacher approval and qualified/native-language verification are separate states. The teacher cannot self-label an output as native-verified through the API.

### 10. Student content is publication-gated

Students only receive `PUBLISHED` lessons. Non-owner members—even if their global account role happens to be admin—cannot see another classroom owner's draft lessons.

### 11. Offline synchronization is user-isolated

Sync records are tied to the signed-in user. Failed queued attempts remain pending instead of being silently marked synchronized. Attempt processing uses a nested transaction so one failed operation cannot roll back unrelated successful operations in the same push batch.

## Actual model evidence used

The supplied 18 Sep 2026 local-model handoff established:

- real EN→Hindi IndicTrans2 inference: PASS
- real Hindi→EN IndicTrans2 inference: PASS
- faster-whisper checkpoint loading: PASS
- English STT: PASS
- IndicTrans2 processor construction: PASS
- TTS package/model initialization: partial PASS
- TTS description tokenizer: blocked until the local FLAN-T5 tokenizer assets are provisioned

The final product incorporates those proven loader decisions rather than replacing them with unrelated model code.

## Validation performed in the build workspace

### Python/backend

- `python -m compileall -q apps/api scripts core`: PASS
- FastAPI/TestClient integration: PASS
- public registration cannot escalate to admin: PASS
- owner classroom creation: PASS
- group join: PASS
- non-owner admin cannot see another owner's drafts: PASS
- student cannot see unpublished lessons: PASS
- publish gate returns explicit blockers: PASS
- model health resolves the correct `apps/api/models` root: PASS
- fresh Alembic migration + seed: PASS
- DB smoke checks: PASS

### Frontend source

- TypeScript/TSX syntax transpilation across the source tree: PASS
- popup worksheet flow removed: PASS
- authenticated media loading implemented: PASS
- role-gated routes present: PASS
- builder readiness is backend-state-driven: PASS

### Windows-only final verification

The sandbox cannot access the user's local `D:` drive, model weights, browser, or Windows npm cache. Therefore the following must be executed on the actual Windows machine:

```powershell
python scripts\verify_models.py
python scripts\model_lab.py --skip-tts
python scripts\model_lab.py
npm install
npm run build
```

A real Hindi recording should also be passed to the model lab with an explicit language code before claiming Hindi/Santhali STT support:

```powershell
python scripts\model_lab.py --audio path\to\hindi_recording.wav --stt-language hin_Deva --skip-tts
```

## Product acceptance sequence

```text
Login
  ↓
Create classroom
  ↓
Create lesson
  ↓
Hindi source / recording
  ↓
Whisper transcript
  ↓
Edit transcript
  ↓
Understand
  ↓
Concepts + learning outcome
  ↓
Hindi → English
Hindi → Santhali
  ↓
Translation Guard
  ↓
Teacher approval
  ↓
Santhali practice draft
  ↓
Teacher approves practice
  ↓
Worksheet
  ↓
Flashcards
  ↓
Santhali TTS
  ↓
Review
  ↓
Publish
  ↓
Student
  ↓
Santhali
  ↓
Read + Listen + Practice
  ↓
Download
  ↓
Offline
  ↓
Answer
  ↓
Sync
```

## Trust constraints preserved

- original teacher source is preserved
- AI output remains reviewable
- Santhali is not automatically called native-verified
- unapproved AI content cannot be published
- students receive published lesson packages only
- no zero-error claim is made
- no paid runtime API is required
- no hard-coded Santhali translation is used as a substitute for live translation inference
