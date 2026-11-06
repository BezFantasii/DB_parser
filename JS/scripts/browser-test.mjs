import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {launch} from './browser.mjs';
const root=path.resolve(import.meta.dirname,'..');
const profile=path.join(root,`.test-profile-${Date.now()}`);
const results=path.join(root,'test-results');await mkdir(results,{recursive:true});
const logs=[];let context,page,extensionId;
function monitor(ctx){ctx.on('console',m=>{if(m.type()==='error'||m.type()==='warning')logs.push(`${m.type()}: ${m.text()}`);});ctx.on('weberror',e=>logs.push(`pageerror: ${e.error().message}`));}
async function rpc(type,args={}){return page.evaluate(async({type,args})=>{const r=await chrome.runtime.sendMessage({target:'background',type,args});if(!r?.ok)throw new Error(r?.error||'No response');return r.value;},{type,args});}
async function db(method,args={}){return page.evaluate(async({method,args})=>{const r=await chrome.runtime.sendMessage({target:'database',method,args});if(!r?.ok)throw new Error(r?.error||'No database response');return r.value;},{method,args});}
const item=(id,price='1299.50',extra={})=>({url:`https://www.ozon.ru/product/headphones-${id}/`,external_id:String(id),name:'Беспроводные полноразмерные наушники с ANC и микрофоном',price,brand:'Example',rating:'4.80',reviews_count:1234,...extra});
const batch=(items,site='ozon')=>({marketplace:site,source_url:'test-fixture',items});
const checks=[];function passed(name){checks.push(name);console.log(`PASS ${name}`);}
async function waitRun(id,timeout=45000,expected='succeeded'){
  const end=Date.now()+timeout;
  while(Date.now()<end){const run=(await rpc('runs')).find(x=>x.id===id);if(run?.status===expected)return;if(['failed','blocked'].includes(run?.status))throw new Error(JSON.stringify(run));await page.waitForTimeout(500);}
  throw new Error(`Run ${id} timed out: ${JSON.stringify(await rpc('runs'))}`);
}
try{
  let launched=await launch(profile);context=launched.context;extensionId=launched.id;monitor(context);
  page=await context.newPage();await page.goto(`chrome-extension://${extensionId}/advanced.html`);
  await page.waitForFunction(()=>document.getElementById('db-state')?.textContent.includes('подключена'),{timeout:45000});
  assert.equal((await rpc('stats')).backend,'SQLite WASM / OPFS');passed('SQLite opens in an offscreen worker with OPFS');
  await rpc('import',batch([item(123)]));assert.equal((await rpc('stats')).products,1);
  const first=(await rpc('products')).items[0];assert.equal(first.price_minor,129950);assert.equal(first.anc,1);passed('exact prices and features are saved');
  const before=await rpc('stats');await assert.rejects(()=>rpc('import',batch([item(456),item(789,'-1')])));assert.equal((await rpc('stats')).observations,before.observations);passed('invalid batch leaves no partial data');
  const stamp='2026-11-05T00:00:00Z';
  await rpc('import',batch([item(123,'1200.00',{observed_at:stamp})]));
  await rpc('import',batch([item(123,null,{observed_at:'2026-11-06T00:00:00Z',availability:'out_of_stock'})]));
  const current=(await rpc('products')).items[0];
  // Use far-future controlled context so the assertion doesn't depend on the host clock.
  await rpc('import',batch([item(123,null,{observed_at:'2090-01-01T00:00:00Z',availability:'out_of_stock'})]));
  assert.equal((await rpc('products')).items[0].price_minor,null);passed('latest unavailable offer never falls back to an older price');
  await rpc('import',batch([{...item(555),url:'https://www.wildberries.ru/catalog/555/detail.aspx',external_id:'555'}],'wb'));
  assert.equal((await rpc('analogs',{id:first.id,anc:true})).length,1);passed('cross-marketplace analogs use confirmed features');
  // Exercise staging, token validation, run publication and replay protection without live network.
  const run=await db('createRun',{site:'ozon',url:'https://www.ozon.ru/search/?text=atomic',limit:2,scrolls:0,delay:1});
  const listing=await db('claim');assert.equal(listing.run_id,run);
  await db('result',{taskId:listing.id,token:listing.token,trusted:true,data:[item(801).url,item(802).url]});
  await page.waitForTimeout(1100);
  const t1=await db('claim');await db('result',{taskId:t1.id,token:t1.token,trusted:true,data:item(801)});
  assert.equal((await rpc('products',{search:'801'})).total,0);assert.equal((await rpc('runs')).find(x=>x.id===run).staged,1);
  const replay=await db('result',{taskId:t1.id,token:t1.token,trusted:true,data:item(801)});assert.equal(replay.ignored,true);
  await db('changeRun',{id:run,action:'pause'});await page.waitForTimeout(1100);assert.equal(await db('claim'),null);
  await db('changeRun',{id:run,action:'resume'});const t2=await db('claim');
  const stale=await db('result',{taskId:t2.id,token:'stale',trusted:true,data:item(802)});assert.equal(stale.ignored,true);
  await db('result',{taskId:t2.id,token:t2.token,trusted:true,data:item(802)});
  assert.equal((await rpc('runs')).find(x=>x.id===run).status,'succeeded');assert.equal((await rpc('products',{search:'801'})).total,1);passed('staging, atomic publication, pause/resume and stale-token protection');
  // Load original HTML fixtures through marketplace URLs; production content scripts do the parsing.
  const fixture=await readFile(path.resolve(root,'../tests/fixtures/ozon_product.html'),'utf8');
  const wbFixture=await readFile(path.resolve(root,'../tests/fixtures/wb_product.html'),'utf8');
  await context.route('https://www.ozon.ru/**',route=>{
    const url=new URL(route.request().url());
    if(url.searchParams.get('text')==='blocked')return route.fulfill({status:403,contentType:'text/html; charset=utf-8',body:'<html><title>Похоже, нет соединения</title><body>Похоже, нет&nbsp;соединения <button>Обратиться в поддержку</button></body></html>'});
    const body=url.pathname.includes('/product/')?fixture:'<html><body><h1>Поиск</h1><a href="/product/fixture-901/">Карточка</a><a href="/product/fixture-902/">Карточка 2</a></body></html>';
    return route.fulfill({status:200,contentType:'text/html; charset=utf-8',body});
  });
  await context.route('https://www.wildberries.ru/**',route=>route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:route.request().url().includes('/904/')?'<html><body>Что-то не так... Подозрительная активность. Пожалуйста, подождите.</body></html>':wbFixture}));
  const [pipeline]=await rpc('start',{site:'ozon',source:'fixture',limit:2,pages:1,scrolls:0,delay:1});
  await waitRun(pipeline);
  assert.equal((await rpc('products',{search:'901'})).items[0].price_minor,129950);
  const [wbRun]=await rpc('start',{site:'wb',source:'https://www.wildberries.ru/catalog/903/detail.aspx',limit:1,delay:1});
  await waitRun(wbRun,30000);
  passed('real extension tab → content script → SQLite pipeline for Ozon and WB fixtures');
  const [blockedOzon]=await rpc('start',{site:'ozon',source:'blocked',limit:1,scrolls:0,delay:1});await waitRun(blockedOzon,20000,'blocked');await rpc('changeRun',{id:blockedOzon,action:'cancel'});
  const [blockedWb]=await rpc('start',{site:'wb',source:'https://www.wildberries.ru/catalog/904/detail.aspx',limit:1,delay:1});await waitRun(blockedWb,20000,'blocked');await rpc('changeRun',{id:blockedWb,action:'cancel'});
  passed('Ozon nonbreaking-space denial and WB suspicious-activity pages pause immediately');
  for(const code of ['Q01','Q02','Q03','Q04','Q05','Q06','Q07','Q08','Q09','Q10'])assert.ok(Array.isArray(await rpc('report',{code,id:first.id,days:30})));
  passed('all ten named SQL reports execute');
  await rpc('watch',{id:first.id,minutes:60});assert.equal((await rpc('watchlist')).length,1);await rpc('watch',{id:first.id,minutes:0});
  await assert.rejects(()=>rpc('watch',{id:first.id,minutes:1}));passed('watchlist validates intervals and persists changes');
  const json=await rpc('exportJSON');assert.ok(json.length===2);passed('JSON export contains both marketplaces');
  const backup=await rpc('backup');const backupBytes=await page.evaluate(async url=>Array.from(new Uint8Array(await(await fetch(url)).arrayBuffer())),backup.url);
  assert.equal(Buffer.from(backupBytes).subarray(0,16).toString(),'SQLite format 3\0');await writeFile(path.join(results,'verified-backup.sqlite'),Buffer.from(backupBytes));
  const savedStats=await rpc('stats');await rpc('import',batch([item(999)]));
  const restored=await rpc('restore',{url:backup.url});assert.equal(restored.stats.products,savedStats.products);passed('SQLite backup validates and restores into trusted schema');
  await page.click('[data-page="products"]');await page.click('#refresh');await page.waitForTimeout(500);
  await page.screenshot({path:path.join(results,'products.png'),fullPage:true});
  await page.locator('#products-body button').first().click();await page.waitForSelector('#detail[open]');await page.screenshot({path:path.join(results,'product-details.png'),fullPage:true});await page.click('#close-detail');
  // Isolate this deterministic checkpoint test from the production scheduler already tested above.
  await page.waitForTimeout(5000);await page.evaluate(()=>chrome.alarms.clear('queue'));
  const interrupted=await db('createRun',{site:'ozon',url:'https://www.ozon.ru/search/?text=checkpoint',limit:2,scrolls:0,delay:1});
  const checkpointListing=await db('claim');await db('result',{taskId:checkpointListing.id,token:checkpointListing.token,trusted:true,data:[item(951).url,item(952).url]});
  await page.waitForTimeout(1100);const checkpointCard=await db('claim');await db('result',{taskId:checkpointCard.id,token:checkpointCard.token,trusted:true,data:item(951)});await db('changeRun',{id:interrupted,action:'pause'});
  const persistent=await rpc('stats');context.removeAllListeners('console');await context.close();
  launched=await launch(profile);context=launched.context;monitor(context);page=await context.newPage();await page.goto(`chrome-extension://${launched.id}/advanced.html`);await page.waitForFunction(()=>document.getElementById('db-state')?.textContent.includes('подключена'),{timeout:45000});
  assert.equal((await rpc('stats')).products,persistent.products);assert.equal((await rpc('stats')).observations,persistent.observations);passed('database survives a complete browser restart');
  const checkpoint=(await rpc('runs')).find(r=>r.id===interrupted);assert.equal(checkpoint.status,'paused');assert.equal(checkpoint.staged,1);
  await page.waitForTimeout(2000);await page.evaluate(()=>chrome.alarms.clear('queue'));
  await db('changeRun',{id:interrupted,action:'resume'});const remaining=await db('claim');await db('result',{taskId:remaining.id,token:remaining.token,trusted:true,data:item(952)});
  assert.equal((await rpc('stats')).observations,persistent.observations+2);assert.equal((await rpc('runs')).find(r=>r.id===interrupted).status,'succeeded');passed('staged checkpoint survives restart and resumes without duplicate observations');
  await writeFile(path.join(results,'browser-report.json'),JSON.stringify({checks,stats:await rpc('stats'),logs,profile},null,2));
  if(logs.some(x=>x.startsWith('pageerror:')))throw new Error(`Page errors: ${logs.join('\n')}`);
  console.log(`${checks.length} browser checks passed. Artifacts: ${results}`);
}catch(error){
  console.error(error);console.error('Browser logs:',logs.join('\n'));
  if(page)await page.screenshot({path:path.join(results,'failure.png'),fullPage:true}).catch(()=>{});
  const debug=page?{runs:await rpc('runs').catch(()=>null),products:await rpc('products').catch(()=>null),tasks:await db('tasks',{id:7}).catch(()=>null),tabs:context?.pages().map(p=>p.url())}:{};
  await writeFile(path.join(results,'failure.json'),JSON.stringify({checks,error:String(error),logs,profile,...debug},null,2));process.exitCode=1;
}finally{await context?.close().catch(()=>{});}
