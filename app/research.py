"""Сбор материала по выбранной теме: статьи, Википедия, свежие новости, YouTube, картинки."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import trafilatura

from .collectors import rss, social
from .collectors.base import client
from .config import settings


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml", "Accept-Language": "ru,en;q=0.8",
}


def _fetch_article(url: str) -> dict | None:
    if not url or "news.google.com" in url or "trends.google" in url:
        return None
    try:
        with client(timeout=12) as c:
            r = c.get(url, headers=BROWSER_HEADERS)
            if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
                return None
            html = r.text
        text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True) or ""
        meta = trafilatura.extract_metadata(html)
        img = ""
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html)
        if m:
            img = m.group(1)
        if len(text) < 200:
            return None
        return {"url": url, "title": (meta.title if meta else "") or url, "text": text[:12000], "image": img}
    except Exception:  # noqa: BLE001
        return None


def wikipedia(query: str, lang: str, n: int = 3) -> list[dict]:
    api = f"https://{lang}.wikipedia.org/w/api.php"
    out = []
    try:
        with client() as c:
            hits = c.get(api, params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": n}).json()
            titles = [h["title"] for h in hits.get("query", {}).get("search", [])]
            if not titles:
                return []
            for title in titles:
                pages = c.get(api, params={
                    "action": "query", "prop": "extracts|pageimages", "explaintext": 1,
                    "titles": title, "format": "json", "pithumbsize": 1280, "redirects": 1,
                }).json()
                for p in pages.get("query", {}).get("pages", {}).values():
                    txt = re.split(r"\n== (Примечания|Ссылки|Литература|См\. также|References|See also) ==", p.get("extract") or "")[0].strip()
                    if len(txt) > 300 and "может означать" not in txt[:300]:
                        out.append({"url": f"https://{lang}.wikipedia.org/wiki/{p['title'].replace(' ', '_')}",
                                    "title": f"Википедия: {p['title']}", "text": txt[:15000],
                                    "image": (p.get("thumbnail") or {}).get("source", "")})
    except Exception:  # noqa: BLE001
        pass
    return out


def gather(topic: dict, log=print) -> dict:
    query = topic.get("query") or topic["title"]
    docs: list[dict] = []
    images: list[str] = [i["image"] for i in topic.get("items", []) if i.get("image")]

    # 1) Свежие новости по запросу (заголовки + анонсы)
    news = []
    try:
        news = rss.google_news_search(query, settings.region, settings.language, limit=15)
    except Exception as e:  # noqa: BLE001
        log(f"Google Новости: {e}")
    headlines = [{"title": n.title, "summary": n.summary, "url": n.url, "source": n.source_label} for n in news]
    headlines += [{"title": i["title"], "summary": i.get("summary", ""), "url": i["url"], "source": i["source_label"]}
                  for i in topic.get("items", [])]

    # 2) Полные тексты статей из кластера
    urls = list(dict.fromkeys(i["url"] for i in topic.get("items", []) if i.get("url")))[:10]
    log(f"Читаю статьи: {len(urls)}")
    with ThreadPoolExecutor(max_workers=6) as ex:
        for art in ex.map(_fetch_article, urls):
            if art:
                docs.append(art)
                if art["image"]:
                    images.append(art["image"])

    # 3) Википедия — справочный контекст (для длинного заголовка ищем по именам собственным)
    wq = query
    if len(query.split()) > 4:
        caps = [w.strip("«»\"',.:;!?()") for w in query.split() if w[:1].isupper() or w[:1] in "«\""]
        caps = [c for c in caps if len(c) >= 3]
        wq = " ".join(caps[:3]) or query
    for w in wikipedia(wq, settings.language):
        docs.append(w)
        if w["image"]:
            images.append(w["image"])

    # 4) YouTube — что говорят в видео (описания)
    try:
        for v in social.youtube_search(settings.youtube_api_key, query, settings.region, settings.language):
            headlines.append({"title": v.title, "summary": v.summary[:300], "url": v.url, "source": "YouTube"})
            if v.image:
                images.append(v.image)
    except Exception as e:  # noqa: BLE001
        log(f"YouTube поиск: {e}")

    # убираем дубли заголовков
    seen, uniq = set(), []
    for h in headlines:
        k = h["title"].lower()[:60]
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    words = sum(len(d["text"].split()) for d in docs) + sum(len((h["title"] + " " + h["summary"]).split()) for h in uniq)
    return {"query": query, "docs": docs, "headlines": uniq[:30], "images": list(dict.fromkeys(images))[:30], "words": words}
