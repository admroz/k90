import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";
import * as render from "../web/render.mjs";

function dayData(day = "2026-10-23", calories = 600) {
  return {
    date: day, today: "2026-10-23",
    previous_date: day === "2026-10-23" ? "2026-10-22" : "2026-10-21",
    next_date: day === "2026-10-23" ? null : "2026-10-23",
    meals: [{opis: `Posiłek ${day}`, czas: "12:00", kalorie: calories, bialko_g: 30, weglowodany_g: 50, tluszcze_g: 10}],
    totals: {kalorie: calories, bialko_g: 30, weglowodany_g: 50, tluszcze_g: 10},
    missing_values: {kalorie: 0, bialko_g: 0, weglowodany_g: 0, tluszcze_g: 0}
  };
}

async function app(mealsHandler) {
  const source = (await readFile(new URL("../web/app.js", import.meta.url), "utf8"))
    .replace(/^import\s+[\s\S]*?\s+from\s+["'][^"']+["'];\n?/gm, "");
  const elements = new Map(), requests = [];
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, {
      value: "", textContent: "", innerHTML: "", hidden: false, disabled: false,
      setAttribute(name, value) { this[name] = value; },
      replaceChildren() {}, checkValidity() { return true; }
    });
    return elements.get(selector);
  }
  const context = vm.createContext({
    ...render, trackSelectionGesture: () => () => false,
    document: {querySelector: element, querySelectorAll: () => []},
    window: {addEventListener() {}}, location: {hash: ""}, setInterval() {},
    async fetch(path) {
      requests.push(path);
      if (path === "/api/session") return {ok: false, status: 401, json: async () => ({detail: "Zaloguj się"})};
      if (path.startsWith("/api/meals")) {
        const body = await mealsHandler(new URL(path, "http://test").searchParams.get("date"));
        return {ok: true, json: async () => body};
      }
      assert.ok(path.startsWith("/api/dashboard"));
      return {ok: true, json: async () => ({
        from: "2026-10-17", to: "2026-10-23", latest: {},
        waga: [], sen: [], hrv: [], cisnienie: [], kalorie: [], body_battery: [], aktywnosci: [], glukoza: [], sync: [], kalorie_dzienne: [], metryki_dzienne: []
      })};
    }
  });
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("session = {}", context);
  return {element, requests, evaluate: expression => vm.runInContext(expression, context)};
}

test("Meal navigation defaults to today and retains the selected day when charts refresh", async () => {
  const ui = await app(day => dayData(day || undefined));
  await ui.evaluate("loadMeals()");
  assert.equal(ui.element("#meal-date").value, "2026-10-23");
  assert.equal(ui.element("#meal-next").disabled, true);
  assert.equal(ui.element("#meal-today").disabled, true);
  await ui.element("#meal-previous").onclick();
  assert.equal(ui.element("#meal-date").value, "2026-10-22");
  assert.ok(ui.element("#meal-day-label").textContent.startsWith("Wczoraj"));
  assert.equal(ui.element("#meal-next").disabled, false);
  await ui.evaluate("days = 7; loadDashboard()");
  assert.ok(ui.requests.includes("/api/dashboard?days=7"));
  assert.equal(ui.requests.at(-1), "/api/meals?date=2026-10-22");
  assert.equal(ui.element("#meal-date").value, "2026-10-22");
  await ui.element("#meal-today").onclick();
  assert.equal(ui.requests.at(-1), "/api/meals");
  assert.equal(ui.element("#meal-date").value, "2026-10-23");
});

test("An older response cannot overwrite the most recently requested meal day", async () => {
  const pending = new Map();
  const ui = await app(day => !day ? dayData() : new Promise(resolve => pending.set(day, resolve)));
  await ui.evaluate("loadMeals()");
  const older = ui.evaluate('loadMeals("2026-10-22")');
  const latest = ui.evaluate('loadMeals("2026-10-21")');
  pending.get("2026-10-21")(dayData("2026-10-21", 900));
  await latest;
  pending.get("2026-10-22")(dayData("2026-10-22", 300));
  await older;
  assert.equal(ui.element("#meal-date").value, "2026-10-21");
  assert.ok(ui.element("#meal-summary").innerHTML.includes("900"));
  assert.ok(!ui.element("#meal-summary").innerHTML.includes("300"));
});

test("Failed navigation preserves the previous day's date and totals and allows retry", async () => {
  const ui = await app(day => {
    if (day) throw new Error("Connection lost");
    return dayData();
  });
  await ui.evaluate("loadMeals()");
  await ui.element("#meal-previous").onclick();
  assert.equal(ui.element("#meal-date").value, "2026-10-23");
  assert.ok(ui.element("#meal-summary").innerHTML.includes("600"));
  assert.equal(ui.element("#meal-error").hidden, false);
  assert.equal(ui.element("#meal-previous").disabled, false);
  assert.equal(ui.element("#meals-panel")["aria-busy"], "false");
  await ui.evaluate("loadMeals()");
  assert.equal(ui.requests.at(-1), "/api/meals");
});

test("Recovery and activity tabs load their functional charts without changing meal dates", async () => {
  const ui = await app(day => dayData(day || undefined));
  await ui.evaluate('loadMeals("2026-10-22")');
  await ui.evaluate('navigate("recovery")');
  assert.ok(ui.element("#recovery-charts").innerHTML.includes("Długość snu"));
  assert.ok(ui.element("#recovery-charts").innerHTML.includes("HRV w nocy"));
  assert.ok(!ui.element("#recovery-charts").innerHTML.includes("Masa ciała"));
  await ui.evaluate('navigate("activity")');
  assert.ok(ui.element("#activity-charts").innerHTML.includes("Kalorie aktywne"));
  assert.ok(ui.element("#activities").innerHTML.includes("Brak aktywności"));
  await ui.evaluate('navigate("dashboard")');
  assert.equal(ui.element("#meal-date").value, "2026-10-22");
  assert.ok(!ui.element("#charts").innerHTML.includes("Długość snu"));
});


test("meal actions render stored text safely and keep zero quantity", () => {
  const html = render.mealList([{id: 1, opis: '<img src=x onerror=alert(1)>', quantity: 0, unit: 'g', kalorie: 0}]);
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img/);
  assert.match(html, /0 g/);
  assert.match(html, /data-meal-edit="1"/);
});
