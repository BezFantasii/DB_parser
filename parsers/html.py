"""Extract one product only; do not pair parallel arrays or scrape all page prices."""
import json
import re
from decimal import Decimal

from bs4 import BeautifulSoup

from contracts import normalize_item, product_url
from features import extract_all


def _products(value):
    if isinstance(value, list):
        for child in value:
            yield from _products(child)
    elif isinstance(value, dict):
        kinds = value.get("@type", [])
        if isinstance(kinds, str):
            kinds = [kinds]
        if "Product" in kinds:
            yield value
        if "@graph" in value:
            yield from _products(value["@graph"])


def _text(soup, selectors):
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = node.get("content") or node.get("data-price") or node.get_text(" ", strip=True)
            if value:
                return value
    return None


def _money(text):
    if text is None:
        return None
    match = re.search(r"\d[\d\s\xa0\u202f]*(?:[.,]\d{1,2})?", str(text))
    return Decimal(re.sub(r"\s", "", match.group()).replace(",", ".")) if match else None


def parse_product(source, url, marketplace):
    url, external_id = product_url(url, marketplace)
    soup = BeautifulSoup(source, "html.parser")
    if soup.select_one('[data-widget="searchResults"], [data-widget="searchResultsV2"]') and not soup.select_one("h1"):
        raise ValueError("Получена выдача вместо карточки")
    text = soup.get_text("\n", strip=True)
    if "Похоже, нет соединения" in text and "Обратиться в поддержку" in text:
        raise ValueError("Получена страница отказа в доступе")
    candidates = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            candidates.extend(_products(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError):
            continue
    # If structured data identifies a different product (e.g. recommendations), skip it.
    matching = []
    for candidate in candidates:
        candidate_url = candidate.get("url")
        if candidate_url:
            try:
                if product_url(candidate_url, marketplace)[1] != external_id:
                    continue
            except ValueError:
                continue
        matching.append(candidate)
    data = matching[0] if len(matching) == 1 else {}
    name = _text(soup, ("h1", '[itemprop="name"]', "[class*='productTitle']")) or data.get("name")
    if not name:
        raise ValueError("Название карточки не найдено")
    brand = data.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if not isinstance(brand, str):
        brand = _text(soup, ('[itemprop="brand"]', '[data-widget="webBrand"] a', '[class*="product-page__brand"]'))
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else {}
    if not isinstance(offers, dict):
        offers = {}
    # Never use lowPrice from AggregateOffer as the price of this exact offer.
    price_text = _text(soup, ('[itemprop="price"]', '[data-widget="webPrice"] [data-price]',
                              '[class*="price-block__final-price"]', '[class*="priceBlockFinalPrice"]'))
    price = _money(price_text)
    if price is None:
        price = _money(offers.get("price"))
    if price is None:
        container = soup.select_one('[data-widget="webPrice"], [class*="price-block"], [class*="priceBlock"]')
        if container:
            for node in container.select("span, ins"):
                if node.find_parent(["del", "s"]) or "line-through" in node.get("style", ""):
                    continue
                value = node.get_text(" ", strip=True)
                if re.fullmatch(r"\d[\d\s\xa0\u202f]*(?:[.,]\d{1,2})?\s*₽", value):
                    price = _money(value)
                    break
    if price is None and offers.get("availability", "").split("/")[-1] != "OutOfStock":
        raise ValueError("Текущая цена не найдена; цены из рекомендаций не используются")
    old_price = _money(_text(soup, ('[data-widget="webPrice"] del', '[data-widget="webPrice"] s',
                                   '[class*="price-block"] del', '[class*="price-block"] s')))
    aggregate = data.get("aggregateRating", {})
    if not isinstance(aggregate, dict):
        aggregate = {}
    rating_text = _text(soup, ('[itemprop="ratingValue"]', '[data-widget="webSingleProductScore"]'))
    rating = _money(aggregate.get("ratingValue") if aggregate.get("ratingValue") is not None else rating_text)
    count = aggregate.get("reviewCount", aggregate.get("ratingCount"))
    if count is None:
        count = _text(soup, ('[itemprop="reviewCount"]', '[class*="product-review__count"]'))
    if count is not None:
        digits = re.sub(r"\s", "", str(count))
        count = int(digits) if digits.isdigit() else None
    # Ozon uses dl/table attributes, WB can supply an expanded specs dialog.
    specs = []
    for term in soup.select('dt'):
        definition = term.find_next_sibling("dd")
        if definition:
            specs += [term.get_text(" ", strip=True), definition.get_text(" ", strip=True)]
    for row in soup.select('[data-widget="webCharacteristics"] tr, .product-params__row'):
        cells = row.select("th, td, dt, dd")
        if len(cells) >= 2:
            specs += [cells[0].get_text(" ", strip=True), cells[1].get_text(" ", strip=True)]
    item = {"features": extract_all(name, "\n".join(specs)), "external_id": external_id,
            "name": name, "url": url, "brand": brand, "price": price, "old_price": old_price,
            "rating": rating, "reviews_count": count}
    currency = offers.get("priceCurrency")
    if currency and currency != "RUB":
        item["currency"] = currency
    return normalize_item(item, marketplace)
