import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    # SOCKS/HTTP прокси до api.telegram.org, если сеть режет Telegram (например http://127.0.0.1:7890)
    telegram_http_proxy: str | None


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    db_url = os.getenv("DATABASE_URL", "").strip()
    proxy = os.getenv("TELEGRAM_HTTP_PROXY", "").strip() or None
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return Settings(
        bot_token=token,
        database_url=db_url,
        telegram_http_proxy=proxy,
    )
