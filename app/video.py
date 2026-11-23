"""Сборка ролика: слайды (картинки темы + тезисы) + субтитры + мужская озвучка → MP4 через ffmpeg."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import tts
from .collectors.base import client
from .config import settings

FONT_CANDIDATES = [
    os.getenv("FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
BOLD_CANDIDATES = [
    os.getenv("FONT_BOLD_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
ACCENT = (255, 77, 46)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in BOLD_CANDIDATES if bold else FONT_CANDIDATES:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} ошибка: {p.stderr[-800:]}")
    return p.stdout


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])


# ---------- картинки ----------

def download_images(urls: list[str], folder: Path, limit: int = 12) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)

    def get(args):
        i, url = args
        try:
            with client(timeout=15) as c:
                r = c.get(url)
                r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if im.width < 300 or im.height < 200:
                return None
            p = folder / f"img{i:02d}.jpg"
            im.save(p, quality=90)
            return p
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(get, enumerate(urls[: limit * 2])))
    return [p for p in res if p][:limit]


def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _background(img: Path | None, w: int, h: int, idx: int) -> Image.Image:
    if img:
        try:
            base = _cover(Image.open(img).convert("RGB"), w, h).filter(ImageFilter.GaussianBlur(1.2))
            dark = Image.new("RGB", (w, h), (8, 10, 20))
            return Image.blend(base, dark, 0.55)
        except Exception:  # noqa: BLE001
            pass
    # градиент, если картинки нет
    palettes = [((18, 18, 40), (70, 20, 60)), ((10, 30, 50), (20, 80, 90)), ((40, 15, 15), (110, 40, 20))]
    a, b = palettes[idx % len(palettes)]
    g = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(g)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    return g


def render_slide(seg: dict, img: Path | None, idx: int, total: int, channel: str, topic_title: str) -> Image.Image:
    w, h = settings.video_width, settings.video_height
    s = w / 1280
    im = _background(img, w, h, idx)
    d = ImageDraw.Draw(im, "RGBA")
    # верхняя плашка
    d.rectangle([0, 0, w, int(56 * s)], fill=(0, 0, 0, 150))
    d.rectangle([int(24 * s), int(16 * s), int(36 * s), int(40 * s)], fill=ACCENT)
    d.text((int(46 * s), int(14 * s)), "TREND HUNTER · В ТРЕНДЕ СЕЙЧАС", font=_font(int(22 * s), True), fill="white")
    ch = channel.replace("https://t.me/", "@")
    f = _font(int(20 * s))
    d.text((w - d.textlength(ch, font=f) - int(24 * s), int(17 * s)), ch, font=f, fill=(220, 220, 220))
    # заголовок
    fh = _font(int(46 * s), True)
    y = int(100 * s)
    for line in _wrap(d, seg.get("heading", ""), fh, w - int(120 * s))[:3]:
        d.text((int(60 * s), y), line, font=fh, fill="white", stroke_width=2, stroke_fill=(0, 0, 0))
        y += int(58 * s)
    d.rectangle([int(60 * s), y + int(6 * s), int(160 * s), y + int(12 * s)], fill=ACCENT)
    y += int(36 * s)
    # тезисы
    fb = _font(int(30 * s))
    for b in (seg.get("bullets") or [])[:4]:
        lines = _wrap(d, str(b), fb, w - int(170 * s))[:2]
        d.ellipse([int(64 * s), y + int(12 * s), int(78 * s), y + int(26 * s)], fill=ACCENT)
        for line in lines:
            d.text((int(96 * s), y), line, font=fb, fill=(240, 240, 240), stroke_width=1, stroke_fill=(0, 0, 0))
            y += int(40 * s)
        y += int(14 * s)
    # прогресс
    d.rectangle([0, h - int(6 * s), w, h], fill=(255, 255, 255, 40))
    d.rectangle([0, h - int(6 * s), int(w * (idx + 1) / total), h], fill=ACCENT)
    return im


def add_subtitle(slide: Image.Image, text: str) -> Image.Image:
    im = slide.copy()
    w, h = im.size
    s = w / 1280
    d = ImageDraw.Draw(im, "RGBA")
    f = _font(int(32 * s), True)
    lines = _wrap(d, text, f, w - int(200 * s))[:3]
    lh = int(44 * s)
    box_h = lh * len(lines) + int(24 * s)
    top = h - int(40 * s) - box_h
    d.rounded_rectangle([int(80 * s), top, w - int(80 * s), top + box_h], radius=int(14 * s), fill=(0, 0, 0, 175))
    y = top + int(12 * s)
    for line in lines:
        tw = d.textlength(line, font=f)
        d.text(((w - tw) / 2, y), line, font=f, fill=(255, 235, 80))
        y += lh
    return im


def subtitle_chunks(text: str, max_len: int = 90) -> list[str]:
    parts = re.split(r"(?<=[.!?…;])\s+", text.strip())
    out = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            if cut < max_len // 3:
                cut = p.rfind(" ", 0, max_len)
            if cut <= 0:
                cut = max_len
            out.append(p[: cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


# ---------- сборка ----------

def build_video(script: dict, images: list[Path], workdir: Path, channel: str, log=print,
                tts_provider: str | None = None, voice: str | None = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    segs = script["segments"]
    frames_txt, wavs = [], []

    def voice_seg(i_seg, provider):
        i, seg = i_seg
        src = tts.synthesize(seg["narration"], workdir / f"seg{i:03d}.mp3", provider=provider, voice=voice)
        wav = workdir / f"seg{i:03d}.wav"
        tmp = workdir / f"seg{i:03d}_pad.wav"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", "apad=pad_dur=0.35", "-ar", "24000", "-ac", "1", str(tmp)])
        tmp.replace(wav)
        return wav

    provider = tts_provider or settings.tts_provider
    log(f"Озвучка мужским голосом ({provider}): {len(segs)} фрагментов")
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            wavs = list(ex.map(lambda a: voice_seg(a, provider), enumerate(segs)))
    except Exception as e:  # noqa: BLE001
        if provider == "piper":
            raise
        # один голос на весь ролик: если основной сервис подвёл — переозвучиваем всё офлайн-голосом Piper
        log(f"Голос {provider} не ответил ({str(e)[:80]}) — переключаюсь на офлайн мужской голос Piper «Дмитрий»")
        wavs = [voice_seg(a, "piper") for a in enumerate(segs)]

    log("Рисую слайды и субтитры")
    for i, (seg, wav) in enumerate(zip(segs, wavs)):
        dur = duration(wav)
        img = images[i % len(images)] if images else None
        slide = render_slide(seg, img, i, len(segs), channel, script.get("title", ""))
        chunks = subtitle_chunks(tts.clean_for_speech(seg["narration"])) or [""]
        total_chars = sum(len(c) for c in chunks) or 1
        for j, ch in enumerate(chunks):
            p = workdir / f"f{i:03d}_{j:03d}.jpg"
            add_subtitle(slide, ch).save(p, quality=88)
            frames_txt.append((p, dur * len(ch) / total_chars))

    # concat demuxer: длительность каждой картинки
    lst = workdir / "frames.txt"
    with lst.open("w") as fh:
        for p, dur in frames_txt:
            fh.write(f"file '{p.name}'\nduration {dur:.3f}\n")
        fh.write(f"file '{frames_txt[-1][0].name}'\n")
    alst = workdir / "audio.txt"
    alst.write_text("".join(f"file '{w.name}'\n" for w in wavs))
    voice_wav = workdir / "voice.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alst), "-c", "copy", str(voice_wav)])

    log("Склеиваю видео (ffmpeg)")
    out = workdir / "video.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(voice_wav),
         "-vf", f"fps=10,scale={settings.video_width}:{settings.video_height},format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "28", "-g", "50",
         "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out)])
    # обложка
    cover = Image.open(frames_txt[0][0])
    cover.save(workdir / "cover.jpg", quality=90)
    cover.thumbnail((320, 320))
    cover.save(workdir / "thumb.jpg", quality=80)  # Telegram: превью ≤ 320 px и ≤ 200 КБ
    for p in workdir.glob("f*_*.jpg"):
        p.unlink()
    for p in list(workdir.glob("seg*.mp3")) + list(workdir.glob("seg*.wav")) + [voice_wav]:
        p.unlink()
    return out


def fit_size(video: Path, max_mb: int, log=print) -> list[Path]:
    """Telegram Bot API принимает до 50 МБ. Сначала пережимаем, если не влезает — режем на части."""
    size_mb = video.stat().st_size / 1e6
    if size_mb <= max_mb:
        return [video]
    dur = duration(video)
    log(f"Видео {size_mb:.0f} МБ > {max_mb} МБ — пережимаю")
    target_kbps = int(max_mb * 8000 * 0.92 / dur) - 64
    small = video.with_name("video_small.mp4")
    if target_kbps > 120:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-c:v", "libx264", "-preset", "veryfast",
             "-b:v", f"{target_kbps}k", "-maxrate", f"{target_kbps * 2}k", "-bufsize", f"{target_kbps * 4}k",
             "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", str(small)])
        if small.stat().st_size / 1e6 <= max_mb:
            return [small]
    import math
    parts = math.ceil(size_mb / (max_mb * 0.85))
    for _ in range(6):
        for old in video.parent.glob("part*.mp4"):
            old.unlink()
        seg_time = int(dur / parts) + 1
        log(f"Режу на {parts} част(и) по ~{max(1, seg_time // 60)} мин")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-c", "copy", "-map", "0", "-f", "segment",
             "-segment_time", str(seg_time), "-reset_timestamps", "1", str(video.with_name("part%02d.mp4"))])
        out = sorted(video.parent.glob("part*.mp4"))
        if all(p.stat().st_size / 1e6 <= max_mb for p in out):
            return out
        parts += 1
    raise RuntimeError("Не удалось уложиться в лимит Telegram — включите локальный Bot API сервер (TELEGRAM_API_URL)")
