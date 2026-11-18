import {searchContext,validOffer,type Offer,type Comparison} from './comparison.ts';
import {ozonComposerURL,ozonJSONOffers} from './ozon-session.ts';
import {wbOffers,wbSearchURL} from './wb-data.ts';
export {wbOffers,wbSearchURL} from './wb-data.ts';

async function marketplaceSession(job:Comparison,signal:AbortSignal):Promise<Offer[]>{
  const patterns=job.target==='ozon'?['https://www.ozon.ru/*','https://ozon.ru/*']:['https://www.wildberries.ru/*','https://wildberries.ru/*'];
  const messageTarget=job.target==='ozon'?'comparison-ozon-session':'comparison-wb-session';
  const tabs=(await chrome.tabs.query({url:patterns})).filter(tab=>tab.id!==job.originTab && !tab.discarded);
  tabs.sort((a,b)=>Number(searchContext(b.url||'')?.query===job.query)-Number(searchContext(a.url||'')?.query===job.query) || (b.lastAccessed||0)-(a.lastAccessed||0));
  if(!tabs.length)throw new Error(`Нет открытой вкладки ${job.target==='ozon'?'Ozon':'WB'}`);
  const tab=tabs[0],id=crypto.randomUUID();
  let abort:()=>void=()=>{};
  const cancelled=new Promise<never>((_,reject)=>{
    abort=()=>{void chrome.tabs.sendMessage(tab.id!,{target:messageTarget,id,cancel:true}).catch(()=>{});reject(new Error('Запрос отменён'));};
    if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});
  });
  try {
    signal.throwIfAborted();
    const result=await Promise.race([chrome.tabs.sendMessage(tab.id!,{target:messageTarget,id,query:job.query}),cancelled]);
    if(result?.error)throw new Error(result.error);
    if(!Array.isArray(result?.items) || result.items.length>5 || !result.items.length || !result.items.every((item:unknown)=>validOffer(item,job.target)))throw new Error('Вкладка площадки не вернула карточки');
    return result.items;
  }finally{signal.removeEventListener('abort',abort);}
}

async function request(url:string,signal:AbortSignal):Promise<Response>{
  const response=await fetch(url,{credentials:'include',redirect:'follow',signal});
  if(!response.ok)throw new Error(`Площадка ответила HTTP ${response.status}. Автоматический переход отключён; можно открыть поиск вручную.`);
  const host=new URL(response.url).hostname;
  if(!['www.ozon.ru','ozon.ru','www.wildberries.ru','wildberries.ru','search.wb.ru'].includes(host))throw new Error('Площадка направила запрос на другой домен. Автоматический переход отключён.');
  return response;
}
export async function searchHTTP(job:Comparison,signal:AbortSignal):Promise<Offer[]>{
  let apiError='';
  if(job.target==='ozon'){
    let sessionError='';
    try{return await marketplaceSession(job,signal);}catch(error){signal.throwIfAborted();sessionError=String(error instanceof Error?error.message:error);}
    // First-time use can work without an open session if Ozon permits HTTP.
    try {
      const response=await request(ozonComposerURL(job.searchUrl),signal);
      const items=ozonJSONOffers(await response.json());if(items.length)return items;
    }catch{signal.throwIfAborted();}
    apiError=`${sessionError}. `;
  }
  if(job.target==='wb'){
    try{return await marketplaceSession(job,signal);}catch(error){signal.throwIfAborted();apiError=String(error instanceof Error?error.message:error);}
    try {
      const response=await request(wbSearchURL(job.query),signal);
      const items=wbOffers(await response.json());
      if(items.length)return items;
      apiError='JSON выдачи WB не содержит товаров с ценами.';
    }catch(error){if(signal.aborted)throw error;apiError=String(error instanceof Error?error.message:error);}
  }
  let response:Response;
  try {response=await request(job.searchUrl,signal);}
  catch(error){
    if(job.target==='ozon' && !signal.aborted)throw new Error(`Ozon не разрешил прямой запрос. Откройте Ozon вручную в отдельной вкладке, пройдите проверку при необходимости и обновите ту вкладку после обновления расширения. Затем нажмите «Повторить» здесь. Вкладки не переключаются. ${apiError}`);
    throw error;
  }
  const html=await response.text();
  if(html.length>8_000_000)throw new Error('Ответ площадки слишком большой. Откройте поиск вручную.');
  const result=await chrome.tabs.sendMessage(job.originTab,{target:'comparison-parse',site:job.target,url:response.url,html});
  if(result?.error)throw new Error(result.error);
  if(!Array.isArray(result?.items) || !result.items.length)throw new Error(`${apiError?apiError+' ':''}Площадка не отдала готовые карточки без загрузки страницы. Автоматический переход отключён.`);
  if(result.items.length>5 || !result.items.every((item:unknown)=>validOffer(item,job.target)))throw new Error('Получен неверный формат карточек.');
  return result.items;
}
