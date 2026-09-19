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
- Marathi translation + approval
- approved practice
- approved Marathi practice
- Marathi audio artifact
- translation confidence/flags

### 6. Worksheet popup failure removed

Worksheet preview is rendered inside the application. Printing/saving as PDF uses the browser print dialog and does not depend on popup permissions.

### 7. Audio authentication fixed

Protected artifacts are fetched with the signed API session and converted to Blob URLs before playback. The UI no longer relies on a raw protected URL inside an `<audio>` element without authorization headers.

### 8. Practice is teacher-controlled

Generated practice starts unapproved. The educator explicitly approves the questions that are allowed into a published lesson.

### 9. Marathi trust state is protected

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

A real Hindi recording should also be passed to the model lab with an explicit language code before claiming Hindi/Marathi STT support:

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
Hindi → Marathi
  ↓
Translation Guard
  ↓
Teacher approval
  ↓
Marathi practice draft
  ↓
Teacher approves practice
  ↓
Worksheet
  ↓
Flashcards
  ↓
Marathi TTS
  ↓
Review
  ↓
Publish
  ↓
Student
  ↓
Marathi
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
- Marathi is not automatically called native-verified
- unapproved AI content cannot be published
- students receive published lesson packages only
- no zero-error claim is made
- no paid runtime API is required
- no hard-coded Marathi translation is used as a substitute for live translation inference


# 19 Sep 2026 — Product-change + SIH alignment audit

## Requested product changes completed

### 1. No language selection during registration

Registration now asks only for identity and password. There is no fixed account language and no Creator-vs-Student account choice. A new account is a flexible classroom account.

### 2. One account can teach and learn

The product now treats classroom ownership/membership as the capability boundary:

```text
User
 ├─ owns Classroom A → creator/editor capabilities
 └─ joins Classroom B → learner capabilities
```

Creating a classroom no longer requires a global admin role. Editing lessons is still protected by classroom ownership on the API. Published lessons remain learner-visible only.

### 3. Language is chosen per workflow

The sidebar language selector is independent of authentication. Lesson creation and Lesson Builder expose source-language selection and target-language selection. Supported prototype languages are:

- Hindi (`hin_Deva`)
- English (`eng_Latn`)
- Marathi (`mar_Deva`)

Therefore selecting Hindi in the workspace does **not** prevent English → Hindi translation. The translation source/target pair is selected inside the lesson workflow.

### 4. Santhali → Marathi prototype substitution

All product code, validation, glossary, practice, worksheet, flashcard, TTS and publish requirements were changed from Santhali/Ol Chiki to Marathi/Devanagari.

This is technically supported by the selected model stack: IndicTrans2 model cards list `mar_Deva`, and AI4Bharat's Indic Parler-TTS documentation lists Marathi among supported languages.

**Important:** this change creates a direct SIH26042 alignment gap because the SIH statement names Ho, Mundari and Santhali as the target tribal languages. Marathi should be described as the current engineering prototype language, not as satisfaction of the tribal-language requirement.

## SIH26042 requirements audit

| Requirement | Current state | Audit note |
|---|---|---|
| Hindi FLN/curriculum translation | **Partial / working core** | Local IndicTrans2 pipeline is integrated and tested for supported pairs. |
| Ho/Mundari/Santhali target language | **Gap** | Current product uses Marathi instead. This is the biggest PS-alignment gap. |
| Synthesized target-language audio | **Working for Marathi** | Local Indic Parler-TTS is integrated and cached; Marathi is supported by the model. |
| Hindi teacher voice input | **Working** | faster-whisper Small is integrated for local transcription. |
| Real-time voice-to-voice, ≤3 seconds | **Gap** | Current flow is record/upload → STT → translation → TTS; a dedicated live streaming voice-to-voice mode and measured sub-3-second latency are not yet implemented. |
| Bilingual worksheets | **Working prototype** | In-app worksheet generation + print/save-PDF flow exists. |
| Visual flashcards | **Partial** | Concept flashcards are generated; they are visual-ready cards rather than a full image-generation/visual pedagogy system. |
| NIPUN Bharat / FLN learning outcomes | **Partial** | Learning outcome is stored and used in lesson content; formal NIPUN outcome IDs/framework metadata are not yet modeled. |
| Offline after synchronization | **Working web/PWA prototype** | IndexedDB caching, service worker, offline practice and sync queue are present. |
| Low-cost Android 9 / ~2 GB RAM verification | **Not yet proven** | PWA behavior exists, but actual Android 9 + 2 GB performance/latency has not been benchmarked in this audit. |
| Teacher-controlled approval | **Working** | Translation and practice require approval before publish. |
| Versioning / rollback | **Working** | Published versions are explicit and rollback preserves history. |

## Current product acceptance flow

```text
Register / Login
      ↓
Flexible Teach + Learn Workspace
      ↓
Create classroom OR Join classroom
      ↓
Create lesson
      ↓
Choose source language
      ↓
Write / record / upload
      ↓
STT + editable transcript
      ↓
Learning outcome + concepts
      ↓
Choose target language(s)
      ↓
IndicTrans2
      ↓
Translation Guard
      ↓
Teacher edit + approval
      ↓
Practice + worksheet + flashcards + TTS
      ↓
Review readiness
      ↓
Publish
      ↓
My Learning
      ↓
Choose learning language
      ↓
Download
      ↓
Offline reading + audio + practice
      ↓
Sync
```

## Verification performed for this revision

- Python source compile: **PASS**
- Web TS/TSX transpile syntax check: **PASS**
- stale Santhali/Ol-Chiki identifiers in application source: **NONE**
- registration language/role fields removed from UI: **PASS**
- new account default is flexible `user`: **PASS**
- classroom creation uses authenticated user + ownership: **PASS**
- lesson editing uses classroom ownership rather than global account role: **PASS**
- source language persisted on lesson edits: **PASS**
- target-language selector supports Hindi/English/Marathi: **PASS**
- Marathi publish gate/practice/TTS path: **PASS at code level**
- full browser build: **NOT VERIFIED in sandbox** because npm dependency installation timed out
- local model inference: **must be re-run on the user's Windows environment**

## Final recommendation for the prototype state

The web product is now structurally closer to the requested flexible classroom product: account language is not fixed, account capability is not globally locked to Student/Creator, and translation direction is chosen per lesson.

For SIH26042 specifically, do not present Marathi as the tribal-language solution. Present it as the current reliable engineering-language prototype and explicitly identify the tribal-language adapter/native-review work as the next PS-compliance step. The other major missing PS feature is the dedicated sub-3-second live voice-to-voice loop.
