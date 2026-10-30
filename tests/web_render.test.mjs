import test from "node:test";
import assert from "node:assert/strict";
import {
  markdown,
  chart,
  number,
  formatTimestamp,
  mealList,
  mealSummary,
  mealDayLabel,
  energyBalance
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

test("Long gaps connect only actual points without adding absent days", () => {
  const rendered = chart([{
    data: "2026-09-20",
    value: 80
  }, {
    data: "2026-09-28",
    value: 82
  }], "value");
  const path = rendered.match(/<path d="([^"]+)"/)[1];
  assert.equal((path.match(/M/g) || []).length, 1);
  assert.equal((path.match(/L/g) || []).length, 1);
});

test("SQLite UTC timestamps and explicit timezone offsets display consistently", () => {
  assert.equal(formatTimestamp("2026-09-20 14:00:00"), formatTimestamp("2026-09-20T16:00:00+02:00"));
  assert.ok(formatTimestamp("2026-09-20 14:00:00").includes("16:00"));
});

test("Daily meal list includes every meal and escapes descriptions", () => {
  const meals = Array.from({length: 6}, (_, i) => ({
    opis: i === 0 ? '<script>test</script>' : `Posiłek ${i}`,
    czas: i === 0 ? null : '12:30', kalorie: i === 0 ? 0 : 200,
    bialko_g: null, weglowodany_g: 20, tluszcze_g: 10
  }));
  const html = mealList(meals);
  assert.equal((html.match(/class="meal-row"/g) || []).length, 6);
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('0 kcal'));
  assert.ok(html.includes('Białko — g'));
  assert.ok(html.includes('Godzina niepodana'));
  assert.ok(mealList([]).includes('Brak zapisanych posiłków w tym dniu'));
});

test("Meal summary flags partial sums and preserves unknown and zero values", () => {
  const html = mealSummary(
    {kalorie: 500, bialko_g: 20, weglowodany_g: null, tluszcze_g: 0},
    {kalorie: 0, bialko_g: 1, weglowodany_g: 2, tluszcze_g: 0}
  );
  assert.ok(html.includes('20 *'));
  assert.ok(html.includes('>— <small>g'));
  assert.ok(html.includes('>0 <small>g'));
  assert.ok(!html.includes('null') && !html.includes('NaN'));
});

test("Meal date labels use calendar days across year and daylight-saving boundaries", () => {
  assert.ok(mealDayLabel('2026-01-01', '2026-01-01').startsWith('Dzisiaj'));
  assert.ok(mealDayLabel('2025-12-31', '2026-01-01').startsWith('Wczoraj'));
  assert.ok(mealDayLabel('2026-03-29', '2026-03-30').includes('29 marca 2026'));
  assert.ok(!mealDayLabel('2024-02-29', '2026-01-01').includes('Wczoraj'));
});

test("Energy balance preserves positive, negative, zero and unknown values", () => {
  const data = {meals: [{}], missing_values: {kalorie: 0}, energy: {resting_kcal: 1900, active_kcal: 0, burned_kcal: 1900, balance_kcal: -200, day_in_progress: true}};
  assert.ok(energyBalance(data).includes('-200'));
  assert.ok(energyBalance(data).includes('0 kcal'));
  assert.ok(energyBalance(data).includes('Dzień jeszcze trwa'));
  data.energy.balance_kcal = 200;
  assert.ok(energyBalance(data).includes('+200'));
  data.energy.balance_kcal = 0;
  assert.ok(energyBalance(data).includes('>0 <small>kcal'));
  data.energy = {};
  assert.ok(energyBalance(data).includes('Brak kompletnych danych Garmin'));
  assert.ok(energyBalance(data).includes('>— <small>kcal'));
});
