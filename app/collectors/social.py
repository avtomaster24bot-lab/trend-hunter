"""Hacker News, Reddit, YouTube, Instagram."""
from __future__ import annotations

import time
from datetime import datetime

from .base import Item, client


def hackernews() -> list[Item]:
    with client() as c:
        data = c.get("https://hn.algolia.com/api/v1/search", params={"tags": "front_page", "hitsPerPage": 30}).json()
    items = []
    for i, h in enumerate(data.get("hits", [])):
        items.append(Item(
            title=h.get("title") or "", url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            source="hackernews", source_label="Hacker News", popularity=(h.get("points") or 0) + 2 * (h.get("num_comments") or 0),
            rank=i, published=h.get("created_at_i") or time.time(),
            extra={"discussion": f"https://news.ycombinator.com/item?id={h.get('objectID')}"},
        ))
    return items


def reddit() -> list[Item]:
    """Reddit часто отвечает 403 серверам из дата-центров — тогда источник просто пропускается."""
    with client() as c:
        r = c.get("https://www.reddit.com/r/popular/top.json", params={"t": "day", "limit": 40})
        r.raise_for_status()
        data = r.json()
    items = []
    for i, ch in enumerate(data.get("data", {}).get("children", [])):
        d = ch.get("data", {})
        img = d.get("thumbnail") if str(d.get("thumbnail", "")).startswith("http") else ""
        items.append(Item(
            title=d.get("title", ""), url="https://www.reddit.com" + d.get("permalink", ""), source="reddit",
            source_label=f"Reddit r/{d.get('subreddit', '')}", popularity=d.get("score", 0), rank=i,
            published=d.get("created_utc") or time.time(), summary=(d.get("selftext") or "")[:500], image=img,
        ))
    return items


def youtube(api_key: str, region: str) -> list[Item]:
    """Тренды YouTube (mostPopular) через YouTube Data API v3. Нужен YOUTUBE_API_KEY."""
    if not api_key:
        raise RuntimeError("нет YOUTUBE_API_KEY")
    with client() as c:
        r = c.get("https://www.googleapis.com/youtube/v3/videos", params={
            "part": "snippet,statistics", "chart": "mostPopular", "regionCode": region,
            "maxResults": 40, "key": api_key,
        })
        r.raise_for_status()
        data = r.json()
    items = []
    for i, v in enumerate(data.get("items", [])):
        sn, st = v.get("snippet", {}), v.get("statistics", {})
        try:
            pub = datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            pub = time.time()
        thumbs = sn.get("thumbnails", {})
        img = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}).get("url", "")
        items.append(Item(
            title=sn.get("title", ""), url=f"https://www.youtube.com/watch?v={v.get('id')}", source="youtube",
            source_label=f"YouTube · {sn.get('channelTitle', '')}", popularity=float(st.get("viewCount", 0)),
            rank=i, published=pub, summary=(sn.get("description") or "")[:500], image=img,
            extra={"tags": sn.get("tags", [])[:10]},
        ))
    return items


def youtube_search(api_key: str, query: str, region: str, language: str, limit: int = 8) -> list[Item]:
    if not api_key:
        return []
    with client() as c:
        r = c.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "q": query, "type": "video", "order": "relevance", "regionCode": region,
            "relevanceLanguage": language, "publishedAfter": datetime.utcfromtimestamp(time.time() - 7 * 86400).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxResults": limit, "key": api_key,
        })
        r.raise_for_status()
    out = []
    for i, v in enumerate(r.json().get("items", [])):
        sn = v.get("snippet", {})
        out.append(Item(title=sn.get("title", ""), url=f"https://www.youtube.com/watch?v={v['id'].get('videoId')}",
                        source="youtube", source_label="YouTube", rank=i, summary=sn.get("description", ""),
                        image=(sn.get("thumbnails", {}).get("high") or {}).get("url", "")))
    return out


def instagram(apify_token: str, hashtags: list[str]) -> list[Item]:
    """Instagram не даёт публичного API трендов. Используем сторонний сервис Apify
    (актор instagram-hashtag-scraper), если задан APIFY_TOKEN."""
    if not apify_token:
        raise RuntimeError("нет APIFY_TOKEN — Instagram пропущен")
    with client(timeout=120) as c:
        r = c.post(
            "https://api.apify.com/v2/acts/apify~instagram-hashtag-scraper/run-sync-get-dataset-items",
            params={"token": apify_token},
            json={"hashtags": hashtags, "resultsLimit": 20, "resultsType": "posts"},
        )
        r.raise_for_status()
        posts = r.json()
    items = []
    for i, p in enumerate(posts):
        caption = (p.get("caption") or "").strip()
        if not caption:
            continue
        items.append(Item(
            title=caption.split("\n")[0][:140], url=p.get("url", ""), source="instagram", source_label="Instagram",
            popularity=(p.get("likesCount") or 0) + 3 * (p.get("commentsCount") or 0), rank=i,
            summary=caption[:600], image=p.get("displayUrl", ""),
        ))
    return items
