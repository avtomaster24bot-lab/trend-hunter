"""Настройки из переменных окружения (.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


class Settings:
    # Где хранить задания и видео
    data_dir = Path(_get("DATA_DIR", str(ROOT / "data")))

    # Регион/язык трендов
    region = _get("TREND_REGION", "RU")  # RU, KZ, US ...
    language = _get("TREND_LANGUAGE", "ru")
    custom_rss = [u for u in _get("EXTRA_RSS_FEEDS").split(",") if u.strip()]
    enabled_sources = [s.strip() for s in _get(
        "SOURCES", "google_trends,google_news,youtube,hackernews,reddit,habr,lenta,tass,instagram,custom_rss"
    ).split(",") if s.strip()]

    # YouTube Data API v3
    youtube_api_key = _get("YOUTUBE_API_KEY")

    # Instagram — только через сторонний сервис (Apify)
    apify_token = _get("APIFY_TOKEN")
    instagram_hashtags = [h.strip().lstrip("#") for h in _get("INSTAGRAM_HASHTAGS", "новости,тренды").split(",") if h.strip()]

    # LLM (любой OpenAI-совместимый API: OpenAI, xAI, OpenRouter, DeepSeek, локальный Ollama...)
    llm_api_key = _get("LLM_API_KEY") or _get("OPENAI_API_KEY") or _get("XAI_API_KEY")
    llm_base_url = _get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    llm_model = _get("LLM_MODEL", "gpt-4o-mini")

    # Озвучка — мужской голос
    tts_provider = _get("TTS_PROVIDER", "edge")  # edge | openai | elevenlabs
    edge_voice = _get("EDGE_TTS_VOICE", "ru-RU-DmitryNeural")
    edge_rate = _get("EDGE_TTS_RATE", "+0%")
    openai_tts_voice = _get("OPENAI_TTS_VOICE", "onyx")
    openai_tts_model = _get("OPENAI_TTS_MODEL", "tts-1")
    openai_api_key = _get("OPENAI_API_KEY") or _get("LLM_API_KEY")
    elevenlabs_api_key = _get("ELEVENLABS_API_KEY")
    elevenlabs_voice_id = _get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam (мужской)

    # Видео
    video_width = _int("VIDEO_WIDTH", 1280)
    video_height = _int("VIDEO_HEIGHT", 720)
    words_per_minute = _int("WORDS_PER_MINUTE", 120)

    # Telegram
    telegram_bot_token = _get("TELEGRAM_BOT_TOKEN")
    telegram_channel = _get("TELEGRAM_CHANNEL", "@koleso_uspeha")
    telegram_api_url = _get("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/")
    # Лимит обычного Bot API — 50 МБ. Для локального Bot API сервера можно поставить 2000.
    telegram_max_mb = _int("TELEGRAM_MAX_MB", 49)

    # Простая защита веб-интерфейса (необязательно)
    admin_password = _get("ADMIN_PASSWORD")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
