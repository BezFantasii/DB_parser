"""Parsers send normalized batches; no DB credentials in parser processes."""
import os
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from contracts import dumps, loads, validate_batch


def send_batch(payload, server_url="http://127.0.0.1:8000"):
    validate_batch(payload)
    parts = urlsplit(server_url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Неверный адрес сервера")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("Для удалённого сервера нужен HTTPS")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("INGEST_API_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(server_url.rstrip("/") + "/api/v1/batches", data=dumps(payload).encode("utf-8"), headers=headers)
    with urlopen(request, timeout=60) as response:
        return loads(response.read().decode("utf-8"))
