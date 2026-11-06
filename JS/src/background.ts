import {marketplaceFor, productUrl, sourceUrl} from "./domain.ts";
let creating: Promise<void> | null = null;
async function ensureDatabase(): Promise<void> {
  const url = chrome.runtime.getURL("offscreen.html");
  if ((await chrome.runtime.getContexts({contextTypes:[chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],documentUrls:[url]})).length) return;
  if (!creating) creating = chrome.offscreen.createDocument({url:"offscreen.html",reasons:[chrome.offscreen.Reason.WORKERS,chrome.offscreen.Reason.BLOBS],justification:"SQLite WASM runs in a dedicated worker and creates database backup blobs."}).finally(()=>{creating=null;});
  await creating;
}
export async function db(method: string, args: any = {}): Promise<any> {
  await ensureDatabase();
  const response = await chrome.runtime.sendMessage({target:"database",method,args});
  if (!response?.ok) throw new Error(response?.error || "База не ответила");
  return response.value;
}
async function broadcast(): Promise<void> { await chrome.runtime.sendMessage({target:"ui",type:"changed"}).catch(()=>{}); }
const dispatching = new Set<string>();
async function dispatch(task: any): Promise<void> {
  if (dispatching.has(task.token) || task.run_status !== "running") return;
  dispatching.add(task.token);
  try {
    const tab = await chrome.tabs.get(task.tab_id);
    await db("localEvent",{runId:task.run_id,stage:"page.parsing",data:{url:task.url,kind:task.kind}});
    if (!tab.url || marketplaceFor(tab.url) !== task.marketplace) throw new Error("Рабочая вкладка перешла на другую площадку");
    if (task.kind === "product" && productUrl(tab.url,task.marketplace).id !== productUrl(task.url,task.marketplace).id) throw new Error("Открылась другая карточка");
    await chrome.scripting.executeScript({target:{tabId:tab.id!},files:["content.js"]});
    await chrome.tabs.sendMessage(tab.id!,{target:"parser",type:"collect",taskId:task.id,token:task.token,site:task.marketplace,kind:task.kind,limit:task.settings.limit,scrolls:task.settings.scrolls});
  } catch(error) {
    await db("result",{taskId:task.id,token:task.token,error:error instanceof Error ? error.message : String(error),trusted:true});
    dispatching.delete(task.token);
    kick();
  }
}
let pumping: Promise<void> | null = null;
let sessionReady: Promise<void> | null = null;
function ensureSession(): Promise<void> {
  if(!sessionReady) sessionReady=(async()=>{
    const state=await chrome.storage.session.get("parserSession");
    if(!state.parserSession){await db("recoverSession");await chrome.storage.session.set({parserSession:crypto.randomUUID()});}
  })().catch(error=>{sessionReady=null;throw error;});
  return sessionReady;
}
function kick(delay=3500): void { setTimeout(()=>void pump().catch(console.error),delay); }
async function pump(): Promise<void> {
  if (pumping) return pumping;
  pumping = (async()=>{
    await ensureSession();
    await db("schedule");
    const task = await db("claim");
    if (task) {
      try {
        let tab: chrome.tabs.Tab | null = null;
        if (task.tab_id) tab = await chrome.tabs.get(task.tab_id).catch(()=>null);
        if(tab){try{if(marketplaceFor(tab.url||"")!==task.marketplace)tab=null;}catch{tab=null;}}
        if (!tab) tab = await chrome.tabs.create({url:"about:blank",active:false});
        if (!tab?.id) throw new Error("Не удалось открыть рабочую вкладку");
        await db("bind",{id:task.id,token:task.token,tabId:tab.id});
        await db("localEvent",{runId:task.run_id,stage:"page.loading",data:{url:task.url,attempt:task.attempts}});
        await chrome.tabs.update(tab.id,{url:task.url});
        const current = await chrome.tabs.get(tab.id!);
        if (current.status === "complete") await dispatch(await db("task",{id:task.id}));
      } catch(error) {
        await db("result",{taskId:task.id,token:task.token,error:String(error),trusted:true});
        kick();
      }
      await broadcast();
    }
    const alerts = await db("pendingAlerts");
    for (const alert of alerts) {
      await chrome.notifications.create(`price-${alert.id}`,{type:"basic",iconUrl:"icon.png",title:"Цена снизилась",message:alert.message}).catch(console.error);
      await db("alertNotified",{id:alert.id});
    }
  })().finally(()=>{pumping=null;});
  return pumping;
}
async function openApp(): Promise<void> {
  const url = chrome.runtime.getURL("index.html");
  const existing = (await chrome.tabs.query({})).find(tab=>tab.url?.split("#")[0]===url);
  if (existing?.id) { await chrome.tabs.update(existing.id,{active:true}); if (existing.windowId) await chrome.windows.update(existing.windowId,{focused:true}); }
  else await chrome.tabs.create({url});
}
chrome.action.onClicked.addListener(()=>void openApp());
chrome.runtime.onInstalled.addListener(()=>{
  void chrome.alarms.create("queue",{periodInMinutes:1});
});
chrome.runtime.onStartup.addListener(()=>{
  void chrome.alarms.create("queue",{periodInMinutes:1});
  void pump().catch(console.error);
});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==="queue") void pump().catch(console.error);});
chrome.tabs.onUpdated.addListener((tabId,change,tab)=>{
  if(change.status!=="complete") return;
  try{marketplaceFor(tab.url||"");}catch{return;}
  void db("tasksForTab",{tabId}).then(async(tasks)=>{for(const task of tasks) await dispatch(task);}).catch(console.error);
});
chrome.tabs.onRemoved.addListener(tabId=>{
  void db("tasksForTab",{tabId}).then(async tasks=>{
    for(const t of tasks) await db("result",{taskId:t.id,token:t.token,error:"Рабочая вкладка закрыта",trusted:true});
    if(tasks.length) {await broadcast();kick();}
  }).catch(console.error);
});
const publicMethods = new Set(["stats","products","details","analogs","runs","runResults","watch","watchlist","alerts","errors","exportJSON","storage","backup","cleanup","report","localEvents"]);
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message.target!=="background" || sender.id!==chrome.runtime.id) return;
  void (async()=>{
    try {
      if(message.type==="task.result") {
        if(!sender.tab?.id || !sender.url) throw new Error("Результат без рабочей вкладки");
        marketplaceFor(sender.url);
        let result;
        try {result=await db("result",{taskId:message.taskId,token:message.token,tabId:sender.tab.id,data:message.data,error:message.error});}
        catch(error) {result=await db("result",{taskId:message.taskId,token:message.token,tabId:sender.tab.id,error:String(error)});}
        dispatching.delete(message.token);
        if(!result?.ignored){const task=await db("task",{id:message.taskId});await db("localEvent",{runId:task.run_id,stage:message.error?"page.error":task.kind==="listing"?"listing.collected":"product.parsed",data:message.error?{error:message.error}:task.kind==="listing"?{links:message.data.length}:{name:message.data.name}});}
        respond({ok:true,value:result});await broadcast();kick();return;
      }
      if(!sender.url?.startsWith(chrome.runtime.getURL(""))) throw new Error("Команда доступна только интерфейсу расширения");
      let result: any;
      if(message.type==="backend.request") {
        const config:any=await chrome.storage.local.get(["apiUrl","apiToken"]);
        const base=new URL(config.apiUrl||"http://127.0.0.1:8000");
        if(base.protocol!=="https:" && !(base.protocol==="http:" && ["127.0.0.1","localhost"].includes(base.hostname)))throw new Error("Для удалённого сервера нужен HTTPS");
        const {path,method="GET",body}=message.args;
        if(typeof path!=="string"||!/^\/(?:api\/v1\/|health\/)/.test(path)||path.includes("..")||path.includes("\\"))throw new Error("Неверный путь API");
        if(!["GET","POST"].includes(method))throw new Error("Неверный метод");
        const response=await fetch(new URL(path,base.origin),{method,headers:{"Authorization":`Bearer ${config.apiToken||"local-development-token"}`,"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000),credentials:"omit",redirect:"error"});
        const text=await response.text();let payload:any;try{payload=JSON.parse(text);}catch{throw new Error(`Сервер вернул не JSON (${response.status})`);}
        if(!response.ok)throw new Error(`HTTP ${response.status}: ${typeof payload.detail==="string"?payload.detail:JSON.stringify(payload.detail||payload)}`);
        result=payload;
      } else if(message.type==="start") {
        await ensureSession();
        const sites = message.args.site==="both" ? ["ozon","wb"] : [message.args.site];
        result=[];
        if(sites.length===2 && /^https?:/i.test(message.args.source)) throw new Error("Для URL выберите одну площадку");
        for(const site of sites) {
          if(!["ozon","wb"].includes(site)) throw new Error("Неизвестная площадка");
          result.push(await db("createRun",{...message.args,site,url:sourceUrl(message.args.source,site)}));
        }
        kick(0);
      } else if(message.type==="capture") {
        await ensureSession();
        const tab = (await chrome.tabs.query({active:true,lastFocusedWindow:true}))[0];
        let candidate = tab;
        // Called from the app tab: select the most recently used marketplace tab.
        if(!candidate?.url || candidate.url.startsWith("chrome-extension:")) candidate=(await chrome.tabs.query({})).filter(t=>{try{marketplaceFor(t.url||"");return true;}catch{return false;}}).sort((a,b)=>(b.lastAccessed||0)-(a.lastAccessed||0))[0];
        if(!candidate?.url) throw new Error("Откройте карточку товара в другой вкладке");
        const site=marketplaceFor(candidate.url);const card=productUrl(candidate.url,site);
        result=await db("createRun",{site,url:card.url,limit:1});kick(0);
      } else if(message.type==="focusRun") {
        const tasks=await db("tasks",{id:Number(message.args.id)});
        const owned=[...new Set<number>(tasks.map((t:any)=>t.tab_id).filter((id:any)=>typeof id==="number"))].reverse();
        let focused=false;
        for(const id of owned){const tab=await chrome.tabs.get(id).catch(()=>null);if(!tab?.url)continue;try{marketplaceFor(tab.url);}catch{continue;}await chrome.tabs.update(id,{active:true});await chrome.windows.update(tab.windowId,{focused:true});focused=true;break;}
        if(!focused)throw new Error("Рабочая вкладка уже закрыта. Продолжите задание для открытия новой.");
        result=null;
      } else if(message.type==="changeRun") {result=await db("changeRun",message.args);kick(0);}
      else if(message.type==="import") {
        const batches=Array.isArray(message.args)?message.args:[message.args];
        result=[];
        for(const batch of batches) result.push(await db("import",batch));
      } else if(message.type==="restore") {result=await db("restore",message.args);}
      else if(publicMethods.has(message.type)) result=await db(message.type,message.args);
      else throw new Error("Неизвестная команда");
      respond({ok:true,value:result ?? null});
      if(!["stats","products","details","analogs","runs","watchlist","alerts","errors","exportJSON","storage","backup"].includes(message.type)) await broadcast();
    } catch(error) {respond({ok:false,error:error instanceof Error?error.message:String(error)});}
  })();
  return true;
});
// Reconcile alarms even after an extension reload (which doesn't fire onStartup).
void chrome.alarms.create("queue",{periodInMinutes:1});
void chrome.storage.local.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"});
