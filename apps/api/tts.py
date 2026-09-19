from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import soundcard as sc
import torch
from scipy.signal import resample_poly
from transformers import AutoTokenizer
from parler_tts import ParlerTTSForConditionalGeneration


ROOT = Path(__file__).resolve().parent
TTS_DIR = ROOT / "models" / "tts" / "indic-parler-tts"
FLAN_DIR = ROOT / "models" / "tts" / "flan-t5-large"

TEXT = "नमस्ते, यह भाषा साथी का परीक्षण है।"

# Use TTS_DEVICE=cpu to force CPU, or TTS_DEVICE=cuda to force CUDA.
DEVICE = os.getenv("TTS_DEVICE", "cuda" if torch.cuda.is_available() else "cpu").lower()

DESCRIPTION = (
    "Rohit's voice is clear and natural, speaking at a moderate pace "
    "with clear pronunciation and very clear audio in a close-sounding recording."
)


def pick_speaker():
    speakers = sc.all_speakers()
    print("\n=== SoundCard speakers ===")
    for i, sp in enumerate(speakers):
        try:
            print(f"[{i}] {sp.name}")
        except Exception:
            print(f"[{i}] <unnamed speaker>")

    # Prefer the user's physical headphones if present.
    for sp in speakers:
        name = str(getattr(sp, "name", "")).lower()
        if "headphones" in name or "boult" in name or "airbass" in name:
            print(f"\nSelected speaker: {sp.name}")
            return sp

    sp = sc.default_speaker()
    print(f"\nSelected default speaker: {sp.name}")
    return sp


def main():
    print("=== BhashaSaathi TTS isolation probe ===")
    print(f"Python TTS device: {DEVICE}")
    print(f"TTS model: {TTS_DIR}")
    print(f"FLAN tokenizer: {FLAN_DIR}")

    if not TTS_DIR.exists():
        raise FileNotFoundError(TTS_DIR)
    if not FLAN_DIR.exists():
        raise FileNotFoundError(FLAN_DIR)

    print("\n[1/4] Loading tokenizers...")
    prompt_tokenizer = AutoTokenizer.from_pretrained(
        str(TTS_DIR), local_files_only=True
    )
    description_tokenizer = AutoTokenizer.from_pretrained(
        str(FLAN_DIR), local_files_only=True
    )

    print("[2/4] Loading Parler-TTS model...")
    model_kwargs = {"local_files_only": True}
    if DEVICE == "cuda":
        model_kwargs["torch_dtype"] = torch.float16

    try:
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            str(TTS_DIR),
            attn_implementation="sdpa",
            **model_kwargs,
        )
    except (TypeError, ValueError):
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            str(TTS_DIR),
            **model_kwargs,
        )

    model = model.to(DEVICE).eval()

    description_inputs = description_tokenizer(
        DESCRIPTION,
        return_tensors="pt",
        truncation=True,
        max_length=128,
    ).to(DEVICE)

    prompt_inputs = prompt_tokenizer(
        TEXT,
        return_tensors="pt",
        truncation=True,
        max_length=256,
    ).to(DEVICE)

    print("[3/4] Generating full TTS waveform...")
    started = time.perf_counter()

    with torch.inference_mode():
        generation = model.generate(
            input_ids=description_inputs.input_ids,
            attention_mask=description_inputs.attention_mask,
            prompt_input_ids=prompt_inputs.input_ids,
            prompt_attention_mask=prompt_inputs.attention_mask,
            do_sample=False,
            use_cache=True,
        )

    elapsed = time.perf_counter() - started

    if hasattr(generation, "sequences"):
        if getattr(generation, "audios_length", None) is not None:
            length = int(generation.audios_length[0].item())
            audio = generation.sequences[0, :length]
        else:
            audio = generation.sequences[0]
    else:
        audio = generation[0] if getattr(generation, "ndim", 1) > 1 else generation

    audio = audio.detach().float().cpu().numpy().squeeze().astype(np.float32)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)

    sampling_rate = int(getattr(model.config, "sampling_rate", 44100))
    duration = len(audio) / float(sampling_rate) if len(audio) else 0.0
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0

    print(f"\nGeneration time : {elapsed:.2f}s")
    print(f"Samples         : {len(audio)}")
    print(f"Sample rate     : {sampling_rate} Hz")
    print(f"Duration        : {duration:.2f}s")
    print(f"Peak amplitude  : {peak:.6f}")
    print(f"RMS             : {rms:.6f}")

    if len(audio) == 0:
        raise RuntimeError("Parler returned ZERO audio samples.")

    if peak < 1e-5:
        raise RuntimeError("Parler returned audio, but amplitude is effectively zero.")

    wav_path = ROOT / "tts_probe.wav"
    sf.write(str(wav_path), audio, sampling_rate, subtype="PCM_16")
    print(f"\nWAV saved: {wav_path}")

    print("\n[4/4] Playing the generated WAV through SoundCard...")
    speaker = pick_speaker()

    output_rate = 48000
    play_audio = audio

    if sampling_rate != output_rate:
        gcd = np.gcd(sampling_rate, output_rate)
        up = output_rate // gcd
        down = sampling_rate // gcd
        print(f"Resampling: {sampling_rate} Hz -> {output_rate} Hz")
        play_audio = resample_poly(play_audio, up, down).astype(np.float32)

    channels = getattr(speaker, "channels", 2)
    if isinstance(channels, int):
        channels = max(1, min(channels, 2))
    else:
        channels = 2

    stereo = np.repeat(play_audio[:, None], 2, axis=1) if channels == 2 else play_audio[:, None]

    with speaker.player(
        samplerate=output_rate,
        channels=channels,
        blocksize=512,
        exclusive_mode=False,
    ) as player:
        player.play(stereo.astype(np.float32, copy=False))
        # SoundCard queues audio asynchronously; keep the player alive.
        time.sleep(len(play_audio) / output_rate + 0.5)

    print("\nDONE.")
    print("If tts_probe.wav exists and has a waveform but you heard nothing,")
    print("the Parler model is working and only Windows/Bluetooth playback remains.")
    print("If generation fails before WAV creation, the problem is inside Parler/model generation.")


if __name__ == "__main__":
    main()
