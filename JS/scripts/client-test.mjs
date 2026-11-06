import assert from 'node:assert/strict';
import path from 'node:path';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {launch} from './browser.mjs';
const root=path.resolve(import.meta.dirname,'..'),out=path.join(root,'test-results');await mkdir(out,{recursive:true});
const {context,id}=await launch(path.join(root,`.test-profile-client-${Date.now()}`));const errors=[];
context.on('weberror',e=>errors.push(e.error().message));
const page=await context.newPage();
async function waitUntil(fn,timeout=45000){const end=Date.now()+timeout;while(Date.now()<end){if(await fn())return;await page.waitForTimeout(400);}throw new Error('Timed out');}
async function rpc(type,args={}){return page.evaluate(async({type,args})=>{const r=await chrome.runtime.sendMessage({target:'background',type,args});if(!r?.ok)throw new Error(r?.error);return r.value;},{type,args});}
async function http(url){return rpc('backend.request',{path:url});}
const checks=[];const pass=x=>{checks.push(x);console.log('PASS',x);};
try{
  await page.goto(`chrome-extension://${id}/index.html`);
  await page.waitForFunction(()=>document.body.dataset.initialized==='true');
  await page.locator('#api-url').fill(process.env.TEST_API_URL||'http://127.0.0.1:8001');await page.locator('#api-token').fill('test-token');await page.click('#save-config');
  await waitUntil(async()=>await page.locator('#db-state').getAttribute('data-ready')==='true');
  assert.equal((await http('/health/ready')).database,'ok');pass('extension talks to real HTTP API with Bearer auth');
  await page.locator('#api-token').fill('wrong');await page.click('#save-config');await waitUntil(async()=>(await page.locator('#notice').innerText()).includes('401'));
  await page.locator('#api-token').fill('test-token');await page.click('#save-config');await waitUntil(async()=>await page.locator('#db-state').getAttribute('data-ready')==='true');
  const existingJobs=new Set((await http('/api/v1/jobs')).items.map(j=>j.id));
  await page.check('#fixture');await page.locator('#limit').fill('1');await page.click('#start');
  await waitUntil(async()=>{const jobs=(await http('/api/v1/jobs')).items.filter(j=>!existingJobs.has(j.id));return jobs.length===2&&jobs.every(j=>j.status==='succeeded');});
  await waitUntil(async()=>(await page.locator('#events').innerText()).includes('job.succeeded'));
  await page.click('#load-products');await waitUntil(async()=>await page.locator('#results tr').count()===2);
  assert.ok((await page.locator('#results').innerText()).includes('fixture'));await page.screenshot({path:path.join(out,'client-backend.png'),fullPage:true});pass('simplified UI displays jobs, progress events and PostgreSQL results for both parsers');
  const fixture=await readFile(path.resolve(root,'../tests/fixtures/ozon_product.html'),'utf8'),wb=await readFile(path.resolve(root,'../tests/fixtures/wb_current.html'),'utf8');
  await context.route('https://www.ozon.ru/**',route=>route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:route.request().url().includes('/product/')?fixture:'<html><body><a href="/product/fixture-701/">Товар</a></body></html>'}));
  await context.route('https://www.wildberries.ru/**',route=>route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:route.request().url().includes('/catalog/0/')?'<html><body><a href="/catalog/702/detail.aspx">Товар</a></body></html>':wb}));
  await page.selectOption('#mode','local');await waitUntil(async()=>(await page.locator('#db-state').innerText()).includes('SQLite'));
  await page.click('#start');
  await waitUntil(async()=>{const jobs=await rpc('runs');return jobs.length===2&&jobs.every(j=>j.status==='succeeded');},60000);
  const local=(await rpc('products')).items;assert.equal(local.length,2);assert.equal(local.find(p=>p.marketplace==='wb').price_minor,129900);assert.equal(local.find(p=>p.marketplace==='wb').old_price_minor,200000);
  await page.click('#load-products');await waitUntil(async()=>await page.locator('#results tr').count()===2);await page.screenshot({path:path.join(out,'client-local.png'),fullPage:true});pass('same UI runs native JS port of new WB algorithm and Ozon parser with SQLite');
  assert.equal(errors.length,0,errors.join('\n'));
  await writeFile(path.join(out,'client-report.json'),JSON.stringify({checks,errors},null,2));
}catch(e){await page.screenshot({path:path.join(out,'client-failure.png'),fullPage:true});console.error(e);console.error(errors);process.exitCode=1;}finally{await context.close();}
