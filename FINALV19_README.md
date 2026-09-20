# BhashaSaathi FinalV19 — Speed + Full-Text Reliability

FinalV19 is focused on the exact failures observed in the local classroom builder:

1. Long English lessons were being silently truncated by a fixed 256-token tokenizer input and too-small output ceilings.
2. Audio/practice background jobs were making the lesson appear stuck and were also blocking publication.
3. Every lesson GET recomputed worksheet/flashcard data even when the teacher only needed translation state.
4. Background audio used a single shared queue where practice could sit in front of another TTS job.
5. Flashcards were removed from the product flow as requested.

## New flow

```text
Teacher source
   ↓
Concepts (optional metadata)
   ↓
English / Hindi / Marathi translation
   ↓
Teacher reviews + approves translated text
   ↓
PUBLISH IS UNLOCKED
   ├── TTS audio → background
   ├── Practice → background
   └── Worksheet → on demand
```

## Translation reliability

- IndicTrans2 remains resident locally.
- Lesson text is split into tokenizer-safe chunks before inference.
- The API never sends an oversized lesson with `truncation=True`.
- Chunks are batched (default 4) and merged in original order.
- Output generation uses an adaptive ceiling up to 512 tokens.
- If a result reaches the generation ceiling without EOS, only that result is retried with a larger ceiling.
- This avoids the screenshot failure where Hindi/Marathi ended halfway through a sentence.

## Publish rule

Only these are publication-critical:

- title
- source text
- every required target translation exists
- every required target translation is teacher-approved

Audio, practice and worksheet preparation do not block publication.
Validation flags remain visible to the teacher; explicit teacher approval is the human gate.

## TTS behavior

- Target audio is created after translated text approval.
- Hindi and Marathi TTS jobs run in a dedicated audio worker.
- Practice has a separate worker so practice generation cannot queue ahead of audio.
- TTS remains local and cached by text/language/speaker.
- Long lessons stay chunked inside Parler-TTS rather than becoming one giant generation.
- Published lessons can acquire their audio artifacts after publication because the same lesson version remains authoritative.

## UI changes

- Removed flashcards completely.
- Removed learning-outcome generation/blocking from the builder flow.
- Added progressive background status for audio/practice.
- `Generate targets` launches the target translation requests together; the backend serializes CPU model inference safely while the UI updates each completed result.
- `Meaning Check` remains available on demand for teachers who do not know the target language; it does not block translation generation.

## What is not claimed

This release does not promise cloud-service latency from a CPU-only laptop. It removes avoidable application/API waiting and fixes silent long-text truncation. Actual inference time remains hardware/model dependent.
