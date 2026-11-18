import {siteName,type Comparison} from './comparison.ts';

export const widgetCSS=`
:host {all:initial;color-scheme:light;position:fixed;top:18px;right:18px;z-index:2147483647;display:block;width:342px;max-width:calc(100vw - 24px);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;color:#1e293b}
*{box-sizing:border-box} .panel{background:#fff;border:1px solid #e2e8f0;border-radius:18px;box-shadow:0 8px 40px #0f172a26;overflow:hidden}
header{display:flex;align-items:center;gap:8px;padding:13px 15px;background:#f8fafc} header strong{flex:1;font-size:14px} .dot{width:9px;height:9px;border-radius:50%;background:#6366f1}
button{font:inherit;cursor:pointer;border:0;border-radius:9px;background:#eef2ff;color:#4338ca;padding:7px 10px} button:hover{background:#e0e7ff} button:focus-visible,a:focus-visible{outline:2px solid #6366f1;outline-offset:2px} .icon{background:transparent;padding:3px 6px;color:#64748b}
.body{padding:14px 15px;max-height:440px;overflow:auto} p{margin:0 0 10px} .muted,small{color:#64748b;font-size:12px} .query{font-weight:600;overflow-wrap:anywhere} .status{padding:10px;background:#f1f5f9;border-radius:10px} .error{background:#fff7ed;color:#9a3412}
.offer{display:block;text-decoration:none;color:#1e293b;border:1px solid #e2e8f0;border-radius:11px;padding:10px;margin:9px 0} .offer:hover{border-color:#818cf8;background:#fafaff} .name{display:block;max-height:42px;overflow:hidden} .price{display:block;color:#4338ca;font-size:18px;margin-top:4px;font-weight:700} small{display:block;margin-top:3px} .actions{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px} a{color:#4338ca} .foot{margin:12px 0 0;font-size:11px;color:#64748b}
@media(max-width:420px){:host{top:10px;right:10px}}
`;
export function node<K extends keyof HTMLElementTagNameMap>(tag:K,text='',className=''):HTMLElementTagNameMap[K]{
  const element=document.createElement(tag);element.textContent=text;element.className=className;return element;
}
export function renderComparison(container:HTMLElement,job:Comparison|null,enabled:boolean,retry:()=>void){
  container.replaceChildren();
  if(!enabled){container.append(node('p','Автопоиск выключен. Включите переключатель, чтобы сравнивать выдачу.','status'));return;}
  if(!job){container.append(node('p','Найдите товар на Ozon или Wildberries. Мы автоматически покажем выдачу с другой площадки.','status'));return;}
  container.append(node('p',`${siteName(job.source)} → ${siteName(job.target)}`,'muted'),node('p',job.query,'query'));
  if(job.status==='loading')container.append(node('p',job.mode==='backend'?(job.phase||'Отправляем поиск на backend…'):`Ищем на ${siteName(job.target)}… Запрашиваем данные в фоне, без открытия страниц.`,'status'));
  else if(job.status==='error')container.append(node('p',job.error||'Не удалось получить выдачу.','status error'));
  else {
    container.append(node('p',`Найдено: ${job.items.length} · ${new Date(job.updatedAt).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}`,'muted'));
    for(const item of job.items){
      const link=node('a','','offer');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      link.append(node('span',item.name,'name'),node('span',`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(item.price))} ₽`,'price'),node('small',item.priceNote));
      container.append(link);
    }
  }
  const actions=node('div','','actions');
  const search=node('a','Открыть поиск ↗');search.href=job.searchUrl;search.target='_blank';search.rel='noopener noreferrer';actions.append(search);
  if(job.status!=='loading'){const button=node('button','Повторить');button.onclick=retry;actions.append(button);}
  container.append(actions,node('p',`${job.mode==='backend'?'Получено через backend. ':''}Это результаты одинакового запроса. Модель, доставка и условия цены могут отличаться.`,'foot'));
}
