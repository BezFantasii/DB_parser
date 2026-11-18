import {searchContext,type Comparison} from './comparison.ts';
import {marketplaceFor,productUrl} from './domain.ts';
import {listingOffers} from './listing.ts';
import {checkBlocked} from './parser.ts';
import {node,renderComparison,widgetCSS} from './comparison-view.ts';
import {searchFromOzonPage} from './ozon-session.ts';
import {searchFromWBPage,observedWBSearch} from './wb-session.ts';
const ozonRequests=new Map<string,AbortController>();

let lastURL='',pending=false,closedFor='',collapsed=false,current:Comparison|null=null;
let host:HTMLElement|null=null,body:HTMLElement|null=null;
const rpc=async(type:string,args:Record<string,unknown>={})=>{
  const result=await chrome.runtime.sendMessage({target:'comparison',type,...args});
  if(!result?.ok)throw new Error(result?.error||'Расширение не отвечает');
  return result.value;
};
function removeWidget(){host?.remove();host=null;body=null;}
function show(job:Comparison|null,enabled:boolean){
  current=job;
  if(!job || !enabled || closedFor===job.id){removeWidget();return;}
  if(!host){
    host=node('div');host.id='marketplace-comparison-widget';
    const shadow=host.attachShadow({mode:'open'}),style=node('style',widgetCSS);
    const panel=node('section','','panel');panel.setAttribute('aria-label','Сравнение маркетплейсов');
    const header=node('header');const dot=node('span','','dot');
    const collapse=node('button','−','icon');collapse.title='Свернуть / развернуть';
    collapse.setAttribute('aria-label',collapse.title);collapse.setAttribute('aria-expanded',String(!collapsed));
    const close=node('button','×','icon');close.title='Скрыть до следующего поиска';close.setAttribute('aria-label',close.title);
    header.append(dot,node('strong','Сравнить цены'),collapse,close);body=node('div','','body');
    collapse.onclick=()=>{collapsed=!collapsed;body!.hidden=collapsed;collapse.textContent=collapsed?'+':'−';collapse.setAttribute('aria-expanded',String(!collapsed));};
    close.onclick=()=>{closedFor=current?.id||'';removeWidget();};
    panel.append(header,body);shadow.append(style,panel);document.documentElement.append(host);
  }
  body!.hidden=collapsed;
  renderComparison(body!,job,enabled,()=>void retry());
}
async function retry(){
  // Content scripts cannot choose another tab or send administrative commands.
  lastURL='';
  await chrome.runtime.sendMessage({target:'comparison',type:'retry-current'});
  await sync(true);
}
async function sync(force=false){
  if(pending || (!force && location.href===lastURL))return;
  pending=true;const url=location.href;
  try {
    const state=await rpc('sync');lastURL=url;
    show(state.job,state.enabled);
  }catch(error){console.warn('[Сравнить цены]',String(error));removeWidget();}finally{pending=false;}
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message.target==='comparison-browser-diagnostics' && sender.id===chrome.runtime.id){
    try{
      const site=marketplaceFor(location.href);
      const search=searchContext(location.href);
      const links=new Set<string>();
      if(search)for(const anchor of document.querySelectorAll<HTMLAnchorElement>('a[href]')){try{links.add(productUrl(anchor.href,site).url);}catch{}}
      const endpoints=site==='wb'?[...new Set(performance.getEntriesByType('resource').map(e=>observedWBSearch([e.name],'diagnostic')).filter((v):v is string=>!!v))].slice(-5).map(value=>{const u=new URL(value);return {origin:u.origin,path:u.pathname,parameterNames:[...u.searchParams.keys()]};}):[];
      respond({contentScriptAvailable:true,contentScriptVersion:chrome.runtime.getManifest().version,site,accessCheckInTitle:/captcha|доступ ограничен|нет соединения|access denied/i.test(document.title),
        search,productLinkCount:search?links.size:null,domOffers:search?listingOffers(document,location.href,site):[],wbSearchEndpoints:endpoints});
    }catch(error){respond({contentScriptAvailable:true,error:String(error)});}
    return false;
  }
  if(['comparison-ozon-session','comparison-wb-session'].includes(message.target) && sender.id===chrome.runtime.id){
    if(message.cancel){ozonRequests.get(message.id)?.abort();respond({ok:true});return false;}
    const controller=new AbortController();ozonRequests.set(message.id,controller);
    const timeout=setTimeout(()=>controller.abort(),18000);
    const search=message.target==='comparison-ozon-session'?searchFromOzonPage:searchFromWBPage;
    void search(message.query,controller.signal).then(items=>respond({items}),error=>respond({error:String(error instanceof Error?error.message:error)})).finally(()=>{clearTimeout(timeout);ozonRequests.delete(message.id);});
    return true;
  }
  if(message.target==='comparison-parse' && sender.id===chrome.runtime.id){
    try {
      const root=new DOMParser().parseFromString(message.html,'text/html');
      checkBlocked(root);
      respond({items:listingOffers(root,message.url,message.site)});
    }catch(error){respond({error:String(error instanceof Error?error.message:error).replace(/^BLOCKED:.*/,'Площадка запросила проверку или ограничила доступ. Автоматический переход отключён; откройте поиск вручную и повторите.')});}
    return false;
  }
  if(message.target==='comparison-view'){
    const context=searchContext(location.href);
    if(context && context.query===message.job.query && context.site===message.job.source)show(message.job,true);
  }
  if(message.target==='comparison-refresh'){lastURL='';void sync(true);}
});
void sync();
// Both sites change the query through SPA navigation, without document reload.
const timer=setInterval(()=>{if(!chrome.runtime.id){clearInterval(timer);removeWidget();return;}void sync();},1000);
window.addEventListener('pageshow',()=>{lastURL='';void sync(true);});
