"""Кластеризация новостей в темы и оценка «горячести прямо сейчас»."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import defaultdict

from .collectors import collect_all
from .collectors.base import Item
from .config import settings

SOURCE_WEIGHT = {
    "github": 1.0, "producthunt": 1.0, "devto": 0.8, "medium": 0.8, "vcru": 0.9,
    "google_trends": 1.4, "youtube": 1.3, "instagram": 1.1, "reddit": 1.0, "google_news": 1.0,
    "lenta": 0.9, "tass": 0.8, "hackernews": 0.9, "habr": 0.7, "custom_rss": 0.8,
}

STOP = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему
теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они
тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого
какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть
после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть
том нельзя такой им более всегда конечно всю между это года году год стал стало заявил заявила рассказал назвал россии рф новости
the a an of to in and or for on with at by from is are was be as it its this that new how why what you your about after over into
show hn ask vs not just more than will can has have our we they их также ещё
""".split())

_END = re.compile(r"(ами|ями|ого|его|ому|ему|ыми|ими|ой|ей|ий|ый|ая|яя|ое|ее|ые|ие|ов|ев|ах|ях|ам|ям|ом|ем|а|я|ы|и|у|ю|е|о|ь)$")
WORD = re.compile(r"[a-zа-яё0-9]+", re.I)


def stems(text: str) -> set[str]:
    out = set()
    for w in WORD.findall(text.lower().replace("ё", "е")):
        if len(w) < 3 or w in STOP or w.isdigit():
            continue
        if len(w) > 4 and not w.isascii():
            w = _END.sub("", w)
        out.add(w[:6])  # грубый стемминг: окончания + обрезка до 6 букв
    return out


def _item_scores(items: list[Item]) -> dict[int, float]:
    by_src: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        by_src[it.source].append(it)
    now = time.time()
    scores = {}
    for src, lst in by_src.items():
        pops = sorted(math.log1p(max(0, i.popularity)) for i in lst)
        n = len(lst)
        for it in lst:
            rank_score = max(0.0, 1 - it.rank / max(n, 1))
            lp = math.log1p(max(0, it.popularity))
            pct = (sum(1 for p in pops if p <= lp) / n) if n else 0
            age_h = max(0, (now - it.published) / 3600)
            fresh = math.exp(-age_h / 36)
            prac = (it.extra or {}).get("practical", {}).get("score")
            boost = 1.0 if prac is None else (0.2 + prac / 60)
            scores[id(it)] = SOURCE_WEIGHT.get(src, 0.8) * (0.5 * rank_score + 0.5 * pct) * (0.35 + 0.65 * fresh) * boost
    return scores


def recommend_minutes(n_items: int, n_sources: int, research_words: int | None = None) -> int:
    """Рекомендуемая длительность ролика 1–30 мин по «богатству» темы."""
    base = 1 + 1.3 * (n_items - 1) + 1.5 * (n_sources - 1)
    if research_words is not None:
        # Пересказывать можно примерно треть собранного материала
        by_text = research_words / 3 / settings.words_per_minute
        base = 0.4 * base + 0.6 * by_text
    return int(max(1, min(30, round(base))))


