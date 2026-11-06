import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from contracts import dumps, validate_batch


def json_value(value):
    return Json(json.loads(dumps(value)))


class Store:
    def __init__(self, dsn=None):
        self.dsn = dsn or os.environ.get("DATABASE_URL")
        if not self.dsn:
            raise RuntimeError("DATABASE_URL is required")

    @contextmanager
    def connection(self):
        conn = psycopg2.connect(self.dsn, connect_timeout=5, cursor_factory=RealDictCursor)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL search_path TO parser_api,public")
                    yield cur
        finally:
            conn.close()

    def initialize(self):
        with self.connection() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(75427381)")
            cur.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def health(self):
        with self.connection() as cur:
            cur.execute("SELECT COUNT(*) AS online FROM workers WHERE last_seen_at>now()-interval '30 seconds'")
            return {"database": "ok", "workers_online": cur.fetchone()["online"]}

    def event(self, job_id, stage, data=None):
        with self.connection() as cur:
            cur.execute("INSERT INTO events(job_id,stage,data) VALUES(%s,%s,%s) RETURNING id", (job_id,stage,json_value(data or {})))
            return cur.fetchone()["id"]

    def create(self, marketplace, source_url, options, mode="live", status="queued"):
        job_id = str(uuid.uuid4())
        with self.connection() as cur:
            cur.execute("INSERT INTO jobs(id,marketplace,source_url,options,mode,status) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *", (job_id,marketplace,source_url,json_value(options),mode,status))
            job = dict(cur.fetchone())
            cur.execute("INSERT INTO events(job_id,stage,data) VALUES(%s,'job.queued',%s)",(job_id,json_value({"mode":mode,"source_url":source_url})))
        return job

    def get(self, job_id):
        with self.connection() as cur:
            cur.execute("SELECT * FROM jobs WHERE id=%s", (job_id,))
            return cur.fetchone()

    def jobs(self, limit=50, offset=0, status=None):
        with self.connection() as cur:
            cur.execute("SELECT * FROM jobs WHERE (%s IS NULL OR status=%s) ORDER BY created_at DESC LIMIT %s OFFSET %s", (status,status,limit,offset))
            return cur.fetchall()

    def events(self, job_id, after=0, limit=200):
        with self.connection() as cur:
            cur.execute("SELECT * FROM events WHERE job_id=%s AND id>%s ORDER BY id LIMIT %s", (job_id,after,limit))
            return cur.fetchall()

    def heartbeat(self, worker_id, job_id=None):
        with self.connection() as cur:
            cur.execute("INSERT INTO workers(id) VALUES(%s) ON CONFLICT(id) DO UPDATE SET last_seen_at=now()", (worker_id,))
            if job_id:
                cur.execute("UPDATE jobs SET lease_until=now()+interval '45 seconds' WHERE id=%s AND worker_id=%s AND status='running'",(job_id,worker_id))

    def claim(self, worker_id):
        with self.connection() as cur:
            cur.execute("UPDATE jobs SET status='failed',error='Worker interrupted after three attempts',finished_at=now() WHERE status='running' AND lease_until<now() AND attempt>=3")
            cur.execute("UPDATE jobs SET status='queued',worker_id=NULL WHERE status='running' AND lease_until<now() AND attempt<3")
            cur.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
            job = cur.fetchone()
            if not job:
                return None
            cur.execute("UPDATE jobs SET status='running',worker_id=%s,attempt=attempt+1,started_at=now(),lease_until=now()+interval '45 seconds' WHERE id=%s RETURNING *",(worker_id,job["id"]))
            job = dict(cur.fetchone())
            cur.execute("INSERT INTO events(job_id,stage,data) VALUES(%s,'job.started',%s)",(job["id"],json_value({"attempt":job["attempt"],"mode":job["mode"]})))
            return job

    def owns(self, job_id, worker_id, attempt):
        job = self.get(job_id)
        return job and job["status"] == "running" and job["worker_id"] == worker_id and job["attempt"] == attempt

    def cancel(self, job_id):
        with self.connection() as cur:
            cur.execute("UPDATE jobs SET status='cancelled',finished_at=now() WHERE id=%s AND status IN ('queued','running') RETURNING id",(job_id,))
            if not cur.fetchone():
                return False
            cur.execute("INSERT INTO events(job_id,stage,data) VALUES(%s,'job.cancelled','{}')",(job_id,))
            return True

    def fail(self, job_id, worker_id, attempt, error):
        status = "blocked" if any(s in error.lower() for s in ("403","498","captcha","капча","блокиров","отказ в доступе","подозрительная")) else "failed"
        with self.connection() as cur:
            cur.execute("UPDATE jobs SET status=%s,error=%s,finished_at=now() WHERE id=%s AND worker_id=%s AND attempt=%s AND status='running' RETURNING id",(status,error[:3000],job_id,worker_id,attempt))
            if cur.fetchone():
                cur.execute("INSERT INTO events(job_id,stage,data) VALUES(%s,%s,%s)",(job_id,f"job.{status}",json_value({"error":error[:3000]})))

    def publish(self, job_id, items, worker_id=None, attempt=None):
        job = self.get(job_id)
        _, _, normalized = validate_batch({"marketplace":job["marketplace"],"source_url":job["source_url"],"items":items})
        with self.connection() as cur:
            cur.execute("SELECT * FROM jobs WHERE id=%s FOR UPDATE",(job_id,))
            locked = cur.fetchone()
            if locked["status"] != "running" or (worker_id and (locked["worker_id"] != worker_id or locked["attempt"] != attempt)):
                return False
            for item in normalized:
                stamp = item.get("observed_at",datetime.now(timezone.utc).isoformat())
                item["observed_at"] = stamp
                item["data_source"] = job["mode"]
                cur.execute("""INSERT INTO products(marketplace,external_id,data,first_seen_at,last_seen_at) VALUES(%s,%s,%s,%s,%s)
                  ON CONFLICT(marketplace,external_id) DO UPDATE SET
                  data=CASE WHEN excluded.last_seen_at>=products.last_seen_at THEN excluded.data ELSE products.data END,
                  first_seen_at=LEAST(products.first_seen_at,excluded.first_seen_at),last_seen_at=GREATEST(products.last_seen_at,excluded.last_seen_at)
                  RETURNING id""",(job["marketplace"],item["external_id"],json_value(item),stamp,stamp))
                product_id = cur.fetchone()["id"]
                cur.execute("INSERT INTO observations(job_id,product_id,observed_at,region,currency,price_kind,data) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                            (job_id,product_id,stamp,item.get("region","unknown"),item.get("currency","RUB"),item.get("price_kind","unknown"),json_value(item)))
            cur.execute("UPDATE jobs SET status='succeeded',saved=%s,finished_at=now(),error=NULL WHERE id=%s",(len(normalized),job_id))
            cur.execute("INSERT INTO events(job_id,stage,data) VALUES(%s,'job.succeeded',%s)",(job_id,json_value({"saved":len(normalized)})))
        return True

    def results(self, job_id):
        with self.connection() as cur:
            cur.execute("SELECT product_id,data FROM observations WHERE job_id=%s ORDER BY id",(job_id,))
            return cur.fetchall()

    def products(self, limit=100, offset=0, marketplace=None, search=""):
        with self.connection() as cur:
            cur.execute("""SELECT p.id,p.marketplace,p.external_id,p.first_seen_at,p.last_seen_at,c.data,c.region,c.currency,c.price_kind
              FROM products p JOIN current_prices c ON c.product_id=p.id
              WHERE (%s IS NULL OR p.marketplace=%s) AND (p.data->>'name' ILIKE %s OR p.external_id=%s)
              ORDER BY p.last_seen_at DESC,p.id DESC LIMIT %s OFFSET %s""",(marketplace,marketplace,f"%{search}%",search,limit,offset))
            return cur.fetchall()

    def product(self, product_id):
        with self.connection() as cur:
            cur.execute("SELECT * FROM products WHERE id=%s",(product_id,))
            return cur.fetchone()

    def history(self, product_id, limit=200, offset=0):
        with self.connection() as cur:
            cur.execute("SELECT * FROM observations WHERE product_id=%s ORDER BY observed_at DESC,id DESC LIMIT %s OFFSET %s",(product_id,limit,offset))
            return cur.fetchall()

    def analogs(self, product_id):
        with self.connection() as cur:
            cur.execute("""SELECT p.id,p.marketplace,c.data FROM products p JOIN products s ON s.id=%s
              JOIN current_prices c ON c.product_id=p.id WHERE p.marketplace!=s.marketplace
              AND s.data->'features'->>'connection_type' IS NOT NULL AND s.data->'features'->>'form_factor' IS NOT NULL
              AND p.data->'features'->>'connection_type'=s.data->'features'->>'connection_type'
              AND p.data->'features'->>'form_factor'=s.data->'features'->>'form_factor' ORDER BY p.id LIMIT 100""",(product_id,))
            return cur.fetchall()
