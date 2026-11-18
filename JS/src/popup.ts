import {renderComparison} from './comparison-view.ts';
import {backendOrigin,backendRequest,type BackendConfig} from './backend-search.ts';
import {popupState} from './popup-state.ts';
const body=document.getElementById('results')!;
const toggle=document.getElementById('enabled') as HTMLInputElement;
let tabId:number|undefined;
const mode=document.getElementById('mode') as HTMLSelectElement;
const address=document.getElementById('backend-url') as HTMLInputElement;
const token=document.getElementById('backend-token') as HTMLInputElement;
const settingsStatus=document.getElementById('settings-status')!;
let settingsLoaded=false;
mode.onchange=()=>{document.getElementById('backend-fields')!.hidden=mode.value!=='backend';};
function config():BackendConfig{
  let url=address.value;
  if(mode.value==='browser'){try{url=backendOrigin(url);}catch{url='http://127.0.0.1:8000';}}
  return {mode:mode.value as BackendConfig['mode'],url:backendOrigin(url),token:token.value.trim()};
}
async function permission(value:BackendConfig){if(value.mode==='backend' && value.url.startsWith('https:') && !await chrome.permissions.request({origins:[value.url+'/*']}))throw new Error('Не предоставлен доступ к серверу');}
document.getElementById('settings-save')!.onclick=()=>{
  void (async()=>{try{const value=config();await permission(value);await rpc('configure',{config:value});settingsStatus.textContent='Настройки сохранены';await refresh();}catch(error){settingsStatus.textContent=String(error);}})();
};
document.getElementById('backend-check')!.onclick=()=>{
  void (async()=>{try{const value=config();await permission({...value,mode:'backend'});settingsStatus.textContent='Проверяем API, token и базу данных…';await backendRequest(value,'/api/v1/marketplaces',AbortSignal.timeout(10000));const health=await backendRequest(value,'/health/ready',AbortSignal.timeout(10000));settingsStatus.textContent=health.workers_online===0?'API и БД доступны, но worker не запущен':`API и БД доступны. Исполнителей: ${health.workers_online??'см. статус сервера'}`;}catch(error){settingsStatus.textContent=String(error);}})();
};
async function rpc(type:string,args:Record<string,unknown>={}){
  const result=await chrome.runtime.sendMessage({target:'comparison',type,...args});
  if(!result?.ok)throw new Error(result?.error||'Расширение не отвечает');return result.value;
}
async function refresh(){
  const state=popupState(await rpc('state',{tabId}));toggle.checked=state.enabled;
  if(state.missingSettings){settingsStatus.textContent='Настройки не пришли от фонового процесса. Обновите расширение на chrome://extensions и перезагрузите страницы магазинов.';document.getElementById('settings')!.setAttribute('open','');}
  if(!settingsLoaded){mode.value=state.backend.mode;address.value=state.backend.url;token.value=state.backend.token;document.getElementById('backend-fields')!.hidden=mode.value!=='backend';settingsLoaded=true;}
  renderComparison(body,state.job,state.enabled,()=>void action(async()=>{await rpc('retry',{tabId});await refresh();}));
}
document.getElementById('browser-diagnostics')!.onclick=()=>{
  void (async()=>{try{
    const report=await rpc('browser.diagnostics',{tabId});
    const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='marketplace-browser-diagnostics.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),5000);
  }catch(error){settingsStatus.textContent=`Не удалось собрать диагностику: ${String(error)}. Обновите расширение и страницы магазинов.`;}})();
};
async function action(work:()=>Promise<void>){try{await work();}catch(error){body.textContent=String(error);}}
toggle.onchange=()=>void action(async()=>{await rpc('enable',{enabled:toggle.checked});await refresh();});
chrome.runtime.onMessage.addListener(message=>{if(message.target==='comparison-view' && message.job.originTab===tabId)void action(refresh);});
void action(async()=>{tabId=(await chrome.tabs.query({active:true,currentWindow:true}))[0]?.id;await refresh();document.body.dataset.ready='true';});
