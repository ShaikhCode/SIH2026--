from __future__ import annotations

import threading
from pathlib import Path

import torch


LANGUAGE_TO_WHISPER = {
    'hin_Deva': 'hi',
    'eng_Latn': 'en',
    # Marathi ASR is not claimed as verified by the MVP. None lets Whisper
    # detect it while still preserving the explicit limitation in the UI.
    'mar_Deva': 'mr',
}


class FasterWhisperAdapter:
    """Adapter for a local CTranslate2/faster-whisper checkpoint."""

    def __init__(self, model_root: Path, cpu_only: bool = False) -> None:
        self.path = Path(model_root) / 'stt' / 'whisper-small'
        self.cpu_only = cpu_only
        self._model = None
        self._lock = threading.RLock()

    def health(self) -> bool:
        required = self.path / 'model.bin'
        return self.path.is_dir() and required.is_file()

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            if not self.path.is_dir():
                raise FileNotFoundError(f'Missing Whisper model folder: {self.path}')
            if not (self.path / 'model.bin').is_file():
                raise RuntimeError(
                    'Whisper checkpoint is not a faster-whisper/CTranslate2 model: model.bin is missing.'
                )
            from faster_whisper import WhisperModel

            device = 'cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda'
            compute = 'int8' if device == 'cpu' else 'float16'
            self._model = WhisperModel(str(self.path), device=device, compute_type=compute)
            return self._model

    def transcribe(self, audio_path: Path, language: str | None = 'hi') -> dict:
        model = self._load()
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        collected = []
        segment_views = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                collected.append(text)
            segment_views.append({
                'start': float(segment.start),
                'end': float(segment.end),
                'text': text,
            })
        text = ' '.join(collected).strip()
        return {
            'text': text,
            'language': info.language,
            'probability': float(info.language_probability),
            'segments': segment_views,
        }

    def unload(self) -> None:
        with self._lock:
            self._model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
