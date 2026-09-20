# BhashaSaathi FinalV18 — Speed-Focused Local Build

This is the next incremental product release after FinalV16.

## Main focus

1. Faster classroom text translation path.
2. Removal of unnecessary API/DB round trips.
3. Resident IndicTrans2 with bounded CPU execution.
4. Translation result timing diagnostics.
5. Background audio without full lesson refreshes.
6. Faster first-audio streaming profile for Live Translate.
7. Replayable temporary live-history audio remains intact.

## Supported live languages

- English (`eng_Latn`)
- Hindi (`hin_Deva`)
- Marathi (`mar_Deva`)

## Local model folders

Keep your existing local model weights outside this ZIP:

```text
apps/api/models/
  translation/
    en-indic/
    indic-en/
    indic-indic/
  stt/
    whisper-small/
  tts/
    indic-parler-tts/
    flan-t5-large/
```

## Do not reinstall the Python environment blindly

The known working environment from the user's machine should be preserved. In particular:

```text
transformers==4.46.1
huggingface_hub==0.36.0
parler-tts==0.2.2
IndicTransToolkit==1.1.1
faster-whisper==1.2.1
```

## Windows run

Backend:

```powershell
D:
cd \git\BhashaSaathi_FinalV18\apps\api
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
D:
cd \git\BhashaSaathi_FinalV18\apps\web
npm install
npm run build
npm run dev
```

Open `http://localhost:5173`.

## Speed benchmark

With the local models installed:

```powershell
D:
cd \git\BhashaSaathi_FinalV18
python scripts\perf_probe.py --source hin_Deva --target eng_Latn --text "हमारी कक्षा में पौधों के बारे में सीखते हैं।" --repeat 3
```

For a TTS timing check:

```powershell
python scripts\perf_probe.py --source hin_Deva --target eng_Latn --text "हमारी कक्षा में पौधों के बारे में सीखते हैं।" --repeat 3 --tts
```

## Performance knobs

Place these in `apps/api/.env` when tuning the laptop:

```text
TORCH_THREADS=6
TEXT_TRANSLATION_BEAMS=1
LIVE_TRANSLATION_BEAMS=1
TRANSLATION_MAX_NEW_TOKENS=128
LIVE_TRANSLATION_MAX_NEW_TOKENS=96
TRANSLATION_ROUTE_CACHE_LIMIT=2
LIVE_TTS_STREAM_SECONDS=0.5
```

Benchmark one change at a time on the actual machine.
