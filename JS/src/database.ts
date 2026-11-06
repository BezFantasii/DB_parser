import {decimal, normalize, productUrl, scaled, siteUrl, validateBatch, type Marketplace, type Product} from "./domain.ts";

// Only this module owns a SQLite connection. Its public methods receive validated commands, never UI SQL.
export class Database {
  constructor(private db: any) { this.migrate(); }
  rows(sql: string, bind: any[] = []): any[] { return this.db.exec({sql, bind, rowMode: "object", returnValue: "resultRows"}); }
  exec(sql: string, bind: any[] = []): void { this.db.exec({sql, bind}); }
  one(sql: string, bind: any[] = []): any { return this.rows(sql, bind)[0]; }
  tx<T>(fn: () => T): T {
    this.exec("BEGIN IMMEDIATE");
    try { const result = fn(); this.exec("COMMIT"); return result; }
    catch (error) { this.exec("ROLLBACK"); throw error; }
  }
  migrate(): void {
    this.exec("PRAGMA foreign_keys=ON");
    this.exec("PRAGMA trusted_schema=OFF");
    const version = this.one("PRAGMA user_version").user_version;
    if (version > 2) throw new Error("База создана более новой версией расширения");
    if (version === 2) return;
    if (version === 1) {this.tx(()=>{this.exec("CREATE TABLE local_events(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL,created_at TEXT NOT NULL,stage TEXT NOT NULL,data TEXT NOT NULL)");this.exec("PRAGMA user_version=2");});return;}
    this.tx(() => {
      this.exec(`
        CREATE TABLE products (
          id INTEGER PRIMARY KEY, marketplace TEXT NOT NULL CHECK(marketplace IN ('wb','ozon')),
          external_id TEXT NOT NULL, name TEXT NOT NULL, url TEXT NOT NULL, brand TEXT, model TEXT,
          connection_type TEXT, form_factor TEXT, anc INTEGER, microphone INTEGER, battery_hours REAL,
          first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, UNIQUE(marketplace,external_id)
        );
        CREATE TABLE parse_runs (
          id INTEGER PRIMARY KEY, marketplace TEXT NOT NULL, source_url TEXT NOT NULL,
          status TEXT NOT NULL, settings TEXT NOT NULL, parser_version TEXT NOT NULL DEFAULT '1',
          created_at TEXT NOT NULL, finished_at TEXT, error TEXT
        );
        CREATE TABLE parse_tasks (
          id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES parse_runs(id), kind TEXT NOT NULL,
          url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
          token TEXT, tab_id INTEGER, lease_until INTEGER, next_at INTEGER NOT NULL DEFAULT 0, error TEXT,
          UNIQUE(run_id,kind,url)
        );
        CREATE TABLE staged_products (
          task_id INTEGER PRIMARY KEY REFERENCES parse_tasks(id), run_id INTEGER NOT NULL REFERENCES parse_runs(id),
          payload TEXT NOT NULL
        );
        CREATE TABLE price_history (
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
          run_id INTEGER NOT NULL REFERENCES parse_runs(id), observed_at TEXT NOT NULL,
          price_minor INTEGER CHECK(price_minor>=0), old_price_minor INTEGER CHECK(old_price_minor>=0),
          currency TEXT NOT NULL, region TEXT NOT NULL, price_kind TEXT NOT NULL, availability TEXT NOT NULL,
          rating REAL, reviews_count INTEGER,
          UNIQUE(run_id,product_id,region,currency,price_kind)
        );
        CREATE TABLE watchlist (
          product_id INTEGER PRIMARY KEY REFERENCES products(id), interval_minutes INTEGER NOT NULL,
          next_at INTEGER NOT NULL, last_run_id INTEGER REFERENCES parse_runs(id), last_price_minor INTEGER
        );
        CREATE TABLE error_log (
          id INTEGER PRIMARY KEY, run_id INTEGER, task_id INTEGER, created_at TEXT NOT NULL, message TEXT NOT NULL
        );
        CREATE TABLE alerts (
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
          created_at TEXT NOT NULL, message TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX price_latest ON price_history(product_id,region,currency,price_kind,observed_at DESC,id DESC);
        CREATE INDEX task_queue ON parse_tasks(status,next_at);
        CREATE INDEX product_features ON products(connection_type,form_factor);
        CREATE VIEW current_prices AS SELECT * FROM (
          SELECT h.*, ROW_NUMBER() OVER(PARTITION BY product_id,region,currency,price_kind ORDER BY observed_at DESC,id DESC) AS rn
          FROM price_history h
        ) WHERE rn=1;
        CREATE TABLE local_events(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL,created_at TEXT NOT NULL,stage TEXT NOT NULL,data TEXT NOT NULL);
        PRAGMA user_version=2;
      `);
    });
  }
  createRun(args: {site: Marketplace; url: string; limit?: number; pages?: number; scrolls?: number; delay?: number}): number {
    siteUrl(args.url, args.site);
    const settings = {limit: args.limit ?? 30, pages: args.pages ?? 1, scrolls: args.scrolls ?? 3, delay: args.delay ?? 3};
    for (const [key, value] of Object.entries(settings)) if (!Number.isInteger(value) || value < (key === "scrolls" ? 0 : 1) || value > ({limit: 500, pages: 20, scrolls: 10, delay: 60} as any)[key]) throw new Error(`Неверный параметр ${key}`);
    return this.tx(() => {
      this.exec("INSERT INTO parse_runs(marketplace,source_url,status,settings,created_at) VALUES(?,?,'running',?,?)", [args.site, args.url, JSON.stringify(settings), new Date().toISOString()]);
      const id = this.one("SELECT last_insert_rowid() AS id").id;
      let direct: string | null = null;
      try { direct = productUrl(args.url, args.site).url; } catch { /* Search URL. */ }
      if (direct) this.exec("INSERT INTO parse_tasks(run_id,kind,url) VALUES(?,'product',?)", [id, direct]);
      else for (let page = 1; page <= settings.pages; page++) {
        const u = new URL(args.url); u.searchParams.set("page", String(page));
        this.exec("INSERT INTO parse_tasks(run_id,kind,url) VALUES(?,'listing',?)", [id, u.href]);
      }
      this.exec("INSERT INTO local_events(run_id,created_at,stage,data) VALUES(?,?,'job.queued',?)",[id,new Date().toISOString(),JSON.stringify({url:args.url})]);
      return id;
    });
  }
  runs(): any[] {
    return this.rows(`SELECT r.*, COUNT(t.id) AS total, SUM(t.status='done') AS done,
      SUM(t.status='error') AS failed, (SELECT COUNT(*) FROM staged_products s WHERE s.run_id=r.id) AS staged
      FROM parse_runs r LEFT JOIN parse_tasks t ON t.run_id=r.id GROUP BY r.id ORDER BY r.id DESC LIMIT 100`);
  }
  claim(): any {
    return this.tx(() => {
      const now = Date.now();
      // An interrupted claim can be delivered again, with a NEW attempt token.
      const exhausted = this.rows("SELECT id,run_id FROM parse_tasks WHERE status='running' AND lease_until<? AND attempts>=3",[now]);
      for(const t of exhausted){this.exec("UPDATE parse_tasks SET status='error',token=NULL,lease_until=NULL,error='Три прерванные попытки; требуется продолжение вручную' WHERE id=?",[t.id]);this.exec("UPDATE parse_runs SET status='failed',error='Рабочая вкладка не отвечает; продолжите сбор вручную' WHERE id=?",[t.run_id]);}
      this.exec("UPDATE parse_tasks SET status='queued', token=NULL,lease_until=NULL,error='Предыдущая попытка прервана' WHERE status='running' AND lease_until<?", [now]);
      if (this.one("SELECT id FROM parse_tasks WHERE status='running'")) return null;
      const task = this.one(`SELECT t.*,r.marketplace,r.settings FROM parse_tasks t JOIN parse_runs r ON r.id=t.run_id
        WHERE t.status='queued' AND t.next_at<=? AND r.status='running'
        ORDER BY CASE t.kind WHEN 'listing' THEN 0 ELSE 1 END,t.id LIMIT 1`, [now]);
      if (!task) return null;
      const token = crypto.randomUUID();
      this.exec("UPDATE parse_tasks SET status='running',token=?,attempts=attempts+1,lease_until=? WHERE id=?", [token, now + 120000, task.id]);
      const previousTab = this.one("SELECT tab_id FROM parse_tasks WHERE run_id=? AND tab_id IS NOT NULL ORDER BY id DESC LIMIT 1",[task.run_id]);
      return {...task, tab_id:task.tab_id ?? previousTab?.tab_id ?? null, token, attempts: task.attempts + 1, settings: JSON.parse(task.settings)};
    });
  }
  task(id: number): any { const r = this.one("SELECT t.*,r.marketplace,r.settings,r.status AS run_status FROM parse_tasks t JOIN parse_runs r ON r.id=t.run_id WHERE t.id=?", [id]); return r ? {...r, settings: JSON.parse(r.settings)} : null; }
  bindTask(id: number, token: string, tabId: number): void { this.exec("UPDATE parse_tasks SET tab_id=? WHERE id=? AND token=? AND status='running'", [tabId, id, token]); }
  tasksForTab(tabId: number): any[] { return this.rows("SELECT id FROM parse_tasks WHERE tab_id=? AND status='running'", [tabId]).map(x => this.task(x.id)); }
  result(args: {taskId: number; token: string; tabId?: number; data?: unknown; error?: string; trusted?: boolean}): any {
    return this.tx(() => {
      const t = this.task(args.taskId);
      if (!t || t.status !== "running" || t.run_status !== "running" || t.token !== args.token || (!args.trusted && t.tab_id !== args.tabId)) return {ignored: true};
      if (args.error) {
        const error = String(args.error).slice(0, 2000);
        const blocked = error.includes("BLOCKED:");
        const retry = !blocked && t.attempts < 3;
        this.exec("INSERT INTO error_log(run_id,task_id,created_at,message) VALUES(?,?,?,?)", [t.run_id,t.id,new Date().toISOString(),error]);
        this.exec("UPDATE parse_tasks SET status=?,token=NULL,lease_until=NULL,next_at=?,error=? WHERE id=?", [retry ? "queued" : "error", Date.now() + 15000 * t.attempts, error, t.id]);
        if (!retry) this.exec("UPDATE parse_runs SET status=?,error=? WHERE id=?", [blocked ? "blocked" : "failed", error, t.run_id]);
        return {runId: t.run_id, blocked, retry};
      }
      if (t.kind === "listing") {
        if (!Array.isArray(args.data) || !args.data.length) throw new Error("Пустая выдача");
        const existing = this.one("SELECT COUNT(*) AS n FROM parse_tasks WHERE run_id=? AND kind='product'", [t.run_id]).n;
        let remaining = t.settings.limit - existing;
        for (const raw of args.data) {
          if (remaining <= 0) break;
          const {url} = productUrl(String(raw), t.marketplace);
          const exists = this.one("SELECT id FROM parse_tasks WHERE run_id=? AND kind='product' AND url=?", [t.run_id,url]);
          if (!exists) { this.exec("INSERT INTO parse_tasks(run_id,kind,url,next_at) VALUES(?,'product',?,?)", [t.run_id,url,Date.now() + t.settings.delay * 1000]); remaining--; }
        }
      } else {
        const item = normalize(args.data, t.marketplace);
        if (productUrl(t.url,t.marketplace).id !== item.external_id) throw new Error("Получена другая карточка");
        this.exec("INSERT INTO staged_products(task_id,run_id,payload) VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload", [t.id,t.run_id,JSON.stringify(item)]);
      }
      this.exec("UPDATE parse_tasks SET status='done',token=NULL,lease_until=NULL,error=NULL WHERE id=?", [t.id]);
      this.exec("UPDATE parse_tasks SET next_at=MAX(next_at,?) WHERE run_id=? AND status='queued'", [Date.now() + t.settings.delay * 1000,t.run_id]);
      if (!this.one("SELECT id FROM parse_tasks WHERE run_id=? AND status!='done'", [t.run_id])) this.publish(t.run_id);
      return {runId: t.run_id};
    });
  }
  private publish(runId: number): void {
    const run = this.one("SELECT * FROM parse_runs WHERE id=?", [runId]);
    const staged = this.rows("SELECT payload FROM staged_products WHERE run_id=? ORDER BY task_id", [runId]);
    if (!staged.length) throw new Error("Нет карточек для публикации");
    for (const row of staged) this.saveProduct(normalize(JSON.parse(row.payload),run.marketplace),run.marketplace,runId);
    this.exec("UPDATE parse_runs SET status='succeeded',finished_at=?,error=NULL WHERE id=?", [new Date().toISOString(),runId]);
    this.exec("DELETE FROM staged_products WHERE run_id=?", [runId]);
  }
  private saveProduct(item: Product, site: Marketplace, runId: number): void {
    const stamp = item.observed_at;
    const f = item.features;
    this.exec(`INSERT INTO products(marketplace,external_id,name,url,brand,model,connection_type,form_factor,anc,microphone,battery_hours,first_seen_at,last_seen_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(marketplace,external_id) DO UPDATE SET
      name=excluded.name,url=excluded.url,brand=excluded.brand,model=excluded.model,connection_type=excluded.connection_type,
      form_factor=excluded.form_factor,anc=excluded.anc,microphone=excluded.microphone,battery_hours=excluded.battery_hours,
      first_seen_at=MIN(products.first_seen_at,excluded.first_seen_at),last_seen_at=excluded.last_seen_at WHERE excluded.last_seen_at>=products.last_seen_at`,
      [site,item.external_id,item.name,item.url,item.brand,item.model,f.connection_type,f.form_factor,f.anc === null ? null : +f.anc,f.microphone === null ? null : +f.microphone,f.battery_hours,stamp,stamp]);
    const id = this.one("SELECT id FROM products WHERE marketplace=? AND external_id=?", [site,item.external_id]).id;
    const before = this.one("SELECT * FROM current_prices WHERE product_id=? AND region=? AND currency=? AND price_kind=?", [id,item.region,item.currency,item.price_kind]);
    const price = scaled(item.price);
    this.exec(`INSERT INTO price_history(product_id,run_id,observed_at,price_minor,old_price_minor,currency,region,price_kind,availability,rating,reviews_count)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)`, [id,runId,stamp,price,scaled(item.old_price),item.currency,item.region,item.price_kind,item.availability,item.rating,item.reviews_count]);
    // Only confirmed, comparable offer contexts generate price alerts.
    if (before && before.observed_at < stamp && before.price_minor !== null && price !== null && price < before.price_minor &&
      item.region !== "unknown" && item.price_kind !== "unknown" && item.availability === "in_stock" &&
      this.one("SELECT product_id FROM watchlist WHERE product_id=?", [id])) {
      this.exec("INSERT INTO alerts(product_id,created_at,message) VALUES(?,?,?)", [id,stamp,`${item.name}: ${decimal(before.price_minor)} → ${item.price} ${item.currency}`]);
    }
  }
  changeRun(id: number, action: string): any {
    return this.tx(() => {
      const run = this.one("SELECT * FROM parse_runs WHERE id=?", [id]);
      if (!run) throw new Error("Запуск не найден");
      if (["succeeded","cancelled"].includes(run.status)) throw new Error("Запуск уже завершён");
      const tabs = this.rows("SELECT DISTINCT tab_id FROM parse_tasks WHERE run_id=? AND tab_id IS NOT NULL", [id]).map(x => x.tab_id);
      if (action === "resume") {
        this.exec("UPDATE parse_tasks SET status='queued',token=NULL,lease_until=NULL,attempts=0,next_at=0 WHERE run_id=? AND status!='done'", [id]);
        this.exec("UPDATE parse_runs SET status='running',error=NULL WHERE id=?", [id]);
      } else if (action === "pause" || action === "cancel") {
        this.exec("UPDATE parse_tasks SET status='queued',token=NULL,lease_until=NULL WHERE run_id=? AND status='running'", [id]);
        this.exec("UPDATE parse_runs SET status=? WHERE id=?", [action === "pause" ? "paused" : "cancelled",id]);
      } else throw new Error("Неизвестное действие");
      return {tabs};
    });
  }
  importBatch(payload: unknown): any {
    const batch = validateBatch(payload);
    return this.tx(() => {
      this.exec("INSERT INTO parse_runs(marketplace,source_url,status,settings,created_at) VALUES(?,?,'running','{}',?)", [batch.marketplace,batch.source_url,new Date().toISOString()]);
      const id = this.one("SELECT last_insert_rowid() AS id").id;
      for (const item of batch.items) this.saveProduct(item,batch.marketplace,id);
      this.exec("UPDATE parse_runs SET status='succeeded',finished_at=? WHERE id=?", [new Date().toISOString(),id]);
      return {runId: id, saved: batch.items.length};
    });
  }
  products(args: any = {}): any {
    const conditions = ["1=1"], bind: any[] = [];
    if (args.search) { conditions.push("(p.name LIKE ? OR p.brand LIKE ? OR p.external_id=?)"); bind.push(`%${String(args.search).slice(0,200)}%`,`%${String(args.search).slice(0,200)}%`,String(args.search)); }
    if (args.site) { conditions.push("p.marketplace=?"); bind.push(args.site); }
    for (const key of ["connection_type","form_factor"] as const) if (args[key]) { conditions.push(`p.${key}=?`); bind.push(args[key]); }
    if (args.maxPrice) { conditions.push("c.price_minor<=?"); bind.push(scaled(args.maxPrice)); }
    if (args.anc) conditions.push("p.anc=1");
    if (args.microphone) conditions.push("p.microphone=1");
    if (args.inStock) conditions.push("c.availability='in_stock'");
    if (args.minRating) { conditions.push("c.rating>=?"); bind.push(Number(args.minRating)); }
    const where = conditions.join(" AND ");
    const from = "FROM products p LEFT JOIN current_prices c ON c.product_id=p.id LEFT JOIN watchlist w ON w.product_id=p.id";
    const total = this.one(`SELECT COUNT(*) AS n ${from} WHERE ${where}`,bind).n;
    const offset = Math.max(0,Math.min(Number(args.offset) || 0,10000000));
    const limit = Math.max(1,Math.min(Number(args.limit) || 100,500));
    const items = this.rows(`SELECT p.*,c.price_minor,c.old_price_minor,c.currency,c.region,c.price_kind,c.availability,c.rating,c.reviews_count,c.observed_at,
      w.interval_minutes AS watch_interval ${from} WHERE ${where} ORDER BY p.last_seen_at DESC,p.id DESC,c.id DESC LIMIT ? OFFSET ?`,[...bind,limit,offset]);
    return {items,total};
  }
  details(id: number): any {
    return {product: this.one("SELECT * FROM products WHERE id=?",[id]),history: this.rows("SELECT * FROM price_history WHERE product_id=? ORDER BY observed_at DESC,id DESC LIMIT 1000",[id])};
  }
  analogs(id: number, args: any = {}): any[] {
    const p = this.one("SELECT * FROM products WHERE id=?",[id]);
    if (!p) throw new Error("Товар не найден");
    if (!p.connection_type || !p.form_factor) return [];
    const clauses = ["p.marketplace!=?","p.connection_type=?","p.form_factor=?"], bind = [p.marketplace,p.connection_type,p.form_factor];
    if (args.anc) clauses.push("p.anc=1");
    if (args.microphone) clauses.push("p.microphone=1");
    return this.rows(`SELECT p.*,c.price_minor,c.currency,c.region,c.price_kind,c.availability,c.observed_at FROM products p
      LEFT JOIN current_prices c ON c.product_id=p.id WHERE ${clauses.join(" AND ")}
      ORDER BY c.price_minor IS NULL,c.price_minor,p.id LIMIT 100`,bind);
  }
  watch(args: any): void {
    if (!this.one("SELECT id FROM products WHERE id=?",[args.id])) throw new Error("Товар не найден");
    if (!args.minutes) { this.exec("DELETE FROM watchlist WHERE product_id=?",[args.id]); return; }
    if (!Number.isInteger(args.minutes) || args.minutes < 5 || args.minutes > 525600) throw new Error("Интервал: от 5 минут до года");
    this.exec("INSERT INTO watchlist(product_id,interval_minutes,next_at) VALUES(?,?,?) ON CONFLICT(product_id) DO UPDATE SET interval_minutes=excluded.interval_minutes,next_at=excluded.next_at", [args.id,args.minutes,Date.now() + args.minutes * 60000]);
  }
  schedule(): any[] {
    const ids: any[] = [];
    for (const w of this.rows("SELECT w.*,p.marketplace,p.url FROM watchlist w JOIN products p ON p.id=w.product_id WHERE w.next_at<=?",[Date.now()])) {
      const active = this.one("SELECT id,status FROM parse_runs WHERE id=?",[w.last_run_id]);
      if (active && !["succeeded","cancelled"].includes(active.status)) continue;
      this.tx(() => {
        // createRun has its own transaction, so create the small direct run here.
        this.exec("INSERT INTO parse_runs(marketplace,source_url,status,settings,created_at) VALUES(?,?,'running',?,?)",[w.marketplace,w.url,JSON.stringify({limit:1,pages:1,scrolls:0,delay:3}),new Date().toISOString()]);
        const id = this.one("SELECT last_insert_rowid() AS id").id;
        this.exec("INSERT INTO parse_tasks(run_id,kind,url) VALUES(?,'product',?)",[id,w.url]);
        this.exec("UPDATE watchlist SET next_at=?,last_run_id=? WHERE product_id=?",[Date.now() + w.interval_minutes * 60000,id,w.product_id]);
        ids.push(id);
      });
    }
    return ids;
  }
  exportJSON(): any[] {
    const rows = this.rows("SELECT p.*,c.* ,p.id AS pid FROM products p JOIN current_prices c ON c.product_id=p.id ORDER BY p.marketplace,p.id");
    return (["ozon","wb"] as const).map(site => ({marketplace:site,source_url:"extension-export",items:rows.filter(r=>r.marketplace===site).map(r=>({
      external_id:r.external_id,name:r.name,url:r.url,brand:r.brand,model:r.model,
      features:{connection_type:r.connection_type,form_factor:r.form_factor,anc:r.anc === null ? null : !!r.anc,microphone:r.microphone === null ? null : !!r.microphone,battery_hours:r.battery_hours},
      price:decimal(r.price_minor),old_price:decimal(r.old_price_minor),currency:r.currency,region:r.region,price_kind:r.price_kind,
      availability:r.availability,rating:r.rating,reviews_count:r.reviews_count,observed_at:r.observed_at,
    }))})).filter(b=>b.items.length);
  }
  stats(): any {
    return {...this.one("SELECT (SELECT COUNT(*) FROM products) AS products,(SELECT COUNT(*) FROM price_history) AS observations,(SELECT COUNT(*) FROM parse_runs) AS runs,(SELECT COUNT(*) FROM watchlist) AS watching"),
      bytes:this.one("PRAGMA page_count").page_count * this.one("PRAGMA page_size").page_size, backend:"SQLite WASM / OPFS",schema:2};
  }
  call(method: string, args: any = {}): any {
    switch(method) {
      case "stats": return this.stats();
      case "products": return this.products(args);
      case "details": return this.details(Number(args.id));
      case "analogs": return this.analogs(Number(args.id),args);
      case "runs": return this.runs();
      case "runResults": return this.rows("SELECT p.*,h.price_minor,h.old_price_minor,h.currency,h.region,h.price_kind,h.availability,h.rating,h.reviews_count,h.observed_at FROM price_history h JOIN products p ON p.id=h.product_id WHERE h.run_id=? ORDER BY h.id",[args.id]);
      case "createRun": return this.createRun(args);
      case "claim": return this.claim();
      case "bind": return this.bindTask(args.id,args.token,args.tabId);
      case "task": return this.task(args.id);
      case "tasks": return this.rows("SELECT * FROM parse_tasks WHERE run_id=? ORDER BY id",[args.id]);
      case "tasksForTab": return this.tasksForTab(args.tabId);
      case "result": return this.result(args);
      case "changeRun": return this.changeRun(args.id,args.action);
      case "import": return this.importBatch(args);
      case "exportJSON": return this.exportJSON();
      case "watch": return this.watch(args);
      case "watchlist": return this.rows("SELECT w.*,p.name,p.url,p.marketplace FROM watchlist w JOIN products p ON p.id=w.product_id ORDER BY next_at");
      case "report": return this.report(args);
      case "schedule": return this.schedule();
      case "recoverSession": return this.tx(()=>{this.exec("UPDATE parse_tasks SET status='queued',token=NULL,lease_until=NULL WHERE status='running'");this.exec("UPDATE parse_tasks SET tab_id=NULL");return null;});
      case "alerts": return this.rows("SELECT * FROM alerts ORDER BY id DESC LIMIT 100");
      case "pendingAlerts": return this.rows("SELECT * FROM alerts WHERE notified=0 LIMIT 20");
      case "alertNotified": return this.exec("UPDATE alerts SET notified=1 WHERE id=?",[args.id]);
      case "errors": return this.rows("SELECT * FROM error_log ORDER BY id DESC LIMIT 200");
      case "localEvent": return this.exec("INSERT INTO local_events(run_id,created_at,stage,data) VALUES(?,?,?,?)",[args.runId,new Date().toISOString(),args.stage,JSON.stringify(args.data||{})]);
      case "localEvents": return this.rows("SELECT * FROM local_events WHERE run_id=? AND id>? ORDER BY id LIMIT 500",[args.runId,args.after||0]);
      case "cleanup": return this.tx(()=>{this.exec("DELETE FROM error_log WHERE created_at<?",[new Date(Date.now()-30*86400000).toISOString()]);this.exec("DELETE FROM staged_products WHERE run_id IN (SELECT id FROM parse_runs WHERE status='cancelled')");return this.stats();});
      default: throw new Error("Неизвестная операция базы");
    }
  }
  report(args:any): any[] {
    const id=Number(args.id)||0,days=Math.max(1,Math.min(Number(args.days)||30,3650));
    const since=new Date(Date.now()-days*86400000).toISOString();
    switch(args.code){
      case "Q01": return this.analogs(id,args);
      case "Q02": return this.products({...args,limit:500}).items;
      case "Q03": return this.rows(`SELECT p.*,c.price_minor,c.currency,c.observed_at FROM products p JOIN products source ON source.id=?
        LEFT JOIN current_prices c ON c.product_id=p.id WHERE p.marketplace!=source.marketplace
        AND source.brand IS NOT NULL AND source.model IS NOT NULL AND length(trim(source.model))>0
        AND lower(trim(p.brand))=lower(trim(source.brand)) AND lower(trim(p.model))=lower(trim(source.model)) LIMIT 500`,[id]);
      case "Q04": return this.rows(`SELECT p.marketplace,c.region,c.currency,c.price_kind,MIN(c.price_minor) AS min_price_minor,COUNT(*) AS offers
        FROM current_prices c JOIN products p ON p.id=c.product_id WHERE c.price_minor IS NOT NULL AND c.availability!='out_of_stock'
        GROUP BY p.marketplace,c.region,c.currency,c.price_kind LIMIT 500`);
      case "Q05": return this.rows(`WITH ranked AS (SELECT p.name,p.marketplace,c.price_minor,c.currency,c.region,c.price_kind,c.observed_at,
        ROW_NUMBER() OVER(PARTITION BY c.region,c.currency,c.price_kind ORDER BY c.price_minor,p.id) AS position
        FROM current_prices c JOIN products p ON p.id=c.product_id WHERE c.price_minor IS NOT NULL AND c.availability!='out_of_stock' AND c.observed_at>=?)
        SELECT * FROM ranked WHERE position<=5 ORDER BY currency,region,price_kind,position LIMIT 500`,[since]);
      case "Q06": return this.rows("SELECT observed_at,price_minor,currency,region,price_kind,availability FROM price_history WHERE product_id=? AND observed_at>=? ORDER BY observed_at DESC,id DESC LIMIT 1000",[id,since]);
      case "Q07": return this.rows(`WITH changes AS (
        SELECT h.*, LAG(price_minor) OVER(PARTITION BY product_id,region,currency,price_kind ORDER BY observed_at,id) AS previous_price_minor,
        ROW_NUMBER() OVER(PARTITION BY product_id,region,currency,price_kind ORDER BY observed_at DESC,id DESC) AS position
        FROM price_history h
        ) SELECT p.name,p.marketplace,c.price_minor,c.previous_price_minor,c.currency,c.region,c.price_kind,c.observed_at
        FROM changes c JOIN products p ON p.id=c.product_id WHERE c.position=1 AND c.observed_at>=?
        AND c.price_minor<c.previous_price_minor AND c.availability='in_stock' AND c.region!='unknown' AND c.price_kind!='unknown' LIMIT 500`,[since]);
      case "Q08": return this.rows(`SELECT p.name,p.marketplace,c.rating,c.reviews_count,c.price_minor,c.currency,c.observed_at
        FROM current_prices c JOIN products p ON p.id=c.product_id WHERE c.rating>=? AND c.reviews_count>=?
        ORDER BY c.rating DESC,c.reviews_count DESC LIMIT 500`,[Number(args.minRating)||4.5,Number(args.minReviews)||100]);
      case "Q09": return this.rows(`SELECT p.connection_type,p.form_factor,c.region,c.currency,c.price_kind,COUNT(*) AS offers,
        MIN(c.price_minor) AS min_price_minor,AVG(c.price_minor) AS avg_price_minor,MAX(c.price_minor) AS max_price_minor
        FROM current_prices c JOIN products p ON p.id=c.product_id WHERE c.price_minor IS NOT NULL AND c.availability!='out_of_stock' AND c.observed_at>=?
        GROUP BY p.connection_type,p.form_factor,c.region,c.currency,c.price_kind LIMIT 500`,[since]);
      case "Q10": return this.rows(`SELECT id,marketplace,source_url,status,created_at,finished_at,error FROM parse_runs
        WHERE status!='succeeded' OR created_at<? ORDER BY id DESC LIMIT 500`,[since]);
      default: throw new Error("Неизвестный именованный запрос");
    }
  }
}
