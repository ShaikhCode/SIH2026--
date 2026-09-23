# BhashaSaathi V23 — Product-Ready Audit

## Product rule
English is the main/default lesson language. Hindi and Marathi are optional target languages. The teacher can publish the original lesson without generating or approving either optional target.

## Language persistence
- `Lesson.source_language` is the authoritative stored source/spoken lesson language.
- Live sessions persist both `source` (You speak) and `target` (Listener hears) in device history.
- Live Translate remembers the last language pair locally and supports Swap for the reverse direction.
- Student language choices are limited to the original source plus actually teacher-approved translations.

## Performance rule
- Translation is interactive and independent per target language.
- Practice is manual/on-demand; approval no longer starts practice generation automatically.
- TTS is manual/on-demand and never blocks Publish.
- Heavy Parler-TTS is not part of the critical path.

## Publish rule
Publish requires a title and original lesson source. Optional translations, practice, audio, and worksheet are derivative assets and do not block publication.

## TTS hardware finding
Verified on RTX 2050 4 GB: 30.20 s audio required 116.12 s generation and used 3.46 GB peak VRAM. Dynamic Parler generation therefore remains explicitly opt-in.

## Reliability changes carried forward
- Per-language translation states.
- Optional targets never lock the wizard.
- Idempotent TTS job submission.
- Manual practice/audio generation.
- No automatic background preparation after approval.
- Publish does not wait for preparation jobs.
- Preparation jobs use terminal READY/FAILED states.
- Source text and source language remain authoritative.

## Validation
- Python source: `python -m compileall` passed in the build workspace.
- Web `npm install` / Vite production build could not be completed inside the sandbox before the command timeout; the final Windows environment should run `npm install` and `npm run build` once before the demo.
