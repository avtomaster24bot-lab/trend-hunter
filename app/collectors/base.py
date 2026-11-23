from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

import httpx

UA = "Mozilla/5.0 (compatible; TrendHunter/1.0; +https://github.com/avtomaster24bot-lab/trend-hunter)"


@dataclass
class Item:
    title: str
    url: str
    source: str            # google_trends, youtube, hackernews ...
    source_label: str      # «Google Тренды», «YouTube» ...
    popularity: float = 0  # сырая метрика источника (просмотры, очки, трафик)
    rank: int = 0          # позиция в выдаче источника (0 = первый)
    published: float = field(default_factory=time.time)  # unix time
    summary: str = ""
    image: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def client(timeout: float = 15) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True)


def parse_time(entry) -> float:
    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None) or (entry.get(key) if isinstance(entry, dict) else None)
        if val:
            try:
                return time.mktime(val)
            except Exception:  # noqa: BLE001
                pass
    return time.time()
