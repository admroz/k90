// Pure rendering helpers: input text is escaped before it becomes markup.
export const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
} [c]));
export const number = (value, digits = 0) => value == null ? "—" : Number(value).toLocaleString("pl-PL", {
  maximumFractionDigits: digits
});

export function mealSummary(totals, missing) {
  return [
    ["Kalorie", "kalorie", "kcal"], ["Białko", "bialko_g", "g"],
    ["Węglowodany", "weglowodany_g", "g"], ["Tłuszcz", "tluszcze_g", "g"]
  ].map(([label, key, unit]) => `<div><span>${label}</span><strong>${number(totals[key], 1)}${missing[key] && totals[key] != null ? " *" : ""} <small>${unit}</small></strong></div>`).join("");
}

export function energyBalance(data) {
  const energy = data.energy || {};
  const balance = energy.balance_kcal;
  const signed = balance > 0 ? `+${number(balance, 0)}` : number(balance, 0);
  let note = "Zapisane kalorie minus spalanie. Minus oznacza deficyt, plus — nadwyżkę.";
  if (energy.burned_kcal == null) note = "Brak kompletnych danych Garmin o spalaniu dla tego dnia.";
  else if (!data.meals.length) note = "Zapisz posiłki, aby obliczyć bilans dnia.";
  else if (data.missing_values.kalorie) note = "Bilans niedostępny: część posiłków nie ma podanych kalorii.";
  return `<dl class="energy-breakdown"><div><dt>Zapisane kalorie</dt><dd>${number(data.totals?.kalorie, 0)}${data.missing_values.kalorie ? " *" : ""} kcal</dd></div><div><dt>Spoczynkowe</dt><dd>${number(energy.resting_kcal, 0)} kcal</dd></div><div><dt>Aktywne</dt><dd>${number(energy.active_kcal, 0)} kcal</dd></div><div><dt>Spalone łącznie</dt><dd>${number(energy.burned_kcal, 0)} kcal</dd></div></dl><div class="energy-result"><span>Bilans dnia</span><strong>${signed} <small>kcal</small></strong></div><p class="subtle">${note}</p><p class="subtle">Spalanie jest estymacją Garmin.${energy.day_in_progress ? " Dzień jeszcze trwa; wartości mogą się zmienić." : ""}${energy.fetched_at ? ` Odczyt: ${escapeHTML(formatTimestamp(energy.fetched_at))}.` : ""}</p>`;
}

export function activityList(rows) {
  return rows.slice(-20).reverse().map(row => `<div class="meal-row"><div class="meal-description"><strong>${escapeHTML(row.nazwa || row.typ || "Aktywność")}</strong><small>${escapeHTML(row.data)} · ${escapeHTML(row.czas || "")}</small><p class="meal-macros">${number(row.czas_trwania_min, 0)} min · ${number(row.dystans_km, 1)} km</p></div><span>${number(row.kalorie, 0)} kcal</span></div>`).join("") || '<div class="empty">Brak aktywności w wybranym okresie.</div>';
}

export function mealList(meals) {
  return meals.map(meal => `<div class="meal-row"><div class="meal-description"><strong>${escapeHTML(meal.opis || "Posiłek")}</strong><small>${escapeHTML(meal.czas || "Godzina niepodana")}</small><p class="meal-macros">Białko ${number(meal.bialko_g, 1)} g · Węglowodany ${number(meal.weglowodany_g, 1)} g · Tłuszcz ${number(meal.tluszcze_g, 1)} g</p></div><span>${number(meal.kalorie, 1)} kcal</span></div>`).join("") || '<div class="empty">Brak zapisanych posiłków w tym dniu.</div>';
}

export function mealDayLabel(day, today) {
  // ISO calendar dates come from the server's application timezone.
  const yesterday = new Date(`${today}T12:00:00Z`);
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const prefix = day === today ? "Dzisiaj · " : day === yesterday.toISOString().slice(0, 10) ? "Wczoraj · " : "";
  return prefix + new Date(`${day}T12:00:00Z`).toLocaleDateString("pl-PL", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC"
  });
}

