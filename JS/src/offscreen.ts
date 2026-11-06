const worker = new Worker("sqlite.worker.js",{type:"module"});
const waiting = new Map<string,{resolve:(v:any)=>void;reject:(e:Error)=>void}>();
worker.onmessage = ({data}) => {
  const pending = waiting.get(data.id);
  if (!pending) return;
  waiting.delete(data.id);
  data.ok ? pending.resolve(data.value) : pending.reject(new Error(data.error));
};
worker.onerror = event => {
  for (const p of waiting.values()) p.reject(new Error(event.message || "Ошибка Worker базы"));
  waiting.clear();
};
function call(method: string, args: any, bytes?: Blob): Promise<any> {
  const id = crypto.randomUUID();
  return new Promise((resolve,reject)=>{
    waiting.set(id,{resolve,reject}); worker.postMessage({id,method,args,bytes});
  });
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if (message.target !== "database" || sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(""))) return;
  void (async()=>{
    try {
      if (message.method === "backup") {
        const blob = await call("backup",{});
        const url = URL.createObjectURL(blob);
        setTimeout(()=>URL.revokeObjectURL(url),300000);
        respond({ok:true,value:{url}});
      } else if (message.method === "restore") {
        if (typeof message.args?.url !== "string" || !message.args.url.startsWith(`blob:chrome-extension://${chrome.runtime.id}/`)) throw new Error("Неверный адрес файла");
        const bytes = await (await fetch(message.args.url)).blob();
        const restored = await call("restore",{},bytes);
        const backupUrl = URL.createObjectURL(restored.backup);
        setTimeout(()=>URL.revokeObjectURL(backupUrl),300000);
        respond({ok:true,value:{stats:restored.stats,backupUrl}});
      } else respond({ok:true,value:await call(message.method,message.args)});
    } catch(error) {respond({ok:false,error:error instanceof Error ? error.message : String(error)});}
  })();
  return true;
});
