import {productUrl, type Marketplace} from './domain.ts';
import type {Offer} from './comparison.ts';

function amount(text:string):string|null {
  const match=text.replace(/[\u00a0\u202f\u2009]/g,' ').match(/(\d[\d ]*(?:[.,]\d{1,2})?)\s*(?:₽|руб\.?)/i);
  if(!match)return null;
  const value=match[1].replace(/ /g,'').replace(',','.');
  return /^\d{1,10}(?:\.\d{1,2})?$/.test(value) && Number(value)>0 ? value : null;
}

/** Resolve price within one product card, never from the whole listing. */
export function listingOffers(root:Document,address:string,site:Marketplace,limit=5):Offer[] {
  const offers=new Map<string,Offer>();
  for(const anchor of root.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    let canonical:string;
    try {canonical=productUrl(new URL(anchor.getAttribute('href')!,address).href,site).url;} catch {continue;}
    if(offers.has(canonical))continue;
    const card=anchor.closest('article.product-card, .product-card, [data-nm-id], [data-product-id], [data-index]') || findCard(anchor,canonical,address,site);
    if(!card)continue;
    // A container containing several different products is not a card.
    const urls=new Set<string>();
    for(const a of card.querySelectorAll<HTMLAnchorElement>('a[href]')) {
      try {urls.add(productUrl(new URL(a.getAttribute('href')!,address).href,site).url);} catch {}
    }
    if(urls.size!==1 || !urls.has(canonical))continue;
    const priceNode=card.querySelector('.price__lower-price, .lower-price, [class*="priceSm"], [class*="priceMain"], [data-widget="tilePrice"], [itemprop="price"]');
    const clean=card.cloneNode(true) as Element;
    for(const old of clean.querySelectorAll('del,s,strike,[class*="old-price"],[class*="oldPrice"],button'))old.remove();
    const price=amount(priceNode?.textContent||'') || amount(clean.textContent||'');
    if(!price)continue;
    const title=card.querySelector('.product-card__name, [class*="product-card__name"], [data-widget="tileTitle"], [itemprop="name"], [class*="tsBody"]');
    const image=card.querySelector('img[alt]');
    const name=(title?.textContent || anchor.getAttribute('title') || image?.getAttribute('alt') ||
      [...card.querySelectorAll('a')].map(a=>a.textContent?.trim()).find(t=>t && !amount(t)) || '').replace(/\s+/g,' ').trim().slice(0,500);
    if(!name)continue;
    const text=(card.textContent||'').replace(/\s+/g,' ');
    const priceNote=/с\s+(?:ozon\s*карт|картой)/i.test(text)?'Цена с картой площадки':/кошел[еёь]к|wb\s*кошел/i.test(text)?'Цена с кошельком WB':'Цена из выдачи; условия уточняйте в карточке';
    offers.set(canonical,{name,url:canonical,price,priceNote});
    if(offers.size>=limit)break;
  }
  return [...offers.values()];
}
function findCard(anchor:Element,canonical:string,address:string,site:Marketplace):Element|null {
  let current:Element|null=anchor;
  for(let depth=0;current && depth<7;depth++,current=current.parentElement) {
    const urls=new Set<string>();
    for(const a of current.querySelectorAll('a[href]')) {
      try {urls.add(productUrl(new URL(a.getAttribute('href')!,address).href,site).url);} catch {}
      if(urls.size>1)return null;
    }
    if(urls.has(canonical) && amount(current.textContent||''))return current;
  }
  return null;
}
