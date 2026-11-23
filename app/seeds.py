"""Проверенная вручную «вечная» база: кейсы и инструменты с реальными источниками.
Цифры дохода — только как их сообщает автор/первоисточник, без додумывания."""

SEEDS = [
    {
        "id": "seed-larry",
        "title": "Larry — ИИ-агент на старом игровом ПК, который продвигает приложения в TikTok (Oliver Henry)",
        "url": "https://www.shippingskool.com/use-cases/oliver-henry-openclaw-agent-larry-tiktok-slideshows",
        "source_label": "Shipping Skool (кейс)", "type": "case", "level": "средний", "needs": ["ПК", "API-ключ"],
        "money": "высокий", "score": 98, "pinned": True,
        "summary_ru": (
            "Oliver Henry (не студент — разработчик, сотрудник RevenueCat) поставил на старый игровой ПК Ubuntu и агент "
            "OpenClaw на модели Claude и назвал его Larry. Larry сам делает TikTok-слайдшоу для двух его iOS-приложений "
            "(Snugly — редизайн комнаты, Liply — превью губ), пишет подписи и выкладывает черновики через Postiz. "
            "По словам автора: 500 000 просмотров меньше чем за неделю, 108 платящих подписчиков и ≈ $588 MRR; "
            "позже ≈ $714 MRR (Luminary Lane). Пост стоит ≈ $0,50 API. Громкие «$4000 за неделю» — в основном "
            "мем-монета, созданная фанатами, и партнёрские ссылки — это не повторяемая часть."),
        "steps": [
            "Ключевая идея: агент отвечает за всю воронку — контент → просмотры → установки → оплаты (RevenueCat) — и сам правит слабое звено.",
            "Нужен свой продукт или партнёрский оффер: агент продвигает, а не создаёт ценность из воздуха.",
            "Поставьте OpenClaw (github.com/openclaw/openclaw) на ПК или отдельную машину с Ubuntu.",
            "Установите навык Larry (github.com/OllieWazza/LarrySkill) — в песочнице: навык хранит много API-ключей.",
            "Подключите Postiz для публикации и аналитику дохода; музыку и финальную публикацию автор добавлял вручную (~60 с на пост).",
            "Считайте не просмотры, а платящих клиентов: «200K просмотров без конверсий ничего не стоят».",
        ],
        "sources": [
            {"title": "Shipping Skool: кейс Larry", "url": "https://www.shippingskool.com/use-cases/oliver-henry-openclaw-agent-larry-tiktok-slideshows"},
            {"title": "Luminary Lane: 8M просмотров, $714 MRR", "url": "https://www.luminarylane.app/blog/from-larry-to-lane/"},
            {"title": "Подкаст Startup Ideas с Oliver Henry", "url": "https://podcasts.apple.com/us/podcast/i-let-openclaw-run-my-organic-marketing-while-i-sleep/id1593424985?i=1000754066019"},
            {"title": "GitHub: LarrySkill", "url": "https://github.com/OllieWazza/LarrySkill"},
            {"title": "ClawHub: навык larry", "url": "https://clawhub.ai/oliverhenry/skills/larry"},
        ],
        "tags": ["agent", "money", "automation", "content"],
    },
    {
        "id": "seed-larryskill", "title": "LarrySkill — бесплатный навык OpenClaw для автоматического TikTok-маркетинга",
        "url": "https://github.com/OllieWazza/LarrySkill", "source_label": "GitHub", "type": "skill", "level": "средний",
        "needs": ["ПК", "API-ключ"], "money": "средний", "score": 90,
        "summary_ru": ("Навык от автора Larry: исследование конкурентов, генерация картинок, текст поверх слайдов, "
                       "публикация через Postiz, ежедневная аналитика и разбор, где ломается воронка. "
                       "Внимание: навык хранит много ключей — проверяйте конфиг и запускайте в песочнице."),
        "tags": ["skill", "content", "automation"],
    },
    {
        "id": "seed-openclaw", "title": "OpenClaw — открытый ИИ-агент, который «реально делает дела» на вашем ПК",
        "url": "https://github.com/openclaw/openclaw", "source_label": "GitHub", "type": "agent", "level": "средний",
        "needs": ["ПК", "API-ключ"], "money": "средний", "score": 92,
        "summary_ru": ("Самый популярный открытый агент (сотни тысяч звёзд на GitHub). Работает на любой ОС, общается "
                       "через мессенджеры, ставит навыки из маркетплейса ClawHub. На нём собран Larry."),
        "tags": ["agent", "local"],
    },
    {
        "id": "seed-ollama", "title": "Ollama — запуск локальных моделей (Llama, Qwen, DeepSeek, Gemma) на своём ПК",
        "url": "https://github.com/ollama/ollama", "source_label": "GitHub", "type": "tool", "level": "новичок",
        "needs": ["ПК", "локальная модель"], "money": "низкий", "score": 85,
        "summary_ru": ("Одна команда — и у вас своя нейросеть без абонплаты и с OpenAI-совместимым API на localhost. "
                       "Подходит для черновиков текстов, разбора документов, приватных данных. Для больших моделей нужна видеокарта."),
        "steps": ["Скачайте Ollama с ollama.com и установите.", "ollama run qwen2.5:7b — первая модель (≈ 5 ГБ).",
                  "В Trend Hunter можно указать LLM_BASE_URL=http://localhost:11434/v1 и LLM_MODEL=qwen2.5:7b — сценарии без платного API."],
        "tags": ["local", "tool"],
    },
    {
        "id": "seed-n8n", "title": "n8n — автоматизации и ИИ-агенты без кода, можно поставить у себя бесплатно",
        "url": "https://github.com/n8n-io/n8n", "source_label": "GitHub", "type": "tool", "level": "новичок",
        "needs": ["ПК"], "money": "средний", "score": 88,
        "summary_ru": ("Визуальный конструктор цепочек: Telegram, Google Таблицы, CRM, ИИ-узлы. Self-hosted версия "
                       "бесплатна. На n8n часто продают автоматизации бизнесу как услугу."),
        "steps": ["docker run -it --rm -p 5678:5678 n8nio/n8n", "Откройте http://localhost:5678 и соберите первый сценарий: Telegram → ИИ → ответ.",
                  "Упакуйте 2–3 типовые автоматизации (заявки, контент, отчёты) и предложите местному бизнесу."],
        "tags": ["automation", "tool", "money"],
    },
    {
        "id": "seed-postiz", "title": "Postiz — открытый планировщик публикаций в 20+ соцсетей с API",
        "url": "https://github.com/gitroomhq/postiz-app", "source_label": "GitHub", "type": "tool", "level": "средний",
        "needs": ["ПК"], "money": "средний", "score": 80,
        "summary_ru": "Через него Larry выкладывает посты. Можно поставить у себя и дать агенту публиковать по API в TikTok, Instagram, YouTube Shorts и др.",
        "tags": ["content", "automation", "tool"],
    },
    {
        "id": "seed-comfyui", "title": "ComfyUI — генерация картинок и видео на своей видеокарте",
        "url": "https://github.com/comfyanonymous/ComfyUI", "source_label": "GitHub", "type": "tool", "level": "продвинутый",
        "needs": ["ПК", "GPU", "локальная модель"], "money": "средний", "score": 75,
        "summary_ru": "Нодовый редактор для Stable Diffusion/Flux и видео-моделей. Обложки, слайды, креативы без оплаты за каждую картинку.",
        "tags": ["local", "content", "tool"],
    },
    {
        "id": "seed-openwebui", "title": "Open WebUI — свой «ChatGPT» в браузере поверх локальных моделей",
        "url": "https://github.com/open-webui/open-webui", "source_label": "GitHub", "type": "tool", "level": "новичок",
        "needs": ["ПК", "локальная модель"], "money": "низкий", "score": 70,
        "summary_ru": "Удобный чат-интерфейс для Ollama и API-моделей, с базой документов (RAG). Можно развернуть для клиентов как приватного ассистента.",
        "tags": ["local", "tool"],
    },
    {
        "id": "seed-tg-ads", "title": "Telegram делится 50% дохода от рекламы с владельцами каналов",
        "url": "https://telegram.org/blog/monetization-for-channels", "source_label": "Telegram (официально)", "type": "guide",
        "level": "новичок", "needs": ["ПК"], "money": "средний", "score": 78,
        "summary_ru": "Официальная программа: каналы получают 50% дохода от официальной рекламы Telegram. Плюс платные посты и Telegram Stars.",
        "sources": [{"title": "Telegram: монетизация каналов", "url": "https://telegram.org/blog/monetization-for-channels"},
                    {"title": "Telegram Stars", "url": "https://telegram.org/blog/telegram-stars"}],
        "tags": ["money", "content"],
    },
    {
        "id": "seed-trend-hunter", "title": "Trend Hunter — ваш конвейер: находки → видео с мужским голосом → Telegram-канал",
        "url": "https://github.com/avtomaster24bot-lab/trend-hunter", "source_label": "Этот проект", "type": "agent",
        "level": "новичок", "needs": ["ПК"], "money": "средний", "score": 80, "pinned": True,
        "summary_ru": ("Это и есть первый этап вашей машины дохода — контент-канал. Сайт сам собирает практичные ИИ-находки, "
                       "делает видео (edge-tts / Piper, ffmpeg) и публикует в @glush_io через GitHub Actions."),
        "tags": ["content", "automation", "agent"],
    },
]
