import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { createRequestId } from "../web/request.mjs";
import * as render from "../web/render.mjs";

const requestPattern = /^web:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const httpCrypto = {
  getRandomValues: bytes => webcrypto.getRandomValues(bytes)
};

test("Native UUIDs keep the web request namespace", () => {
  assert.equal(createRequestId({randomUUID: () => "native-uuid"}), "web:native-uuid");
});

test("LAN HTTP creates unique UUIDv4 IDs without randomUUID", () => {
  assert.equal(httpCrypto.randomUUID, undefined);
  const ids = Array.from({length: 100}, () => createRequestId(httpCrypto));
  assert.ok(ids.every(id => requestPattern.test(id)));
  assert.equal(new Set(ids).size, ids.length);
});

test("UUID fallback sets the version and variant for any random bytes", () => {
  for (const value of [0, 255]) {
    const id = createRequestId({getRandomValues: bytes => bytes.fill(value)});
    assert.match(id, requestPattern);
  }
});

test("Chat sends over HTTP and retries the same message with the same ID", async () => {
  // Exercise the real event handlers with the browser capability missing on LAN HTTP.
  const source = (await readFile(new URL("../web/app.js", import.meta.url), "utf8"))
    .replace(/^import\s+[\s\S]*?\s+from\s+["'][^"']+["'];\n?/gm, "");
  const elements = new Map();
  function element(selector) {
    if (!elements.has(selector)) {
      elements.set(selector, {
        value: "", textContent: "", innerHTML: "", disabled: false, hidden: false,
        replaceChildren() {},
        click() { this.onclick?.(); }
      });
    }
    return elements.get(selector);
  }
  const submissions = [];
  let generated = 0;
  vm.runInNewContext(source, {
    ...render, trackSelectionGesture: () => () => false,
    createRequestId() { generated++; return createRequestId(httpCrypto); },
    crypto: httpCrypto,
    isSecureContext: false,
    document: {querySelector: element, querySelectorAll: () => []},
    window: {addEventListener() {}},
    location: {hash: ""},
    setInterval() {},
    async fetch(path, options = {}) {
      if (path === "/api/session") {
        return {ok: false, status: 401, json: async () => ({detail: "Zaloguj się"})};
      }
      if (path === "/api/messages" && options.method === "POST") {
        submissions.push(JSON.parse(options.body));
        if (submissions.length === 1) throw new Error("Connection lost");
        return {ok: true, json: async () => ({state: "queued"})};
      }
      assert.ok(path === "/api/messages" || path === "/api/jobs");
      return {ok: true, json: async () => []};
    }
  });
  // Let the initial unauthenticated session check settle before exercising chat.
  await new Promise(resolve => setImmediate(resolve));
  element("#message").value = "Wiadomość testowa";
  const submit = () => element("#chat-form").onsubmit({preventDefault() {}});
  await submit();
  assert.match(element("#chat-error").textContent, /Możesz ponowić/);
  assert.equal(element("#send-message").disabled, false);
  await submit();
  assert.equal(submissions.length, 2);
  assert.deepEqual(submissions[0], submissions[1]);
  assert.match(submissions[0].request_id, requestPattern);
  assert.equal(submissions[0].text, "Wiadomość testowa");
  assert.equal(generated, 1);
  assert.equal(element("#message").value, "");
  assert.equal(element("#chat-error").textContent, "");

  element("#message").value = "Kolejna wiadomość";
  element("#message").oninput();
  await submit();
  assert.notEqual(submissions[2].request_id, submissions[1].request_id);

});
