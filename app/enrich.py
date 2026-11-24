"""Русские описания, репозитории GitHub и «как собрать на ПК», картинки — без платных ключей.

* Перевод: бесплатный веб-переводчик Google (пакетно, с повторами) → запасной MyMemory.
  Кеш переводов хранится в knowledge/translations_cache.json и коммитится workflow,
  поэтому одно и то же не переводится повторно. С LLM_API_KEY описания делает LLM (knowledge.enrich_with_llm).
* Репозитории: ссылка на GitHub ищется в самой находке и в тексте статьи (dev.to, Хабр, HN, Medium…);
  по GitHub API + README достаются стек и настоящие команды установки/запуска.
* Картинки: og:image статьи или карточка репозитория opengraph.githubassets.com.
"""
from __future__ import annotations

import html as htmlmod
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .config import ROOT

CACHE_DIR = Path(os.getenv("ENRICH_CACHE_DIR", str(ROOT / "knowledge")))
TR_FILE = CACHE_DIR / "translations_cache.json"
REPO_FILE = CACHE_DIR / "repos_cache.json"
ART_FILE = CACHE_DIR / "articles_cache.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
REPO_TTL = 7 * 86400


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


# ---------------- перевод ----------------

def is_ru(s: str) -> bool:
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", s or "")
    return bool(letters) and sum(1 for c in letters if re.match(r"[А-Яа-яЁё]", c)) / len(letters) > 0.4


def _clean(s: str) -> str:
    s = htmlmod.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _google_batch(c: httpx.Client, texts: list[str]) -> list[str] | None:
    r = c.post("https://clients5.google.com/translate_a/t", params={"client": "dict-chrome-ex", "sl": "auto", "tl": "ru"},
               content=urlencode([("q", t) for t in texts]), headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    if r.status_code != 200:
        return None
    res = r.json()
    out = []
    for x in res:
        if isinstance(x, list):
            out.append(x[0])
        elif isinstance(x, str):
            out.append(x)
    return out if len(out) == len(texts) else None


def _google_single(c: httpx.Client, t: str) -> str | None:
    r = c.get("https://translate.googleapis.com/translate_a/single",
              params={"client": "gtx", "sl": "auto", "tl": "ru", "dt": "t", "q": t})
    if r.status_code != 200 or not r.text.startswith("["):
        return None
    return "".join(p[0] for p in r.json()[0] if p and p[0])


def _mymemory(c: httpx.Client, t: str) -> str | None:
    r = c.get("https://api.mymemory.translated.net/get", params={"q": t[:480], "langpair": "en|ru"})
    if r.status_code != 200:
        return None
    d = r.json()
    if d.get("quotaFinished") or d.get("responseStatus") != 200:
        return None
    return d["responseData"]["translatedText"]


class Translator:
    def __init__(self):
        self.cache = _load(TR_FILE)
        self.new = 0
        self.failed = 0

    def __call__(self, text: str) -> str:
        t = _clean(text)
        if not t or is_ru(t):
            return t
        return self.cache.get(t, t)

    def prepare(self, texts, log=print) -> None:
        self.new = 0
        todo = sorted({_clean(t) for t in texts if t} - set(self.cache))
        todo = [t for t in todo if not is_ru(t) and re.search(r"[A-Za-z]{3}", t)]
        if not todo:
            return
        batches, cur, size = [], [], 0
        for t in todo:
            if cur and (len(cur) >= 12 or size + len(t) > 3000):
                batches.append(cur)
                cur, size = [], 0
            cur.append(t)
            size += len(t)
        if cur:
            batches.append(cur)

        def run(batch):
            with httpx.Client(timeout=25, headers={"User-Agent": UA}) as c:
                for attempt in range(3):
                    try:
                        res = _google_batch(c, batch)
                        if res:
                            return dict(zip(batch, res))
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(1.5 * (attempt + 1))
                out = {}
                for t in batch:  # по одному, другими путями
                    for fn in (_google_single, _mymemory):
                        try:
                            v = fn(c, t)
                            if v:
                                out[t] = v
                                break
                        except Exception:  # noqa: BLE001
                            continue
                return out

        with ThreadPoolExecutor(4) as ex:
            for res in ex.map(run, batches):
                for k, v in res.items():
                    if v and v.strip():
                        self.cache[k] = v.strip()
                        self.new += 1
        self.failed = len(todo) - sum(1 for t in todo if t in self.cache)
        log(f"Перевод: +{self.new} новых, не удалось {self.failed}, в кеше {len(self.cache)}")

    def save(self) -> None:
        if len(self.cache) > 20000:  # кеш не раздуваем бесконечно
            self.cache = dict(list(self.cache.items())[-15000:])
        _save(TR_FILE, self.cache)


# ---------------- GitHub ----------------

GH_SKIP = {"features", "topics", "sponsors", "orgs", "settings", "marketplace", "about", "pricing", "login", "join", "explore",
           "collections", "apps", "site", "contact", "security", "enterprise", "readme", "trending", "notifications", "new",
           "customer-stories", "team", "github", "forem", "codespaces", "events", "solutions", "resources", "users", "search"}
GH_RE = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100})", re.I)


