# BhashaSaathi FinalV16

## This release fixes the main issues discussed in the latest review

### Classroom Builder
- Translation remains validated and teacher-approved.
- Interactive translation uses the faster beam profile.
- Generate-target requests can be run together rather than waiting for one language to finish before starting the next.
- Once a translation is `TEACHER_APPROVED`, target audio is automatically queued in the background.
- The builder does not lock into a global `Creating … audio` loading state.
- Audio status is shown independently per language: `Queued`, `Generating`, `Ready`, or `Retry audio`.
- Audio does not require a second approval. The teacher reviews/approves the text; the generated audio is treated as a representation of that approved text.
- A real audio preview/replay control is available once the artifact is ready.
- If an approved translation is edited or regenerated, stale audio is invalidated and re-generated from the new approved text.
- Publish still requires the required audio artifacts to exist, so an incomplete package cannot silently ship.

### Live Translate
- Only English, Hindi and Marathi are exposed.
- Laptop microphone + Buds/headphones remains the recommended demo arrangement.
- Fixed the browser PCM playback path so the media element is explicitly started after the `MediaStreamAudioDestinationNode` is attached.
- Live UI shows when audio generation starts and when audio has actually been generated.
- The same generated audio is stored on the temporary turn and can be replayed with `Hear audio`; replay does not regenerate TTS.
- Temporary sessions expire after 24 hours unless saved. Saved sessions remain until deleted.

## Important
The local model stack is intentionally not bundled. Keep the existing `apps/api/models` tree and working Python environment.
