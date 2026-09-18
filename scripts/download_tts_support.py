from pathlib import Path
import os
root=Path(__file__).resolve().parents[1]/'apps/api/models/tts/description-tokenizer'
root.mkdir(parents=True,exist_ok=True)
try:
    from transformers import AutoTokenizer
    print('Downloading only tokenizer/config files for google/flan-t5-large into:',root)
    tok=AutoTokenizer.from_pretrained('google/flan-t5-large',token=os.getenv('HF_TOKEN') or None)
    tok.save_pretrained(root)
    print('Done. No Flan-T5 model weights were downloaded by this script.')
except Exception as exc:
    print('Unable to download support tokenizer:',exc)
    print('Accept Hugging Face access if prompted and rerun this script.')
    raise SystemExit(1)
