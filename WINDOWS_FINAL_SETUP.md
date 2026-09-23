# BhashaSaathi V25 — Windows Final Setup

## 1. API environment

```powershell
cd apps\api
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-windows-cuda128.txt
```

Verify CUDA:

```powershell
python -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
```

Expected on the target laptop:

```text
Torch: 2.8.0+cu128
CUDA: True
GPU: NVIDIA GeForce RTX 2050
```

If Parler reports a missing audio codec package:

```powershell
pip install descript-audio-codec
```

## 2. Start API

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For TTS benchmarking, avoid `--reload` so the reloader cannot create a second process.

## 3. Web

```powershell
cd ..\web
npm install
npm run dev
```

For a production build check:

```powershell
npm run build
```

## 4. Optional Santali STT

Santali speech input requires the optional IndicConformer checkpoint. Accept the model terms on Hugging Face and set `HF_TOKEN` if the checkpoint requires it, then run:

```powershell
cd ..\..\
python scripts\download_santali_stt.py
```

Afterward restart the API.

## 5. Existing data

Before replacing a running installation, back up:

```text
apps\api\data\bhashasaathi.db
apps\api\data\storage\
```

The application database stores lesson/source/translation/job metadata. Audio artifacts are stored under the local storage directory and can be reused without regenerating TTS.

## 6. Demo rule

Do not wait for Parler-TTS during Publish. Publish is source-first. Generate lesson audio manually/on demand or pre-generate the small demo lesson before the viva.
