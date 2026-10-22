"""Разовое дозаполнение признаков для товаров, которые уже лежат в products.

Запуск:  python backfill_features.py
Берёт name каждого товара, прогоняет через features.extract_features и пишет результат.
Только для строк, где признак ещё NULL (COALESCE): ничего известного не затирает.
"""
import db
from features import extract_features


def main():
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM products ORDER BY id")
            rows = cur.fetchall()
            for product_id, name in rows:
                f = extract_features(name)
                cur.execute(
                    """UPDATE products SET
                           connection_type = COALESCE(connection_type, %s),
                           form_factor     = COALESCE(form_factor, %s),
                           anc             = COALESCE(anc, %s),
                           microphone      = COALESCE(microphone, %s),
                           battery_hours   = COALESCE(battery_hours, %s)
                       WHERE id = %s""",
                    (f["connection_type"], f["form_factor"], f["anc"],
                     f["microphone"], f["battery_hours"], product_id),
                )
        conn.commit()
        print("Обработано товаров: %s" % len(rows))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
