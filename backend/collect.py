"""One disposable parser process. stdout is NDJSON; arbitrary parser prints go to stderr."""
import contextlib
import json
import os
from pathlib import Path
import sys

from contracts import dumps, normalize_item


def run(payload):
    protocol=sys.stdout
    def emit(stage,data=None):
        protocol.write(json.dumps({"type":"event","stage":stage,"data":data or {}},ensure_ascii=False)+"\n");protocol.flush()
    with contextlib.redirect_stdout(sys.stderr):
        from parsers import ParserOzon,ParserWildberries
        site=payload["marketplace"]
        factory=ParserOzon if site=="ozon" else ParserWildberries
        options=payload["options"]
        if payload["mode"]=="fixture":
            emit("fixture.loading",{"warning":"Учебный HTML, не живой сбор"})
            root=Path(__file__).resolve().parents[1]
            fixture=root/"tests/fixtures"/("wb_current.html" if site=="wb" else "ozon_product.html")
            url="https://www.wildberries.ru/catalog/456/detail.aspx" if site=="wb" else "https://www.ozon.ru/product/test-123/"
            item=normalize_item(factory(url)._parse_data(fixture.read_text(encoding="utf-8"),url),site)
            emit("product.parsed",{"external_id":item["external_id"],"name":item["name"]})
            items=[item]
        else:
            from backend.profiles import managed_profile
            with managed_profile(site) as profile:
                parser=factory(payload["source_url"],profile=profile,on_event=emit,**{k:options[k] for k in ("headed","limit","pages","scrolls","delay","timeout")})
                items=parser.get_data()
    protocol.write(dumps({"type":"result","items":items}).replace("\n","")+"\n");protocol.flush()


if __name__=="__main__":
    try:
        run(json.loads(sys.stdin.readline()))
    except Exception as error:
        print(json.dumps({"type":"error","error":str(error)},ensure_ascii=False),flush=True)
        sys.exit(1)
