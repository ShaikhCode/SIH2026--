from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

LANGUAGE_DESCRIPTIONS = {
    'eng_Latn': 'English',
    'hin_Deva': 'Hindi',
    'mar_Deva': 'Marathi',
}


class IndicParlerTTSAdapter:
    """Local Indic Parler-TTS adapter.

    IMPORTANT: the Indic Parler-TTS checkpoint uses two tokenizers: its prompt
    tokenizer plus a description tokenizer whose model/config points to FLAN-T5.
    Only the tokenizer/config assets are needed from FLAN-T5; the large FLAN-T5
    model weights are not loaded by this adapter.
    """

    def __init__(self, model_root: Path, cpu_only: bool = False, description_tokenizer: str = ''):
        self.model_root = Path(model_root)
        self.model_path = self.model_root / 'tts' / 'indic-parler-tts'
        self.cpu_only = cpu_only
        configured = description_tokenizer.strip() or os.getenv('PARLER_DESCRIPTION_TOKENIZER', '').strip()
        self.description_tokenizer_path = self._resolve_description_path(configured)
        self._bundle = None
        self._lock = threading.RLock()

    def _resolve_description_path(self, configured: str) -> Path:
        candidates = []
        if configured:
            p = Path(configured)
            candidates.append(p if p.is_absolute() else self.model_root / p)
        candidates.extend([
            self.model_root / 'tts' / 'flan-t5-large',
            self.model_root / 'tts' / 'description-tokenizer',
        ])
        for path in candidates:
            if path.is_dir() and (path / 'tokenizer_config.json').is_file() and (
                (path / 'tokenizer.json').is_file() or (path / 'spiece.model').is_file()
            ):
                return path.resolve()
        return candidates[0].resolve() if candidates else (self.model_root / 'tts' / 'flan-t5-large').resolve()

    def health(self) -> dict[str, bool | str]:
        model_ready = self.model_path.is_dir() and (self.model_path / 'config.json').is_file() and any(
            (self.model_path / name).is_file() for name in ('model.safetensors', 'pytorch_model.bin')
        )
        tokenizer_ready = self.description_tokenizer_path.is_dir() and (
            (self.description_tokenizer_path / 'tokenizer.json').is_file()
            or (self.description_tokenizer_path / 'spiece.model').is_file()
        ) and (self.description_tokenizer_path / 'tokenizer_config.json').is_file()
        prompt_tokenizer_ready = (self.model_path / 'tokenizer.json').is_file() or (self.model_path / 'tokenizer.model').is_file()
        feature_ready = (self.model_path / 'preprocessor_config.json').is_file()
        return {
            'model': model_ready,
            'prompt_tokenizer': prompt_tokenizer_ready,
            'description_tokenizer': tokenizer_ready,
            'feature_extractor': feature_ready,
            'runtime_ready': bool(model_ready and tokenizer_ready and prompt_tokenizer_ready and feature_ready),
            'description_tokenizer_path': str(self.description_tokenizer_path),
        }

    def _load(self):
        with self._lock:
            if self._bundle is not None:
                return self._bundle

            health = self.health()
            if not health['model']:
                raise FileNotFoundError(f'Indic Parler-TTS model is incomplete: {self.model_path}')
            if not health['description_tokenizer']:
                raise RuntimeError(
                    'Indic Parler-TTS needs the local FLAN-T5 description tokenizer. '
                    f'Expected it at: {self.description_tokenizer_path}. '
                    'Run scripts\\download_tts_support.py once.'
                )
            if not health['prompt_tokenizer'] or not health['feature_extractor']:
                raise RuntimeError(
                    'Indic Parler-TTS model folder is missing tokenizer or preprocessor files. '
                    f'Check: {self.model_path}'
                )

            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoFeatureExtractor, AutoTokenizer

            device = torch.device('cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda')
            dtype = torch.float32 if device.type == 'cpu' else torch.bfloat16
            model = ParlerTTSForConditionalGeneration.from_pretrained(
                str(self.model_path),
                local_files_only=True,
                attn_implementation='eager',
                torch_dtype=dtype,
            ).to(device)
            model.eval()
            tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), local_files_only=True)
            description_tokenizer = AutoTokenizer.from_pretrained(
                str(self.description_tokenizer_path),
                local_files_only=True,
            )
            feature = AutoFeatureExtractor.from_pretrained(str(self.model_path), local_files_only=True)
            self._bundle = (model, tokenizer, description_tokenizer, feature, device)
            return self._bundle

    @staticmethod
    def _description(language: str, speaker: str) -> str:
        language_name = LANGUAGE_DESCRIPTIONS.get(language, 'English')
        return (
            f'{speaker} speaks {language_name} clearly at a calm, moderate pace, '
            'with a neutral classroom-teaching tone. The recording is high quality, '
            'clear and close, with no background noise.'
        )

    def synthesize(self, text: str, out_path: Path, language: str, speaker: str = 'classroom_teacher') -> dict:
        text = (text or '').strip()
        if not text:
            raise ValueError('Cannot synthesize empty text.')

        model, tokenizer, description_tokenizer, feature, device = self._load()
        description_inputs = description_tokenizer(
            self._description(language, speaker),
            return_tensors='pt',
        ).to(device)

        # The model's prompt context is sensitive to very long inputs. Keep chunks
        # moderate and concatenate the generated waveforms for a classroom lesson.
        words = text.split()
        chunks = [' '.join(words[i:i + 15]) for i in range(0, len(words), 15)] or [text]
        audio_chunks: list[np.ndarray] = []
        sampling_rate = int(feature.sampling_rate)

        with torch.inference_mode():
            for chunk in chunks:
                prompt_inputs = tokenizer(chunk, return_tensors='pt').to(device)
                generation = model.generate(
                    input_ids=description_inputs.input_ids,
                    attention_mask=description_inputs.attention_mask,
                    prompt_input_ids=prompt_inputs.input_ids,
                    prompt_attention_mask=prompt_inputs.attention_mask,
                    do_sample=True,
                    return_dict_in_generate=True,
                )
                if not hasattr(generation, 'sequences'):
                    raise RuntimeError('Indic Parler-TTS returned no audio sequence.')
                audio = generation.sequences[0]
                if hasattr(generation, 'audios_length'):
                    length = int(generation.audios_length[0])
                    audio = audio[:length]
                array = audio.to(torch.float32).detach().cpu().numpy().reshape(-1)
                if array.size:
                    audio_chunks.append(array)

        if not audio_chunks:
            raise RuntimeError('Indic Parler-TTS produced empty audio.')

        waveform = np.concatenate(audio_chunks).astype(np.float32)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_path, waveform, sampling_rate, subtype='PCM_16')
        return {
            'path': str(out_path),
            'sample_rate': sampling_rate,
            'duration_seconds': round(float(len(waveform) / sampling_rate), 2),
        }

    def unload(self) -> None:
        with self._lock:
            self._bundle = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