def repo_from_text(text: str) -> str | None:
    cnt = Counter()
    for owner, name in GH_RE.findall(text or ""):
        name = re.sub(r"\.git$|[.,)]+$", "", name)
        if owner.lower() in GH_SKIP or not name or name.lower() in {"issues", "pulls", "blob", "tree"}:
            continue
        if owner.lower() in {"forem", "habr", "medium", "devto"}:
            continue
        cnt[f"{owner}/{name}"] += 1
    return cnt.most_common(1)[0][0] if cnt else None


BODY_MARKERS = [r'id="article-body"', r'class="tm-article-body', r'id="post-content-body"', r"<article", r'class="article']


def _article_meta(c: httpx.Client, url: str) -> dict:
    try:
        r = c.get(url, timeout=12)
    except Exception:  # noqa: BLE001
        return {"ok": False}
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return {"ok": False, "status": r.status_code}
    h = r.text[:800_000]
    img = ""
    m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', h, re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', h, re.I)
    if m:
        img = htmlmod.unescape(m.group(1))
    desc = ""
    for pat in (r'<meta[^>]+(?:property|name)=["\'](?:og:description|description|twitter:description)["\'][^>]*content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:description|description)["\']'):
        m = re.search(pat, h, re.I)
        if m:
            desc = _clean(m.group(1))[:500]
            break
    body = h
    for mk in BODY_MARKERS:
        i = h.find(mk) if not mk.startswith("<") else h.lower().find(mk)
        if i >= 0:
            body = h[i:i + 300_000]
            break
    links = " ".join(re.findall(r'href=["\'](https?://github\.com/[^"\'#?]+)', body))
    return {"ok": True, "image": img, "desc": desc, "repo": repo_from_text(links)}


def _cmd_like(line: str) -> bool:
    first = line.split()[0] if line.split() else ""
    first = first.lower()
    return bool(re.match(r"^(git|pip3?|uv|uvx|pipx|python3?|py|npm|npx|pnpm|yarn|bun|bunx|docker|docker-compose|podman|make|cargo|go|brew|"
                         r"curl|wget|poetry|conda|ollama|cd|cp|copy|export|set|bash|sh|node|deno|streamlit|uvicorn|winget|choco|irm|iwr|"
                         r"\./[\w.-]+|\.\\[\w.-]+|source|mv|mkdir|claude|openclaw|helm|kubectl|just|task|composer|php|java|mvn|gradle|dotnet|"
                         r"flutter|cmake|nix|apt|sudo|gh|hf|huggingface-cli|playwright)$", first))


def readme_commands(md: str, full: str) -> list[str]:
    """Команды из блоков кода README; сначала разделы «установка/быстрый старт/запуск»."""
    name = full.split("/")[1].lower()
    blocks = []
    pos_head = [(m.start(), m.group(1)) for m in re.finditer(r"^#{1,4}\s*(.+)$", md, re.M)]
    for m in re.finditer(r"```([\w+-]*)[^\n]*\n(.*?)```", md, re.S):
        lang = m.group(1).lower()
        if lang and lang not in {"bash", "sh", "shell", "console", "zsh", "powershell", "ps1", "cmd", "bat", "terminal", "text", "fish"}:
            continue
        head = next((h for p, h in reversed(pos_head) if p < m.start()), "")
        prio = 0 if re.search(r"install|quick|start|setup|getting|usage|run|build|deploy|docker|установ|запуск|быстр|сборк", head, re.I) else 1
        blocks.append((prio, m.start(), m.group(2)))
    out = []
    for _, _, code in sorted(blocks):
        for raw in code.splitlines():
            line = re.sub(r"^\s*(\$|>|PS [^>]*>|❯)\s*", "", raw).strip()
            if not line or line.startswith("#") or len(line) > 180 or not _cmd_like(line):
                continue
            low = line.lower()
            if (low.startswith("git clone") and name in low) or low in {f"cd {name}", f"cd ./{name}"}:
                continue  # клонирование добавляем сами
            if line not in out:
                out.append(line)
            if len(out) >= 10:
                return out
    return out


