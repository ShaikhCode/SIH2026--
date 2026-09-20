# BhashaSaathi FinalV15 — Speed & Temporary Audio Audit

## Scope
This release implements the first requested change set only: faster translation/audio paths and an explicit audio replay control in live temporary history.

## Root causes addressed
1. **Translation route eviction** — the previous adapter kept only two model routes. The product supports three validated demo routes: English→Indic, Indic→English, and Indic→Indic. Switching across all three could evict a route and force a full model reload on the next request. The cache is now configurable and defaults to 3.
2. **TTS over-fragmentation** — normal lesson text was split into fixed 18-word chunks, causing more Parler generation calls than necessary. It is now split on sentence boundaries and only further chunked around 240 characters.
3. **Repeated TTS prompt work** — the same per-language voice description is now tokenized once per adapter lifetime/device and reused.
4. **Audio warm-up timing** — the Lesson Builder warms the resident TTS model in the background as soon as translation work completes and also on lesson-builder entry.

## What was intentionally NOT removed
- Translation Guard / validation remains required for classroom content.
- Teacher approval remains required before student-facing TTS/publish.
- Local model inference remains the source of truth; no fake/demo result is introduced.

## Live history
- Temporary session retention remains 24 hours by default.
- Saved sessions remain until the user deletes them.
- Completed live turns retain their generated audio Blob locally in IndexedDB.
- The history UI now explicitly provides **Hear audio** for turns with captured audio.

## Verification performed in this build environment
- Python files compile with `python -m compileall`.
- TypeScript/TSX source was syntax-scanned for the modified files.
- No model weights are bundled; local model folders are still required on the user's machine.

## Performance claim boundary
This release is designed to reduce avoidable latency. Exact milliseconds still depend on the user's CPU/GPU, model load state, text length, and browser audio path. This audit does not claim a fixed latency number without running the user's local model stack.
