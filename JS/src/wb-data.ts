import {validOffer,type Offer} from './comparison.ts';

export function wbSearchURL(query:string):string {
  const url=new URL('https://search.wb.ru/exactmatch/ru/common/v18/search');
  url.search=new URLSearchParams({appType:'1',curr:'rub',dest:'-1257786',lang:'ru',page:'1',query,resultset:'catalog',sort:'popular',spp:'30'}).toString();
  return url.href;
}
export function wbOffers(payload:any):Offer[] {
  const products=payload?.data?.products ?? payload?.products;
  if(!Array.isArray(products))return [];
  const offers:Offer[]=[];const seen=new Set<string>();
  for(const product of products){
    const id=String(product?.id||'');if(!/^\d+$/.test(id) || seen.has(id))continue;
    const prices=(Array.isArray(product.sizes)?product.sizes:[]).map((size:any)=>size?.price?.product).filter((p:unknown)=>typeof p==='number' && Number.isSafeInteger(p) && p>0);
    const minor=prices.length?Math.min(...prices):product.salePriceU;
    if(!Number.isSafeInteger(minor) || minor<=0)continue;
    const name=[product.brand,product.name].filter(v=>typeof v==='string' && v.trim()).join(' · ').slice(0,500);
    const item:Offer={name,url:`https://www.wildberries.ru/catalog/${id}/detail.aspx`,price:(minor/100).toFixed(2),priceNote:'Цена WB для региона запроса; доставка и скидки могут отличаться'};
    if(validOffer(item,'wb')){offers.push(item);seen.add(id);}
    if(offers.length===5)break;
  }
  return offers;
}