STACK_FILES = {
    "requirements.txt": "Python", "pyproject.toml": "Python", "setup.py": "Python", "Pipfile": "Python",
    "package.json": "Node.js", "bun.lockb": "Bun", "Dockerfile": "Docker", "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose", "compose.yml": "Docker Compose", "compose.yaml": "Docker Compose",
    "Cargo.toml": "Rust", "go.mod": "Go", "Makefile": "Make", "pom.xml": "Java", "build.gradle": "Java", "deno.json": "Deno",
}
PREREQ = {"Python": "Python 3.10+", "Node.js": "Node.js 18+ (LTS)", "Bun": "Bun", "Docker": "Docker Desktop", "Docker Compose": "Docker Desktop",
          "Rust": "Rust (rustup)", "Go": "Go 1.21+", "Java": "JDK 17+", "Deno": "Deno"}


def _fallback_cmds(stack: list[str], files: set[str]) -> list[str]:
    if "Docker Compose" in stack:
        return ["docker compose up -d"]
    if "Python" in stack:
        if "requirements.txt" in files:
            return ["python -m venv .venv", "source .venv/bin/activate   # Windows: .venv\\Scripts\\activate", "pip install -r requirements.txt"]
        return ["python -m venv .venv", "source .venv/bin/activate   # Windows: .venv\\Scripts\\activate", "pip install -e ."]
    if "Node.js" in stack or "Bun" in stack:
        return ["npm install", "npm run dev   # или npm start — смотрите scripts в package.json"]
    if "Rust" in stack:
        return ["cargo build --release"]
    if "Go" in stack:
        return ["go build ./..."]
    if "Docker" in stack:
        return ["docker build -t app .", "docker run --rm -it app"]
    return []


