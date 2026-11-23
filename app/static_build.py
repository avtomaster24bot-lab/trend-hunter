"""Сборка статической версии сайта для GitHub Pages.

  python -m app.static_build _site

Собирает свежие тренды → _site/data/trends.json, список готовых видео из GitHub Releases →
_site/data/videos.json, и копирует интерфейс в режиме «только просмотр»."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import httpx

from . import trends
from .config import ROOT, settings

REPO = os.getenv("GITHUB_REPOSITORY", "avtomaster24bot-lab/trend-hunter")
WORKFLOW = "generate-video.yml"


def videos_from_releases() -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    out = []
    try:
        r = httpx.get(f"https://api.github.com/repos/{REPO}/releases", params={"per_page": 50}, headers=headers, timeout=30)
        r.raise_for_status()
        releases = r.json()
    except Exception as e:  # noqa: BLE001
        print("releases:", e)
        return []
    for rel in releases:
        if not rel.get("tag_name", "").startswith("video-"):
            continue
        m = re.search(r"<!--meta\s*(\{.*?\})\s*-->", rel.get("body") or "", re.S)
        meta = json.loads(m.group(1)) if m else {}
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        mp4 = next((u for n, u in sorted(assets.items()) if n.endswith(".mp4")), None)
        if not mp4:
            continue
        parts = [u for n, u in sorted(assets.items()) if n.endswith(".mp4")]
        out.append({
            "id": rel["tag_name"], "created": meta.get("created") or time.time(),
            "status": "published" if meta.get("published") else "done",
            "topic": meta.get("topic") or {"title": rel.get("name") or rel["tag_name"]},
            "title": meta.get("script_title") or rel.get("name"),
            "minutes": meta.get("minutes"), "duration": meta.get("duration"), "size_mb": meta.get("size_mb"),
            "video": mp4, "parts": parts, "cover": assets.get("cover.jpg", ""), "release": rel.get("html_url"),
            "script_mode": meta.get("script_mode"), "log": [],
        })
    out.sort(key=lambda v: v["created"], reverse=True)
    return out


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)
    data = trends.refresh()
    (out_dir / "data" / "trends.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    vids = videos_from_releases()
    (out_dir / "data" / "videos.json").write_text(json.dumps(vids, ensure_ascii=False), encoding="utf-8")
    cfg = {
        "static": True, "repo": REPO,
        "workflow_url": f"https://github.com/{REPO}/actions/workflows/{WORKFLOW}",
        "channel": settings.telegram_channel, "region": settings.region, "words_per_minute": settings.words_per_minute,
        "needs_password": False, "tts_provider": "edge", "edge_voice": settings.edge_voice,
        "keys": {"llm": os.getenv("HAS_LLM") == "true", "llm_model": settings.llm_model if os.getenv("HAS_LLM") == "true" else None,
                 "youtube": bool(settings.youtube_api_key), "instagram": bool(settings.apify_token),
                 "telegram": os.getenv("HAS_TELEGRAM") == "true", "openai_tts": False, "elevenlabs": False},
        "built": time.time(),
    }
    (out_dir / "data" / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    static = ROOT / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/', 'href="./').replace('src="/static/', 'src="./')
    html = html.replace("<head>", "<head>\n<script>window.TH_STATIC = true;</script>", 1)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    for f in ("app.js", "style.css"):
        shutil.copy(static / f, out_dir / f)
    (out_dir / ".nojekyll").write_text("")
    print(f"Готово: {len(data['topics'])} тем, {len(vids)} видео → {out_dir}")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "_site"))
