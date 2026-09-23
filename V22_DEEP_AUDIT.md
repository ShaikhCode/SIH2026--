# BhashaSaathi V22 Deep Audit

## What was wrong in V20/V20.1

### 1. Languages step was globally locked
`translateAll()` used the shared `busy` state around `Promise.all`, so while either target language was generating, the approval controls were disabled. The teacher could see a completed translation but could not approve it until the other request finished. This matches the screenshot symptom: “Preparing target translations…” plus an approval action that appeared unavailable.

### 2. Activities navigation was intentionally blocked until every target translation was approved
The UI correctly enforces teacher approval before Activities, but the blocked-state message was generic. V22 explains exactly which language remains.

### 3. Preparation polling refreshed the entire lesson pack on every state change
That could overwrite unsaved editor state and caused unnecessary React churn. V22 only refreshes when a preparation reaches a terminal state (`READY`/`FAILED`).

### 4. Manual TTS retry could submit duplicate executor work
Repeated `/retry` requests were visible in the API log. V21/V22 add idempotent job submission and process-local deduplication.

### 5. Background TTS could remain RUNNING forever after a worker/process failure
V22 adds a watchdog: TTS jobs older than 15 minutes become `FAILED`; practice jobs older than 3 minutes become `FAILED`. The user always gets a terminal state and a Retry path.

### 6. TTS was allowed to occupy the only GPU
The RTX 2050 has 4 GB VRAM. V22 defaults Translation + Whisper to CPU and Parler-TTS to CUDA, which matches the measured hardware constraint.

### 7. Requirements did not reproduce the verified GPU environment
The old requirements used a loose `torch>=2.5,<3`. V22 pins Torch 2.8.0 / torchvision 0.23.0 / torchaudio 2.8.0 and provides an explicit CUDA 12.8 Windows requirements file.

### 8. Frontend requests had no timeout
A stalled API/model operation could leave a spinner forever. V22 adds client-side timeouts, with longer limits for translation/back-translation/practice/transcription.

### 9. The page had a white-screen failure mode
V22 keeps the React error boundary so render exceptions result in a recovery screen rather than an unrecoverable blank page.

## V22 behavior

```text
Source
  -> Concepts
  -> Generate Hindi + Marathi independently
  -> Approve whichever is ready
  -> Approve the remaining language
  -> Activities unlock
  -> Practice can run independently
  -> Audio is manual and idempotent
  -> Publish requires approved text only
```

## TTS benchmark on the actual target laptop

Measured separately on the user's RTX 2050 4 GB:
- 30.20 s generated audio
- 116.12 s generation
- 3.85x realtime factor
- 3.46 GB peak GPU memory

Therefore Parler-TTS is kept out of the critical publish path and out of automatic translation approval flow. It remains a manual derivative asset.

## Verification completed in the build environment

- Python API source compiles with `python -m compileall`.
- The existing local Parler GPU benchmark successfully loaded CUDA and generated WAV audio.
- The web dependency install could not be completed in the sandbox before timeout, so a full Vite production build was not independently executed here. The source was reviewed statically for the specific runtime path reported by the user.
