"""Оценка «можно применить на своём ПК + потенциал дохода» и теги для каждой находки."""
from __future__ import annotations

import re

# (паттерн, вес) — ищем в заголовке и описании, без учёта регистра
BOOST = {
    "agent": ([r"\bagents?\b", r"агент", r"openclaw", r"claude code", r"\bcodex\b", r"\bmcp\b", r"\bskills?\b", r"навык",
               r"autonomous", r"автоном", r"assistant", r"ассистент", r"\bbot\b", r"\bбот"], 14),
    "money": ([r"(made|earn\w*|making|generat\w*|revenue|income|profit)\W{1,25}\$\s?\d",
               r"\$\s?\d[\d,.]*\s?(k|m)?\s?(/|per |a )\s?(mo|month|year|day|week)", r"\bmrr\b", r"\barr\b", r"revenue", r"income", r"profit", r"made \$?\d",
               r"paying (users|customers|subscribers)", r"монетиз", r"заработ", r"доход", r"прибыл", r"выручк", r"клиент",
               r"продаж", r"side ?hustle", r"passive", r"пассивн", r"\bsaas\b", r"affiliate", r"платящ", r"first (customer|client|sale)"], 18),
    "build": ([r"\bi built\b", r"\bi made\b", r"how i\b", r"\bwe built\b", r"show hn", r"собрал", r"сделал", r"запустил",
               r"мой опыт", r"кейс", r"case study", r"from scratch", r"с нуля", r"weekend project"], 12),
    "tool": ([r"open[- ]source", r"github", r"self[- ]host", r"\btool\b", r"инструмент", r"library", r"библиотек", r"\bcli\b",
              r"plugin", r"плагин", r"extension", r"framework", r"\bapi\b", r"free\b", r"бесплатн"], 8),
    "guide": ([r"how to", r"tutorial", r"guide", r"step[- ]by[- ]step", r"гайд", r"инструкц", r"пошаг", r"\bкак\b",
               r"руководств", r"урок", r"шаблон", r"template", r"playbook", r"cheat ?sheet"], 10),
    "local": ([r"\blocal\b", r"локальн", r"ollama", r"llama\.?cpp", r"lm studio", r"comfyui", r"stable diffusion", r"whisper",
               r"on your (pc|computer|laptop|machine)", r"на своём (пк|компьютере)", r"offline", r"офлайн", r"\bgpu\b",
               r"qwen", r"deepseek", r"mistral", r"gemma", r"\bllama\b"], 10),
    "automation": ([r"automat", r"автоматиз", r"\bn8n\b", r"zapier", r"make\.com", r"workflow", r"pipeline", r"скрипт",
                    r"script", r"парсер", r"scraper", r"crawler", r"no[- ]?code", r"low[- ]?code", r"tiktok", r"youtube",
                    r"telegram", r"контент", r"content"], 9),
}
PENALTY = [r"space ?ship", r"spacecraft", r"космич", r"\bnasa\b", r"mars\b", r"military", r"военн", r"pentagon", r"пентагон",
           r"government", r"правительств", r"regulat", r"регулир", r"\blaw\b", r"закон", r"senat", r"сенат", r"election", r"выбор",
           r"lawsuit", r"суд\b", r"иск\b", r"trump", r"трамп", r"путин", r"putin", r"санкц", r"sanction", r"ipo\b", r"stock",
           r"акци[ия]", r"shares", r"valuation", r"оценк[аи] в", r"raises \$", r"привлек", r"billion", r"млрд", r"acquir",
           r"покупает", r"поглощ", r"ceo\b", r"гендиректор", r"layoff", r"увольн", r"arxiv", r"paper\b", r"benchmark",
           r"policy", r"политик", r"market (to reach|size|report)", r"revenue (rose|grew|fell)", r"quarter", r"квартал", r"cagr",
           r"\bltd\b", r"co\s?:", r"shareholders", r"earnings", r"press release", r"сокращени", r"штат[ае]? ", r"журнал time", r"газпром", r"войн", r"\bwar\b", r"ukrain", r"украин", r"china ban", r"export control", r"nvidia earnings"]

STRONG_MONEY = re.compile(
    r"(made|earn\w*|making|generat\w*|revenue|income|profit)\W{1,25}\$\s?\d|\$\s?\d[\d,.]*\s?(k|m)?\s?(/|per |a )\s?(mo|month|year|day|week)"
    r"|\bmrr\b|\barr\b|revenue|income|profit|заработ|доход|прибыл|выручк|монетиз|side ?hustle|passive income|пассивн"
    r"|paying (users|customers|subscribers)|first (customer|client|sale)|платящ|\d+\s?(тыс\.?|000)?\s?(₽|руб|\$)\s?(в|/)\s?мес", re.I)
_BOOST_RE = {k: (re.compile("|".join(p), re.I), w) for k, (p, w) in BOOST.items()}
_PEN_RE = re.compile("|".join(PENALTY), re.I)
AI_RE = re.compile(r"\bai\b|\bии\b|ии-|нейросет|\bllm|gpt|claude|gemini|grok|openai|anthropic|agent|агент|ollama|"
                   r"machine learning|машинн|chatbot|чат-?бот|mcp\b|copilot|cursor\b|deepseek|qwen|mistral|"
                   r"stable diffusion|comfyui|whisper|n8n|automat|автоматиз|openclaw|prompt|промпт", re.I)

TYPES = {"case": "кейс с доходом", "agent": "агент", "tool": "инструмент", "guide": "гайд", "skill": "навык"}


