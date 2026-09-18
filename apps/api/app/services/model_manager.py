import threading
import torch
from ..core.config import MODELS_ROOT, settings
from ..adapters.translation import IndicTrans2Adapter
from ..adapters.stt import FasterWhisperAdapter
from ..adapters.tts import IndicParlerTTSAdapter

class ModelManager:
    def __init__(self):
        self.lock=threading.RLock()
        self.translation=IndicTrans2Adapter(MODELS_ROOT,settings.cpu_only)
        self.stt=FasterWhisperAdapter(MODELS_ROOT,settings.cpu_only)
        self.tts=IndicParlerTTSAdapter(MODELS_ROOT,settings.cpu_only)
    def status(self)->dict:
        return {'demo_mode':settings.demo_mode,'enabled':{'translation':settings.translation_enabled,'stt':settings.stt_enabled,'tts':settings.tts_enabled,'llm':settings.llm_enabled},'device':'cpu' if settings.cpu_only else ('cuda' if torch.cuda.is_available() else 'cpu'),'cuda_available':bool(torch.cuda.is_available()),'translation':self.translation.health(),'stt':self.stt.health(),'tts':self.tts.health()}
    def unload_heavy(self)->None:
        with self.lock:
            self.translation.unload(); self.stt.unload(); self.tts.unload()
            if torch.cuda.is_available(): torch.cuda.empty_cache()

manager=ModelManager()
