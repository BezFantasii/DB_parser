"""Run against a NEW PostgreSQL database, never against user's application tables."""
import json
import os
from pathlib import Path
import uuid
from urllib.parse import urlsplit,urlunsplit

import psycopg2
from psycopg2 import sql
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.store import Store
from backend.worker import execute


def run():
    original=os.environ["DATABASE_URL"]
    parsed=urlsplit(original);name="parser_test_"+uuid.uuid4().hex
    dsn=urlunsplit(parsed._replace(path="/"+name))
    admin=psycopg2.connect(original);admin.autocommit=True
    checks=[]
    def ok(name):checks.append(name);print("PASS",name,flush=True)
    with admin.cursor() as c:c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    os.environ["DATABASE_URL"]=dsn
    try:
        storage=Store(dsn)
        app=create_app(storage,token="test-token",allow_fixtures=True)
        with TestClient(app,headers={"Authorization":"Bearer test-token"}) as client:
            assert client.get("/api/v1/jobs",headers={"Authorization":"wrong"}).status_code==401
            assert client.get("/health/ready").status_code==200
            assert "HTTPBearer" in client.get("/openapi.json").json()["components"]["securitySchemes"]
            assert client.get("/api/v1/marketplaces").status_code==200
            ok("health, auth, OpenAPI and marketplace registry")
            assert client.post("/api/v1/jobs",json={"marketplace":"ozon","source":"http://evil.test/"}).status_code==422
            assert client.post("/api/v1/jobs",json={"marketplace":"wb","source":"test","limit":0}).status_code==422
            assert client.post("/api/v1/jobs",json={"marketplace":"ozon","source":"https://name:pass@www.ozon.ru/product/123/"}).status_code==422
            ok("job URL, credential and bounds validation")
            root=Path(__file__).resolve().parents[2]
            for site,file,url in [("ozon","ozon_product.html","https://www.ozon.ru/product/test-123/"),("wb","wb_current.html","https://www.wildberries.ru/catalog/456/detail.aspx")]:
                html=(root/"tests/fixtures"/file).read_text(encoding="utf-8")
                response=client.post("/api/v1/parse-html",json={"marketplace":site,"url":url,"html":html})
                assert response.status_code==200,response.text
                price=response.json()["item"]["price"]
                assert price==("1299.50" if site=="ozon" else "1299"),price
                submitted=client.post("/api/v1/jobs",json={"marketplace":site,"source":"наушники","mode":"fixture"})
                assert submitted.status_code==202,submitted.text
                job_id=submitted.json()["id"]
                job=storage.claim("integration-worker");assert str(job["id"])==job_id
                execute(storage,job,"integration-worker")
                j=client.get(f"/api/v1/jobs/{job_id}").json();assert j["status"]=="succeeded",j
                events=client.get(f"/api/v1/jobs/{job_id}/events").json()
                assert "database.saving" in [e["stage"] for e in events["items"]]
                cursor=events["next_cursor"];assert not client.get(f"/api/v1/jobs/{job_id}/events?after_id={cursor}").json()["items"]
                results=client.get(f"/api/v1/jobs/{job_id}/results").json();assert len(results["items"])==1
                assert results["items"][0]["data"]["data_source"]=="fixture"
            ok("both current Python parsers: HTML → real child process → events → atomic PostgreSQL publication")
            products=client.get("/api/v1/products").json()["items"];assert len(products)==2
            pid=products[0]["id"]
            assert client.get(f"/api/v1/products/{pid}").status_code==200
            assert len(client.get(f"/api/v1/products/{pid}/history").json()["items"])==1
            assert len(client.get(f"/api/v1/products/{pid}/analogs").json()["items"])==1
            assert client.get("/api/v1/products/99999999").status_code==404
            assert client.get("/api/v1/export?format=csv").status_code==200
            assert client.get("/api/v1/export").status_code==200
            ok("products, history, analogs, pagination and JSON/CSV exports")
            j=client.post("/api/v1/jobs",json={"marketplace":"ozon","source":"cancel me"}).json()
            assert client.post(f"/api/v1/jobs/{j['id']}/cancel").status_code==200
            assert client.post(f"/api/v1/jobs/{j['id']}/cancel").status_code==409
            retry=client.post(f"/api/v1/jobs/{j['id']}/retry");assert retry.status_code==202
            client.post(f"/api/v1/jobs/{retry.json()['id']}/cancel")
            ok("cancel and retry produce durable, separate jobs")
            # Reject the second row in SQL, proving that the first write is rolled back too.
            with storage.connection() as cur:
                cur.execute("CREATE FUNCTION reject_test_product() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.external_id='999' THEN RAISE EXCEPTION 'test failure'; END IF; RETURN NEW; END $$")
                cur.execute("CREATE TRIGGER reject_test BEFORE INSERT ON products FOR EACH ROW EXECUTE FUNCTION reject_test_product()")
            template={"name":"Тест","price":"10.01","url":"https://www.ozon.ru/product/test-888/"}
            payload={"marketplace":"ozon","source_url":"integration-import","items":[template,{**template,"url":"https://www.ozon.ru/product/test-999/"}]}
            assert client.post("/api/v1/batches",json=payload).status_code==503
            assert not client.get("/api/v1/products?search=888").json()["items"]
            with storage.connection() as cur:cur.execute("DROP TRIGGER reject_test ON products")
            ok("actual PostgreSQL error rolls back the entire batch")
            imported=client.post("/api/v1/batches",json={**payload,"items":[template]});assert imported.status_code==201
            assert client.post("/api/v1/batches",json={**payload,"items":[template]}).status_code==201
            product=client.get("/api/v1/products?search=888").json()["items"][0]
            assert len(client.get(f"/api/v1/products/{product['id']}/history").json()["items"])==2
            unavailable={**template,"price":None,"availability":"out_of_stock","observed_at":"2090-01-01T00:00:00Z"}
            assert client.post("/api/v1/batches",json={**payload,"items":[unavailable]}).status_code==201
            assert client.get("/api/v1/products?search=888").json()["items"][0]["data"]["price"] is None
            ok("imports are repeatable; latest unavailable price does not fall back")
            # Stale worker cannot commit after a lease has been reclaimed or cancellation.
            j=storage.create("ozon","test-source",{},"fixture")
            claimed=storage.claim("lease-worker");storage.cancel(str(j["id"]))
            assert not storage.publish(str(j["id"]),[template],"lease-worker",claimed["attempt"])
            ok("cancelled/stale workers cannot publish")
        print(json.dumps({"checks":checks,"count":len(checks)},ensure_ascii=False),flush=True)
    finally:
        os.environ["DATABASE_URL"]=original
        with admin.cursor() as c:c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


if __name__=="__main__":run()
