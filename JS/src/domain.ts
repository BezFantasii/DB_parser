export type Marketplace = "ozon" | "wb";
export type Features = {
  connection_type: "wired" | "bluetooth" | "radio" | null;
  form_factor: "in_ear" | "on_ear" | "over_ear" | null;
  anc: boolean | null;
  microphone: boolean | null;
  battery_hours: number | null;
};
export type Product = {
  external_id: string; name: string; url: string; brand: string | null;
  model: string | null; features: Features; price: string | null;
  old_price: string | null; rating: number | null; reviews_count: number | null;
  currency: string; region: string; price_kind: string; availability: string;
  observed_at: string;
};
export const HOSTS: Record<Marketplace, string[]> = {
  ozon: ["ozon.ru", "www.ozon.ru"], wb: ["wildberries.ru", "www.wildberries.ru"],
};
export function marketplaceFor(url: string): Marketplace {
  const u = new URL(url);
  for (const site of ["ozon", "wb"] as const) if (HOSTS[site].includes(u.hostname)) return site;
  throw new Error("Нужен адрес Ozon или Wildberries");
}
export function siteUrl(url: string, site: Marketplace): URL {
  const u = new URL(url);
  if (!HOSTS[site]?.includes(u.hostname) || u.protocol !== "https:" || u.username || u.password || u.port) {
    throw new Error("Нужен HTTPS-адрес выбранной площадки");
  }
  return u;
}
export function productUrl(url: string, site: Marketplace): {url: string; id: string} {
  const u = siteUrl(url, site);
  const match = u.pathname.match(site === "wb" ? /^\/catalog\/(\d+)\/detail\.aspx\/?$/ : /^\/product\/(?:[^/]*-)?(\d+)\/?$/);
  if (!match) throw new Error("Нужна ссылка на карточку товара");
  u.hostname = site === "wb" ? "www.wildberries.ru" : "www.ozon.ru";
  u.search = ""; u.hash = "";
  return {url: u.href, id: match[1]};
}
export function sourceUrl(source: string, site: Marketplace): string {
  if (/^https?:/i.test(source)) return siteUrl(source, site).href;
  if (!source.trim()) throw new Error("Укажите запрос или URL");
  const u = new URL(site === "ozon" ? "https://www.ozon.ru/search/" : "https://www.wildberries.ru/catalog/0/search.aspx");
  u.searchParams.set(site === "ozon" ? "text" : "search", source.trim());
  return u.href;
}
/** Strict decimal conversion without floating point multiplication. */
export function scaled(value: unknown, field = "число", scale = 2, maximum = 99999999999999): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" && typeof value !== "number") throw new Error(`${field}: ожидается число`);
  const text = String(value).trim();
  const match = text.match(/^(\d+)(?:\.(\d+))?$/);
  if (!match || (match[2] || "").length > scale) throw new Error(`${field}: неверное десятичное число`);
  const units = BigInt(match[1]) * (10n ** BigInt(scale)) + BigInt((match[2] || "").padEnd(scale, "0") || "0");
  if (units > BigInt(maximum)) throw new Error(`${field}: вне диапазона`);
  return Number(units);
}
export function decimal(units: number | null, scale = 2): string | null {
  if (units === null) return null;
  return `${Math.floor(units / 10 ** scale)}.${String(units % 10 ** scale).padStart(scale, "0")}`;
}
const textOf = (name: string) => name.toLowerCase().replaceAll("ё", "е");
const token = (s: string) => new RegExp(`(?<![a-z0-9])(?:${s})(?![a-z0-9])`);
function connection(t: string): Features["connection_type"] {
  if (/радиоканал|2[.,]4\s?g/.test(t)) return "radio";
  if (/беспровод|bluetooth|блютуз|блютус/.test(t) || token("bt|tws").test(t)) return "bluetooth";
  return t.includes("проводн") ? "wired" : null;
}
function form(t: string): Features["form_factor"] {
  if (/накладн/.test(t)) return "on_ear";
  if (/полноразмер|мониторн/.test(t)) return "over_ear";
  if (/вкладыш|внутриканал|вакуумн|капельк/.test(t) || token("tws").test(t)) return "in_ear";
  return t.includes("больш") ? "over_ear" : null;
}
function anc(t: string): boolean | null {
  if (/без\s+(?:активного\s+)?шумоподавл|без\s+anc(?![a-z0-9])/.test(t)) return false;
  if (token("anc").test(t) || /активн[\p{L}\p{N}_]*\s+(?:шумоподавл|подавлени[\p{L}\p{N}_]*\s+шум)|active\s+noise/u.test(t)) return true;
  return /шумоподавл/.test(t) && !/микрофон/.test(t) && !token("mic").test(t) ? true : null;
}
function mic(t: string): boolean | null {
  if (/без\s+микрофон/.test(t)) return false;
  return /микрофон/.test(t) || token("mic").test(t) ? true : null;
}
function battery(t: string): number | null {
  const m = t.match(/(\d+(?:[.,]\d+)?)\s*(?:часов|часа|час|ч|hours?|h)(?![a-zа-я])/);
  if (!m) return null;
  const n = Number(m[1].replace(",", "."));
  return n > 0 && n < 1000 ? n : null;
}
export function extractFeatures(name: string, specs = ""): Features {
  const t = textOf(name);
  const result: Features = {connection_type: connection(t), form_factor: form(t), anc: anc(t), microphone: mic(t), battery_hours: battery(t)};
  const lines = specs.split(/\r?\n/).map(x => textOf(x.trim())).filter(Boolean);
  const labels = new Map<string, string>();
  for (let i = 0; i < lines.length - 1; i++) if (!labels.has(lines[i])) labels.set(lines[i], lines[i + 1]);
  const link = ["тип подключения", "беспроводные интерфейсы", "вид наушников"].map(k => labels.get(k) || "").join(" ");
  result.connection_type = connection(link) ?? result.connection_type;
  for (const key of ["вид наушников", "тип крепления наушников"]) {
    const v = labels.get(key) || "";
    const f = form(v) ?? (/ушной раковин|earbud/.test(v) ? "in_ear" : null);
    if (f) { result.form_factor = f; break; }
  }
  const options = labels.get("доп. опции наушников") || "";
  if (/шумоподавл|подавлени[\p{L}_]*\s+шум/u.test(options) && !/без|шумоподавлени[\p{L}_]*\s+микрофон/u.test(options)) result.anc = true;
  if (options.includes("микрофон") && !/без\s+микрофон/.test(options)) result.microphone = true;
  result.battery_hours = battery(labels.get("время работы от аккумулятора, до") || "") ?? result.battery_hours;
  return result;
}
export function normalize(raw: unknown, site: Marketplace): Product {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Товар должен быть объектом");
  const r = raw as Record<string, any>;
  const {url, id} = productUrl(r.url, site);
  if (r.external_id !== undefined && String(r.external_id) !== id) throw new Error("Артикул не соответствует URL");
  if (typeof r.name !== "string" || !r.name.trim() || r.name.length > 10000) throw new Error("Неверное название");
  const features = extractFeatures(r.name);
  if (r.features !== undefined) {
    if (!r.features || typeof r.features !== "object" || Array.isArray(r.features)) throw new Error("Неверные характеристики");
    for (const [key, value] of Object.entries(r.features)) {
      if (!(key in features)) throw new Error("Неизвестный признак");
      (features as any)[key] = value;
    }
  }
  if (features.connection_type !== null && !["wired", "bluetooth", "radio"].includes(features.connection_type)) throw new Error("Неверное подключение");
  if (features.form_factor !== null && !["in_ear", "on_ear", "over_ear"].includes(features.form_factor)) throw new Error("Неверный форм-фактор");
  for (const key of ["anc", "microphone"] as const) if (features[key] !== null && typeof features[key] !== "boolean") throw new Error("Неверный boolean");
  const hours = scaled(features.battery_hours, "время работы", 1, 9999);
  features.battery_hours = hours === null ? null : hours / 10;
  const count = r.reviews_count ?? null;
  if (count !== null && (!Number.isInteger(count) || typeof count !== "number" || count < 0 || count > 2147483647)) throw new Error("Неверное число отзывов");
  const currency = r.currency ?? "RUB", region = r.region ?? "unknown";
  const kind = r.price_kind ?? "unknown", availability = r.availability ?? "unknown";
  if (typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)) throw new Error("Неверная валюта");
  if (typeof region !== "string" || !region.trim() || region.length > 200) throw new Error("Неверный регион");
  if (!["unknown", "regular", "card", "subscription"].includes(kind)) throw new Error("Неверный тип цены");
  if (!["unknown", "in_stock", "out_of_stock"].includes(availability)) throw new Error("Неверное наличие");
  const observed = r.observed_at ?? new Date().toISOString();
  if (typeof observed !== "string" || !/(?:Z|[+-]\d\d:\d\d)$/.test(observed) || !Number.isFinite(Date.parse(observed))) throw new Error("Нужна дата с часовым поясом");
  for (const key of ["brand", "model"]) if (r[key] != null && typeof r[key] !== "string") throw new Error(`Неверное поле ${key}`);
  const rating = scaled(r.rating, "рейтинг", 2, 500);
  return {external_id: id, url, name: r.name.trim().replace(/\s+/g, " "), brand: r.brand ?? null, model: r.model ?? null,
    features, price: decimal(scaled(r.price, "цена")), old_price: decimal(scaled(r.old_price, "старая цена")),
    rating: rating === null ? null : rating / 100, reviews_count: count, currency, region: region.trim(), price_kind: kind,
    availability, observed_at: new Date(observed).toISOString()};
}
export function validateBatch(payload: any): {marketplace: Marketplace; source_url: string; items: Product[]} {
  if (!payload || !["ozon", "wb"].includes(payload.marketplace)) throw new Error("marketplace: ozon или wb");
  if (typeof payload.source_url !== "string" || !payload.source_url.trim() || payload.source_url.length > 4096) throw new Error("Неверный источник");
  if (!Array.isArray(payload.items) || !payload.items.length || payload.items.length > 500) throw new Error("Пакет: от 1 до 500 товаров");
  const items = payload.items.map((r: unknown) => normalize(r, payload.marketplace));
  const keys = items.map((x: Product) => JSON.stringify([x.external_id, x.region, x.currency, x.price_kind]));
  if (new Set(keys).size !== keys.length) throw new Error("Повтор товара с тем же контекстом");
  return {marketplace: payload.marketplace, source_url: payload.source_url, items};
}
