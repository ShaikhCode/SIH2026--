from __future__ import annotations

import threading

import torch

from ..adapters.stt import FasterWhisperAdapter
from ..adapters.translation import IndicTrans2Adapter
from ..adapters.tts import IndicParlerTTSAdapter
from ..core.config import MODELS_ROOT, settings


class ModelManager:
    """Serializes heavy local model use so low-VRAM machines do not keep every model resident."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.translation = IndicTrans2Adapter(MODELS_ROOT, settings.cpu_only, settings.max_translation_chars)
        self.stt = FasterWhisperAdapter(MODELS_ROOT, settings.cpu_only)
        self.tts = IndicParlerTTSAdapter(
            MODELS_ROOT,
            settings.cpu_only,
            settings.parler_description_tokenizer,
        )
        self.last_error: dict[str, str] | None = None

    def status(self) -> dict:
        return {
            'demo_mode': settings.demo_mode,
            'enabled': {
                'translation': settings.translation_enabled,
                'stt': settings.stt_enabled,
                'tts': settings.tts_enabled,
                'llm': settings.llm_enabled,
            },
            'device': 'cpu' if settings.cpu_only else ('cuda' if torch.cuda.is_available() else 'cpu'),
            'cuda_available': bool(torch.cuda.is_available()),
            'model_root': str(MODELS_ROOT),
            'translation': self.translation.health(),
            'stt': self.stt.health(),
            'tts': self.tts.health(),
            'last_error': self.last_error,
        }

    def _record_error(self, stage: str, exc: Exception) -> None:
        self.last_error = {'stage': stage, 'type': type(exc).__name__, 'message': str(exc)[:1000]}

    def translate(self, text: str, src: str, tgt: str) -> str:
        with self.lock:
            self.stt.unload()
            self.tts.unload()
            try:
                return self.translation.translate(text, src, tgt)
            except Exception as exc:
                self._record_error('translation', exc)
                raise

    def transcribe(self, audio_path, language: str | None = 'hi') -> dict:
        with self.lock:
            self.translation.unload()
            self.tts.unload()
            try:
                return self.stt.transcribe(audio_path, language)
            except Exception as exc:
                self._record_error('stt', exc)
                raise

    def synthesize(self, text: str, out_path, language: str, speaker: str) -> dict:
        with self.lock:
            self.translation.unload()
            self.stt.unload()
            try:
                return self.tts.synthesize(text, out_path, language, speaker)
            except Exception as exc:
                self._record_error('tts', exc)
                raise

    def unload_heavy(self) -> None:
        with self.lock:
            self.translation.unload()
            self.stt.unload()
            self.tts.unload()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


manager = ModelManager()
