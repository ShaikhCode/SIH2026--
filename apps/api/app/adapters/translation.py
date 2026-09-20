from __future__ import annotations

import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import torch


class IndicTrans2Adapter:
    """Fast, persistent local IndicTrans2 adapter.

    Important performance choices:
    - model bundles stay warm instead of being unloaded after every request;
    - repeated text is served from a bounded in-memory cache;
    - short interactive translations use a smaller beam count than lesson-scale text;
    - multiple strings are translated in one model call when possible.
    """

    def __init__(
        self,
        model_root: Path,
        cpu_only: bool = False,
        max_chars: int = 12000,
        text_beams: int = 3,
        route_cache_limit: int = 3,
    ) -> None:
        self.model_root = Path(model_root)
        self.cpu_only = cpu_only
        self.max_chars = max_chars
        self.text_beams = max(1, min(int(text_beams), 5))
        self.live_beams = max(1, min(int(text_beams), 3))
        self._bundles: dict[str, tuple[Any, Any, Any, torch.device]] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._registry_lock = threading.RLock()
        self._cache: OrderedDict[tuple[str, str, str, int], str] = OrderedDict()
        self._cache_limit = 256
        # Keep all three validated demo routes resident: en↔Indic and Indic↔Indic.
        # Evicting one route caused a full model reload when the user switched
        # repeatedly between English, Hindi and Marathi in the lesson builder.
        self._route_limit = max(1, min(int(route_cache_limit), 3))
        self._route_order: OrderedDict[str, None] = OrderedDict()

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

    def _get_lock(self, key: str) -> threading.RLock:
        with self._registry_lock:
            return self._locks.setdefault(key, threading.RLock())

    def health(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for key in ('indic-indic', 'en-indic', 'indic-en'):
            path = self._resolve_model_dir(self._path(key))
            has_config = (path / 'config.json').is_file()
            has_weights = any(path.glob('*.safetensors')) or any(
                (path / name).is_file() for name in ('pytorch_model.bin', 'model.bin')
            )
            has_tokenizer = any(
                (path / name).is_file()
                for name in ('tokenizer.json', 'tokenizer.model', 'sentencepiece.bpe.model', 'tokenizer_config.json')
            )
            result[key] = bool(path.is_dir() and has_config and has_weights and has_tokenizer)
        return result

    def loaded(self) -> dict[str, bool]:
        with self._registry_lock:
            return {key: key in self._bundles for key in ('indic-indic', 'en-indic', 'indic-en')}

    def _load(self, key: str):
        lock = self._get_lock(key)
        with lock:
            if key in self._bundles:
                with self._registry_lock:
                    self._route_order.pop(key, None)
                    self._route_order[key] = None
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
                except Exception as exc:
                    raise RuntimeError(
                        'IndicProcessor could not be imported. Install IndicTransToolkit==1.1.1.'
                    ) from exc

            device = torch.device('cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda')
            tokenizer = AutoTokenizer.from_pretrained(
                str(path), trust_remote_code=True, local_files_only=True
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
            bundle = (tokenizer, model, processor, device)
            self._bundles[key] = bundle
            with self._registry_lock:
                self._route_order.pop(key, None)
                self._route_order[key] = None
                while len(self._route_order) > self._route_limit:
                    old_key, _ = self._route_order.popitem(last=False)
                    if old_key != key:
                        self._bundles.pop(old_key, None)
            return bundle

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'\s+', ' ', (text or '').strip())

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        normalized = IndicTrans2Adapter._normalize(text)
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
                continue
            if current:
                chunks.append(current)
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

    def _cache_get(self, key: tuple[str, str, str, int]) -> str | None:
        with self._registry_lock:
            value = self._cache.get(key)
            if value is None:
                return None
            self._cache.move_to_end(key)
            return value

    def _cache_put(self, key: tuple[str, str, str, int], value: str) -> None:
        with self._registry_lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)

    def _translate_batch(self, texts: list[str], src: str, tgt: str, beams: int) -> list[str]:
        tokenizer, model, processor, device = self._load(self._key(src, tgt))
        batch = processor.preprocess_batch(texts, src_lang=src, tgt_lang=tgt, visualize=False)
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
                num_beams=max(1, min(beams, 5)),
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

    def translate_many(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        *,
        beams: int | None = None,
    ) -> list[str]:
        normalized = [self._normalize(item) for item in texts]
        if not any(normalized):
            return ['' for _ in texts]
        if src == tgt:
            return normalized

        beam_count = max(1, min(int(beams if beams is not None else self.text_beams), 5))
        results: list[str | None] = [None] * len(normalized)
        pending_texts: list[str] = []
        pending_indices: list[int] = []
        for index, text in enumerate(normalized):
            if not text:
                results[index] = ''
                continue
            cache_key = (src, tgt, text, beam_count)
            cached = self._cache_get(cache_key)
            if cached is not None:
                results[index] = cached
            else:
                chunks = self._split_text(text, self.max_chars)
                if len(chunks) > 1:
                    translated_chunks = self.translate_many(chunks, src, tgt, beams=beam_count)
                    combined = ' '.join(item for item in translated_chunks if item).strip()
                    self._cache_put(cache_key, combined)
                    results[index] = combined
                else:
                    pending_texts.append(text)
                    pending_indices.append(index)

        for start in range(0, len(pending_texts), 8):
            batch_texts = pending_texts[start:start + 8]
            translated = self._translate_batch(batch_texts, src, tgt, beam_count)
            for offset, value in enumerate(translated):
                index = pending_indices[start + offset]
                results[index] = value
                self._cache_put((src, tgt, batch_texts[offset], beam_count), value)

        return [value or '' for value in results]

    def translate(self, text: str, src: str, tgt: str, *, beams: int | None = None) -> str:
        result = self.translate_many([text], src, tgt, beams=beams)
        if not result or not result[0]:
            raise RuntimeError('IndicTrans2 returned an empty translation.')
        return result[0]

    def warm(self, src: str, tgt: str, *, beams: int | None = None) -> dict[str, object]:
        if src == tgt:
            return {'route': 'bypass', 'loaded': True}
        key = self._key(src, tgt)
        self._load(key)
        return {'route': key, 'loaded': True, 'device': str(self._bundles[key][3])}

    def unload(self) -> None:
        with self._registry_lock:
            self._bundles.clear()
            self._route_order.clear()
            self._cache.clear()
            self._locks.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
