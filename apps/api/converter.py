"""
BhashaSaathi - single-file local real-time speech translation prototype.

Expected directory layout (relative to this file):

models/
├── translation/
│   ├── en-indic/
│   ├── indic-en/
│   └── indic-indic/
├── stt/
│   └── whisper-small/
└── tts/
    ├── indic-parler-tts/
    └── flan-t5-large/

Environment already used by the diagnostic bench:
    transformers==4.46.1
    huggingface_hub==0.36.0
    parler-tts==0.2.2
    IndicTransToolkit==1.1.1
    faster-whisper (installed and working)

Additional runtime packages used by this single file:
    numpy
    scipy
    sounddevice
    soundfile
    soundcard  # Windows/WASAPI output path (recommended)

Example install command:
    pip install numpy scipy sounddevice soundfile soundcard

This program intentionally uses local_files_only=True for the Transformers-based
models. It will not silently download model weights during inference.

IMPORTANT:
- The supplied BhashaSaathi handoff says the current Whisper checkpoint is
  CTranslate2/faster-whisper style. Do NOT rename model.bin.
- The supplied handoff also says Parler-TTS is currently blocked until the
  local FLAN-T5 description tokenizer exists at models/tts/flan-t5-large
  (or PARLER_DESCRIPTION_TOKENIZER points to it).
- This prototype is one-way live translation per run. Use Swap and restart for
  the reverse direction. True automatic two-speaker diarized conversation is a
  separate layer and is deliberately not faked here.
"""

from __future__ import annotations

import argparse
import gc
import io
import math
import os
import queue
import re
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# -----------------------------
# Optional imports with friendly errors
# -----------------------------

try:
    import numpy as np
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing numpy. Install with: pip install numpy") from exc

try:
    import scipy.signal
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing scipy. Install with: pip install scipy") from exc

try:
    import sounddevice as sd
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing sounddevice. Install with: pip install sounddevice") from exc

try:
    import soundfile as sf
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing soundfile. Install with: pip install soundfile") from exc

if sys.platform.startswith("win"):
    try:
        import winsound
    except Exception:
        winsound = None
else:
    winsound = None

try:
    import soundcard as sc
except Exception:
    sc = None

try:
    import torch
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing torch. Install the PyTorch build appropriate for your system.") from exc

try:
    from faster_whisper import WhisperModel
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing faster-whisper. Install with: pip install faster-whisper") from exc

try:
    from transformers import AutoFeatureExtractor, AutoModelForSeq2SeqLM, AutoTokenizer
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing transformers. Install the pinned version from the BhashaSaathi handoff.") from exc

try:
    from IndicTransToolkit.processor import IndicProcessor
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing IndicTransToolkit. Install IndicTransToolkit==1.1.1") from exc

try:
    from parler_tts import ParlerTTSForConditionalGeneration
    try:
        from parler_tts import ParlerTTSStreamer
    except Exception:
        ParlerTTSStreamer = None
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing parler-tts. Install parler-tts==0.2.2") from exc

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception as exc:  # pragma: no cover
    raise SystemExit("Tkinter is required. On Windows it is normally included with Python.") from exc


# -----------------------------
# Configuration
# -----------------------------

APP_NAME = "BhashaSaathi"
ROOT_DIR = Path(__file__).resolve().parent

def _resolve_model_root() -> Path:
    candidates = [ROOT_DIR / "models", ROOT_DIR]
    for candidate in candidates:
        if (candidate / "stt" / "whisper-small").exists():
            return candidate
    return candidates[0]

MODEL_ROOT = _resolve_model_root()

STT_DIR = MODEL_ROOT / "stt" / "whisper-small"
EN_INDIC_DIR = MODEL_ROOT / "translation" / "en-indic"
INDIC_EN_DIR = MODEL_ROOT / "translation" / "indic-en"
INDIC_INDIC_DIR = MODEL_ROOT / "translation" / "indic-indic"
TTS_DIR = MODEL_ROOT / "tts" / "indic-parler-tts"
DEFAULT_FLAN_DIR = MODEL_ROOT / "tts" / "flan-t5-large"

AUDIO_RATE = 16_000
BLOCK_MS = 30
MAX_INPUT_QUEUE = 128
MAX_STAGE_QUEUE = 24

# Speech segmentation / VAD-like energy parameters.
PRE_ROLL_MS = 180
START_HOLD_MS = 120
END_SILENCE_MS = 280
MIN_UTTERANCE_MS = 250
# Do not wait for the speaker to finish a long sentence. Continuous speech is
# emitted in short live chunks so STT/translation/TTS can begin while the user
# is still talking. This is intentionally a product-level latency trade-off.
MAX_UTTERANCE_MS = 2_200
BOUNDARY_SEARCH_MS = 550
LIVE_MIN_CHUNK_MS = 1_200
TTS_STREAM_CHUNK_S = 0.50
START_DB = -39.0
SPEECH_OFFSET_DB = 7.0
SILENCE_OFFSET_DB = 3.0
NOISE_EMA = 0.02

# Translation parameters. The official IndicTrans2 example uses 5 beams;
# 4 is a deliberate latency/quality compromise for an interactive demo.
NUM_BEAMS = 4
MAX_TRANSLATION_LENGTH = 256

# Parler description. The model's prompt text is the translated sentence;
# this description controls the speaking style.
TTS_SPEAKERS = {
    "English": "Thoma",
    "Hindi": "Rohit",
    "Marathi": "Sanjay",
    "Bengali": "Arjun",
    "Gujarati": "Yash",
    "Kannada": "Suresh",
    "Malayalam": "Anjali",
    "Nepali": "Amrita",
    "Odia": "Manas",
    "Tamil": "Jaya",
    "Telugu": "Prakash",
}


def tts_description_for(language_name: str) -> str:
    speaker = TTS_SPEAKERS.get(language_name)
    if speaker:
        return (
            f"{speaker}'s voice is clear and natural, speaking at a moderate pace "
            "with clear pronunciation and very clear audio in a close-sounding recording."
        )
    return (
        "A clear natural Indian speaker delivers the sentence at a moderate pace "
        "with clear pronunciation and very clear audio in a close-sounding recording."
    )

# Optional environment controls.
# BHASHA_MODEL_DEVICE=cpu|cuda|auto
MODEL_DEVICE_OVERRIDE = os.getenv("BHASHA_MODEL_DEVICE", "auto").strip().lower()
PARLER_DESCRIPTION_TOKENIZER = Path(
    os.getenv("PARLER_DESCRIPTION_TOKENIZER", str(DEFAULT_FLAN_DIR))
).expanduser()
if not PARLER_DESCRIPTION_TOKENIZER.is_absolute():
    PARLER_DESCRIPTION_TOKENIZER = (ROOT_DIR / PARLER_DESCRIPTION_TOKENIZER).resolve()


# -----------------------------
# Language registry
# -----------------------------

@dataclass(frozen=True)
class Language:
    name: str
    indic_code: str
    whisper_code: Optional[str]
    tts_supported: bool = True


LANGUAGES: dict[str, Language] = {
    "English": Language("English", "eng_Latn", "en", True),
    "Hindi": Language("Hindi", "hin_Deva", "hi", True),
    "Marathi": Language("Marathi", "mar_Deva", "mr", True),
    "Bengali": Language("Bengali", "ben_Beng", "bn", True),
    "Gujarati": Language("Gujarati", "guj_Gujr", "gu", True),
    "Kannada": Language("Kannada", "kan_Knda", "kn", True),
    "Malayalam": Language("Malayalam", "mal_Mlym", "ml", True),
    "Punjabi": Language("Punjabi", "pan_Guru", "pa", True),
    "Tamil": Language("Tamil", "tam_Taml", "ta", True),
    "Telugu": Language("Telugu", "tel_Telu", "te", True),
    "Odia": Language("Odia", "ory_Orya", "or", True),
    "Assamese": Language("Assamese", "asm_Beng", "as", True),
    "Nepali": Language("Nepali", "npi_Deva", "ne", True),
    "Urdu": Language("Urdu", "urd_Arab", "ur", True),
    # Whisper language handling for Santali is intentionally left as auto until
    # the local checkpoint is tested with real Santali audio, matching the handoff.
    "Santali (experimental)": Language("Santali (experimental)", "sat_Olck", None, True),
}

LANGUAGE_NAMES = list(LANGUAGES.keys())


# -----------------------------
# Data objects
# -----------------------------

@dataclass
class SpeechSegment:
    sequence_id: int
    audio: np.ndarray
    sample_rate: int
    created_at: float
    ended_at: float
    duration_s: float


@dataclass
class TextJob:
    segment: SpeechSegment
    transcript: str
    detected_language: Optional[str] = None
    language_probability: float = 0.0
    stt_time_s: float = 0.0


@dataclass
class TranslationJob:
    segment: SpeechSegment
    transcript: str
    translated_text: str
    stt_time_s: float
    translation_time_s: float


