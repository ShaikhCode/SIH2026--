# BhashaSaathi V20 — Demo-safe preparation fixes

- Publishing never waits for TTS or practice.
- Translation approval auto-starts practice only.
- Heavy Parler-TTS is now explicit/opt-in from Activities → Audio → Generate.
- Lesson GET no longer starts translation warm-up on every refresh/poll.
- Old queued/running TTS jobs are not resurrected on API restart.
- Publish cancels pending autosave and locks it after successful publish, preventing a published lesson from being immediately converted into a new draft by a stale autosave.
- The live voice-translation TTS path is unchanged; this patch specifically fixes lesson-builder/demo stability.
