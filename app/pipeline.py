"""Задания: тема → материалы → сценарий → озвучка → видео → (Telegram)."""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from html import escape

from . import research, script, telegram, trends, video
from .config import settings

JOBS_DIR = settings.data_dir / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()
_queue_sem = threading.Semaphore(1)  # одно видео за раз — бережём CPU


def _path(job_id: str):
    return JOBS_DIR / job_id / "job.json"


def save(job: dict) -> None:
    p = _path(job["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        p.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")


def get(job_id: str) -> dict | None:
    p = _path(job_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def list_jobs(limit: int = 30) -> list[dict]:
    jobs = []
    for p in JOBS_DIR.glob("*/job.json"):
        try:
            jobs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    jobs.sort(key=lambda j: j.get("created", 0), reverse=True)
    for j in jobs:
        j.pop("script", None)
    return jobs[:limit]


def create(topic: dict, minutes: int | None, publish: bool, channel: str | None = None,
           tts_provider: str | None = None, voice: str | None = None) -> dict:
    job = {
        "id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
        "created": time.time(), "status": "queued", "progress": 0, "log": [],
        "topic": {k: topic[k] for k in ("id", "title", "query", "hotness", "sources", "recommended_minutes", "practical", "url") if k in topic},
        "minutes": minutes, "publish": publish, "channel": channel or settings.telegram_channel,
        "tts_provider": tts_provider or settings.tts_provider, "voice": voice,
    }
    save(job)
    threading.Thread(target=run, args=(job, topic), daemon=True).start()
    return job


def run(job: dict, topic: dict) -> dict:
    def log(msg: str, progress: int | None = None):
        job["log"].append(f"{time.strftime('%H:%M:%S')} {msg}")
        if progress is not None:
            job["progress"] = progress
        save(job)

    with _queue_sem:
        try:
            job["status"] = "running"
            log("Собираю материалы по теме", 5)
            res = research.gather(topic, log=log)
            rec = trends.recommend_minutes(len(topic.get("items", [])), len(topic.get("sources", [])), res["words"])
            job["recommended_minutes"] = rec
            minutes = int(job.get("minutes") or rec)
            minutes = max(1, min(30, minutes))
            job["minutes"] = minutes
            log(f"Материалов: {len(res['docs'])} текстов, {len(res['headlines'])} заголовков, ~{res['words']} слов. "
                f"Рекомендую {rec} мин, делаю {minutes} мин", 20)

            sc = script.make_script(topic, res, minutes, job["channel"], log=log)
            job["script"] = sc
            words = sum(len(s["narration"].split()) for s in sc["segments"])
            log(f"Сценарий готов ({sc['mode']}): {len(sc['segments'])} слайдов, {words} слов ≈ "
                f"{words / settings.words_per_minute:.1f} мин", 35)
            if sc["mode"] == "extractive" and words < minutes * settings.words_per_minute * 0.7:
                log("⚠️ Без LLM текста хватило на меньшую длительность. Добавьте LLM_API_KEY для полноценного сценария.")

            workdir = JOBS_DIR / job["id"]
            imgs = video.download_images(res["images"], workdir / "img")
            log(f"Картинок: {len(imgs)}", 40)
            out = video.build_video(sc, imgs, workdir, job["channel"], log=lambda m: log(m),
                                    tts_provider=job.get("tts_provider"), voice=job.get("voice"))
            job["video"] = f"/files/{job['id']}/{out.name}"
            job["cover"] = f"/files/{job['id']}/cover.jpg"
            job["duration"] = round(video.duration(out))
            job["size_mb"] = round(out.stat().st_size / 1e6, 1)
            log(f"Видео готово: {job['duration'] // 60}:{job['duration'] % 60:02d}, {job['size_mb']} МБ", 90)
            job["status"] = "done"
            if job.get("publish"):
                try:
                    publish(job, log=log)
                except Exception as e:  # noqa: BLE001 — видео готово, ошибка только в отправке
                    job["error"] = f"Публикация: {e}"
                    log(f"Ошибка публикации: {e}")
            job["progress"] = 100
            save(job)
        except Exception as e:  # noqa: BLE001
            job["status"] = "error"
            job["error"] = str(e)
            log(f"Ошибка: {e}")
            traceback.print_exc()
    return job


def caption_for(job: dict) -> str:
    sc = job.get("script") or {}
    t = job["topic"]
    title = escape(sc.get("title") or t["title"])
    src = escape(", ".join(t.get("sources", [])[:5]))
    p = t.get("practical")
    if p:
        link = f"\n\n🔗 Источник: {escape(t.get('url', ''))}" if t.get("url") else ""
        return (f"🛠 <b>{title}</b>\n\nПрактичная ИИ-находка, которую можно повторить на своём ПК.\n"
                f"Тип: {escape(p.get('type_ru', ''))} · Сложность: {escape(p.get('level', ''))} · Нужно: {escape(', '.join(p.get('needs', [])))}"
                f"{link}\n\n#ии #агенты #автоматизация #машинадохода")
    return (f"🔥 <b>{title}</b>\n\nТема, которая набирает популярность прямо сейчас.\n"
            f"Горячесть: {t.get('hotness', '—')}/100 · Источники: {src}\n\n#тренды #новости")


def publish(job: dict, log=print) -> dict:
    workdir = JOBS_DIR / job["id"]
    files = video.fit_size(workdir / "video.mp4", settings.telegram_max_mb, log=log)
    log(f"Отправляю в Telegram {telegram.normalize_channel(job['channel'])}: {len(files)} файл(ов)")
    res = telegram.send_video(files, caption_for(job), job["channel"], thumb=workdir / "thumb.jpg",
                              width=settings.video_width, height=settings.video_height,
                              durations=[video.duration(f) for f in files])
    job["published"] = {"at": time.time(), "message_ids": [r.get("message_id") for r in res]}
    job["status"] = "published"
    log("Опубликовано в Telegram ✅", 100)
    return job


def publish_async(job_id: str) -> dict:
    job = get(job_id)
    if not job:
        raise KeyError(job_id)

    def _go():
        def log(msg, progress=None):
            job["log"].append(f"{time.strftime('%H:%M:%S')} {msg}")
            save(job)
        try:
            job["status"] = "publishing"
            save(job)
            publish(job, log=log)
            save(job)
        except Exception as e:  # noqa: BLE001
            job["status"] = "done"
            job["error"] = f"Публикация: {e}"
            log(f"Ошибка публикации: {e}")
    threading.Thread(target=_go, daemon=True).start()
    return job
