"""Local HTTP ingestion service; PostgreSQL only, no ORM or web framework."""
import argparse
import hmac
import logging
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
from contracts import dumps, loads, validate_batch

MAX_BODY = 2 * 1024 * 1024


class IngestHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def reply(self, status, data):
        body = dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        token = self.server.api_token
        if not token:
            return True
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "ok"})
        else:
            self.reply(404, {"error": "not_found"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"error": "unauthorized"})
        if self.path != "/api/v1/batches":
            return self.reply(404, {"error": "not_found"})
        if self.headers.get_content_type() != "application/json":
            return self.reply(415, {"error": "Нужен Content-Type application/json"})
        if self.headers.get("Transfer-Encoding"):
            return self.reply(400, {"error": "Transfer-Encoding не поддерживается"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 < length <= MAX_BODY:
                return self.reply(413, {"error": "Пакет должен быть не больше 2 МБ"})
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Неполный запрос")
            payload = loads(data.decode("utf-8"))
            validate_batch(payload)
        except (ValueError, TypeError, UnicodeError, socket.timeout) as exc:
            return self.reply(400, {"error": str(exc)})
        conn = None
        try:
            conn = db.get_connection()
            result = db.save_batch(conn, payload)
        except Exception as exc:
            # DB diagnostics can contain full rejected rows or credentials.
            logging.error("Не удалось сохранить пакет; транзакция отменена (%s)", type(exc).__name__)
            return self.reply(503, {"error": "Не удалось записать пакет. Проверьте БД и журнал сервера"})
        finally:
            if conn is not None:
                conn.close()
        self.reply(201, result)


def create_server(host="127.0.0.1", port=8000):
    token = os.environ.get("INGEST_API_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise ValueError("Для внешнего интерфейса задайте INGEST_API_TOKEN")
    if host == "::1":
        raise ValueError("Используйте IPv4 127.0.0.1")
    server = ThreadingHTTPServer((host, port), IngestHandler)
    server.api_token = token
    return server


def main():
    parser = argparse.ArgumentParser(description="Сервер записи товаров в PostgreSQL")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.error("Задайте DATABASE_URL")
    with create_server(args.host, args.port) as server:
        print("Сервер: http://%s:%s" % server.server_address, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
