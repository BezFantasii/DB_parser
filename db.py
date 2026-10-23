"""Работа с PostgreSQL: подключение, запуски сбора, запись товаров и цен."""
import os

from datetime import datetime, timezone
import models_simple as sql
from contracts import normalize_item, validate_batch


def get_connection():
    """Подключение берётся из переменной окружения DATABASE_URL, пароля в коде нет."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Не задана переменная окружения DATABASE_URL. Пример: "
            "postgresql://postgres:ПАРОЛЬ@localhost:5432/marketplace_db")
    import psycopg2
    return psycopg2.connect(url, connect_timeout=5)


def get_marketplace_id(conn, code):
    """Возвращает id площадки по коду ('wb', 'ozon', 'ym')."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM marketplaces WHERE code = %s", (code,))
        row = cur.fetchone()
    if row is None:
        raise ValueError("Площадка %r не найдена в marketplaces" % code)
    return row[0]


def start_run(conn, marketplace_id, source_url):
    """Создаёт запись о запуске сбора и возвращает её id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parse_runs (marketplace_id, source_url) VALUES (%s, %s) RETURNING id",
            (marketplace_id, source_url),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id, status, error_message=None):
    """Закрывает запуск: status = 'succeeded' или 'failed'."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE parse_runs SET finished_at = now(), status = %s, error_message = %s WHERE id = %s",
            (status, error_message, run_id),
        )
    conn.commit()


def save_item(conn, marketplace_id, run_id, item, *, commit=True):
    """Plain parameterized SQL. Batch owner can defer the commit."""
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM marketplaces WHERE id = %s", (marketplace_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Неизвестная площадка")
        item = normalize_item(item, row[0])
        cur.execute("SELECT marketplace_id FROM parse_runs WHERE id = %s", (run_id,))
        if cur.fetchone() != (marketplace_id,):
            raise ValueError("Запуск относится к другой площадке")
        product = {k: item.get(k) for k in ("external_id", "name", "url", "brand", "model")}
        product.update(item["features"], marketplace_id=marketplace_id)
        product_id = sql.upsert_product(cur, product)
        observation = {k: item[k] for k in ("price", "rating", "reviews_count")}
        observation.update(product_id=product_id, run_id=run_id,
                           observed_at=item.get("observed_at", datetime.now(timezone.utc)))
        for key in ("currency", "region", "price_kind", "availability"):
            if key in item:
                observation[key] = item[key]
        sql.add_price(cur, observation)
    if commit:
        conn.commit()
    return product_id


def save_batch(conn, payload):
    """All validated items are committed together; failed runs remain auditable."""
    code, source, items = validate_batch(payload)
    marketplace_id = get_marketplace_id(conn, code)
    run_id = start_run(conn, marketplace_id, source)
    try:
        ids = [save_item(conn, marketplace_id, run_id, item, commit=False) for item in items]
        finish_run(conn, run_id, "succeeded")
    except Exception:
        conn.rollback()
        finish_run(conn, run_id, "failed", "Пакет отклонён при записи; данные пакета отменены")
        raise
    return {"run_id": run_id, "saved": len(ids), "product_ids": ids}
