from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

import torch


class IndicTrans2Adapter:
    """Local-only IndicTrans2 adapter.

    Models are loaded lazily and kept in memory until explicitly unloaded.
    The adapter supports Indic↔Indic, English→Indic, and Indic→English.
    """

    def __init__(self, model_root: Path, cpu_only: bool = False) -> None:
        self.model_root = model_root
        self.cpu_only = cpu_only
        self._models: dict[str, tuple[Any, Any]] = {}
        self._processors: dict[str, Any] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(src: str, tgt: str) -> str:
        if src.startswith("eng") and not tgt.startswith("eng"):
            return "en-indic"
        if not src.startswith("eng") and tgt.startswith("eng"):
            return "indic-en"
        return "indic-indic"

    def _path(self, key: str) -> Path:
        return self.model_root / "translation" / key

    def health(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for key in ("indic-indic", "en-indic", "indic-en"):
            path = self._path(key)
            # verify_models.py only needs a populated folder, while runtime
            # needs an actual HF model config as well.
            result[key] = (
                path.is_dir()
                and (path / "config.json").is_file()
                and any(path.iterdir())
            )
        return result

    def _load(self, key: str) -> tuple[tuple[Any, Any], Any]:
        with self._lock:
            if key in self._models:
                return self._models[key], self._processors[key]

            path = self._path(key)
            if not path.is_dir():
                raise FileNotFoundError(f"Missing translation model folder: {path}")
            if not (path / "config.json").is_file():
                raise RuntimeError(
                    f"IndicTrans2 model is incomplete: {path} is missing config.json. "
                    "Re-copy the complete Hugging Face model folder."
                )

            try:
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            except Exception as exc:
                raise RuntimeError(
                    "Transformers could not be imported. Run: pip install -r requirements.txt"
                ) from exc

            # Current IndicTransToolkit releases expose IndicProcessor from
            # the processor submodule. Keep a fallback for older installations.
            try:
                from IndicTransToolkit.processor import IndicProcessor
            except Exception:
                try:
                    from IndicTransToolkit import IndicProcessor  # type: ignore
                except Exception as exc:
                    raise RuntimeError(
                        "IndicProcessor could not be imported. "
                        "Run: pip install --upgrade IndicTransToolkit==1.1.1"
                    ) from exc

            device = torch.device(
                "cpu" if self.cpu_only or not torch.cuda.is_available() else "cuda"
            )

            tokenizer = AutoTokenizer.from_pretrained(
                str(path),
                trust_remote_code=True,
                local_files_only=True,
            )

            model_kwargs: dict[str, Any] = {
                "trust_remote_code": True,
                "local_files_only": True,
            }
            if device.type == "cuda":
                model_kwargs["torch_dtype"] = torch.float16

            model = AutoModelForSeq2SeqLM.from_pretrained(str(path), **model_kwargs)
            model.to(device).eval()
            processor = IndicProcessor(inference=True)

            self._models[key] = (tokenizer, model)
            self._processors[key] = processor
            return (tokenizer, model), processor

    def translate(self, text: str, src: str, tgt: str) -> str:
        text = (text or "").strip()
        if not text:
            raise ValueError("Cannot translate empty text.")
        if src == tgt:
            return text

        (tokenizer, model), processor = self._load(self._key(src, tgt))

        batch = processor.preprocess_batch(
            [text],
            src_lang=src,
            tgt_lang=tgt,
            visualize=False,
        )
        encoded = tokenizer(
            batch,
            padding="longest",
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        encoded = {k: v.to(model.device) for k, v in encoded.items()}

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
        translations = processor.postprocess_batch(
            decoded,
            lang=tgt,
        )
        if not translations or not translations[0].strip():
            raise RuntimeError("IndicTrans2 returned an empty translation.")
        return translations[0].strip()

    def unload(self) -> None:
        with self._lock:
            self._models.clear()
            self._processors.clear()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
