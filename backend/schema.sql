CREATE SCHEMA IF NOT EXISTS parser_api;
CREATE TABLE IF NOT EXISTS parser_api.jobs (
 id uuid PRIMARY KEY, marketplace text NOT NULL CHECK(marketplace IN ('ozon','wb')),
 source_url text NOT NULL, options jsonb NOT NULL, mode text NOT NULL,
 status text NOT NULL CHECK(status IN ('queued','running','succeeded','failed','blocked','cancelled')),
 created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz,
 lease_until timestamptz, worker_id text, attempt integer NOT NULL DEFAULT 0,
 error text, saved integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS jobs_queue ON parser_api.jobs(status,created_at);
CREATE TABLE IF NOT EXISTS parser_api.events (
 id bigserial PRIMARY KEY, job_id uuid NOT NULL REFERENCES parser_api.jobs(id),
 created_at timestamptz NOT NULL DEFAULT now(), stage text NOT NULL, data jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job ON parser_api.events(job_id,id);
CREATE TABLE IF NOT EXISTS parser_api.products (
 id bigserial PRIMARY KEY, marketplace text NOT NULL, external_id text NOT NULL,
 data jsonb NOT NULL, first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL,
 UNIQUE(marketplace,external_id)
);
CREATE TABLE IF NOT EXISTS parser_api.observations (
 id bigserial PRIMARY KEY, job_id uuid NOT NULL REFERENCES parser_api.jobs(id),
 product_id bigint NOT NULL REFERENCES parser_api.products(id), observed_at timestamptz NOT NULL,
 region text NOT NULL, currency text NOT NULL, price_kind text NOT NULL, data jsonb NOT NULL,
 UNIQUE(job_id,product_id,region,currency,price_kind)
);
CREATE INDEX IF NOT EXISTS observations_latest ON parser_api.observations(product_id,region,currency,price_kind,observed_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS parser_api.workers (
 id text PRIMARY KEY, last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE VIEW parser_api.current_prices AS
SELECT DISTINCT ON(product_id,region,currency,price_kind) * FROM parser_api.observations
ORDER BY product_id,region,currency,price_kind,observed_at DESC,id DESC;
