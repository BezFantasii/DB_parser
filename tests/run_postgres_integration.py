"""End-to-end HTTP + PostgreSQL test in a NEW disposable local cluster.

Uses installed PostgreSQL binaries, never the user's running database.
Artifacts stay under ignored tmp/db-tests; server is stopped in finally.
"""
import http.client
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psycopg2
import db
from contracts import dumps, loads
from parsers import ParserOzon, ParserWildberries
from server import create_server


def run():
    pg_bin = Path(os.environ.get("PG_BIN", "C:/Program Files/PostgreSQL/16/bin"))
    directory = ROOT / "tmp/db-tests" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    cluster = directory / "cluster"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    def command(*args):
        log = directory / "commands.log"
        with log.open("ab") as stream:
            result = subprocess.run([str(pg_bin / args[0]), *map(str, args[1:])],
                                    stdout=stream, stderr=stream, timeout=90,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(log.read_text(encoding="utf-8", errors="replace"))
    command("initdb.exe", "-D", cluster, "-U", "parser_test", "-A", "trust", "--encoding=UTF8", "--locale=C")
    command("pg_ctl.exe", "-D", cluster, "-l", directory / "postgres.log", "-o", f"-p {port} -h 127.0.0.1", "-w", "start")
    try:
        dsn = f"host=127.0.0.1 port={port} dbname=postgres user=parser_test"
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute((ROOT / "db/schema.sql").read_text(encoding="utf-8"))
            conn.commit()
            with patch.dict(os.environ, {"DATABASE_URL": dsn, "INGEST_API_TOKEN": "integration-token"}):
                server = create_server(port=0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    def post(payload):
                        client = http.client.HTTPConnection(*server.server_address, timeout=10)
                        try:
                            client.request("POST", "/api/v1/batches", dumps(payload).encode("utf-8"),
                                           {"Content-Type":"application/json", "Authorization":"Bearer integration-token"})
                            response = client.getresponse()
                            return response.status, loads(response.read().decode("utf-8"))
                        finally:
                            client.close()
                    fixtures = ROOT / "tests/fixtures"
                    ozon = ParserOzon("https://www.ozon.ru/product/test-123/")._parse_data((fixtures / "ozon_product.html").read_text(encoding="utf-8"))
                    wb = ParserWildberries("https://www.wildberries.ru/catalog/456/detail.aspx")._parse_data((fixtures / "wb_product.html").read_text(encoding="utf-8"))
                    payload = {"marketplace":"ozon", "source_url":ozon["url"], "items":[ozon]}
                    assert post(payload)[0] == 201
                    assert post(payload)[0] == 201  # new run, same product, new history
                    assert post({"marketplace":"wb", "source_url":wb["url"], "items":[wb]})[0] == 201
                    with conn.cursor() as cur:
                        cur.execute("SELECT count(*) FROM products")
                        assert cur.fetchone()[0] == 2
                        cur.execute("SELECT count(*) FROM price_history")
                        assert cur.fetchone()[0] == 3
                        cur.execute("SELECT price FROM current_prices ORDER BY product_id")
                        assert all(str(row[0]) == "1299.50" for row in cur.fetchall())
                        cur.execute("SELECT anc, microphone, connection_type FROM products")
                        assert all(row == (True, True, "bluetooth") for row in cur.fetchall())
                    bad = dict(ozon, external_id="777", url="https://www.ozon.ru/product/test-777/")
                    bad2 = dict(ozon, external_id="888", url="https://www.ozon.ru/product/test-888/")
                    original = db.sql.add_price
                    calls = []
                    def fail_second(cur, observation):
                        calls.append(1)
                        if len(calls) == 2:
                            raise RuntimeError("test simulated write failure")
                        return original(cur, observation)
                    with patch.object(db.sql, "add_price", side_effect=fail_second):
                        assert post(dict(payload, items=[bad, bad2]))[0] == 503
                    with conn.cursor() as cur:
                        cur.execute("SELECT count(*) FROM products")
                        assert cur.fetchone()[0] == 2, "partial batch was not rolled back"
                        cur.execute("SELECT count(*) FROM price_history")
                        assert cur.fetchone()[0] == 3
                        cur.execute("SELECT status FROM parse_runs ORDER BY id")
                        assert [row[0] for row in cur.fetchall()] == ["succeeded"] * 3 + ["failed"]
                    print("PASS: HTTP -> real PostgreSQL, WB/Ozon same schema, product upsert, history, current prices, atomic rollback, failed run")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
        finally:
            conn.close()
    finally:
        command("pg_ctl.exe", "-D", cluster, "-m", "fast", "-w", "stop")


if __name__ == "__main__":
    run()