@dataclass
class AudioJob:
    segment: SpeechSegment
    transcript: str
    translated_text: str
    audio: np.ndarray
    sample_rate: int
    stage_time_s: float
    stt_time_s: float
    translation_time_s: float
    tts_time_s: float
    ready_at: float


# -----------------------------
# Helpers
# -----------------------------


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def rms_db(audio: np.ndarray) -> float:
    if audio.size == 0:
        return -120.0
    a = np.asarray(audio, dtype=np.float32)
    rms = float(np.sqrt(np.mean(np.square(a)) + 1e-12))
    return 20.0 * math.log10(max(rms, 1e-7))


def resample_to_16k(audio: np.ndarray, source_rate: int) -> np.ndarray:
    if source_rate == AUDIO_RATE:
        return np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return np.zeros(0, dtype=np.float32)
    g = math.gcd(int(source_rate), AUDIO_RATE)
    up = AUDIO_RATE // g
    down = int(source_rate) // g
    out = scipy.signal.resample_poly(np.asarray(audio, dtype=np.float32), up, down)
    return np.asarray(out, dtype=np.float32)


def get_output_config(output_device: int, preferred_rate: int) -> tuple[int, int]:
    """Choose a sample rate/channel count accepted by the selected Windows output device.

    WASAPI Bluetooth devices often expose stereo-only endpoints.  The previous
    implementation forced mono and then used the blocking OutputStream.write()
    API, which can fail on some WASAPI devices.  We now select a valid channel
    count and use callback-driven playback instead.
    """
    info = sd.query_devices(output_device, "output")
    default_rate = int(round(float(info.get("default_samplerate", 48000))))
    max_channels = int(info.get("max_output_channels", 2) or 2)
    channel_candidates = [2, 1] if max_channels >= 2 else [1]
    rate_candidates: list[int] = []
    for rate in (preferred_rate, default_rate, 48000, 44100, 32000, 24000, 16000):
        rate = int(rate)
        if rate > 0 and rate not in rate_candidates:
            rate_candidates.append(rate)

    errors: list[str] = []
    for channels in channel_candidates:
        for rate in rate_candidates:
            try:
                sd.check_output_settings(
                    device=output_device,
                    samplerate=rate,
                    channels=channels,
                    dtype="float32",
                )
                return rate, channels
            except Exception as exc:
                errors.append(f"{rate}Hz/{channels}ch: {exc}")

    raise RuntimeError(
        f"Output device {output_device} ({info.get('name', 'unknown')}) does not accept the tested "
        f"audio formats. Last errors: {' | '.join(errors[-4:])}"
    )


def get_output_sample_rate(output_device: int, preferred_rate: int) -> int:
    return get_output_config(output_device, preferred_rate)[0]


def resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """High-quality CPU resampling used only at the audio-device boundary."""
    if audio.size == 0 or source_rate == target_rate:
        return np.asarray(audio, dtype=np.float32)
    g = math.gcd(int(source_rate), int(target_rate))
    up = int(target_rate) // g
    down = int(source_rate) // g
    return np.asarray(
        scipy.signal.resample_poly(np.asarray(audio, dtype=np.float32), up, down),
        dtype=np.float32,
    )


def _normalize_device_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def resolve_soundcard_speaker(output_device: int):
    """Map PortAudio's selected output index to a Windows/WASAPI SoundCard speaker."""
    if sc is None:
        return None
    try:
        portaudio_name = str(sd.query_devices(output_device, "output")["name"])
    except Exception:
        return None
    try:
        return sc.get_speaker(portaudio_name)
    except Exception:
        pass
    target = _normalize_device_name(portaudio_name)
    try:
        speakers = sc.all_speakers()
    except Exception:
        return None
    # Prefer exact/containment matches, then a token-overlap match.
    for speaker in speakers:
        sn = _normalize_device_name(getattr(speaker, "name", ""))
        if sn == target or target in sn or sn in target:
            return speaker
    target_tokens = set(target.split())
    best = None
    best_score = 0
    for speaker in speakers:
        sn = _normalize_device_name(getattr(speaker, "name", ""))
        score = len(target_tokens.intersection(sn.split()))
        if score > best_score:
            best_score = score
            best = speaker
    return best if best_score >= 1 else None


def cleanup_torch() -> None:
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


def choose_compute_device() -> str:
    if MODEL_DEVICE_OVERRIDE in {"cpu", "cuda"}:
        if MODEL_DEVICE_OVERRIDE == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return MODEL_DEVICE_OVERRIDE

    if not torch.cuda.is_available():
        return "cpu"

    # A 4 GB-class GPU is deliberately not selected for both the 0.9B TTS and
    # translation model automatically. The diagnostic environment in the handoff
    # is CPU-only, and the local TTS checkpoint is large enough that conservative
    # auto-selection is safer.
    try:
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024 ** 3)
        return "cuda" if vram_gb >= 8.0 else "cpu"
    except Exception:
        return "cpu"


def choose_tts_device() -> str:
    override = os.getenv("BHASHA_TTS_DEVICE", "auto").strip().lower()
    if override == "cpu":
        return "cpu"
    if override == "cuda" and torch.cuda.is_available():
        return "cuda"
    # For TTS specifically, prefer CUDA whenever available because autoregressive
    # waveform generation is the current latency bottleneck. If loading fails
    # with OOM, the engine automatically falls back to CPU.
    if override == "auto" and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def choose_whisper_device() -> tuple[str, str]:
    if torch.cuda.is_available():
        try:
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024 ** 3)
            if vram_gb >= 4.0:
                return "cuda", "float16"
        except Exception:
            pass
    return "cpu", "int8"


def device_dtype(device: str) -> torch.dtype:
    return torch.float16 if device == "cuda" else torch.float32


def tensor_to_numpy_audio(tensor: Any) -> np.ndarray:
    if isinstance(tensor, torch.Tensor):
        arr = tensor.detach().float().cpu().numpy()
    else:
        arr = np.asarray(tensor, dtype=np.float32)
    arr = np.asarray(arr, dtype=np.float32).squeeze()
    if arr.ndim > 1:
        arr = np.mean(arr, axis=0)
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 1.0:
        arr = arr / peak
    return np.clip(arr, -1.0, 1.0).astype(np.float32)


def _device_role_tag(device: dict[str, Any]) -> str:
    kind = []
    if int(device.get("max_input_channels", 0)) > 0:
        kind.append("IN")
    if int(device.get("max_output_channels", 0)) > 0:
        kind.append("OUT")
    return "/".join(kind)


def _is_likely_virtual_or_loopback(name: str) -> bool:
    low = name.lower()
    blocked = (
        "stereo mix",
        "what u hear",
        "wave out",
        "loopback",
        "cable output",
        "voicemeeter",
        "virtual",
        "vb-audio",
        "monitor",
    )
    return any(token in low for token in blocked)


def _preferred_input_name(name: str) -> bool:
    low = name.lower()
    return any(token in low for token in (
        "microphone array", "microphone", "mic", "realtek", "usb", "webcam"
    )) and not _is_likely_virtual_or_loopback(name)


def _preferred_output_name(name: str) -> bool:
    low = name.lower()
    # Prefer normal stereo headphones/earbuds over Bluetooth Hands-Free/HFP.
    return any(token in low for token in (
        "headphones", "headphone", "earphones", "earphone", "buds", "stereo", "speaker"
    )) and "hands-free" not in low and "headset" not in low


def pretty_device_name(index: int, device: dict[str, Any], default_in: int | None = None, default_out: int | None = None) -> str:
    tag = _device_role_tag(device)
    markers = []
    if default_in == index:
        markers.append("DEFAULT IN")
    if default_out == index:
        markers.append("DEFAULT OUT")
    marker = f" | {' + '.join(markers)}" if markers else ""
    return f"{index}: {device['name']} [{tag}{marker}]"


def list_audio_devices() -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    inputs: list[tuple[int, str]] = []
    outputs: list[tuple[int, str]] = []
    try:
        default_in, default_out = sd.default.device
        default_in = int(default_in) if default_in is not None and int(default_in) >= 0 else None
        default_out = int(default_out) if default_out is not None and int(default_out) >= 0 else None
    except Exception:
        default_in = default_out = None

    for idx, d in enumerate(sd.query_devices()):
        label = pretty_device_name(idx, d, default_in, default_out)
        if int(d.get("max_input_channels", 0)) > 0:
            # Keep all valid input devices visible, but mark likely bad loopbacks.
            inputs.append((idx, label))
        if int(d.get("max_output_channels", 0)) > 0:
            outputs.append((idx, label))
    return inputs, outputs


def find_device_index(label: str) -> Optional[int]:
    if not label:
        return None
    m = re.match(r"\s*(\d+)\s*:", label)
    return int(m.group(1)) if m else None


