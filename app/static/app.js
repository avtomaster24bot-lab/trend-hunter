const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let CFG = {}, TOPICS = [], CURRENT = null;

async function api(path, opts = {}) {
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
  $("#pw-wrap").hidden = !CFG.needs_password;
}

const SRC = { google_trends: "Google Тренды", google_news: "Google Новости", youtube: "YouTube", hackernews: "Hacker News",
  reddit: "Reddit", habr: "Хабр", lenta: "Лента.ру", tass: "ТАСС", instagram: "Instagram", custom_rss: "Свои RSS" };

async function loadTrends(refresh = false) {
  $("#refresh").disabled = true;
  if (refresh) $("#topics").innerHTML = `<div class="loader">Обновляю тренды…</div>`;
  try {
    const d = await api(`/api/trends${refresh ? "?refresh=true" : ""}`);
    TOPICS = d.topics;
    $("#updated").textContent = "обновлено " + new Date(d.updated * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    $("#sources").innerHTML = Object.entries(d.status).map(([k, v]) => `<span class="chip ${v.startsWith("ok") ? "ok" : "off"}" title="${esc(v)}">${esc(SRC[k] || k)}: ${v.startsWith("ok") ? v.slice(4) : "—"}</span>`).join("");
    renderTopics();
  } catch (e) {
    $("#topics").innerHTML = `<div class="loader">Ошибка: ${esc(e.message)}</div>`;
  }
  $("#refresh").disabled = false;
}

function renderTopics() {
  const q = $("#search").value.toLowerCase();
  const list = TOPICS.filter((t) => !q || t.title.toLowerCase().includes(q) || t.query.toLowerCase().includes(q));
  $("#topics").innerHTML = list.map((t, i) => `
    <article class="card">
      <div class="img" style="background-image:url('${esc(t.image)}')"><span class="rank">#${i + 1}</span></div>
      <div class="body">
        <h3>${esc(t.title)}</h3>
        <div class="hot">🔥 <div class="bar"><i style="width:${t.hotness}%"></i></div> <b>${t.hotness}</b></div>
        <div class="chips small">${t.sources.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>
        <details><summary>${t.items.length} материал(ов)</summary><ul>${t.items.map((it) =>
          `<li><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a> <span class="muted">· ${esc(it.source_label)}</span></li>`).join("")}</ul></details>
        <div class="foot"><span class="muted">≈ ${t.recommended_minutes} мин</span>
          <button class="btn small" data-id="${t.id}">🎬 Сделать видео</button></div>
      </div>
    </article>`).join("") || `<div class="loader">Ничего не найдено</div>`;
}

function openDialog(id) {
  CURRENT = TOPICS.find((t) => t.id === id);
  $("#dlg-title").textContent = CURRENT.title;
  $("#dlg-meta").textContent = `Горячесть ${CURRENT.hotness}/100 · ${CURRENT.sources.join(", ")}`;
  const m = $("#minutes");
  m.value = CURRENT.recommended_minutes;
  $("#rec").textContent = `(рекомендовано ${CURRENT.recommended_minutes} мин — по количеству материала)`;
  $("#rec-mark").style.left = `calc(${((CURRENT.recommended_minutes - 1) / 29) * 100}% - 1px)`;
  $("#min-val").textContent = m.value;
  $("#publish").disabled = !CFG.keys.telegram;
  $("#publish").checked = false;
  $("#dlg").showModal();
}

$("#minutes").addEventListener("input", (e) => ($("#min-val").textContent = e.target.value));
$("#search").addEventListener("input", renderTopics);
$("#refresh").addEventListener("click", () => loadTrends(true));
$("#topics").addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) openDialog(b.dataset.id); });
$("#form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "go") return;
  e.preventDefault();
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
  if (!jobs.length) return;
  $("#jobs").innerHTML = jobs.map((j) => `
    <div class="job">
      <h4>${esc(j.topic.title)}</h4>
      <span class="status ${j.status}">${STATUS[j.status] || j.status}</span>
      <span class="muted"> · ${j.minutes || "авто"} мин${j.duration ? ` · вышло ${Math.floor(j.duration / 60)}:${String(j.duration % 60).padStart(2, "0")}` : ""}${j.size_mb ? ` · ${j.size_mb} МБ` : ""}</span>
      <div class="progress"><i style="width:${j.progress || 0}%"></i></div>
      ${j.video ? `<video controls preload="metadata" poster="${esc(j.cover || "")}" src="${esc(j.video)}"></video>` : ""}
      ${j.error ? `<p class="accent">${esc(j.error)}</p>` : ""}
      <div class="row" style="margin-top:8px;justify-content:flex-start">
        ${j.video ? `<a class="btn small ghost" href="${esc(j.video)}" download>⬇ Скачать</a>` : ""}
        ${(j.status === "done") && CFG.keys.telegram ? `<button class="btn small" data-pub="${j.id}">📤 В Telegram</button>` : ""}
      </div>
      <details><summary class="muted">журнал</summary><div class="log">${esc((j.log || []).join("\n"))}</div></details>
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
