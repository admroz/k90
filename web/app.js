"use strict";
import {
  escapeHTML,
  renderTimeline,
  number,
  markdown,
  chart,
  formatTimestamp,
  mealSummary,
  mealList,
  mealDayLabel,
  energyBalance,
  activityList
} from "./render.mjs";
import { createRequestId } from "./request.mjs";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const labels = {
  dashboard: "Przegląd",
  recovery: "Regeneracja",
  activity: "Aktywność",
  chat: "Rozmowa",
  data: "Dane",
  documents: "Dokumenty",
  timings: "Diagnostyka / Czasy",
  catalog: "Katalog"
};
let currentView = "dashboard",
  days = 30,
  session = null,
  tableOffset = 0,
  tableSort = null,
  tableDescending = true;
let history = new Map(),
  imageData = [],
  attachmentVersion = 0,
  pendingSubmission = null,
  currentDocument = null,
  pollBusy = false,
  dashboardRequest = 0,
  tableRequest = 0,
  documentRequest = 0;
let mealDate = null, mealView = null, mealRequest = 0;
let garminActive = false, garminPendingRequest = null, garminStatusBusy = false, garminStatusVersion = 0;

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
let catalogLoader;
async function loadCatalog() {
  if (!catalogLoader) {
    const { setupCatalog } = await import('./catalog.mjs');
    catalogLoader = setupCatalog(api, $('#catalog-view'), err => error(err.message));
  }
  await catalogLoader();
}

