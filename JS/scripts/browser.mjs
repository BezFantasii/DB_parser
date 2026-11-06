import {chromium} from 'playwright';
import {existsSync,readdirSync} from 'node:fs';
import path from 'node:path';
export function executable(){
  if(process.env.CHROMIUM_PATH){if(!existsSync(process.env.CHROMIUM_PATH))throw new Error('CHROMIUM_PATH does not exist');return process.env.CHROMIUM_PATH;}
  const expected=chromium.executablePath();if(existsSync(expected))return expected;
  const cache=path.resolve(expected,'../../..');
  const candidates=existsSync(cache)?readdirSync(cache).filter(x=>/^chromium-\d+$/.test(x)).sort((a,b)=>Number(b.split('-')[1])-Number(a.split('-')[1])):[];
  for(const name of candidates)for(const suffix of ['chrome-win64/chrome.exe','chrome-win/chrome.exe','chrome-linux/chrome']){const file=path.join(cache,name,suffix);if(existsSync(file))return file;}
  throw new Error('Chromium not found. Run: npx playwright install chromium');
}
export async function launch(profile,{headless=true}={}){
  const extension=path.resolve(import.meta.dirname,'../dist');
  const context=await chromium.launchPersistentContext(profile,{executablePath:executable(),headless,viewport:{width:1440,height:1000},args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker',{timeout:30000});
  return {context,worker,id:new URL(worker.url()).hostname};
}
