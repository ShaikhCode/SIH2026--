from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import torch


LANGUAGE_TO_WHISPER = {
    'hin_Deva': 'hi',
    'eng_Latn': 'en',
    'mar_Deva': 'mr',
}


class FasterWhisperAdapter:
    """Persistent faster-whisper adapter with an optimized live path."""

    def __init__(self, model_root: Path, cpu_only: bool = False) -> None:
        self.path = Path(model_root) / 'stt' / 'whisper-small'
        self.cpu_only = cpu_only
        self._model = None
        self._lock = threading.RLock()

    def health(self) -> bool:
        return self.path.is_dir() and (self.path / 'model.bin').is_file()

    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            if not self.path.is_dir():
                raise FileNotFoundError(f'Missing Whisper model folder: {self.path}')
            if not (self.path / 'model.bin').is_file():
                raise RuntimeError('Whisper checkpoint is not a faster-whisper/CTranslate2 model: model.bin is missing.')
            from faster_whisper import WhisperModel
            device = 'cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda'
            compute = 'int8' if device == 'cpu' else 'float16'
            kwargs = {'device': device, 'compute_type': compute}
            if device == 'cpu':
                kwargs['cpu_threads'] = max(4, (torch.get_num_threads() or 4))
                kwargs['num_workers'] = 1
            self._model = WhisperModel(str(self.path), **kwargs)
            return self._model

    @staticmethod
    def _language(language: str | None) -> str | None:
        if language in {'en', 'hi', 'mr'}:
            return language
        return LANGUAGE_TO_WHISPER.get(language or '')

    def transcribe_audio(self, audio: np.ndarray, language: str | None = None) -> dict:
        model = self._load()
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return {'text': '', 'language': self._language(language) or '', 'probability': 0.0, 'segments': []}
        segments, info = model.transcribe(
            audio,
            language=self._language(language),
            task='transcribe',
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            word_timestamps=False,
        )
        collected: list[str] = []
        views: list[dict[str, object]] = []
        for segment in segments:
            text = (segment.text or '').strip()
            if text:
                collected.append(text)
            views.append({'start': float(segment.start), 'end': float(segment.end), 'text': text})
        return {
            'text': ' '.join(collected).strip(),
            'language': getattr(info, 'language', '') or '',
            'probability': float(getattr(info, 'language_probability', 0.0) or 0.0),
            'segments': views,
        }

    def transcribe(self, audio_path: Path, language: str | None = None) -> dict:
        model = self._load()
        segments, info = model.transcribe(
            str(audio_path),
            language=self._language(language),
            task='transcribe',
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            word_timestamps=False,
        )
        collected: list[str] = []
        views: list[dict[str, object]] = []
        for segment in segments:
            text = (segment.text or '').strip()
            if text:
                collected.append(text)
            views.append({'start': float(segment.start), 'end': float(segment.end), 'text': text})
        return {
            'text': ' '.join(collected).strip(),
            'language': getattr(info, 'language', '') or '',
            'probability': float(getattr(info, 'language_probability', 0.0) or 0.0),
            'segments': views,
        }

    def warm(self) -> None:
        self._load()

    def unload(self) -> None:
        with self._lock:
            self._model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
