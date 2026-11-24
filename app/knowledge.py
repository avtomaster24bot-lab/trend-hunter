"""База знаний: копится между запусками (knowledge/knowledge.json в репозитории), дубли склеиваются."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import practical
from .config import ROOT, settings
from .seeds import SEEDS

KB_FILE = Path(__import__("os").getenv("KNOWLEDGE_FILE", str(ROOT / "knowledge" / "knowledge.json")))
MIN_SCORE = 35
MAX_ITEMS = 800


def _norm_url(u: str) -> str:
    u = re.sub(r"[?#].*$", "", (u or "").strip().lower())
    return re.sub(r"^https?://(www\.)?", "", u).rstrip("/")


def _key(item: dict) -> str:
    base = _norm_url(item.get("url", "")) or item.get("title", "").lower()
    return "k" + hashlib.md5(base.encode()).hexdigest()[:12]


def _title_key(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()[:70]


def load() -> list[dict]:
    if KB_FILE.exists():
        return json.loads(KB_FILE.read_text(encoding="utf-8")).get("items", [])
    return []


def save(items: list[dict]) -> None:
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_FILE.write_text(json.dumps({"updated": time.time(), "count": len(items), "items": items},
                                  ensure_ascii=False, indent=0), encoding="utf-8")


def _ru_summary(it: dict) -> str:
    s = (it.get("summary") or "").strip()
    if re.search(r"[а-яё]", it["title"] + s, re.I):
        return (s or it["title"])[:400]
    extra = it.get("extra") or {}
    bits = [f"{it.get('type_ru', 'Находка').capitalize()} из {it.get('source_label', 'сети')}"]
    if extra.get("stars"):
        bits.append(f"★ {extra['stars']} на GitHub" + (f", {extra['language']}" if extra.get("language") else ""))
    if extra.get("points"):
        bits.append(f"{extra['points']} очков на Hacker News")
    text = ". ".join(bits) + "."
    if s:
        text += f" Описание (англ.): {s[:280]}"
    return text


def to_entry(item: dict, now: float) -> dict | None:
    a = practical.analyze(item["title"], item.get("summary", ""), item.get("source", ""), item.get("extra"))
    if a["score"] < MIN_SCORE or not a["is_ai"]:
        return None
    url = re.sub(r"[?&]utm_[^#]*", "", item["url"])
    e = {
        "id": _key(item), "title": item["title"], "url": url, "source": item.get("source"),
        "source_label": item.get("source_label"), "summary": (item.get("summary") or "")[:600], "image": item.get("image", ""),
        "published": item.get("published"), "popularity": item.get("popularity", 0), "extra": item.get("extra") or {},
        "first_seen": now, "last_seen": now, **{k: a[k] for k in ("score", "type", "type_ru", "level", "needs", "money", "signals")},
    }
    e["tags"] = a["signals"]
    e["summary_ru"] = _ru_summary(e)
    e["steps"] = practical.apply_steps(e)
    return e


def merge(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Добавляет находки в базу. Возвращает (вся база, новые за этот запуск)."""
    now = time.time()
    kb = {e["id"]: e for e in load()}
    titles = {_title_key(e["title"]): e["id"] for e in kb.values()}
    new = []
    for it in items:
        e = to_entry(it, now)
        if not e:
            continue
        old_id = e["id"] if e["id"] in kb else titles.get(_title_key(e["title"]))
        if old_id:
            o = kb[old_id]
            o["last_seen"] = now
            o["popularity"] = max(o.get("popularity", 0), e["popularity"])
            o["seen_count"] = o.get("seen_count", 1) + 1
            if e["extra"].get("stars"):
                o.setdefault("extra", {})["stars"] = e["extra"]["stars"]
            continue
        kb[e["id"]] = e
        titles[_title_key(e["title"])] = e["id"]
        new.append(e)
    # проверенные вручную материалы всегда в базе
    for s in SEEDS:
        base = kb.get(s["id"], {})
        kb[s["id"]] = {**base, **s, "type_ru": practical.TYPES[s["type"]], "source": "seed", "first_seen": base.get("first_seen", now),
                       "last_seen": now, "steps": s.get("steps") or practical.apply_steps(s), "summary": s.get("summary", ""),
                       "extra": s.get("extra", {}), "image": s.get("image", "")}
    out = sorted(kb.values(), key=lambda e: (e.get("pinned", False), e["score"]), reverse=True)
    if len(out) > MAX_ITEMS:  # выкидываем самое слабое и давно не встречавшееся
        keep = out[:MAX_ITEMS]
        out = keep
    return out, new