function inline(text) {
  return escapeHTML(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
}

export function markdown(text) {
  // Deliberately supports a small subset. Raw HTML, images and links stay text.
  const lines = String(text).split("\n"),
    result = [];
  let inCode = false,
    list = null;
  const closeList = () => {
    if (list) {
      result.push(`</${list}>`);
      list = null;
    }
  };
  const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    if (raw.startsWith("```")) {
      closeList();
      result.push(inCode ? "</code></pre>" : "<pre><code>");
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      result.push(escapeHTML(raw) + "\n");
      continue;
    }
    if (raw.includes("|") && i + 1 < lines.length && cells(lines[i + 1]).every(c => /^:?-{3,}:?$/.test(c))) {
      closeList();
      result.push(`<div class="markdown-table"><table><thead><tr>${cells(raw).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>`);
      i += 1;
      while (i + 1 < lines.length && lines[i + 1].includes("|") && lines[i + 1].trim()) {
        i += 1;
        result.push(`<tr>${cells(lines[i]).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`);
      }
      result.push("</tbody></table></div>");
      continue;
    }
    const heading = raw.match(/^(#{1,3}) (.+)/);
    const item = raw.match(/^(?:([-*])|\d+\.) (.+)/);
    if (item) {
      const kind = item[1] ? "ul" : "ol";
      if (list !== kind) {
        closeList();
        result.push(`<${kind}>`);
        list = kind;
      }
      result.push(`<li>${inline(item[2])}</li>`);
    } else {
      closeList();
      if (heading) result.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`);
      else if (raw.startsWith("> ")) result.push(`<blockquote>${inline(raw.slice(2))}</blockquote>`);
      else if (raw.trim()) result.push(`<p>${inline(raw)}</p>`);
    }
  }
  closeList();
  if (inCode) result.push("</code></pre>");
  return result.join("\n");
}

export function formatTimestamp(value, timezone = "Europe/Warsaw") {
  if (!value) return "—";
  // SQLite CURRENT_TIMESTAMP is UTC. Preserve explicit offsets in newer records.
  const normalized = value.replace(" ", "T");
  const date = new Date(normalized + (/Z$|[+-]\d{2}:?\d{2}$/.test(normalized) ? "" : "Z"));
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("pl-PL", {
    timeZone: timezone
  });
}

export function chart(rows, key, color = "#9fc7a3", maxGapHours = 48) {
  const points = rows.filter(r => r[key] != null && r[key] !== "" && Number.isFinite(Number(r[key])))
    .map(r => ({
      x: Date.parse(r.data.length === 10 ? r.data + "T12:00:00" : r.data),
      y: Number(r[key]),
      date: r.data
    }))
    .filter(p => Number.isFinite(p.x)).sort((a, b) => a.x - b.x);
  if (!points.length) return '<div class="empty">Brak pomiarów w wybranym okresie.</div>';
  const w = 500,
    h = 154,
    pad = 40;
  const min = Math.min(...points.map(p => p.y)),
    max = Math.max(...points.map(p => p.y));
  const spread = max - min || Math.max(Math.abs(max) * .05, 1),
    low = min - spread * .2,
    high = max + spread * .2;
  const x0 = points[0].x,
    x1 = points.at(-1).x;
  const xpos = p => x1 === x0 ? w / 2 : pad + (p.x - x0) / (x1 - x0) * (w - pad - 10);
  const ypos = p => 12 + (high - p.y) / (high - low) * (h - 38);
  let path = "";
  points.forEach((p, i) => {
    const gap = i && p.x - points[i - 1].x > maxGapHours * 3600000;
    path += `${i && !gap ? "L" : "M"}${xpos(p).toFixed(1)},${ypos(p).toFixed(1)} `;
  });
  const safeColor = /^#[0-9a-f]{6}$/i.test(color) ? color : "#9fc7a3";
  const grid = [low, (low + high) / 2, high].map(y => {
    const py = ypos({
      y
    });
    return `<line x1="${pad}" y1="${py}" x2="${w-10}" y2="${py}" stroke="var(--line)"/><text x="0" y="${py+3}">${number(y,1)}</text>`;
  }).join("");
  const dots = points.length < 100 ? points.map(p => `<circle cx="${xpos(p)}" cy="${ypos(p)}" r="2.8" fill="${safeColor}"><title>${escapeHTML(p.date)}: ${number(p.y,1)}</title></circle>`).join("") : "";
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Wykres: ${points.length} pomiarów, od ${number(min,1)} do ${number(max,1)}">${grid}<path d="${path}" fill="none" stroke="${safeColor}" stroke-width="2.5" stroke-linejoin="round"/>${dots}<text x="${pad}" y="${h-1}">${escapeHTML(points[0].date.slice(5,10))}</text><text x="${w-10}" y="${h-1}" text-anchor="end">${escapeHTML(points.at(-1).date.slice(5,10))}</text></svg><p class="chart-summary">${points.length} pomiarów · zakres ${number(min,1)}–${number(max,1)}</p>`;
}
