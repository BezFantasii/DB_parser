-- Clean installation matching db/marketplace_db_dump.sql (without personal data).
-- For a NEW database only; existing database does not need a migration.
BEGIN;
CREATE TABLE marketplaces (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code varchar(100) NOT NULL UNIQUE,
    name varchar(100) NOT NULL
);
CREATE TABLE products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marketplace_id bigint NOT NULL REFERENCES marketplaces(id),
    external_id text NOT NULL,
    name text NOT NULL,
    url text,
    brand text,
    model text,
    connection_type text CHECK (connection_type IN ('wired', 'bluetooth', 'radio')),
    form_factor text CHECK (form_factor IN ('in_ear', 'on_ear', 'over_ear')),
    anc boolean,
    microphone boolean,
    battery_hours numeric(4,1),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (marketplace_id, external_id)
);
CREATE TABLE parse_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marketplace_id bigint NOT NULL REFERENCES marketplaces(id),
    source_url text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed')),
    error_message text
);
CREATE TABLE price_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES products(id),
    run_id bigint NOT NULL REFERENCES parse_runs(id),
    observed_at timestamptz NOT NULL DEFAULT now(),
    price numeric(14,2) CHECK (price >= 0),
    currency char(3) NOT NULL DEFAULT 'RUB',
    region text NOT NULL DEFAULT 'unknown',
    price_kind text NOT NULL DEFAULT 'unknown' CHECK (price_kind IN ('regular', 'card', 'subscription', 'unknown')),
    availability text NOT NULL DEFAULT 'unknown' CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
    rating numeric(3,2) CHECK (rating BETWEEN 0 AND 5),
    reviews_count integer CHECK (reviews_count >= 0),
    UNIQUE (run_id, product_id, region, currency, price_kind)
);
CREATE VIEW current_prices AS
SELECT DISTINCT ON (product_id, region, currency, price_kind) *
FROM price_history
ORDER BY product_id, region, currency, price_kind, observed_at DESC, id DESC;
CREATE INDEX products_marketplace_idx ON products(marketplace_id);
CREATE INDEX products_features_idx ON products(connection_type, form_factor);
CREATE INDEX products_brand_idx ON products(brand);
CREATE INDEX price_history_latest_idx ON price_history(product_id, region, currency, price_kind, observed_at DESC);
CREATE INDEX price_history_run_idx ON price_history(run_id);
CREATE INDEX parse_runs_marketplace_idx ON parse_runs(marketplace_id);
INSERT INTO marketplaces(code, name) VALUES ('wb', 'Wildberries'), ('ozon', 'Ozon'), ('ym', 'Яндекс Маркет');
COMMIT;
