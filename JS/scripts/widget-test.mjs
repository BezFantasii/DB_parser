import assert from 'node:assert/strict';
import {mkdir,writeFile,rm,readFile} from 'node:fs/promises';
import path from 'node:path';
import {launch} from './browser.mjs';
import {fixtureNetwork} from './fixture-network.mjs';
import {backendFixture} from './backend-fixture.mjs';
const root=path.resolve(import.meta.dirname,'..');
const profile=path.join(root,`.test-profile-widget-${Date.now()}`);
await mkdir(path.join(root,'test-results'),{recursive:true});
const checks=[],requests=[],errors=[];
let context,worker,id;
let backendAPI;
let blocked=false,slow=false,wbDenied=false,sessionOnly=false,wbSessionOnly=false;
const pass=name=>{checks.push(name);console.log(`PASS ${name}`);};
const html=(site,query)=>`<!doctype html><html lang="ru"><head><title>${blocked&&site==='ozon'?'Captcha':'Поиск'}</title></head><body><h1>${query.replace(/[<>&]/g,'')}</h1>${blocked&&site==='ozon'?'Подтвердите, что вы не робот':Array.from({length:7},(_,i)=>site==='wb'?`<article class="product-card" data-nm-id="${100+i}"><a class="product-card__link" href="/catalog/${100+i}/detail.aspx"><img alt="Наушники WB ${i}"></a><span class="product-card__name">Наушники WB ${i}</span><del>9 999 ₽</del><span class="price__lower-price">${1299+i} ₽</span><span>С кошельком WB</span></article>`:`<div data-index="${i}"><a href="/product/headphones-${200+i}/"><img alt="Наушники Ozon ${i}"></a><div data-widget="tilePrice"><span>${2399+i} ₽</span><del>8 999 ₽</del></div><a href="/product/headphones-${200+i}/"><span class="tsBody500Medium">Наушники Ozon ${i}</span></a><span>с Ozon Картой</span></div>`).join('')}</body></html>`;
const network=await fixtureNetwork(async(request,response)=>{
  const url=new URL(request.url,`https://${request.headers.host}`);
  if(url.hostname==='search.wb.ru'){
    const query=url.searchParams.get('query')||'';requests.push({site:'wb',query,origin:request.headers.origin});
    if(wbSessionOnly && request.headers.origin!=='https://www.wildberries.ru'){response.writeHead(403);response.end('Forbidden');return;}
    if(wbDenied){response.writeHead(403);response.end('Forbidden');return;}
    if(slow)await new Promise(resolve=>setTimeout(resolve,2500));
    response.writeHead(200,{'Content-Type':'application/json','Access-Control-Allow-Origin':'https://www.wildberries.ru','Access-Control-Allow-Credentials':'true'});response.end(JSON.stringify({products:Array.from({length:7},(_,i)=>({id:100+i,name:`Наушники WB ${i}`,sizes:[{price:{product:(1299+i)*100}}]}))}));return;
  }
  if(!['www.ozon.ru','www.wildberries.ru'].includes(url.hostname)){response.writeHead(404);response.end();return;}
  if(url.pathname==='/favicon.ico'){response.writeHead(204);response.end();return;}
  const site=url.hostname.includes('ozon')?'ozon':'wb';
  const query=url.pathname.startsWith('/api/composer')?new URL(url.searchParams.get('url'),'https://www.ozon.ru').searchParams.get('text')||'':url.searchParams.get(site==='ozon'?'text':'search')||'';
  const sameOrigin=request.headers['sec-fetch-site']==='same-origin';
  requests.push({site,query,sameOrigin});
  if(sessionOnly && site==='ozon' && url.pathname!=='/' && !sameOrigin){response.writeHead(403);response.end('Forbidden');return;}
  if(sessionOnly && site==='ozon' && url.pathname.startsWith('/api/composer')){
    response.writeHead(200,{'Content-Type':'application/json'});
    response.end(JSON.stringify({widgetStates:{'tileGridDesktop-1':JSON.stringify({items:Array.from({length:5},(_,i)=>({action:{link:`/product/hudi-${200+i}/`},mainState:[{priceV2:{price:[{text:'5 999 ₽',textStyle:'ORIGINAL_PRICE'},{text:`${2399+i} ₽`,textStyle:'PRICE'}],priceStyle:{styleType:'CARD_PRICE'}}},{id:'name',textDS:{text:`Худи мужское ${i}`}}]}))})}}));return;
  }
  if(site==='wb' && wbDenied){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});response.end('<html><body><div id="app"></div></body></html>');return;}
  if(slow)await new Promise(resolve=>setTimeout(resolve,2500));
  response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});response.end(html(site,query));
});
try {({context,worker,id}=await launch(profile,{headless:process.env.HEADFUL!=='1',args:network.args}));}
catch(error){await network.close();throw error;}
context.on('weberror',error=>errors.push(error.error().message));
context.on('console',message=>{if(['error','warning'].includes(message.type()))console.log(`BROWSER: ${message.text()}`);});
const page=await context.newPage();
const widget=page.locator('#marketplace-comparison-widget');
let openedPages=0;
context.on('page',()=>openedPages++);
async function waitDone(){await widget.locator('.offer').first().waitFor({timeout:20000});}
try {
  await page.goto('https://www.ozon.ru/search/?text=Sony%20ANC');
  await waitDone();
  assert.equal(await widget.locator('.offer').count(),5);
  assert.equal((await widget.locator('.price').first().innerText()).replace(/\s/g,' '),'1 299 ₽');
  assert.match(await widget.locator('.offer').first().getAttribute('href'),/wildberries\.ru\/catalog\/100\/detail/);
  pass('Ozon search automatically shows five WB cards with their own prices and links');
  await page.waitForTimeout(1500);
  assert.equal(requests.length,2);assert.equal(context.pages().length,2); // initial blank page + user page
  assert.equal(openedPages,0);assert.equal(page.url(),'https://www.ozon.ru/search/?text=Sony%20ANC');
  pass('HTTP search opens no tabs, preserves the source URL and does not trigger a loop');
  await page.evaluate(()=>history.pushState({},'', '/search/?text=JBL%20%26%20Sony'));
  await page.waitForFunction(()=>document.querySelector('#marketplace-comparison-widget')?.shadowRoot?.querySelector('.query')?.textContent==='JBL & Sony');
  await waitDone();
  assert.equal(requests.at(-1).query,'JBL & Sony');assert.equal(requests.length,3);
  pass('SPA query changes start exactly one new partner search');
  await page.goto('https://www.ozon.ru/category/naushniki-15555/?text=Sony');await waitDone();
  assert.equal(await widget.locator('.offer').count(),5);assert.equal(openedPages,0);
  pass('Ozon category search also triggers WB JSON search without navigation');
  wbDenied=true;
  await page.evaluate(()=>history.pushState({},'', '/search/?text=wb-denied'));
  await widget.locator('.error').waitFor();
  assert.match(await widget.locator('.error').innerText(),/HTTP 403/);
  assert.equal(openedPages,0);assert.equal(page.url(),'https://www.ozon.ru/search/?text=wb-denied');
  wbDenied=false;await widget.getByRole('button',{name:'Повторить',exact:true}).click();await waitDone();
  pass('WB HTTP 403 and empty SPA HTML show an error without navigation; retry recovers');
  await page.goto('https://www.wildberries.ru/catalog/0/search.aspx?search=Sony');
  await waitDone();
  assert.equal((await widget.locator('.price').first().innerText()).replace(/\s/g,' '),'2 399 ₽');
  assert.match(await widget.locator('.offer').first().getAttribute('href'),/ozon\.ru\/product\/headphones-200/);
  pass('WB search automatically shows Ozon prices; old prices are not mixed in');
  await widget.getByRole('button',{name:'Свернуть / развернуть'}).click();
  assert.equal(await widget.locator('.body').isVisible(),false);
  await widget.getByRole('button',{name:'Свернуть / развернуть'}).click();
  pass('the page widget collapses and expands');
  blocked=true;
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=blocked'));
  await widget.locator('.error').waitFor({timeout:20000});
  assert.match(await widget.locator('.error').innerText(),/проверку|доступ/);
  blocked=false;await widget.getByRole('button',{name:'Повторить',exact:true}).click();await waitDone();
  pass('a CAPTCHA is reported honestly and retry works after access is restored');
  const popup=await context.newPage();await page.bringToFront();
  await popup.goto(`chrome-extension://${id}/popup.html`);
  await popup.waitForFunction(()=>document.body.dataset.ready==='true');
  assert.equal(await popup.locator('.offer').count(),5);
  assert.equal(await worker.evaluate(()=>chrome.offscreen.hasDocument()),false);
  pass('compact popup displays the active tab results without starting SQLite or a server');
  await popup.locator('#enabled').uncheck();await widget.waitFor({state:'detached'});
  const count=requests.length;
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=disabled'));
  await page.waitForTimeout(1800);assert.equal(requests.length,count);
  await popup.locator('#enabled').check();await waitDone();
  pass('the auto-search switch prevents new searches and resumes on enable');
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=Sony%20WH-1000XM5'));
  await page.waitForFunction(()=>document.querySelector('#marketplace-comparison-widget')?.shadowRoot?.querySelector('.query')?.textContent==='Sony WH-1000XM5');
  await waitDone();await popup.locator('.query').filter({hasText:'Sony WH-1000XM5'}).waitFor();
  await page.screenshot({path:path.join(root,'test-results/widget.png')});
  await popup.screenshot({path:path.join(root,'test-results/popup.png'),clip:{x:0,y:0,width:360,height:540}});
  slow=true;
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=cancelled'));
  await page.waitForFunction(()=>document.querySelector('#marketplace-comparison-widget')?.shadowRoot?.textContent?.includes('без открытия страниц'));
  await page.goto('https://www.wildberries.ru/');await page.waitForTimeout(3000);
  assert.equal(await widget.count(),0);
  const state=await popup.evaluate(async()=>{const {comparisons}=await chrome.storage.session.get('comparisons');return comparisons;});
  assert.equal(Object.keys(state).length,0);
  assert.equal(context.pages().length,3); // initial blank + user + popup
  pass('leaving search cancels the HTTP request without opening any worker tab');
  slow=false;sessionOnly=true;
  const ozon=await context.newPage();await ozon.goto('https://www.ozon.ru/');
  const denied=await popup.evaluate(async()=>{const r=await fetch('https://www.ozon.ru/search/?text=худи',{credentials:'include'});return r.status;});
  assert.equal(denied,403);
  const pageCount=context.pages().length;
  await page.bringToFront();await page.goto('https://www.wildberries.ru/catalog/0/search.aspx?search=худи%20мужское');
  await waitDone();
  assert.match(await widget.locator('.offer').first().innerText(),/Худи мужское/);
  assert.equal((await widget.locator('.price').first().innerText()).replace(/\s/g,' '),'2 399 ₽');
  assert.equal(ozon.url(),'https://www.ozon.ru/');
  assert.equal(page.url(),'https://www.wildberries.ru/catalog/0/search.aspx?search=%D1%85%D1%83%D0%B4%D0%B8%20%D0%BC%D1%83%D0%B6%D1%81%D0%BA%D0%BE%D0%B5');
  assert.equal(context.pages().length,pageCount);
  assert.equal(requests.at(-1).sameOrigin,true);
  pass('when extension fetch returns 403, existing Ozon tab reads same-origin JSON without navigation or new tabs');
  await ozon.close();
  backendAPI=await backendFixture();
  await popup.locator('#settings').evaluate(e=>e.open=true);
  await popup.locator('#mode').selectOption('backend');
  await popup.locator('#backend-url').fill(backendAPI.url);
  await popup.locator('#backend-token').fill('test-token');
  await popup.locator('#backend-check').click();
  await popup.locator('#settings-status').filter({hasText:'Исполнителей: 1'}).waitFor();
  await popup.locator('#settings-save').click();
  await popup.locator('#settings-status').filter({hasText:'Настройки сохранены'}).waitFor();
  await widget.locator('.price').filter({hasText:'1\u00a0234,5 ₽'}).waitFor();
  assert.match(await widget.locator('.foot').innerText(),/backend/);
  assert.equal([...backendAPI.jobs.values()][0].engine,'chrome-session');
  assert.equal([...backendAPI.jobs.values()][0].source,'худи мужское');
  pass('backend settings validate token, create the same query job, poll status and display API observations');
  await popup.locator('#backend-token').fill('wrong-token');await popup.locator('#backend-check').click();
  await popup.locator('#settings-status').filter({hasText:'HTTP 401'}).waitFor();
  await popup.locator('#backend-token').fill('test-token');
  pass('backend health check rejects an invalid API token');
  backendAPI.setBehavior('blocked');
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=backend-blocked'));
  await widget.locator('.error').filter({hasText:'Backend: Ozon HTTP 403'}).waitFor();
  assert.equal(context.pages().length,3);
  pass('backend access restrictions are shown as server errors without browser navigation');
  backendAPI.setBehavior('fixture');
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=backend-fixture'));
  await widget.locator('.error').filter({hasText:'учебные данные'}).waitFor();
  assert.equal(await widget.locator('.offer').count(),0);
  pass('automatic comparison rejects fixture jobs as live offers');
  backendAPI.setBehavior('pending');
  await page.evaluate(()=>history.pushState({},'', '/catalog/0/search.aspx?search=backend-cancel'));
  await page.waitForFunction(()=>document.querySelector('#marketplace-comparison-widget')?.shadowRoot?.textContent?.includes('Backend: задание в очереди'));
  const remote=[...backendAPI.jobs.values()].find(job=>job.source==='backend-cancel');
  await page.goto('https://www.wildberries.ru/');
  for(let i=0;i<30&&!backendAPI.cancelled.includes(remote.id);i++)await page.waitForTimeout(100);
  assert.ok(backendAPI.cancelled.includes(remote.id));
  pass('leaving the source page cancels the remote backend job');
  await popup.locator('#mode').selectOption('browser');await popup.locator('#settings-save').click();
  await popup.locator('#settings-status').filter({hasText:'Настройки сохранены'}).waitFor();
  sessionOnly=false;wbSessionOnly=true;
  const ozonSource=await context.newPage();await ozonSource.goto('https://www.ozon.ru/search/?text=session-wb');
  const otherWidget=ozonSource.locator('#marketplace-comparison-widget');
  await otherWidget.locator('.offer').first().waitFor();
  assert.equal(requests.filter(r=>r.site==='wb' && r.query==='session-wb').at(-1).origin,'https://www.wildberries.ru');
  assert.equal(page.url(),'https://www.wildberries.ru/');
  assert.equal(ozonSource.url(),'https://www.ozon.ru/search/?text=session-wb');
  await ozonSource.close();
  pass('browser Ozon → WB uses the existing WB page origin without navigation');
  const downloadPromise=popup.waitForEvent('download');await popup.locator('#browser-diagnostics').click();
  const download=await downloadPromise;await download.saveAs(path.join(resultsPath(),'browser-diagnostics-test.json'));
  const report=JSON.parse(await readFile(path.join(resultsPath(),'browser-diagnostics-test.json'),'utf8'));
  assert.equal(report.selectedMode,'browser');assert.ok(report.pages[0].contentScriptAvailable);
  assert.equal(JSON.stringify(report).includes('test-token'),false);
  assert.equal(JSON.stringify(report).includes('Authorization'),false);
  assert.ok(report.pages.every(p=>!('title' in p)));
  assert.ok(report.pages.filter(p=>!p.search).every(p=>p.domOffers.length===0));
  pass('browser diagnostic download includes page/parser state without backend credentials');
  const legacyPopup=await context.newPage();
  await legacyPopup.addInitScript(()=>{const send=chrome.runtime.sendMessage.bind(chrome.runtime);chrome.runtime.sendMessage=(...args)=>{const result=send(...args);return args[0]?.type==='state'?result.then(r=>({...r,value:{...r.value,backend:undefined}})):result;};});
  await legacyPopup.goto(`chrome-extension://${id}/popup.html`);
  await legacyPopup.waitForFunction(()=>document.body.dataset.ready==='true');
  assert.equal(await legacyPopup.locator('#mode').inputValue(),'browser');
  assert.match(await legacyPopup.locator('#settings-status').innerText(),/Обновите расширение/);
  assert.equal((await legacyPopup.locator('body').innerText()).includes('TypeError'),false);
  await legacyPopup.close();
  pass('popup handles an older service worker without settings instead of crashing on mode');
  assert.deepEqual(errors,[]);
  pass('no uncaught browser errors');
}catch(error){
  const debug={jobs:await worker.evaluate(()=>chrome.storage.session.get('comparisons')).catch(String),pages:[]};
  for(const tab of context.pages())debug.pages.push(await tab.evaluate(()=>({url:location.href,body:document.body?.innerText,widget:document.querySelector('#marketplace-comparison-widget')?.shadowRoot?.innerHTML})).catch(String));
  console.log(JSON.stringify(debug,null,2));
  throw error;
}finally{
  await mkdir(path.join(root,'test-results'),{recursive:true});
  await writeFile(path.join(root,'test-results/widget-report.json'),JSON.stringify({checks,requests,errors},null,2));
  await context.close();
  await network.close();
  await backendAPI?.close();
  if(path.dirname(profile)!==root || !path.basename(profile).startsWith('.test-profile-widget-'))throw new Error('Unsafe test profile path');
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
function resultsPath(){return path.join(root,'test-results');}
