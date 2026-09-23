# BhashaSaathi V21 Deep Audit

## Critical bugs fixed

- Batch translation no longer locks the whole Languages step. A completed Hindi result can be approved while Marathi is still generating.
- Activities unlock only after all required target languages are teacher-approved.
- Preparation polling no longer refreshes the entire lesson pack on every QUEUED/RUNNING transition, protecting unsaved edits.
- Fixed the FAILED -> QUEUED hidden mutation that caused manual TTS retry to return QUEUED without submitting the worker.
- Added process-local job submission deduplication so repeated retry clicks cannot create duplicate executor work.
- Manual Generate/Retry now kicks the preparation poller immediately.
- TTS API endpoints return the real job state (READY/RUNNING/QUEUED/FAILED).
- Translation and Whisper default to CPU; Parler-TTS gets the RTX 2050 GPU to avoid 4 GB VRAM contention.
- Added a React error boundary so render exceptions no longer produce an unrecoverable white screen.
- Fixed missing `Layers` Lucide import used by the Review page.
- Added explicit eager attention default to avoid an SDPA/T5 startup failure on the pinned Transformers stack; it remains configurable.
- Added a Windows GPU requirements file and offline WAV pre-generation CLI for viva preparation.

## TTS reality

Measured on RTX 2050: 30.2 seconds of Parler audio took 116.12 seconds (~3.85x real-time) and peaked at 3.46 GB VRAM. The GPU is therefore working, but this laptop/model combination is still not real-time. The product keeps TTS manual and non-blocking.

## Intended demo flow

Source -> Concepts -> Translate independently -> Approve each language -> Activities -> Publish.

Publish requires approved text only. Audio is never required for publication.
