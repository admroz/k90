"use strict";
import {
  escapeHTML,
  number,
  markdown,
  chart,
  formatTimestamp
} from "./render.mjs";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const labels = {
  dashboard: "Przegląd",
  chat: "Rozmowa",
  data: "Dane",
  documents: "Dokumenty"
};
let currentView = "dashboard",
  days = 30,
  session = null,
  tableOffset = 0,
  tableSort = null,
  tableDescending = true;
let history = new Map(),
  imageData = null,
  pendingSubmission = null,
  currentDocument = null,
  pollBusy = false,
  dashboardRequest = 0,
  tableRequest = 0,
  documentRequest = 0;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-K90-Request": "1",
      ...options.headers
    }
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/login") showLogin();
    throw new Error(typeof data.detail === "string" ? data.detail : "Nie udało się wykonać operacji. Sprawdź dane i spróbuj ponownie.");
  }
  return data;
}

function error(message) {
  $("#global-error").textContent = message;
  $("#global-error").hidden = !message;
}

function showLogin() {
  session = null;
  history.clear();
  $("#messages").replaceChildren();
  $("#jobs").replaceChildren();
  $("#app").hidden = true;
  $("#login-view").hidden = false;
}
async function enter() {
  session = await api("/api/session");
  $("#login-view").hidden = true;
  $("#app").hidden = false;
  $("#password").value = "";
  $("#mode-banner").hidden = !session.local && !session.preview;
  $("#mode-banner").textContent = session.preview ? "Lokalny podgląd · osobna kopia danych · chat demonstracyjny bez wywoływania AI" : "Lokalna kopia danych · agent AI włączony · synchronizacja źródeł wyłączona";
  updateTransport();
  $("#sync-data").disabled = !session.sync_enabled;
  $("#today").textContent = new Date().toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "long",
    year: "numeric"
  });
  const [tables, documents] = await Promise.all([api("/api/tables"), api("/api/documents")]);
  $("#table-select").innerHTML = tables.map(t => `<option>${escapeHTML(t)}</option>`).join("");
  $("#document-list").innerHTML = documents.map(t => `<button data-document="${escapeHTML(t)}">${t==="patient_summary"?"Pamięć pacjenta":escapeHTML(t)}</button>`).join("");
  $$("[data-document]").forEach(b => b.onclick = () => loadDocument(b.dataset.document).catch(e => error(e.message)));
  await navigate(labels[location.hash.slice(1)] ? location.hash.slice(1) : "dashboard");
}

