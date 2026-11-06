const $=<T extends HTMLElement=HTMLElement>(id:string)=>document.getElementById(id) as T;
const value=(id:string)=>($<HTMLInputElement>(id)).value;
let mode="backend",selected:string|number|null=null,shown:any[]=[],busy=false;
let eventCursor=0,eventLines:string[]=[],loadedResults="",epoch=0;
let connectionSequence=0;
const statuses:Record<string,string>={queued:"В очереди",running:"Выполняется",succeeded:"Завершено",failed:"Ошибка",blocked:"Доступ ограничен",cancelled:"Отменено",paused:"Пауза"};
async function rpc(type:string,args:any={}):Promise<any>{const r=await chrome.runtime.sendMessage({target:"background",type,args});if(!r?.ok)throw new Error(r?.error||"Нет ответа от расширения");return r.value;}
async function http(path:string,method="GET",body?:unknown):Promise<any>{return rpc("backend.request",{path,method,body});}
function notice(text:string,error=false){$("notice").hidden=false;$("notice").textContent=text;$("notice").className=error?"error":"";}
async function action(fn:()=>Promise<unknown>){try{await fn();}catch(e){notice(e instanceof Error?e.message:String(e),true);}}
const el=(tag:string,text="",cls="")=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
function button(text:string,fn:()=>Promise<unknown>){const b=el("button",text);b.onclick=()=>void action(fn);return b;}
function resetSelection(){selected=null;eventCursor=0;eventLines=[];loadedResults="";$("selected").textContent="Выберите задание";$("events").textContent="Здесь появятся этапы получения данных.";}
function renderData(rows:any[],description:string){
  shown=rows;$("data-description").textContent=description;
  const body=$("results");body.replaceChildren();
  for(const row of rows){const p=row.data||row;const tr=el("tr");
    const site=row.marketplace||p.marketplace||"—";
    const name=el("td");const link=el("a",p.name||"Без названия") as HTMLAnchorElement;
    try{const u=new URL(p.url);if(u.protocol==="https:"&&["ozon.ru","www.ozon.ru","wildberries.ru","www.wildberries.ru"].includes(u.hostname)){link.href=u.href;link.target="_blank";link.rel="noopener noreferrer";}}catch{}
    name.append(link);
    const price=p.price!==undefined?p.price:row.price_minor===null?null:(row.price_minor/100).toFixed(2);
    const priceCell=el("td",price===null||price===undefined?"Не определена":`${price} ${p.currency||row.currency||"RUB"}`);priceCell.append(el("small",`${p.price_kind||row.price_kind||"unknown"} / ${p.region||row.region||"unknown"}`));
    const date=p.observed_at||row.observed_at;const origin=el("td",p.data_source||"Локальный DOM");origin.append(el("small",date?new Date(date).toLocaleString("ru-RU"):"—"));
    tr.append(el("td",`${site} / ${p.external_id||row.external_id||"—"}`),name,priceCell,el("td",`${p.rating??row.rating??"—"} / ${p.reviews_count??row.reviews_count??"—"}`),origin,el("td",JSON.stringify(p.features||{connection_type:row.connection_type,form_factor:row.form_factor,anc:row.anc,microphone:row.microphone})));
    body.append(tr);
  }
  if(!rows.length){const tr=el("tr"),td=el("td","Данных пока нет.") as HTMLTableCellElement;td.colSpan=6;tr.append(td);body.append(tr);}
}
async function connect(){
  const sequence=++connectionSequence;
  $("db-state").dataset.ready="false";$("db-state").textContent="Проверка подключения…";
  if(mode==="backend"){const health=await http("/health/ready");await http("/api/v1/marketplaces");if(sequence!==connectionSequence)return;$("db-state").textContent=`Backend подключён · PostgreSQL · workers: ${health.workers_online}`;$("mode-description").textContent="Python-парсер работает на сервере. Закрытие расширения не останавливает задание. Данные сохраняются в PostgreSQL.";}
  else {await rpc("stats");if(sequence!==connectionSequence)return;$("db-state").textContent="SQLite OPFS подключена";$("mode-description").textContent="JavaScript-парсер работает в вкладках этого браузера. Он переносит извлечение данных из Python, но не запускает Selenium или undetected-chromedriver.";}
  $("db-state").dataset.ready="true";await refresh();
}
async function saveConfig(){
  const u=new URL(value("api-url"));if(u.username||u.password||u.pathname!=="/"||u.search||u.hash)throw new Error("Укажите только origin API, например http://127.0.0.1:8000");
  if(u.protocol!=="https:"&&!(u.protocol==="http:"&&["127.0.0.1","localhost"].includes(u.hostname)))throw new Error("Для удалённого API нужен HTTPS");
  if(u.protocol==="https:"&&!await chrome.permissions.request({origins:[`${u.origin}/*`]}))throw new Error("Не предоставлен доступ к адресу backend");
  await chrome.storage.local.set({apiUrl:u.origin,apiToken:value("api-token")});notice("Подключение сохранено");await connect();
}
async function listJobs():Promise<any[]>{return mode==="backend"?(await http("/api/v1/jobs?limit=50")).items:await rpc("runs");}
async function refresh(){
  if(busy)return;busy=true;const turn=epoch;
  try{
    const jobs=await listJobs();if(turn!==epoch)return;
    const root=$("jobs");root.replaceChildren();
    for(const job of jobs){const row=el("div","",`job ${String(job.id)===String(selected)?"selected":""}`);const info=el("div");
      const title=el("strong",`${job.marketplace} · ${String(job.id).slice(0,8)} · ${job.mode||"local"}`);title.append(el("span",statuses[job.status]||job.status,`status ${job.status}`));
      info.append(title,el("small",job.source_url));
      if(job.error)info.append(el("small",job.error,"error"));
      info.append(el("small",mode==="local"?`${job.done||0}/${job.total} шагов · черновик ${job.staged}`:`Записано: ${job.saved}`));
      const controls=el("div");controls.append(button("Процесс и данные",async()=>{epoch++;selected=job.id;eventCursor=0;eventLines=[];loadedResults="";$("selected").textContent=String(job.id);renderData([],"Ожидание результатов выбранного задания.");await refreshSelected(job);}));
      if(mode==="backend"){
        if(["queued","running"].includes(job.status))controls.append(button("Отменить",async()=>{await http(`/api/v1/jobs/${job.id}/cancel`,"POST");await refresh();}));
        if(["failed","blocked","cancelled"].includes(job.status))controls.append(button("Повторить",async()=>{await http(`/api/v1/jobs/${job.id}/retry`,"POST");await refresh();}));
      }else{
        if(job.status==="running")controls.append(button("Пауза",async()=>{await rpc("changeRun",{id:job.id,action:"pause"});await refresh();}));
        if(["paused","failed","blocked"].includes(job.status))controls.append(button("Продолжить",async()=>{await rpc("changeRun",{id:job.id,action:"resume"});await refresh();}));
        controls.append(button("Вкладка",async()=>rpc("focusRun",{id:job.id})));
        if(!["succeeded","cancelled"].includes(job.status))controls.append(button("Отменить",async()=>{await rpc("changeRun",{id:job.id,action:"cancel"});await refresh();}));
      }
      row.append(info,controls);root.append(row);
    }
    if(!jobs.length)root.append(el("p","Заданий пока нет."));
    if(selected===null&&jobs.length){selected=jobs[0].id;$("selected").textContent=String(selected);}
    const job=jobs.find(j=>String(j.id)===String(selected));if(job)await refreshSelected(job);
  }finally{busy=false;}
}
async function refreshSelected(job:any){
  const e=epoch;
  const events=mode==="backend"?(await http(`/api/v1/jobs/${job.id}/events?after_id=${eventCursor}`)).items:await rpc("localEvents",{runId:job.id,after:eventCursor});
  if(e!==epoch)return;
  for(const event of events){eventCursor=Math.max(eventCursor,event.id);let data=event.data;try{if(typeof data==="string")data=JSON.parse(data);}catch{}eventLines.push(`${new Date(event.created_at).toLocaleTimeString("ru-RU")}  ${event.stage}  ${JSON.stringify(data)}`);}
  const lines=[...eventLines,`\nСостояние: ${statuses[job.status]||job.status}${job.error?`\nОшибка: ${job.error}`:""}`];$("events").textContent=lines.join("\n");$("events").scrollTop=$("events").scrollHeight;
  if(job.status==="succeeded"&&loadedResults!==`${mode}:${job.id}`){
    if(mode==="backend"){const r=await http(`/api/v1/jobs/${job.id}/results`);if(e!==epoch)return;renderData(r.items.map((x:any)=>({...x,marketplace:job.marketplace})),`Результаты задания ${job.id}. Источник: ${job.mode}.`);}
    else {const rows=await rpc("runResults",{id:job.id});if(e!==epoch)return;renderData(rows,`Сохранённые результаты локального задания ${job.id}.`);}
    loadedResults=`${mode}:${job.id}`;
  }
}
$("save-config").onclick=()=>void action(saveConfig);$("connect").onclick=()=>void action(connect);$("refresh").onclick=()=>void action(refresh);
$("mode").onchange=()=>void action(async()=>{mode=value("mode");epoch++;busy=false;resetSelection();renderData([],"Выберите задание или загрузите сохранённые товары.");$("backend-config").hidden=mode!=="backend";$("fixture-label").hidden=mode!=="backend";await chrome.storage.local.set({clientMode:mode});await connect();});
$("start-form").onsubmit=e=>{e.preventDefault();void action(async()=>{
  const start=$<HTMLButtonElement>("start");start.disabled=true;
  try{const site=value("site"),source=value("source"),limit=Number(value("limit")),pages=Number(value("pages"));
    if(site==="both"&&/^https?:/i.test(source))throw new Error("Для URL выберите одну площадку");
    if(mode==="backend")for(const marketplace of site==="both"?["ozon","wb"]:[site])await http("/api/v1/jobs","POST",{marketplace,source,limit,pages,mode:$<HTMLInputElement>("fixture").checked?"fixture":"live"});
    else await rpc("start",{site,source,limit,pages,scrolls:3,delay:2});
    resetSelection();notice("Задание создано. Ниже отображаются этапы работы.");await refresh();
  }finally{start.disabled=false;}
});};
$("load-products").onclick=()=>void action(async()=>{if(mode==="backend")renderData((await http("/api/v1/products?limit=500")).items,"Последние наблюдения PostgreSQL, до 500 предложений.");else renderData((await rpc("products",{limit:500})).items,"Последние наблюдения локальной SQLite, до 500 предложений.");});
$("export").onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(shown,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="parser-results.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);};
setInterval(()=>{if(document.visibilityState==="visible")void action(refresh);},2000);
void action(async()=>{const saved:any=await chrome.storage.local.get(["clientMode","apiUrl","apiToken"]);mode=saved.clientMode||"backend";$<HTMLSelectElement>("mode").value=mode;$<HTMLInputElement>("api-url").value=saved.apiUrl||"http://127.0.0.1:8000";$<HTMLInputElement>("api-token").value=saved.apiToken||"";$("backend-config").hidden=mode!=="backend";$("fixture-label").hidden=mode!=="backend";document.body.dataset.initialized="true";await connect();});
