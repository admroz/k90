import test from "node:test";
import assert from "node:assert/strict";
import {
  markdown,
  chart,
  number,
  formatTimestamp
} from "../web/render.mjs";

test("Markdown escapes HTML and never activates links or images", () => {
  const rendered = markdown('# Title\n<script>alert(1)</script>\n![photo](https://example.com/a.png)\n[x](javascript:alert(1))\n**bold**');
  assert.ok(rendered.includes("<h1>Title</h1>"));
  assert.ok(rendered.includes("&lt;script&gt;"));
  assert.ok(rendered.includes("<strong>bold</strong>"));
  assert.ok(!rendered.includes("<script>"));
  assert.ok(!rendered.includes("<img"));
  assert.ok(!rendered.includes("<a "));
});

test("Markdown renders tables, numbered lists and closed code fences", () => {
  const rendered = markdown('| Test | Result |\n| --- | --- |\n| Glucose | <100> |\n\n1. First\n2. Second\n\n```\n<script>');
  assert.ok(rendered.includes("<table>"));
  assert.ok(rendered.includes("<td>&lt;100&gt;</td>"));
  assert.ok(rendered.includes("<ol>"));
  assert.ok(rendered.endsWith("</code></pre>"));
});

test("Missing measurements are not charted as zero", () => {
  const rendered = chart([{
    data: "2026-09-20",
    value: null
  }, {
    data: "2026-09-21",
    value: ""
  }], "value");
  assert.ok(rendered.includes("Brak pomiarów"));
  assert.ok(!rendered.includes("<svg"));
  assert.equal(number(null), "—");
});

test("One point and constant measurements have finite coordinates", () => {
  for (const rows of [
      [{
        data: "2026-09-20",
        value: 80
      }],
      [{
        data: "2026-09-20",
        value: 80
      }, {
        data: "2026-09-21",
        value: 80
      }]
    ]) {
    const rendered = chart(rows, "value");
    assert.ok(rendered.includes("<svg"));
    assert.ok(!/NaN|Infinity/.test(rendered));
  }
});

test("Long gaps split the line instead of interpolating absent days", () => {
  const rendered = chart([{
    data: "2026-09-20",
    value: 80
  }, {
    data: "2026-09-28",
    value: 82
  }], "value");
  const path = rendered.match(/<path d="([^"]+)"/)[1];
  assert.equal((path.match(/M/g) || []).length, 2);
  assert.ok(!path.includes("L"));
});

test("SQLite UTC timestamps and explicit timezone offsets display consistently", () => {
  assert.equal(formatTimestamp("2026-09-20 14:00:00"), formatTimestamp("2026-09-20T16:00:00+02:00"));
  assert.ok(formatTimestamp("2026-09-20 14:00:00").includes("16:00"));
});
