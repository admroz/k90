import test from 'node:test';
import assert from 'node:assert/strict';
import * as render from '../web/render.mjs';

test('timeline renders failures at their request and escapes untrusted text', () => {
  const rows = [
    {id:1, role:'user', content:{text:'<img src=x onerror=alert(1)>'}},
    {id:2, role:'assistant', state:'failed', content:{text:'<script>private</script>'}},
    {id:3, role:'user', content:{text:'later'}},
    {id:4, role:'assistant', state:'running', content:{text:''}}
  ];
  const html = render.renderTimeline(rows, 'UTC');
  assert.ok(html.indexOf('Błąd odpowiedzi') < html.indexOf('later'));
  assert.match(html, /Agent pracuje/);
  assert.doesNotMatch(html, /<script>|<img|data-dismiss/);
  assert.equal(render.renderTimeline(rows, 'UTC'), html);
});
