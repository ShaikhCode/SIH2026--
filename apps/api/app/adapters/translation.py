from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

import torch


class IndicTrans2Adapter:
    """Local IndicTrans2 adapter using the known-working HF + IndicProcessor flow.

    The adapter deliberately stays independent of FastAPI/SQL/UI. It accepts local
    model directories and never needs runtime internet access.
    """

    def __init__(self, model_root: Path, cpu_only: bool = False, max_chars: int = 12000) -> None:
        self.model_root = Path(model_root)
        self.cpu_only = cpu_only
        self.max_chars = max_chars
        self._bundles: dict[str, tuple[Any, Any, Any, torch.device]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(src: str, tgt: str) -> str:
        if src.startswith('eng') and not tgt.startswith('eng'):
            return 'en-indic'
        if not src.startswith('eng') and tgt.startswith('eng'):
            return 'indic-en'
        return 'indic-indic'

    def _path(self, key: str) -> Path:
        return self.model_root / 'translation' / key

    @staticmethod
    def _resolve_model_dir(path: Path) -> Path:
        if (path / 'config.json').is_file():
            return path
        if not path.is_dir():
            return path
        configs = [p for p in path.iterdir() if p.is_dir() and (p / 'config.json').is_file()]
        return configs[0] if len(configs) == 1 else path

    def health(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for key in ('indic-indic', 'en-indic', 'indic-en'):
            path = self._resolve_model_dir(self._path(key))
            has_config = (path / 'config.json').is_file()
            has_weights = any(
                (path / name).is_file()
                for name in ('model.safetensors', 'pytorch_model.bin', 'model.bin')
            )
            has_tokenizer = any(
                (path / name).is_file()
                for name in ('tokenizer.json', 'tokenizer.model', 'sentencepiece.bpe.model')
            )
            result[key] = path.is_dir() and has_config and has_weights and has_tokenizer
        return result

    def _load(self, key: str):
        with self._lock:
            if key in self._bundles:
                return self._bundles[key]

            path = self._resolve_model_dir(self._path(key))
            if not path.is_dir() or not (path / 'config.json').is_file():
                raise FileNotFoundError(f'IndicTrans2 model folder is incomplete: {path}')

            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            try:
                from IndicTransToolkit.processor import IndicProcessor
            except Exception:
                try:
                    from IndicTransToolkit import IndicProcessor
                except Exception as exc:  # pragma: no cover - environment specific
                    raise RuntimeError(
                        'IndicProcessor could not be imported. Install IndicTransToolkit==1.1.1 '
                        'inside the BhashaSaathi virtual environment.'
                    ) from exc

            device = torch.device(
                'cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda'
            )
            tokenizer = AutoTokenizer.from_pretrained(
                str(path),
                trust_remote_code=True,
                local_files_only=True,
            )
            kwargs: dict[str, Any] = {
                'trust_remote_code': True,
                'local_files_only': True,
            }
            if device.type == 'cuda':
                kwargs['torch_dtype'] = torch.float16

            model = AutoModelForSeq2SeqLM.from_pretrained(str(path), **kwargs)
            model.to(device).eval()
            processor = IndicProcessor(inference=True)
            self._bundles[key] = (tokenizer, model, processor, device)
            return self._bundles[key]

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        normalized = re.sub(r'\s+', ' ', text.strip())
        if not normalized:
            return []
        if len(normalized) <= max_chars:
            return [normalized]

        sentences = re.split(r'(?<=[.!?।॥])\s+', normalized)
        chunks: list[str] = []
        current = ''
        for sentence in sentences:
            if not sentence:
                continue
            candidate = sentence if not current else f'{current} {sentence}'
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # Hard split an unusually long sentence so we never silently truncate.
                while len(sentence) > max_chars:
                    cut = sentence.rfind(' ', 0, max_chars)
                    if cut < max_chars // 2:
                        cut = max_chars
                    chunks.append(sentence[:cut].strip())
                    sentence = sentence[cut:].strip()
                current = sentence
        if current:
            chunks.append(current)
        return chunks

    def _translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        tokenizer, model, processor, device = self._load(self._key(src, tgt))
        batch = processor.preprocess_batch(
            texts,
            src_lang=src,
            tgt_lang=tgt,
            visualize=False,
        )
        encoded = tokenizer(
            batch,
            padding='longest',
            truncation=True,
            max_length=256,
            return_tensors='pt',
            return_attention_mask=True,
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            outputs = model.generate(
                **encoded,
                use_cache=True,
                num_beams=5,
                num_return_sequences=1,
                max_length=256,
            )
        decoded = tokenizer.batch_decode(
            outputs.detach().cpu().tolist(),
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )
        translations = processor.postprocess_batch(decoded, lang=tgt)
        if len(translations) != len(texts):
            raise RuntimeError(
                f'IndicTrans2 returned {len(translations)} outputs for {len(texts)} inputs.'
            )
        return [item.strip() for item in translations]

    def translate(self, text: str, src: str, tgt: str) -> str:
        text = re.sub(r'\s+', ' ', (text or '').strip())
        if not text:
            raise ValueError('Cannot translate empty text.')
        if src == tgt:
            return text

        chunks = self._split_text(text, self.max_chars)
        outputs: list[str] = []
        # Small batches reduce peak memory and make long classroom lessons safe.
        for index in range(0, len(chunks), 8):
            outputs.extend(self._translate_batch(chunks[index:index + 8], src, tgt))
        result = ' '.join(item for item in outputs if item).strip()
        if not result:
            raise RuntimeError('IndicTrans2 returned an empty translation.')
        return result

    def unload(self) -> None:
        with self._lock:
            self._bundles.clear()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
