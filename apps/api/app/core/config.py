from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api (not apps/api/app) is the runtime root.
API_ROOT = Path(__file__).resolve().parents[2]


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
    max_translation_chars: int = 12000
    parler_description_tokenizer: str = ''

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )


settings = Settings()


def _resolve_local_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (API_ROOT / path).resolve()


# Keep local paths stable regardless of whether uvicorn is started from apps/api,
# the repository root, or another working directory.
STORAGE_ROOT = _resolve_local_path(settings.storage_dir)
MODELS_ROOT = _resolve_local_path(settings.model_dir)
DATA_ROOT = API_ROOT / 'data'

if settings.database_url.startswith('sqlite:///'):
    sqlite_path = Path(settings.database_url.removeprefix('sqlite:///'))
    if not sqlite_path.is_absolute():
        settings.database_url = f'sqlite:///{(API_ROOT / sqlite_path).resolve().as_posix()}'

# Relative PARLER_DESCRIPTION_TOKENIZER values are resolved by the TTS adapter
# against MODELS_ROOT. Absolute values are preserved.

STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
MODELS_ROOT.mkdir(parents=True, exist_ok=True)
DATA_ROOT.mkdir(parents=True, exist_ok=True)


def origins() -> list[str]:
    return [item.strip() for item in settings.cors_origins.split(',') if item.strip()]
