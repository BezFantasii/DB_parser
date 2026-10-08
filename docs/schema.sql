-- Proposed schema only. Not applied to a database or connected to the parser.
BEGIN;

CREATE TABLE marketplace (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    base_url text NOT NULL
);

CREATE TABLE brand (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE category (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id bigint REFERENCES category(id),
    name text NOT NULL,
    CHECK (parent_id IS NULL OR parent_id <> id)
);

-- One exact variant: capacity, colour, package size, etc. are significant.
-- Link listings only after matching reliable identifiers, not just titles.
CREATE TABLE product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    brand_id bigint REFERENCES brand(id),
    category_id bigint REFERENCES category(id),
    gtin text,
    manufacturer_sku text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (jsonb_typeof(attributes) = 'object')
);

CREATE TABLE listing (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marketplace_id bigint NOT NULL REFERENCES marketplace(id),
    external_id text NOT NULL,
    product_id bigint REFERENCES product(id),
    title text NOT NULL,
    url text NOT NULL,
    brand_id bigint REFERENCES brand(id),
    category_id bigint REFERENCES category(id),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (marketplace_id, external_id),
    UNIQUE (id, marketplace_id),
    CHECK (jsonb_typeof(attributes) = 'object'),
    CHECK (last_seen_at >= first_seen_at)
);

CREATE TABLE scrape_run (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marketplace_id bigint NOT NULL REFERENCES marketplace(id),
    source_url text NOT NULL,
    parser_version text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed')),
    error_message text,
    UNIQUE (id, marketplace_id),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

-- A displayed listing price, not a guaranteed seller-level offer.
CREATE TABLE observation (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marketplace_id bigint NOT NULL REFERENCES marketplace(id),
    listing_id bigint NOT NULL,
    run_id bigint NOT NULL,
    observed_at timestamptz NOT NULL,
    region_key text NOT NULL DEFAULT 'unknown',
    price_kind text NOT NULL DEFAULT 'unknown'
        CHECK (price_kind IN ('regular', 'card', 'subscription', 'unknown')),
    condition_key text NOT NULL DEFAULT 'unknown',
    currency char(3) NOT NULL DEFAULT 'RUB',
    price numeric(14,2) CHECK (price >= 0),
    price_text text,
    availability text NOT NULL DEFAULT 'unknown'
        CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
    rating numeric(3,2) CHECK (rating BETWEEN 0 AND 5),
    reviews_count integer CHECK (reviews_count >= 0),
    raw_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (listing_id, marketplace_id) REFERENCES listing(id, marketplace_id),
    FOREIGN KEY (run_id, marketplace_id) REFERENCES scrape_run(id, marketplace_id),
    UNIQUE (run_id, listing_id, region_key, price_kind, condition_key, currency),
    CHECK (jsonb_typeof(raw_data) = 'object')
);

CREATE INDEX listing_product_idx ON listing(product_id);
CREATE INDEX listing_category_brand_idx ON listing(category_id, brand_id);
CREATE INDEX listing_attributes_idx ON listing USING gin(attributes);
CREATE INDEX category_parent_idx ON category(parent_id);
CREATE INDEX product_brand_category_idx ON product(brand_id, category_id);
CREATE INDEX observation_latest_idx ON observation
    (listing_id, region_key, price_kind, condition_key, currency, observed_at DESC, id DESC);
CREATE INDEX observation_run_idx ON observation(run_id);
CREATE INDEX scrape_run_marketplace_idx ON scrape_run(marketplace_id, started_at DESC);

-- Choose the latest observation BEFORE filtering by price or availability.
-- NULL price and out_of_stock observations intentionally supersede old prices.
CREATE VIEW latest_observation AS
SELECT DISTINCT ON (listing_id, region_key, price_kind, condition_key, currency) *
FROM observation
ORDER BY listing_id, region_key, price_kind, condition_key, currency,
         observed_at DESC, id DESC;

COMMIT;

-- Optional substring-search index, if pg_trgm can be installed:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- CREATE INDEX listing_title_trgm_idx ON listing USING gin(title gin_trgm_ops);
