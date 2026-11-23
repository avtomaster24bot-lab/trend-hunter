"""Сценарий ролика: через LLM (любой OpenAI-совместимый API) или без ключа — экстрактивно из собранных текстов."""
from __future__ import annotations

import json
import re

import httpx

from .config import settings

SYSTEM = (
    "Ты — сценарист новостного YouTube/Telegram-канала. Пишешь живой, точный, увлекательный текст на русском языке "
    "для озвучки мужским голосом диктора. Только факты из материалов, без выдумок; если данных мало — честно говори, "
    "что известно на данный момент. Никакой разметки, эмодзи и ссылок в тексте озвучки. Числа пиши так, как их читают."
)


def _llm(messages: list[dict], max_tokens: int = 4000) -> str:
    r = httpx.post(
        f"{settings.llm_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={"model": settings.llm_model, "messages": messages, "temperature": 0.7, "max_tokens": max_tokens},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    m = re.search(r"[\{\[].*[\}\]]", text, re.S)
    return json.loads(m.group(0) if m else text)


def _material(research: dict, limit: int = 24000) -> str:
    parts = ["СВЕЖИЕ ЗАГОЛОВКИ:"]
    for h in research["headlines"]:
        parts.append(f"- [{h['source']}] {h['title']}. {h['summary'][:300]}")
    for d in research["docs"]:
        parts.append(f"\nИСТОЧНИК: {d['title']} ({d['url']})\n{d['text'][:6000]}")
    return "\n".join(parts)[:limit]


PRACTICAL_PLAN = ("Структура обязательна: 1) что это за находка; 2) кто это сделал и какой результат — только по фактам "
                  "из материалов, с упоминанием источника, без выдуманных цифр дохода; 3) как повторить на своём ПК — "
                  "конкретные шаги; 4) что понадобится: ПК, видеокарта, API-ключи, примерные расходы; 5) как это встроить "
                  "в свою «машину дохода»; 6) вывод и призыв подписаться на канал. Материалы могут быть на английском — "
                  "пиши по-русски.")


def _llm_script(topic: dict, research: dict, minutes: int, channel: str) -> dict:
    words = minutes * settings.words_per_minute
    material = _material(research)
    if topic.get("practical"):
        p = topic["practical"]
        material = (f"ТИП: {p.get('type_ru')}; сложность: {p.get('level')}; нужно: {', '.join(p.get('needs', []))}; "
                    f"ссылка: {topic.get('url', '')}\n\n" + material)
        return _llm_practical(topic, material, minutes, words, channel)
    n_sections = max(3, min(24, round(minutes * 1.2)))
    if minutes <= 4:
        prompt = (
            f"Тема, которая сейчас набирает популярность: «{topic['title']}».\n"
            f"Напиши сценарий ролика на {minutes} мин (~{words} слов озвучки всего), {n_sections + 1}-{n_sections + 3} слайдов: "
            "цепляющее вступление, суть, детали и контекст, почему это важно, вывод и призыв подписаться на канал "
            f"{channel}.\nВерни ТОЛЬКО JSON: {{\"title\": str, \"segments\": [{{\"heading\": str (до 60 символов), "
            "\"bullets\": [2-3 коротких тезиса до 70 символов], \"narration\": str}}]}}\n\nМАТЕРИАЛЫ:\n" + material
        )
        return _json(_llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]))

    # Длинный ролик: сначала план, потом каждую часть отдельно — так LLM выдерживает нужный объём
    outline = _json(_llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
        f"Тема дня: «{topic['title']}». Составь план ролика на {minutes} минут из {n_sections} частей "
        "(вступление, развитие, контекст и история вопроса, мнения, последствия, вывод). "
        "Верни ТОЛЬКО JSON: {\"title\": str, \"sections\": [{\"heading\": str, \"points\": [str]}]}\n\nМАТЕРИАЛЫ:\n" + material
    )}], max_tokens=2000))
    per = max(60, words // len(outline["sections"]))
    segments = []
    for i, sec in enumerate(outline["sections"]):
        role = "Это вступление — зацепи зрителя." if i == 0 else (
            f"Это финал — подведи итог и призови подписаться на {channel}." if i == len(outline["sections"]) - 1 else "")
        part = _json(_llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
            f"Ролик «{outline['title']}». Напиши часть {i + 1} из {len(outline['sections'])}: «{sec['heading']}» "
            f"(пункты: {'; '.join(sec.get('points', []))}). {role} Объём озвучки ~{per} слов, разбей на 1-3 слайда. "
            "Не повторяй вступление в каждой части. Верни ТОЛЬКО JSON: {\"segments\": [{\"heading\": str, \"bullets\": [str], "
            "\"narration\": str}]}\n\nМАТЕРИАЛЫ:\n" + material
        )}], max_tokens=min(8000, per * 4 + 500)))
        segments += part["segments"]
    return {"title": outline["title"], "segments": segments}


