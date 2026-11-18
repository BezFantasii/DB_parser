import {launch} from './browser.mjs';
import path from 'node:path';
const {context,id}=await launch(path.resolve(import.meta.dirname,'../.browser-profile'),{headless:false});
const page=await context.newPage();await page.goto(`chrome-extension://${id}/popup.html`);
await page.waitForFunction(()=>document.body.dataset.ready==='true',null,{timeout:15000});
console.log(`Extension running: chrome-extension://${id}/popup.html`);
console.log('Search on Ozon or Wildberries: the comparison widget appears automatically.');
console.log('Close the browser window to stop. Data is saved in JS/.browser-profile.');
await new Promise(resolve=>context.on('close',resolve));
