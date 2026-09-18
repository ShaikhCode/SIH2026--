from pathlib import Path
import threading
import numpy as np
import soundfile as sf
import torch

LANGUAGE_DESCRIPTIONS={'eng_Latn':'English','hin_Deva':'Hindi','sat_Olck':'Santali'}

class IndicParlerTTSAdapter:
    def __init__(self,model_root:Path,cpu_only:bool=False):
        self.root=model_root/'tts'; self.model_path=self.root/'indic-parler-tts'; self.desc_path=self.root/'description-tokenizer'; self.cpu_only=cpu_only; self._bundle=None; self._lock=threading.RLock()
    def health(self): return {'model':self.model_path.exists() and any(self.model_path.iterdir()),'description_tokenizer':self.desc_path.exists() and any(self.desc_path.iterdir())}
    def _load(self):
        with self._lock:
            if self._bundle is not None: return self._bundle
            if not self.model_path.exists(): raise FileNotFoundError(f'Missing TTS model folder: {self.model_path}')
            if not self.desc_path.exists(): raise FileNotFoundError(f'Missing TTS description tokenizer folder: {self.desc_path}. Run scripts/download_tts_support.py')
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer,AutoFeatureExtractor
            device=torch.device('cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda')
            dtype=torch.float32 if device.type=='cpu' else torch.float16
            model=ParlerTTSForConditionalGeneration.from_pretrained(str(self.model_path),local_files_only=True,attn_implementation='eager',torch_dtype=dtype).to(device)
            tokenizer=AutoTokenizer.from_pretrained(str(self.model_path),local_files_only=True)
            desc_tokenizer=AutoTokenizer.from_pretrained(str(self.desc_path),local_files_only=True)
            feature=AutoFeatureExtractor.from_pretrained(str(self.model_path),local_files_only=True)
            self._bundle=(model,tokenizer,desc_tokenizer,feature,device); return self._bundle
    def synthesize(self,text:str,out_path:Path,language:str,speaker:str='classroom_teacher')->dict:
        model,tokenizer,desc_tokenizer,feature,device=self._load()
        description=f'{speaker} speaks {LANGUAGE_DESCRIPTIONS.get(language,"English")} clearly at a calm moderate pace, suitable for a primary classroom, with clean close audio and no background noise.'
        desc=desc_tokenizer(description,return_tensors='pt').to(device); prompt=tokenizer(text,return_tensors='pt').to(device)
        with torch.inference_mode():
            generation=model.generate(input_ids=desc.input_ids,attention_mask=desc.attention_mask,prompt_input_ids=prompt.input_ids,prompt_attention_mask=prompt.attention_mask,do_sample=True,return_dict_in_generate=True)
        if not hasattr(generation,'audios_length'): raise RuntimeError('TTS model did not return audio length metadata.')
        audio=generation.sequences[0,:generation.audios_length[0]].to(torch.float32).cpu().numpy().squeeze(); audio=np.asarray(audio,dtype=np.float32).reshape(-1)
        out_path.parent.mkdir(parents=True,exist_ok=True); sf.write(out_path,audio,int(feature.sampling_rate))
        return {'path':str(out_path),'sample_rate':int(feature.sampling_rate),'duration_seconds':round(float(len(audio)/feature.sampling_rate),2)}
    def unload(self):
        with self._lock: self._bundle=None; torch.cuda.empty_cache() if torch.cuda.is_available() else None
