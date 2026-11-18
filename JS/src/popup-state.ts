import {defaultBackend,type BackendConfig} from './backend-search.ts';
import type {Comparison} from './comparison.ts';

/** Older service workers do not include settings in their state response. */
export function popupState(value:any):{enabled:boolean;job:Comparison|null;backend:BackendConfig;missingSettings:boolean}{
  if(!value || typeof value!=='object')throw new Error('Не получено состояние расширения. Обновите расширение на chrome://extensions и перезагрузите страницы магазинов.');
  const stored=value.backend;
  return {enabled:value.enabled!==false,job:value.job||null,missingSettings:!stored || typeof stored!=='object',backend:{
    mode:stored?.mode==='backend'?'backend':'browser',
    url:typeof stored?.url==='string'?stored.url:defaultBackend.url,
    token:typeof stored?.token==='string'?stored.token:'',
  }};
}
