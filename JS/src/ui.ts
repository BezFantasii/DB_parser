import {decimal, marketplaceFor, type Marketplace} from "./domain.ts";
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const input = (id: string) => $<HTMLInputElement>(id);
const value = (id: string) => ($<HTMLInputElement | HTMLSelectElement>(id)).value;
export async function api(type: string, args: any = {}): Promise<any> {
  const response = await chrome.runtime.sendMessage({target:"background",type,args});
  if (!response?.ok) throw new Error(response?.error || "Расширение не ответило");
  return response.value;
}
const names: Record<string,string> = {products:"Товары",collect:"Новый сбор",runs:"Задания",watchlist:"Наблюдение",storage:"Хранилище",reports:"SQL-отчёты"};
const statuses: Record<string,string> = {running:"Выполняется",paused:"Пауза",blocked:"Проверка доступа",failed:"Ошибка",cancelled:"Отменён",succeeded:"Завершён"};
let current = "products", offset = 0, total = 0;
let refreshing = false;
function node(tag: string, text = "", className = ""): HTMLElement {
  const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;
}
function button(text: string, handler: ()=>unknown, cls=""): HTMLButtonElement {
  const b=node("button",text,cls) as HTMLButtonElement;
  b.onclick=()=>void action(async()=>{await handler();});return b;
}
function notify(text: string, error=false): void {$("notice").hidden=false;$("notice").textContent=text;$("notice").className=error?"error":"";}
async function action(fn:()=>Promise<unknown>): Promise<void> {try{await fn();}catch(error){notify(error instanceof Error?error.message:String(error),true);}}
function date(v: string | number | null): string {return v ? new Date(v).toLocaleString("ru-RU",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}) : "—";}
function money(v: number | null, currency="RUB"): string {return v===null || v===undefined?"Не определена":new Intl.NumberFormat("ru-RU",{style:"currency",currency,maximumFractionDigits:2}).format(v/100);}
function bytes(v: number): string {return v<1048576?`${(v/1024).toFixed(0)} КБ`:`${(v/1048576).toFixed(1)} МБ`;}
function tag(site: string): HTMLElement {return node("span",site==="ozon"?"Ozon":"Wildberries",`site-tag ${site}`);}
function siteLink(url: string,label: string): HTMLAnchorElement {
  const a=node("a",label,"detail-link") as HTMLAnchorElement;
  try{const u=new URL(url);marketplaceFor(u.href);if(u.protocol!=="https:")throw new Error();a.href=u.href;a.target="_blank";a.rel="noopener noreferrer";}catch{a.removeAttribute("href");}
  return a;
}
async function showPage(page: string): Promise<void> {
  current=names[page]?page:"products";
  document.querySelectorAll<HTMLElement>(".page").forEach(el=>{el.hidden=el.id!==`page-${current}`;});
  document.querySelectorAll<HTMLElement>("nav button").forEach(el=>el.classList.toggle("active",el.dataset.page===current));
  $("breadcrumb").textContent=names[current];location.hash=current;
  await refresh();
}
function filters(): any {return {search:value("search"),site:value("site-filter"),connection_type:value("connection-filter"),maxPrice:value("max-price"),anc:input("filter-anc").checked,microphone:input("filter-mic").checked,inStock:input("filter-stock").checked,offset,limit:50};}
async function products(): Promise<void> {
  const result=await api("products",filters());total=result.total;
  const tbody=$("products-body");tbody.replaceChildren();
  for(const p of result.items) {
    const row=node("tr");const title=node("td");title.append(node("strong",p.name),node("small",`${p.brand||"Без бренда"} · ${p.external_id}`));
    const site=node("td");site.append(tag(p.marketplace));
    const price=node("td");price.append(node("strong",money(p.price_minor,p.currency)),node("small",`${p.price_kind==="unknown"?"Условие цены неизвестно":p.price_kind} · ${p.region||"unknown"}`));
    const rating=node("td",p.rating===null||p.rating===undefined?"—":`★ ${p.rating}`);rating.append(node("small",p.reviews_count===null?"Нет данных об отзывах":`${p.reviews_count} отзывов`));
    const observed=node("td",date(p.observed_at));observed.append(node("small",p.availability==="out_of_stock"?"Нет в наличии":p.availability==="in_stock"?"В наличии":"Наличие неизвестно"));
    const controls=node("td");controls.append(button("Открыть",()=>details(p.id),"quiet"));
    row.append(title,site,price,rating,observed,controls);tbody.append(row);
  }
  $("empty").hidden=total>0;
  $("product-count").textContent=total?`${offset+1}–${Math.min(offset+50,total)} из ${total} предложений` : "Нет предложений по выбранным условиям";
  $<HTMLButtonElement>("prev").disabled=offset===0;$<HTMLButtonElement>("next").disabled=offset+50>=total;
}
async function runs(): Promise<void> {
  const items=await api("runs");const root=$("runs-list");root.replaceChildren();
  if(!items.length) root.append(node("p","Заданий пока нет. Создайте первый сбор.","muted"));
  const active=items.filter((r:any)=>r.status==="running").length;$("run-badge").textContent=active?String(active):"";
  for(const r of items) {
    const card=node("article","","panel run-card"),head=node("div","","run-title");
    head.append(tag(r.marketplace),node("strong",`Сбор #${r.id}`),node("span",statuses[r.status]||r.status,`pill ${r.status}`));
    const progress=document.createElement("progress");progress.max=r.total||1;progress.value=r.done||0;
    card.append(head,node("p",r.source_url,"source-text"),progress,node("p",`${r.done||0} / ${r.total} шагов · ${r.staged} карточек в черновике · ${date(r.created_at)}`));
    if(r.error)card.append(node("p",r.error));
    const actions=node("div","","actions");
    if(r.status!=="succeeded")actions.append(button("Рабочая вкладка ↗",()=>api("focusRun",{id:r.id})));
    if(r.status==="running")actions.append(button("Пауза",async()=>{await api("changeRun",{id:r.id,action:"pause"});await refresh();}));
    if(["paused","failed","blocked"].includes(r.status))actions.append(button("Продолжить",async()=>{await api("changeRun",{id:r.id,action:"resume"});await refresh();},"primary"));
    if(!["succeeded","cancelled"].includes(r.status))actions.append(button("Отменить",async()=>{await api("changeRun",{id:r.id,action:"cancel"});await refresh();}));
    card.append(actions);root.append(card);
  }
  const errors=await api("errors");$("errors-list").replaceChildren(...errors.map((e:any)=>node("div",`${date(e.created_at)} · Сбор #${e.run_id}: ${e.message}`,"log")));
}
async function watchlist(): Promise<void> {
  const rows=await api("watchlist");const root=$("watch-list");root.replaceChildren();
  if(!rows.length)root.append(node("p","Пока нет товаров под наблюдением.","muted"));
  for(const w of rows){const card=node("article","","panel run-card");card.append(tag(w.marketplace),node("h2",w.name),node("p",`Каждые ${w.interval_minutes} мин. · Следующая проверка: ${date(w.next_at)}`),button("Убрать из наблюдения",async()=>{await api("watch",{id:w.product_id,minutes:0});await refresh();}));root.append(card);}
  const alerts=await api("alerts");$("alerts-list").replaceChildren(...alerts.map((a:any)=>node("p",`${date(a.created_at)} · ${a.message}`)));
  if(!alerts.length)$("alerts-list").append(node("p","Подтверждённых снижений пока нет.","muted"));
}
async function storage(stats:any): Promise<void> {
  const estimate=await api("storage");
  const settings: any=await chrome.storage.local.get(["lastBackup"]);
  const rows=[["Движок",stats.backend],["Размер SQLite",bytes(stats.bytes)],["Использование хранилища",bytes(estimate.usage||0)],["Товаров / наблюдений",`${stats.products} / ${stats.observations}`],["Версия схемы",String(stats.schema)],["Последний экспорт SQLite",settings.lastBackup?date(settings.lastBackup):"Ещё не выполнялся"]];
  $("storage-info").replaceChildren(...rows.flatMap(([key,v])=>[node("dt",key),node("dd",v)]));
}
async function refresh(): Promise<void> {
  if(refreshing)return;refreshing=true;
  try {
    const stats=await api("stats");
    $("stat-products").textContent=String(stats.products);$("stat-observations").textContent=String(stats.observations);$("stat-watching").textContent=String(stats.watching);$("stat-size").textContent=bytes(stats.bytes);$("db-state").textContent="База подключена · OPFS";
    if(current==="products")await products();else if(current==="runs")await runs();else if(current==="watchlist")await watchlist();else if(current==="storage")await storage(stats);
  } finally{refreshing=false;}
}
async function details(id:number): Promise<void> {
  const {product:p,history}=await api("details",{id});
  if(!p)throw new Error("Товар не найден");
  const root=$("detail-body");root.replaceChildren(tag(p.marketplace),node("h2",p.name),siteLink(p.url,"Открыть на площадке ↗"));
  const grid=node("div","","details-grid");
  const labels:Record<string,string>={connection_type:"Подключение",form_factor:"Форм-фактор",anc:"ANC",microphone:"Микрофон",battery_hours:"Время работы, ч",brand:"Бренд"};
  const values:Record<string,string>={bluetooth:"Bluetooth",wired:"Проводные",radio:"Радиоканал",over_ear:"Полноразмерные",on_ear:"Накладные",in_ear:"Вкладыши"};
  for(const [key,label] of Object.entries(labels)) {const cell=node("div");const v=p[key];cell.append(node("small",label),node("strong",v===null?"Неизвестно":key==="anc"||key==="microphone"?(v?"Да":"Нет"):values[v]||String(v)));grid.append(cell);}
  root.append(node("p",`ID в локальной базе: ${p.id}`,"muted"),grid);
  const controls=node("div","","actions");
  controls.append(button("Обновить цену",async()=>{await api("start",{site:p.marketplace,source:p.url,limit:1});notify("Задание обновления создано");}),button("Наблюдать каждые 60 минут",async()=>{await api("watch",{id,minutes:60});notify("Товар добавлен в наблюдение");await refresh();}));
  root.append(controls,node("h2","История цены"));
  const contexts=[...new Set<string>(history.map((h:any)=>JSON.stringify([h.currency,h.region,h.price_kind])))];
  const select=document.createElement("select");
  for(const context of contexts){const option=document.createElement("option");option.value=context;option.textContent=JSON.parse(context).join(" · ");select.append(option);}
  const chart=node("div"),historyWrap=node("div","","history-wrap");
  const renderHistory=()=>{
    const subset=history.filter((h:any)=>JSON.stringify([h.currency,h.region,h.price_kind])===select.value);
    chart.replaceChildren();const points=subset.filter((h:any)=>h.price_minor!==null).reverse();
    if(points.length>1){
      const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg");svg.classList.add("chart");svg.setAttribute("viewBox","0 0 800 160");svg.setAttribute("role","img");svg.setAttribute("aria-label","График сохранённых цен одного контекста");
      const min=Math.min(...points.map((h:any)=>h.price_minor)),max=Math.max(...points.map((h:any)=>h.price_minor));
      const line=document.createElementNS(ns,"polyline");line.setAttribute("points",points.map((h:any,i:number)=>`${20+i*760/(points.length-1)},${135-(h.price_minor-min)*110/(max-min||1)}`).join(" "));line.setAttribute("fill","none");line.setAttribute("stroke","#305df5");line.setAttribute("stroke-width","3");svg.append(line);chart.append(svg);
    }else chart.append(node("p","Для графика нужны два наблюдения с ценой в одинаковых условиях.","muted"));
    const table=document.createElement("table");const header=node("tr");for(const h of ["Дата","Цена","Наличие","Рейтинг"])header.append(node("th",h));const thead=document.createElement("thead");thead.append(header);table.append(thead);const tbody=document.createElement("tbody");
    for(const h of subset){const tr=node("tr");tr.append(node("td",date(h.observed_at)),node("td",money(h.price_minor,h.currency)),node("td",h.availability),node("td",h.rating===null?"—":String(h.rating)));tbody.append(tr);}table.append(tbody);historyWrap.replaceChildren(table);
  };
  select.onchange=renderHistory;root.append(select,chart,historyWrap);renderHistory();
  root.append(node("h2","Подходящие аналоги с другой площадки"),node("p","Совпадают подтверждённые подключение и форм-фактор. Это не подтверждение идентичности модели; цены разных условий напрямую не сравниваются.","muted"));
  const analogOptions=node("div","","actions");
  const ancInput=document.createElement("input");ancInput.type="checkbox";const micInput=document.createElement("input");micInput.type="checkbox";
  const ancLabel=node("label");ancLabel.append(ancInput,document.createTextNode(" Требовать ANC"));const micLabel=node("label");micLabel.append(micInput,document.createTextNode(" Требовать микрофон"));analogOptions.append(ancLabel,micLabel);
  const analogRoot=node("div");
  const renderAnalogs=async()=>{const rows=await api("analogs",{id,anc:ancInput.checked,microphone:micInput.checked});analogRoot.replaceChildren();for(const a of rows){const item=node("p");item.append(tag(a.marketplace),document.createTextNode(` ${a.name} · ${money(a.price_minor,a.currency)} · ${a.region||"unknown"} / ${a.price_kind||"unknown"} `),siteLink(a.url,"Открыть ↗"));analogRoot.append(item);}if(!rows.length)analogRoot.append(node("p","Подтверждённых аналогов в локальной коллекции не найдено.","muted"));};
  ancInput.onchange=()=>void action(renderAnalogs);micInput.onchange=()=>void action(renderAnalogs);root.append(analogOptions,analogRoot);await renderAnalogs();
  const dialog=$<HTMLDialogElement>("detail");if(!dialog.open)dialog.showModal();
}
function download(url:string,filename:string):void {const a=document.createElement("a");a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();}
function downloadBlob(blob:Blob,filename:string):void {const url=URL.createObjectURL(blob);download(url,filename);setTimeout(()=>URL.revokeObjectURL(url),60000);}
const filename=(ext:string)=>`marketplace-${new Date().toISOString().slice(0,10)}.${ext}`;
async function importJSON(file:File):Promise<void>{
  if(file.size>20*1024*1024)throw new Error("JSON должен быть не больше 20 МБ; разделите большой файл на пакеты");
  let payload=JSON.parse(await file.text());
  if(Array.isArray(payload)&&payload.length&&payload[0]?.url){
    const grouped=new Map<Marketplace,any[]>();for(const item of payload){const site=marketplaceFor(item.url);grouped.set(site,[...(grouped.get(site)||[]),item]);}
    payload=[...grouped].flatMap(([marketplace,items])=>{const batches=[];for(let i=0;i<items.length;i+=500)batches.push({marketplace,source_url:file.name,items:items.slice(i,i+500)});return batches;});
  }
  // Exports can contain more than 500 rows per marketplace; preserve atomicity of each bounded batch.
  if(!Array.isArray(payload))payload=[payload];
  payload=payload.flatMap((b:any)=>Array.isArray(b.items)&&b.items.length>500?Array.from({length:Math.ceil(b.items.length/500)},(_,i)=>({...b,items:b.items.slice(i*500,(i+1)*500)})):[b]);
  const result=await api("import",payload);notify(`Импортировано наблюдений: ${result.reduce((n:number,b:any)=>n+b.saved,0)}. Каждый пакет записан транзакционно.`);await refresh();
}
document.querySelectorAll<HTMLElement>("nav button").forEach(el=>el.onclick=()=>void action(()=>showPage(el.dataset.page!)));
for(const id of ["new-collect","empty-collect"])$(id).onclick=()=>void action(()=>showPage("collect"));
$("refresh").onclick=()=>void action(refresh);
$("filters").onsubmit=e=>{e.preventDefault();offset=0;void action(async()=>{await chrome.storage.local.set({filters:filters()});await products();});};
$("prev").onclick=()=>{offset=Math.max(0,offset-50);void action(products);};$("next").onclick=()=>{offset+=50;void action(products);};
$("collect-form").onsubmit=e=>{e.preventDefault();void action(async()=>{const args={source:value("collect-source"),site:value("collect-site"),limit:Number(value("collect-limit")),pages:Number(value("collect-pages")),scrolls:Number(value("collect-scrolls")),delay:Number(value("collect-delay"))};await api("start",args);await chrome.storage.local.set({lastCollection:args});notify("Задания созданы. Рабочая вкладка откроется автоматически.");await showPage("runs");});};
$("capture").onclick=()=>void action(async()=>{await api("capture");notify("Создано задание для открытой карточки");await showPage("runs");});
for(const id of ["empty-import","import-json"])$(id).onclick=()=>input("json-file").click();
input("json-file").onchange=()=>void action(async()=>{const file=input("json-file").files?.[0];if(file)await importJSON(file);input("json-file").value="";});
$("backup").onclick=()=>void action(async()=>{const result=await api("backup");download(result.url,filename("sqlite"));await chrome.storage.local.set({lastBackup:new Date().toISOString()});notify("Резервная копия подготовлена к скачиванию. Проверьте сохранённый файл.");await refresh();});
$("export-json").onclick=()=>void action(async()=>{downloadBlob(new Blob([JSON.stringify(await api("exportJSON"),null,2)],{type:"application/json"}),filename("json"));});
$("export-csv").onclick=()=>void action(async()=>{
  const batches=await api("exportJSON");const rows=[["marketplace","external_id","name","url","price","currency","region","price_kind","availability","observed_at"]];
  for(const b of batches)for(const p of b.items)rows.push([b.marketplace,p.external_id,p.name,p.url,p.price??"",p.currency,p.region,p.price_kind,p.availability,p.observed_at]);
  // Protect spreadsheet formulas as well as CSV delimiters.
  const csv=rows.map(r=>r.map((v:any)=>`"${String(/^[=+@\-\t\r]/.test(String(v))?`'${v}`:v).replaceAll('"','""')}"`).join(";")).join("\r\n");downloadBlob(new Blob(["\uFEFF",csv],{type:"text/csv;charset=utf-8"}),filename("csv"));
});
$("restore").onclick=()=>{if(!input("restore-confirm").checked){notify("Подтвердите замену данных флажком",true);return;}input("sqlite-file").click();};
input("sqlite-file").onchange=()=>void action(async()=>{
  const file=input("sqlite-file").files?.[0];if(!file)return;if(file.size>200*1024*1024)throw new Error("Восстановление через интерфейс ограничено 200 МБ");
  const url=URL.createObjectURL(file);try{const result=await api("restore",{url});download(result.backupUrl,`before-restore-${filename("sqlite")}`);notify("База восстановлена. Предыдущая версия подготовлена к скачиванию.");await refresh();}finally{URL.revokeObjectURL(url);input("sqlite-file").value="";input("restore-confirm").checked=false;}
});
$("cleanup").onclick=()=>void action(async()=>{await api("cleanup");notify("Ошибки старше 30 дней и отменённые черновики очищены");await refresh();});
$("report-form").onsubmit=e=>{e.preventDefault();void action(async()=>{
  const rows=await api("report",{...filters(),code:value("report-code"),id:Number(value("report-id")),days:Number(value("report-days"))});
  const root=$("report-result");root.replaceChildren();if(!rows.length){root.append(node("p","По этим условиям данных нет.","muted"));return;}
  const table=document.createElement("table"),head=document.createElement("thead"),tr=node("tr");const keys=Object.keys(rows[0]);for(const k of keys)tr.append(node("th",k));head.append(tr);table.append(head);const body=document.createElement("tbody");for(const row of rows){const tr=node("tr");for(const k of keys)tr.append(node("td",row[k]===null?"—":String(row[k])));body.append(tr);}table.append(body);root.append(table);
});};
$("close-detail").onclick=()=>$<HTMLDialogElement>("detail").close();
chrome.runtime.onMessage.addListener(message=>{if(message.target==="ui"&&message.type==="changed")void action(refresh);});
window.addEventListener("hashchange",()=>{const p=location.hash.slice(1);if(p!==current)void action(()=>showPage(p));});
setInterval(()=>{if(document.visibilityState==="visible"&&current==="runs")void action(refresh);},5000);
void action(async()=>{
  const saved: any=await chrome.storage.local.get(["filters","lastCollection"]);
  if(saved.filters){const f=saved.filters;input("search").value=f.search||"";($<HTMLSelectElement>("site-filter")).value=f.site||"";($<HTMLSelectElement>("connection-filter")).value=f.connection_type||"";input("max-price").value=f.maxPrice||"";input("filter-anc").checked=!!f.anc;input("filter-mic").checked=!!f.microphone;input("filter-stock").checked=!!f.inStock;}
  if(saved.lastCollection)for(const key of ["source","site","limit","pages","scrolls","delay"])($<HTMLInputElement>(`collect-${key}`)).value=String(saved.lastCollection[key]??"");
  await showPage(location.hash.slice(1)||"products");
});
