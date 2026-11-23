"""Источники практичного ИИ: то, что можно повторить на своём ПК и превратить в доход."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .base import Item, client
from .rss import fetch_feed

# Запросы для поиска по новостям/HN — кейсы, агенты, автоматизация, локальные модели
HN_QUERIES = ["AI agent", "agents", "MCP", "local LLM", "Ollama", "automation", "Claude Code", "side project revenue",
              "open source", "self-hosted", "n8n", "skill"]
NEWS_QUERIES_EN = ['"AI agent" made money', '"AI agent" MRR', 'built an AI agent revenue', 'OpenClaw agent',
                   'n8n automation business', 'local LLM run on your PC', '"Claude Code" built app revenue']
NEWS_QUERIES_RU = ['ИИ агент заработок', 'нейросеть автоматизация заработок', 'n8n автоматизация',
                   'локальная нейросеть на ПК', 'ИИ-агент своими руками']
GITHUB_TOPICS = ["ai-agent", "ai-agents", "mcp-server", "agent-skills", "claude-code", "llm-tools", "automation",
                 "n8n", "local-llm", "ollama", "openclaw", "workflow-automation", "browser-automation"]


def hn_ai() -> list[Item]:
    """Hacker News: Show HN и обсуждения про агентов/инструменты за последние 30 дней."""
    since = int(time.time() - 30 * 86400)
    seen, items = set(), []
    with client() as c:
        for q in HN_QUERIES:
            try:
                data = c.get("https://hn.algolia.com/api/v1/search", params={
                    "query": q, "tags": "(story,show_hn)", "numericFilters": f"points>40,created_at_i>{since}",
                    "hitsPerPage": 15}).json()
            except Exception:  # noqa: BLE001
                continue
            for h in data.get("hits", []):
                oid = h.get("objectID")
                if oid in seen or not h.get("title"):
                    continue
                seen.add(oid)
                disc = f"https://news.ycombinator.com/item?id={oid}"
                items.append(Item(
                    title=h["title"], url=h.get("url") or disc, source="hackernews", source_label="Hacker News",
                    popularity=(h.get("points") or 0) + 2 * (h.get("num_comments") or 0), rank=len(items),
                    published=h.get("created_at_i") or time.time(),
                    summary=(h.get("story_text") or "")[:500], extra={"discussion": disc, "points": h.get("points")},
                ))
    items.sort(key=lambda i: i.popularity, reverse=True)
    for r, it in enumerate(items):
        it.rank = r
    return items


def github_new() -> list[Item]:
    """GitHub: новые репозитории (за 45 дней) по темам агентов/MCP/автоматизации, по звёздам."""
    since = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    seen, items = set(), []
    with client() as c:
        for topic in GITHUB_TOPICS:
            try:
                r = c.get("https://api.github.com/search/repositories", headers=headers, params={
                    "q": f"topic:{topic} created:>{since} stars:>80", "sort": "stars", "order": "desc", "per_page": 15})
                if r.status_code != 200:
                    continue
                repos = r.json().get("items", [])
            except Exception:  # noqa: BLE001
                continue
            for rp in repos:
                if rp["full_name"] in seen or not rp.get("description") or rp.get("archived") or rp.get("fork"):
                    continue
                seen.add(rp["full_name"])
                if re.search(r"\d{4}", rp["owner"]["login"]):  # частый признак накрученных звёзд
                    continue
                age_days = max(1.0, (time.time() - datetime.fromisoformat(rp["created_at"].replace("Z", "+00:00")).timestamp()) / 86400)
                items.append(Item(
                    title=f"{rp['full_name']}: {rp['description'][:160]}", url=rp["html_url"], source="github",
                    source_label="GitHub", popularity=rp["stargazers_count"] / age_days ** 0.5, rank=0,
                    published=datetime.fromisoformat(rp["pushed_at"].replace("Z", "+00:00")).timestamp(),
                    summary=rp["description"], image=f"https://opengraph.githubassets.com/1/{rp['full_name']}",
                    extra={"stars": rp["stargazers_count"], "language": rp.get("language"), "topics": rp.get("topics", [])[:8],
                           "repo": rp["full_name"], "license": (rp.get("license") or {}).get("spdx_id")},
                ))
    items.sort(key=lambda i: i.popularity, reverse=True)
    for r, it in enumerate(items):
        it.rank = r
    return items


def product_hunt() -> list[Item]:
    return fetch_feed("https://www.producthunt.com/feed", "producthunt", "Product Hunt", limit=40)


def habr_ai() -> list[Item]:
    out = []
    for url in ("https://habr.com/ru/rss/hubs/artificial_intelligence/articles/?fl=ru",
                "https://habr.com/ru/rss/hubs/machine_learning/articles/?fl=ru",
                f"https://habr.com/ru/rss/search/?q={quote('ИИ-агент')}&order=date&fl=ru",
                f"https://habr.com/ru/rss/search/?q={quote('n8n')}&order=date&fl=ru"):
        try:
            out += fetch_feed(url, "habr", "Хабр", limit=30)
        except Exception:  # noqa: BLE001
            continue
    return out


def vc_ru() -> list[Item]:
    return fetch_feed("https://vc.ru/rss", "vcru", "vc.ru", limit=60)


def devto() -> list[Item]:
    out = []
    for tag in ("aiagents", "ai", "automation", "llm", "sideprojects", "mcp"):
        try:
            out += fetch_feed(f"https://dev.to/feed/tag/{tag}", "devto", "dev.to", limit=20)
        except Exception:  # noqa: BLE001
            continue
    return out


def medium() -> list[Item]:
    out = []
    for tag in ("ai-agents", "automation", "side-hustle", "local-llm", "n8n"):
        try:
            out += fetch_feed(f"https://medium.com/feed/tag/{tag}", "medium", "Medium", limit=15)
        except Exception:  # noqa: BLE001
            continue
    return out


def reddit_ai() -> list[Item]:
    """Reddit через RSS (с серверов часто 403 — тогда пропускаем)."""
    out, errors = [], 0
    for sub in ("LocalLLaMA", "SideProject", "n8n", "AI_Agents", "ClaudeAI", "Entrepreneur"):
        try:
            out += fetch_feed(f"https://www.reddit.com/r/{sub}/top/.rss?t=week", "reddit", f"Reddit r/{sub}", limit=15)
        except Exception:  # noqa: BLE001
            errors += 1
    if errors and not out:
        raise RuntimeError("Reddit недоступен с этого сервера (403)")
    return out


def news_ai(region: str = "US") -> list[Item]:
    out = []
    for q in NEWS_QUERIES_EN:
        try:
            out += fetch_feed(f"https://news.google.com/rss/search?q={quote(q + ' when:60d')}&hl=en-US&gl=US&ceid=US:en",
                              "google_news", "Google News", limit=8)
        except Exception:  # noqa: BLE001
            pass
    for q in NEWS_QUERIES_RU:
        try:
            out += fetch_feed(f"https://news.google.com/rss/search?q={quote(q + ' when:60d')}&hl=ru&gl=RU&ceid=RU:ru",
                              "google_news", "Google Новости", limit=8)
        except Exception:  # noqa: BLE001
            pass
    import re
    for it in out:
        it.title = re.sub(r"\s+[-–—]\s+[^-–—]{2,40}$", "", it.title)
    return out


def youtube_ai(api_key: str) -> list[Item]:
    if not api_key:
        raise RuntimeError("нет YOUTUBE_API_KEY")
    from .social import youtube_search
    out = []
    for q in ("AI agent tutorial make money", "n8n automation tutorial", "local LLM setup", "ИИ агент своими руками"):
        out += youtube_search(api_key, q, "US", "ru" if any("а" <= ch <= "я" for ch in q.lower()) else "en", limit=6)
    return out


CASE_QUERIES = ["MRR", "revenue side project", "AI agent revenue", "making money AI", "passive income",
                "my SaaS", "bootstrapped profitable", "indie hacker", "first paying customers", "GPT wrapper revenue",
                "automation agency", "n8n", "AI agent built"]


def hn_cases() -> list[Item]:
    """Hacker News за всё время: истории «как я построил и сколько заработал» — вечная база знаний."""
    seen, items = set(), []
    with client() as c:
        for q in CASE_QUERIES:
            try:
                data = c.get("https://hn.algolia.com/api/v1/search", params={
                    "query": q, "tags": "story", "numericFilters": "points>120", "hitsPerPage": 20}).json()
            except Exception:  # noqa: BLE001
                continue
            for h in data.get("hits", []):
                oid = h.get("objectID")
                if oid in seen or not h.get("title"):
                    continue
                seen.add(oid)
                disc = f"https://news.ycombinator.com/item?id={oid}"
                items.append(Item(
                    title=h["title"], url=h.get("url") or disc, source="hackernews", source_label="Hacker News (архив)",
                    popularity=(h.get("points") or 0), rank=0, published=h.get("created_at_i") or time.time(),
                    summary=(h.get("story_text") or "")[:500], extra={"discussion": disc, "points": h.get("points"), "evergreen": True},
                ))
    items.sort(key=lambda i: i.popularity, reverse=True)
    for r, it in enumerate(items):
        it.rank = r
    return items
