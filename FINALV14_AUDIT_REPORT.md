# BhashaSaathi FinalV14 — Deep Audit Report

## Audit scope

This release was reviewed across:

- React/Vite UI and routing
- Live Translate browser audio transport
- FastAPI routing and lifecycle
- model loading and caching
- STT, translation and TTS adapters
- classroom translation/practice/TTS paths
- authentication and classroom membership boundaries
- local history and offline storage
- publish gating
- static Python syntax and targeted protocol tests

The current code base is the senior-audited build plus a performance/live refactor. The uploaded desktop live translator was treated as the source of the proven low-latency pipeline ideas: short VAD segments, bounded worker queues, faster Whisper settings, low-beam interactive translation, and ParlerTTSStreamer-based streaming.

## Highest-impact defects found and addressed

### A. Model unloading was destroying web performance

The previous `ModelManager` explicitly unloaded the other heavy models around individual translation, STT and TTS requests. That made web actions repeatedly pay model construction time.

FinalV14 changes the runtime to keep heavy models resident by default and uses explicit manual `unload_heavy()` only for deliberate maintenance.

### B. Translation route retention was unbounded

FinalV14 keeps a small two-route LRU for IndicTrans2 models. This is a deliberate memory/performance compromise: the most recently used translation routes stay warm while old routes can be released.

### C. Browser live audio was being downsampled twice

The browser already converted microphone audio to 16 kHz PCM but sent the native AudioContext rate in the WebSocket query. The server therefore attempted to resample already-downsampled audio again.

FinalV14 sends `sample_rate=16000` after the single browser-side conversion.

### D. Live queues could become a stale FIFO backlog

FinalV14 uses bounded stage queues of size 2 and replaces the oldest pending item when a stage falls behind. This is appropriate for live interaction because old speech is less useful than the latest speech once latency starts to accumulate.

### E. Live TTS only became audible after full waveform generation

FinalV14 adds a WebSocket PCM path based on ParlerTTSStreamer when it is available. The browser schedules streamed PCM chunks in Web Audio while the backend is still generating later chunks. The complete result is also reconstructed to a WAV blob for local history/cache purposes.

### F. Classroom first-use waiting felt like a stuck button

FinalV14 adds authenticated runtime prewarm endpoints. The lesson builder prewarms the selected translation route, and the Activities step prewarms TTS. The builder also stops eagerly downloading every previous audio artifact on every refresh.

### G. Practice generator argument collision

The existing runtime bug caused `ensure_practice()` to receive `source_language` twice. The route now passes the arguments explicitly by keyword.

## Live architecture after FinalV14

```text
Browser microphone
      ↓
16 kHz PCM
      ↓
WebSocket
      ↓
Energy VAD + short segmentation
      ↓
Bounded segment queue (latest work wins)
      ↓
Faster-Whisper Small
      ↓
Bounded translation queue
      ↓
IndicTrans2 (2-beam live path)
      ↓
Bounded TTS queue
      ↓
ParlerTTSStreamer
      ↓
PCM WebSocket chunks
      ↓
Browser Web Audio scheduler
      ↓
Buds / headphones
```

The stages overlap. STT does not wait for TTS playback to finish, translation does not wait for the browser to finish playing previous audio, and the microphone capture loop never blocks on audio playback.

## Classroom architecture after FinalV14

```text
Lesson source
   ↓
editable transcript
   ↓
concepts + learning outcome
   ↓
IndicTrans2
   ↓
Translation Guard
   ↓
teacher edit + approval
   ↓
practice / worksheet / flashcards
   ↓
prewarmed Parler-TTS + disk cache
   ↓
review readiness
   ↓
publish
```

The teacher-facing workflow remains approval-gated. Performance work does not remove the review boundary.

## Language scope

FinalV14 intentionally supports only:

- English — `eng_Latn`
- Hindi — `hin_Deva`
- Marathi — `mar_Deva`

No unvalidated language selector is exposed in the current prototype.

## Device policy

For the demo:

```text
Input  = laptop built-in microphone
Output = Buds / headphones
```

The browser requests echo cancellation, noise suppression and automatic gain control. The Buds microphone is not required and is not the selected input path.

## History policy

Live Translate history is browser/device-local using IndexedDB.

- Default: temporary.
- Temporary retention: 24 hours.
- Saved sessions: retained until the user deletes them.
- Microphone input: not persisted by the live backend.
- Generated translated audio: can be retained inside the local history entry because it is user-visible output.

## Validation performed in this build workspace

### Python

- `python -m compileall -q apps/api/app core/layer2 scripts` — PASS
- FastAPI `GET /api/v1/health` — PASS
- FastAPI `GET /api/v1/live/languages` — PASS
- FastAPI `GET /api/v1/health/models` — PASS (expected no local model weights in sandbox)
- Python AST audit — covered by `scripts/audit_finalv14.py`
- Targeted fake-model live pipeline protocol test — `scripts/test_live_pipeline.py`

### Browser source

A full registry-backed `npm install` did not complete in the isolated build environment, so `npm run build` could not be truthfully claimed here. A global TypeScript parser was available, but project dependency type definitions were not installed.

The final ZIP therefore includes the source and a clear Windows verification step rather than claiming a browser build that was not executed.

## Required Windows verification before the SIH demo

```powershell
python scripts\verify_models.py
python scripts\model_lab.py
npm install
npm run build
```

Then manually verify:

1. `/live` opens without login.
2. Laptop mic is selected.
3. Buds/headphones are selected as output.
4. Hindi → Marathi works.
5. English → Hindi works.
6. Marathi → English works.
7. Live transcript and translation update with measured timings.
8. TTS starts streaming when the local `ParlerTTSStreamer` implementation is available.
9. A live session appears as temporary history.
10. Save and Delete work.
11. Classroom translation shows warm-up only on first route use.
12. Classroom audio uses the cached artifact after first generation.

## Honesty boundary

FinalV14 improves latency and removes known architecture-level causes of unnecessary waiting, but exact end-to-end latency depends on the user's Windows CPU/GPU, RAM, audio device, browser and the local model runtime. No hard numerical latency promise is made without measuring the real machine.