def analyze(title: str, summary: str = "", source: str = "", extra: dict | None = None) -> dict:
    text = f"{title} {summary}"
    extra = extra or {}
    hits = {k: len(rx.findall(text)) for k, (rx, _) in _BOOST_RE.items()}
    score = sum(min(2, n) * _BOOST_RE[k][1] for k, n in hits.items())
    pen = len(_PEN_RE.findall(text))
    is_ai = bool(AI_RE.search(text)) or source == "github"
    money_case = bool(STRONG_MONEY.search(title))
    if money_case:
        score += 15  # реальные истории «построил → заработал» — ядро базы знаний
    if not is_ai:
        score *= 0.7 if money_case else 0.25
        is_ai = money_case  # кейсы дохода без ИИ тоже берём: их воронку можно автоматизировать агентом
    score -= 22 * min(3, pen)
    if source == "github":
        score += 10  # открытый код — можно запустить у себя
    score = max(0, min(100, round(score)))

    # тип
    low = text.lower()
    strong_title = bool(STRONG_MONEY.search(title))
    strong_any = bool(STRONG_MONEY.search(text))
    if strong_title or (strong_any and _BOOST_RE["build"][0].search(title)):
        typ = "case"
    elif re.search(r"\bskills?\b|навык|skill\.md|claude skill|agent skill", low):
        typ = "skill"
    elif hits["agent"] and (hits["build"] or source == "github"):
        typ = "agent"
    elif hits["guide"]:
        typ = "guide"
    elif hits["tool"] or source in ("github", "producthunt"):
        typ = "tool"
    elif hits["agent"]:
        typ = "agent"
    elif hits["local"] or hits["automation"]:
        typ = "tool"
    else:
        typ = "guide"

    # что нужно
    needs = ["ПК"]
    if re.search(r"\bgpu\b|cuda|vram|stable diffusion|comfyui|fine-?tun|дообуч|видеокарт|rtx", low):
        needs.append("GPU")
    if re.search(r"openai|claude|anthropic|gpt-|gemini|grok|\bapi\b|api key|ключ", low) or typ in ("agent", "case"):
        needs.append("API-ключ")
    if re.search(r"ollama|llama\.?cpp|lm studio|local|локальн|offline|офлайн", low):
        needs.append("локальная модель")

    # сложность
    if re.search(r"no[- ]?code|без кода|n8n|zapier|make\.com|шаблон|template|beginner|новичк|за \d+ минут|in \d+ minutes", low):
        level = "новичок"
    elif "GPU" in needs or re.search(r"fine-?tun|дообуч|kubernetes|rust|c\+\+|train", low):
        level = "продвинутый"
    else:
        level = "средний"

    # потенциал дохода (оценка по типу, не обещание)
    if typ == "case":
        money = "высокий"
    elif strong_any or (hits["automation"] and hits["agent"]):
        money = "средний"
    elif typ in ("agent", "tool", "skill") and hits["automation"]:
        money = "средний"
    else:
        money = "низкий"

    return {"score": score, "type": typ, "type_ru": TYPES[typ], "level": level, "needs": needs, "money": money,
            "is_ai": is_ai, "penalty": pen, "signals": [k for k, n in hits.items() if n]}


def apply_steps(item: dict) -> list[str]:
    """Как применить у себя — короткий план по типу находки."""
    t = item.get("type")
    url = item.get("url", "")
    repo = (item.get("extra") or {}).get("repo")
    if repo:
        steps = [f"Откройте репозиторий {repo} и прочитайте README: требования, лицензия, пример запуска.",
                 f"Склонируйте на свой ПК: git clone https://github.com/{repo}.git",
                 "Установите зависимости по README (обычно pip/npm/docker) и запустите пример.",
                 "Подключите свою модель: облачный API-ключ или локальную через Ollama.",
                 "Примените к своей задаче: контент, лиды, поддержка клиентов, парсинг — и замерьте результат."]
    elif t == "case":
        steps = ["Прочитайте первоисточник: что именно делает агент, какие сервисы и сколько стоит запуск.",
                 "Выпишите воронку: откуда трафик → что продаётся → как платят (подписка, услуга, партнёрка).",
                 "Соберите минимальную копию на своём ПК (OpenClaw / n8n / Python-скрипт + API модели).",
                 "Запустите на своей нише на 1–2 недели, считайте просмотры → клиентов → деньги.",
                 "Оставьте только то, что даёт конверсии, и автоматизируйте это полностью."]
    elif t == "skill":
        steps = ["Откройте описание навыка (SKILL.md): что он умеет и какие ключи просит.",
                 "Установите агента (OpenClaw, Claude Code или аналог) на свой ПК.",
                 "Подключите навык и проверьте его в песочнице — навыки могут хранить ключи.",
                 "Встройте навык в свой конвейер (контент, продажи, аналитика)."]
    elif t == "agent":
        steps = ["Разберитесь, какую работу делает агент и какие инструменты ему нужны.",
                 "Поставьте агентную среду на ПК (OpenClaw / Claude Code / n8n с AI-узлами).",
                 "Дайте агенту одну узкую задачу с измеримым результатом.",
                 "Настройте расписание и отчёт в Telegram, чтобы агент работал без вас."]
    elif t == "tool":
        steps = ["Откройте страницу инструмента, проверьте цену/лицензию и требования к ПК.",
                 "Установите и повторите пример из документации.",
                 "Решите им одну свою задачу и встройте в конвейер."]
    else:
        steps = ["Прочитайте материал целиком и сохраните ключевые команды/промпты.",
                 "Повторите шаги на своём ПК в отдельной папке.",
                 "Запишите, что получилось, и добавьте в свою «машину дохода»."]
    if url and not repo:
        steps.insert(0, f"Источник: {url}")
    return steps
