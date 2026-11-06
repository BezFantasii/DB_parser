import {launch} from './browser.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..'),results=path.join(root,'test-results');
await mkdir(results,{recursive:true});
const {context,id}=await launch(path.join(root,'.live-profile'),{headless:false});
const page=await context.newPage();
async function rpc(type,args={}){return page.evaluate(async({type,args})=>{const r=await chrome.runtime.sendMessage({target:'background',type,args});if(!r?.ok)throw new Error(r?.error||'No response');return r.value;},{type,args});}
try{
  await page.goto(`chrome-extension://${id}/advanced.html#runs`);
  await page.waitForFunction(()=>document.getElementById('db-state')?.textContent.includes('подключена'),null,{timeout:45000});
  const ids=await rpc('start',{site:'both',source:'наушники',limit:1,pages:1,scrolls:1,delay:3});
  const deadline=Date.now()+110000;
  let last='';
  while(Date.now()<deadline){
    const runs=(await rpc('runs')).filter(r=>ids.includes(r.id));
    const summary=runs.map(r=>`${r.marketplace}: ${r.status} (${r.done||0}/${r.total}) ${r.error||''}`).join('\n');
    if(summary!==last){console.log(summary);last=summary;}
    if(runs.length===ids.length&&runs.every(r=>['succeeded','failed','blocked','cancelled'].includes(r.status)))break;
    await page.waitForTimeout(2000);
  }
  const runs=(await rpc('runs')).filter(r=>ids.includes(r.id));
  const products=await rpc('products');
  const errors=await rpc('errors');
  const pages=[];
  for(const [i,p] of context.pages().entries()){
    pages.push({url:p.url(),title:await p.title().catch(()=>''),body:(await p.locator('body').innerText({timeout:3000}).catch(()=>'' )).slice(0,1500).replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g,'[IP]')});
    await p.screenshot({path:path.join(results,`live-${i}.png`),fullPage:false}).catch(()=>{});
  }
  const report={checkedAt:new Date().toISOString(),runs,products,errors,pages};
  await writeFile(path.join(results,'live-report.json'),JSON.stringify(report,null,2));
  console.log(`Live collection: ${runs.filter(r=>r.status==='succeeded').length}/${ids.length} successful. ${products.total} saved offers.`);
  console.log(`Report: ${path.join(results,'live-report.json')}`);
  // Leave unfinished work paused, so running this diagnostic won't silently resume later.
  for(const r of runs)if(r.status==='running')await rpc('changeRun',{id:r.id,action:'pause'});
}finally{await context.close();}
