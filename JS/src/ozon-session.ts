import {productUrl} from './domain.ts';
import {searchContext,validOffer,type Offer} from './comparison.ts';
import {listingOffers} from './listing.ts';
import {checkBlocked} from './parser.ts';

export function ozonComposerURL(searchURL:string):string {
  const search=new URL(searchURL);
  if(search.protocol!=='https:' || !['ozon.ru','www.ozon.ru'].includes(search.hostname) || search.username || search.password || search.port)throw new Error('Неверный адрес Ozon');
  const url=new URL('/api/composer-api.bx/page/json/v2',search.origin);
  url.searchParams.set('url',search.pathname+search.search);return url.href;
}
function texts(value:any,depth=0):string[]{
  if(depth>10 || value===null)return [];
  if(typeof value==='string')return [value];
  if(Array.isArray(value))return value.slice(0,100).flatMap(v=>texts(v,depth+1));
  if(typeof value==='object'){
    if(/ORIGINAL|OLD/i.test(value.textStyle||''))return [];
    return Object.entries(value).filter(([key])=>!/old|original/i.test(key)).flatMap(([,v])=>texts(v,depth+1));
  }
  return [];
}
/** Only search widgets count as results; recommendation and advert widgets do not. */
export function ozonJSONOffers(payload:any):Offer[]{
  const offers=new Map<string,Offer>();
  for(const [key,raw] of Object.entries(payload?.widgetStates||{})){
    if(!/^(?:searchResults|tileGridDesktop)/i.test(key))continue;
    let state:any=raw;try{if(typeof raw==='string')state=JSON.parse(raw);}catch{continue;}
    for(const item of Array.isArray(state?.items)?state.items:[]){
      try {
        const url=productUrl(new URL(item?.action?.link||item?.link,'https://www.ozon.ru').href,'ozon').url;
        const main=Array.isArray(item.mainState)?item.mainState:[];
        const priceState=main.find((s:any)=>s?.priceV2)?.priceV2 || main.find((s:any)=>s?.price)?.price;
        const priceText=texts(priceState).find(t=>/\d[\d\s\u00a0\u202f]*\s*₽/.test(t));
        const amount=priceText?.match(/(\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?)\s*₽/)?.[1].replace(/\s/g,'').replace(',','.');
        const titleState=main.find((s:any)=>s?.id==='name') || main.find((s:any)=>s?.textAtom?.text || s?.textDS?.text);
        const name=titleState?.textDS?.text || titleState?.textAtom?.text;
        const brand=main.find((s:any)=>s?.labelListV2?.testInfo?.automatizationId==='tile-list-labels')?.labelListV2.items?.find((i:any)=>i?.text?.text)?.text.text;
        const label=[typeof brand==='string' && !/^бренд проверен$/i.test(brand)?brand:null,name].filter(v=>typeof v==='string' && v.trim()).join(' · ').slice(0,500);
        const priceNote=priceState?.priceStyle?.styleType==='CARD_PRICE'?'Цена с Ozon Картой; доставка уточняется в карточке':'Цена из выдачи Ozon; условия карты и доставки уточняйте в карточке';
        const offer={name:label,url,price:amount||'',priceNote};
        if(validOffer(offer,'ozon'))offers.set(url,offer);
        if(offers.size===5)return [...offers.values()];
      }catch{/* Unavailable or unrelated tiles are not offers. */}
    }
  }
  return [...offers.values()];
}
export function parseOzonHTML(html:string,url:string):Offer[]{
  const root=new DOMParser().parseFromString(html,'text/html');checkBlocked(root);
  return listingOffers(root,url,'ozon');
}
export async function searchFromOzonPage(query:string,signal:AbortSignal):Promise<Offer[]>{
  if(!['ozon.ru','www.ozon.ru'].includes(location.hostname) || location.protocol!=='https:')throw new Error('Нужна открытая вкладка Ozon');
  if(typeof query!=='string' || !query.trim() || query.length>300)throw new Error('Неверный запрос');
  const current=searchContext(location.href);
  if(current?.site==='ozon' && current.query===query){
    checkBlocked(document);
    const items=listingOffers(document,location.href,'ozon');if(items.length)return items;
  }
  const url=new URL('/search/',location.origin);url.searchParams.set('text',query);
  const failures:string[]=[];
  // These are same-origin requests made by an Ozon content script, with the
  // browser's existing session. No cookie export or header spoofing is used.
  for(const endpoint of [ozonComposerURL(url.href),url.href]){
    signal.throwIfAborted();
    try {
      const response=await fetch(endpoint,{credentials:'include',signal,redirect:'follow'});
      if(new URL(response.url).origin!==location.origin)throw new Error('Ozon изменил домен ответа');
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const body=await response.text();if(body.length>8_000_000)throw new Error('Ответ Ozon слишком большой');
      const items=endpoint.includes('/api/')?ozonJSONOffers(JSON.parse(body)):parseOzonHTML(body,response.url);
      if(items.length)return items;
      failures.push('нет карточек в ответе');
    }catch(error){signal.throwIfAborted();failures.push(String(error instanceof Error?error.message:error));}
  }
  throw new Error(`Ozon отклонил запрос из открытой вкладки (${failures.join('; ')}). Проверьте, открывается ли поиск в ней без проверки безопасности.`);
}
