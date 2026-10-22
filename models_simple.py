"""Plain SQL access for the marketplace database (no ORM, no model classes).

Every query is ordinary SQL text with psycopg2 placeholders (%s or %(name)s).
Values are passed separately from the text, so there is no string
concatenation and no SQL injection. Tables and constraints are defined in
db/marketplace_db_dump.sql (tables: marketplaces, products, price_history,
parse_runs).

Functions take an open psycopg2 cursor and return plain tuples or dicts.
"""

SQL_GET_MARKETPLACE_ID = """
    SELECT id FROM marketplaces WHERE code = %s
"""

SQL_START_RUN = """
    INSERT INTO parse_runs (marketplace_id, source_url, status)
    VALUES (%s, %s, 'running')
    RETURNING id
"""

SQL_FINISH_RUN = """
    UPDATE parse_runs
       SET finished_at = now(), status = %s, error_message = %s
     WHERE id = %s
"""

# Upsert: unknown (NULL) values never overwrite known ones.
SQL_UPSERT_PRODUCT = """
    INSERT INTO products
        (marketplace_id, external_id, name, url, brand, model,
         connection_type, form_factor, anc, microphone, battery_hours)
    VALUES
        (%(marketplace_id)s, %(external_id)s, %(name)s, %(url)s, %(brand)s,
         %(model)s, %(connection_type)s, %(form_factor)s, %(anc)s,
         %(microphone)s, %(battery_hours)s)
    ON CONFLICT (marketplace_id, external_id) DO UPDATE SET
        name            = EXCLUDED.name,
        url             = EXCLUDED.url,
        brand           = COALESCE(EXCLUDED.brand, products.brand),
        model           = COALESCE(EXCLUDED.model, products.model),
        connection_type = COALESCE(EXCLUDED.connection_type, products.connection_type),
        form_factor     = COALESCE(EXCLUDED.form_factor, products.form_factor),
        anc             = COALESCE(EXCLUDED.anc, products.anc),
        microphone      = COALESCE(EXCLUDED.microphone, products.microphone),
        battery_hours   = COALESCE(EXCLUDED.battery_hours, products.battery_hours),
        last_seen_at    = now()
    RETURNING id
"""

SQL_ADD_PRICE = """
    INSERT INTO price_history
        (product_id, run_id, observed_at, price, currency, region,
         price_kind, availability, rating, reviews_count)
    VALUES
        (%(product_id)s, %(run_id)s, %(observed_at)s, %(price)s,
         %(currency)s, %(region)s, %(price_kind)s, %(availability)s,
         %(rating)s, %(reviews_count)s)
    RETURNING id
"""

SQL_PRICE_HISTORY = """
    SELECT observed_at, price, currency, price_kind, availability
      FROM price_history
     WHERE product_id = %s
     ORDER BY observed_at
"""


def get_marketplace_id(cur, code):
    cur.execute(SQL_GET_MARKETPLACE_ID, (code,))
    row = cur.fetchone()
    return row[0] if row else None


def start_run(cur, marketplace_id, source_url):
    cur.execute(SQL_START_RUN, (marketplace_id, source_url))
    return cur.fetchone()[0]


def finish_run(cur, run_id, status, error_message=None):
    cur.execute(SQL_FINISH_RUN, (status, error_message, run_id))


def upsert_product(cur, product):
    """product: dict with keys marketplace_id, external_id, name, url and
    optional brand, model, connection_type, form_factor, anc, microphone,
    battery_hours (missing keys are stored as NULL = unknown)."""
    params = {
        "brand": None, "model": None, "connection_type": None,
        "form_factor": None, "anc": None, "microphone": None,
        "battery_hours": None,
    }
    params.update(product)
    cur.execute(SQL_UPSERT_PRODUCT, params)
    return cur.fetchone()[0]


def add_price(cur, observation):
    """observation: dict with product_id, run_id, observed_at, price and
    optional currency, region, price_kind, availability, rating,
    reviews_count."""
    params = {
        "currency": "RUB", "region": "unknown", "price_kind": "unknown",
        "availability": "unknown", "rating": None, "reviews_count": None,
    }
    params.update(observation)
    cur.execute(SQL_ADD_PRICE, params)
    return cur.fetchone()[0]


def price_history(cur, product_id):
    cur.execute(SQL_PRICE_HISTORY, (product_id,))
    return cur.fetchall()
