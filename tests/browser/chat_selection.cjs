// Optional real-browser regression: PLAYWRIGHT_CORE, CHROMIUM_PATH and BROWSER_EVIDENCE
// point to existing installations and an evidence directory. No downloads required.
const {chromium} = require(process.env.PLAYWRIGHT_CORE);
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../web');
const evidence = process.env.BROWSER_EVIDENCE;
fs.mkdirSync(evidence, {recursive:true});
const row = (id, text, state='done') => ({id, role:'assistant', state, timestamp:'2026-10-29T12:00:00Z', content:{text}});
let rows = [row(1, 'Synthetic selection target & evidence **bold**.'), row(2, 'Waiting', 'queued')];
let polls = 0, fail = false;
const server = http.createServer((req,res) => {
 const url = new URL(req.url, 'http://localhost');
 if (url.pathname.startsWith('/api/')) {
  res.setHeader('Content-Type','application/json');
  let data = [];
  if(url.pathname === '/api/session') data={timezone:'UTC',local:true,telegram_enabled:false,sync_enabled:false};
  if(url.pathname === '/api/sync/garmin') data=null;
  if(url.pathname === '/api/messages') {
   polls++;
   if(fail){res.statusCode=503;data={detail:'Synthetic polling failure'};}
   else { const before=Number(url.searchParams.get('before'))||Infinity; data=rows.filter(r=>r.id<before).slice(-50); }
  }
  res.end(JSON.stringify(data));return;
 }
 const name=url.pathname==='/'?'index.html':url.pathname.replace(/^\/static\//,'');
 if(!/^[a-zA-Z0-9_.-]+$/.test(name)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',name.endsWith('.html')?'text/html':/\.(js|mjs)$/.test(name)?'text/javascript':name.endsWith('.css')?'text/css':'image/svg+xml');
 try{res.end(fs.readFileSync(path.join(root,name)));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox','--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 let page;
 try {
  page=await browser.newPage({viewport:{width:1200,height:850}});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto(`http://127.0.0.1:${server.address().port}/#chat`);
  await page.locator('[data-message-id="1"] .message-body').waitFor();
  const target=page.locator('[data-message-id="1"] .message-body p');
  const bounds=await target.evaluate(el=>{const r=document.createRange();r.setStart(el.firstChild,0);r.setEnd(el.firstChild,19);const b=r.getBoundingClientRect();window.originalText=el.firstChild;return {x:b.x,y:b.y,w:b.width,h:b.height};});
  await page.mouse.move(bounds.x+1,bounds.y+bounds.h/2);
  await page.mouse.down();await page.mouse.move(bounds.x+bounds.w,bounds.y+bounds.h/2,{steps:15});await page.mouse.up();
  const selected=await page.evaluate(()=>getSelection().toString());assert.ok(selected.length>5,'real mouse drag selected text');
  await page.screenshot({path:path.join(evidence,'before-poll.png')});
  const poll=async()=>{const n=polls;await page.waitForFunction(()=>true);while(polls<=n)await page.waitForTimeout(100);await page.waitForTimeout(100);};
  const check=async(label)=>{const result=await page.evaluate(()=>({text:getSelection().toString(),same:document.querySelector('[data-message-id="1"] .message-body p').firstChild===window.originalText}));console.log(label,JSON.stringify({selected,...result}));fs.appendFileSync(path.join(evidence,'observations.jsonl'),JSON.stringify({label,selected,...result})+'\n');await page.screenshot({path:path.join(evidence,label+'.png')});assert.equal(result.text,selected,label+' preserves selected text');assert.equal(result.same,true,label+' retains text node');};
  await poll();await check('unchanged-poll');
  await poll();await check('repeated-poll');
  rows.push(row(3,'Unrelated appended response'));await poll();await check('append');
  for(const state of ['running','done','failed']){rows[1]=row(2,'Unrelated status & detail',state);await poll();await check(state);}
  fail=true;await poll();await check('http-error');fail=false;
  await page.evaluate(()=>getSelection().removeAllRanges());
  rows.push(...Array.from({length:70},(_,i)=>row(i+4,'History synthetic '+i+'\n\n'+('long content '.repeat(20)))));
  await poll();
  assert.equal(await page.locator('[data-message-id]').count(),73);
  const gap=()=>page.locator('#messages').evaluate(e=>e.scrollHeight-e.scrollTop-e.clientHeight);
  assert.ok(await gap()<3,'idle follows bottom');
  const boxBounds=await page.locator('#messages').boundingBox();
  await page.mouse.move(boxBounds.x+boxBounds.width-20,boxBounds.y+boxBounds.height-30);
  await page.mouse.down();
  const gestureTop=await page.locator('#messages').evaluate(e=>e.scrollTop);
  rows.push(row(74,'Append during gesture\n\n'+('new text '.repeat(80))));
  await poll();
  assert.equal(await page.locator('#messages').evaluate(e=>e.scrollTop),gestureTop,'active pointer gesture prevents bottom jump');
  await page.mouse.up();
  await page.locator('#messages').evaluate(e=>e.scrollTo({top:300,behavior:'instant'}));const top=await page.locator('#messages').evaluate(e=>e.scrollTop);
  rows.push(row(75,'Append while reading'));await poll();assert.equal(await page.locator('#messages').evaluate(e=>e.scrollTop),top,'reading position preserved');
  await page.reload();await page.locator('[data-message-id="75"]').waitFor();
  await page.locator('#older-messages').click();await page.locator('[data-message-id="1"]').waitFor();
  rows[1]=row(2,'Old paginated completion');await poll();await page.getByText('Old paginated completion',{exact:true}).waitFor();
  console.log('PASS Chromium selection, append/status/error, idle/reading scroll, reload/history refresh');
 } finally {if(page)await page.screenshot({path:path.join(evidence,'final.png')});await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
