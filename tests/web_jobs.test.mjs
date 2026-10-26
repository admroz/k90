import test from "node:test";
import assert from "node:assert/strict";
test("app polls persistent timeline through state changes and reload without retries", async () => {
  const {readFile} = await import("node:fs/promises");
  const vm = await import("node:vm");
  const render = await import("../web/render.mjs");
  const source = (await readFile(new URL("../web/app.js", import.meta.url), "utf8"))
    .replace(/^import\s+[\s\S]*?\s+from\s+["'][^"']+["'];\n?/gm, "");
  const elements = new Map(), requests = [];
  let state = "queued";
  const rows = () => [{id:1,role:"user",channel:"web",content:{text:"first"}},
    {id:2,role:"assistant",state,content:{text:"safe failure"}},
    {id:3,role:"user",channel:"telegram",content:{text:"later"}}];
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, {value: "", innerHTML: "", setAttribute() {}, replaceChildren() {}});
    return elements.get(selector);
  };
  const context = vm.createContext({
    ...render, createRequestId: () => "web:unused",
    document: {querySelector: element, querySelectorAll: () => []},
    window: {addEventListener() {}, get localStorage() {throw Error("must not read localStorage");}}, location: {hash: ""}, setInterval() {},
    fetch: async (path, options = {}) => {
      requests.push({path, options});
      return {ok: true, json: async () => path.startsWith("/api/messages") ? rows() : []};
    }
  });
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("session = {timezone: 'UTC'}", context);
  await vm.runInContext("loadChat()", context);
  assert.match(element("#messages").innerHTML, /W kolejce/);
  for (const next of ["running", "failed", "interrupted", "done"]) {
    state = next;
    await vm.runInContext("loadChat()", context);
    const html = element("#messages").innerHTML;
    assert.equal((html.match(/class="message /g)||[]).length, 3);
    assert.ok(html.indexOf("safe failure") < html.indexOf("later"));
    assert.equal(element("#jobs").innerHTML, "");
    assert.doesNotMatch(html, /data-dismiss-job/);
  }
  state = "failed";
  vm.runInContext("history.clear()", context);
  await vm.runInContext("loadChat()", context);
  assert.match(element("#messages").innerHTML, /Błąd odpowiedzi/);
  assert.ok(requests.every(r => !r.options.method));
});