class GitHub:
    def __init__(self, token: str | None = None, max_new: int | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.cache = _load(REPO_FILE)
        self.max_new = max_new if max_new is not None else (150 if self.token else 20)
        self.fetched = 0
        self.lock = __import__("threading").Lock()

    def _api(self, c: httpx.Client, path: str):
        h = {"Accept": "application/vnd.github+json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        r = c.get("https://api.github.com" + path, headers=h)
        self.last_status = r.status_code
        return r.json() if r.status_code == 200 else None

    def info(self, full: str) -> dict | None:
        key = full.lower()
        cached = self.cache.get(key)
        if cached and time.time() - cached.get("fetched", 0) < REPO_TTL:
            return cached if cached.get("ok") else None
        with self.lock:
            if self.fetched >= self.max_new:
                return cached if cached and cached.get("ok") else None
            self.fetched += 1
        try:
            with httpx.Client(timeout=15, headers={"User-Agent": UA}, follow_redirects=True) as c:
                meta = self._api(c, f"/repos/{full}")
                if not meta:
                    if self.last_status in (404, 451):  # репозитория нет — не спрашиваем неделю
                        self.cache[key] = {"ok": False, "fetched": time.time()}
                    return None
                full = meta["full_name"]
                br = meta.get("default_branch") or "main"
                files = {x["name"] for x in (self._api(c, f"/repos/{full}/contents") or []) if isinstance(x, dict)}
                md = ""
                for fn in ("README.md", "readme.md", "README.MD", "Readme.md", "README.rst", "README"):
                    if fn in files or not files:
                        r = c.get(f"https://raw.githubusercontent.com/{full}/{br}/{fn}")
                        if r.status_code == 200:
                            md = r.text[:200_000]
                            break
        except Exception:  # noqa: BLE001
            return cached if cached and cached.get("ok") else None
        stack = []
        for f, s in STACK_FILES.items():
            if f in files and s not in stack:
                stack.append(s)
        if meta.get("language") and meta["language"] not in stack and meta["language"] not in {"Jupyter Notebook", "HTML", "CSS", "Shell"}:
            lang = {"TypeScript": "Node.js", "JavaScript": "Node.js"}.get(meta["language"], meta["language"])
            if lang not in stack:
                stack.append(lang)
        cmds = readme_commands(md, full)
        env = sorted(set(re.findall(r"\b([A-Z][A-Z0-9]*_(?:API_KEY|KEY|TOKEN|SECRET|API_BASE|BASE_URL))\b", md)))[:8]
        envfile = next((f for f in (".env.example", ".env.sample", ".env.template", "env.example") if f in files), "")
        d = {
            "ok": True, "fetched": time.time(), "full": full, "url": meta["html_url"], "description": meta.get("description") or "",
            "stars": meta.get("stargazers_count", 0), "language": meta.get("language"), "license": (meta.get("license") or {}).get("spdx_id"),
            "homepage": meta.get("homepage") or "", "topics": (meta.get("topics") or [])[:8], "pushed": meta.get("pushed_at"),
            "branch": br, "stack": stack, "commands": cmds, "fallback": _fallback_cmds(stack, files) if not cmds else [],
            "env": env, "envfile": envfile, "archived": meta.get("archived", False),
        }
        self.cache[key] = d
        return d

    def save(self) -> None:
        _save(REPO_FILE, self.cache)


def build_steps(info: dict) -> dict:
    """Русская инструкция «как собрать и запустить на ПК» с блоками команд."""
    full, name = info["full"], info["full"].split("/")[1]
    pre = ["Git"] + [PREREQ[s] for s in info["stack"] if s in PREREQ]
    pre = list(dict.fromkeys(pre))
    steps = [{"t": "Поставьте заранее: " + ", ".join(pre) + "."}]
    steps.append({"t": "Скачайте код репозитория:", "cmd": f"git clone https://github.com/{full}.git\ncd {name}"})
    if info.get("envfile") or info.get("env"):
        t = "Создайте файл настроек .env"
        if info.get("env"):
            t += " и впишите ключи: " + ", ".join(info["env"])
        steps.append({"t": t + ".", "cmd": f"cp {info['envfile']} .env" if info.get("envfile") else ""})
    cmds = [c for c in info.get("commands", []) if not re.match(r"^(cp|copy)\s+\S*env\S*\s+\.env\b", c)] if info.get("envfile") else info.get("commands", [])
    if cmds:
        steps.append({"t": "Установите и запустите — команды из README проекта (в порядке, как у автора):",
                      "cmd": "\n".join(cmds)})
    elif info.get("fallback") or (info.get("commands") and _fallback_cmds(info["stack"], set())):
        steps.append({"t": "В README нет готовых команд — стандартная сборка для этого стека:", "cmd": "\n".join(info.get("fallback") or _fallback_cmds(info["stack"], set()))})
    steps.append({"t": "Если что-то не запускается — полная инструкция и настройки в README:",
                  "link": f"https://github.com/{full}#readme"})
    return {"repo": full, "url": info["url"], "stack": info["stack"], "stars": info.get("stars"), "license": info.get("license"),
            "homepage": info.get("homepage"), "steps": steps, "from_readme": bool(info.get("commands"))}


# ---------------- общая обработка ----------------

WHY = {
    "agent": "Зачем вам: свой ИИ-агент на своём ПК — забирает рутину без подписок на чужие сервисы.",
    "tool": "Зачем вам: готовый инструмент — ставится у себя и встраивается в ваш конвейер.",
    "case": "Чем полезно: реальный пример «собрал → заработал» — схему можно повторить у себя.",
    "guide": "Чем полезно: пошаговый разбор, который можно повторить на своём ПК.",
    "skill": "Чем полезно: навык для агента — добавляет ему новую способность.",
}


def _short(s: str, n: int = 320) -> str:
    s = _clean(s)
    if len(s) <= n:
        return s
    cut = s[:n]
    i = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:i + 1] if i > n * 0.5 else cut.rsplit(" ", 1)[0] + "…")


ARTS: dict = {}


def _src_text(e: dict) -> tuple[str, str]:
    """(заголовок для перевода, описание для перевода)."""
    title = e.get("title", "")
    summ = e.get("summary", "") or ""
    if len(_clean(summ)) < 40:
        summ = (ARTS.get(e.get("url", "")) or {}).get("desc") or summ
    if e.get("source") == "github" and ":" in title:
        title = title.split(":", 1)[1].strip()
    if _clean(summ).lower().startswith(_clean(title).lower()[:60]) and len(_clean(summ)) < len(_clean(title)) + 20:
        summ = ""
    return _clean(title), _short(summ)


def _repo_name(e: dict) -> str | None:
    if e.get("source") == "github":
        return (e.get("extra") or {}).get("repo") or repo_from_text(e.get("url", ""))
    return repo_from_text(e.get("url", "")) or repo_from_text(" ".join(s.get("url", "") for s in e.get("sources", []) or []))


