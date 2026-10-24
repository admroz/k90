import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";
import * as render from "../web/render.mjs";

async function app({post, status}) {
  const source = (await readFile(new URL("../web/app.js", import.meta.url), "utf8"))
    .replace(/^import\s+[\s\S]*?\s+from\s+["'][^"']+["'];\n?/gm, "");
  const elements = new Map(), requests = [];
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, {
      value: "", textContent: "", innerHTML: "", hidden: false, disabled: false,
      setAttribute() {}, replaceChildren() {}
    });
    return elements.get(selector);
  };
  let ids = 0;
  const context = vm.createContext({
    ...render, createRequestId: () => `web:sync-${++ids}`,
    document: {querySelector: element, querySelectorAll: () => []},
    window: {addEventListener() {}}, location: {hash: ""}, setInterval() {},
    async fetch(path, options = {}) {
      requests.push({path, options});
      if (path === "/api/session") return {ok: false, status: 401, json: async () => ({detail: "Zaloguj się"})};
      let data;
      if (path === "/api/sync/garmin") data = options.method === "POST" ? await post(JSON.parse(options.body)) : await status();
      else if (path.startsWith("/api/meals")) {
        const date = new URL(path, "http://test").searchParams.get("date") || "2026-10-24";
        data = {date, today: "2026-10-24", meals: [], totals: {}, missing_values: {}, previous_date: "2026-10-23", next_date: null};
      } else {
        assert.ok(path.startsWith("/api/dashboard"), "Sync must not submit a chat message");
        data = {from: "2026-10-01", to: "2026-10-24", latest: {}, waga: [], cisnienie: [], glukoza: [], sync: []};
      }
      return {ok: true, json: async () => data};
    }
  });
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("session = {sync_enabled: true}", context);
  return {element, requests, evaluate: source => vm.runInContext(source, context)};
}

test("Garmin button uses the data-only endpoint and refreshes the selected meal day on completion", async () => {
  let state = "queued", posts = 0;
  const ui = await app({post: body => {posts++; return {request_id: body.request_id, state};}, status: () => ({request_id: "web:sync-1", state, response: "Dane pobrane"})});
  await ui.evaluate('loadMeals("2026-10-22")');
  await ui.element("#sync-garmin").onclick();
  await ui.element("#sync-data").onclick();
  assert.equal(posts, 1);
  assert.equal(ui.element("#sync-garmin").disabled, true);
  assert.equal(ui.element("#sync-data").disabled, true);
  state = "done";
  await ui.evaluate("checkGarminSync()");
  assert.equal(ui.element("#sync-garmin").disabled, false);
  assert.ok(ui.requests.some(request => request.path === "/api/meals?date=2026-10-22"));
  assert.equal(ui.element("#meal-date").value, "2026-10-22");
  assert.ok(!ui.requests.some(request => request.path === "/api/messages"));
});

test("Retry after an uncertain POST reuses the same sync request ID", async () => {
  const bodies = [];
  const ui = await app({
    post: body => {bodies.push(body); if (bodies.length === 1) throw new Error("Connection lost"); return {state: "queued"};},
    status: () => ({state: "running", calories_through: "2024-06-30"})
  });
  await ui.element("#sync-data").onclick();
  assert.equal(ui.element("#sync-data").disabled, false);
  await ui.element("#sync-data").onclick();
  assert.deepEqual(bodies[0], bodies[1]);
  assert.ok(ui.element("#garmin-sync-status").textContent.includes("2024-06-30"));
});

test("A stale status response cannot clear a newly started sync", async () => {
  let resolveOld, fresh = false;
  const ui = await app({post: () => ({state: "queued"}), status: () => fresh ? {state: "queued"} : new Promise(resolve => {resolveOld = resolve;})});
  const old = ui.evaluate("checkGarminSync(false)");
  await ui.element("#sync-garmin").onclick();
  resolveOld({state: "done", response: "Old result"});
  await old;
  assert.equal(ui.element("#sync-garmin").disabled, true);
  fresh = true;
  await ui.evaluate("checkGarminSync()");
  assert.ok(ui.element("#garmin-sync-status").textContent.includes("oczekiwanie"));
});
