"""Командная строка и режим «автопилот» (для GitHub Actions / cron).

  python -m app.cli trends                 — показать топ трендов
  python -m app.cli auto [--minutes 5] [--publish]   — взять самую горячую новую тему, сделать видео и (опц.) опубликовать
  python -m app.cli auto --topic "nvidia" --minutes 3  — конкретная тема (из топа или любой запрос)
  python -m app.cli sample --out sample.mp4 — короткий тестовый ролик без ключей
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time

from . import pipeline, trends
from .config import settings

POSTED = settings.data_dir / "posted.json"


def _posted() -> dict:
    return json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}


def _adhoc_topic(text: str) -> dict:
    """Тема, которой нет в текущем топе: собираем свежие новости по запросу."""
    import hashlib
    from .collectors import rss
    items = []
    try:
        items = rss.google_news_search(text, settings.region, settings.language, limit=12)
    except Exception as e:  # noqa: BLE001
        print("Google Новости:", e)
    srcs = sorted({i.source_label for i in items}) or ["Запрос"]
    from .practical import analyze
    a = analyze(text, " ".join(i.title for i in items[:5]))
    return {"practical": {k: a[k] for k in ("score", "type", "type_ru", "level", "needs", "money")},
            "url": items[0].url if items else "","id": "t" + hashlib.md5(text.encode()).hexdigest()[:10], "title": text[:1].upper() + text[1:], "query": text,
            "hotness": 0, "sources": srcs, "items": [i.to_dict() for i in items], "image": "",
            "recommended_minutes": trends.recommend_minutes(len(items), len(srcs))}


def pick_topic(data: dict, wanted: str | None, posted: dict) -> dict | None:
    if wanted:
        w = wanted.strip().lower()
        for t in data["topics"]:
            if w in (t["id"].lower(), t["query"].lower(), t["title"].lower()):
                return t
        for t in data["topics"]:
            if w in t["title"].lower() or w in t["query"].lower():
                return t
        return _adhoc_topic(wanted.strip())
    fresh = [t for t in data["topics"] if t["id"] not in posted and t["query"].lower() not in posted.values()]
    # для автопилота — лучшая находка с потенциалом дохода из первой десятки
    money = [t for t in fresh[:10] if (t.get("practical") or {}).get("money") in ("высокий", "средний")]
    return (money or fresh or [None])[0]


def auto(minutes: int | None, publish: bool, max_minutes: int | None = None, topic_text: str | None = None,
         meta_out: str | None = None) -> dict:
    data = trends.refresh()
    posted = _posted()
    for name, st in data["status"].items():
        print(f"  {name}: {st}")
    topic = pick_topic(data, topic_text, posted)
    if not topic:
        raise SystemExit("Нет новых тем")
    print(f"Тема: {topic['title']} (горячесть {topic['hotness']}, рекомендовано {topic['recommended_minutes']} мин)")
    job = {
        "id": time.strftime("%Y%m%d-%H%M%S-auto"), "created": time.time(), "status": "queued", "progress": 0,
        "log": [], "topic": {k: topic[k] for k in ("id", "title", "query", "hotness", "sources", "recommended_minutes", "practical", "url", "title_ru", "repo_url") if k in topic},
        "minutes": minutes, "publish": publish, "channel": settings.telegram_channel,
        "tts_provider": settings.tts_provider, "voice": None,
    }
    if minutes is None and max_minutes:
        job["minutes"] = min(max_minutes, topic["recommended_minutes"])
    pipeline.save(job)
    job = pipeline.run(job, topic)
    print("\n".join(job["log"]))
    if job["status"] == "error":
        raise SystemExit(1)
    if publish and job["status"] == "published":
        posted[topic["id"]] = topic["query"].lower()
        POSTED.write_text(json.dumps(posted, ensure_ascii=False), encoding="utf-8")
    if meta_out:
        meta = {k: job.get(k) for k in ("id", "created", "status", "minutes", "recommended_minutes", "duration",
                                         "size_mb", "published", "error")}
        meta["topic"] = job["topic"]
        meta["script_title"] = (job.get("script") or {}).get("title")
        meta["script_mode"] = (job.get("script") or {}).get("mode")
        meta["dir"] = str(pipeline.JOBS_DIR / job["id"])
        with open(meta_out, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
    return job


def main(argv=None):
    ap = argparse.ArgumentParser(prog="trend-hunter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("trends")
    a = sub.add_parser("auto")
    a.add_argument("--minutes", type=int, default=None, help="1–30; по умолчанию — рекомендованное")
    a.add_argument("--max-minutes", type=int, default=None, help="потолок для рекомендованной длительности")
    a.add_argument("--publish", action="store_true")
    a.add_argument("--topic", default=None, help="тема: id, запрос или любой текст; пусто = самая горячая")
    a.add_argument("--meta-out", default=None, help="записать сведения о ролике в JSON")
    s = sub.add_parser("sample")
    s.add_argument("--minutes", type=int, default=1)
    s.add_argument("--out", default="sample.mp4")
    args = ap.parse_args(argv)

    if args.cmd == "trends":
        d = trends.refresh()
        for name, st in d["status"].items():
            print(f"  {name}: {st}")
        for t in d["topics"][:20]:
            print(f"{t['hotness']:>3} | {t['recommended_minutes']:>2} мин | {', '.join(t['sources'])} | {t['title']}")
    elif args.cmd == "auto":
        auto(args.minutes, args.publish, args.max_minutes, args.topic or None, args.meta_out)
    elif args.cmd == "sample":
        job = auto(args.minutes, publish=False)
        src = pipeline.JOBS_DIR / job["id"] / "video.mp4"
        shutil.copy(src, args.out)
        print("Сохранено:", args.out)


if __name__ == "__main__":
    sys.exit(main())
