"""WB-compatible dictionaries shared by parsers, imports and the ingest server."""
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

FEATURE_KEYS = ("connection_type", "form_factor", "anc", "microphone", "battery_hours")
ITEM_KEYS = ("features", "external_id", "name", "url", "brand", "price", "old_price", "rating", "reviews_count")
HOSTS = {"wb": {"wildberries.ru", "www.wildberries.ru"}, "ozon": {"ozon.ru", "www.ozon.ru"}}


def product_url(url, marketplace):
    if marketplace not in HOSTS or not isinstance(url, str):
        raise ValueError("Неизвестная площадка или неверный URL")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in HOSTS[marketplace]
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise ValueError("Нужна HTTPS-ссылка выбранной площадки")
    pattern = r"/catalog/(\d+)/detail\.aspx/?$" if marketplace == "wb" else r"/product/(?:[^/]*-)?(\d+)/?$"
    match = re.fullmatch(pattern, parts.path)
    if not match:
        raise ValueError("Нужна ссылка на карточку товара")
    host = "www.wildberries.ru" if marketplace == "wb" else "www.ozon.ru"
    return urlunsplit(("https", host, parts.path, "", "")), match.group(1)


def number(value, field, maximum=Decimal("999999999999.99"), scale=2):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(field + ": ожидается число")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + ": неверное число") from None
    if not result.is_finite() or not 0 <= result <= maximum:
        raise ValueError(field + ": число вне диапазона")
    if result != result.quantize(Decimal(1).scaleb(-scale)):
        raise ValueError(field + ": слишком много знаков после запятой")
    return result


def normalize_item(raw, marketplace):
    """Validate at every boundary; unknown fields never overwrite the schema."""
    if not isinstance(raw, dict):
        raise ValueError("Товар должен быть объектом")
    url, external_id = product_url(raw.get("url"), marketplace)
    if str(raw.get("external_id", external_id)) != external_id:
        raise ValueError("external_id не соответствует URL")
    if not isinstance(raw.get("name"), str) or not raw["name"].strip():
        raise ValueError("Пустое название товара")
    from features import extract_features
    features = extract_features(raw["name"])
    explicit = raw.get("features", {})
    if not isinstance(explicit, dict) or set(explicit) - set(FEATURE_KEYS):
        raise ValueError("Неверные features")
    features.update(explicit)
    for key, choices in (("connection_type", ("wired", "bluetooth", "radio")),
                         ("form_factor", ("in_ear", "on_ear", "over_ear"))):
        if features[key] is not None and features[key] not in choices:
            raise ValueError("Неверный признак " + key)
    for key in ("anc", "microphone"):
        if features[key] is not None and type(features[key]) is not bool:
            raise ValueError(key + ": ожидается boolean или null")
    features["battery_hours"] = number(features["battery_hours"], "battery_hours", Decimal("999.9"), 1)
    count = raw.get("reviews_count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 2147483647):
        raise ValueError("reviews_count: ожидается неотрицательное целое")
    for key in ("brand", "model"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            raise ValueError(key + ": ожидается строка")
    item = {
        "features": features, "external_id": external_id,
        "name": " ".join(raw["name"].split()), "url": url,
        "brand": raw.get("brand"), "price": number(raw.get("price"), "price"),
        "old_price": number(raw.get("old_price"), "old_price"),
        "rating": number(raw.get("rating"), "rating", Decimal("5")), "reviews_count": count,
    }
    # Optional metadata; the nine WB fields above are the common required shape.
    if raw.get("model") is not None:
        item["model"] = raw["model"]
    for key, choices in (("price_kind", ("regular", "card", "subscription", "unknown")),
                         ("availability", ("in_stock", "out_of_stock", "unknown"))):
        if key in raw:
            if raw[key] not in choices:
                raise ValueError("Неверное поле " + key)
            item[key] = raw[key]
    for key in ("region", "currency"):
        if key in raw:
            if not isinstance(raw[key], str) or not raw[key].strip():
                raise ValueError("Неверное поле " + key)
            item[key] = raw[key]
    if "currency" in item and not re.fullmatch(r"[A-Z]{3}", item["currency"]):
        raise ValueError("Неверная валюта")
    if "observed_at" in raw:
        try:
            stamp = datetime.fromisoformat(str(raw["observed_at"]).replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("observed_at: нужна дата с часовым поясом") from None
        item["observed_at"] = stamp.isoformat()
    return item


def dumps(value):
    # Decimal is transported as a decimal string, never via binary float.
    return json.dumps(value, ensure_ascii=False, indent=2, default=lambda v: str(v) if isinstance(v, Decimal) else _unsupported(v), allow_nan=False)


def _unsupported(value):
    raise TypeError("Нельзя сериализовать " + type(value).__name__)


def loads(text):
    return json.loads(text, parse_float=Decimal, parse_constant=lambda v: _unsupported(v))


def validate_batch(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("marketplace"), str) or payload.get("marketplace") not in HOSTS:
        raise ValueError("marketplace: wb или ozon")
    source = payload.get("source_url")
    if not isinstance(source, str) or not source.strip() or len(source) > 4096:
        raise ValueError("source_url обязателен")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 500:
        raise ValueError("items должен содержать от 1 до 500 товаров")
    normalized = [normalize_item(item, payload["marketplace"]) for item in items]
    keys = [(x["external_id"], x.get("region", "unknown"), x.get("currency", "RUB"), x.get("price_kind", "unknown")) for x in normalized]
    if len(set(keys)) != len(keys):
        raise ValueError("Повтор товара с тем же контекстом в пакете")
    return payload["marketplace"], source, normalized
