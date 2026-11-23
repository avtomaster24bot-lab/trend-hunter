"""Публикация в Telegram-канал через Bot API (бот должен быть администратором канала)."""
from __future__ import annotations

from pathlib import Path

import httpx

from .config import settings


def normalize_channel(ch: str) -> str:
    ch = ch.strip()
    for pre in ("https://t.me/", "http://t.me/", "t.me/"):
        if ch.startswith(pre):
            ch = "@" + ch[len(pre):].strip("/")
    if not ch.startswith("@") and not ch.lstrip("-").isdigit():
        ch = "@" + ch
    return ch


def send_video(files: list[Path], caption: str, channel: str | None = None, thumb: Path | None = None,
               width: int | None = None, height: int | None = None, durations: list[float] | None = None) -> list[dict]:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")
    chat = normalize_channel(channel or settings.telegram_channel)
    url = f"{settings.telegram_api_url}/bot{token}/sendVideo"
    results = []
    for i, f in enumerate(files):
        cap = caption if len(files) == 1 else f"Часть {i + 1}/{len(files)}\n\n{caption}"
        data = {"chat_id": chat, "caption": cap[:1024], "parse_mode": "HTML", "supports_streaming": "true"}
        if width:
            data.update(width=str(width), height=str(height))
        if durations and i < len(durations):
            data["duration"] = str(int(durations[i]))
        with f.open("rb") as fh:
            files_payload = {"video": (f.name, fh, "video/mp4")}
            if thumb and thumb.exists():
                files_payload["thumbnail"] = ("thumb.jpg", thumb.open("rb"), "image/jpeg")
            r = httpx.post(url, data=data, files=files_payload, timeout=600)
        try:
            js = r.json()
        except ValueError:
            js = {"ok": False, "description": f"HTTP {r.status_code}: {r.text[:200]}"}
        if not js.get("ok"):
            raise RuntimeError(f"Telegram: {js.get('description', r.text[:200])}")
        results.append(js["result"])
    return results


def check() -> dict:
    token = settings.telegram_bot_token
    if not token:
        return {"ok": False, "error": "нет TELEGRAM_BOT_TOKEN"}
    me = httpx.get(f"{settings.telegram_api_url}/bot{token}/getMe", timeout=20).json()
    chat = httpx.get(f"{settings.telegram_api_url}/bot{token}/getChat",
                     params={"chat_id": normalize_channel(settings.telegram_channel)}, timeout=20).json()
    return {"ok": me.get("ok") and chat.get("ok"), "bot": me.get("result", {}).get("username"),
            "channel": chat.get("result", {}).get("title"), "error": chat.get("description")}
