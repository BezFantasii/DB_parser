"""Работа с PostgreSQL: подключение, запуски сбора, запись товаров и цен."""
import os

import psycopg2

from features import extract_features


def get_connection():
    """Подключение берётся из переменной окружения DATABASE_URL, пароля в коде нет."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Не задана переменная окружения DATABASE_URL. Пример: "
            "postgresql://postgres:ПАРОЛЬ@localhost:5432/marketplace_db")
    return psycopg2.connect(url)


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


def save_item(conn, marketplace_id, run_id, item):
    """Записывает товар и его цену одной транзакцией (один commit в конце).

    Если что-то упало, снаружи нужно вызвать conn.rollback().
    Признаки наушников (connection_type, form_factor, anc, microphone, battery_hours)
    извлекаются из названия (features.py). Неизвестное = None = NULL.
    При повторном сборе COALESCE не даёт NULL затереть уже известное значение:
    брендом и признаками, найденными раньше, нельзя пожертвовать ради пустого нового.
    """
    # WB передаёт готовые признаки (название + характеристики); Ozon - только название
    f = item.get("features") or extract_features(item["name"])
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO products
                   (marketplace_id, external_id, name, url, brand,
                    connection_type, form_factor, anc, microphone, battery_hours)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (marketplace_id, external_id) DO UPDATE SET
                   name = EXCLUDED.name,
                   url = COALESCE(EXCLUDED.url, products.url),
                   brand = COALESCE(EXCLUDED.brand, products.brand),
                   connection_type = COALESCE(EXCLUDED.connection_type, products.connection_type),
                   form_factor = COALESCE(EXCLUDED.form_factor, products.form_factor),
                   anc = COALESCE(EXCLUDED.anc, products.anc),
                   microphone = COALESCE(EXCLUDED.microphone, products.microphone),
                   battery_hours = COALESCE(EXCLUDED.battery_hours, products.battery_hours),
                   last_seen_at = now()
               RETURNING id""",
            (marketplace_id, item["external_id"], item["name"], item["url"], item["brand"],
             f["connection_type"], f["form_factor"], f["anc"], f["microphone"], f["battery_hours"]),
        )
        product_id = cur.fetchone()[0]

        # price_history - журнал: каждый запуск добавляет новую строку
        cur.execute(
            """INSERT INTO price_history
                   (product_id, run_id, observed_at, price, currency, region,
                    price_kind, availability, rating, reviews_count)
               VALUES (%s, %s, now(), %s, 'RUB', 'unknown', 'unknown', 'unknown', %s, %s)
               ON CONFLICT DO NOTHING""",
            (product_id, run_id, item["price"], item["rating"], item["reviews_count"]),
        )
    conn.commit()
    return product_id
