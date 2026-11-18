"""Search offers via a separate ordinary Chrome session; no extension tab required."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote, urljoin, urlsplit

from contracts import normalize_item, product_url


def texts(value, depth=0):
    if depth > 10:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value[:100] for s in texts(v, depth+1)]
    if isinstance(value, dict):
        if re.search(r"ORIGINAL|OLD", str(value.get("textStyle", "")), re.I):
            return []
        return [s for k,v in value.items() if not re.search(r"old|original", k, re.I) for s in texts(v, depth+1)]
    return []


def parse_search(payload, limit=5):
    items = {}
    for key, raw in payload.get("widgetStates", {}).items():
        if not re.match(r"searchResults|tileGridDesktop", key, re.I):
            continue
        try:
            state = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            continue
        for tile in state.get("items", []) if isinstance(state, dict) else []:
            try:
                url, external_id = product_url(urljoin("https://www.ozon.ru", tile.get("action", {}).get("link", "")), "ozon")
                main = tile.get("mainState", [])
                price = next((s["priceV2"] for s in main if "priceV2" in s), {})
                match = next((m for t in texts(price) if (m := re.search(r"(\d[\d\s]*(?:[.,]\d{1,2})?)\s*₽", t))), None)
                if not match:
                    continue
                title = next((s for s in main if s.get("id") == "name"), None) or next((s for s in main if "textDS" in s or "textAtom" in s), {})
                name = (title.get("textDS") or title.get("textAtom") or {}).get("text", "")
                labels = next((s["labelListV2"] for s in main if s.get("labelListV2", {}).get("testInfo", {}).get("automatizationId") == "tile-list-labels"), {})
                brand = next((s["text"]["text"] for s in labels.get("items", []) if s.get("text", {}).get("text")), None)
                if brand and brand.lower() == "бренд проверен":
                    brand = None
                item = normalize_item({"url":url,"external_id":external_id,"name":" · ".join(v for v in (brand,name) if v),"brand":brand,
                    "price":re.sub(r"\s", "", match[1]).replace(",", "."),"currency":"RUB","region":"unknown",
                    "price_kind":"card" if price.get("priceStyle", {}).get("styleType") == "CARD_PRICE" else "unknown",
                    "observed_at":datetime.now(timezone.utc).isoformat()}, "ozon")
                items[url] = item
                if len(items) >= limit:
                    return list(items.values())
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
    return list(items.values())


def collect(source, options, emit):
    from backend.ozon_session import OzonSession, valid_ozon_url
    from backend.profiles import managed_profile
    valid_ozon_url(source)
    limit = options.get("limit", 5)
    profile_root = Path(os.environ["PROFILE_ROOT"]) if os.environ.get("PROFILE_ROOT") else Path(__file__).resolve().parent/"data"
    profile_name = "ozon-session" if os.environ.get("PROFILE_ROOT") else "ozon-chrome-session"
    with managed_profile(profile_name,root=profile_root) as profile, OzonSession(profile=profile,wait=options.get("timeout",30)) as session:
        emit("browser.ready", {"engine":"chrome-session","source":"backend"})
        if re.match(r"^/product/", urlsplit(source).path):
            return session.collect(source,limit=1)
        session.navigate("https://www.ozon.ru/", "home")
        session.page.wait_for_timeout(2500)
        target = urlsplit(source)
        endpoint = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="+quote(target.path+("?"+target.query if target.query else ""),safe="")
        emit("page.loading", {"url":source,"engine":"chrome-session"})
        response = session.page.evaluate("""async ({endpoint,timeout})=>{
          const r=await fetch(endpoint,{credentials:'include',signal:AbortSignal.timeout(timeout)});
          return {status:r.status,body:await r.text()};
        }""", {"endpoint":endpoint,"timeout":min(options.get("timeout",30),45)*1000})
        if response["status"] != 200:
            raise RuntimeError(f"Ozon HTTP {response['status']}: серверная сессия не имеет доступа; нужна доступная сессия Chrome")
        if len(response["body"]) > 8_000_000:
            raise RuntimeError("Ответ Ozon слишком большой")
        try:
            items = parse_search(json.loads(response["body"]),limit)
        except ValueError:
            raise RuntimeError("Ozon вернул проверку безопасности или HTML вместо JSON") from None
        if not items:
            raise RuntimeError("Ozon не вернул товары с ценами: проверьте серверную сессию и запрос")
        emit("listing.collected", {"items":len(items),"engine":"chrome-session"})
        for item in items:
            emit("product.parsed", {"external_id":item["external_id"],"name":item["name"]})
        return items
