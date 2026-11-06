import csv
import io
import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts import HOSTS, normalize_item, validate_batch
from backend.store import Store


def encode(value):
    if isinstance(value, (datetime, date, uuid.UUID, Decimal)):
        return str(value) if not isinstance(value, (datetime,date)) else value.isoformat()
    if isinstance(value, dict):
        return {k:encode(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [encode(x) for x in value]
    return value


def result(value, status=200):
    return JSONResponse(encode(value), status_code=status)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marketplace: Literal["ozon","wb"]
    source: str = Field(min_length=1,max_length=4096)
    limit: int = Field(default=5,ge=1,le=100)
    pages: int = Field(default=1,ge=1,le=10)
    scrolls: int = Field(default=3,ge=0,le=10)
    delay: int = Field(default=2,ge=1,le=30)
    timeout: int = Field(default=45,ge=5,le=90)
    headed: bool = True
    mode: Literal["live","fixture"] = "live"

    def url(self):
        if self.source.lower().startswith(("http:","https:")):
            u = urlsplit(self.source)
            if u.scheme != "https" or u.hostname not in HOSTS[self.marketplace] or u.username or u.password or u.port not in (None,443):
                raise ValueError("Нужен HTTPS-адрес выбранной площадки")
            return self.source
        if not self.source.strip():
            raise ValueError("Пустой запрос")
        if self.marketplace == "ozon":
            return "https://www.ozon.ru/search/?" + urlencode({"text":self.source.strip()})
        return "https://www.wildberries.ru/catalog/0/search.aspx?" + urlencode({"search":self.source.strip()})

    @model_validator(mode="after")
    def validate_source(self):
        self.url()
        return self


class HTMLRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marketplace: Literal["ozon","wb"]
    url: str
    html: str = Field(min_length=1,max_length=2_000_000)


def create_app(store=None, token=None, allow_fixtures=None):
    storage = store or Store()
    expected_token = os.environ.get("API_TOKEN", "local-development-token") if token is None else token
    fixtures = os.environ.get("ALLOW_FIXTURE_JOBS","0") == "1" if allow_fixtures is None else allow_fixtures

    @asynccontextmanager
    async def lifespan(_app):
        storage.initialize()
        yield

    app = FastAPI(title="Marketplace Parser API",version="1.0.0",lifespan=lifespan,
                  description="Durable parsing jobs, progress events, products and PostgreSQL price history. Live and fixture results are labeled separately.")
    app.state.store = storage
    app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.environ.get("CORS_ORIGINS","").split(",") if x.strip()],
                       allow_methods=["GET","POST","OPTIONS"],allow_headers=["Authorization","Content-Type"],allow_credentials=False)

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        if request.method in ("POST","PUT","PATCH"):
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>3_000_000:
                    return result({"detail":"Request body exceeds 3 MB"},413)
                chunks.append(chunk)
            request._body=b"".join(chunks)
        response = await call_next(request)
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

    bearer=HTTPBearer(auto_error=False)
    def auth(credentials:Optional[HTTPAuthorizationCredentials]=Depends(bearer)):
        supplied = credentials.credentials if credentials and credentials.scheme.lower()=="bearer" else ""
        if not expected_token or not secrets.compare_digest(supplied.encode(),expected_token.encode()):
            raise HTTPException(401,"Нужен Bearer API token",headers={"WWW-Authenticate":"Bearer"})

    def job_or_404(job_id):
        job = storage.get(str(job_id))
        if not job:
            raise HTTPException(404,"Задание не найдено")
        return job

    @app.get("/health/live",tags=["health"])
    def live():
        return {"status":"ok"}

    @app.get("/health/ready",tags=["health"])
    def ready():
        try:
            return result({"status":"ok",**storage.health()})
        except Exception:
            raise HTTPException(503,"Database unavailable")

    @app.get("/api/v1/marketplaces",dependencies=[Depends(auth)],tags=["parsers"])
    def marketplaces():
        return {"items":[{"code":"ozon","engine":"selenium / undetected-chromedriver"},{"code":"wb","engine":"selenium / undetected-chromedriver","price_algorithm":"second and third displayed RUB amounts; structured fallback"}],"fixture_jobs":fixtures}

    @app.post("/api/v1/jobs",status_code=202,dependencies=[Depends(auth)],tags=["jobs"])
    def create_job(body: JobRequest):
        if body.mode == "fixture" and not fixtures:
            raise HTTPException(403,"Fixture jobs are disabled on this server")
        return result(storage.create(body.marketplace,body.url(),body.model_dump(exclude={"marketplace","source","mode"}),body.mode),202)

    @app.get("/api/v1/jobs",dependencies=[Depends(auth)],tags=["jobs"])
    def jobs(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),status:Optional[Literal["queued","running","succeeded","failed","blocked","cancelled"]]=None):
        return result({"items":storage.jobs(limit,offset,status),"limit":limit,"offset":offset})

    @app.get("/api/v1/jobs/{job_id}",dependencies=[Depends(auth)],tags=["jobs"])
    def job(job_id:uuid.UUID):
        return result(job_or_404(job_id))

    @app.get("/api/v1/jobs/{job_id}/events",dependencies=[Depends(auth)],tags=["jobs"])
    def events(job_id:uuid.UUID,after_id:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=1000)):
        job_or_404(job_id)
        rows=storage.events(str(job_id),after_id,limit)
        return result({"items":rows,"next_cursor":rows[-1]["id"] if rows else after_id})

    @app.get("/api/v1/jobs/{job_id}/results",dependencies=[Depends(auth)],tags=["jobs"])
    def results(job_id:uuid.UUID):
        j=job_or_404(job_id)
        return result({"job":j,"items":storage.results(str(job_id))})

    @app.post("/api/v1/jobs/{job_id}/cancel",dependencies=[Depends(auth)],tags=["jobs"])
    def cancel(job_id:uuid.UUID):
        job_or_404(job_id)
        if not storage.cancel(str(job_id)):
            raise HTTPException(409,"Задание уже завершено")
        return result(job_or_404(job_id))

    @app.post("/api/v1/jobs/{job_id}/retry",dependencies=[Depends(auth)],tags=["jobs"])
    def retry(job_id:uuid.UUID):
        j=job_or_404(job_id)
        if j["status"] not in ("failed","blocked","cancelled"):
            raise HTTPException(409,"Повтор разрешён для остановленного задания")
        return result(storage.create(j["marketplace"],j["source_url"],j["options"],j["mode"]),202)

    @app.get("/api/v1/products",dependencies=[Depends(auth)],tags=["products"])
    def products(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),marketplace:Optional[Literal["ozon","wb"]]=None,search:str=Query("",max_length=200)):
        return result({"items":storage.products(limit,offset,marketplace,search),"limit":limit,"offset":offset})

    @app.get("/api/v1/products/{product_id}",dependencies=[Depends(auth)],tags=["products"])
    def product(product_id:int):
        p=storage.product(product_id)
        if not p:
            raise HTTPException(404,"Товар не найден")
        return result(p)

    @app.get("/api/v1/products/{product_id}/history",dependencies=[Depends(auth)],tags=["products"])
    def history(product_id:int,limit:int=Query(200,ge=1,le=1000),offset:int=Query(0,ge=0)):
        if not storage.product(product_id):
            raise HTTPException(404,"Товар не найден")
        return result({"items":storage.history(product_id,limit,offset)})

    @app.get("/api/v1/products/{product_id}/analogs",dependencies=[Depends(auth)],tags=["products"])
    def analogs(product_id:int):
        if not storage.product(product_id):
            raise HTTPException(404,"Товар не найден")
        return result({"items":storage.analogs(product_id)})

    @app.post("/api/v1/batches",status_code=201,dependencies=[Depends(auth)],tags=["imports"])
    def import_batch(body:dict):
        try:
            site,source,items=validate_batch(body)
        except (ValueError,TypeError) as e:
            raise HTTPException(422,str(e))
        j=storage.create(site,source,{},"import",status="running")
        try:
            storage.publish(str(j["id"]),items)
        except Exception:
            with storage.connection() as cur:
                cur.execute("UPDATE jobs SET status='failed',error='Import transaction failed' WHERE id=%s",(j["id"],))
            raise HTTPException(503,"Import transaction failed")
        return result(storage.get(str(j["id"])),201)

    @app.post("/api/v1/parse-html",dependencies=[Depends(auth)],tags=["parsers"])
    def parse_html(body:HTMLRequest):
        try:
            from parsers import ParserOzon,ParserWildberries
            factory=ParserOzon if body.marketplace=="ozon" else ParserWildberries
            item=normalize_item(factory(body.url)._parse_data(body.html,body.url),body.marketplace)
            return result({"marketplace":body.marketplace,"data_source":"supplied-html","item":item})
        except ValueError as e:
            raise HTTPException(422,str(e))

    @app.get("/api/v1/export",dependencies=[Depends(auth)],tags=["exports"])
    def export(format:Literal["json","csv"]="json",limit:int=Query(500,ge=1,le=500),offset:int=Query(0,ge=0)):
        rows=storage.products(limit,offset)
        if format=="json":
            return result({"items":rows,"limit":limit,"offset":offset})
        output=io.StringIO(newline="");writer=csv.writer(output,delimiter=";")
        writer.writerow(["marketplace","external_id","name","price","currency","region","price_kind","observed_at","data_source"])
        for r in rows:
            values=[r["marketplace"],r["external_id"],*[r["data"].get(k,"") for k in ("name","price","currency","region","price_kind","observed_at","data_source")]]
            writer.writerow(["'"+str(v) if str(v).startswith(("=","+","-","@","\t","\r")) else v for v in values])
        return Response("\ufeff"+output.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=products.csv"})

    return app


def main():
    import uvicorn
    uvicorn.run(create_app(),host=os.environ.get("API_HOST","127.0.0.1"),port=int(os.environ.get("API_PORT","8000")))


if __name__=="__main__":
    main()
