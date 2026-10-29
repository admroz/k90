import test from 'node:test';
import assert from 'node:assert/strict';
import {renderProfiling, loadProfiling} from '../web/profiling.mjs';
test('empty, incomplete and escaped report',()=>{
 assert.match(renderProfiling({enabled:false,requests:[]}),/Profilowanie wyłączone.*Brak danych/);
 const html=renderProfiling({enabled:true,requests:[{utc:null,channel:'<img src=x onerror=alert(1)>',job_id:1,outcome:'error',request_id:'<svg>',incomplete:true,model_calls:1,delivery_attempts:2,slowest:['tool'],failure_stages:['tool'],stages:[]}]});
 assert.ok(!html.includes('<img')&&!html.includes('<svg>'));
 assert.match(html,/pomiar niepełny/); assert.match(html,/brak pomiaru/);
});
test('read failure produces visible recovery instruction',async()=>{
 const container={}; await loadProfiling(async()=>{throw Error('private');},container);
 assert.match(container.textContent,/Nie udało się/); assert.ok(!container.textContent.includes('private'));
});