function showLogin() {
  session = null;
  history.clear();
  mealDate = null;
  mealView = null;
  mealRequest++;
  garminActive = false;
  garminPendingRequest = null;
  garminStatusVersion++;
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
  updateSyncButtons();
  $("#today").textContent = new Date().toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "long",
    year: "numeric"
  });
  const [tables, documents] = await Promise.all([api("/api/tables"), api("/api/documents")]);
  $("#table-select").innerHTML = tables.map(t => `<option>${escapeHTML(t)}</option>`).join("");
  $("#document-list").innerHTML = documents.map(t => `<button data-document="${escapeHTML(t)}">${t==="patient_summary"?"Pamięć pacjenta":escapeHTML(t)}</button>`).join("");
  $$("[data-document]").forEach(b => b.onclick = () => loadDocument(b.dataset.document).catch(e => error(e.message)));
  await checkGarminSync(false);
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
  if (view === "recovery" || view === "activity") await loadHealthView(view);
  if (view === "chat") await loadChat();
  if (view === "data") await loadTable();
  if (view === "documents") await loadDocument(currentDocument?.name || "pacjent.md");
  if (view === "catalog") await loadCatalog();
  if (view === "timings") {
    const { loadProfiling } = await import("./profiling.mjs");
    await loadProfiling(api, $("#timings-content"));
  }
}
async function loadDashboard() {
  const request = ++dashboardRequest;
  const [d] = await Promise.all([api(`/api/dashboard?days=${days}`), loadMeals()]);
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
  const configsCharts = [
    ["Masa ciała", "kg", d.waga, "waga_kg", "#9fc7a3"],
    ["Ciśnienie skurczowe", "mmHg", d.cisnienie, "skurczowe", "#d7a48b"],
    ["Glukoza", "mg/dL · średnie godzinowe", d.glukoza, "glukoza", "#d3b974", 2]
  ];
  renderCharts("#charts", configsCharts, d);
  $("#sync-status").innerHTML = d.sync.map(r => {
    const status = r.last_status || "";
    const label = status.startsWith("running") ? "Pobieranie danych" : status.startsWith("success") ? "Pobrano dane" : status.startsWith("error") ? "Błąd pobierania" : "Brak synchronizacji";
    return `<div class="sync-row"><div>${escapeHTML(r.source === "garmin" ? "Garmin" : r.source === "libre" ? "Libre" : r.source)}<small>${label}</small></div><small>${r.last_success_at ? escapeHTML(formatTimestamp(r.last_success_at)) : "Jeszcze nie pobrano danych"}</small></div>`;
  }).join("") || '<div class="empty">Brak historii synchronizacji.</div>';
}
function renderCharts(target, configs, d) {
  $(target).innerHTML = configs.map(([title, unit, rows, key, color, gap]) => `<section class="chart-card"><div class="chart-heading"><div><h2>${title}</h2><p>${unit}</p></div><button class="text-button discuss" data-topic="${title}">Omów ↗</button></div>${chart(rows,key,color,gap)}</section>`).join("");
  $$(`${target} .discuss`).forEach(b => b.onclick = async () => {
    try {
      await navigate("chat");
      $("#message").value = `Przeanalizuj ${b.dataset.topic.toLowerCase()} w okresie ${d.from}–${d.to}. Uwzględnij dostępność danych i porównaj trendy.`;
      pendingSubmission = null;
      $("#message").focus();
    } catch (e) {
      error(e.message);
    }
  });
}
async function loadHealthView(view) {
  const request = ++dashboardRequest;
  const d = await api(`/api/dashboard?days=${days}`);
  if (request !== dashboardRequest || !session || currentView !== view) return;
  $(`#${view}-range`).textContent = `${d.from} — ${d.to}`;
  if (view === "recovery") {
    const sleep = d.sen.map(row => ({...row, hours: row.total_sleep_min == null ? null : row.total_sleep_min / 60}));
    renderCharts("#recovery-charts", [
      ["Długość snu", "godziny", sleep, "hours", "#a6b3da"],
      ["HRV w nocy", "ms", d.hrv, "hrv_noc", "#87bdb5"],
      ["Body Battery", "maksimum dnia", d.body_battery, "max_bateria", "#b0c78a"],
      ["Tętno spoczynkowe", "uderzenia / min", d.metryki_dzienne, "rhr", "#d7a48b"],
      ["Średni stres", "wskaźnik Garmin", d.metryki_dzienne, "avg_stres", "#d3b974"],
      ["Oddech", "oddechy / min", d.metryki_dzienne, "avg_oddech", "#9fc7a3"]
    ], d);
  } else {
    renderCharts("#activity-charts", [
      ["Czas aktywności", "minuty / aktywność", d.aktywnosci, "czas_trwania_min", "#9fc7a3"],
      ["Dystans", "km / aktywność", d.aktywnosci, "dystans_km", "#a6b3da"],
      ["Kalorie aktywne", "kcal / dzień · Garmin", d.kalorie_dzienne, "aktywne_kcal", "#d3b974"],
      ["Spalanie łącznie", "spoczynkowe + aktywne · kcal / dzień", d.kalorie_dzienne, "spalone_kcal", "#87bdb5"]
    ], d);
    $("#activities").innerHTML = activityList(d.aktywnosci);
  }
}
async function loadMeals(day = mealDate) {
  const request = ++mealRequest;
  mealDate = day;
  const controls = ["#meal-previous", "#meal-next", "#meal-date", "#meal-today"];
  $("#meals-panel").setAttribute("aria-busy", "true");
  controls.forEach(selector => $(selector).disabled = true);
  $("#meal-error").hidden = true;
  try {
    const data = await api(`/api/meals${day ? `?date=${encodeURIComponent(day)}` : ""}`);
    if (request !== mealRequest || !session) return;
    mealView = data;
    mealDate = data.date === data.today ? null : data.date;
    $("#meal-date").value = data.date;
    $("#meal-date").max = data.today;
    $("#meal-day-label").textContent = mealDayLabel(data.date, data.today);
    $("#meal-summary").innerHTML = mealSummary(data.totals, data.missing_values);
    $("#energy-balance").innerHTML = energyBalance(data);
    $("#meal-note").hidden = !Object.values(data.missing_values).some(count => count > 0);
    $("#meals").innerHTML = mealList(data.meals);
  } catch (e) {
    if (request !== mealRequest || !session) return;
    // Keep the previous day and its data together if navigation fails.
    if (mealView) $("#meal-date").value = mealView.date;
    mealDate = mealView && mealView.date !== mealView.today ? mealView.date : null;
    $("#meal-error").textContent = e.message;
    $("#meal-error").hidden = false;
  } finally {
    if (request === mealRequest) {
      $("#meals-panel").setAttribute("aria-busy", "false");
      $("#meal-date").disabled = false;
      $("#meal-previous").disabled = !mealView?.previous_date;
      $("#meal-next").disabled = !mealView?.next_date;
      $("#meal-today").disabled = !!mealView && mealView.date === mealView.today;
    }
  }
}
$("#meal-previous").onclick = () => loadMeals(mealView.previous_date);
$("#meal-next").onclick = () => loadMeals(mealView.next_date);
$("#meal-today").onclick = () => loadMeals(null);
$("#meal-date").onchange = () => {
  const input = $("#meal-date");
  if (input.value && input.checkValidity()) loadMeals(input.value);
  else if (mealView) input.value = mealView.date;
};
// The editor owns a snapshot/revision. Loads never replace its typed values.
const mealEditor = $("#meal-editor"), mealForm = $("#meal-edit-form");
let editingMeal = null, mealSaveBusy = false, mealLastInput = null;
const mealFields = [
  ["description", "Nazwa / opis", "opis", "text"],
  ["quantity", "Ilość", "quantity", "decimal"],
  ["unit", "Jednostka", "unit", "unit"],
  ["calories", "Kalorie (kcal)", "kalorie", "decimal"],
  ["protein_g", "Białko (g)", "bialko_g", "decimal"],
  ["carbs_g", "Węglowodany (g)", "weglowodany_g", "decimal"],
  ["fat_g", "Tłuszcz (g)", "tluszcze_g", "decimal"],
  ["date", "Data", "data", "date"],
  ["time", "Godzina", "czas", "time"]
];
function buildMealFields() {
if ($("#meal-fields").childElementCount) return;
for (const [name, title, , type] of mealFields) {
  const label = document.createElement("label");
  label.textContent = title;
  const input = document.createElement(type === "unit" ? "select" : "input");
  input.name = name;
  if (type === "unit") {
    for (const value of ["", "g", "ml", "szt"]) {
      const option = document.createElement("option");
      option.value = value; option.textContent = value || "Niepodana";
      input.append(option);
    }
  } else {
    input.type = type === "decimal" ? "text" : type;
    if (type === "decimal") input.inputMode = "decimal";
    if (name === "description") { input.required = true; input.maxLength = 2000; }
    if (name === "date") input.required = true;
  }
  input.onfocus = () => { mealLastInput = input; };
  label.append(input); $("#meal-fields").append(label);
}
}
function mealEditError(message) {
  $("#meal-edit-error").textContent = message;
  $("#meal-edit-error").hidden = !message;
}
$("#meal-edit-cancel").onclick = () => mealEditor.close();
mealEditor.oncancel = event => { if (mealSaveBusy) event.preventDefault(); };
$("#meals").onclick = async event => {
  const button = event.target.closest("[data-meal-edit], [data-meal-delete]");
  if (!button || mealSaveBusy) return;
  const id = Number(button.dataset.mealEdit || button.dataset.mealDelete);
  const meal = mealView?.meals.find(row => row.id === id);
  if (!meal) return;
  if (button.dataset.mealEdit) {
    buildMealFields();
    editingMeal = {...meal};
    for (const [name, , source] of mealFields) mealForm.elements[name].value = meal[source] ?? "";
    mealEditError(""); mealEditor.showModal();
    mealForm.elements.description.focus();
    return;
  }
  if (!window.confirm(`Usunąć posiłek „${meal.opis}” z ${meal.data} ${meal.czas || ""}?`)) return;
  mealSaveBusy = true; button.disabled = true;
  ++mealRequest; ++dashboardRequest;
  try {
    await api(`/api/meals/${meal.id}`, {method: "DELETE", body: JSON.stringify({
      expected_revision: meal.revision, request_id: createRequestId()
    })});
    $("#meal-result").textContent = "Posiłek usunięty.";
    await loadDashboard().catch(e => error(`Usunięto posiłek. Odśwież widok: ${e.message}`));
  } catch (e) {
    $("#meal-error").textContent = `${e.message} Odśwież listę przed kolejną próbą usunięcia.`;
    $("#meal-error").hidden = false;
  } finally { mealSaveBusy = false; button.disabled = false; }
};
mealForm.onsubmit = async event => {
  event.preventDefault();
  if (mealSaveBusy) return;
  const body = {expected_revision: editingMeal.revision, request_id: createRequestId()};
  try {
    for (const [name, title, , type] of mealFields) {
      const value = mealForm.elements[name].value.trim();
      if (type === "decimal") {
        // Accept one Polish decimal comma deliberately; no exponent/group separators.
        if (value && !/^\d+(?:[.,]\d+)?$/.test(value)) throw new Error(`${title}: wpisz nieujemną liczbę, np. 12,5, albo pozostaw puste.`);
        body[name] = value === "" ? null : Number(value.replace(",", "."));
        if (body[name] !== null && (!Number.isFinite(body[name]) || body[name] > 1000000)) throw new Error(`${title}: zakres 0–1000000.`);
      } else body[name] = value || (name === "unit" || name === "time" ? null : "");
    }
    if ((body.quantity === null) !== (body.unit === null)) throw new Error("Podaj ilość i jednostkę razem albo pozostaw oba puste.");
  } catch (e) { mealEditError(e.message); mealLastInput?.focus(); return; }
  mealSaveBusy = true;
  const focus = mealLastInput;
  const buttons = [...mealForm.querySelectorAll("button")];
  buttons.forEach(button => button.disabled = true);
  ++mealRequest; ++dashboardRequest;
  try {
    await api(`/api/meals/${editingMeal.id}`, {method: "PUT", body: JSON.stringify(body)});
    mealEditor.close();
    $("#meal-result").textContent = "Zmiany posiłku zapisane.";
    // The dashboard range and current day are fetched anew; moved days have no cache.
    await loadDashboard().catch(e => error(`Zapisano posiłek. Odśwież widok: ${e.message}`));
  } catch (e) {
    mealEditError(`${e.message} Wartości zachowano. Przy konflikcie zamknij formularz, odśwież listę i otwórz go ponownie.`);
    focus?.focus();
  } finally { mealSaveBusy = false; buttons.forEach(button => button.disabled = false); }
};
async function loadChat(before = null) {
  const messages = await api(`/api/messages${before?`?before=${before}`:""}`);
  if (!session) return;
  // Refresh previously loaded pages as well: an old queued job can finish
  // after many later submissions have pushed it out of the newest page.
  if (!before && history.size) {
    const oldest = Math.min(...history.keys());
    let page = messages;
    while (page.length === 50 && page[0].id > oldest) {
      page = await api(`/api/messages?before=${page[0].id}`);
      if (!session) return;
      messages.unshift(...page);
    }
  }
  const box = $("#messages"),
    atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  const oldTop = box.scrollTop;
  const anchor = [...box.children].find(node => node.getBoundingClientRect().bottom > box.getBoundingClientRect().top);
  const anchorId = anchor?.dataset.messageId;
  const anchorTop = anchor?.getBoundingClientRect().top;
  messages.forEach(m => history.set(m.id, m));
  const sorted = [...history.values()].sort((a, b) => a.id - b.id);
  const html = renderTimeline(sorted, session.timezone);
  if (box.innerHTML !== html) {
    const oldHeight = box.scrollHeight;
    box.innerHTML = html;
    const restoredAnchor = anchorId && [...box.children].find(node => node.dataset.messageId === anchorId);
    // Replacing the list can reset/clamp its scroll offset. Restore within this
    // layout turn: CSS smooth scrolling would paint the wrong history first.
    const top = !before && atBottom ? box.scrollHeight : restoredAnchor
      ? box.scrollTop + restoredAnchor.getBoundingClientRect().top - anchorTop
      : before ? oldTop + box.scrollHeight - oldHeight : oldTop;
    box.scrollTo({top, behavior: "instant"});
  }
  if (before || history.size <= 50) $("#older-messages").hidden = messages.length < 50;
  $("#jobs").innerHTML = "";
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
  $$("[data-days]").forEach(x => x.classList.toggle("selected", Number(x.dataset.days) === days));
  (currentView === "recovery" || currentView === "activity" ? loadHealthView(currentView) : loadDashboard()).catch(e => error(e.message));
});
$("[data-open-meals]").onclick = () => {
  $("#table-select").value = "posilki";
  tableOffset = 0;
  tableSort = null;
  navigate("data").catch(e => error(e.message));
};
function updateSyncButtons() {
  ["#sync-data", "#sync-garmin"].forEach(selector => {
    $(selector).disabled = !session?.sync_enabled || garminActive;
    $(selector).textContent = garminActive ? "Pobieranie…" : "Pobierz Garmin ↻";
  });
}
async function checkGarminSync(refresh = true) {
  if (!session || garminStatusBusy) return;
  garminStatusBusy = true;
  const version = garminStatusVersion;
  try {
    const job = await api("/api/sync/garmin");
    if (!session || version !== garminStatusVersion) return;
    const wasActive = garminActive;
    garminActive = !!job && ["queued", "running"].includes(job.state);
    if (job) {
      $("#garmin-sync-status").textContent = job.state === "queued" ? "Garmin: oczekiwanie na rozpoczęcie pobierania." : job.state === "running" ? `Pobieranie danych Garmin…${job.calories_through ? ` Kalorie zapisane do ${job.calories_through}.` : " Pierwsze uzupełnienie historii może potrwać dłużej."}` : job.response;
    }
    updateSyncButtons();
    if (refresh && wasActive && job?.state === "done" && currentView === "dashboard") await loadDashboard();
  } catch (e) {
    if (session && version === garminStatusVersion) $("#garmin-sync-status").textContent = e.message;
  } finally {
    garminStatusBusy = false;
  }
}
async function startGarminSync() {
  if (!session?.sync_enabled || garminActive) return;
  garminStatusVersion++;
  const version = garminStatusVersion;
  garminPendingRequest ||= createRequestId();
  garminActive = true;
  updateSyncButtons();
  try {
    await api("/api/sync/garmin", {
      method: "POST",
      body: JSON.stringify({request_id: garminPendingRequest})
    });
    if (!session || version !== garminStatusVersion) return;
    garminPendingRequest = null;
    await checkGarminSync();
  } catch (e) {
    if (!session || version !== garminStatusVersion) return;
    garminActive = false;
    updateSyncButtons();
    $("#garmin-sync-status").textContent = `${e.message} Możesz ponowić pobieranie.`;
  }
}
$("#sync-data").onclick = startGarminSync;
$("#sync-garmin").onclick = startGarminSync;
$("#older-messages").onclick = () => loadChat(Math.min(...history.keys())).catch(e => error(e.message));
function renderAttachments() {
  const root = $("#attachment-name");
  root.replaceChildren();
  imageData.forEach((photo, index) => {
    const item = document.createElement("span");
    const img = document.createElement("img");
    img.src = photo.url; img.alt = photo.name; img.width = 64; img.height = 64;
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = `Usuń ${photo.name}`;
    remove.onclick = () => { imageData.splice(index, 1); pendingSubmission = null; renderAttachments(); };
    item.append(img, remove); root.append(item);
  });
  if (imageData.length) root.append(document.createTextNode(` ${imageData.length}/4 · ${(imageData.reduce((n,p) => n+p.size,0)/1000000).toFixed(2)}/10 MB`));
  $("#remove-image").hidden = !imageData.length;
}
$("#image").onchange = async () => {
  const version = ++attachmentVersion;
  const files = Array.from($("#image").files);
  if (!files.length) return;
  if (files.length > 4 || files.some(f => f.size > 5000000) || files.reduce((n,f) => n+f.size,0) > 10000000) {
    $("#chat-error").textContent = "Wybierz 1–4 zdjęcia, każde do 5 MB, łącznie do 10 MB.";
    return;
  }
  if (files.some(f => !["image/jpeg","image/png","image/webp"].includes(f.type))) {
    $("#chat-error").textContent = "Obsługujemy JPG, PNG i WebP.";
    return;
  }
  $("#send-message").disabled = true;
  try {
    const photos = [];
    for (const file of files) {
      const url = await new Promise((resolve,reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result);
        reader.onerror = reject; reader.readAsDataURL(file);
      });
      photos.push({url, name:file.name, size:file.size});
    }
    if (version !== attachmentVersion) return;
    imageData = photos; pendingSubmission = null;
    $("#chat-error").textContent = ""; renderAttachments();
  } catch {
    $("#chat-error").textContent = "Nie udało się odczytać zdjęć.";
  } finally { if (version === attachmentVersion) $("#send-message").disabled = false; }
};
$("#remove-image").onclick = () => {
  ++attachmentVersion;
  imageData = []; $("#image").value = ""; pendingSubmission = null;
  renderAttachments();
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
      request_id: createRequestId(),
      text: $("#message").value,
      ...(imageData.length ? {images:imageData.map(p => p.url)} : {})
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
    updateSyncButtons();
    if (garminActive) await checkGarminSync();
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
