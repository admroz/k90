import test from 'node:test';
import assert from 'node:assert/strict';
import { energyBalance } from '../web/render.mjs';

test('today resting estimate adds only a tilde, never to missing or past readings', () => {
  const data = {meals:[], totals:{}, missing_values:{}, energy:{resting_kcal:2000, resting_estimated:true}};
  assert.match(energyBalance(data), /Spoczynkowe<\/dt><dd>~2000 kcal/);
  data.energy.resting_kcal = null;
  assert.doesNotMatch(energyBalance(data), /~—/);
  data.energy = {resting_kcal:2050, resting_estimated:false};
  assert.match(energyBalance(data), /Spoczynkowe<\/dt><dd>2050 kcal/);
});
