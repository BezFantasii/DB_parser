import {mkdir,writeFile,rm} from 'node:fs/promises';
import path from 'node:path';
import {launch} from './browser.mjs';
const root=path.resolve(import.meta.dirname,'..'),out=path.join(root,'test-results');
await mkdir(out,{recursive:true});
const profile=path.join(root,`.test-profile-widget-live-${Date.now()}`);
const {context,id}=await launch(profile,{headless:false});
const control=await context.newPage();await control.goto(`chrome-extension://${id}/popup.html`);
const page=await context.newPage();
const report=[];
try {
  if(process.argv.includes('--ozon-session')){
    const query='худи мужское';
    const direct=await control.evaluate(async()=>{try{const r=await fetch('https://www.ozon.ru/search/?text='+encodeURIComponent('худи мужское'),{credentials:'include',signal:AbortSignal.timeout(10000)});return {status:r.status};}catch(e){return {error:String(e)};}});
    let navigationError=null;
    await page.goto('https://www.ozon.ru/',{waitUntil:'domcontentloaded',timeout:20000}).catch(e=>{navigationError=e.message;});
    await page.waitForTimeout(2000);
    const session=await control.evaluate(async query=>{
      const tab=(await chrome.tabs.query({url:['https://www.ozon.ru/*','https://ozon.ru/*']}))[0];
      if(!tab?.id)return {error:'Ozon did not open'};
      try{return await chrome.tabs.sendMessage(tab.id,{target:'comparison-ozon-session',id:'live-probe',query});}
      catch(e){return {error:String(e)};}
    },query);
    report.push({query,direct,actualURL:page.url(),title:await page.title().catch(String),navigationError,session});
    console.log(JSON.stringify(report[0],null,2));
  }else for(const url of ['https://www.ozon.ru/search/?text=Sony%20WH-1000XM5','https://www.wildberries.ru/catalog/0/search.aspx?search=Sony%20WH-1000XM5']){
    console.log(`Checking ${url}`);
    let navigationError=null;
    await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000}).catch(e=>{navigationError=e.message;});
    const deadline=Date.now()+65000;
    let state=null;
    while(Date.now()<deadline){
      state=await control.evaluate(async()=>{const {comparisons}=await chrome.storage.session.get('comparisons');return Object.values(comparisons||{})[0]||null;});
      if(state && state.status!=='loading')break;
      if(!state && navigationError)break;
      await page.waitForTimeout(1000);
    }
    const entry={url,actualURL:page.url(),title:await page.title().catch(String),navigationError,state};
    report.push(entry);console.log(JSON.stringify(entry,null,2));
    await page.screenshot({path:path.join(out,`widget-live-${report.length}.png`)}).catch(()=>{});
    await page.goto('about:blank');
  }
}finally{
  await writeFile(path.join(out,process.argv.includes('--ozon-session')?'ozon-session-live.json':'widget-live.json'),JSON.stringify(report,null,2));
  await context.close();
  if(path.dirname(profile)!==root || !path.basename(profile).startsWith('.test-profile-widget-live-'))throw new Error('Unsafe test profile path');
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
