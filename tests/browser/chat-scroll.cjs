// Real layout regression. Install playwright@1.56.1 in scratch; see evidence notes.
const { chromium } = require(process.env.K90_PLAYWRIGHT || 'playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../web');
const evidence = process.env.K90_SCROLL_EVIDENCE;
const rows = Array.from({length:150}, (_, i) => ({id:i+1, role:i%2?'assistant':'user', channel:'web', timestamp:'2026-01-01 12:00:00', state:'completed', content:{text:`Synthetic message ${i+1}. ` + 'Long synthetic history for browser layout. '.repeat(12)}}));
let posts = [], gets = [];
const server = http.createServer((req,res) => {
  const url = new URL(req.url, 'http://localhost');
  const json = data => {res.setHeader('Content-Type','application/json'); res.end(JSON.stringify(data));};
  if (url.pathname === '/api/messages') {
    if (req.method === 'POST') {
      let body=''; req.on('data', c=>body+=c); req.on('end',()=>{
        const data=JSON.parse(body); posts.push(data);
        rows.push({...rows[0],id:rows.length+1,content:{text:data.text,has_image:!!data.image}});
        rows.push({...rows[1],id:rows.length+1,state:'queued',content:{text:'Synthetic pending'}});
        json({id:1});
      }); return;
    }
    gets.push(url.search); return json(rows.filter(r=>!url.searchParams.has('before') || r.id < +url.searchParams.get('before')).slice(-50));
  }
  if (url.pathname === '/api/session') return json({timezone:'UTC',telegram_enabled:false,telegram:{},local:false});
  if (url.pathname === '/api/tables' || url.pathname === '/api/documents') return json([]);
  if (url.pathname === '/api/sync/garmin') return json({});
  const file=path.join(root,url.pathname==='/'?'index.html':url.pathname.replace(/^\/static\//, ''));
  if (!file.startsWith(root + '/')) {res.writeHead(404);return res.end();}
  try {res.setHeader('Content-Type',file.endsWith('.js')||file.endsWith('.mjs')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));} catch {res.writeHead(404);res.end();}
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const origin=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true, executablePath:process.env.K90_CHROMIUM});
  const results=[];
  try {
    for (const viewport of [{width:1280,height:900},{width:390,height:844}]) {
      rows.splice(150); posts=[]; gets=[];
      const page=await browser.newPage({viewport});
      page.on('pageerror', e=>console.error('Browser error:',e.message));
      page.setDefaultTimeout(10000);
      await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
      await page.goto(origin+'/#chat');
      await page.waitForFunction(()=>document.querySelectorAll('.message').length===50);
      await page.evaluate(()=>{const b=document.querySelector('#messages');b.scrollTo({top:b.scrollHeight,behavior:'instant'});});
      await page.locator('#message').fill('Synthetic Enter submission');
      await page.evaluate(()=>{
        const b=document.querySelector('#messages');window.samples=[];
        let n=0;const sample=()=>{window.samples.push({frame:n,top:b.scrollTop,height:b.scrollHeight,client:b.clientHeight});if(++n<100)requestAnimationFrame(sample);};requestAnimationFrame(sample);
      });
      await page.locator('#message').press('Enter');
      await page.waitForFunction(()=>window.samples.length===100);
      const samples=await page.evaluate(()=>window.samples);
      const result={viewport,samples,posts:[...posts]};results.push(result);
      if(evidence){fs.mkdirSync(evidence,{recursive:true});fs.writeFileSync(path.join(evidence,`enter-${viewport.width}.json`),JSON.stringify(result,null,2));await page.screenshot({path:path.join(evidence,`enter-${viewport.width}.png`)});}
      assert.equal(posts.length,1,'Enter submits exactly once');
      assert(samples.every(s=>s.height-s.client-s.top < 80) && samples.every(s=>s.top >= samples[0].top-2),`visible Enter jump: initial ${samples[0].top}, minimum ${Math.min(...samples.map(s=>s.top))}`);
      assert(samples.at(-1).height-samples.at(-1).client-samples.at(-1).top<2,'follows bottom');
      // Keep an actual visible message anchored through polling and older pages.
      await page.evaluate(()=>{const b=document.querySelector('#messages');b.scrollTo({top:900,behavior:'instant'});});
      const anchor=()=>page.evaluate(()=>{const b=document.querySelector('#messages'),top=b.getBoundingClientRect().top;const el=[...b.children].find(e=>e.getBoundingClientRect().bottom>top+30);return {text:el.querySelector('.message-body').textContent,y:el.getBoundingClientRect().top};});
      const a=await anchor();
      rows.at(-1).state='running';
      const count=gets.length;await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Agent pracuje'));
      assert(gets.length>count,'real interval polled');
      assert.deepEqual(await anchor(),a,'poll preserves reading anchor');
      rows.at(-1).state='completed';rows.at(-1).content.text='Synthetic answer. '.repeat(150);
      await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Synthetic answer.'));
      assert.deepEqual(await anchor(),a,'answer preserves reading anchor');
      const beforeCount=await page.locator('.message').count();
      await page.locator('#older-messages').click();
      await page.waitForFunction(n=>document.querySelectorAll('.message').length>n,beforeCount);
      assert.deepEqual(await anchor(),a,'prepend preserves visible anchor');
      const messageCount=await page.locator('.message').count();
      await page.waitForTimeout(2700); // Observe an unchanged real polling cycle, never a source fix.
      assert.equal(await page.locator('.message').count(),messageCount,'poll retains loaded pages without duplicates');
      assert.deepEqual(await anchor(),a);
      await page.locator('#message').fill('Synthetic draft');await page.locator('#message').press('Shift+Enter');
      assert.equal(posts.length,1);
      await page.locator('#message').dispatchEvent('keydown',{key:'Enter',isComposing:true});assert.equal(posts.length,1);
      await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.message').length===50);
      assert.equal(posts.length,1,'reload does not retry');
      await page.close();
    }
    console.log('PASS real Chromium desktop + narrow: Enter, anchor, polling, pending/running/answer, pagination, reload, keyboard');
  } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