def split_sentences(text: str, max_chars: int = 320) -> list[str]:
    """Keep TTS prompts reasonably sized without breaking normal punctuation."""
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?।॥])\s+", text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            chunks.append(part)
            continue
        words = part.split()
        current = []
        current_len = 0
        for word in words:
            add = len(word) + (1 if current else 0)
            if current and current_len + add > max_chars:
                chunks.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += add
        if current:
            chunks.append(" ".join(current))
    return chunks or [text]


# -----------------------------
# Model wrappers
# -----------------------------

class WhisperEngine:
    def __init__(self, model_dir: Path, ui: "UIBridge") -> None:
        self.model_dir = model_dir
        self.ui = ui
        self.model: Optional[WhisperModel] = None
        self.device, self.compute_type = choose_whisper_device()
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self.model is not None:
                return
            if not self.model_dir.exists():
                raise FileNotFoundError(f"Whisper model directory not found: {self.model_dir}")
            self.ui.status(f"Loading Whisper on {self.device} ({self.compute_type})...")
            kwargs: dict[str, Any] = {
                "device": self.device,
                "compute_type": self.compute_type,
            }
            if self.device == "cpu":
                kwargs["cpu_threads"] = max(4, (os.cpu_count() or 8) // 2)
            self.model = WhisperModel(str(self.model_dir), **kwargs)
            self.ui.status("Whisper ready")

    def transcribe(self, audio: np.ndarray, language: Optional[str]) -> tuple[str, str, float, float]:
        self.load()
        assert self.model is not None
        started = time.perf_counter()
        segments, info = self.model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            word_timestamps=False,
        )
        text_parts: list[str] = []
        for seg in segments:
            txt = (seg.text or "").strip()
            if txt:
                text_parts.append(txt)
        text = " ".join(text_parts).strip()
        elapsed = time.perf_counter() - started
        detected = getattr(info, "language", "") or ""
        probability = safe_float(getattr(info, "language_probability", 0.0))
        return text, detected, probability, max(elapsed, 0.0)


class IndicTranslationEngine:
    def __init__(self, ui: "UIBridge", source: Language, target: Language) -> None:
        self.ui = ui
        self.source = source
        self.target = target
        self.device = choose_compute_device()
        self.dtype = device_dtype(self.device)
        self.processor = IndicProcessor(inference=True)
        self.model: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.model_dir: Optional[Path] = None
        self._lock = threading.Lock()

    def _route(self) -> Optional[Path]:
        src_en = self.source.name == "English"
        tgt_en = self.target.name == "English"
        if src_en and tgt_en:
            return None
        if src_en:
            return EN_INDIC_DIR
        if tgt_en:
            return INDIC_EN_DIR
        return INDIC_INDIC_DIR

    def load(self) -> None:
        route_dir = self._route()
        if route_dir is None:
            return
        with self._lock:
            if self.model is not None:
                return
            if not route_dir.exists():
                raise FileNotFoundError(f"Translation model directory not found: {route_dir}")
            self.ui.status(f"Loading IndicTrans2: {route_dir.name} on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(route_dir),
                trust_remote_code=True,
                local_files_only=True,
            )
            kwargs: dict[str, Any] = {
                "trust_remote_code": True,
                "local_files_only": True,
            }
            if self.device == "cuda":
                kwargs["torch_dtype"] = self.dtype
            self.model = AutoModelForSeq2SeqLM.from_pretrained(str(route_dir), **kwargs)
            self.model = self.model.to(self.device)
            self.model.eval()
            self.model_dir = route_dir
            self.ui.status(f"Translation model ready: {route_dir.name}")

    def translate(self, text: str) -> tuple[str, float]:
        if self.source.name == self.target.name:
            return text, 0.0
        self.load()
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Translation model did not initialize")

        started = time.perf_counter()
        processed = self.processor.preprocess_batch(
            [text],
            src_lang=self.source.indic_code,
            tgt_lang=self.target.indic_code,
        )
        inputs = self.tokenizer(
            processed,
            truncation=True,
            padding="longest",
            return_tensors="pt",
            return_attention_mask=True,
        ).to(self.device)

        with torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                use_cache=True,
                min_length=0,
                max_length=MAX_TRANSLATION_LENGTH,
                num_beams=NUM_BEAMS,
                num_return_sequences=1,
            )

        decoded = self.tokenizer.batch_decode(
            generated,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )
        result = self.processor.postprocess_batch(
            decoded,
            lang=self.target.indic_code,
        )[0]
        elapsed = time.perf_counter() - started
        return result.strip(), max(elapsed, 0.0)


