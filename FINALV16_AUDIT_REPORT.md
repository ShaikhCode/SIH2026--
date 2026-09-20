# FinalV16 Audit Report

## Audited areas
- Lesson translation request path and beam profile
- Translation Guard preservation
- Audio generation trigger and UI blocking behavior
- Per-language audio readiness state
- Audio artifact preview/replay
- Live WebSocket PCM playback path
- Temporary live-history audio persistence and replay
- Language registry

## Key findings and fixes
1. Lesson TTS was invoked through a global `busy` action; the UI therefore showed a long `Creating … audio` banner and prevented other work. FinalV16 moves TTS into a dedicated background queue in the Lesson Builder.
2. Each target language now gets its own background state, so users can continue editing/reviewing while audio is generated.
3. Teacher approval remains text-focused. Audio is generated from that approved text and is previewable, but it is not a second approval gate.
4. Live PCM playback used a `MediaStreamAudioDestinationNode` connected to a hidden HTML audio element but did not explicitly call `audio.play()` after assigning the stream. FinalV16 explicitly starts playback after resuming the audio context.
5. Live temporary history already had a real `Blob` storage path; FinalV16 exposes the audio-ready state and keeps the replay button tied to that exact stored blob.
6. Translation regeneration and teacher edits now invalidate the target-language audio artifact whenever the text actually changes, preventing stale speech from passing the final publish checklist.

## Non-claims
- No exact millisecond latency guarantee is made because the full model stack depends on the user's Windows CPU/GPU and browser audio device.
- No bundled model weights are included in the release ZIP.
