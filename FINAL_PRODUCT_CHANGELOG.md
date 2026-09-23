# BhashaSaathi V25 — Final Product Changelog

## V25 — final product/viva baseline

### Lesson Builder
- English remains the default source/main lesson language.
- Hindi and Marathi are explicit optional targets.
- Santali is an explicit optional temporary target and never requires approval.
- Source-only publishing is supported.
- Changing the lesson source language no longer silently inserts English as a target.
- Publish is independent of optional translation, practice, worksheet, and audio generation.

### Santali
- Added `sat_Olck` to API and web language registries.
- Added source-language persistence for Santali.
- Added IndicTrans2 Santali translation routes.
- Added Indic Parler-TTS Santali speaker routing.
- Added optional IndicConformer Santali STT routing.
- Added temporary Santali storage/edit path without teacher approval.
- Added Santali to student language selection and Live Translate.

### Audio/reliability
- TTS is explicit/on-demand and cached.
- One preparation job is submitted at a time; duplicate retry requests are idempotent.
- Audio can be generated for the original lesson source as well as translated text.
- Santali temporary translations are accepted for audio generation.
- Preparation jobs have terminal `READY` / `FAILED` outcomes and a safety timeout.
- API restart does not resurrect heavyweight generation automatically.

### Runtime/performance
- Translation and Whisper default to CPU so the 4 GB GPU remains available for TTS.
- Parler uses CUDA + FP16 when available.
- Description inputs are cached.
- Long translation/TTS text is chunked before tokenizer limits are reached.
- Safe CUDA TF32 flags are enabled for the TTS runtime where available.
- `PARLER_COMPILE=1` remains opt-in because the target GPU is memory-constrained.

### Final verification
- Python syntax: PASS.
- Live protocol + Santali routing protocol: PASS.
- FastAPI import: PASS.
- API health: PASS.
- Live languages endpoint: PASS.
- Static product invariants: PASS.

### Known hardware limitation
The measured target-laptop Parler benchmark was 116.12 seconds to generate 30.20 seconds of audio at 3.85x realtime, with 3.46 GB peak VRAM. Therefore the product never makes classroom publishing depend on TTS completion.
