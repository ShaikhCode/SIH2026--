from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    app_env: str = 'development'
    secret_key: str = 'change-this-local-secret-key-32-bytes-minimum-demo-value'
    database_url: str = 'sqlite:///./data/bhashasaathi.db'
    storage_dir: str = './data/storage'
    model_dir: str = './models'
    hf_token: str | None = None
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    api_base_url: str = 'http://127.0.0.1:8000/api/v1'
    demo_mode: bool = False
    translation_enabled: bool = True
    stt_enabled: bool = True
    tts_enabled: bool = True
    llm_enabled: bool = False
    cpu_only: bool = False
    log_level: str = 'INFO'
    max_audio_mb: int = 30

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

settings = Settings()

API_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = API_ROOT / 'data'
STORAGE_ROOT = (API_ROOT / settings.storage_dir).resolve() if not Path(settings.storage_dir).is_absolute() else Path(settings.storage_dir)
MODELS_ROOT = (API_ROOT / settings.model_dir).resolve() if not Path(settings.model_dir).is_absolute() else Path(settings.model_dir)
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
MODELS_ROOT.mkdir(parents=True, exist_ok=True)

def origins() -> list[str]:
    return [x.strip() for x in settings.cors_origins.split(',') if x.strip()]