def cluster(items: list[Item]) -> list[dict]:
    scores = _item_scores(items)
    items = [i for i in items if i.title]
    items.sort(key=lambda i: scores[id(i)], reverse=True)
    # Частотность слов: слишком общие запросы («россия») не склеивают темы
    df: dict[str, int] = defaultdict(int)
    for it in items:
        for w in stems(it.title):
            df[w] += 1
    clusters: list[dict] = []
    for it in items:
        title_st = stems(it.title)
        if not title_st:
            continue
        best, best_ov = None, 0.0
        for c in clusters:
            seed = c["seed_stems"]
            q = c.get("query_stems")
            ctx = seed - (q or set())
            if q and q <= title_st and (len(q) >= 2 or title_st & ctx):
                ov = 1.0
            elif it.source == "google_trends" and title_st <= seed and (len(title_st) >= 2 or df[next(iter(title_st))] <= 2):
                ov = 1.0
            else:
                shared = {w for w in title_st & seed if df[w] <= 5}  # частые слова («agent», «open») не склеивают
                if len(shared) < 2:
                    continue
                ov = len(shared) / max(1, min(len(title_st), len(seed)))
                if ov < 0.5:
                    continue
            if ov > best_ov:
                best, best_ov = c, ov
        if best is not None and best_ov >= 0.4:
            best["items"].append(it)
            if it.source == "google_trends" and not best.get("query_stems"):
                best["query"], best["query_stems"] = it.title, title_st
        else:
            seed = set(title_st)
            if it.source == "google_trends":
                seed |= stems(it.summary[:200])
            clusters.append({
                "items": [it], "seed_stems": seed,
                "query": it.title if it.source == "google_trends" else "",
                "query_stems": title_st if it.source == "google_trends" else None,
            })

    topics = []
    for c in clusters:
        its = c["items"]
        sources = {i.source for i in its}
        raw = sum(scores[id(i)] for i in its) * (1 + 0.6 * (len(sources) - 1))
        headline = next((i.title for i in its if i.source != "google_trends"), its[0].title)
        query = c["query"] or headline
        image = next((i.image for i in its if i.image and i.source != "google_trends"), "") or next((i.image for i in its if i.image), "")
        best = max(its, key=lambda i: (i.extra or {}).get("practical", {}).get("score", 0))
        prac = (best.extra or {}).get("practical")
        if prac:
            headline = best.title
            query = c["query"] or best.title
        topics.append({
            "id": "t" + hashlib.md5(query.encode()).hexdigest()[:10],
            "practical": prac and {k: prac[k] for k in ("score", "type", "type_ru", "level", "needs", "money")},
            "url": best.url,
            "title": headline[:1].upper() + headline[1:],
            "query": query,
            "raw": raw,
            "sources": sorted({i.source_label.split(" · ")[0] for i in its}),
            "items": [i.to_dict() for i in its[:12]],
            "image": image,
            "recommended_minutes": recommend_minutes(len(its), len(sources)),
        })
    # итоговый порядок: «горячо» × «применимо у себя» × «потенциал дохода»
    for t in topics:
        p = t.get("practical") or {}
        t["raw"] *= (0.4 + p.get("score", 40) / 100) * {"высокий": 1.8, "средний": 1.2}.get(p.get("money"), 1.0)
    topics.sort(key=lambda t: t["raw"], reverse=True)
    top = max([t["raw"] for t in topics] + [1e-9])
    for t in topics:
        t["hotness"] = max(1, round(100 * math.sqrt(max(0.0, t["raw"]) / top)))
        del t["raw"]
    return topics


TRENDS_FILE = settings.data_dir / "trends.json"


def _enrich(kb: list[dict], topics: list[dict]) -> None:
    """Русские заголовки/описания, репозиторий + «как собрать», картинки — для базы и для находок."""
    from . import enrich
    pseudo = []
    for t in topics:
        its = t.get("items") or [{}]
        best = next((i for i in its if i.get("url") == t.get("url")), its[0])
        pseudo.append({"id": t["id"], "title": t["title"], "url": t.get("url", ""), "summary": best.get("summary", ""),
                       "source": best.get("source", ""), "extra": best.get("extra") or {}, "image": t.get("image", ""),
                       "type": (t.get("practical") or {}).get("type"), "items": its})
    try:
        enrich.enrich(kb + pseudo)
    except Exception as ex:  # noqa: BLE001 — сайт должен собраться даже без перевода
        print(f"Обогащение не удалось: {ex}")
        return
    for t, p in zip(topics, pseudo):
        for k in ("title_ru", "title_orig", "summary_ru", "repo", "repo_url", "build", "image"):
            if p.get(k):
                t[k] = p[k]
        t["steps"] = __import__("app.practical", fromlist=["x"]).apply_steps({**p, **(t.get("practical") or {})}) if t.get("practical") else []


def refresh() -> dict:
    from . import knowledge, practical
    items, status = collect_all()
    keep = []
    for it in items:
        a = practical.analyze(it.title, it.summary, it.source, it.extra)
        it.extra = {**(it.extra or {}), "practical": a}
        if a["is_ai"] and a["score"] >= knowledge.MIN_SCORE:
            keep.append(it)
    topics = cluster(keep)[:60]
    kb, new = knowledge.merge([i.to_dict() for i in items])
    knowledge.enrich_with_llm(kb)
    _enrich(kb, topics)
    knowledge.save(kb)
    data = {"updated": time.time(), "region": settings.region, "status": status, "topics": topics,
            "collected": len(items), "practical": len(keep), "kb_new": len(new), "kb_total": len(kb)}
    TRENDS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def load(max_age: int = 1800) -> dict:
    if TRENDS_FILE.exists():
        data = json.loads(TRENDS_FILE.read_text(encoding="utf-8"))
        if time.time() - data.get("updated", 0) < max_age:
            return data
    return refresh()


def find_topic(topic_id: str) -> dict | None:
    data = load(max_age=10**9)
    return next((t for t in data["topics"] if t["id"] == topic_id), None)