def enrich_with_llm(entries: list[dict], limit: int = 40, log=print) -> int:
    """С ключом LLM: русское описание, шаги «как повторить», уточнение типа и полезности."""
    if not settings.llm_api_key:
        return 0
    from .script import _json, _llm
    todo = [e for e in entries if not e.get("llm") and e.get("source") != "seed"][:limit]
    done = 0
    for i in range(0, len(todo), 8):
        batch = todo[i:i + 8]
        listing = "\n".join(f"{n}. {e['title']} — {e.get('summary', '')[:300]} ({e['url']})" for n, e in enumerate(batch))
        prompt = ("Ты отбираешь ИИ-находки, которые обычный человек может применить на своём ПК, чтобы зарабатывать. "
                  "Для каждой верни JSON-массив объектов {\"n\": номер, \"useful\": true/false (false — новости про политику, "
                  "космос, корпорации, чистую науку), \"type\": \"case|agent|tool|guide|skill\", \"money\": \"высокий|средний|низкий\", "
                  "\"title_ru\": заголовок по-русски, \"summary_ru\": 2 предложения по-русски только по фактам из описания, \"steps\": [3-5 коротких шагов как повторить у себя]}. "
                  "Не выдумывай цифры дохода.\n\n" + listing)
        try:
            res = _json(_llm([{"role": "user", "content": prompt}], max_tokens=3000))
            for r in res if isinstance(res, list) else res.get("items", []):
                e = batch[int(r["n"])]
                e["llm"] = True
                if not r.get("useful", True):
                    e["score"] = min(e["score"], 20)
                if r.get("type") in practical.TYPES:
                    e["type"], e["type_ru"] = r["type"], practical.TYPES[r["type"]]
                for k in ("money", "title_ru", "summary_ru", "steps"):
                    if r.get(k):
                        e[k] = r[k]
                done += 1
        except Exception as ex:  # noqa: BLE001
            log(f"LLM-разметка: {ex}")
            break
    return done


# ---------- Машина дохода ----------

ROADMAP = [
    {"id": "base", "title": "Этап 0. Фундамент на своём ПК",
     "goal": "Рабочее место: локальная модель, агентная среда, доступ к API.",
     "tasks": ["Установить Ollama и запустить локальную модель", "Поставить OpenClaw или n8n", "Завести API-ключ одной облачной модели (на сложные задачи)",
               "Завести отдельную папку/репозиторий под свою машину"],
     "match": ["local", "agent"], "types": ["tool"], "seeds": ["seed-ollama", "seed-openclaw", "seed-n8n", "seed-openwebui"]},
    {"id": "niche", "title": "Этап 1. Ниша и продукт",
     "goal": "Что продаём и кому: своё приложение, услуга автоматизации, контент-канал, партнёрский оффер.",
     "tasks": ["Выписать 3 ниши, где вы понимаете клиента", "Найти 3 кейса с реальным доходом в базе знаний и разобрать воронки",
               "Выбрать одну нишу и один оффер", "Посчитать: сколько клиентов × чек нужно для цели"],
     "match": ["money", "build"], "types": ["case"], "seeds": ["seed-larry"]},
    {"id": "agent", "title": "Этап 2. Свой агент",
     "goal": "Агент делает одну работу, которая приносит деньги (как Larry — маркетинг приложений).",
     "tasks": ["Описать работу агента одним предложением", "Собрать минимальную версию за выходные", "Подключить навыки (skills/MCP) под задачу",
               "Запускать по расписанию и получать отчёт в Telegram"],
     "match": ["agent"], "types": ["agent", "skill"], "seeds": ["seed-openclaw", "seed-larryskill"]},
    {"id": "content", "title": "Этап 3. Автоматизация контента (трафик)",
     "goal": "Постоянный поток внимания: канал, ролики, слайдшоу — без ручной работы.",
     "tasks": ["✅ Trend Hunter уже делает видео для @glush_io — подключить бота админом канала", "Добавить LLM-ключ для качественных сценариев",
               "Включить кросс-постинг (Postiz) в TikTok / Shorts / Reels", "Мерить, какие темы приводят подписчиков"],
     "match": ["automation"], "types": ["tool", "skill"], "seeds": ["seed-trend-hunter", "seed-postiz", "seed-comfyui", "seed-larryskill"]},
    {"id": "money", "title": "Этап 4. Монетизация",
     "goal": "Превратить внимание в деньги: подписки, услуги, реклама, партнёрки.",
     "tasks": ["Включить монетизацию канала Telegram (реклама 50%, платные посты, Stars)", "Сделать один платный продукт/услугу под нишу",
               "Поставить партнёрские ссылки на инструменты, которые реально используете", "Считать доход по каждому источнику"],
     "match": ["money"], "types": ["case", "guide"], "seeds": ["seed-tg-ads", "seed-larry"]},
    {"id": "loop", "title": "Этап 5. Аналитика и самоулучшение",
     "goal": "Агент смотрит не на просмотры, а на деньги, и сам правит слабое место воронки.",
     "tasks": ["Свести в одну таблицу: просмотры → клиенты → оплата", "Раз в день — отчёт агента о слабом звене", "Убирать то, что не конвертирует"],
     "match": ["money", "automation"], "types": ["case", "tool"], "seeds": ["seed-larry"]},
    {"id": "scale", "title": "Этап 6. Масштаб",
     "goal": "Повторить работающую связку в новых нишах/языках/площадках.",
     "tasks": ["Клонировать конвейер на вторую нишу", "Добавить ещё площадки и языки", "Перевести рутину на локальные модели, чтобы снизить расходы"],
     "match": ["automation", "local"], "types": ["tool", "agent"], "seeds": ["seed-ollama", "seed-n8n"]},
]


def roadmap(kb: list[dict], per_stage: int = 6) -> list[dict]:
    out = []
    for st in ROADMAP:
        linked = list(st["seeds"])
        cands = [e for e in kb if e["id"] not in linked and e.get("type") in st["types"]
                 and set(e.get("tags", [])) & set(st["match"])]
        cands.sort(key=lambda e: e["score"], reverse=True)
        linked += [e["id"] for e in cands[: max(0, per_stage - len(linked))]]
        out.append({k: st[k] for k in ("id", "title", "goal", "tasks")} | {"items": linked})
    return out
