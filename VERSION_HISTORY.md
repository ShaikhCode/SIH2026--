# BhashaSaathi Build History — FinalV14

The working directory contained 13 prior BhashaSaathi ZIP builds. This release is therefore **FinalV14**.

| Build | What it represented |
|---|---|
| 01 | MVP foundation |
| 02 | Local no-Docker model layout |
| 03 | Web rebuild |
| 04 | Full local classroom build |
| 05 | Translation corrections |
| 06 | Full audited local build |
| 07 | Model/result diagnostic build |
| 08 | Final web product |
| 09 | Updated web product |
| 10 | Tested web product |
| 11 | Flexible account model |
| 12 | Practice runtime fix |
| 13 | Senior-audited web product — **base for this release** |
| **14** | **FinalV14 — performance refactor + Live Translate + streaming TTS + temporary history** |

## What FinalV14 changes

### Performance

- IndicTrans2 route models stay resident instead of being unloaded around unrelated requests.
- A bounded translation LRU keeps the active routes warm without indefinitely retaining every route.
- Text translation has an in-memory result cache and batch path for practice generation.
- Parler-TTS stays resident and has a bounded in-memory audio cache.
- The Lesson Builder prewarms the selected translation route.
- The Activities step prewarms the TTS model.
- Existing audio artifacts are no longer downloaded automatically on every builder refresh.
- The live pipeline uses bounded stage queues and latest-work replacement to avoid stale backlog.
- Browser audio is downsampled once to 16 kHz; the backend no longer resamples those already-16-kHz live packets.
- Live Parler-TTS uses the same streaming approach as the uploaded working desktop translator when `ParlerTTSStreamer` is available.

### Live Translate

- First-class `/live` page.
- English / Hindi / Marathi only.
- Laptop microphone recommended as input.
- Buds/headphones recommended as output.
- No account required.
- WebSocket duplex pipeline: VAD → Whisper → IndicTrans2 → streaming Parler-TTS.
- Real stage timings and time-to-first-audio reporting.
- Temporary device-only history expires after 24 hours.
- User can save or delete history manually.
- Microphone audio is not written to persistent server storage.

### Reliability

- Fixed the historical practice-generation argument collision by using keyword arguments.
- Added runtime warm-up endpoints.
- Added stronger model health checks for sharded `.safetensors` checkpoints.
- Added a graceful final-phrase flush when Live Translate stops.
- Added cleanup on unexpected WebSocket close.
- Added static audit and live protocol test scripts.

## Verification notes

The build workspace can syntax-check the Python code and exercise the FastAPI public health/live-language contract. The sandbox does not contain the user's Windows model weights and did not complete a registry-backed `npm install`, so the final browser build and real local model inference must still be run in the user's Windows project environment.
