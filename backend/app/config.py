from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str
    allowed_origins: list[str] = ['http://127.0.0.1:5173', 'http://localhost:5173']
    cookie_secure: bool = True
    session_hours: int = 12
    redis_url: str = 'redis://127.0.0.1:6379/0'
    broker_url: str = 'redis://127.0.0.1:6379/1'
    rate_limit_enabled: bool = True
    login_limit: int = 10
    login_window_seconds: int = 60
    export_dir: Path = ROOT / '.local' / 'exports'


settings = Settings()
