"""Standalone Ozon access diagnostics and bounded recovery; never treats a denial page as data.

Run: python -m backend.ozon_access --engine tls
     python -m backend.ozon_access --engine browser --warmup
"""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit, quote

from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_URL="https://www.ozon.ru/search/?text="+quote("наушники")
BLOCK_MARKERS=("похоже, нет соединения","доступ ограничен","доступ заблокирован","access denied","подтвердите, что вы не робот")


def check_url(url):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname not in ("www.ozon.ru","ozon.ru") or p.username or p.password or p.port not in (None,443):
        raise ValueError("Нужен HTTPS URL Ozon")
    return url


def inspect_html(html,url,status=None):
    soup=BeautifulSoup(html,"html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    body=" ".join(soup.get_text(" ",strip=True).split())
    blocked=status in (403,429) or "captcha" in title.lower() or any(s in (title+" "+body[:6000]).lower() for s in BLOCK_MARKERS)
    links=[a.get("href") for a in soup.select('a[href*="/product/"]')]
    return {"url":url,"status":status,"title":title,"blocked":blocked,"product_links":len(links),"has_product_title":bool(soup.select_one("h1")),"bytes":len(html.encode("utf-8"))}


def tls_probe(url,warmup=False,direct=False):
    from curl_cffi import requests
    report=[]
    proxy="" if direct else os.environ.get("OZON_PROXY")
    with requests.Session(impersonate="chrome",proxy=proxy,trust_env=not direct,headers={"Accept-Language":"ru-RU,ru;q=0.9,en;q=0.8"}) as session:
        if warmup:
            r=session.get("https://www.ozon.ru/",timeout=25,allow_redirects=True,max_redirects=3)
            report.append(inspect_html(r.text,str(r.url),r.status_code))
            time.sleep(2)
        for target in [url,"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="+quote(urlsplit(url).path+("?"+urlsplit(url).query if urlsplit(url).query else ""),safe="")]:
            r=session.get(target,timeout=25,allow_redirects=True,max_redirects=3,headers={"Referer":"https://www.ozon.ru/"})
            row=inspect_html(r.text,str(r.url),r.status_code)
            row["content_type"]=r.headers.get("content-type","")
            report.append(row)
            time.sleep(2)
    return report


def browser_probe(url,warmup=False,wait=15):
    import shutil
    import tempfile
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    directory=tempfile.mkdtemp(prefix="ozon-access-")
    options=uc.ChromeOptions()
    options.add_argument("--lang=ru-RU")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--user-data-dir="+str(Path(directory)/"profile"))
    if os.environ.get("CHROME_NO_SANDBOX")=="1":options.add_argument("--no-sandbox")
    extra={}
    if os.environ.get("CHROME_BINARY"):extra["browser_executable_path"]=os.environ["CHROME_BINARY"]
    if os.environ.get("CHROME_VERSION_MAIN"):extra["version_main"]=int(os.environ["CHROME_VERSION_MAIN"])
    if os.environ.get("CHROMEDRIVER_PATH"):
        copied=Path(directory)/"chromedriver";shutil.copy2(os.environ["CHROMEDRIVER_PATH"],copied);extra["driver_executable_path"]=str(copied)
    driver=uc.Chrome(options=options,**extra)
    report=[]
    try:
        driver.set_page_load_timeout(35)
        # Keep the browser's own UA/WebGL/platform: adding contradictory spoofed properties can hurt access.
        targets=(["https://www.ozon.ru/"] if warmup else [])+[url]
        for target in targets:
            try:driver.get(target)
            except Exception:pass
            end=time.monotonic()+wait
            while time.monotonic()<end:
                row=inspect_html(driver.page_source,driver.current_url)
                if not row["blocked"] and (row["product_links"] or row["has_product_title"]):break
                time.sleep(1)
            report.append(inspect_html(driver.page_source,driver.current_url))
        return report
    finally:
        driver.quit()
        # A fresh diagnostic profile is deliberately not the application's persisted/login profile.
        # It lives in the OS temp directory and is not copied into collected product data.


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--url",default=DEFAULT_URL)
    cli.add_argument("--engine",choices=("tls","browser"),default="tls")
    cli.add_argument("--warmup",action="store_true")
    cli.add_argument("--wait",type=int,default=15)
    cli.add_argument("--direct",action="store_true",help="Do not use proxy variables in TLS mode")
    args=cli.parse_args()
    url=check_url(args.url)
    rows=tls_probe(url,args.warmup,args.direct) if args.engine=="tls" else browser_probe(url,args.warmup,wait=max(1,min(args.wait,60)))
    report={"engine":args.engine,"warmup":args.warmup,"proxy_configured":bool(os.environ.get("OZON_PROXY")),"pages":rows}
    path=ROOT/"backend/test-results"/f"ozon-access-{args.engine}.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if any(not r["blocked"] and (r["product_links"] or r["has_product_title"]) for r in rows) else 2


if __name__=="__main__":
    raise SystemExit(main())