function updateTransport() {
  const t = session.telegram;
  $("#transport-status").textContent = !session.telegram_enabled ? "Telegram wyłączony" : Date.now() / 1000 - t.at > 90 ? "Telegram: brak połączenia" : `Telegram: ${t.status}`;
}
async function navigate(view) {
  currentView = view;
  location.hash = view;
  error("");
  $$(".view").forEach(s => s.hidden = s.id !== `${view}-view`);
  $$("[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  $("#breadcrumb").textContent = labels[view].toUpperCase();
  if (view === "dashboard") await loadDashboard();
  if (view === "chat") await loadChat();
  if (view === "data") await loadTable();
  if (view === "documents") await loadDocument(currentDocument?.name || "pacjent.md");
}
async function loadDashboard() {
  const request = ++dashboardRequest;
  const d = await api(`/api/dashboard?days=${days}`);
  if (request !== dashboardRequest || !session) return;
  $("#date-range").textContent = `${d.from} — ${d.to}`;
  const configs = [
    ["Masa ciała", "waga", "waga_kg", "kg", 1],
    ["Sen", "sen", "total_sleep_min", "h", 1],
    ["HRV w nocy", "hrv", "hrv_noc", "ms", 0],
    ["Ciśnienie", "cisnienie", "skurczowe", "mmHg", 0]
  ];
  $("#kpis").innerHTML = configs.map(([title, table, key, unit, dec]) => {
    let r = d.latest[table],
      v = r?.[key];
    if (table === "sen" && v != null) v /= 60;
    return `<div class="kpi"><div class="kpi-label">${title}<span>↗</span></div><div class="kpi-value">${table==="cisnienie"&&r?`${number(v)}/${number(r.rozkurczowe)}`:number(v,dec)}<span>${unit}</span></div><small>${r?`Ostatni pomiar · ${escapeHTML(r.data)}`:"Brak pomiarów"}</small></div>`;
  }).join("");
  const sleep = d.sen.map(r => ({
    ...r,
    hours: r.total_sleep_min == null ? null : r.total_sleep_min / 60
  }));
  const configsCharts = [
    ["Masa ciała", "kg", d.waga, "waga_kg", "#608969"],
    ["Energia z posiłków", "kcal / dzień", d.kalorie, "kcal", "#b29b5a"],
    ["Długość snu", "godziny", sleep, "hours", "#7b87ad"],
    ["HRV w nocy", "ms", d.hrv, "hrv_noc", "#6a9993"],
    ["Ciśnienie skurczowe", "mmHg", d.cisnienie, "skurczowe", "#bc8772"],
    ["Body Battery", "maksimum dnia", d.body_battery, "max_bateria", "#83a465"],
    ["Aktywność", "minuty / aktywność", d.aktywnosci, "czas_trwania_min", "#608969"],
    ["Glukoza", "mg/dL · średnie godzinowe", d.glukoza, "glukoza", "#b29b5a", 2]
  ];
  $("#charts").innerHTML = configsCharts.map(([title, unit, rows, key, color, gap]) => `<section class="chart-card"><div class="chart-heading"><div><h2>${title}</h2><p>${unit}</p></div><button class="text-button discuss" data-topic="${title}">Omów ↗</button></div>${chart(rows,key,color,gap)}</section>`).join("");
  $$(".discuss").forEach(b => b.onclick = async () => {
    try {
      await navigate("chat");
      $("#message").value = `Przeanalizuj ${b.dataset.topic.toLowerCase()} w okresie ${d.from}–${d.to}. Uwzględnij dostępność danych i porównaj trendy.`;
      pendingSubmission = null;
      $("#message").focus();
    } catch (e) {
      error(e.message);
    }
  });
  $("#meals").innerHTML = d.posilki.slice(-4).reverse().map(r => `<div class="meal-row"><div><strong>${escapeHTML(r.opis||"Posiłek")}</strong><small>${escapeHTML(r.data)} · ${escapeHTML(r.czas||"")}</small></div><span>${number(r.kalorie)} kcal</span></div>`).join("") || '<div class="empty">Brak zapisanych posiłków.</div>';
  $("#sync-status").innerHTML = d.sync.map(r => `<div class="sync-row"><div>${escapeHTML(r.source)}<small>${escapeHTML(r.last_status||"Brak synchronizacji")}</small></div><small>${escapeHTML(r.last_success_at||"Jeszcze nie pobrano danych")}</small></div>`).join("") || '<div class="empty">Brak historii synchronizacji.</div>';
}
async function loadChat(before = null) {
  const [messages, jobs] = await Promise.all([api(`/api/messages${before?`?before=${before}`:""}`), api("/api/jobs")]);
  if (!session) return;
  const box = $("#messages"),
    atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  messages.forEach(m => history.set(m.id, m));
  const sorted = [...history.values()].sort((a, b) => a.id - b.id);
  const html = sorted.map(m => `<div class="message ${m.role==="user"?"user":"assistant"}"><div class="meta">${m.role==="user"?"Ty":"k90"} · ${escapeHTML(m.channel||"historia")} · ${escapeHTML(formatTimestamp(m.timestamp,session.timezone))}</div><div class="message-body">${m.role==="assistant"?markdown(m.content.text):escapeHTML(m.content.text)}</div>${m.content.has_image?'<div class="image-note">▧ Załączono zdjęcie</div>':""}</div>`).join("") || '<div class="empty">Zacznij od pytania. Twój agent ma wspólną pamięć w obu kanałach.</div>';
  if (box.innerHTML !== html) {
    const oldHeight = box.scrollHeight;
    box.innerHTML = html;
    if (before) box.scrollTop += box.scrollHeight - oldHeight;
    else if (atBottom) box.scrollTop = box.scrollHeight;
  }
  if (before || history.size <= 50) $("#older-messages").hidden = messages.length < 50;
  $("#jobs").innerHTML = jobs.map(j => `<div class="job ${j.state}"><strong>${{queued:"W kolejce",running:"Agent pracuje…",failed:"Błąd odpowiedzi",interrupted:"Przerwana odpowiedź"}[j.state]||j.state}</strong> · ${escapeHTML(j.payload.text.slice(0,100))}${j.response?`<div>${escapeHTML(j.response)}</div>`:""}</div>`).join("");
}
async function loadTable() {
  const request = ++tableRequest;
  const params = new URLSearchParams({
    offset: tableOffset,
    limit: 50,
    search: $("#table-search").value,
    descending: tableDescending
  });
  if (tableSort) params.set("sort", tableSort);
  const result = await api(`/api/tables/${encodeURIComponent($("#table-select").value)}?${params}`);
  if (request !== tableRequest || !session) return;
  $("#raw-table").innerHTML = `<thead><tr>${result.columns.map(c=>`<th><button data-sort="${escapeHTML(c)}">${escapeHTML(c)} ${tableSort===c?(tableDescending?"↓":"↑"):"↕"}</button></th>`).join("")}</tr></thead><tbody>${result.rows.map(r=>`<tr>${result.columns.map(c=>`<td><div class="cell">${r[c]===null?"—":escapeHTML(r[c])}</div></td>`).join("")}</tr>`).join("")||`<tr><td colspan="${result.columns.length}">Brak rekordów.</td></tr>`}</tbody>`;
  $("#row-count").textContent = `${result.total?tableOffset+1:0}–${tableOffset+result.rows.length} z ${result.total} rekordów`;
  $("#previous-page").disabled = tableOffset === 0;
  $("#next-page").disabled = tableOffset + 50 >= result.total;
  $$("[data-sort]").forEach(b => b.onclick = () => {
    tableDescending = tableSort === b.dataset.sort ? !tableDescending : true;
    tableSort = b.dataset.sort;
    tableOffset = 0;
    loadTable().catch(e => error(e.message));
  });
}
async function loadDocument(name) {
  const request = ++documentRequest;
  const loaded = await api(`/api/documents/${encodeURIComponent(name)}`);
  if (request !== documentRequest || !session) return;
  currentDocument = loaded;
  $("#document-title").textContent = name === "patient_summary" ? "Pamięć pacjenta" : name;
  const stamp = currentDocument.updated_at;
  $("#document-date").textContent = stamp ? `Ostatnia zmiana: ${typeof stamp==="number"?new Date(stamp*1000).toLocaleString("pl-PL"):stamp}` : "Brak zapisanego dokumentu";
  $("#document-content").innerHTML = markdown(currentDocument.content) || '<p class="subtle">Ten dokument nie ma jeszcze treści.</p>';
  $("#document-raw").textContent = currentDocument.content;
  $$("[data-document]").forEach(b => b.classList.toggle("selected", b.dataset.document === name));
}
$("#login-form").onsubmit = async event => {
  event.preventDefault();
  const b = event.submitter;
  b.disabled = true;
  try {
    await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        password: $("#password").value
      })
    });
    $("#login-error").textContent = "";
    await enter();
  } catch (e) {
    $("#login-error").textContent = e.message;
  } finally {
    b.disabled = false;
  }
};
$("#logout").onclick = async () => {
  try {
    await api("/api/logout", {
      method: "POST"
    });
    showLogin();
  } catch (e) {
    error(e.message);
  }
};
$$("[data-view]").forEach(b => b.onclick = () => navigate(b.dataset.view).catch(e => error(e.message)));
$("#refresh-dashboard").onclick = () => loadDashboard().catch(e => error(e.message));
$$("[data-days]").forEach(b => b.onclick = () => {
  days = Number(b.dataset.days);
  $$("[data-days]").forEach(x => x.classList.toggle("selected", x === b));
  loadDashboard().catch(e => error(e.message));
});
$("[data-open-meals]").onclick = () => {
  $("#table-select").value = "posilki";
  tableOffset = 0;
  tableSort = null;
  navigate("data").catch(e => error(e.message));
};
$("#sync-data").onclick = async () => {
  try {
    await api("/api/messages", {
      method: "POST",
      body: JSON.stringify({
        request_id: `web:${crypto.randomUUID()}`,
        text: "/update"
      })
    });
    await navigate("chat");
  } catch (e) {
    error(e.message);
  }
};
$("#older-messages").onclick = () => loadChat(Math.min(...history.keys())).catch(e => error(e.message));
$("#image").onchange = async () => {
  imageData = null;
  pendingSubmission = null;
  $("#attachment-name").textContent = "";
  $("#remove-image").hidden = true;
  const file = $("#image").files[0];
  if (!file) return;
  if (file.size > 5000000) {
    $("#chat-error").textContent = "Zdjęcie może mieć maksymalnie 5 MB.";
    return;
  }
  try {
    imageData = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    $("#attachment-name").textContent = file.name;
    $("#remove-image").hidden = false;
    pendingSubmission = null;
  } catch {
    $("#chat-error").textContent = "Nie udało się odczytać zdjęcia.";
  }
};
$("#remove-image").onclick = () => {
  imageData = null;
  $("#image").value = "";
  $("#attachment-name").textContent = "";
  $("#remove-image").hidden = true;
  pendingSubmission = null;
};
$("#message").oninput = () => pendingSubmission = null;
$("#message").onkeydown = event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$("#send-message").disabled) $("#chat-form").requestSubmit();
  }
};
$("#chat-form").onsubmit = async event => {
  event.preventDefault();
  const b = $("#send-message");
  b.disabled = true;
  try {
    pendingSubmission ||= {
      request_id: `web:${crypto.randomUUID()}`,
      text: $("#message").value,
      image: imageData
    };
    await api("/api/messages", {
      method: "POST",
      body: JSON.stringify(pendingSubmission)
    });
    $("#message").value = "";
    $("#remove-image").click();
    pendingSubmission = null;
    $("#chat-error").textContent = "";
    await loadChat();
  } catch (e) {
    $("#chat-error").textContent = e.message + " Możesz ponowić wysyłanie tej samej wiadomości.";
  } finally {
    b.disabled = false;
  }
};
$("#table-form").onsubmit = e => {
  e.preventDefault();
  tableOffset = 0;
  loadTable().catch(e => error(e.message));
};
$("#table-select").onchange = () => {
  tableOffset = 0;
  tableSort = null;
  loadTable().catch(e => error(e.message));
};
$("#previous-page").onclick = () => {
  tableOffset = Math.max(0, tableOffset - 50);
  loadTable().catch(e => error(e.message));
};
$("#next-page").onclick = () => {
  tableOffset += 50;
  loadTable().catch(e => error(e.message));
};
$("#toggle-raw").onclick = () => {
  const raw = $("#document-raw");
  raw.hidden = !raw.hidden;
  $("#document-content").hidden = !raw.hidden;
  $("#toggle-raw").textContent = raw.hidden ? "Pokaż źródło" : "Pokaż dokument";
};
setInterval(async () => {
  if (!session || document.hidden || pollBusy) return;
  pollBusy = true;
  try {
    if (currentView === "chat") await loadChat();
    session = await api("/api/session");
    updateTransport();
  } catch (e) {
    error(e.message);
  } finally {
    pollBusy = false;
  }
}, 2500);
enter().catch(() => showLogin());
window.addEventListener("hashchange", () => {
  const view = location.hash.slice(1);
  if (session && labels[view] && view !== currentView) navigate(view).catch(e => error(e.message));
});
