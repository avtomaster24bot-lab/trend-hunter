"""Озвучка мужским голосом: edge-tts (бесплатно, ru-RU-DmitryNeural), Piper (офлайн, запасной),
OpenAI TTS (onyx) или ElevenLabs."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx

from .config import settings


async def _edge_once(text: str, voice: str, rate: str, attempts: int = 4) -> bytes:
    import edge_tts
    last = None
    for attempt in range(attempts):
        try:
            buf = bytearray()
            async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            if buf:
                return bytes(buf)
            raise RuntimeError("пустой ответ")
        except Exception as e:  # noqa: BLE001  — сервис Edge иногда отвечает пусто, просто повторяем
            last = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"edge-tts не ответил: {last}")


async def _edge(text: str, out: Path, voice: str, rate: str) -> None:
    try:
        out.write_bytes(await _edge_once(text, voice, rate))
        return
    except RuntimeError:
        pass
    # запасной путь: по предложениям (MP3-кадры можно склеивать подряд)
    parts = [p for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    data = b"".join([await _edge_once(p, voice, rate, attempts=3) for p in parts])
    out.write_bytes(data)


# ---------- Piper: офлайн, бесплатно, мужской голос «Дмитрий» (запасной вариант) ----------
_piper_voice = None
PIPER_MODEL = "ru_RU-dmitri-medium"


def _piper(text: str, out: Path) -> Path:
    global _piper_voice
    import wave
    from piper import PiperVoice
    if _piper_voice is None:
        vdir = settings.data_dir / "voices"
        vdir.mkdir(parents=True, exist_ok=True)
        model = vdir / f"{PIPER_MODEL}.onnx"
        if not model.exists():
            base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/"
            for name in (f"{PIPER_MODEL}.onnx", f"{PIPER_MODEL}.onnx.json"):
                with httpx.stream("GET", base + name, follow_redirects=True, timeout=300) as r:
                    r.raise_for_status()
                    with (vdir / name).open("wb") as fh:
                        for chunk in r.iter_bytes():
                            fh.write(chunk)
        _piper_voice = PiperVoice.load(str(model))
    out = out.with_suffix(".wav")
    with wave.open(str(out), "wb") as w:
        _piper_voice.synthesize_wav(text, w)
    return out


def clean_for_speech(text: str) -> str:
    text = text.replace("\u0301", "")                 # ударения из Википедии
    text = re.sub(r"=+\s*[^=]{1,80}?\s*=+", " ", text)  # == Заголовки ==
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("→", ", затем ").replace("×", " на ").replace("≈", "примерно ")
    text = re.sub(r"[*_#`|<>]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def synthesize(text: str, out: Path, provider: str | None = None, voice: str | None = None) -> Path:
    text = clean_for_speech(text)
    provider = provider or settings.tts_provider
    if provider == "openai" and settings.openai_api_key:
        r = httpx.post("https://api.openai.com/v1/audio/speech",
                       headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                       json={"model": settings.openai_tts_model, "voice": voice or settings.openai_tts_voice,
                             "input": text, "response_format": "mp3"}, timeout=300)
        r.raise_for_status()
        out.write_bytes(r.content)
        return out
    if provider == "elevenlabs" and settings.elevenlabs_api_key:
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice or settings.elevenlabs_voice_id}",
                       headers={"xi-api-key": settings.elevenlabs_api_key},
                       json={"text": text, "model_id": "eleven_multilingual_v2"}, timeout=300)
        r.raise_for_status()
        out.write_bytes(r.content)
        return out
    if provider == "piper":
        return _piper(text, out)
    asyncio.run(_edge(text, out, voice or settings.edge_voice, settings.edge_rate))
    return out


MALE_VOICES = {
    "edge": ["ru-RU-DmitryNeural"],
    "piper": ["ru_RU-dmitri-medium"],
    "openai": ["onyx", "echo", "ash"],
    "elevenlabs": ["pNInz6obpgDQGcFmaJgB"],
}
