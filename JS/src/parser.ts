import {extractFeatures, normalize, productUrl, siteUrl, type Marketplace, type Product} from "./domain.ts";

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
function text(root: ParentNode, selectors: string[]): string | null {
  for (const selector of selectors) {
    const el = root.querySelector(selector);
    const value = el?.getAttribute("content") || el?.getAttribute("data-price") || el?.textContent?.trim();
    if (value) return value.replace(/\s+/g, " ");
  }
  return null;
}
function money(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const match = String(v).match(/\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?/);
  return match ? match[0].replace(/\s/g, "").replace(",", ".") : null;
}
function* structured(value: any): Generator<any> {
  if (Array.isArray(value)) for (const child of value) yield* structured(child);
  else if (value && typeof value === "object") {
    if ([value["@type"]].flat().includes("Product")) yield value;
    if (value["@graph"]) yield* structured(value["@graph"]);
  }
}
export function checkBlocked(root: Document): void {
  const body = (root.body?.innerText || root.body?.textContent || "").replace(/\s+/g," ");
  const title = root.title.toLowerCase();
  if ((body.includes("Похоже, нет соединения") && body.includes("Обратиться в поддержку")) ||
      /доступ ограничен|доступ заблокирован|access denied|captcha|проверка безопасности/.test(title) ||
      /подтвердите,? что вы не робот|подтвердите,? что вы человек|подозрительная активность|доступ временно ограничен|доступ ограничен|access denied/i.test(body.slice(0,5000))) {
    throw new Error("BLOCKED: площадка ограничила доступ. Откройте рабочую вкладку, пройдите проверку и продолжите сбор.");
  }
}
export function parseDocument(root: Document, url: string, site: Marketplace, expandedSpecs = ""): Product {
  checkBlocked(root);
  const {id, url: canonical} = productUrl(url, site);
  // Port of the current Python WB algorithm; keep the second/third RUB amounts intact.
  if(site==="wb" && root.querySelector('[class*="productTitle"]')){
    const parts:string[]=[];
    const walker=root.createTreeWalker(root.body,NodeFilter.SHOW_TEXT);
    while(walker.nextNode()){const n=walker.currentNode;const value=n.textContent?.trim();if(value&&!n.parentElement?.closest("script,style"))parts.push(value);}
    const pageText=parts.join("\n");
    const amounts=[...pageText.matchAll(/(\d[\d\s\u00a0]*\d|\d)\s*₽/g)].slice(0,3).map(m=>m[1].replace(/\D/g,""));
    if(amounts.length===3){
      const name=root.querySelector('[class*="productTitle"]')!.textContent!.trim();
      const brand=pageText.match(/^(\S+)\s*\//m)?.[1]||null;
      const rating=pageText.match(/^(\d,\d)\s*/m)?.[1].replace(",", ".")||null;
      const count=pageText.match(/^(\d[\d \u00a0\u2009]*)оцен/m)?.[1].replace(/\D/g,"");
      return normalize({external_id:id,url:canonical,name,brand,price:amounts[1],old_price:amounts[2],rating,reviews_count:count?Number(count):null,
        features:extractFeatures(name,expandedSpecs),price_kind:"unknown",region:"unknown",availability:"unknown",observed_at:new Date().toISOString()},site);
    }
  }
  if (root.querySelector('[data-widget="searchResults"], [data-widget="searchResultsV2"]') && !root.querySelector("h1")) throw new Error("Получена выдача вместо карточки");
  const candidates: any[] = [];
  for (const script of root.querySelectorAll('script[type="application/ld+json"]')) {
    try { candidates.push(...structured(JSON.parse(script.textContent || ""))); } catch { /* A malformed JSON-LD block is not the card. */ }
  }
  const matching = candidates.filter(x => {
    if (!x.url) return true;
    try { return productUrl(new URL(x.url, url).href, site).id === id; } catch { return false; }
  });
  const data = matching.length === 1 ? matching[0] : {};
  const name = text(root, ["h1", '[itemprop="name"]', '[class*="productTitle"]']) || data.name;
  if (typeof name !== "string" || !name.trim()) throw new Error("Название карточки не найдено");
  const brand = typeof data.brand === "string" ? data.brand : data.brand?.name || text(root, ['[itemprop="brand"]', '[data-widget="webBrand"] a', '[class*="product-page__brand"]']);
  let offers = data.offers || {};
  if (Array.isArray(offers)) offers = offers.length === 1 ? offers[0] : {};
  let price = money(text(root, ['[itemprop="price"]', '[data-widget="webPrice"] [data-price]', '[class*="price-block__final-price"]', '[class*="priceBlockFinalPrice"]'])) || money(offers.price);
  if (price === null) {
    const container = root.querySelector('[data-widget="webPrice"], [class*="price-block"], [class*="priceBlock"]');
    for (const node of container?.querySelectorAll("span, ins") || []) {
      if (node.closest("del, s") || /line-through/.test(node.getAttribute("style") || "")) continue;
      if (/^\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,2})?\s*₽$/.test(node.textContent?.trim() || "")) { price = money(node.textContent); break; }
    }
  }
  const availability = String(offers.availability || "").split("/").at(-1);
  if (price === null && availability !== "OutOfStock") throw new Error("Текущая цена не найдена; цены рекомендаций не используются");
  const aggregate = data.aggregateRating || {};
  const count = aggregate.reviewCount ?? aggregate.ratingCount ?? text(root, ['[itemprop="reviewCount"]', '[class*="product-review__count"]']);
  const digits = count == null ? "" : String(count).replace(/\s/g, "");
  const specs: string[] = [];
  for (const term of root.querySelectorAll("dt")) {
    const dd = term.nextElementSibling;
    if (dd?.tagName === "DD") specs.push(term.textContent?.trim() || "", dd.textContent?.trim() || "");
  }
  for (const row of root.querySelectorAll('[data-widget="webCharacteristics"] tr, .product-params__row')) {
    const cells = row.querySelectorAll("th,td,dt,dd");
    if (cells.length >= 2) specs.push(cells[0].textContent?.trim() || "", cells[1].textContent?.trim() || "");
  }
  return normalize({external_id: id, url: canonical, name, brand, price,
    old_price: money(text(root, ['[data-widget="webPrice"] del', '[data-widget="webPrice"] s', '[class*="price-block"] del', '[class*="price-block"] s'])),
    rating: money(aggregate.ratingValue ?? text(root, ['[itemprop="ratingValue"]', '[data-widget="webSingleProductScore"]'])),
    reviews_count: /^\d+$/.test(digits) ? Number(digits) : null,
    features: extractFeatures(name, expandedSpecs || specs.join("\n")), currency: offers.priceCurrency || "RUB",
    availability: availability === "OutOfStock" ? "out_of_stock" : availability === "InStock" ? "in_stock" : "unknown",
    price_kind: "unknown", region: "unknown", observed_at: new Date().toISOString()}, site);
}
export function collectLinks(root: Document, url: string, site: Marketplace): string[] {
  const links = new Map<string, string>();
  for (const a of root.querySelectorAll("a[href]")) {
    try { const p = productUrl(new URL(a.getAttribute("href")!, url).href, site); links.set(p.id, p.url); } catch { /* Non-product link. */ }
  }
  return [...links.values()];
}
export async function collectPage(site: Marketplace, kind: string, limit = 30, scrolls = 3): Promise<Product | string[]> {
  siteUrl(location.href, site);
  const deadline = Date.now() + 35000;
  if (kind === "listing") {
    let links: string[] = [];
    while(Date.now()<deadline){checkBlocked(document);links=collectLinks(document,location.href,site);if(links.length)break;await sleep(700);}
    for (let step = 0; step <= scrolls && Date.now() < deadline; step++) {
      checkBlocked(document);
      const found = collectLinks(document, location.href, site);
      links = [...new Set([...links, ...found])];
      if (links.length >= limit) break;
      window.scrollBy(0, 1400);
      await sleep(1500);
    }
    if (!links.length) throw new Error("Товарные ссылки не найдены: проверьте доступ и разметку");
    return links.slice(0, limit);
  }
  let last: unknown = new Error("Карточка не загрузилась");
  while (Date.now() < deadline) {
    checkBlocked(document);
    try {
      let specs = "";
      if (site === "wb") {
        const button = [...document.querySelectorAll<HTMLElement>("button,a,[role='button']")].find(x => x.textContent?.trim() === "Характеристики и описание");
        if (button) {
          button.scrollIntoView({block:"center"});button.click();
          await sleep(500);
          const dialog = [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].find(x => x.innerText.includes("Характеристики и описание"));
          specs = dialog?.innerText || "";
        }
      }
      return parseDocument(document, location.href, site, specs);
    } catch (error) { last = error; await sleep(800); }
  }
  throw last;
}
