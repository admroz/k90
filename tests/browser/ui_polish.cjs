// Genuine synthetic backend + shipped assets; no mocked catalog/meal APIs.
const {chromium} = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const origin = process.env.K90_UI_ORIGIN || 'http://127.0.0.1:18998';
assert.equal(new URL(origin).hostname, '127.0.0.1');
const evidence = process.env.BROWSER_EVIDENCE;
assert.ok(evidence, 'BROWSER_EVIDENCE must point outside the repository');
fs.mkdirSync(evidence, {recursive:true});
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_PATH, headless:true,
    args:['--no-sandbox','--disable-background-networking','--disable-component-update',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
  const errors = [], observations = {};
  async function configure(page) {
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  }
  async function shot(page, name) { await page.screenshot({path:path.join(evidence,name+'.png'),fullPage:true}); }
  async function api(page, url, method='GET', body) {
    return page.evaluate(async ({url,method,body}) => {
      const r=await fetch(url,{method,headers:{'Content-Type':'application/json','X-K90-Request':'1'},body:body===undefined?undefined:JSON.stringify(body)});
      return {status:r.status, data:await r.json()};
    },{url,method,body});
  }
  const putResponse = page => page.waitForResponse(r => r.request().method()==='PUT' && r.url().includes('/api/catalog/'));
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    await configure(page);
    await page.goto(origin);
    await page.locator('#password').fill('synthetic-browser-password');
    await page.locator('#login-form button').click();
    await page.locator('#charts .chart').first().waitFor();
    assert.equal(await page.locator('#energy-balance dt').filter({hasText:/^Spoczynkowe$/}).locator('..').locator('dd').innerText(),'~2000 kcal');
    assert.deepEqual(await page.locator('#meals .meal-description strong').allTextContents(),['Synthetic late','Synthetic early','Synthetic untimed']);
    // Independent day navigation: past readings stay actual, not estimated.
    await page.locator('#meal-date').fill('2026-10-28');
    await page.locator('#meal-date').dispatchEvent('change');
    await page.locator('#energy-balance dd').filter({hasText:/^2050 kcal$/}).waitFor();
    await page.locator('#meal-today').click();
    await page.locator('#energy-balance dd').filter({hasText:/^~2000 kcal$/}).waitFor();
    const chart = page.locator('#charts .chart-card').first();
    assert.equal(await chart.locator('[data-chart-label]').count(),3);
    const line=await chart.locator('path[stroke-width="2.5"]').getAttribute('d');
    assert.equal((line.match(/M/g)||[]).length,1); assert.equal((line.match(/L/g)||[]).length,2);
    const xs=[...line.matchAll(/[ML]([\d.]+),/g)].map(m=>Number(m[1]));
    assert.ok(Math.abs((xs[1]-xs[0])/(xs[2]-xs[0])-1/27)<.001);
    observations.sparsePath=line;
    await chart.locator('[data-chart-label]').last().hover();
    assert.equal(await chart.locator('.chart-tooltip').innerText(),'2026-10-29: 80 kg');
    await chart.locator('[data-chart-label]').first().focus();

    assert.equal(await chart.locator('.chart-tooltip').innerText(),'2026-10-02: 83 kg');
    await page.keyboard.press('Escape');
    assert.equal(await chart.locator('.chart-tooltip').innerText(),'');
    await page.keyboard.press('Enter');
    assert.equal(await chart.locator('.chart-tooltip').innerText(),'2026-10-02: 83 kg');
    assert.equal(await chart.locator('a').getAttribute('href'),'https://connect.garmin.com/app/weight');
    await shot(page,'desktop-dashboard');
    // AI remains a prompt-preparation action, including keyboard activation.
    await chart.getByRole('button',{name:'Omów z AI: Masa ciała'}).focus();
    await page.keyboard.press('Enter');
    await page.locator('#chat-view').waitFor({state:'visible'});
    assert.match(await page.locator('#message').inputValue(),/Przeanalizuj masa ciała.*2026-09-30–2026-10-29/);
    await page.locator('[data-view="recovery"]').click();
    await page.locator('#recovery-charts a').waitFor();
    assert.equal(await page.locator('#recovery-charts a').getAttribute('href'),'https://connect.garmin.com/app/sleep/2026-10-28');
    assert.ok(await page.getByLabel('Brak zweryfikowanego linku Garmin Connect: HRV w nocy').isVisible());
    observations.garmin={weight:'owner-confirmed',sleepDate:'2026-10-28',otherCategories:'unverified, no links guessed'};
    // Legacy NULL owner: explicit preview, then exact version-bound edit.
    await page.locator('[data-view="catalog"]').click();
    const previewResponse=page.waitForResponse(r=>r.url().endsWith('/preview'));
    await page.locator('[data-edit]').click();
    assert.equal((await previewResponse).status(),200);
    const field=name=>page.locator(`#catalog-editor [name="${name}"]`);
    await field('piece_size').fill('100');
    const edited=putResponse(page); await page.locator('#catalog-editor button[type="submit"]').click();
    assert.equal((await edited).status(),200);
    await page.locator('[data-confirm]').waitFor();
    let product=(await api(page,'/api/catalog')).data[0];
    assert.equal(product.piece_size,100); assert.equal(product.version,3); assert.equal(product.status,'draft');
    await page.locator('[data-confirm]').click(); await page.locator('[data-portion]').waitFor();
    product=(await api(page,'/api/catalog')).data[0];
    assert.equal(product.version,4); assert.equal(product.status,'confirmed');
    await shot(page,'desktop-catalog');
    await page.locator('[data-portion]').click();
    await page.locator('#catalog-portion-unit').selectOption('szt'); await page.locator('#catalog-quantity').fill('0.5');
    await page.locator('#catalog-log').click(); await page.getByText('Zapisano porcję: 32 kcal',{exact:true}).waitFor();
    // Actual API validation error preserves input and both close actions work.
    await page.locator('[data-edit]').click(); await field('piece_size').fill('0');
    let rejected=putResponse(page); await page.locator('#catalog-editor button[type="submit"]').click();
    assert.equal((await rejected).status(),409);
    assert.equal(await field('piece_size').inputValue(),'0');
    await shot(page,'invalid-editor');
    assert.equal(await page.evaluate(()=>document.querySelector('#catalog-editor').contains(document.activeElement)),true);
    await page.keyboard.press('Escape'); assert.equal(await page.locator('#catalog-editor').isHidden(),true);
    assert.equal(await page.evaluate(()=>document.activeElement.hasAttribute('data-edit')),true,'closing restores focus to the edit trigger');
    await page.locator('[data-edit]').click(); await field('piece_size').fill('0');
    rejected=putResponse(page); await page.locator('#catalog-editor button[type="submit"]').click();
    assert.equal((await rejected).status(),409);
    await page.locator('#catalog-cancel').click(); assert.equal(await page.locator('#catalog-editor').isHidden(),true);
    // Genuine concurrent edit remains rejected: no silent refresh/retry/overwrite.
    await page.locator('[data-edit]').click(); await field('piece_size').fill('120');
    const concurrent=await api(page,`/api/catalog/${product.id}`,'PUT',{version:4,product:{piece_size:110}});
    assert.equal(concurrent.status,200);
    rejected=putResponse(page); await page.locator('#catalog-editor button[type="submit"]').click();
    const stale=await rejected; assert.equal(stale.status(),409);
    assert.equal((await stale.json()).detail,'owner or version mismatch; preview required');
    assert.equal(await field('piece_size').inputValue(),'120');
    assert.equal((await api(page,'/api/catalog')).data[0].piece_size,110);
    await shot(page,'stale-editor');
    await page.locator('#catalog-cancel').click();
    await page.locator('#catalog-search-form button').click();
    await page.getByText(/wersja 5/).waitFor();
    // Small meal action icons still perform real revision-aware writes/deletes.
    await page.locator('[data-view="dashboard"]').click();
    await page.getByRole('button',{name:'Edytuj posiłek: Synthetic late',exact:true}).click();
    await page.locator('#meal-edit-form [name="description"]').fill('Synthetic edited');
    const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().includes('/api/meals/'));
    await page.locator('#meal-edit-form button[type="submit"]').click(); assert.equal((await saved).status(),200);
    await page.getByRole('button',{name:'Usuń posiłek: Synthetic edited',exact:true}).waitFor();
    const meals=(await api(page,'/api/meals')).data.meals;
    const meal=meals.find(m=>m.opis==='Synthetic edited'); assert.ok(meal);
    page.once('dialog',d=>d.dismiss());
    await page.getByRole('button',{name:'Usuń posiłek: Synthetic edited',exact:true}).click();
    assert.ok((await api(page,'/api/meals')).data.meals.some(m=>m.id===meal.id));
    page.once('dialog',d=>d.accept());
    const deleted=page.waitForResponse(r=>r.request().method()==='DELETE'&&r.url().endsWith('/'+meal.id));
    await page.getByRole('button',{name:'Usuń posiłek: Synthetic edited',exact:true}).click();
    assert.equal((await deleted).status(),200);
    assert.ok(!(await api(page,'/api/meals')).data.meals.some(m=>m.id===meal.id));
    // Real Chromium touch emulation, not a claim about physical devices/WebKit.
    const mobileContext=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
    await mobileContext.addCookies(await page.context().cookies());
    const mobile=await mobileContext.newPage(); await configure(mobile);
    await mobile.goto(origin+'/#dashboard'); await mobile.locator('#charts .chart').first().waitFor();
    const mobileChart=mobile.locator('#charts .chart-card').first();
    await mobileChart.locator('[data-chart-label]').last().tap();
    assert.equal(await mobileChart.locator('.chart-tooltip').innerText(),'2026-10-29: 80 kg');
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await shot(mobile,'mobile-touch-dashboard');
    await mobile.locator('[data-view="catalog"]').click(); await mobile.locator('[data-edit]').click();
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    const closeBox=await mobile.locator('#catalog-cancel').boundingBox(); assert.ok(closeBox.width>=40&&closeBox.height>=40);
    await shot(mobile,'mobile-catalog-editor');
    await mobile.locator('#catalog-cancel').tap(); assert.equal(await mobile.locator('#catalog-editor').isHidden(),true);
    assert.deepEqual(errors,[]);
    observations.result='PASS genuine API/SQLite legacy preview/edit/confirm/portion; invalid+stale409 input preservation; Escape+close; meal edit/delete cancel+confirm; previous-week energy; real spaced SVG hover/keyboard/touch; dynamic verified links; keyboard AI intent; 1280 desktop and 390 touch layout; no uncaught JS errors';
    fs.writeFileSync(path.join(evidence,'observations.json'),JSON.stringify(observations,null,2));
    console.log(observations.result);
    console.log('Chromium '+browser.version());
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1);});
