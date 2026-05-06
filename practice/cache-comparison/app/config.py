from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheMode(str, Enum):
    CACHE_ASIDE = "cache_aside"
    WRITE_THROUGH = "write_through"
    WRITE_BACK = "write_back"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://bench:bench@127.0.0.1:5433/cachebench"
    )
    redis_url: str = "redis://127.0.0.1:6380/0"
    cache_mode: CacheMode = CacheMode.CACHE_ASIDE
    cache_ttl_sec: int = 300
    write_back_flush_interval_sec: float = 1.0
    item_key_prefix: str = "item:"


settings = Settings()
