import io
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Setup paths
REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import numpy as np
import soundfile as sf
import torch

from app.adapters.tts import IndicParlerTTSAdapter

def analyze_waveform(wav: np.ndarray, sr: int) -> dict:
    if wav.size == 0:
        return {"error": "empty waveform"}
    
    abs_wav = np.abs(wav)
    peak = float(np.max(abs_wav))
    rms = float(np.sqrt(np.mean(wav**2)))
    mean_abs = float(np.mean(abs_wav))
    near_zero_pct = float(np.mean(abs_wav < 1e-4) * 100.0)
    dc_offset = float(np.mean(wav))
    zcr = float(np.mean(np.diff(np.sign(wav) != 0)))
    duration = float(len(wav) / sr)
    
    return {
        "duration_seconds": round(duration, 3),
        "sampling_rate": sr,
        "samples": len(wav),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "mean_abs": round(mean_abs, 6),
        "near_zero_pct": round(near_zero_pct, 2),
        "dc_offset": round(dc_offset, 6),
        "zcr": round(zcr, 4),
        "is_audible": bool(peak > 0.05 and rms > 0.005 and near_zero_pct < 95.0),
    }

def main():
    print("=" * 80)
    print("TTS DIRECT AUDIO QUALITY & SILENCE DIAGNOSTIC")
    print("=" * 80)
    
    adapter = IndicParlerTTSAdapter(model_root=API_ROOT / "models")
    adapter.warm()
    
    test_cases = [
        # English
        {
            "lang_code": "eng_Latn",
            "lang_name": "English",
            "speaker": "Thoma",
            "text": "Hello children, today we are learning about plants.",
            "desc": "Thoma's voice is clear, with a close-sounding recording and excellent quality.",
        },
        {
            "lang_code": "eng_Latn",
            "lang_name": "English",
            "speaker": "Mary",
            "text": "Hello children, today we are learning about plants.",
            "desc": "Mary speaks clearly at a moderate pace in a high quality recording.",
        },
        # Hindi
        {
            "lang_code": "hin_Deva",
            "lang_name": "Hindi",
            "speaker": "Rohit",
            "text": "बच्चों, आज हम पौधों के बारे में सीख रहे हैं।",
            "desc": "Rohit speaks Hindi clearly at a slightly fast natural pace. The recording is very clear, close and without background noise.",
        },
        {
            "lang_code": "hin_Deva",
            "lang_name": "Hindi",
            "speaker": "Divya",
            "text": "बच्चों, आज हम पौधों के बारे में सीख रहे हैं।",
            "desc": "Divya's voice is clear and slightly fast in delivery, with a very close recording that has no background noise.",
        },
        {
            "lang_code": "hin_Deva",
            "lang_name": "Hindi",
            "speaker": "Divya",
            "text": "बच्चों, आज हम पौधों के बारे में सीख रहे हैं।",
            "desc": "A female speaker delivers a clear speech in Hindi with high quality and no background noise.",
        },
        # Marathi
        {
            "lang_code": "mar_Deva",
            "lang_name": "Marathi",
            "speaker": "Sanjay",
            "text": "मुलांनो, आज आपण वनस्पतींबद्दल शिकत आहोत.",
            "desc": "Sanjay speaks Marathi clearly at a slightly fast natural pace. The recording is very clear, close and without background noise.",
        },
        {
            "lang_code": "mar_Deva",
            "lang_name": "Marathi",
            "speaker": "Sunita",
            "text": "मुलांनो, आज आपण वनस्पतींबद्दल शिकत आहोत.",
            "desc": "Sunita speaks in a clear and high-pitched voice in a close environment with excellent recording quality.",
        },
        # Santali
        {
            "lang_code": "sat_Olck",
            "lang_name": "Santali (Ol Chiki)",
            "speaker": "Arjun",
            "text": "ᱥᱟᱱᱛᱟᱲᱤ ᱛᱮ ᱯᱟᱲᱦᱟᱣ ᱢᱮ ᱾",
            "desc": "A speaker delivers clear speech in Santali with high quality recording and no background noise.",
        },
        {
            "lang_code": "sat_Olck",
            "lang_name": "Santali (Ol Chiki)",
            "speaker": "Arjun",
            "text": "ᱥᱟᱱᱛᱟᱲᱤ ᱛᱮ ᱯᱟᱲᱦᱟᱣ ᱢᱮ ᱾",
            "desc": "Arjun speaks clearly with a close recording.",
        },
        {
            "lang_code": "sat_Olck",
            "lang_name": "Santali (Transliterated)",
            "speaker": "Arjun",
            "text": "Santali te padhao me.",
            "desc": "A speaker delivers clear speech with high quality recording.",
        },
    ]
    
    out_dir = REPO_ROOT / "scratch" / "tts_diag"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    model, tokenizer, description_tokenizer, feature, device = adapter._load()
    sampling_rate = int(feature.sampling_rate)
    frame_rate = int(getattr(model.audio_encoder.config, "frame_rate", 86))
    
    for i, tc in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] Testing {tc['lang_name']} | Speaker: {tc['speaker']}")
        print(f"  Prompt: '{tc['text']}'")
        print(f"  Desc:   '{tc['desc']}'")
        
        t0 = time.perf_counter()
        
        desc_inputs = description_tokenizer(tc["desc"], return_tensors="pt").to(device)
        prompt_inputs = tokenizer(tc["text"], return_tensors="pt").to(device)
        decoder_mask = torch.ones((1, 1), device=device, dtype=prompt_inputs.attention_mask.dtype)
        
        with torch.inference_mode():
            gen = model.generate(
                input_ids=desc_inputs.input_ids,
                attention_mask=desc_inputs.attention_mask,
                prompt_input_ids=prompt_inputs.input_ids,
                prompt_attention_mask=prompt_inputs.attention_mask,
                decoder_attention_mask=decoder_mask,
                do_sample=False,
                use_cache=True,
                max_new_tokens=adapter._estimate_max_new_tokens(tc["text"], frame_rate, 30.0),
                return_dict_in_generate=True,
            )
            
            audio = gen.sequences[0]
            if hasattr(gen, "audios_length"):
                audio = audio[: int(gen.audios_length[0])]
            arr = audio.to(torch.float32).detach().cpu().numpy().reshape(-1)
            
        gen_time = time.perf_counter() - t0
        
        # Save raw wav
        filename = f"{i+1:02d}_{tc['lang_code']}_{tc['speaker']}.wav"
        filepath = out_dir / filename
        sf.write(str(filepath), arr, sampling_rate, format="WAV", subtype="PCM_16")
        
        stats = analyze_waveform(arr, sampling_rate)
        stats["gen_time"] = round(gen_time, 2)
        stats["rtf"] = round(gen_time / stats["duration_seconds"], 2) if stats.get("duration_seconds") else 0
        stats["file"] = str(filepath)
        stats["lang"] = tc["lang_code"]
        stats["speaker"] = tc["speaker"]
        stats["text"] = tc["text"]
        stats["desc"] = tc["desc"]
        
        print(f"  --> Dur: {stats.get('duration_seconds')}s | Peak: {stats.get('peak')} | RMS: {stats.get('rms')} | NearZero%: {stats.get('near_zero_pct')}% | Audible: {stats.get('is_audible')}")
        results.append(stats)
        
    res_path = out_dir / "diagnostic_results.json"
    res_path.write_text(json.dumps(results, indent=2))
    print(f"\nAll results saved to {res_path}")

if __name__ == "__main__":
    main()
