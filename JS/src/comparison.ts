import {marketplaceFor, productUrl, sourceUrl, type Marketplace} from './domain.ts';

export type Offer = {name:string; url:string; price:string; priceNote:string};
export type Comparison = {
  mode?:'browser'|'backend';backendJobId?:string;phase?:string;
  id:string; originTab:number; workerTab?:number; query:string;
  source:Marketplace; target:Marketplace; searchUrl:string;
  status:'loading'|'done'|'error'; items:Offer[]; error?:string; updatedAt:number;
};
export const siteName = (site:Marketplace) => site === 'ozon' ? 'Ozon' : 'Wildberries';
export function searchContext(address:string):{site:Marketplace;query:string}|null {
  try {
    const url=new URL(address), site=marketplaceFor(address);
    if(url.protocol!=='https:' || url.username || url.password || url.port) return null;
    if(site==='ozon' && !/^\/(?:search\/?$|category\/)/.test(url.pathname)) return null;
    if(site==='wb' && !/^\/catalog\/0\/search\.aspx\/?$/.test(url.pathname)) return null;
    const query=(url.searchParams.get(site==='ozon'?'text':'search')||'').trim().replace(/\s+/g,' ');
    return query && query.length<=300 ? {site,query} : null;
  } catch {return null;}
}
export function partnerSearch(query:string,source:Marketplace):string {
  return sourceUrl(query,source==='ozon'?'wb':'ozon');
}
export function validOffer(value:unknown,site:Marketplace):value is Offer {
  const item=value as Offer;
  try {
    return !!item && typeof item.name==='string' && item.name.length>0 && item.name.length<=500 &&
      typeof item.price==='string' && /^\d{1,10}(?:\.\d{1,2})?$/.test(item.price) && Number(item.price)>0 &&
      typeof item.priceNote==='string' && item.priceNote.length<=200 &&
      productUrl(item.url,site).url===item.url;
  } catch {return false;}
}
