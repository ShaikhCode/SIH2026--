import sys
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
from transformers import AutoTokenizer
from app.adapters.tts import IndicParlerTTSAdapter

def analyze_waveform(wav: np.ndarray, sr: int) -> dict:
    abs_wav = np.abs(wav)
    peak = float(np.max(abs_wav))
    rms = float(np.sqrt(np.mean(wav**2)))
    near_zero_pct = float(np.mean(abs_wav < 1e-4) * 100.0)
    return {
        "duration_seconds": round(float(len(wav) / sr), 3),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "near_zero_pct": round(near_zero_pct, 2),
        "is_audible": bool(peak > 0.05 and rms > 0.005 and near_zero_pct < 90.0),
    }

def main():
    adapter = IndicParlerTTSAdapter(model_root=API_ROOT / "models")
    adapter.warm()
    model, tokenizer, description_tokenizer, feature, device = adapter._load()
    sampling_rate = int(feature.sampling_rate)
    frame_rate = int(getattr(model.audio_encoder.config, "frame_rate", 86))

    # Test sentence 2 variations for Santali:
    s2_raw = "ᱫᱟᱜ ᱟᱨ ᱥᱤᱛᱩᱝ ᱛᱮ ᱫᱟᱨᱮ ᱦᱟᱨᱟᱜᱼᱟ ᱾"
    
    # Try cleaning/normalizing Ol Chiki punctuation & special characters
    s2_clean1 = "ᱫᱟᱜ ᱟᱨ ᱥᱤᱛᱩᱝ ᱛᱮ ᱫᱟᱨᱮ ᱦᱟᱨᱟᱜᱟ ᱾" # without hyphen/glottal dash
    s2_clean2 = "ᱫᱟᱜ ᱟᱨ ᱥᱤᱛᱩᱝ ᱛᱮ ᱫᱟᱨᱮ ᱦᱟᱨᱟᱜᱟ."   # with period instead of danda
    s2_clean3 = "ᱫᱟᱨᱮ ᱫᱟᱜ ᱟᱨ ᱥᱤᱛᱩᱝ ᱛᱮ ᱦᱟᱨᱟᱜ ᱠᱟᱱᱟ ᱾" # alternative natural phrasing
    
    print("Tokens for s2_raw:", tokenizer.tokenize(s2_raw), tokenizer(s2_raw).input_ids)
    print("Tokens for s2_clean1:", tokenizer.tokenize(s2_clean1), tokenizer(s2_clean1).input_ids)

    santali_variants = [
        ("s2_raw", s2_raw),
        ("s2_clean1", s2_clean1),
        ("s2_clean2", s2_clean2),
        ("s2_clean3", s2_clean3),
    ]

    desc = "Arjun speaks clearly in a high quality close recording."
    desc_inputs = description_tokenizer(desc, return_tensors="pt").to(device)

    for name, text in santali_variants:
        prompt_inputs = tokenizer(text, return_tensors="pt").to(device)
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
                max_new_tokens=adapter._estimate_max_new_tokens(text, frame_rate, 30.0),
                return_dict_in_generate=True,
            )
            audio = gen.sequences[0]
            if hasattr(gen, "audios_length"):
                audio = audio[: int(gen.audios_length[0])]
            arr = audio.to(torch.float32).detach().cpu().numpy().reshape(-1)
        stats = analyze_waveform(arr, sampling_rate)
        print(f"Variant: {name:<12} | Text: '{text}' | Peak: {stats['peak']:<8} | RMS: {stats['rms']:<8} | Audible: {stats['is_audible']}")

    # Let's also check Rani and Aman for Hindi with standard classroom sentences
    hindi_sentences = [
        "बच्चों, आज हम पौधों के बारे में सीख रहे हैं।",
        "हरी पत्तियाँ पौधे के लिए भोजन बनाती हैं।",
        "पौधों को बढ़ने के लिए पानी और धूप की जरूरत होती है।",
    ]
    print("\n--- HINDI WITH RANI & AMAN ---")
    for text in hindi_sentences:
        for spk, desc in [
            ("Rani", "Rani speaks with a high-pitched, clear voice in a close recording."),
            ("Aman", "Aman speaks in a clear voice with a close recording and high quality."),
        ]:
            desc_inputs = description_tokenizer(desc, return_tensors="pt").to(device)
            prompt_inputs = tokenizer(text, return_tensors="pt").to(device)
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
                    max_new_tokens=adapter._estimate_max_new_tokens(text, frame_rate, 30.0),
                    return_dict_in_generate=True,
                )
                audio = gen.sequences[0]
                if hasattr(gen, "audios_length"):
                    audio = audio[: int(gen.audios_length[0])]
                arr = audio.to(torch.float32).detach().cpu().numpy().reshape(-1)
            stats = analyze_waveform(arr, sampling_rate)
            print(f"Hindi | Speaker: {spk:<6} | Peak: {stats['peak']:<8} | RMS: {stats['rms']:<8} | Audible: {stats['is_audible']} | Text: {text[:30]}...")

    # Let's check Sunita and Isha for Marathi with standard classroom sentences
    marathi_sentences = [
        "मुलांनो, आज आपण वनस्पतींबद्दल शिकत आहोत.",
        "हिरवी पाने वनस्पतीसाठी अन्न तयार करतात.",
        "वनस्पतींना वाढण्यासाठी सूर्यप्रकाश आणि पाण्याची गरज असते.",
    ]
    print("\n--- MARATHI WITH SUNITA & ISHA ---")
    for text in marathi_sentences:
        for spk, desc in [
            ("Sunita", "Sunita speaks clearly in a close-sounding environment with high quality."),
            ("Isha", "Isha speaks clearly in a high quality recording."),
        ]:
            desc_inputs = description_tokenizer(desc, return_tensors="pt").to(device)
            prompt_inputs = tokenizer(text, return_tensors="pt").to(device)
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
                    max_new_tokens=adapter._estimate_max_new_tokens(text, frame_rate, 30.0),
                    return_dict_in_generate=True,
                )
                audio = gen.sequences[0]
                if hasattr(gen, "audios_length"):
                    audio = audio[: int(gen.audios_length[0])]
                arr = audio.to(torch.float32).detach().cpu().numpy().reshape(-1)
            stats = analyze_waveform(arr, sampling_rate)
            print(f"Marathi | Speaker: {spk:<6} | Peak: {stats['peak']:<8} | RMS: {stats['rms']:<8} | Audible: {stats['is_audible']} | Text: {text[:30]}...")

if __name__ == "__main__":
    main()
