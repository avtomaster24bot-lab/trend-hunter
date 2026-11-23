"""Командная строка и режим «автопилот» (для GitHub Actions / cron).

  python -m app.cli trends                 — показать топ трендов
  python -m app.cli auto [--minutes 5] [--publish]   — взять самую горячую новую тему, сделать видео и (опц.) опубликовать
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


def auto(minutes: int | None, publish: bool, max_minutes: int | None = None) -> dict:
    data = trends.refresh()
    posted = _posted()
    for name, st in data["status"].items():
        print(f"  {name}: {st}")
    topic = next((t for t in data["topics"] if t["id"] not in posted and t["query"].lower() not in posted.values()), None)
    if not topic:
        raise SystemExit("Нет новых тем")
    print(f"Тема: {topic['title']} (горячесть {topic['hotness']}, рекомендовано {topic['recommended_minutes']} мин)")
    job = {
        "id": time.strftime("%Y%m%d-%H%M%S-auto"), "created": time.time(), "status": "queued", "progress": 0,
        "log": [], "topic": {k: topic[k] for k in ("id", "title", "query", "hotness", "sources", "recommended_minutes")},
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
    return job


def main(argv=None):
    ap = argparse.ArgumentParser(prog="trend-hunter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("trends")
    a = sub.add_parser("auto")
    a.add_argument("--minutes", type=int, default=None, help="1–30; по умолчанию — рекомендованное")
    a.add_argument("--max-minutes", type=int, default=None, help="потолок для рекомендованной длительности")
    a.add_argument("--publish", action="store_true")
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
        auto(args.minutes, args.publish, args.max_minutes)
    elif args.cmd == "sample":
        job = auto(args.minutes, publish=False)
        src = pipeline.JOBS_DIR / job["id"] / "video.mp4"
        shutil.copy(src, args.out)
        print("Сохранено:", args.out)


if __name__ == "__main__":
    sys.exit(main())