class ParlerTTSEngine:
    def __init__(self, ui: "UIBridge", model_dir: Path, description_tokenizer_dir: Path, target_language_name: str) -> None:
        self.ui = ui
        self.model_dir = model_dir
        self.description_tokenizer_dir = description_tokenizer_dir
        self.target_language_name = target_language_name
        self.device = choose_tts_device()
        self.dtype = device_dtype(self.device)
        self.model: Optional[Any] = None
        self.prompt_tokenizer: Optional[Any] = None
        self.description_tokenizer: Optional[Any] = None
        self.feature_extractor: Optional[Any] = None
        self.sampling_rate = 44100
        self.frame_rate = 86
        self._lock = threading.Lock()
        self.streaming_supported = ParlerTTSStreamer is not None

    def _load_model_on(self, device: str) -> Any:
        kwargs: dict[str, Any] = {"local_files_only": True}
        if device == "cuda":
            kwargs["torch_dtype"] = torch.float16
            # SDPA is supported by Parler-TTS and is faster than eager attention.
            # If the pinned local stack rejects the kwarg, retry without it.
            try:
                return ParlerTTSForConditionalGeneration.from_pretrained(
                    str(self.model_dir), attn_implementation="sdpa", **kwargs
                ).to(device)
            except (TypeError, ValueError):
                return ParlerTTSForConditionalGeneration.from_pretrained(
                    str(self.model_dir), **kwargs
                ).to(device)
        return ParlerTTSForConditionalGeneration.from_pretrained(
            str(self.model_dir), **kwargs
        ).to(device)

    def load(self) -> None:
        with self._lock:
            if self.model is not None:
                return
            if not self.model_dir.exists():
                raise FileNotFoundError(f"Parler-TTS model directory not found: {self.model_dir}")
            if not self.description_tokenizer_dir.exists():
                raise FileNotFoundError(
                    "Parler-TTS is blocked because the local FLAN-T5 description tokenizer "
                    f"was not found at: {self.description_tokenizer_dir}\n"
                    "Set PARLER_DESCRIPTION_TOKENIZER to the directory containing the FLAN-T5 tokenizer assets."
                )

            self.ui.status(f"Loading Parler-TTS on {self.device}...")
            self.prompt_tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_dir), local_files_only=True
            )
            self.description_tokenizer = AutoTokenizer.from_pretrained(
                str(self.description_tokenizer_dir), local_files_only=True
            )
            self.feature_extractor = AutoFeatureExtractor.from_pretrained(
                str(self.model_dir), local_files_only=True
            )

            try:
                self.model = self._load_model_on(self.device)
            except RuntimeError as exc:
                # A 4-GB-class laptop GPU may not have enough VRAM for the whole
                # local TTS stack. Falling back automatically is better than killing
                # the live app; the user can force a device with BHASHA_TTS_DEVICE.
                if self.device == "cuda" and "out of memory" in str(exc).lower():
                    self.ui.warning("TTS GPU memory is insufficient; falling back to CPU. Set BHASHA_TTS_DEVICE=cpu to silence this warning.")
                    cleanup_torch()
                    self.device = "cpu"
                    self.dtype = torch.float32
                    self.model = self._load_model_on("cpu")
                else:
                    raise

            self.model.eval()
            self.sampling_rate = int(
                getattr(self.feature_extractor, "sampling_rate", None)
                or getattr(self.model.config, "sampling_rate", 44100)
            )
            self.frame_rate = int(
                getattr(self.model.audio_encoder.config, "frame_rate", 86)
            )
            self.streaming_supported = ParlerTTSStreamer is not None
            self.ui.status(
                f"Parler-TTS ready ({self.sampling_rate} Hz, {self.device.upper()}" +
                (", streaming)" if self.streaming_supported else ", full-generation fallback)"))
            
    def _tokenize(self, text: str) -> tuple[Any, Any]:
        if self.description_tokenizer is None or self.prompt_tokenizer is None:
            raise RuntimeError("Parler-TTS tokenizers are not initialized")
        description = tts_description_for(self.target_language_name)
        description_inputs = self.description_tokenizer(
            description, return_tensors="pt", truncation=True, max_length=128
        ).to(self.device)
        prompt_inputs = self.prompt_tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256
        ).to(self.device)
        return description_inputs, prompt_inputs

    def _full_generate(self, text: str) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Parler-TTS model is not loaded")
        description_inputs, prompt_inputs = self._tokenize(text)
        with torch.inference_mode():
            generation = self.model.generate(
                input_ids=description_inputs.input_ids,
                attention_mask=description_inputs.attention_mask,
                prompt_input_ids=prompt_inputs.input_ids,
                prompt_attention_mask=prompt_inputs.attention_mask,
                do_sample=False,
                use_cache=True,
            )
        if hasattr(generation, "sequences"):
            if hasattr(generation, "audios_length") and generation.audios_length is not None:
                length = int(generation.audios_length[0].item())
                waveform = generation.sequences[0, :length]
            else:
                waveform = generation.sequences[0]
        else:
            waveform = generation[0] if getattr(generation, "ndim", 1) > 1 else generation
        return tensor_to_numpy_audio(waveform)

    def synthesize(self, text: str) -> tuple[np.ndarray, int, float]:
        """Compatibility path for diagnostics; live playback uses stream_to_output."""
        self.load()
        started = time.perf_counter()
        sentences = split_sentences(text, max_chars=240)
        parts = [self._full_generate(part) for part in sentences]
        if not parts:
            audio = np.zeros(0, dtype=np.float32)
        else:
            gap = np.zeros(int(self.sampling_rate * 0.02), dtype=np.float32)
            assembled: list[np.ndarray] = []
            for i, piece in enumerate(parts):
                assembled.append(piece)
                if i != len(parts) - 1:
                    assembled.append(gap)
            audio = np.concatenate(assembled).astype(np.float32)
        return audio, self.sampling_rate, max(time.perf_counter() - started, 0.0)

    def _play_callback_audio(
        self,
        audio: np.ndarray,
        source_rate: int,
        output_device: int,
        stop_event: threading.Event,
    ) -> float:
        """Play a complete waveform through callback mode (not blocking write).

        Some Windows WASAPI endpoints report that PortAudio's blocking API is not
        supported.  Callback mode avoids that limitation and is also the mode used
        by the live streamer below.
        """
        if audio.size == 0 or stop_event.is_set():
            return 0.0

        output_rate, channels = get_output_config(output_device, source_rate)
        arr = resample_audio(audio, source_rate, output_rate)
        state = {"pos": 0, "started": time.perf_counter(), "done": False}
        lock = threading.Lock()
        finished = threading.Event()

        def callback(outdata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
            if status:
                pass
            outdata.fill(0.0)
            with lock:
                if stop_event.is_set():
                    finished.set()
                    return
                pos = int(state["pos"])
                remaining = len(arr) - pos
                take = min(frames, max(0, remaining))
                if take > 0:
                    mono = arr[pos:pos + take]
                    if channels == 1:
                        outdata[:take, 0] = mono
                    else:
                        outdata[:take, :] = mono[:, None]
                    state["pos"] = pos + take
                if state["pos"] >= len(arr):
                    finished.set()

        stream = None
        try:
            stream = sd.OutputStream(
                samplerate=output_rate,
                device=output_device,
                channels=channels,
                dtype="float32",
                blocksize=0,
                latency="high",
                callback=callback,
            )
            stream.start()
            while not finished.wait(0.05):
                if stop_event.is_set():
                    break
            return max(time.perf_counter() - state["started"], 0.0)
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    def _play_wav_native_windows(self, audio: np.ndarray, sample_rate: int, stop_event: threading.Event) -> None:
        """Play a short PCM WAV chunk through Windows Media Sound.

        This intentionally bypasses PortAudio/WASAPI for the TTS playback path.
        The user's Windows endpoint previously rejected PortAudio's blocking WASAPI
        path (-9999). winsound uses the Windows multimedia playback path instead.
        """
        if winsound is None:
            raise RuntimeError("Native Windows audio playback is unavailable")
        if stop_event.is_set() or audio.size == 0:
            return

        pcm = io.BytesIO()
        sf.write(pcm, np.asarray(audio, dtype=np.float32), int(sample_rate), format="WAV", subtype="PCM_16")
        wav_bytes = pcm.getvalue()
        # SND_MEMORY accepts the complete in-memory RIFF/WAV payload.
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_SYNC)

    def _play_chunk(self, audio: np.ndarray, sample_rate: int, output_device: int, stop_event: threading.Event, player=None) -> None:
        """Play one generated TTS chunk.

        Preferred Windows path: SoundCard/WASAPI, because it addresses the selected
        physical speaker directly and supports a persistent player for consecutive
        chunks. Native winsound is the second Windows fallback, then sounddevice.
        """
        if stop_event.is_set() or audio.size == 0:
            return

        # If a persistent SoundCard player is supplied, queue this piece onto it.
        if player is not None:
            player.play(np.asarray(audio, dtype=np.float32))
            return

        if winsound is not None and sys.platform.startswith("win"):
            try:
                self._play_wav_native_windows(audio, sample_rate, stop_event)
                return
            except Exception as native_exc:
                self.ui.warning(f"Native Windows TTS playback failed; trying soundcard/sounddevice: {native_exc}")

        output_rate, channels = get_output_config(output_device, sample_rate)
        arr = resample_audio(audio, sample_rate, output_rate)
        if channels == 2:
            arr = np.repeat(arr[:, None], 2, axis=1)
        sd.play(arr, samplerate=output_rate, device=output_device, blocking=True)

    def stream_to_output(
        self,
        text: str,
        output_device: int,
        stop_event: threading.Event,
        on_first_audio: Optional[Callable[[float], None]] = None,
    ) -> float:
        """Generate and play TTS incrementally, using a Windows-native audio path.

        The previous implementation tried to feed Parler chunks into PortAudio's
        WASAPI output stream. The user's machine rejected that route with -9999.
        Here we prefer SoundCard's native WASAPI player for the selected endpoint;
        winsound and sounddevice remain fallbacks.
        """
        self.load()
        started = time.perf_counter()

        # Build a persistent output player when SoundCard is available. SoundCard's
        # player queues successive pieces one after another, which is exactly what
        # the Parler streamer needs for ordered incremental audio.
        sc_speaker = resolve_soundcard_speaker(output_device) if sc is not None else None
        sc_player = None
        sc_rate = self.sampling_rate
        sc_channels = 2
        if sc_speaker is not None:
            available_channels = getattr(sc_speaker, "channels", 2)
            if isinstance(available_channels, int):
                sc_channels = max(1, min(int(available_channels), 2))
            elif isinstance(available_channels, (list, tuple)):
                sc_channels = max(1, min(len(available_channels), 2))

            # Shared WASAPI normally performs the system-side conversion. Try the
            # model's native rate first, then the common Windows 48 kHz rate.
            for rate in (self.sampling_rate, 48000, 44100):
                try:
                    sc_player = sc_speaker.player(
                        samplerate=int(rate),
                        channels=sc_channels,
                        blocksize=1024,
                        exclusive_mode=False,
                    )
                    sc_rate = int(rate)
                    break
                except Exception:
                    sc_player = None

        self.ui.status(
            f"TTS output: {self.sampling_rate} Hz | "
            + (f"SoundCard/WASAPI {sc_rate} Hz / {sc_channels}ch" if sc_player is not None else "fallback playback")
        )

        def play_piece(piece: np.ndarray) -> None:
            nonlocal sc_player
            if stop_event.is_set() or piece.size == 0:
                return
            if sc_player is not None:
                arr = resample_audio(piece, self.sampling_rate, sc_rate)
                if sc_channels == 2:
                    arr = np.repeat(arr[:, None], 2, axis=1)
                else:
                    arr = arr.reshape(-1, 1)
                sc_player.play(arr)
            else:
                self._play_chunk(piece, self.sampling_rate, output_device, stop_event)

        if self.streaming_supported and self.model is not None:
            streamer = ParlerTTSStreamer(
                self.model,
                device=self.device,
                play_steps=max(1, int(self.frame_rate * TTS_STREAM_CHUNK_S)),
                timeout=0.5,
            )
            description_inputs, prompt_inputs = self._tokenize(text)
            generation_error: list[BaseException] = []
            generation_finished = threading.Event()
            first_audio = False

            generation_kwargs = dict(
                input_ids=description_inputs.input_ids,
                attention_mask=description_inputs.attention_mask,
                prompt_input_ids=prompt_inputs.input_ids,
                prompt_attention_mask=prompt_inputs.attention_mask,
                streamer=streamer,
                do_sample=False,
                use_cache=True,
                min_new_tokens=10,
            )

            def generate_target() -> None:
                try:
                    with torch.inference_mode():
                        self.model.generate(**generation_kwargs)
                except BaseException as exc:
                    generation_error.append(exc)
                finally:
                    generation_finished.set()

            worker = threading.Thread(target=generate_target, name="parler-generate", daemon=True)
            worker.start()
            player_cm = None
            try:
                # Enter the SoundCard player only after all validation is done.
                if sc_speaker is not None and sc_player is not None:
                    player_cm = sc_player
                    player_cm.__enter__()

                while not stop_event.is_set():
                    try:
                        new_audio = next(streamer)
                    except queue.Empty:
                        if generation_error:
                            raise generation_error[0]
                        if generation_finished.is_set():
                            break
                        continue
                    except StopIteration:
                        break

                    piece = tensor_to_numpy_audio(new_audio)
                    if piece.size == 0:
                        if generation_finished.is_set():
                            break
                        continue
                    if not first_audio:
                        first_audio = True
                        if on_first_audio is not None:
                            on_first_audio(time.perf_counter() - started)
                    play_piece(piece)

                worker.join(timeout=5.0)
                if generation_error:
                    raise generation_error[0]
                return max(time.perf_counter() - started, 0.0)
            except Exception as stream_exc:
                self.ui.warning(
                    f"Streaming TTS path failed ({stream_exc}); falling back to full-generation TTS."
                )
                cleanup_torch()
                if stop_event.is_set():
                    return max(time.perf_counter() - started, 0.0)
            finally:
                if player_cm is not None:
                    try:
                        player_cm.__exit__(None, None, None)
                    except Exception:
                        pass

        # Compatibility fallback: use the documented direct model.generate path.
        audio = self._full_generate(text)
        if audio.size and not stop_event.is_set():
            if on_first_audio is not None:
                on_first_audio(time.perf_counter() - started)
            if sc_speaker is not None:
                # Open a short-lived player using the model rate if possible.
                try:
                    rate = self.sampling_rate
                    ch = sc_channels
                    with sc_speaker.player(samplerate=rate, channels=ch, blocksize=1024, exclusive_mode=False) as player:
                        arr = audio
                        if ch == 2:
                            arr = np.repeat(arr[:, None], 2, axis=1)
                        else:
                            arr = arr.reshape(-1, 1)
                        player.play(arr)
                except Exception:
                    self._play_chunk(audio, self.sampling_rate, output_device, stop_event)
            else:
                self._play_chunk(audio, self.sampling_rate, output_device, stop_event)
        return max(time.perf_counter() - started, 0.0)


