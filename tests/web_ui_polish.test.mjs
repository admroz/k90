import test from 'node:test';
import assert from 'node:assert/strict';
import { energyBalance, mealList, chart, chartActions } from '../web/render.mjs';
import { catalogCard } from '../web/catalog.mjs';

test('today resting estimate adds only a tilde, never to missing or past readings', () => {
  const data = {meals:[], totals:{}, missing_values:{}, energy:{resting_kcal:2000, resting_estimated:true}};
  assert.match(energyBalance(data), /Spoczynkowe<\/dt><dd>~2000 kcal/);
  data.energy.resting_kcal = null;
  assert.doesNotMatch(energyBalance(data), /~—/);
  data.energy = {resting_kcal:2050, resting_estimated:false};
  assert.match(energyBalance(data), /Spoczynkowe<\/dt><dd>2050 kcal/);
});

test('meal actions are compact labelled icons with escaped meal context', () => {
  const html = mealList([{id:7, opis:'<Fixture>'}]);
  assert.match(html, /class="icon-button"[^>]*data-meal-edit="7"[^>]*aria-label="Edytuj posiłek: &lt;Fixture&gt;"/);
  assert.match(html, /data-meal-delete="7"[^>]*aria-label="Usuń posiłek: &lt;Fixture&gt;"/);
  assert.match(html, /<svg[^>]*aria-hidden="true"/);
  assert.doesNotMatch(html, />Edytuj<|>Usuń</);
});

test('catalog rows use compact accessible actions without hiding version/nutrition', () => {
  const card = catalogCard({id:1,version:3,status:'draft',name:'Synthetic',basis:'100g',kcal:64,protein:12,carbs:4,fat:0,source_event_id:2});
  assert.match(card, /class="catalog-row"/);
  for (const label of ['Edytuj produkt: Synthetic','Pokaż etykietę: Synthetic','Sprawdziłem wartości — zatwierdź wersję 3']) assert.ok(card.includes(`aria-label="${label}"`));
  assert.ok(card.includes('wersja 3') && card.includes('64 kcal') && card.includes('T 0 g'));
});

test('chart connects sparse actual measurements using elapsed time, without imputation', () => {
  const html = chart([{data:'2026-10-01',value:1},{data:'2026-10-02',value:2},{data:'2026-10-08',value:null},{data:'2026-10-11',value:3}], 'value');
  const path = html.match(/<path d="([^"]+)"/)[1];
  assert.equal((path.match(/M/g)||[]).length,1);
  assert.equal((path.match(/L/g)||[]).length,2);
  const xs = [...path.matchAll(/[ML]([\d.]+),/g)].map(m=>Number(m[1]));
  assert.ok(Math.abs((xs[1]-xs[0])/(xs[2]-xs[0]) - 0.1) < .001);
  assert.doesNotMatch(html, /2026-10-08/);
});

test('every measurement has an accessible date/value/unit target even above 100 points', () => {
  const rows=Array.from({length:101},(_,i)=>({data:new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10),value:i}));
  const html=chart(rows,'value','#9fc7a3','kg');
  assert.equal((html.match(/data-chart-label=/g)||[]).length,101);
  assert.match(html,/data-chart-label="2026-01-01: 0 kg"/);
  assert.match(html,/tabindex="0"/);
  assert.match(html,/class="chart-tooltip"/);
  assert.ok(chart([{data:'2026-10-29',value:0}], 'value','#9fc7a3','<kg>').includes('0 &lt;kg&gt;'));
});

test('chart actions keep AI intent compact and link only owner-verified Garmin categories', () => {
  const weight=chartActions('Masa ciała','waga_kg','2026-10-28');
  assert.match(weight,/aria-label="Omów z AI: Masa ciała"/);
  assert.match(weight,/href="https:\/\/connect.garmin.com\/app\/weight"/);
  assert.doesNotMatch(weight,/>Omów/);
  assert.match(chartActions('Sen','hours','2026-10-28'),/href="https:\/\/connect.garmin.com\/app\/sleep\/2026-10-28"/);
  assert.match(chartActions('HRV','hrv_noc','2026-10-29'),/Brak zweryfikowanego linku Garmin Connect/);
  assert.doesNotMatch(chartActions('HRV','hrv_noc','2026-10-29'),/href=/);
  assert.doesNotMatch(chartActions('Sen','hours','<invalid>'),/href=/);
  assert.doesNotMatch(chartActions('Glukoza','glukoza','2026-10-29'),/Garmin/);
});
