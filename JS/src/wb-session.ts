import {searchContext,type Offer} from './comparison.ts';
import {listingOffers} from './listing.ts';
import {checkBlocked} from './parser.ts';
import {wbOffers,wbSearchURL} from './wb-data.ts';

export function observedWBSearch(entries:string[],query:string):string|null {
  for(const name of [...entries].reverse()){
    try{
      const url=new URL(name);
      if(url.protocol!=='https:' || !['search.wb.ru','u-search.wb.ru'].includes(url.hostname) || url.port || url.username || url.password || !/^\/exactmatch\/ru\/common\/v\d+\/search\/?$/.test(url.pathname))continue;
      // Preserve only catalog protocol and regional settings, never arbitrary
      // query parameters/tokens from a resource URL.
      const next=new URL(url.origin+url.pathname);
      for(const key of ['appType','dest','lang','spp','resultset','sort','suppressSpellcheck','ab_testing'])if(url.searchParams.has(key))next.searchParams.set(key,url.searchParams.get(key)!);
      next.searchParams.set('query',query);next.searchParams.set('page','1');next.searchParams.set('curr','rub');
      return next.href;
    }catch{}
  }
  return null;
}
export async function searchFromWBPage(query:string,signal:AbortSignal):Promise<Offer[]>{
  if(location.protocol!=='https:' || !['wildberries.ru','www.wildberries.ru'].includes(location.hostname))throw new Error('Нужна открытая вкладка WB');
  if(typeof query!=='string' || !query.trim() || query.length>300)throw new Error('Неверный запрос');
  const context=searchContext(location.href);
  if(context?.site==='wb' && context.query===query){checkBlocked(document);const items=listingOffers(document,location.href,'wb');if(items.length)return items;}
  const observed=observedWBSearch(performance.getEntriesByType('resource').map(entry=>entry.name),query);
  const errors:string[]=[];
  for(const endpoint of [...new Set([observed,wbSearchURL(query)].filter((v):v is string=>!!v))]){
    signal.throwIfAborted();
    try{
      const response=await fetch(endpoint,{credentials:'include',signal,redirect:'error'});
      if(!response.ok)throw new Error(`WB HTTP ${response.status}`);
      const items=wbOffers(await response.json());if(items.length)return items;
      errors.push('JSON не содержит цен');
    }catch(error){signal.throwIfAborted();errors.push(String(error instanceof Error?error.message:error));}
  }
  throw new Error(`WB не вернул выдачу из открытой вкладки: ${errors.join('; ')}. Нужен ответ поискового запроса из Network для проверки формата.`);
}
