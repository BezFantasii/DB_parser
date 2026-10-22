-- Intermediate three-table model. Not applied to a database.
-- Use a new database/schema; this is not a migration of docs/schema.sql.
BEGIN;

CREATE TABLE marketplaces (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL
);

-- One row is a marketplace listing, not a cross-marketplace canonical product.
-- MVP category: headphones. External IDs are meaningful only within a marketplace.
CREATE TABLE products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marketplace_id bigint NOT NULL REFERENCES marketplaces(id),
    external_id text NOT NULL,
    name text NOT NULL,
    url text NOT NULL,
    brand text,
    model text,
    connection_type text CHECK (connection_type IN ('wired', 'bluetooth', 'radio')),
    form_factor text CHECK (form_factor IN ('in_ear', 'on_ear', 'over_ear')),
    anc boolean,
    microphone boolean,
    battery_hours numeric(7,2) CHECK (battery_hours >= 0),
    UNIQUE (marketplace_id, external_id)
);

-- Price and availability vary by time and purchasing context.
CREATE TABLE price_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES products(id),
    observed_at timestamptz NOT NULL,
    price numeric(14,2) CHECK (price >= 0),
    currency char(3) NOT NULL DEFAULT 'RUB',
    region text NOT NULL DEFAULT 'unknown',
    price_kind text NOT NULL DEFAULT 'unknown'
        CHECK (price_kind IN ('regular', 'card', 'subscription', 'unknown')),
    availability text NOT NULL DEFAULT 'unknown'
        CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
    rating numeric(3,2) CHECK (rating BETWEEN 0 AND 5),
    reviews_count integer CHECK (reviews_count >= 0),
    price_text text,
    UNIQUE (product_id, observed_at, region, currency, price_kind)
);

CREATE INDEX products_features_idx ON products(connection_type, form_factor);
CREATE INDEX price_history_latest_idx ON price_history
    (product_id, region, currency, price_kind, observed_at DESC, id DESC);

-- A view is a stored query, not a fourth data table.
-- Select the latest row before applying price and availability filters.
CREATE VIEW current_prices AS
SELECT DISTINCT ON (product_id, region, currency, price_kind) *
FROM price_history
ORDER BY product_id, region, currency, price_kind, observed_at DESC, id DESC;

COMMIT;
