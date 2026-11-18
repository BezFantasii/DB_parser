// A controlled WB source page sends a real job to the running backend.
// The backend uses real Ozon and PostgreSQL; product data is not mocked.
import assert from 'node:assert/strict';
import {mkdir,writeFile,rm} from 'node:fs/promises';
import path from 'node:path';
import {launch} from './browser.mjs';
import {fixtureNetwork} from './fixture-network.mjs';
const root=path.resolve(import.meta.dirname,'..'),profile=path.join(root,`.test-profile-widget-backend-live-${Date.now()}`),out=path.join(root,'test-results');
await mkdir(out,{recursive:true});
const network=await fixtureNetwork((request,response)=>{
  response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
  response.end('<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Проверка WB → backend</title></head><body><h1>Тестовая страница поиска WB</h1><p>Результаты в виджете получаются с живого Ozon через настоящий API и PostgreSQL.</p></body></html>');
});
let context;
try{
  const launched=await launch(profile,{args:network.args});context=launched.context;
  const control=await context.newPage();await control.goto(`chrome-extension://${launched.id}/popup.html`);
  await control.evaluate(async config=>{const result=await chrome.runtime.sendMessage({target:'comparison',type:'configure',config});if(!result?.ok)throw new Error(result?.error);},{mode:'backend',url:process.env.API_URL||'http://127.0.0.1:8000',token:process.env.API_TOKEN||''});
  const page=await context.newPage();await page.goto('https://www.wildberries.ru/catalog/0/search.aspx?search='+encodeURIComponent('худи мужское'));
  const widget=page.locator('#marketplace-comparison-widget');
  await widget.locator('.offer').first().waitFor({timeout:120000});
  const state=await control.evaluate(async()=>{const {comparisons}=await chrome.storage.session.get('comparisons');return Object.values(comparisons||{})[0];});
  assert.equal(state.mode,'backend');assert.equal(state.status,'done');assert.equal(state.target,'ozon');
  assert.equal(state.items.length,5);assert.ok(state.backendJobId);
  assert.ok(state.items.every(item=>new URL(item.url).hostname==='www.ozon.ru' && Number(item.price)>0));
  await page.screenshot({path:path.join(out,'backend-live-widget.png')});
  await writeFile(path.join(out,'backend-live-widget.json'),JSON.stringify({source:'Controlled WB search page; actual API, worker, Ozon and PostgreSQL',job:state},null,2));
  console.log(JSON.stringify({status:state.status,saved:state.items.length,backendJobId:state.backendJobId}));
}finally{
  await context?.close();await network.close();
  if(path.dirname(profile)!==root || !path.basename(profile).startsWith('.test-profile-widget-backend-live-'))throw new Error('Unsafe test profile path');
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
