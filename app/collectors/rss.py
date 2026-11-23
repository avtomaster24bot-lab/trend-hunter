"""Бесключевые RSS-источники: Google Тренды, Google Новости, Хабр, Лента, ТАСС, свои ленты."""
from __future__ import annotations

import html
import re

import feedparser

from .base import Item, client, parse_time

_TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _first_image(entry) -> str:
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image"):
            return enc.get("href") or enc.get("url", "")
    m = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", "") or "")
    return m.group(1) if m else ""


def fetch_feed(url: str, source: str, label: str, limit: int = 30) -> list[Item]:
    with client() as c:
        r = c.get(url)
        r.raise_for_status()
    feed = feedparser.parse(r.content)
    items = []
    for i, e in enumerate(feed.entries[:limit]):
        title = clean(e.get("title", ""))
        if not title:
            continue
        items.append(Item(
            title=title, url=e.get("link", ""), source=source, source_label=label,
            popularity=max(0, limit - i), rank=i, published=parse_time(e),
            summary=clean(e.get("summary", ""))[:600], image=_first_image(e),
        ))
    return items


def google_trends(region: str) -> list[Item]:
    """Поисковые запросы, которые взлетают прямо сейчас (с примерным трафиком)."""
    url = f"https://trends.google.com/trending/rss?geo={region}"
    with client() as c:
        r = c.get(url)
        r.raise_for_status()
    feed = feedparser.parse(r.content)
    items = []
    for i, e in enumerate(feed.entries):
        traffic = str(e.get("ht_approx_traffic", "0")).replace(",", "").replace("+", "").replace(" ", "")
        mult = 1
        if traffic.lower().endswith("k"):
            traffic, mult = traffic[:-1], 1000
        try:
            pop = float(traffic) * mult
        except ValueError:
            pop = 0
        news = []
        # feedparser складывает ht:news_item_* в плоские поля — достаём хотя бы первую новость
        if e.get("ht_news_item_title"):
            news.append({"title": clean(e.get("ht_news_item_title")), "url": e.get("ht_news_item_url", ""),
                         "source": e.get("ht_news_item_source", "")})
        items.append(Item(
            title=clean(e.get("title", "")), url=news[0]["url"] if news else f"https://trends.google.com/trends/explore?q={e.get('title','')}&geo={region}",
            source="google_trends", source_label="Google Тренды", popularity=pop, rank=i,
            published=parse_time(e), summary="; ".join(n["title"] for n in news),
            image=e.get("ht_picture", ""), extra={"news": news, "traffic": e.get("ht_approx_traffic", "")},
        ))
    return items


def google_news(region: str, language: str) -> list[Item]:
    url = f"https://news.google.com/rss?hl={language}&gl={region}&ceid={region}:{language}"
    items = fetch_feed(url, "google_news", "Google Новости", limit=40)
    for it in items:  # «Заголовок - Издание» → убираем издание
        it.title = re.sub(r"\s+[-–—]\s+[^-–—]{2,40}$", "", it.title)
    return items


def google_news_search(query: str, region: str, language: str, limit: int = 15) -> list[Item]:
    from urllib.parse import quote
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl={language}&gl={region}&ceid={region}:{language}"
    return fetch_feed(url, "google_news", "Google Новости", limit=limit)


def habr() -> list[Item]:
    return fetch_feed("https://habr.com/ru/rss/articles/top/daily/?fl=ru", "habr", "Хабр")


def lenta() -> list[Item]:
    return fetch_feed("https://lenta.ru/rss/top7", "lenta", "Лента.ру")


def tass() -> list[Item]:
    return fetch_feed("https://tass.ru/rss/v2.xml", "tass", "ТАСС")


def custom(urls: list[str]) -> list[Item]:
    out: list[Item] = []
    for u in urls:
        try:
            out += fetch_feed(u.strip(), "custom_rss", "RSS")
        except Exception:  # noqa: BLE001
            continue
    return out
