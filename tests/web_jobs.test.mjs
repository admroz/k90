import test from "node:test";
import assert from "node:assert/strict";
import {createJobDismissals, renderJobs} from "../web/render.mjs";

const jobs = ["failed", "interrupted", "queued", "running", "done"].map((state, i) =>
  ({request_id: "web:" + i, state, channel: "telegram", created_at: "2026-10-26", payload: {text: "synthetic"}}));

test("only explicitly dismissed terminal failures disappear, including after reload", () => {
  const store = new Map();
  const storage = {getItem: k => store.get(k), setItem: (k,v) => store.set(k,v)};
  const dismissed = createJobDismissals(storage);
  assert.match(renderJobs(jobs, dismissed), /Błąd odpowiedzi/);
  dismissed.dismiss(jobs[0]);
  dismissed.dismiss(jobs[2]);
  const html = renderJobs(jobs, createJobDismissals(storage));
  assert.doesNotMatch(html, /Błąd odpowiedzi/);
  assert.match(html, /Przerwana odpowiedź/);
  assert.match(html, /W kolejce/);
  assert.match(html, /Agent pracuje/);
  assert.doesNotMatch(html, /data-dismiss-job="web:4"/);
  assert.match(html, /telegram/);
  assert.match(html, /tej przeglądarce/);
  assert.doesNotMatch([...store.values()].join(""), /synthetic|telegram|failed/);
  assert.match(renderJobs([{...jobs[0], request_id: "web:new"}], dismissed), /Błąd odpowiedzi/);
});

test("bounded storage and unavailable or malformed storage preserve visible failures", () => {
  const store = new Map();
  const storage = {getItem: k => store.get(k), setItem: (k,v) => store.set(k,v)};
  const dismissed = createJobDismissals(storage);
  for (let i=0; i<600; i++) dismissed.dismiss({...jobs[0], request_id: "web:" + i});
  assert.ok(JSON.parse([...store.values()][0]).length <= 500);
  for (const storage of [undefined, {getItem() {throw Error();}, setItem() {throw Error();}},
                        {getItem: () => '{"bad":true}', setItem() {}}]) {
    assert.match(renderJobs(jobs, createJobDismissals(storage)), /Błąd odpowiedzi/);
  }
});

test("app dismissal listener hides a card without posting or retrying", async () => {
  const {readFile} = await import("node:fs/promises");
  const vm = await import("node:vm");
  const render = await import("../web/render.mjs");
  const source = (await readFile(new URL("../web/app.js", import.meta.url), "utf8"))
    .replace(/^import\s+[\s\S]*?\s+from\s+["'][^"']+["'];\n?/gm, "");
  const elements = new Map(), requests = [];
  let click;
  const button = {dataset: {dismissJob: "web:0"}, addEventListener(name, fn) {assert.equal(name, "click"); click = fn;}};
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, {value: "", innerHTML: "", setAttribute() {}, replaceChildren() {}});
    return elements.get(selector);
  };
  const context = vm.createContext({
    ...render, createRequestId: () => "web:unused",
    document: {querySelector: element, querySelectorAll: s => s === "[data-dismiss-job]" ? [button] : []},
    window: {addEventListener() {}}, location: {hash: ""}, setInterval() {},
    fetch: async (path, options = {}) => {
      requests.push({path, options});
      return {ok: true, json: async () => path === "/api/jobs" ? jobs.slice(0,1) : []};
    }
  });
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("session = {timezone: 'UTC'}", context);
  await vm.runInContext("loadChat()", context);
  assert.match(element("#jobs").innerHTML, /Błąd odpowiedzi/);
  const count = requests.length;
  click();
  assert.equal(element("#jobs").innerHTML, "");
  assert.equal(requests.length, count);
  assert.ok(requests.every(r => !r.options.method));
});
