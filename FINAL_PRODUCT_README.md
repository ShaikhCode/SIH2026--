# BhashaSaathi V25 — Product Ready

BhashaSaathi is a local-first classroom platform for mother-tongue education with a separate Live Translate tool.

## Product contract

- English is the main/default lesson language.
- Hindi and Marathi are optional.
- Santali (`sat_Olck`) is optional and temporary; it does not require the normal teacher approval gate.
- Lesson source/spoken language is persisted and may be English, Hindi, Marathi, or Santali.
- Publish is source-first and never waits for optional language generation, practice, worksheet, or audio.
- Audio is manual/on-demand and cached because local Parler-TTS is computationally expensive on a 4 GB laptop GPU.
- Live Translate stores the spoken/listener language pair locally and supports Swap.

## Models

- IndicTrans2: local multilingual translation.
- faster-whisper: English/Hindi/Marathi STT.
- IndicConformer: optional Santali STT.
- Indic Parler-TTS: multilingual classroom audio, including Santali.

## Demo language choices

For the safest viva flow, use English source only and publish immediately. Add Hindi/Marathi/Santali only when you want to demonstrate those capabilities.

## Windows RTX 2050 setup

Read `WINDOWS_FINAL_SETUP.md`.

## Audit

Read `FINAL_V25_PRODUCT_AUDIT.md` for the final acceptance checklist, bug fixes, runtime measurements, and remaining limitations.
