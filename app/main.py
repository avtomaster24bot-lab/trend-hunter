"""Веб-сервер «Trend Hunter»: дашборд трендов, генерация видео, публикация в Telegram."""
from __future__ import annotations

import threading
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, telegram, trends
from .config import ROOT, settings

app = FastAPI(title="Trend Hunter", version="1.0")
STATIC = ROOT / "app" / "static"


def _auth(pw: str | None):
    if settings.admin_password and pw != settings.admin_password:
        raise HTTPException(401, "Нужен пароль администратора (ADMIN_PASSWORD)")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def config():
    s = settings
    return {
        "channel": s.telegram_channel, "region": s.region, "words_per_minute": s.words_per_minute,
        "needs_password": bool(s.admin_password),
        "keys": {
            "llm": bool(s.llm_api_key), "llm_model": s.llm_model if s.llm_api_key else None,
            "youtube": bool(s.youtube_api_key), "instagram": bool(s.apify_token),
            "telegram": bool(s.telegram_bot_token), "openai_tts": bool(s.openai_api_key),
            "elevenlabs": bool(s.elevenlabs_api_key),
        },
        "tts_provider": s.tts_provider, "edge_voice": s.edge_voice,
        "telegram_max_mb": s.telegram_max_mb,
    }


@app.get("/api/trends")
def get_trends(refresh: bool = False):
    return trends.refresh() if refresh else trends.load()


class JobIn(BaseModel):
    topic_id: str
    minutes: int | None = Field(default=None, ge=1, le=30)
    publish: bool = False
    channel: str | None = None
    tts_provider: str | None = None


@app.post("/api/jobs")
def create_job(body: JobIn, x_admin_password: str | None = Header(default=None)):
    _auth(x_admin_password)
    topic = trends.find_topic(body.topic_id)
    if not topic:
        raise HTTPException(404, "Тема не найдена — обновите тренды")
    return pipeline.create(topic, body.minutes, body.publish, body.channel, body.tts_provider)


@app.get("/api/jobs")
def jobs():
    return pipeline.list_jobs()


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = pipeline.get(job_id)
    if not j:
        raise HTTPException(404)
    return j


@app.post("/api/jobs/{job_id}/publish")
def publish(job_id: str, x_admin_password: str | None = Header(default=None)):
    _auth(x_admin_password)
    j = pipeline.get(job_id)
    if not j or j.get("status") not in ("done", "published"):
        raise HTTPException(400, "Видео ещё не готово")
    pipeline.publish_async(job_id)
    return {"ok": True}


@app.get("/api/knowledge")
def get_knowledge():
    from . import knowledge
    return knowledge.load()


@app.get("/api/roadmap")
def get_roadmap():
    from . import knowledge
    return knowledge.roadmap(knowledge.load())


@app.get("/api/telegram/check")
def tg_check():
    try:
        return telegram.check()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


app.mount("/files", StaticFiles(directory=pipeline.JOBS_DIR), name="files")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# Встроенный автопостинг (если сервер работает постоянно): AUTO_POST_EVERY_HOURS=6
def _auto_loop(hours: float):
    from .cli import auto
    time.sleep(60)
    while True:
        try:
            auto(minutes=None, publish=True)
        except Exception as e:  # noqa: BLE001
            print("auto-post error:", e)
        time.sleep(hours * 3600)


@app.on_event("startup")
def _startup():
    import os
    h = float(os.getenv("AUTO_POST_EVERY_HOURS", "0") or 0)
    if h > 0:
        threading.Thread(target=_auto_loop, args=(h,), daemon=True).start()
