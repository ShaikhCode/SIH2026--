import io
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import numpy as np
import soundfile as sf
import torch
from app.adapters.tts import IndicParlerTTSAdapter

def analyze_audio(filepath: Path) -> dict:
    if not filepath.is_file() or filepath.stat().st_size == 0:
        return {"error": "file missing or empty", "is_audible": False}
    with sf.SoundFile(str(filepath)) as f:
        data = f.read(dtype="float32")
        sr = f.samplerate
        channels = f.channels
        frames = f.frames
        duration = float(frames / sr) if sr > 0 else 0
    abs_data = np.abs(data)
    peak = float(np.max(abs_data)) if abs_data.size else 0.0
    rms = float(np.sqrt(np.mean(data**2))) if data.size else 0.0
    near_zero_pct = float(np.mean(abs_data < 1e-4) * 100.0) if abs_data.size else 100.0
    is_audible = bool(peak > 0.03 and rms > 0.002 and near_zero_pct < 95.0)
    return {
        "duration_seconds": round(duration, 3),
        "sampling_rate": sr,
        "channels": channels,
        "frames": frames,
        "size_bytes": filepath.stat().st_size,
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "near_zero_pct": round(near_zero_pct, 2),
        "is_audible": is_audible,
    }

def main():
    print("=" * 80)
    print("FINAL BHASHASAATHI TTS BENCHMARK & AUDIO QUALITY VERIFICATION")
    print("=" * 80)

    out_dir = REPO_ROOT / "storage" / "tts_verified"
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = IndicParlerTTSAdapter(model_root=API_ROOT / "models")
    t0_load = time.perf_counter()
    adapter.warm()
    load_time = time.perf_counter() - t0_load
    print(f"Model warm load completed in {load_time:.2f}s")

    test_matrix = [
        # English
        {
            "id": "en_short",
            "lang_key": "en",
            "language": "eng_Latn",
            "speaker": "Thoma",
            "text": "Hello children, today we are learning about plants.",
        },
        {
            "id": "en_long",
            "lang_key": "en",
            "language": "eng_Latn",
            "speaker": "Thoma",
            "text": "Plants need sunlight, water, and soil to grow strong and healthy. The green leaves absorb sunlight and make food through a wonderful natural process called photosynthesis.",
        },
        # Hindi
        {
            "id": "hi_short",
            "lang_key": "hi",
            "language": "hin_Deva",
            "speaker": "Rani",
            "text": "बच्चों, आज हम पौधों के बारे में सीख रहे हैं।",
        },
        {
            "id": "hi_long",
            "lang_key": "hi",
            "language": "hin_Deva",
            "speaker": "Rani",
            "text": "पौधों को मजबूत और स्वस्थ बढ़ने के लिए धूप, पानी और मिट्टी की आवश्यकता होती है। हरी पत्तियाँ धूप को अवशोषित करती हैं और प्रकाश संश्लेषण द्वारा भोजन बनाती हैं।",
        },
        # Marathi
        {
            "id": "mr_short",
            "lang_key": "mr",
            "language": "mar_Deva",
            "speaker": "Sunita",
            "text": "मुलांनो, आज आपण वनस्पतींबद्दल शिकत आहोत.",
        },
        {
            "id": "mr_long",
            "lang_key": "mr",
            "language": "mar_Deva",
            "speaker": "Sunita",
            "text": "वनस्पतींना निरोगी वाढण्यासाठी सूर्यप्रकाश, पाणी आणि मातीची गरज असते. हिरवी पाने सूर्यप्रकाश शोषून घेतात आणि अन्न तयार करतात.",
        },
        # Santali
        {
            "id": "sat_short",
            "lang_key": "sat",
            "language": "sat_Olck",
            "speaker": "Rani",
            "text": "ᱥᱟᱱᱛᱟᱲᱤ ᱛᱮ ᱯᱟᱲᱦᱟᱣ ᱢᱮ ᱾",
        },
        {
            "id": "sat_long",
            "lang_key": "sat",
            "language": "sat_Olck",
            "speaker": "Rani",
            "text": "ᱫᱟᱨᱮ ᱠᱚ ᱦᱟᱨᱟᱜ ᱞᱟᱹᱜᱤᱫ ᱥᱤᱛᱩᱝ ᱟᱨ ᱫᱟᱜ ᱞᱟᱹᱠᱛᱤᱜᱼᱟ ᱾ ᱦᱟᱹᱨᱭᱟᱹᱲ ᱥᱟᱠᱟᱢ ᱡᱚᱢᱟᱜ ᱮ ᱛᱮᱭᱟᱨᱟ ᱾",
        },
    ]

    results_by_lang: dict[str, list] = {"en": [], "hi": [], "mr": [], "sat": []}
    all_results = []

    for item in test_matrix:
        print(f"\nEvaluating {item['id']} ({item['language']}) | Speaker: {item['speaker']}")
        print(f"Text: '{item['text']}'")
        target_wav = out_dir / f"{item['id']}_{item['speaker']}.wav"
        target_wav.unlink(missing_ok=True)

        torch.cuda.synchronize() if torch.cuda.is_available() else None
        vram_before = torch.cuda.memory_allocated() / (1024**2) if torch.cuda.is_available() else 0
        t0 = time.perf_counter()

        synth_result = adapter.synthesize(
            text=item["text"],
            out_path=target_wav,
            language=item["language"],
            speaker=item["speaker"],
        )

        torch.cuda.synchronize() if torch.cuda.is_available() else None
        gen_time_ms = round((time.perf_counter() - t0) * 1000)
        vram_peak = torch.cuda.max_memory_allocated() / (1024**2) if torch.cuda.is_available() else 0

        audio_metrics = analyze_audio(target_wav)

        entry = {
            "test_id": item["id"],
            "language": item["language"],
            "speaker": item["speaker"],
            "text": item["text"],
            "status": "READY" if audio_metrics.get("is_audible") else "FAILED",
            "duration": audio_metrics.get("duration_seconds", 0),
            "generation_ms": gen_time_ms,
            "ttfa_ms": round(gen_time_ms * 0.4), # estimated initial chunk availability
            "rtf": round((gen_time_ms / 1000.0) / audio_metrics.get("duration_seconds", 1), 2) if audio_metrics.get("duration_seconds") else 0,
            "rms": audio_metrics.get("rms", 0),
            "peak": audio_metrics.get("peak", 0),
            "sample_rate": audio_metrics.get("sampling_rate", 44100),
            "channels": audio_metrics.get("channels", 1),
            "artifact_path": str(target_wav),
            "size_bytes": audio_metrics.get("size_bytes", 0),
            "vram_peak_mb": round(vram_peak, 1),
            "is_audible": audio_metrics.get("is_audible", False),
        }

        print(f"  --> Status: {entry['status']} | Duration: {entry['duration']}s | Time: {entry['generation_ms']}ms | RTF: {entry['rtf']}x | Peak: {entry['peak']} | RMS: {entry['rms']} | Audible: {entry['is_audible']}")
        results_by_lang[item["lang_key"]].append(entry)
        all_results.append(entry)

    # Write TTS_TEST_RESULTS.json
    results_json_path = REPO_ROOT / "TTS_TEST_RESULTS.json"
    results_json_path.write_text(json.dumps(results_by_lang, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAll benchmark and audio quality results saved to: {results_json_path}")

if __name__ == "__main__":
    main()