def _llm_practical(topic: dict, material: str, minutes: int, words: int, channel: str) -> dict:
    n = max(4, min(24, round(minutes * 1.2)))
    if minutes <= 4:
        prompt = (f"Находка: «{topic['title']}». Сценарий ролика «как повторить это у себя» на {minutes} мин "
                  f"(~{words} слов), {n}-{n + 2} слайдов. {PRACTICAL_PLAN} Канал: {channel}.\nВерни ТОЛЬКО JSON: "
                  "{\"title\": str, \"segments\": [{\"heading\": str, \"bullets\": [str], \"narration\": str}]}\n\nМАТЕРИАЛЫ:\n" + material)
        return _json(_llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]))
    outline = _json(_llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
        f"Находка: «{topic['title']}». План ролика на {minutes} минут из {n} частей. {PRACTICAL_PLAN} "
        "Верни ТОЛЬКО JSON: {\"title\": str, \"sections\": [{\"heading\": str, \"points\": [str]}]}\n\nМАТЕРИАЛЫ:\n" + material)}],
        max_tokens=2000))
    per = max(60, words // len(outline["sections"]))
    segs = []
    for i, sec in enumerate(outline["sections"]):
        part = _json(_llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
            f"Ролик «{outline['title']}». Часть {i + 1}/{len(outline['sections'])}: «{sec['heading']}» "
            f"({'; '.join(sec.get('points', []))}). ~{per} слов, 1-3 слайда, конкретно и по шагам. "
            "Верни ТОЛЬКО JSON: {\"segments\": [{\"heading\": str, \"bullets\": [str], \"narration\": str}]}\n\nМАТЕРИАЛЫ:\n" + material)}],
            max_tokens=min(8000, per * 4 + 500)))
        segs += part["segments"]
    return {"title": outline["title"], "segments": segs}


_CYR = re.compile(r"[а-яё]", re.I)


def _is_ru(t: str) -> bool:
    letters = re.findall(r"[a-zа-яё]", t, re.I)
    return bool(letters) and len(_CYR.findall(t)) / len(letters) > 0.5


_RESULT = re.compile(r"\$\s?\d|\d+\s?(тыс|млн|k\b|%)|подписчик|просмотр|клиент|доход|заработ|выручк|mrr|revenue|users|views|звёзд|stars", re.I)


