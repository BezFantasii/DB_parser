import {validOffer,type Comparison,type Offer} from './comparison.ts';
export type BackendConfig={mode:'browser'|'backend';url:string;token:string};
export const defaultBackend:BackendConfig={mode:'browser',url:'http://127.0.0.1:8000',token:''};
export function backendOrigin(address:string):string{
  const url=new URL(address);
  if(url.username || url.password || url.search || url.hash || url.pathname!=='/')throw new Error('Укажите адрес сервера без пути, логина и параметров');
  if(url.protocol!=='https:' && !(url.protocol==='http:' && ['localhost','127.0.0.1','[::1]'].includes(url.hostname)))throw new Error('Для удалённого backend нужен HTTPS');
  return url.origin;
}
export async function backendRequest(config:BackendConfig,path:string,signal:AbortSignal,body?:unknown):Promise<any>{
  if(!/^\/(?:health\/ready|api\/v1\/marketplaces|api\/v1\/jobs(?:\/[0-9a-f-]+(?:\/results|\/cancel)?)?)$/.test(path))throw new Error('Неверная ручка backend');
  const response=await fetch(backendOrigin(config.url)+path,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${config.token||'local-development-token'}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),credentials:'omit',redirect:'error',signal});
  const payload=await response.json().catch(()=>{throw new Error(`Backend вернул не JSON (HTTP ${response.status})`);});
  if(!response.ok)throw new Error(`Backend HTTP ${response.status}: ${typeof payload.detail==='string'?payload.detail:'ошибка запроса'}`);
  return payload;
}
export function backendOffers(rows:any[],job:Comparison):Offer[]{
  if(!Array.isArray(rows))throw new Error('Backend вернул неверный список товаров');
  const items:Offer[]=[];
  for(const row of rows){
    const product=row?.data;
    if(!product || product.price===null || product.price===undefined || (product.currency && product.currency!=='RUB'))continue;
    const item:Offer={name:product.name,url:product.url,price:String(product.price),priceNote:product.price_kind==='card'?'Backend · цена с картой площадки':'Backend · условия цены и доставки уточняйте в карточке'};
    if(!validOffer(item,job.target))throw new Error('Backend вернул неверную цену или ссылку на другую площадку');
    items.push(item);if(items.length===5)break;
  }
  return items;
}
function pause(signal:AbortSignal):Promise<void>{
  return new Promise((resolve,reject)=>{
    const abort=()=>{clearTimeout(timer);reject(new Error('Запрос отменён'));};
    const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},1000);
    if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});
  });
}
export async function searchBackend(job:Comparison,config:BackendConfig,signal:AbortSignal,progress:(id:string,phase:string)=>Promise<void>):Promise<Offer[]>{
  let id=job.backendJobId,complete=false;
  try{
    if(!id){
      const created=await backendRequest(config,'/api/v1/jobs',signal,{marketplace:job.target,source:job.query,limit:5,pages:1,scrolls:2,delay:1,timeout:30,engine:job.target==='ozon'?'chrome-session':'selenium'});
      id=created.id;
    }
    if(typeof id!=='string' || !/^[0-9a-f-]{36}$/.test(id))throw new Error('Backend не вернул корректный ID задания');
    await progress(id,'Задание отправлено на сервер');
    while(true){
      signal.throwIfAborted();
      const current=await backendRequest(config,`/api/v1/jobs/${id}`,signal);
      if(current.marketplace!==job.target || current.mode!=='live')throw new Error('Backend вернул задание другой площадки или учебные данные');
      if(current.status==='succeeded'){
        complete=true;
        const result=await backendRequest(config,`/api/v1/jobs/${id}/results`,signal);
        if(result.job?.id!==id || result.job?.mode!=='live' || result.job?.marketplace!==job.target)throw new Error('Backend вернул результаты другого задания');
        const items=backendOffers(result.items,job);if(!items.length)throw new Error('Backend завершил сбор без товаров с ценами');return items;
      }
      if(['failed','blocked','cancelled'].includes(current.status)){complete=true;throw new Error(`Backend: ${current.error||current.status}`);}
      await progress(id,current.status==='queued'?'Backend: задание в очереди':'Backend: сервер получает и сохраняет товары');
      await pause(signal);
    }
  }finally{
    if(id && !complete)await backendRequest(config,`/api/v1/jobs/${id}/cancel`,AbortSignal.timeout(5000),{}).catch(()=>{});
  }
}
