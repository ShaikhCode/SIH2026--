from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import torch

from ..adapters.stt import FasterWhisperAdapter
from ..adapters.translation import IndicTrans2Adapter
from ..adapters.tts import IndicParlerTTSAdapter
from ..core.config import MODELS_ROOT, settings


class ModelManager:
    """Shared resident model registry.

    Previous builds unloaded the other two heavy models before every request.
    That guaranteed slow classroom actions because translation/TTS repeatedly paid
    model construction time. This version keeps loaded models warm and lets the
    independent pipeline stages use their own adapter locks.
    """

    def __init__(self) -> None:
        thread_setting = os.getenv('BHASHA_TORCH_THREADS', '').strip()
        if thread_setting.isdigit():
            try:
                torch.set_num_threads(max(1, int(thread_setting)))
            except Exception:
                pass
        self._registry_lock = threading.RLock()
        self.translation = IndicTrans2Adapter(
            MODELS_ROOT,
            settings.cpu_only,
            settings.max_translation_chars,
            text_beams=settings.text_translation_beams,
            route_cache_limit=settings.translation_route_cache_limit,
        )
        self.stt = FasterWhisperAdapter(MODELS_ROOT, settings.cpu_only)
        self.tts = IndicParlerTTSAdapter(MODELS_ROOT, settings.cpu_only, settings.parler_description_tokenizer)
        self.last_error: dict[str, str] | None = None

    def status(self) -> dict[str, Any]:
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
            'translation_loaded': self.translation.loaded(),
            'stt': self.stt.health(),
            'stt_loaded': self.stt.loaded(),
            'tts': self.tts.health(),
            'last_error': self.last_error,
            'performance': {
                'keep_models_loaded': settings.keep_models_loaded,
                'translation_beams': settings.text_translation_beams,
                'live_translation_beams': settings.live_translation_beams,
                'live_segment_ms': settings.max_live_segment_ms,
                'live_queue_size': settings.live_queue_size,
                'live_tts_stream_seconds': settings.live_tts_stream_seconds,
                'live_tts_stream_timeout': settings.live_tts_stream_timeout,
            },
        }

    def _record_error(self, stage: str, exc: Exception) -> None:
        self.last_error = {'stage': stage, 'type': type(exc).__name__, 'message': str(exc)[:1000]}

    def translate(self, text: str, src: str, tgt: str, *, fast: bool = False) -> str:
        try:
            return self.translation.translate(text, src, tgt, beams=settings.live_translation_beams if fast else settings.text_translation_beams)
        except Exception as exc:
            self._record_error('translation', exc)
            raise

    def translate_many(self, texts: list[str], src: str, tgt: str, *, fast: bool = False) -> list[str]:
        try:
            return self.translation.translate_many(texts, src, tgt, beams=settings.live_translation_beams if fast else settings.text_translation_beams)
        except Exception as exc:
            self._record_error('translation', exc)
            raise

    def transcribe(self, audio_path: Path, language: str | None = 'hi') -> dict:
        try:
            return self.stt.transcribe(audio_path, language)
        except Exception as exc:
            self._record_error('stt', exc)
            raise

    def transcribe_audio(self, audio, language: str | None = None) -> dict:
        try:
            return self.stt.transcribe_audio(audio, language)
        except Exception as exc:
            self._record_error('stt', exc)
            raise

    def synthesize(self, text: str, out_path: Path, language: str, speaker: str) -> dict:
        try:
            return self.tts.synthesize(text, out_path, language, speaker)
        except Exception as exc:
            self._record_error('tts', exc)
            raise

    def synthesize_bytes(self, text: str, language: str, speaker: str) -> tuple[bytes, int, float]:
        try:
            return self.tts.synthesize_bytes(text, language, speaker)
        except Exception as exc:
            self._record_error('tts', exc)
            raise

    def warm_translation(self, src: str, tgt: str, *, fast: bool = False) -> dict[str, Any]:
        return self.translation.warm(src, tgt, beams=settings.live_translation_beams if fast else settings.text_translation_beams)

    def warm_live(self, src: str, tgt: str) -> dict[str, Any]:
        """Load only what the live pipeline needs; loading is idempotent."""
        results: dict[str, Any] = {'source': src, 'target': tgt}
        self.stt.warm()
        results['stt'] = True
        if src != tgt:
            results['translation'] = self.translation.warm(src, tgt, beams=settings.live_translation_beams)
        else:
            results['translation'] = {'route': 'bypass', 'loaded': True}
        self.tts.warm()
        results['tts'] = True
        return results

    def unload_heavy(self) -> None:
        with self._registry_lock:
            self.translation.unload()
            self.stt.unload()
            self.tts.unload()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


manager = ModelManager()
