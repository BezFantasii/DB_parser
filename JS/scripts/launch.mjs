import {launch} from './browser.mjs';
import path from 'node:path';
const {context,id}=await launch(path.resolve(import.meta.dirname,'../.browser-profile'),{headless:false});
const page=await context.newPage();await page.goto(`chrome-extension://${id}/index.html`);
await page.waitForFunction(()=>document.getElementById('db-state')?.dataset.ready==='true',null,{timeout:45000});
console.log(`Extension running: chrome-extension://${id}/index.html`);
console.log('Client connected successfully.');
console.log('Close the browser window to stop. Data is saved in JS/.browser-profile.');
await new Promise(resolve=>context.on('close',resolve));
