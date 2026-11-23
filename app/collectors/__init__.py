"""Сбор трендов со всех источников параллельно. Любой упавший источник не ломает остальные."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..config import settings
from . import rss, social
from .base import Item


def _jobs():
    s = settings
    return {
        "google_trends": lambda: rss.google_trends(s.region),
        "google_news": lambda: rss.google_news(s.region, s.language),
        "youtube": lambda: social.youtube(s.youtube_api_key, s.region),
        "hackernews": social.hackernews,
        "reddit": social.reddit,
        "habr": rss.habr,
        "lenta": rss.lenta,
        "tass": rss.tass,
        "instagram": lambda: social.instagram(s.apify_token, s.instagram_hashtags),
        "custom_rss": lambda: rss.custom(s.custom_rss) if s.custom_rss else [],
    }


def collect_all() -> tuple[list[Item], dict[str, str]]:
    """Возвращает (элементы, статус по источникам)."""
    jobs = {k: v for k, v in _jobs().items() if k in settings.enabled_sources}
    items: list[Item] = []
    status: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(jobs) or 1) as ex:
        futures = {name: ex.submit(fn) for name, fn in jobs.items()}
        for name, fut in futures.items():
            try:
                got = fut.result(timeout=150)
                items += got
                status[name] = f"ok: {len(got)}"
            except Exception as e:  # noqa: BLE001
                status[name] = f"пропущен: {str(e)[:120]}"
    return items, status
