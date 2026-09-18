from pathlib import Path
import soundfile as sf
import torch
from .model_manager import manager

def synthesize(text: str, out: Path, language: str):
    model,tokenizer,desc_tok,feature=manager.tts_models()
    device=model.device
    lang_name={"hin_Deva":"Hindi","sat_Olck":"Santali","eng_Latn":"English"}.get(language,"English")
    prompt=text
    description=f"A clear Indian classroom teacher speaks {lang_name} naturally, clearly and at a moderate pace."
    input_ids=tokenizer(prompt,return_tensors="pt").input_ids.to(device)
    desc_ids=desc_tok(description,return_tensors="pt").input_ids.to(device)
    with torch.inference_mode():
        audio=model.generate(input_ids=input_ids,description_input_ids=desc_ids,do_sample=True,temperature=1.0)
    audio=audio.cpu().numpy().squeeze()
    sf.write(out,audio,feature.sampling_rate)
    return out
