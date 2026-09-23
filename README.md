# BhashaSaathi V22 · Viva-Stable

# BhashaSaathi FinalV19

## What this build solves

FinalV19 is the speed/reliability release for the local teacher workflow.

The key rule is:

> **Teacher approves translated text. Audio and practice continue in the background.**

This prevents a slow TTS job from blocking publication.

## Supported languages

The classroom and live demo are intentionally limited to:

- English
- Hindi
- Marathi

## Main classroom flow

```text
1. Source
      ↓
2. Concepts (lightweight, optional metadata)
      ↓
3. Languages
      ↓
   IndicTrans2
      ↓
   Teacher reviews/edits target text
      ↓
   Approve Hindi / Marathi
      ↓
4. Background preparation
      ├── Parler-TTS audio
      ├── Practice drafts
      └── Worksheet on demand
      ↓
5. Review & Publish
```

### Publication gate

Publishing requires only:

- lesson title
- source text
- every required target translation exists
- every required target translation is teacher-approved

Audio and practice are **not** publish blockers. They keep working against the same lesson version after publication.

## Long-text translation reliability

Earlier builds used a fixed tokenizer input ceiling and could silently truncate a long lesson. FinalV19 changes this:

```text
Long lesson
   ↓
sentence grouping
   ↓
token-safe chunks (never silently truncated)
   ↓
batch of up to 4 chunks
   ↓
IndicTrans2 greedy inference
   ↓
reassemble chunks in order
```

The decoder uses a dynamic output ceiling up to 512 tokens. If a chunk reaches its ceiling without EOS, that chunk is retried with a larger ceiling instead of returning a cut sentence.

## Why classroom translation should now behave more like the live translator

The live translator has always had a short, resident-model path. FinalV19 brings the classroom path closer to that architecture by:

- keeping translation models resident;
- using greedy decoding (`num_beams=1`) for the interactive path;
- avoiding SQLite write transactions during transformer inference;
- batching safe long-text chunks;
- caching exact repeated translations;
- showing individual target results as they complete;
- eliminating unnecessary full lesson re-fetch work after translation.

Actual local inference speed is still determined by the laptop CPU/GPU and the size of the text. No honest local build can guarantee a fixed cloud-service latency for every lecture.

## TTS behavior

After a target translation is approved:

```text
Approved text
    ↓
TTS job QUEUED
    ↓
TTS job RUNNING
    ↓
WAV artifact READY
```

Hindi and Marathi TTS jobs use a dedicated background worker. Practice has its own worker, so practice cannot sit in front of the next audio job.

Long TTS text is token-safe chunked before Parler generation so the prompt is not silently truncated.

The generated audio is cached by exact text + language + speaker. Replaying an existing artifact does not regenerate the model output.

## Teacher review when the teacher does not know the target language

The teacher sees source and translated text side by side.

`Meaning Check` is an **on-demand** reverse translation into the teacher's source language. It is intentionally not part of the hot translation path, because another transformer inference would only add waiting to every translation click.

Automated Translation Guard warnings remain visible. Explicit teacher approval remains the publication decision.

## Flashcards

Flashcards were removed from the active product flow in FinalV19. They are no longer generated, displayed, or required.

## Live Translate

The live demo is still separate from classroom publishing:

```text
Laptop microphone
      ↓
VAD / Whisper
      ↓
IndicTrans2
      ↓
ParlerTTS streaming
      ↓
Buds / headphones
```

Recommended demo devices:

- Input: laptop built-in microphone
- Output: Buds/headphones
- Do not use the Buds microphone for the demo unless specifically testing a headset profile.

Live temporary history can replay the same generated audio instead of regenerating it.

## Run on Windows

### Backend

```powershell
D:
cd \git\BhashaSaathi_FinalV19\apps\api
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
D:
cd \git\BhashaSaathi_FinalV19\apps\web
npm install
npm run build
npm run dev
```

Open:

`http://localhost:5173`

### Verify the local models

```powershell
cd D:\git\BhashaSaathi_FinalV19
python scripts\verify_models.py
python scripts\model_lab.py
```

### Translation performance probe

```powershell
python scripts\perf_probe.py --source hin_Deva --target eng_Latn --text "हमारी कक्षा में पौधों के बारे में सीखते हैं।" --repeat 3
```

## Important runtime rule

Keep the working local model directories and the already-compatible Python environment. Do not blindly reinstall the requirements on Python 3.13; the previous environment had old dependency resolution issues involving Cython.

Expected local folders:

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

## Verification in this build environment

- Python compileall: PASS
- FastAPI application import: PASS
- 23 TS/TSX files syntax parsed: PASS
- long-text token-safe translation chunk test: PASS
- TTS token-safe prompt chunk test: PASS
- FinalV19 static audit: 10/10 PASS
- active API/web flashcard reference scan: PASS

The final browser/Vite production build was not completed inside the build sandbox because npm dependency installation exceeded the available build window. Real local model inference and Windows audio playback must be verified on the demo laptop.


## Windows RTX 2050 setup

Use the verified CUDA wheel set before starting the API:

```powershell
cd apps\api
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-windows-cuda128.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
```

The lesson path keeps translation/Whisper on CPU and reserves the 4 GB RTX 2050 for TTS.
