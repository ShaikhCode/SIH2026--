# BhashaSaathi V25 — Final Product Audit

Status: release candidate / viva-stable local MVP
Audit target: Windows laptop with RTX 2050 4 GB, 12 GB RAM

## 1. Product contract

- English is the default/main lesson language.
- Hindi and Marathi are optional target languages.
- Santali is an optional temporary language; it is stored but does not require teacher approval.
- The lesson source/spoken language is persisted in `Lesson.source_language`.
- A lesson can therefore start in English, Hindi, Marathi, or Santali.
- Publish requires valid source content/title only. Optional translations, practice, worksheet, and audio never block Publish.
- Audio is explicit/on-demand and cached; it is not auto-started by approval or Publish.
- Live Translate supports English, Hindi, Marathi, and Santali. Live sessions store source/target language direction in device-local history.

## 2. Santali end-to-end design

### Text translation
IndicTrans2 uses `sat_Olck` for Santali and the same source-to-Indic / Indic-to-source routing used by the rest of the supported language set.

### TTS
Indic Parler-TTS supports Santali. The product maps the default Santali speaker to `Arjun`; users can override the speaker setting where exposed.

### STT
Santali voice input is routed to IndicConformer rather than Whisper. The Santali STT model is optional because the corresponding AI4Bharat checkpoint may require model-term acceptance and a Hugging Face token. Run `scripts\\download_santali_stt.py` after accepting the model terms and setting `HF_TOKEN` when required.

### Temporary semantics
Santali translations are saved with `verification_status=TEMPORARY` and `native_review_status=NOT_REQUIRED`. They remain visible to students and can be edited without passing through the normal approval gate.

## 3. Major bugs fixed in this release line

1. Publish could be blocked or destabilized by unrelated TTS/practice preparation. Publish is now source-first.
2. Background preparation polling could recreate itself through `pack` state changes. Polling now depends on stable lesson/refresh inputs.
3. Retry could submit the same TTS job repeatedly. Job enqueueing is idempotent and UI state changes immediately to queued.
4. Audio source generation previously assumed every audio language had a Translation row. Source-language audio now uses the lesson source correctly.
5. Santali temporary TTS was rejected by the final stale-state validation. It is now explicitly permitted.
6. The lesson TTS queue path had an undefined `x.target_language` reference. It now uses the route's `language` argument.
7. Lesson audio transcription mapped Santali to `sat` before the model manager saw it, which prevented the Santali STT adapter from being selected. The canonical `sat_Olck` code is now passed through the manager.
8. Source-language changes silently added English as a required target. This was removed; all targets are explicit and optional.
9. Live audio was resampled more than once in the earlier path. The live session now performs a single controlled 16 kHz conversion.
10. API restart does not resurrect heavyweight queued/running work. Jobs are marked failed/manual so the user can retry exactly once.
11. Preparation jobs expire to FAILED after the configured safety timeout instead of staying RUNNING forever.

## 4. TTS reality on the target laptop

Verified Windows benchmark:

- GPU: NVIDIA GeForce RTX 2050 4 GB
- PyTorch: 2.8.0+cu128
- CUDA available: True
- Audio generated: 30.20 seconds
- Parler generation: 116.12 seconds
- Realtime factor: 3.85x
- Peak GPU memory: 3.46 GB

Conclusion: CUDA is correctly configured and the GPU is being used, but the current Parler model/runtime is still too slow for true real-time speech on this laptop. Product behavior therefore avoids making classroom publishing or lesson navigation depend on TTS completion.

## 5. Performance strategy

- Translation and Whisper stay on CPU to preserve the 4 GB GPU for TTS.
- Parler uses FP16 on CUDA when available.
- Description tokens are cached.
- Translation results are cached in memory.
- Long text is chunked before model token limits are reached.
- TTS is generated on demand and cached as WAV artifacts.
- Live TTS uses the Parler streamer path when available, so first-audio latency can be earlier than total generation time.
- `PARLER_COMPILE=1` is opt-in; it is not forced because the 4 GB GPU is already near its memory limit.

## 6. Release acceptance checks performed in the build environment

- Python compile: PASS
- Live pipeline protocol: PASS
- Santali live routing protocol: PASS
- FastAPI import: PASS
- `/api/v1/health`: PASS
- `/api/v1/live/languages`: PASS; exposes EN/HI/MR/Santali
- Static source checks for `sat_Olck`, source-language persistence, optional targets, and Publish source-only behavior: PASS

A full Vite production build was not independently completed in the sandbox because dependency installation (`npm install`) timed out. The frontend source was syntax-checked in an earlier pass; the Windows machine should run `npm install` and `npm run build` as the final local release check.

## 7. Final demo path

1. Create lesson with English source (or select another source language).
2. Add concepts.
3. Leave Hindi/Marathi/Santali unselected unless needed.
4. Publish immediately when the source is valid.
5. Add optional translations later.
6. Santali can be added as a temporary language without approval.
7. Generate practice only when needed.
8. Generate audio only when needed.
9. Student opens the published source lesson and switches only among languages that actually exist.
10. Live Translate stores the spoken/listener pair locally and supports Swap.

## 8. Final limitation / honest claim

Do not market the current Parler path as instant or real-time on the RTX 2050. The product is optimized around fast text/translation and non-blocking, cached audio. Live speech input/output remains a higher-latency experimental path on this hardware.
