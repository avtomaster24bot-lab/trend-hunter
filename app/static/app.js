const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let CFG = {}, TOPICS = [], CURRENT = null;
const STATIC = !!window.TH_STATIC;  // GitHub Pages: только просмотр, генерация — через GitHub Actions
const STATIC_MAP = { "/api/config": "data/config.json", "/api/trends": "data/trends.json", "/api/jobs": "data/videos.json",
  "/api/knowledge": "data/knowledge.json", "/api/roadmap": "data/roadmap.json" };

async function api(path, opts = {}) {
  if (STATIC) {
    const r = await fetch(`${STATIC_MAP[path.split("?")[0]]}?t=${Date.now()}`);
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  }
  const headers = { "Content-Type": "application/json" };
  const pw = localStorage.getItem("th_pw");
  if (pw) headers["X-Admin-Password"] = pw;
  const r = await fetch(path, { ...opts, headers });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

function chip(label, ok) { return `<span class="chip ${ok ? "ok" : "off"}">${ok ? "✓" : "○"} ${esc(label)}</span>`; }

async function loadConfig() {
  CFG = await api("/api/config");
  const k = CFG.keys;
  $("#keys").innerHTML = [
    chip(k.llm ? `ИИ-сценарий (${k.llm_model})` : "ИИ-сценарий: нет LLM_API_KEY — текст из источников", k.llm),
    chip("YouTube API", k.youtube), chip("Instagram (Apify)", k.instagram),
    chip(`Telegram → ${CFG.channel}`, k.telegram), chip(`Голос: ${CFG.edge_voice}`, true),
  ].join("");
  $("#channel").value = CFG.channel;
  const ch = String(CFG.channel || "").replace(/^https?:\/\/t\.me\//, "@");
  if (ch.startsWith("@")) { $("#tg-link").href = "https://t.me/" + ch.slice(1); $("#tg-link").textContent = "📣 " + ch; }
  $("#pw-wrap").hidden = !CFG.needs_password;
  if (STATIC) setupStatic();
}

function setupStatic() {
  document.body.classList.add("static");
  $("#refresh").textContent = "↻ Обновить";
  $("#static-note").hidden = false;
  $("#go").textContent = "🚀 Открыть запуск в GitHub";
  $("#publish-wrap").hidden = true;
  $("#channel-wrap").hidden = true;
  $("#tts-wrap").hidden = true;
  $("#gh-hint").hidden = false;
}

function updateHint() {
  if (!STATIC || !CURRENT) return;
  $("#hint-topic").value = CURRENT.query;
  $("#hint-min").value = $("#minutes").value;
}

const SRC = { hn_ai: "Hacker News", hn_cases: "HN: кейсы (архив)", github: "GitHub", producthunt: "Product Hunt", habr_ai: "Хабр ИИ",
  vcru: "vc.ru", devto: "dev.to", medium: "Medium", reddit_ai: "Reddit", news_ai: "Новости: кейсы", youtube_ai: "YouTube", google_trends: "Google Тренды", google_news: "Google Новости", youtube: "YouTube", hackernews: "Hacker News",
  reddit: "Reddit", habr: "Хабр", lenta: "Лента.ру", tass: "ТАСС", instagram: "Instagram", custom_rss: "Свои RSS" };

async function loadTrends(refresh = false) {
  $("#refresh").disabled = true;
  if (refresh) $("#topics").innerHTML = `<div class="loader">Обновляю тренды…</div>`;
  try {
    const d = await api(`/api/trends${refresh ? "?refresh=true" : ""}`);
    TOPICS = d.topics;
    $("#updated").textContent = "обновлено " + new Date(d.updated * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    $("#sources").innerHTML = Object.entries(d.status).map(([k, v]) => `<span class="chip ${v.startsWith("ok") ? "ok" : "off"}" title="${esc(v)}">${esc(SRC[k] || k)}: ${v.startsWith("ok") ? v.slice(4) : "—"}</span>`).join("");
    renderTopics();
  } catch (e) {
    $("#topics").innerHTML = `<div class="loader">Ошибка: ${esc(e.message)}</div>`;
  }
  $("#refresh").disabled = false;
}

function renderTopics() {
  const q = $("#search").value.toLowerCase();
  const list = TOPICS.filter((t) => !q || [t.title, t.title_ru, t.summary_ru, t.query].join(" ").toLowerCase().includes(q));
  $("#topics").innerHTML = list.map((t, i) => {
    const p = t.practical;
    return `
    <article class="card">
      ${cover(t, `#${i + 1}`)}
      <div class="body">
        <h3>${esc(t.title_ru || t.title)}</h3>
        ${t.title_orig ? `<div class="orig" title="${esc(t.title_orig)}">${esc(t.title_orig)}</div>` : ""}
        ${t.summary_ru ? `<p class="desc">${esc(t.summary_ru)}</p>` : ""}
        <div class="hot">🔥 <div class="bar"><i style="width:${t.hotness}%"></i></div> <b>${t.hotness}</b></div>
        ${p ? `<div class="chips small"><span class="tag ${p.type}">${esc(p.type_ru)}</span>
          <span class="tag">${esc(p.level)}</span><span class="tag">${esc(p.needs.join(" · "))}</span>
          <span class="tag m-${p.money}">доход: ${esc(p.money)}</span></div>` : ""}
        <div class="links-row">
          <button class="btn small" data-detail="${t.id}">${t.build ? "🛠 Как собрать" : "📋 Как применить"}</button>
          ${t.repo_url ? `<a class="btn small gh" href="${esc(t.repo_url)}" target="_blank" rel="noopener">GitHub ↗</a>` : ""}
          ${t.url ? `<a class="btn small ghost" href="${esc(t.url)}" target="_blank" rel="noopener">Источник ↗</a>` : ""}
        </div>
        <details><summary>${t.items.length} материал(ов) · ${esc(t.sources.join(", "))}</summary><ul>${t.items.map((it) =>
          `<li><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title_ru || it.title)}</a> <span class="muted">· ${esc(it.source_label)}</span></li>`).join("")}</ul></details>
        <div class="foot"><span class="muted">≈ ${t.recommended_minutes} мин видео</span>
          <button class="btn small ghost" data-id="${t.id}">🎬 Сделать видео</button></div>
      </div>
    </article>`;
  }).join("") || `<div class="loader">Ничего не найдено</div>`;
}

// ---------- обложки: картинка или фирменная заглушка (никогда не пустой блок) ----------
const TYPE_EMOJI = { case: "💰", agent: "🤖", skill: "🧩", tool: "🛠", guide: "📘" };
function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } }
function cover(o, badge = "") {
  const type = o.type || (o.practical && o.practical.type) || "guide";
  const title = (o.title_ru || o.title || "").replace(/^[^—]{1,60} — /, "");
  const label = o.repo || o.source_label || hostOf(o.url) || "Trend Hunter";
  const img = o.image && /^https?:/.test(o.image) ? o.image : "";
  return `<div class="cover t-${esc(type)}">
    <div class="ph"><span class="ph-emoji">${TYPE_EMOJI[type] || "✨"}</span><span class="ph-title">${esc(title.slice(0, 90))}</span><span class="ph-src">${esc(label)}</span></div>
    ${img ? `<img src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()" onload="if(this.naturalWidth<60)this.remove()">` : ""}
    ${badge ? `<span class="rank">${esc(badge)}</span>` : ""}${o.pinned ? `<span class="pinb">★ проверено</span>` : ""}</div>`;
}

// ---------- карточка «как собрать / как применить» ----------
function openDetail(e) {
  const p = { ...(e.practical || {}), ...e };
  const b = e.build;
  const stepsHtml = b ? `<h4>🛠 Как собрать и запустить на своём ПК</h4><ol class="build">${b.steps.map((s) => `<li>${esc(s.t)}
      ${s.cmd ? `<div class="code"><pre>${esc(s.cmd)}</pre><button class="btn small ghost cp" type="button">Копировать</button></div>` : ""}
      ${s.link ? `<div><a href="${esc(s.link)}" target="_blank" rel="noopener">${esc(s.link)}</a></div>` : ""}</li>`).join("")}</ol>
      ${b.from_readme ? "" : `<p class="muted small">Команды подобраны по файлам проекта — сверяйтесь с README.</p>`}` : "";
  const sources = (e.sources || [{ title: e.source_label || hostOf(e.url) || "Источник", url: e.url }]).filter((x) => x.url);
  $("#kb-detail").innerHTML = `
    ${cover(e)}
    <div class="chips small">${p.type_ru ? `<span class="tag ${p.type}">${esc(p.type_ru)}</span>` : ""}${p.level ? `<span class="tag">${esc(p.level)}</span>` : ""}
      ${p.needs ? `<span class="tag">${esc((p.needs || []).join(" · "))}</span>` : ""}${p.money ? `<span class="tag m-${p.money}">потенциал дохода: ${esc(p.money)} (оценка)</span>` : ""}</div>
    <h3>${esc(e.title_ru || e.title)}</h3>
    ${e.title_orig ? `<div class="orig">Оригинал: ${esc(e.title_orig)}</div>` : ""}
    <p>${esc(e.summary_ru || "")}</p>
    <div class="links-row big">
      ${e.repo_url ? `<a class="btn gh" href="${esc(e.repo_url)}" target="_blank" rel="noopener">GitHub: ${esc(e.repo)} ↗</a>` : ""}
      ${e.url && e.url !== e.repo_url ? `<a class="btn ghost" href="${esc(e.url)}" target="_blank" rel="noopener">Источник ↗</a>` : ""}
    </div>
    ${b ? `<div class="chips small">${(b.stack || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}
      ${b.stars ? `<span class="chip">★ ${b.stars}</span>` : ""}${b.license && b.license !== "NOASSERTION" ? `<span class="chip">лицензия ${esc(b.license)}</span>` : ""}</div>` : ""}
    ${stepsHtml}
    ${(e.steps || []).length ? `<h4>${b ? "Как применить для дохода" : "📋 Как применить на своём ПК"}</h4><ol>${e.steps.filter((x) => !/^Источник: /.test(x)).map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
    <h4>Ссылки</h4><ul>${sources.map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a></li>`).join("")}
      ${e.repo_url ? `<li><a href="${esc(e.repo_url)}" target="_blank" rel="noopener">Репозиторий на GitHub: ${esc(e.repo)}</a></li>` : ""}
      ${e.extra && e.extra.discussion ? `<li><a href="${esc(e.extra.discussion)}" target="_blank" rel="noopener">Обсуждение на Hacker News</a></li>` : ""}</ul>`;
  $("#kb-dlg").showModal();
  $("#kb-dlg").scrollTop = 0;
}
document.addEventListener("click", (ev) => {
  const c = ev.target.closest(".cp");
  if (c) { navigator.clipboard?.writeText(c.previousElementSibling.textContent); c.textContent = "✓ Скопировано"; setTimeout(() => (c.textContent = "Копировать"), 1300); return; }
  const d = ev.target.closest("[data-detail]");
  if (d) { const t = TOPICS.find((x) => x.id === d.dataset.detail); if (t) openDetail(t); }
});

function openDialog(id) {
  CURRENT = TOPICS.find((t) => t.id === id);
  $("#dlg-title").textContent = CURRENT.title_ru || CURRENT.title;
  $("#dlg-meta").textContent = `Горячесть ${CURRENT.hotness}/100 · ${CURRENT.sources.join(", ")}`;
  const m = $("#minutes");
  m.value = CURRENT.recommended_minutes;
  $("#rec").textContent = `(рекомендовано ${CURRENT.recommended_minutes} мин — по количеству материала)`;
  $("#rec-mark").style.left = `calc(${((CURRENT.recommended_minutes - 1) / 29) * 100}% - 1px)`;
  $("#min-val").textContent = m.value;
  $("#publish").disabled = !CFG.keys.telegram;
  $("#publish").checked = false;
  updateHint();
  $("#dlg").showModal();
}

$("#minutes").addEventListener("input", (e) => { $("#min-val").textContent = e.target.value; updateHint(); });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  const inp = document.getElementById(b.dataset.copy);
  inp.select();
  navigator.clipboard?.writeText(inp.value);
  b.textContent = "✓";
  setTimeout(() => (b.textContent = "Копировать"), 1200);
});
$("#search").addEventListener("input", renderTopics);
$("#refresh").addEventListener("click", () => (STATIC ? loadTrends(false).then(loadJobs) : loadTrends(true)));
$("#topics").addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) openDialog(b.dataset.id); });
$("#form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "go") return;
  e.preventDefault();
  if (STATIC) {
    navigator.clipboard?.writeText(CURRENT.query).catch(() => {});
    window.open(CFG.workflow_url, "_blank", "noopener");
    return;
  }
  if (CFG.needs_password && $("#pw").value) localStorage.setItem("th_pw", $("#pw").value);
  try {
    await api("/api/jobs", { method: "POST", body: JSON.stringify({
      topic_id: CURRENT.id, minutes: +$("#minutes").value, publish: $("#publish").checked,
      channel: $("#channel").value || null, tts_provider: $("#tts").value }) });
    $("#dlg").close();
    loadJobs();
  } catch (err) { alert(err.message); }
});

const STATUS = { queued: "в очереди", running: "делаю", done: "готово", published: "в канале", error: "ошибка", publishing: "отправляю" };
async function loadJobs() {
  const jobs = await api("/api/jobs").catch(() => []);
  if (!jobs.length) {
    if (STATIC) $("#jobs").innerHTML = `<p class="muted">Видео пока нет. Выберите тему → «Сделать видео» → запустите в GitHub Actions — через 5–15 минут ролик появится здесь.</p>`;
    return;
  }
  $("#jobs").innerHTML = jobs.map((j) => `
    <div class="job">
      <h4>${esc(j.title || j.topic.title)}</h4>
      <span class="status ${j.status}">${STATUS[j.status] || j.status}</span>
      <span class="muted"> · ${j.minutes || "авто"} мин${j.duration ? ` · вышло ${Math.floor(j.duration / 60)}:${String(j.duration % 60).padStart(2, "0")}` : ""}${j.size_mb ? ` · ${j.size_mb} МБ` : ""}</span>
      <div class="progress"><i style="width:${j.progress || 0}%"></i></div>
      ${j.video ? `<video controls preload="metadata" poster="${esc(j.cover || "")}" src="${esc(j.video)}"></video>` : ""}
      ${j.error ? `<p class="accent">${esc(j.error)}</p>` : ""}
      <div class="row" style="margin-top:8px;justify-content:flex-start">
        ${j.video ? `<a class="btn small ghost" href="${esc(j.download || j.video)}" download>⬇ Скачать</a>` : ""}
        ${(j.parts || []).length > 1 ? `<span class="muted">частей: ${j.parts.length}</span>` : ""}
        ${j.release ? `<a class="btn small ghost" href="${esc(j.release)}" target="_blank" rel="noopener">Релиз</a>` : ""}
        ${!STATIC && (j.status === "done") && CFG.keys.telegram ? `<button class="btn small" data-pub="${j.id}">📤 В Telegram</button>` : ""}
      </div>
      ${(j.log || []).length ? `<details><summary class="muted">журнал</summary><div class="log">${esc((j.log || []).join("\n"))}</div></details>` : ""}
    </div>`).join("");
}
$("#jobs").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-pub]");
  if (!b) return;
  b.disabled = true;
  try { await api(`/api/jobs/${b.dataset.pub}/publish`, { method: "POST" }); } catch (err) { alert(err.message); }
  loadJobs();
});

(async () => {
  await loadConfig();
  await loadTrends();
  loadJobs();
  setInterval(refreshRunning, 4000);
})();

async function refreshRunning() {
  // перерисовываем только если есть незавершённые задания (чтобы не сбивать просмотр видео)
  const busy = [...document.querySelectorAll(".status")].some((s) => /queued|running|publishing/.test(s.className));
  if (busy) loadJobs();
}


// ---------- вкладки ----------
function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".pane").forEach((p) => (p.hidden = p.id !== `pane-${name}`));
  if (name === "kb" && !KB.length) loadKB();
  if (name === "machine") loadMachine();
  history.replaceState(null, "", name === "now" ? location.pathname : `#${name}`);
}
document.querySelector(".tabs").addEventListener("click", (e) => { const b = e.target.closest(".tab"); if (b) showTab(b.dataset.tab); });

// ---------- база знаний ----------
let KB = [], KB_LIMIT = 60;
const KB_BY_ID = {};
async function loadKB() {
  try { KB = await api("/api/knowledge"); } catch (e) { $("#kb-list").innerHTML = `<div class="loader">Ошибка: ${esc(e.message)}</div>`; return; }
  KB.forEach((e) => (KB_BY_ID[e.id] = e));
  $("#kb-count").textContent = `(${KB.length})`;
  renderKB();
}
function kbFiltered() {
  const q = $("#kb-search").value.toLowerCase(), t = $("#kb-type").value, l = $("#kb-level").value, n = $("#kb-need").value, m = $("#kb-money").value;
  let list = KB.filter((e) => (!q || (e.title + " " + (e.title_ru || "") + " " + (e.summary_ru || "") + " " + (e.summary || "") + " " + (e.repo || "")).toLowerCase().includes(q))
    && (!t || e.type === t) && (!l || e.level === l) && (!m || e.money === m)
    && (!n || (n === "noGPU" ? !e.needs.includes("GPU") : n === "noAPI" ? !e.needs.includes("API-ключ") : n === "local" ? e.needs.includes("локальная модель") : e.needs.includes(n))));
  if ($("#kb-sort").value === "new") list = list.slice().sort((a, b) => (b.first_seen || 0) - (a.first_seen || 0));
  return list;
}
function kbCard(e) {
  return `<article class="kb">
    ${cover(e)}
    <div class="kb-body">
    <div class="chips small"><span class="tag ${e.type}">${esc(e.type_ru)}</span><span class="tag">${esc(e.level)}</span>
      <span class="tag">${esc((e.needs || []).join(" · "))}</span><span class="tag m-${e.money}">доход: ${esc(e.money)}</span></div>
    <h3>${esc(e.title_ru || e.title)}</h3>
    ${e.title_orig ? `<div class="orig" title="${esc(e.title_orig)}">${esc(e.title_orig)}</div>` : ""}
    <p class="desc">${esc(e.summary_ru || "")}</p>
    <div class="links-row">
      <button class="btn small" data-kb="${e.id}">${e.build ? "🛠 Как собрать" : "📋 Как применить"}</button>
      ${e.repo_url ? `<a class="btn small gh" href="${esc(e.repo_url)}" target="_blank" rel="noopener">GitHub ↗</a>` : ""}
      ${e.url && e.url !== e.repo_url ? `<a class="btn small ghost" href="${esc(e.url)}" target="_blank" rel="noopener">Источник ↗</a>` : ""}
    </div>
    <div class="muted small">${esc(e.source_label || "")}${e.build && e.build.stars ? ` · ★ ${e.build.stars}` : e.extra && e.extra.stars ? ` · ★ ${e.extra.stars}` : ""}${e.build && e.build.stack.length ? ` · ${esc(e.build.stack.join(", "))}` : ""}</div>
    </div>
  </article>`;
}
function renderKB() {
  const list = kbFiltered();
  $("#kb-list").innerHTML = list.slice(0, KB_LIMIT).map(kbCard).join("") || `<div class="loader">Ничего не найдено</div>`;
  $("#kb-more").hidden = list.length <= KB_LIMIT;
}
["#kb-search", "#kb-type", "#kb-level", "#kb-need", "#kb-money", "#kb-sort"].forEach((sel) =>
  $(sel).addEventListener("input", () => { KB_LIMIT = 60; renderKB(); }));
$("#kb-more").addEventListener("click", () => { KB_LIMIT += 60; renderKB(); });
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-kb]");
  if (!b) return;
  const e = KB_BY_ID[b.dataset.kb];
  if (e) openDetail(e);
});

// ---------- машина дохода ----------
const MM_KEY = "th_machine_v1";
const mmState = () => JSON.parse(localStorage.getItem(MM_KEY) || '{"content:0": true}');  // Trend Hunter уже работает
async function loadMachine() {
  if (!KB.length) await loadKB();
  let stages = [];
  try { stages = await api("/api/roadmap"); } catch (e) { $("#machine").innerHTML = `<div class="loader">Ошибка: ${esc(e.message)}</div>`; return; }
  const st = mmState();
  let done = 0, total = 0;
  $("#machine").innerHTML = stages.map((s) => {
    const tasks = s.tasks.map((t, i) => {
      const id = `${s.id}:${i}`; total++; if (st[id]) done++;
      return `<label class="task"><input type="checkbox" data-mm="${id}" ${st[id] ? "checked" : ""}> <span>${esc(t)}</span></label>`;
    }).join("");
    const allDone = s.tasks.every((_, i) => st[`${s.id}:${i}`]);
    const links = s.items.map((id) => KB_BY_ID[id]).filter(Boolean).map((e) =>
      `<a href="#" data-kb="${e.id}" onclick="event.preventDefault()">${e.pinned ? "★ " : ""}${esc((e.title_ru || e.title).slice(0, 70))}${(e.title_ru || e.title).length > 70 ? "…" : ""}</a>`).join("");
    return `<section class="stage ${allDone ? "done" : ""}"><h3>${allDone ? "✅ " : ""}${esc(s.title)}</h3><p class="goal">${esc(s.goal)}</p>
      ${tasks}<div class="links">${links}</div></section>`;
  }).join("");
  const pct = total ? Math.round((100 * done) / total) : 0;
  $("#mm-progress").textContent = `${pct}%`;
  $("#machine").insertAdjacentHTML("afterbegin", `<div class="mm-bar"><i style="width:${pct}%"></i></div><p class="muted">Собрано ${done} из ${total} шагов</p>`);
}
document.addEventListener("change", (e) => {
  const c = e.target.closest("[data-mm]");
  if (!c) return;
  const st = mmState();
  st[c.dataset.mm] = c.checked;
  localStorage.setItem(MM_KEY, JSON.stringify(st));
  loadMachine();
});
if (location.hash === "#kb") showTab("kb");
if (location.hash === "#machine") showTab("machine");
loadKB();

// ---------- мобильный: «о сайте» свёрнуто ----------
$("#about-toggle").addEventListener("click", () => {
  const open = document.body.classList.toggle("about-open");
  $("#about-toggle").textContent = open ? "✕ Скрыть" : "ℹ️ О сайте";
});