def _practical_script(topic: dict, research: dict, minutes: int, channel: str) -> dict:
    """Без LLM: что это → кто/результат → как повторить → что нужно. Англоязычные тексты не зачитываем."""
    from .practical import apply_steps
    p = topic["practical"]
    target = minutes * settings.words_per_minute
    title = topic["title"]
    src = ", ".join(topic.get("sources", [])[:3]) or "сеть"
    ru_sents = []
    for d in research["docs"]:
        for x in _SENT.split(_clean(d["text"])):
            x = _clean(x)
            if 30 < len(x) < 350 and _is_ru(x):
                ru_sents.append(x)
    for h in research["headlines"]:
        t = _strip_pub(_clean(h["title"]))
        if _is_ru(t):
            ru_sents.append(t.rstrip(".") + ".")
    results = [x for x in ru_sents if _RESULT.search(x)]
    other = [x for x in ru_sents if x not in results]

    segs = [{"heading": _short(title, 60), "bullets": [f"Тип: {p['type_ru']}", f"Сложность: {p['level']}", f"Источник: {src}"],
             "narration": f"Находка для вашей машины дохода. {title}. Это {p['type_ru']}, сложность — {p['level']}. "
                          f"Нашёл на {src}. Разбираем, что это и как повторить на своём компьютере."}]
    budget = target - 60
    what = other[:3] if other else []
    if what:
        n = " ".join(what)
        segs.append({"heading": "Что это", "bullets": [_short(x) for x in what[:3]], "narration": n})
        budget -= len(n.split())
    else:
        segs.append({"heading": "Что это", "bullets": [_short(title, 100)],
                     "narration": f"Коротко: {title}. Подробности — по ссылке в описании, материал на английском."})
    if results:
        chunk = results[: max(1, min(4, budget // 40))]
        n = "Что известно о результате, по данным источника. " + " ".join(chunk)
        segs.append({"heading": "Кто сделал и что получил", "bullets": [_short(x) for x in chunk[:3]], "narration": n})
        budget -= len(n.split())
    steps = [x for x in apply_steps({**topic, **p, "extra": {"repo": _repo(topic.get("url", ""))}}) if not x.startswith("Источник")]
    for i in range(0, len(steps), 3):
        ch = steps[i:i + 3]
        segs.append({"heading": "Как повторить на своём ПК" + (f" ({i // 3 + 1})" if len(steps) > 3 else ""),
                     "bullets": [_short(x, 90) for x in ch],
                     "narration": " ".join(f"Шаг {i + k + 1}. {re.sub(r'https?://', '', x)}" for k, x in enumerate(ch))})
    segs.append({"heading": "Что понадобится", "bullets": [", ".join(p["needs"]), f"Сложность: {p['level']}", f"Потенциал дохода: {p['money']} (оценка)"],
                 "narration": f"Что понадобится: {', '.join(p['needs']).replace('API-ключ', 'ключ API')}. Сложность — {p['level']}. "
                              f"Потенциал дохода я оцениваю как {p['money']} — это оценка, не обещание: деньги приносит не инструмент, а продукт и клиенты."})
    for x in other[3:]:
        if budget <= 20:
            break
        segs[-1:-1] = [{"heading": "Подробнее", "bullets": [_short(x)], "narration": x}]
        budget -= len(x.split())
    segs.append({"heading": "Собирайте свою машину дохода", "bullets": [f"Канал: {channel}", "Новые практичные находки — каждый день"],
                 "narration": "Сохраните себе и повторите на выходных. Подписывайтесь на канал — каждый день новые находки, "
                              "которые можно применить у себя. До встречи!"})
    return {"title": f"Как повторить: {title}"[:120], "segments": segs}


def _repo(url: str) -> str | None:
    m = re.match(r"https?://github\.com/([^/]+/[^/#?]+)", url or "")
    return m.group(1) if m else None


# ---------- без LLM ----------

_SENT = re.compile(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z0-9«\"])")


def _clean(t: str) -> str:
    t = t.replace("\u0301", "")
    t = re.sub(r"=+\s*[^=]{1,80}?\s*=+", " ", t)
    t = re.sub(r"\[\d+\]|\[[^\]]{0,30}\]", "", t)
    t = re.sub(r"\([^()]{0,80}(англ|лат|нем|кит|род\.|р\.)[^()]{0,80}\)", "", t)
    t = re.sub(r"https?://\S+", "", t)
    return re.sub(r"\s+", " ", t).strip()


_PUB = re.compile(r"\s+[-–—]\s+([^-–—]{2,40})$")


def _strip_pub(title: str) -> str:
    return _PUB.sub("", title)


def _publisher(h: dict) -> str:
    m = _PUB.search(h["title"])
    if m:
        return f"Пишет {m.group(1).strip()}"
    src = h["source"].split(" · ")[0]
    return {"Google Тренды": "В поиске Google", "Google Новости": "В новостях", "Hacker News": "На Hacker News обсуждают"}.get(src, f"Пишет {src}")


def _short(t: str, n: int = 110) -> str:
    t = t.strip(" .")
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _extractive_script(topic: dict, research: dict, minutes: int, channel: str) -> dict:
    target = minutes * settings.words_per_minute
    title = topic["title"]
    srcs = ", ".join(topic.get("sources", [])[:5])
    segs = [{
        "heading": _short(title, 60),
        "bullets": [f"Источники: {srcs}" if srcs else "Тема набирает популярность", f"Горячесть: {topic.get('hotness', 0)}/100"],
        "narration": f"Привет! Это тема, которая прямо сейчас набирает популярность. {title}. "
                     f"Об этом пишут {srcs or 'сразу несколько источников'}. Разбираемся, что происходит.",
    }]
    used = len(segs[0]["narration"].split())
    outro_words = 20
    budget = target - used - outro_words
    # заголовки — по 3 на слайд (не больше трети ролика)
    heads = [h for h in research["headlines"] if h["title"]][:12]
    head_budget = max(40, budget // 3)
    for i in range(0, len(heads), 3):
        chunk = heads[i:i + 3]
        narr = " ".join(f"{_publisher(h)}: {_strip_pub(_clean(h['title'])).rstrip('.')}." for h in chunk)
        n = len(narr.split())
        if n > head_budget and i > 0:
            break
        segs.append({"heading": "Что пишут прямо сейчас", "bullets": [_short(_strip_pub(_clean(h["title"]))) for h in chunk], "narration": narr})
        head_budget -= n
        budget -= n
    # тексты статей и справка — по 3-4 предложения на слайд, пока не наберём нужный объём
    for d in research["docs"]:
        if budget <= 15:
            break
        sents = [s for s in (_clean(x) for x in _SENT.split(_clean(d["text"]))) if 30 < len(s) < 400]
        chunk: list[str] = []
        for snt in sents:
            n = len(snt.split())
            if budget - n < -10:
                break
            chunk.append(snt)
            budget -= n
            if len(chunk) == 4:
                segs.append({"heading": _short(d["title"].replace("Википедия: ", "Справка: "), 60),
                             "bullets": [_short(x) for x in chunk[:3]], "narration": " ".join(chunk)})
                chunk = []
        if chunk:
            segs.append({"heading": _short(d["title"].replace("Википедия: ", "Справка: "), 60),
                         "bullets": [_short(x) for x in chunk[:3]], "narration": " ".join(chunk)})
    segs.append({
        "heading": "Следите за трендами",
        "bullets": [f"Подписывайтесь: {channel}", "Самое горячее — каждый день"],
        "narration": f"Это была главная тема на данный момент. Подписывайтесь на канал, чтобы первыми узнавать, что набирает популярность. До встречи!",
    })
    return {"title": title, "segments": segs}


def make_script(topic: dict, research: dict, minutes: int, channel: str, log=print) -> dict:
    if settings.llm_api_key:
        try:
            log(f"Пишу сценарий через LLM ({settings.llm_model})")
            sc = _llm_script(topic, research, minutes, channel)
            sc["segments"] = [s for s in sc["segments"] if s.get("narration")]
            if sc["segments"]:
                sc["mode"] = "llm"
                return sc
        except Exception as e:  # noqa: BLE001
            log(f"LLM не сработал ({e}) — делаю сценарий без LLM")
    log("Сценарий без LLM: собираю из найденных текстов")
    sc = (_practical_script if topic.get("practical") else _extractive_script)(topic, research, minutes, channel)
    sc["mode"] = "extractive"
    return sc
