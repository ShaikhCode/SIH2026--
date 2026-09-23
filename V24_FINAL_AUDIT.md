# BhashaSaathi V24 — Final Product Audit

## Product contract
- English is the default/main language.
- Hindi and Marathi are optional target languages.
- Santali (`sat_Olck`) is an optional temporary language: it is stored, displayed, playable and available to students after publish without the normal approval gate.
- Lesson source/spoken language is persisted on `Lesson.source_language`.
- Live Translate persists both speaker and listener language in device history and exposes all four supported live languages.

## Santali coverage
- Translation: IndicTrans2 supports Santali using `sat_Olck` (Ol Chiki).
- TTS: Indic Parler-TTS supports Santali; recommended Santali speakers documented by AI4Bharat are Arjun / Pushpa.
- STT: optional AI4Bharat IndicConformer 600M multilingual checkpoint supports Santali (`sat`).
- The Santali STT model is optional because it is a gated model and can be large; the rest of the product remains usable without it.

## TTS reliability / speed
- Parler-TTS remains manual and non-blocking.
- GPU is reserved for TTS by default; translation and Whisper stay CPU-side in the demo profile.
- Output tokens are dynamically capped from text length to prevent short inputs from producing runaway audio.
- `PARLER_COMPILE=1` enables optional `torch.compile`; default is OFF for 4 GB RTX 2050 stability.
- `PARLER_MAX_OUTPUT_SECONDS` and `PARLER_LIVE_MAX_OUTPUT_SECONDS` provide hard safety caps.
- TTS cache keys include model/prompt revision.

## Job reliability
- TTS jobs are idempotent: repeated clicks cannot create duplicate worker jobs.
- Jobs move through QUEUED -> RUNNING -> READY/FAILED.
- Publish never waits for derivative jobs.
- Santali temporary audio may be generated without approval; English/Hindi/Marathi translated audio still uses the normal approval gate.

## Web UX
- Santali appears in source, optional target, student language switcher and Live Translate.
- Santali uses Ol Chiki as its script metadata.
- Temporary Santali clearly shows its status so teachers do not mistake it for a formally reviewed translation.

## Verification performed in this build workspace
- Python syntax compilation: required for all `.py` files.
- Frontend type/build checks should be run in the Windows project environment with `npm install` and `npm run build` because dependencies are not vendored in the ZIP.
- Runtime model checks are separate; the ZIP does not include multi-GB model weights.
