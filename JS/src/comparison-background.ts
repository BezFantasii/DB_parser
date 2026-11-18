import {searchContext,partnerSearch,validOffer,type Comparison,type Offer} from './comparison.ts';
import {searchHTTP} from './search-http.ts';
import {defaultBackend,backendOrigin,backendRequest,searchBackend,type BackendConfig} from './backend-search.ts';
let backend:BackendConfig={...defaultBackend};
const requests=new Map<string,AbortController>();

// Session storage survives service-worker suspension, but not a browser restart.
let jobs:Record<string,Comparison>={};
let enabled=true;
let legacyTabCheck:(tabId:number)=>Promise<boolean>=async()=>false;
export function setLegacyTabCheck(check:(tabId:number)=>Promise<boolean>){legacyTabCheck=check;}
const ready=(async()=>{
  const [session,settings]=await Promise.all([chrome.storage.session.get('comparisons'),chrome.storage.local.get(['comparisonEnabled','comparisonBackend'])]);
  jobs=(session.comparisons||{}) as Record<string,Comparison>; enabled=settings.comparisonEnabled!==false;
  if(settings.comparisonBackend)backend=settings.comparisonBackend as BackendConfig;
})();
let queue:Promise<unknown>=ready;
function serial<T>(work:()=>Promise<T>):Promise<T> {
  const next=queue.then(work);queue=next.catch(console.error);return next;
}
async function save(){await chrome.storage.session.set({comparisons:jobs});}
async function notify(job:Comparison){
  await chrome.tabs.sendMessage(job.originTab,{target:'comparison-view',job}).catch(()=>{});
  await chrome.runtime.sendMessage({target:'comparison-view',job}).catch(()=>{});
}
async function stop(job:Comparison){
  requests.get(job.id)?.abort();requests.delete(job.id);
  if(job.workerTab!==undefined){const id=job.workerTab;delete job.workerTab;await chrome.tabs.remove(id).catch(()=>{});}
  await chrome.alarms.clear(`compare:${job.id}`);
}
function runHTTP(job:Comparison){
  const controller=new AbortController();requests.set(job.id,controller);
  const useBackend=job.mode==='backend',config={...backend};
  const timeout=setTimeout(()=>controller.abort(),useBackend?180000:25000);
  const search=useBackend?searchBackend(job,config,controller.signal,(id,phase)=>serial(async()=>{
    if(jobs[job.originTab]?.id!==job.id)return;
    const changed=job.phase!==phase || job.backendJobId!==id;job.backendJobId=id;job.phase=phase;
    if(changed){await save();await notify(job);}
  })):searchHTTP(job,controller.signal);
  void search.then(
    items=>serial(async()=>{if(jobs[job.originTab]?.id!==job.id || job.status!=='loading')return;job.items=items;await finish(job);}),
    error=>serial(async()=>{if(jobs[job.originTab]?.id!==job.id || job.status!=='loading')return;await finish(job,controller.signal.aborted?`Запрос не завершился за ${useBackend?180:25} секунд. Повторите поиск.`:String(error instanceof Error?error.message:error));})
  ).catch(console.error).finally(()=>clearTimeout(timeout));
}
async function finish(job:Comparison,error?:string){
  job.status=error?'error':'done';job.error=error;job.updatedAt=Date.now();
  await stop(job);await save();await notify(job);
}
async function sync(tabId:number,address:string,retry=false){
  const owned=Object.values(jobs).find(j=>j.workerTab===tabId);
  if(owned)return {enabled,worker:{id:owned.id,target:owned.target,query:owned.query},job:null};
  if(await legacyTabCheck(tabId))return {enabled,job:null};
  const context=searchContext(address),previous=jobs[tabId];
  if(!enabled || !context){
    if(previous){await stop(previous);delete jobs[tabId];await save();}
    return {enabled,job:null};
  }
  if(!retry && previous?.query===context.query && previous.source===context.site)return {enabled,job:previous};
  if(previous)await stop(previous);
  // Keep at most three browser searches active. User tabs are never closed.
  const active=Object.values(jobs).filter(j=>j.status==='loading');
  if(active.length>=3)await finish(active.sort((a,b)=>a.updatedAt-b.updatedAt)[0],'Поиск остановлен: запущены новые запросы в других вкладках.');
  const target=context.site==='ozon'?'wb':'ozon';
  const job:Comparison={id:crypto.randomUUID(),originTab:tabId,query:context.query,source:context.site,target,
    searchUrl:partnerSearch(context.query,context.site),status:'loading',items:[],updatedAt:Date.now(),mode:backend.mode};
  jobs[tabId]=job;
  try {
    await save();
    await chrome.alarms.create(`compare:${job.id}`,{when:Date.now()+(job.mode==='backend'?210000:60000)});
    runHTTP(job);
  }catch(e){await finish(job,`Не удалось запустить запрос: ${String(e)}`);}
  return {enabled,job};
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message?.target!=='comparison' || sender.id!==chrome.runtime.id)return;
  void serial(async()=>{
    if(message.type==='sync' || message.type==='retry-current'){
      if(!sender.tab?.id || !sender.url || sender.frameId!==0)throw new Error('Нужна вкладка площадки');
      // sender.url can describe the document before a History API navigation.
      const tab=await chrome.tabs.get(sender.tab.id);
      return sync(sender.tab.id,tab.url||'',message.type==='retry-current');
    }
    if(message.type==='result'){
      const job=Object.values(jobs).find(j=>j.workerTab===sender.tab?.id && j.id===message.id && j.status==='loading');
      if(!job || sender.frameId!==0)return {ignored:true};
      const tab=await chrome.tabs.get(sender.tab!.id!);
      const context=searchContext(tab.url||'');
      if(!context || context.site!==job.target || context.query!==job.query){await finish(job,'Площадка перенаправила поиск. Откройте выдачу вручную.');return {};}
      if(message.error){await finish(job,String(message.error).slice(0,500));return {};}
      const items:unknown=message.items;
      if(!Array.isArray(items) || items.length>5 || !items.every((item:unknown)=>validOffer(item,job.target)))throw new Error('Неверные данные карточек');
      job.items=[...new Map((items as Offer[]).map(item=>[item.url,item])).values()];
      await finish(job,job.items.length?undefined:'Не удалось найти карточки с ценами. Откройте поиск на площадке или повторите.');
      return {};
    }
    if(!sender.url?.startsWith(chrome.runtime.getURL('')))throw new Error('Команда доступна только окну расширения');
    if(message.type==='state')return {enabled,job:jobs[Number(message.tabId)]||null,backend};
    if(message.type==='browser.diagnostics'){
      const tabs=await chrome.tabs.query({url:['https://www.ozon.ru/*','https://ozon.ru/*','https://www.wildberries.ru/*','https://wildberries.ru/*']});
      const pages=[];
      for(const tab of tabs.slice(0,10)){
        if(!tab.id)continue;
        const info=searchContext(tab.url||'');
        const safeURL=tab.url?new URL(tab.url):null;
        if(safeURL){safeURL.username='';safeURL.password='';safeURL.search='';safeURL.hash='';if(info)safeURL.searchParams.set(info.site==='ozon'?'text':'search',info.query);else safeURL.pathname='/';}
        let state:any;
        try{state=await chrome.tabs.sendMessage(tab.id,{target:'comparison-browser-diagnostics'});if(!state?.contentScriptAvailable)state={contentScriptAvailable:false,hint:'Скрипт не ответил на диагностику; обновите расширение и перезагрузите вкладку'};}
        catch{state={contentScriptAvailable:false,hint:'Перезагрузите эту вкладку после обновления расширения'};}
        pages.push({url:safeURL?.href,status:tab.status,discarded:tab.discarded,...state});
      }
      const job=jobs[Number(message.tabId)];
      return {formatVersion:1,createdAt:new Date().toISOString(),extensionVersion:chrome.runtime.getManifest().version,userAgent:navigator.userAgent,enabled,selectedMode:backend.mode,
        job:job?(job.mode==='backend'?{mode:'backend',status:job.status,hint:'Для браузерной проверки выберите «В браузере»'}:{query:job.query,source:job.source,target:job.target,mode:job.mode,status:job.status,error:job.error,items:job.items}):null,pages};
    }
    if(message.type==='configure'){
      if(!['browser','backend'].includes(message.config?.mode) || typeof message.config?.token!=='string' || message.config.token.length>1000)throw new Error('Неверные настройки backend');
      const config:BackendConfig={mode:message.config.mode,url:backendOrigin(message.config.url),token:message.config.token};
      if(config.mode==='backend' && !await chrome.permissions.contains({origins:[config.url+'/*']}))throw new Error('Нет разрешения на доступ к backend');
      for(const job of Object.values(jobs))await stop(job);
      jobs={};backend=config;await save();await chrome.storage.local.set({comparisonBackend:backend});
      for(const tab of await chrome.tabs.query({})){if(tab.id)await chrome.tabs.sendMessage(tab.id,{target:'comparison-refresh'}).catch(()=>{});}
      return {};
    }
    if(message.type==='backend.health')return backendRequest(backend,'/health/ready',AbortSignal.timeout(10000));
    if(message.type==='retry'){
      const tab=await chrome.tabs.get(Number(message.tabId));
      return sync(tab.id!,tab.url||'',true);
    }
    if(message.type==='enable'){
      enabled=message.enabled===true;
      await chrome.storage.local.set({comparisonEnabled:enabled});
      if(!enabled){for(const job of Object.values(jobs))await stop(job);jobs={};await save();}
      for(const tab of await chrome.tabs.query({})){if(tab.id)await chrome.tabs.sendMessage(tab.id,{target:'comparison-refresh'}).catch(()=>{});}
      return {enabled};
    }
    throw new Error('Неизвестная команда');
  }).then(value=>respond({ok:true,value}),error=>respond({ok:false,error:String(error)}));
  return true;
});
void ready.then(()=>{for(const job of Object.values(jobs))if(job.status==='loading' && job.mode==='backend')runHTTP(job);});
chrome.alarms.onAlarm.addListener(alarm=>{
  if(!alarm.name.startsWith('compare:'))return;
  void serial(async()=>{const job=Object.values(jobs).find(j=>`compare:${j.id}`===alarm.name);if(job?.status==='loading')await finish(job,'Площадка не ответила за 60 секунд. Повторите поиск или откройте его вручную.');});
});
chrome.tabs.onRemoved.addListener(tabId=>void serial(async()=>{
  if(jobs[tabId]){await stop(jobs[tabId]);delete jobs[tabId];await save();return;}
  const job=Object.values(jobs).find(j=>j.workerTab===tabId);
  if(job)await finish(job,'Фоновая вкладка поиска была закрыта. Нажмите «Повторить».');
}));
chrome.tabs.onUpdated.addListener((tabId,change)=>{
  if(!change.url)return;
  void serial(async()=>{
    const job=jobs[tabId];if(!job)return;
    const context=searchContext(change.url!);
    if(!context || context.query!==job.query || context.site!==job.source){await stop(job);delete jobs[tabId];await save();}
  });
});
