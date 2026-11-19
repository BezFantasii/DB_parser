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
    if "Похоже, нет соединения" in " ".join(text.split()) and "Обратиться в поддержку" in " ".join(text.split()):
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
    if marketplace == "wb":
        # Current WB product pages may use the only h1 for the rating (e.g. "5,0").
        # Prefer the explicitly labelled product name, never an arbitrary h1.
        name_selectors = (
            '[data-testid="product-line-name"]',
            '[class*="productImtName"]',
            '[itemprop="name"]',
            '[class*="productTitle"]',
            'h1',
        )
    else:
        name_selectors = ("h1", '[itemprop="name"]', "[class*='productTitle']")
    name = _text(soup, name_selectors) or data.get("name")
    if not name:
        raise ValueError("Название карточки не найдено")
    brand = data.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if not isinstance(brand, str):
        brand = _text(soup, ('[itemprop="brand"]', '[data-widget="webBrand"] a', "[class*='product-page__brand']", "[class*='brand-name']", "a[href*='/brand/']"))
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else {}
    if not isinstance(offers, dict):
        offers = {}
    # Never use lowPrice from AggregateOffer as the price of this exact offer.
    if marketplace == "wb":
        # WB exposes several amounts on a product page (wallet price, regular
        # price, old price, recommendations). Only semantically labelled
        # current-price nodes are trusted; page-wide/positional price scraping
        # is deliberately forbidden.
        price_selectors = (
            # Current WB product-card DOM (observed in a live saved page).
            # This is the regular product price; the nearby wallet/button price
            # is intentionally not selected.
            '[data-testid="product-price-final"]',
            '[class*="priceBlockFinalPrice"]',
            '[class*="price-block__final-price"]',
            '[data-testid="price-block__final-price"]',
            '[itemprop="price"]',
        )
    else:
        price_selectors = (
            '[itemprop="price"]', '[data-widget="webPrice"] [data-price]',
            '[class*="price-block__final-price"]', '[class*="priceBlockFinalPrice"]',
        )
    price_text = _text(soup, price_selectors)
    price = _money(price_text)
    if price is None:
        price = _money(offers.get("price"))
    if price is None and marketplace == "ozon":
        # Ozon's webPrice container is product-scoped. WB has no equivalent
        # stable generic container, so it must not use this fallback.
        container = soup.select_one('[data-widget="webPrice"]')
        if container:
            for node in container.select("span, ins"):
                if node.find_parent(["del", "s"]) or "line-through" in node.get("style", ""):
                    continue
                value = node.get_text(" ", strip=True)
                if re.fullmatch(r"\d[\d\s\xa0\u202f]*(?:[.,]\d{1,2})?\s*₽", value):
                    price = _money(value)
                    break
    availability = str(offers.get("availability") or "").split("/")[-1]
    if price is None and availability != "OutOfStock":
        raise ValueError("Текущая цена не найдена; цены из рекомендаций не используются")
    old_price = _money(_text(soup, (
        '[data-widget="webPrice"] del', '[data-widget="webPrice"] s',
        '[class*="priceBlockOldPrice"]', '[class*="price-block__old-price"]',
        '[class*="price-block"] del', '[class*="price-block"] s',
    )))
    aggregate = data.get("aggregateRating", {})
    if not isinstance(aggregate, dict):
        aggregate = {}
    rating_text = _text(soup, ('[itemprop="ratingValue"]', '[data-widget="webSingleProductScore"]', "[class*='product-review__rating']", "[class*='product-page__rating']", '[data-testid="product-line-rating"]', "[data-testid*='rating']"))
    rating = _money(aggregate.get("ratingValue") if aggregate.get("ratingValue") is not None else rating_text)
    count = aggregate.get("reviewCount", aggregate.get("ratingCount"))
    if count is None:
        count = _text(soup, ('[itemprop="reviewCount"]', "[class*='product-review__count']", "[class*='product-page__reviews']", '[data-testid="product-line-rating"]', "[data-testid*='review-count']"))
    if count is not None:
        # WB's product-line rating combines score and review count, e.g.
        # "5 · 23 427 оценок". In that case capture the number immediately
        # before the explicit "оценок" label, not the leading score.
        count_text = str(count)
        labelled = re.search(r"(\d{1,3}(?:[ \xa0\u202f\u2009]\d{3})+|\d+)\s*оцен", count_text, re.IGNORECASE)
        match = labelled or re.search(
            r"(?<![\d.,])(\d{1,3}(?:[ \xa0\u202f\u2009]\d{3})+|\d+)(?![\d.,])",
            count_text,
        )
        digits = re.sub(r"\s", "", match.group(1)) if match else ""
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
