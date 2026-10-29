import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogCard } from '../web/catalog.mjs';

test('catalog review escapes source text and offers version-specific approval', () => {
  const card = catalogCard({id:1,version:3,status:'draft',name:'<img onerror="x">',brand:'<script>',basis:'100ml',kcal:64,protein:12,carbs:4.1,fat:0,provenance:'manual'});
  assert.ok(card.includes('&lt;img'));
  assert.ok(!card.includes('<script>'));
  assert.ok(card.includes('wersję 3') && card.includes('100ml') && card.includes('T 0 g'));
  assert.ok(card.includes('data-confirm="1"') && !card.includes('data-portion'));
});

test('confirmed record offers portion instead of another approval', () => {
  const card = catalogCard({id:2,version:4,status:'confirmed',name:'Synthetic',basis:'100g',fat:0});
  assert.ok(card.includes('data-portion="2"') && !card.includes('data-confirm'));
});

test('one-piece size uses the existing native basis and stays optional', () => {
  for (const [basis,unit] of [['100g','g'],['100ml','ml']]) {
    const p = {id:1,version:2,status:'confirmed',name:'Synthetic',basis,piece_size:90};
    assert.ok(catalogCard(p).includes(`Jedna sztuka: 90 ${unit}`));
    assert.ok(catalogCard({...p,piece_size:null}).includes('Rozmiar sztuki: brak'));
    assert.ok(catalogCard({...p,piece_size:'<script>'}).includes('&lt;script&gt;'));
  }
});
