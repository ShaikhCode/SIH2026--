# BhashaSaathi FinalV18 — Speed Audit

## Objective

Remove avoidable waiting from the local web product while preserving the teacher approval workflow and the real local IndicTrans2 / Whisper / Parler-TTS models.

This release does **not** promise a literal 100x model-inference speedup. Model inference time is hardware-bound. The focus is eliminating unnecessary API round trips, model contention, redundant generation, and frontend blocking.

## Why the older web flow felt slow

### Translation request path before V17

`Save draft -> PATCH lesson -> FastAPI -> DB/pack rebuild -> POST translate -> IndicTrans2 -> Translation Guard -> DB commit -> GET full lesson pack -> worksheet/flashcard recomputation -> UI`

The core model call was only one part of the perceived wait.

### V17 translation path

`POST /lessons/{id}/translate with current editor text -> single source flush -> cached-row check -> resident IndicTrans2 -> lightweight Guard -> DB commit -> small timing/result payload -> UI`

No second save request and no full lesson GET are required for an ordinary translation click.

## Optimizations

### 1. Fast interactive decoding
- Interactive/classroom translation uses greedy decoding (`num_beams=1`).
- Output generation is bounded with `max_new_tokens` (default 128).
- Live translation uses a tighter 96-token bound.
- `use_cache=True`, `do_sample=False`, `torch.inference_mode()` remain enabled.

### 2. CPU thread control
- CPU inference defaults to a conservative thread count derived from available CPU cores.
- `torch.set_num_interop_threads(1)` reduces nested parallelism/oversubscription.
- Override with `TORCH_THREADS` when benchmarking the actual laptop.

### 3. Translation model memory discipline
- At most two translation route bundles stay resident by default.
- This reduces RAM pressure on the 12-GB-class laptop profile without forcing every possible route to stay loaded.

### 4. Translation serialization on CPU
- Heavy IndicTrans2 generation is protected by a shared inference lock.
- This avoids two Transformer graphs fighting over the same CPU cores during `Generate targets`.
- `Generate targets` therefore runs target translations sequentially rather than launching competing CPU generations at once.

### 5. Database-level translation cache
- If a translation already exists for the exact active lesson version, the API returns it without model inference unless `force=true` is supplied.
- This makes repeated language clicks effectively immediate.

### 6. Same-request source data
- The browser sends the current `source_text`, `clean_transcript`, and `source_language` with the translation request.
- This removes the old `saveDraft -> translate` round trip.

### 7. No full-pack refresh after translation
- The translation endpoint returns the translated row and measured timings.
- The web page updates the local lesson state directly.
- It does not immediately run the expensive whole lesson pack GET again.

### 8. Audio remains backgrounded
- Audio starts after teacher translation approval.
- The browser processes the audio queue asynchronously.
- The audio queue no longer fetches the generated WAV and refetches the entire lesson pack after every TTS job.
- The server returns artifact metadata; the actual audio bytes are fetched lazily when the educator presses **Hear**.
- There is no separate audio approval step.

### 9. Live TTS first-chunk latency
- Live Parler streaming window is 0.5 seconds by default instead of 1.0 seconds.
- Generated PCM is scheduled in the browser as chunks arrive.
- Temporary history persistence no longer blocks the WebSocket message handler after every turn.

## What is intentionally preserved

- Translation Guard remains enabled for classroom translation.
- Teacher approval remains required before learner-facing translated text is published.
- Audio is generated from the approved translated text.
- Temporary live history retains replayable audio when a live TTS turn completed.
- English, Hindi and Marathi remain the initial live language set.

## Measured timing visibility

V17's translation response now includes:
- `translation_ms` — time spent inside the IndicTrans2 call.
- `total_ms` — total server-side translation request time.

TTS response now includes:
- `tts_ms` — server-side TTS generation/cache time.
- `cached` — whether the audio came from the TTS cache.

Use `scripts/perf_probe.py` on the actual laptop to measure warm translation and TTS times.

## Important limitation

No release can honestly guarantee a fixed multiple such as 100x on arbitrary CPU hardware. The actual model timing depends on the laptop CPU/GPU, RAM pressure, Windows audio stack, and model execution backend.

Final acceptance should be based on the measured `translation_ms`, `total_ms`, and TTS timing on the user's real Windows machine.
