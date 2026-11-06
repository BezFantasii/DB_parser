"""Temporary HTTP API + fixture worker, with an isolated database for extension E2E tests."""
import os
import threading
import time
import uuid
from urllib.parse import urlsplit,urlunsplit

import psycopg2
from psycopg2 import sql
import uvicorn

from backend.api import create_app
from backend.store import Store
from backend.worker import execute


def run():
    original=os.environ["DATABASE_URL"]
    name="parser_extension_test_"+uuid.uuid4().hex
    admin=psycopg2.connect(original);admin.autocommit=True
    with admin.cursor() as c:c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn=urlunsplit(urlsplit(original)._replace(path="/"+name));os.environ["DATABASE_URL"]=dsn
    store=Store(dsn);store.initialize();stop=threading.Event()
    def work():
        while not stop.is_set():
            store.heartbeat("extension-test-worker")
            j=store.claim("extension-test-worker")
            if j:execute(store,j,"extension-test-worker")
            else:stop.wait(.2)
    thread=threading.Thread(target=work,daemon=True);thread.start()
    try:
        uvicorn.run(create_app(store,token="test-token",allow_fixtures=True),host="0.0.0.0",port=8001)
    finally:
        stop.set();thread.join(timeout=5)
        with admin.cursor() as c:c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


if __name__=="__main__":run()
