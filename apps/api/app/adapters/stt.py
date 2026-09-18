from pathlib import Path
import threading

class FasterWhisperAdapter:
    def __init__(self, model_root: Path, cpu_only: bool=False):
        self.path=model_root/'stt'/'whisper-small'; self.cpu_only=cpu_only; self._model=None; self._lock=threading.RLock()
    def health(self)->bool: return self.path.exists() and any(self.path.iterdir())
    def _load(self):
        with self._lock:
            if self._model is not None: return self._model
            from faster_whisper import WhisperModel
            import torch
            device='cpu' if self.cpu_only or not torch.cuda.is_available() else 'cuda'
            compute='int8' if device=='cpu' else 'float16'
            self._model=WhisperModel(str(self.path),device=device,compute_type=compute)
            return self._model
    def transcribe(self,audio_path:Path,language:str|None='hi')->dict:
        model=self._load(); segments,info=model.transcribe(str(audio_path),language=language,beam_size=5,vad_filter=True)
        text=' '.join(seg.text.strip() for seg in segments).strip()
        return {'text':text,'language':info.language,'probability':float(info.language_probability)}
    def unload(self):
        with self._lock: self._model=None