def enrich(entries: list[dict], log=print, fetch_articles: bool = True) -> None:
    """Дописывает в каждую запись: title_ru, desc_ru, summary_ru, repo, build, image. Работает на месте."""
    tr, gh = Translator(), GitHub()
    arts = _load(ART_FILE)
    ARTS.clear()
    ARTS.update(arts)
    # 1) статьи: картинка и ссылка на репозиторий из текста
    if fetch_articles:
        todo = [e["url"] for e in entries if e.get("url") and e.get("source") not in ("github", "seed")
                and "news.google.com" not in e["url"] and e["url"] not in arts and not repo_from_text(e["url"])][:150]
        if todo:
            def one(u):
                with httpx.Client(timeout=12, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"}, follow_redirects=True) as c:
                    return u, _article_meta(c, u)
            with ThreadPoolExecutor(8) as ex:
                for u, m in ex.map(one, todo):
                    m["t"] = time.time()
                    arts[u] = m
            ARTS.update(arts)
            log(f"Статьи: проверено {len(todo)}, найдено репозиториев {sum(1 for u in todo if arts[u].get('repo'))}")
    # 2) репозитории
    names = {}
    for e in entries:
        n = _repo_name(e) or (arts.get(e.get("url", ""), {}) or {}).get("repo")
        if n:
            names[e["id"]] = n
    with ThreadPoolExecutor(6) as ex:
        infos = dict(zip(set(names.values()), ex.map(gh.info, set(names.values()))))
    # 3) перевод
    texts = []
    for e in entries:
        t, s = _src_text(e)
        texts += [t, s]
        inf = infos.get(names.get(e["id"]))
        if inf:
            texts.append(_short(inf.get("description", ""), 300))
        for it in e.get("items", []) or []:
            texts.append(it.get("title", ""))
    tr.prepare(texts, log=log)
    if tr.failed:
        time.sleep(3)
        tr.prepare(texts, log=log)  # второй заход для того, что не перевелось
    # 4) сборка полей
    for e in entries:
        t, s = _src_text(e)
        inf = infos.get(names.get(e["id"]))
        art = arts.get(e.get("url", ""), {}) or {}
        gh_name = (inf or {}).get("full") or (e.get("extra") or {}).get("repo") or (e.get("title", "").split(":")[0] if e.get("source") == "github" else "")
        if e.get("source") == "github" and gh_name:
            nm = gh_name.split("/")[-1]
            d = re.sub(rf"^\W*{re.escape(nm)}\W*(?:—|-|:|–|это)\s*", "", tr(t), flags=re.I) if t else ""
            d = re.split(r"(?<=[.!?])\s", d)[0] if d else ""
            if len(d) > 110:
                d = d[:110].rsplit(" ", 1)[0] + "…"
            e["title_ru"] = f"{nm} — {d[:1].upper() + d[1:]}" if d else gh_name
        elif e.get("source") == "seed" or is_ru(e.get("title", "")):
            e["title_ru"] = e.get("title", "")
        else:
            e["title_ru"] = tr(t)
        if e.get("title_ru", "") == e.get("title", ""):
            e.pop("title_orig", None)
        else:
            e["title_orig"] = e.get("title", "")
        if not (e.get("llm") or e.get("source") == "seed"):
            desc = tr(s) if s else ""
            if inf and inf.get("description") and (not desc or e.get("source") == "github"):
                desc = tr(_short(inf["description"], 300))
            if not desc or not is_ru(desc):
                desc = desc if is_ru(desc) else ""
            why = WHY.get(e.get("type") or (e.get("practical") or {}).get("type"), "")
            parts = [desc] if desc and desc != e.get("title_ru") else []
            if inf and inf.get("stack"):
                parts.append("Стек: " + ", ".join(inf["stack"]) + (f", ★ {inf['stars']}" if inf.get("stars") else "") + ".")
            parts.append(why)
            e["summary_ru"] = " ".join(p for p in parts if p).strip()
        if inf:
            e["repo"] = inf["full"]
            e["repo_url"] = inf["url"]
            e["build"] = build_steps(inf)
        if not e.get("image"):
            if art.get("image") and art["image"].startswith("http"):
                e["image"] = art["image"]
            elif inf:
                e["image"] = f"https://opengraph.githubassets.com/1/{inf['full']}"
        for it in e.get("items", []) or []:
            ru = tr(it.get("title", ""))
            if ru and ru != it.get("title"):
                it["title_ru"] = ru
    tr.save()
    gh.save()
    if len(arts) > 6000:
        arts = dict(sorted(arts.items(), key=lambda kv: kv[1].get("t", 0))[-5000:])
    _save(ART_FILE, arts)
    log(f"Репозитории: {len(infos)} (новых запросов {gh.fetched}), с инструкцией сборки {sum(1 for e in entries if e.get('build'))}")
