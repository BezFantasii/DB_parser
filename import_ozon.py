"""Загрузка JSON от парсера Ozon (products.json) в PostgreSQL по схеме v2.0.

Отдельный запуск:  python import_ozon.py products.json
Нужна переменная окружения DATABASE_URL (см. db.py).

external_id берётся из конца ссылки товара: .../product/example-123456/ -> 123456.
"""
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import db

MARKETPLACE_CODE = "ozon"

# Рекламные плашки Ozon, которые сниппет мог принять за название товара.
BADGE_RE = re.compile(
    r"^(вау-?цен\w*|распродаж\w*|цена что надо|\d+\s*баллов?|хит продаж|новинка|"
    r"бестселлер|акция|скидка|premium)$", re.IGNORECASE)


def external_id_from_url(url):
    match = re.search(r"-(\d+)/?$", urlsplit(url).path)
    if not match:
        raise ValueError("в ссылке нет номера товара: %s" % url)
    return match.group(1)


def to_item(raw):
    """Превращает запись из JSON в словарь для db.save_item."""
    name = " ".join(raw["name"].split())
    if BADGE_RE.match(name) or len(name) < 6:
        raise ValueError("вместо названия рекламная плашка: %r" % name)
    return {
        "external_id": external_id_from_url(raw["url"]),
        "name": name,
        "url": raw["url"],
        "brand": None,
        "price": Decimal(str(raw["price"])),  # через str, чтобы не тащить ошибки float
        "rating": None,
        "reviews_count": None,
    }


def load_items(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_items(conn, marketplace_id, run_id, items):
    """Пишет записи в базу. Возвращает (сохранено, пропущено)."""
    saved = skipped = 0
    for raw in items:
        try:
            db.save_item(conn, marketplace_id, run_id, to_item(raw))
            saved += 1
        except Exception as exc:
            conn.rollback()  # иначе одна ошибка ломает все следующие вставки
            skipped += 1
            print("Пропущено: %s (%s)" % (raw.get("name", "?"), exc))
    return saved, skipped


def import_file(conn, path):
    """Загрузка готового JSON отдельным запуском: в parse_runs пометка 'import:<файл>'."""
    path = Path(path)
    items = load_items(path)
    marketplace_id = db.get_marketplace_id(conn, MARKETPLACE_CODE)
    run_id = db.start_run(conn, marketplace_id, "import:" + path.name)
    saved, skipped = save_items(conn, marketplace_id, run_id, items)
    if saved:
        db.finish_run(conn, run_id, "succeeded")
    else:
        db.finish_run(conn, run_id, "failed", "ни одна запись не загружена")
    print("Запуск %s: загружено %s, пропущено %s" % (run_id, saved, skipped))
    return saved


def main():
    if len(sys.argv) != 2:
        print("Использование: python import_ozon.py products.json")
        return 1
    conn = db.get_connection()
    try:
        import_file(conn, sys.argv[1])
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