# -----------------------------
# Audio capture / segmentation
# -----------------------------

class MicrophoneSegmenter:
    def __init__(
        self,
        input_device: int,
        callback_queue: queue.Queue,
        segment_queue: queue.Queue,
        ui: "UIBridge",
        stop_event: threading.Event,
    ) -> None:
        self.input_device = input_device
        self.callback_queue = callback_queue
        self.segment_queue = segment_queue
        self.ui = ui
        self.stop_event = stop_event
        self.thread = threading.Thread(target=self._run, name="segmenter", daemon=True)
        self.stream: Optional[sd.InputStream] = None
        self.sequence = 0
        self.input_rate = self._query_input_rate()
        self.block_frames = max(1, int(round(self.input_rate * BLOCK_MS / 1000.0)))

    def _query_input_rate(self) -> int:
        info = sd.query_devices(self.input_device, "input")
        rate = int(round(float(info["default_samplerate"])))
        return rate if rate > 0 else AUDIO_RATE

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            self.ui.warning(f"Audio input status: {status}")
        try:
            self.callback_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            self.ui.warning("Microphone input queue is full; dropping an audio block")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stop_event.set()
        self.thread.join(timeout=1.5)

    def _emit_audio(self, audio: np.ndarray, start_at: float) -> None:
        if audio.size == 0:
            return
        audio = np.asarray(audio, dtype=np.float32)
        duration_s = len(audio) / AUDIO_RATE
        if duration_s * 1000.0 < MIN_UTTERANCE_MS:
            return
        self.sequence += 1
        ended = time.perf_counter()
        seg = SpeechSegment(
            sequence_id=self.sequence,
            audio=audio,
            sample_rate=AUDIO_RATE,
            created_at=start_at,
            ended_at=ended,
            duration_s=duration_s,
        )
        try:
            self.segment_queue.put(seg, timeout=0.5)
            self.ui.segment_created(seg)
        except queue.Full:
            self.ui.warning("Speech queue is full. The system is behind real-time processing.")

    def _emit_segment(self, chunks: list[np.ndarray], start_at: float) -> None:
        if chunks:
            self._emit_audio(np.concatenate(chunks).astype(np.float32), start_at)

    def _find_live_boundary(self, audio: np.ndarray) -> int:
        # Look for a low-energy pocket near the end of the live chunk. If one is
        # present, cut there; otherwise cut at the chunk end. This reduces the
        # chance of splitting exactly inside a phoneme while still avoiding a long
        # wait for sentence-final silence.
        min_len = int(AUDIO_RATE * LIVE_MIN_CHUNK_MS / 1000.0)
        if len(audio) < min_len:
            return len(audio)
        search_len = min(len(audio), int(AUDIO_RATE * BOUNDARY_SEARCH_MS / 1000.0))
        start = len(audio) - search_len
        window = int(AUDIO_RATE * 0.06)
        step = max(1, int(AUDIO_RATE * 0.03))
        best_idx = len(audio)
        best_db = 1e9
        threshold = START_DB + 4.0
        for i in range(start, len(audio) - window + 1, step):
            db = rms_db(audio[i:i + window])
            if db < best_db:
                best_db = db
                best_idx = i + window
        if best_db <= threshold and best_idx >= min_len:
            return best_idx
        return len(audio)

    def _run(self) -> None:
        preroll_blocks = max(1, int(round(PRE_ROLL_MS / BLOCK_MS)))
        preroll: deque[np.ndarray] = deque(maxlen=preroll_blocks)
        speech_chunks: list[np.ndarray] = []
        speech_active = False
        start_hold = 0.0
        silence_ms = 0.0
        utterance_ms = 0.0
        speech_start_at = 0.0
        noise_floor = START_DB - 10.0

        self.ui.status(f"Starting microphone stream at {self.input_rate} Hz...")
        try:
            self.stream = sd.InputStream(
                samplerate=self.input_rate,
                blocksize=self.block_frames,
                device=self.input_device,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            with self.stream:
                self.ui.status("Listening... speak naturally")
                while not self.stop_event.is_set():
                    try:
                        raw = self.callback_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    chunk = resample_to_16k(raw, self.input_rate)
                    if chunk.size == 0:
                        continue
                    preroll.append(chunk)

                    db = rms_db(chunk)
                    threshold_start = max(START_DB, noise_floor + SPEECH_OFFSET_DB)
                    threshold_continue = max(START_DB - 4.0, noise_floor + SILENCE_OFFSET_DB)

                    if not speech_active:
                        noise_floor = (1.0 - NOISE_EMA) * noise_floor + NOISE_EMA * min(db, START_DB)
                        if db >= threshold_start:
                            start_hold += BLOCK_MS
                        else:
                            start_hold = 0.0

                        if start_hold >= START_HOLD_MS:
                            speech_active = True
                            silence_ms = 0.0
                            utterance_ms = 0.0
                            speech_start_at = time.perf_counter() - max(0.0, start_hold / 1000.0)
                            speech_chunks = list(preroll)
                            utterance_ms = sum(len(x) for x in speech_chunks) / AUDIO_RATE * 1000.0
                            self.ui.status("Speaking detected...")
                    else:
                        speech_chunks.append(chunk)
                        utterance_ms += BLOCK_MS
                        if db >= threshold_continue:
                            silence_ms = 0.0
                        else:
                            silence_ms += BLOCK_MS

                        if silence_ms >= END_SILENCE_MS:
                            self._emit_segment(speech_chunks, speech_start_at or time.perf_counter())
                            speech_chunks = []
                            speech_active = False
                            start_hold = 0.0
                            silence_ms = 0.0
                            utterance_ms = 0.0
                            speech_start_at = 0.0
                            preroll.clear()
                            self.ui.status("Listening...")
                        elif utterance_ms >= MAX_UTTERANCE_MS:
                            # LIVE MODE: emit a partial phrase even though the speaker
                            # has not stopped. Keep listening immediately so the next
                            # phrase can enter STT while this one reaches TTS.
                            combined = np.concatenate(speech_chunks).astype(np.float32)
                            cut = self._find_live_boundary(combined)
                            self._emit_audio(combined[:cut], speech_start_at or time.perf_counter())
                            remainder = combined[cut:]
                            speech_chunks = [remainder] if remainder.size else []
                            utterance_ms = len(remainder) / AUDIO_RATE * 1000.0
                            speech_start_at = time.perf_counter() - utterance_ms / 1000.0
                            silence_ms = 0.0
                            self.ui.status("Live chunk sent → still listening...")

                # Flush a final active utterance on shutdown.
                if speech_active and speech_chunks:
                    self._emit_segment(speech_chunks, speech_start_at or time.perf_counter())
        except Exception as exc:
            self.ui.error(f"Microphone error: {exc}")
        finally:
            self.stream = None


# -----------------------------
# Pipeline controller
# -----------------------------

class Pipeline:
    def __init__(
        self,
        ui: "UIBridge",
        source: Language,
        target: Language,
        input_device: int,
        output_device: int,
    ) -> None:
        self.ui = ui
        self.source = source
        self.target = target
        self.input_device = input_device
        self.output_device = output_device

        self.stop_event = threading.Event()
        self.input_blocks: queue.Queue[np.ndarray] = queue.Queue(maxsize=MAX_INPUT_QUEUE)
        self.segment_queue: queue.Queue[SpeechSegment] = queue.Queue(maxsize=MAX_STAGE_QUEUE)
        self.stt_queue: queue.Queue[TextJob] = queue.Queue(maxsize=MAX_STAGE_QUEUE)
        self.translation_queue: queue.Queue[TranslationJob] = queue.Queue(maxsize=MAX_STAGE_QUEUE)
        self.playback_queue: queue.Queue[AudioJob] = queue.Queue(maxsize=MAX_STAGE_QUEUE)

        self.ui_thread = threading.Thread(target=self._ui_stats_loop, name="stats", daemon=True)
        self.threads: list[threading.Thread] = []

        self.whisper = WhisperEngine(STT_DIR, ui)
        self.translation = IndicTranslationEngine(ui, source, target)
        self.tts = ParlerTTSEngine(ui, TTS_DIR, PARLER_DESCRIPTION_TOKENIZER, target.name)
        self.segmenter: Optional[MicrophoneSegmenter] = None

        self.ready = False
        self.starting = False
        self.started_at: Optional[float] = None

        self.metrics_lock = threading.Lock()
        self.last_latency: Optional[float] = None
        self.last_stt: Optional[float] = None
        self.last_translation: Optional[float] = None
        self.last_tts: Optional[float] = None

    def validate(self) -> None:
        missing = [
            p for p in [STT_DIR, EN_INDIC_DIR, INDIC_EN_DIR, INDIC_INDIC_DIR, TTS_DIR]
            if not p.exists()
        ]
        if missing:
            joined = "\n".join(str(p) for p in missing)
            raise FileNotFoundError(f"Required model directories are missing:\n{joined}")
        if not PARLER_DESCRIPTION_TOKENIZER.exists():
            raise FileNotFoundError(
                "Missing Parler FLAN-T5 description tokenizer: "
                f"{PARLER_DESCRIPTION_TOKENIZER}\n"
                "Provision it locally as described in the BhashaSaathi handoff, or "
                "set PARLER_DESCRIPTION_TOKENIZER."
            )

        if self.source.name == "Santali (experimental)" and self.source.whisper_code is None:
            self.ui.warning(
                "Santali STT is marked experimental: Whisper language is left on auto-detect. "
                "This matches the current local-model handoff and should be validated with real audio."
            )
        if self.target.name == self.source.name:
            self.ui.warning("Source and target are the same language: translation will be bypassed.")
        if self.target.name == "Punjabi":
            self.ui.warning("Punjabi is not an official language for this Indic Parler-TTS fine-tuned checkpoint; TTS may be experimental.")

    def prepare_models(self) -> None:
        self.starting = True
        self.ui.status("Preparing local models. First startup can take time...")
        try:
            self.validate()
            # Sequential loading is deliberate: it reduces peak RAM/VRAM spikes on a
            # laptop and is safer than loading all 3 large models concurrently.
            self.whisper.load()
            self.translation.load()
            self.tts.load()
            self.ready = True
            self.ui.status("Models ready. Starting microphone...")
        except Exception as exc:
            self.ready = False
            self.stop_event.set()
            self.ui.error(self.format_exception(exc))
            self.ui.stopped()
        finally:
            self.starting = False

    def start(self) -> None:
        if self.starting or self.ready:
            return
        thread = threading.Thread(target=self._start_async, name="bootstrap", daemon=True)
        thread.start()

    def _start_async(self) -> None:
        self.prepare_models()
        if not self.ready or self.stop_event.is_set():
            return

        self.started_at = time.perf_counter()
        self.threads = [
            threading.Thread(target=self._stt_worker, name="stt-worker", daemon=True),
            threading.Thread(target=self._translation_worker, name="translation-worker", daemon=True),
            threading.Thread(target=self._tts_worker, name="tts-worker", daemon=True),
        ]
        for t in self.threads:
            t.start()

        self.segmenter = MicrophoneSegmenter(
            input_device=self.input_device,
            callback_queue=self.input_blocks,
            segment_queue=self.segment_queue,
            ui=self.ui,
            stop_event=self.stop_event,
        )
        self.segmenter.start()
        self.ui.started()
        self.ui_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.segmenter is not None:
            self.segmenter.stop()
        try:
            sd.stop()
        except Exception:
            pass
        self._drain(self.input_blocks)
        self._drain(self.segment_queue)
        self._drain(self.stt_queue)
        self._drain(self.translation_queue)
        self._drain(self.playback_queue)
        for t in self.threads:
            t.join(timeout=1.0)
        if self.ui_thread.is_alive():
            self.ui_thread.join(timeout=0.5)
        self.ui.stopped()

    @staticmethod
    def _drain(q: queue.Queue) -> None:
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                return

    def _stt_worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                segment = self.segment_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                lang = self.source.whisper_code
                transcript, detected, probability, elapsed = self.whisper.transcribe(segment.audio, lang)
                if not transcript.strip():
                    self.ui.warning(f"Segment {segment.sequence_id}: speech was detected but STT returned empty text")
                    continue
                self.ui.transcript(segment.sequence_id, transcript, detected, probability)
                queued = False
                while not self.stop_event.is_set() and not queued:
                    try:
                        self.stt_queue.put(
                            TextJob(
                                segment=segment,
                                transcript=transcript,
                                detected_language=detected,
                                language_probability=probability,
                                stt_time_s=elapsed,
                            ),
                            timeout=0.25,
                        )
                        queued = True
                    except queue.Full:
                        self.ui.status("STT queue full — waiting for translation stage...")
            except Exception as exc:
                self.ui.error(f"STT failed for segment {getattr(segment, 'sequence_id', '?')}: {exc}")

    def _translation_worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.stt_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                translated, elapsed = self.translation.translate(job.transcript)
                self.ui.translation(job.segment.sequence_id, translated)
                queued = False
                while not self.stop_event.is_set() and not queued:
                    try:
                        self.translation_queue.put(
                            TranslationJob(
                                segment=job.segment,
                                transcript=job.transcript,
                                translated_text=translated,
                                stt_time_s=job.stt_time_s,
                                translation_time_s=elapsed,
                            ),
                            timeout=0.25,
                        )
                        queued = True
                    except queue.Full:
                        self.ui.status("Translation queue full — waiting for TTS stage...")
            except Exception as exc:
                self.ui.error(
                    f"Translation failed for segment {getattr(job.segment, 'sequence_id', '?')}: {exc}"
                )

    def _tts_worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.translation_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                started = time.perf_counter()
                first_audio_delay: list[float] = []

                def mark_first_audio(delay: float) -> None:
                    first_audio_delay.append(delay)
                    self.ui.first_audio(job.segment.sequence_id, delay)

                elapsed = self.tts.stream_to_output(
                    job.translated_text,
                    self.output_device,
                    self.stop_event,
                    on_first_audio=mark_first_audio,
                )
                wall = max(time.perf_counter() - started, 0.0)
                with self.metrics_lock:
                    self.last_latency = wall + (job.segment.ended_at - job.segment.created_at)
                    self.last_stt = job.stt_time_s
                    self.last_translation = job.translation_time_s
                    self.last_tts = elapsed
                self.ui.played(job.segment.sequence_id)
                self.ui.status("Listening... speak naturally")
            except Exception as exc:
                self.ui.error(f"TTS failed for segment {getattr(job.segment, 'sequence_id', '?')}: {exc}")

    def _playback_worker(self) -> None:
        # Kept for compatibility with older pipeline state; live TTS now streams
        # directly into the selected output device, preserving FIFO through the
        # single TTS worker.
        while not self.stop_event.is_set():
            time.sleep(0.2)

    def _ui_stats_loop(self) -> None:
        while not self.stop_event.is_set():
            with self.metrics_lock:
                latency = self.last_latency
            self.ui.metrics(
                segment_q=self.segment_queue.qsize(),
                stt_q=self.stt_queue.qsize(),
                translation_q=self.translation_queue.qsize(),
                tts_q=self.playback_queue.qsize(),
                latency=latency,
            )
            time.sleep(0.2)

    @staticmethod
    def format_exception(exc: BaseException) -> str:
        return "\n".join(
            [
                f"{type(exc).__name__}: {exc}",
                "",
                "Traceback (most recent call last):",
                traceback.format_exc().strip(),
            ]
        )


# -----------------------------
# UI bridge
# -----------------------------

class UIBridge:
    """Thread-safe bridge from background workers to Tkinter."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._pipeline: Optional[Pipeline] = None
        self.running = False

        self.source_var = tk.StringVar(value="Hindi")
        self.target_var = tk.StringVar(value="English")
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.latency_var = tk.StringVar(value="—")
        self.queue_var = tk.StringVar(value="STT 0  •  TXT 0  •  TTS 0")
        self.sequence_var = tk.StringVar(value="—")
        self.device_var = tk.StringVar(value="CPU")

        self.transcript_text = tk.StringVar(value="Waiting for speech...")
        self.translation_text = tk.StringVar(value="Waiting for translation...")

        self._build()
        self.root.after(100, self._poll_events)

    def _build(self) -> None:
        self.root.title(f"{APP_NAME} — Real-Time Local Translator")
        self.root.geometry("1100x760")
        self.root.minsize(980, 700)
        self.root.configure(bg="#0b1020")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#0b1020")
        style.configure("Card.TFrame", background="#11182d")
        style.configure("TLabel", background="#0b1020", foreground="#e9eefb", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"), foreground="#ffffff", background="#0b1020")
        style.configure("Muted.TLabel", font=("Segoe UI", 9), foreground="#9aa7c0", background="#0b1020")
        style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"), foreground="#ffffff", background="#11182d")
        style.configure("Big.TLabel", font=("Segoe UI", 17, "bold"), foreground="#ffffff", background="#11182d")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10)
        style.configure("Green.TButton", font=("Segoe UI", 11, "bold"), padding=12)
        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), padding=10)
        style.configure("TCombobox", padding=6)

        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=20, pady=18)

        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="BhashaSaathi", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="Local • Offline-first • Real-time voice translation", style="Muted.TLabel").pack(
            side="left", padx=18, pady=(8, 0)
        )
        ttk.Label(top, textvariable=self.device_var, style="Muted.TLabel").pack(side="right", pady=(8, 0))

        controls = ttk.Frame(outer, style="Card.TFrame", padding=18)
        controls.pack(fill="x", pady=(18, 14))

        row1 = ttk.Frame(controls, style="Card.TFrame")
        row1.pack(fill="x")
        self._field(row1, "SPEAKING LANGUAGE", self.source_var, 0)
        self._field(row1, "LISTENER LANGUAGE", self.target_var, 1)

        swap_btn = ttk.Button(row1, text="⇄  Swap", command=self.swap_languages)
        swap_btn.grid(row=0, column=2, rowspan=2, padx=12, pady=18, sticky="nsew")

        row2 = ttk.Frame(controls, style="Card.TFrame")
        row2.pack(fill="x", pady=(12, 0))
        self._device_field(row2, "MICROPHONE INPUT", self.input_var, 0, input_mode=True)
        self._device_field(row2, "EARPHONES OUTPUT", self.output_var, 1, input_mode=False)

        hint = ttk.Label(
            controls,
            text=(
                "Recommended demo wiring: laptop/external mic as INPUT + wired/Bluetooth earphones as OUTPUT. "
                "Do not use the earbud microphone. TTS on Windows uses native WAV playback to avoid WASAPI blocking-mode conflicts."
            ),
            style="Muted.TLabel",
            wraplength=980,
        )
        hint.pack(fill="x", pady=(12, 0))

        action = ttk.Frame(outer)
        action.pack(fill="x", pady=(0, 14))
        self.start_btn = ttk.Button(action, text="●  START TRANSLATION", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(action, text="■  STOP", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        ttk.Button(action, text="↻  Refresh Devices", command=self.refresh_devices).pack(side="left")
        ttk.Button(action, text="Test TTS", command=self.test_tts).pack(side="right", padx=8)
        ttk.Button(action, text="Test Output", command=self.test_output).pack(side="right")

        status_bar = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
        status_bar.pack(fill="x", pady=(0, 14))
        ttk.Label(status_bar, text="STATUS", style="Muted.TLabel").pack(side="left")
        ttk.Label(status_bar, textvariable=self.status_var, style="CardTitle.TLabel").pack(side="left", padx=14)
        ttk.Label(status_bar, text="Latency", style="Muted.TLabel").pack(side="right", padx=(20, 5))
        ttk.Label(status_bar, textvariable=self.latency_var, style="CardTitle.TLabel").pack(side="right")
        ttk.Label(status_bar, text="Queues", style="Muted.TLabel").pack(side="right", padx=(20, 5))
        ttk.Label(status_bar, textvariable=self.queue_var, style="CardTitle.TLabel").pack(side="right")

        center = ttk.Frame(outer)
        center.pack(fill="both", expand=True)
        center.columnconfigure(0, weight=1)
        center.columnconfigure(1, weight=1)
        center.rowconfigure(0, weight=1)

        self._big_card(
            center,
            "WHAT WAS HEARD",
            "Microphone → Whisper STT",
            self.transcript_text,
            0,
        )
        self._big_card(
            center,
            "WHAT THE OTHER PERSON HEARS",
            "IndicTrans2 → Parler-TTS",
            self.translation_text,
            1,
        )

        bottom = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
        bottom.pack(fill="x", pady=(14, 0))
        ttk.Label(bottom, text="Pipeline", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(
            bottom,
            text="Mic → VAD → live chunks → STT → Translation → streaming TTS → Earphones",
            style="Muted.TLabel",
        ).pack(side="left", padx=15)
        ttk.Label(bottom, textvariable=self.sequence_var, style="Muted.TLabel").pack(side="right")

        self.refresh_devices(initial=True)
        self.device_var.set(f"Model compute: {choose_compute_device().upper()}")

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, col: int) -> None:
        box = ttk.Frame(parent, style="Card.TFrame")
        box.grid(row=0, column=col, padx=(0 if col == 0 else 12, 0), sticky="ew")
        parent.columnconfigure(col, weight=1)
        ttk.Label(box, text=label, style="Muted.TLabel").pack(anchor="w")
        combo = ttk.Combobox(box, textvariable=variable, values=LANGUAGE_NAMES, state="readonly", width=28)
        combo.pack(fill="x", pady=(5, 0))
        if variable.get() in LANGUAGE_NAMES:
            combo.set(variable.get())

    def _device_field(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        col: int,
        input_mode: bool,
    ) -> None:
        box = ttk.Frame(parent, style="Card.TFrame")
        box.grid(row=0, column=col, padx=(0 if col == 0 else 12, 0), sticky="ew")
        parent.columnconfigure(col, weight=1)
        ttk.Label(box, text=label, style="Muted.TLabel").pack(anchor="w")
        combo = ttk.Combobox(box, textvariable=variable, state="readonly", width=50)
        combo.pack(fill="x", pady=(5, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: None)
        if input_mode:
            self.input_combo = combo
        else:
            self.output_combo = combo

    def _big_card(
        self,
        parent: ttk.Frame,
        title: str,
        subtitle: str,
        variable: tk.StringVar,
        col: int,
    ) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=20)
        card.grid(row=0, column=col, padx=(0, 7) if col == 0 else (7, 0), sticky="nsew")
        ttk.Label(card, text=title, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(card, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(4, 14))
        ttk.Label(card, textvariable=variable, style="Big.TLabel", wraplength=470, justify="left").pack(
            anchor="nw", fill="both", expand=True
        )

    # ---- UI event methods ----

    def status(self, text: str) -> None:
        self.events.put(("status", text))

    def warning(self, text: str) -> None:
        self.events.put(("warning", text))

    def error(self, text: str) -> None:
        self.events.put(("error", text))

    def started(self) -> None:
        self.events.put(("started", None))

    def stopped(self) -> None:
        self.events.put(("stopped", None))

    def segment_created(self, seg: SpeechSegment) -> None:
        self.events.put(("segment", seg.sequence_id))

    def transcript(self, seq: int, text: str, detected: str, probability: float) -> None:
        self.events.put(("transcript", (seq, text, detected, probability)))

    def translation(self, seq: int, text: str) -> None:
        self.events.put(("translation", (seq, text)))

    def ready_for_playback(self, seq: int, latency: float) -> None:
        self.events.put(("ready", (seq, latency)))

    def first_audio(self, seq: int, delay: float) -> None:
        self.events.put(("first_audio", (seq, delay)))

    def played(self, seq: int) -> None:
        self.events.put(("played", seq))

    def metrics(self, **values: Any) -> None:
        self.events.put(("metrics", values))

    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                if event == "status":
                    self.status_var.set(str(payload))
                elif event == "warning":
                    self.status_var.set(f"⚠ {payload}")
                elif event == "error":
                    self.status_var.set("ERROR")
                    self._show_error(str(payload))
                elif event == "started":
                    self.running = True
                    self.start_btn.configure(state="disabled")
                    self.stop_btn.configure(state="normal")
                elif event == "stopped":
                    self.running = False
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status_var.set("Stopped")
                elif event == "segment":
                    self.sequence_var.set(f"Segment #{payload}")
                elif event == "transcript":
                    seq, text, detected, prob = payload
                    detail = f"\n\nWhisper: {detected or 'auto'} ({prob:.0%})"
                    self.transcript_text.set(text + detail)
                    self.sequence_var.set(f"Segment #{seq}")
                elif event == "translation":
                    seq, text = payload
                    self.translation_text.set(text)
                    self.sequence_var.set(f"Segment #{seq}")
                elif event == "ready":
                    seq, latency = payload
                    self.latency_var.set(f"{latency:.2f}s")
                    self.sequence_var.set(f"Segment #{seq} ready → FIFO playback")
                elif event == "first_audio":
                    seq, delay = payload
                    self.latency_var.set(f"first audio {delay:.2f}s")
                    self.sequence_var.set(f"Segment #{seq}: first audio playing")
                elif event == "played":
                    self.sequence_var.set(f"Segment #{payload} played")
                elif event == "metrics":
                    v = payload
                    self.queue_var.set(
                        f"STT {v['segment_q']} • TXT {v['stt_q']} • "
                        f"TTS {v['translation_q']} • PLAY live"
                    )
                    if v.get("latency") is not None:
                        self.latency_var.set(f"{float(v['latency']):.2f}s")
            except Exception:
                pass
        self.root.after(100, self._poll_events)

    def start(self) -> None:
        if self.running:
            return
        source_name = self.source_var.get().strip()
        target_name = self.target_var.get().strip()
        input_label = self.input_var.get().strip()
        output_label = self.output_var.get().strip()

        if source_name not in LANGUAGES or target_name not in LANGUAGES:
            messagebox.showerror(APP_NAME, "Select valid source and target languages.")
            return
        input_index = find_device_index(input_label)
        output_index = find_device_index(output_label)
        if input_index is None or output_index is None:
            messagebox.showerror(APP_NAME, "Select both a microphone input and earphones output.")
            return

        if input_index == output_index:
            answer = messagebox.askyesno(
                APP_NAME,
                "Input and output are the same physical device. This can cause feedback. Continue?",
            )
            if not answer:
                return

        source = LANGUAGES[source_name]
        target = LANGUAGES[target_name]
        self.transcript_text.set("Listening for speech...")
        self.translation_text.set("Translation will appear here...")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("Starting...")

        self._pipeline = Pipeline(
            ui=self,
            source=source,
            target=target,
            input_device=input_index,
            output_device=output_index,
        )
        self._pipeline.start()

    def stop(self) -> None:
        if self._pipeline is not None:
            pipeline = self._pipeline
            self._pipeline = None
            threading.Thread(target=pipeline.stop, name="pipeline-stop", daemon=True).start()
        else:
            self.stopped()

    def swap_languages(self) -> None:
        if self.running or (self._pipeline is not None and self._pipeline.starting):
            messagebox.showinfo(APP_NAME, "Stop the current translation before swapping languages.")
            return
        a = self.source_var.get()
        b = self.target_var.get()
        self.source_var.set(b)
        self.target_var.set(a)

    def refresh_devices(self, initial: bool = False) -> None:
        try:
            inputs, outputs = list_audio_devices()
        except Exception as exc:
            self.status_var.set(f"Audio devices unavailable: {exc}")
            return

        in_values = [label for _, label in inputs]
        out_values = [label for _, label in outputs]
        self.input_combo["values"] = in_values
        self.output_combo["values"] = out_values

        def first_matching(values: list[str], predicate: Callable[[str], bool]) -> str:
            for v in values:
                if predicate(v):
                    return v
            return values[0] if values else ""

        if initial:
            # Prefer OS default INPUT, then a physical microphone. Prefer a normal
            # stereo/headphone OUTPUT, avoiding Bluetooth Hands-Free profiles.
            default_input = first_matching(
                in_values,
                lambda v: "DEFAULT IN" in v and not _is_likely_virtual_or_loopback(v),
            )
            if not default_input:
                default_input = first_matching(in_values, lambda v: _preferred_input_name(v))
            default_output = first_matching(out_values, lambda v: "DEFAULT OUT" in v and _preferred_output_name(v))
            if not default_output:
                default_output = first_matching(out_values, lambda v: _preferred_output_name(v))
            self.input_var.set(default_input)
            self.output_var.set(default_output)
        else:
            if self.input_var.get() not in in_values:
                self.input_var.set(in_values[0] if in_values else "")
            if self.output_var.get() not in out_values:
                self.output_var.set(out_values[0] if out_values else "")
        self.status_var.set("Ready")

    def test_output(self) -> None:
        idx = find_device_index(self.output_var.get())
        if idx is None:
            messagebox.showwarning(APP_NAME, "Select an output device first.")
            return
        try:
            fs = get_output_sample_rate(idx, 44100)
        except Exception as exc:
            self._show_error(f"Output device sample-rate check failed: {exc}")
            return
        duration = 0.5
        t = np.arange(int(fs * duration), dtype=np.float32) / fs
        tone = 0.08 * np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
        try:
            sd.play(tone, samplerate=fs, device=idx, blocking=False)
            self.status_var.set("Output test: 440 Hz tone")
        except Exception as exc:
            self._show_error(f"Output test failed: {exc}")

    def test_tts(self) -> None:
        """Generate and play a short local TTS sample without microphone/STT/translation."""
        if self.running:
            messagebox.showinfo(APP_NAME, "Stop the live translator before running the isolated TTS test.")
            return
        output_index = find_device_index(self.output_var.get())
        if output_index is None:
            messagebox.showwarning(APP_NAME, "Select an output device first.")
            return

        target_name = self.target_var.get().strip() or "Hindi"
        target = LANGUAGES.get(target_name, LANGUAGES["Hindi"])
        self.status_var.set("Running isolated Parler-TTS test...")

        def run() -> None:
            try:
                engine = ParlerTTSEngine(self, TTS_DIR, PARLER_DESCRIPTION_TOKENIZER, target.name)
                engine.load()
                sample_text = {
                    "Hindi": "नमस्ते, यह भाषा साथी का परीक्षण है।",
                    "English": "Hello, this is a BhashaSaathi TTS test.",
                    "Marathi": "नमस्कार, हा भाषा साथीचा आवाज चाचणी संदेश आहे.",
                }.get(target.name, "नमस्ते, यह भाषा साथी का परीक्षण है।")
                elapsed = engine.stream_to_output(
                    sample_text,
                    output_index,
                    threading.Event(),
                    on_first_audio=lambda d: self.status(f"TTS first audio: {d:.2f}s"),
                )
                self.status(f"TTS test complete: {elapsed:.2f}s")
            except Exception as exc:
                self.error(Pipeline.format_exception(exc))

        threading.Thread(target=run, name="tts-test", daemon=True).start()

    def _show_error(self, text: str) -> None:
        # Keep very large tracebacks out of the modal message box title area.
        messagebox.showerror(APP_NAME, text[:6000])

    def _on_close(self) -> None:
        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            except Exception:
                pass
        self.root.destroy()


# -----------------------------
# Diagnostics / CLI
# -----------------------------


def print_environment() -> None:
    print("=== BhashaSaathi environment ===")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Transformers: __check at runtime__")
    try:
        import transformers
        print(f"transformers: {transformers.__version__}")
    except Exception:
        pass
    print(f"Torch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        try:
            p = torch.cuda.get_device_properties(0)
            print(f"GPU: {p.name} / VRAM {p.total_memory / (1024**3):.1f} GB")
        except Exception:
            pass
    print(f"Model compute choice: {choose_compute_device()}")
    print(f"Whisper device/compute: {choose_whisper_device()}")
    print(f"SoundCard available: {sc is not None}")
    print(f"Model root: {MODEL_ROOT}")
    for p in [STT_DIR, EN_INDIC_DIR, INDIC_EN_DIR, INDIC_INDIC_DIR, TTS_DIR, PARLER_DESCRIPTION_TOKENIZER]:
        print(f"{'OK ' if p.exists() else 'MISS'} {p}")


def list_devices_cli() -> None:
    print("=== Audio devices ===")
    try:
        default_in, default_out = sd.default.device
        print(f"Windows/PortAudio default input index : {default_in}")
        print(f"Windows/PortAudio default output index: {default_out}")
    except Exception:
        default_in = default_out = None
    print()
    for idx, d in enumerate(sd.query_devices()):
        role = _device_role_tag(d)
        flags = []
        if default_in is not None and idx == int(default_in):
            flags.append("DEFAULT-IN")
        if default_out is not None and idx == int(default_out):
            flags.append("DEFAULT-OUT")
        if int(d.get("max_input_channels", 0)) > 0 and _is_likely_virtual_or_loopback(str(d.get("name", ""))):
            flags.append("AVOID-VIRTUAL/LOOPBACK")
        print(
            f"{idx}: {d['name']} | {role} | SR={d['default_samplerate']}"
            + (f" | {' '.join(flags)}" if flags else "")
        )


def launch_gui() -> None:
    root = tk.Tk()
    UIBridge(root)
    root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BhashaSaathi local real-time voice translator")
    parser.add_argument("--devices", action="store_true", help="List PortAudio input/output devices and exit")
    parser.add_argument("--check", action="store_true", help="Print environment and model-path diagnostics and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.devices:
        list_devices_cli()
        return
    if args.check:
        print_environment()
        return
    launch_gui()


if __name__ == "__main__":
    main()
