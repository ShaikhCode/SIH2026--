# BhashaSaathi — Local Model Integration Handoff

## Evidence used

This final build integrates the verified findings from the **BhashaSaathi Local Model Debugging Handoff, 18 Sep 2026**.

The diagnostic report establishes:

- Python 3.13.5 Windows environment was used.
- `transformers==4.46.1`
- `huggingface_hub==0.36.0`
- `parler-tts==0.2.2`
- `IndicTransToolkit==1.1.1`
- faster-whisper is used for the installed CTranslate2 Whisper checkpoint.
- Real IndicTrans2 EN→Hindi and Hindi→EN inference passed.
- The Whisper checkpoint loads with faster-whisper/CTranslate2; it must not be renamed to a Transformers `pytorch_model.bin` file.
- The Parler-TTS checkpoint reaches the description-tokenizer stage but needs local FLAN-T5 tokenizer/config assets.

## Production integration performed

1. `apps/api` path resolution now points to `apps/api/models`, not `apps/api/app/models`.
2. IndicTrans2 uses `trust_remote_code=True` + `local_files_only=True` and the proven IndicProcessor preprocess → generate → decode → postprocess sequence.
3. Whisper uses faster-whisper/CTranslate2 for the installed checkpoint.
4. Parler-TTS uses the current generation contract and a configurable local FLAN-T5 description tokenizer.
5. A first-class `scripts/download_tts_support.py` provisions only FLAN-T5 tokenizer/config assets.
6. `scripts/model_lab.py` isolates translation, STT and TTS before product integration.
7. The API `/health/models` reports individual TTS support readiness instead of reporting the model folder alone as “ready”.
8. The lesson builder blocks publishing until the required Santhali audio artifact exists.
9. Model errors preserve the lesson and expose a useful local runtime detail to the educator UI.

## Important non-fixes

- Do not rename Whisper `model.bin`.
- Do not download the full FLAN-T5 model just to obtain its tokenizer.
- Do not loosen the pinned Parler/Transformers versions without rerunning isolated model tests.
- Do not label unreviewed Santhali as native-verified.

## Final machine-side proof

On the user's Windows machine, the authoritative proof is:

```powershell
python scripts\verify_models.py
python scripts\model_lab.py --skip-tts
python scripts\model_lab.py
```

Then run the full product path through FastAPI + React.
