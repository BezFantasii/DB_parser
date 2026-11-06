import sqlite3InitModule from "@sqlite.org/sqlite-wasm";
import {Database} from "./database.ts";
let sqlite: any;
let connection: any;
let database: Database;
const ready = (async () => {
  const initialize = sqlite3InitModule as unknown as (options: Record<string, unknown>) => Promise<any>;
  sqlite = await initialize({locateFile: (path: string) => new URL(`vendor/${path}`,self.location.href).href, print:()=>{},printErr:console.error});
  if (!sqlite.oo1.OpfsDb) throw new Error("OPFS SQLite недоступна. Нужен современный Chromium с включённым WebAssembly и изоляцией контекста.");
  connection = new sqlite.oo1.OpfsDb("/marketplace.sqlite3", "c");
  database = new Database(connection);
})();
let queue: Promise<unknown> = Promise.resolve();
self.onmessage = ({data}) => {
  queue = queue.catch(()=>{}).then(async () => {
    try {
      await ready;
      if (data.method === "backup") {
        const bytes = sqlite.capi.sqlite3_js_db_export(connection.pointer);
        const blob = new Blob([bytes],{type:"application/vnd.sqlite3"});
        self.postMessage({id:data.id,ok:true,value:blob});
      } else if (data.method === "storage") {
        self.postMessage({id:data.id,ok:true,value:await navigator.storage.estimate()});
      } else if (data.method === "restore") {
        // Validate an entirely separate database before touching the current one.
        const bytes = new Uint8Array(await data.bytes.arrayBuffer());
        const header = new TextDecoder().decode(bytes.slice(0,16));
        if (header !== "SQLite format 3\u0000") throw new Error("Это не файл SQLite");
        const filename = `/restore-${crypto.randomUUID()}.sqlite3`;
        await sqlite.oo1.OpfsDb.importDb(filename,bytes);
        let candidate: any;
        try {
          candidate = new sqlite.oo1.OpfsDb(filename,"w");
          const check = candidate.exec({sql:"PRAGMA integrity_check",returnValue:"resultRows"});
          if (check[0]?.[0] !== "ok") throw new Error("Нарушена целостность файла");
          const version=candidate.exec({sql:"PRAGMA user_version",returnValue:"resultRows"})[0][0];
          if (![1,2].includes(version)) throw new Error("Неподдерживаемая версия схемы");
          new Database(candidate);
          for (const table of ["products","price_history","parse_runs","parse_tasks","staged_products","watchlist","error_log","alerts"]) candidate.exec(`SELECT * FROM ${table} LIMIT 0`);
          if (candidate.exec({sql:"PRAGMA foreign_key_check",returnValue:"resultRows"}).length) throw new Error("Нарушены связи таблиц");
          const schemaObjects = candidate.exec({sql:"SELECT type,name FROM sqlite_schema WHERE type IN ('trigger','view')",rowMode:"object",returnValue:"resultRows"});
          if (schemaObjects.some((x:any)=> x.type === "trigger" || x.name !== "current_prices")) throw new Error("Неожиданные объекты в базе");
          const active = database.rows("SELECT id FROM parse_runs WHERE status IN ('running','paused','blocked','failed')");
          if (active.length) throw new Error("Перед восстановлением завершите или отмените незавершённые сборы");
          const backup = new Blob([sqlite.capi.sqlite3_js_db_export(connection.pointer)],{type:"application/vnd.sqlite3"});
          // Copy only known tables into the trusted schema; never install imported triggers or views.
          database.tx(()=>{
            for (const table of ["local_events","staged_products","parse_tasks","watchlist","alerts","price_history","error_log","products","parse_runs"]) database.exec(`DELETE FROM ${table}`);
            for (const table of ["products","parse_runs","parse_tasks","staged_products","price_history","watchlist","error_log","alerts","local_events"]) {
              const cols = database.rows(`PRAGMA table_info(${table})`).map(x=>x.name);
              const rows = candidate.exec({sql:`SELECT ${cols.join(",")} FROM ${table}`,rowMode:"array",returnValue:"resultRows"});
              for (const row of rows) database.exec(`INSERT INTO ${table}(${cols.join(",")}) VALUES(${cols.map(()=>"?").join(",")})`,row);
            }
            database.exec("UPDATE parse_runs SET status='paused' WHERE status='running'");
            database.exec("UPDATE parse_tasks SET status='queued',token=NULL,tab_id=NULL,lease_until=NULL WHERE status='running'");
            database.exec("UPDATE parse_tasks SET tab_id=NULL");
          });
          self.postMessage({id:data.id,ok:true,value:{backup,stats:database.stats()}});
        } finally {
          candidate?.close();
          const directory = await navigator.storage.getDirectory();
          await directory.removeEntry(filename.slice(1)).catch(()=>{});
        }
      } else self.postMessage({id:data.id,ok:true,value:database.call(data.method,data.args) ?? null});
    } catch(error) { self.postMessage({id:data.id,ok:false,error:error instanceof Error ? error.message : String(error)}); }
  });
};
