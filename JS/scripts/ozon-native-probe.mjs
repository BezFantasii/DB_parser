// Diagnostic only: run the production Ozon module in an ordinary Chrome page.
// Uses the project's separate diagnostic profile, never the user's main profile.
import {build} from 'esbuild';
import {mkdir,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..');
const output=path.join(root,'JS/test-results');await mkdir(output,{recursive:true});
const bundle=await build({absWorkingDir:path.join(root,'JS'),entryPoints:['src/ozon-session.ts'],bundle:true,write:false,format:'iife',globalName:'OzonProbe',platform:'browser',target:'chrome116'});
await writeFile(path.join(output,'ozon-native-probe.js'),bundle.outputFiles[0].text);
const source=String.raw`
import json
from pathlib import Path
from backend.ozon_session import OzonSession
report={}
try:
    with OzonSession(wait=5) as session:
        try: session.page.goto('https://www.ozon.ru/',wait_until='domcontentloaded',timeout=20000)
        except Exception as exc: report['navigation_error']=type(exc).__name__
        session.page.wait_for_timeout(3000)
        report['title']=session.page.title()
        module=Path('JS/test-results/ozon-native-probe.js').read_text(encoding='utf-8')
        code='async () => {'+module+r'''
          const requests=[];
          const nativeFetch=window.fetch.bind(window);
          window.fetch=async (...args)=>{
            const response=await nativeFetch(...args);
            const row={url:new URL(response.url).pathname,status:response.status,type:response.headers.get('content-type')};
            requests.push(row);
            try {
              const data=await response.clone().json();
              row.fields=Object.keys(data);row.redirect=data.browser?.redirect||data.redirect;
              row.widgets=Object.entries(data.widgetStates||{}).filter(([k])=>/search|tile|catalog/i.test(k)).map(([key,raw])=>{
                let state;try{state=typeof raw==='string'?JSON.parse(raw):raw}catch{return {key}}
                return {key,fields:Object.keys(state||{}),count:Array.isArray(state?.items)?state.items.length:null};
              });
            }catch{}
            return response;
          };
          try {
            const items=await OzonProbe.searchFromOzonPage('\u0445\u0443\u0434\u0438 \u043c\u0443\u0436\u0441\u043a\u043e\u0435',AbortSignal.timeout(18000));
            return {items,requests};
          }catch(error){return {error:String(error),requests};}
          finally{window.fetch=nativeFetch;}
        }'''
        report['result']=session.page.evaluate(code)
except Exception as exc: report['error']=str(exc)
Path('JS/test-results/ozon-native-session-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
`;
const child=spawn(path.join(root,'.venv/Scripts/python.exe'),['-'],{cwd:root,stdio:['pipe','inherit','inherit'],windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
child.stdin.end(source);
child.on('error',error=>{console.error(error.message);process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code||0;});
