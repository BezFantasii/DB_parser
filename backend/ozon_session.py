"""Ozon collection through an ordinary Chrome session, without Selenium/WebDriver.

python -m backend.ozon_session "наушники" --limit 1
The dedicated profile is retained between runs. A 403/CAPTCHA never becomes a product.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlencode
from urllib.request import build_opener, ProxyHandler

from contracts import HOSTS, dumps, normalize_item, product_url

ROOT=Path(__file__).resolve().parents[1]


def chrome_binary(explicit=None):
    choices=[explicit,os.environ.get("OZON_CHROME_BINARY"),os.environ.get("CHROME_BINARY")]
    if os.name=="nt":
        choices += [str(Path(os.environ.get("PROGRAMFILES","C:/Program Files"))/"Google/Chrome/Application/chrome.exe"),str(Path(os.environ.get("LOCALAPPDATA",""))/"Google/Chrome/Application/chrome.exe")]
    choices += [shutil.which("google-chrome-stable"),shutil.which("google-chrome"),shutil.which("chromium")]
    for candidate in choices:
        if candidate and Path(candidate).is_file():return str(Path(candidate))
    raise RuntimeError("Google Chrome не найден; задайте --chrome или OZON_CHROME_BINARY")


def valid_ozon_url(url):
    u=urlsplit(url)
    if u.scheme!="https" or u.hostname not in HOSTS["ozon"] or u.username or u.password or u.port not in (None,443):
        raise ValueError("Нужна HTTPS-ссылка Ozon")
    return url


def wait_endpoint(port,process,seconds=20):
    opener=build_opener(ProxyHandler({}))
    endpoint=f"http://127.0.0.1:{port}"
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            with opener.open(endpoint+"/json/version",timeout=1) as response:
                if json.load(response).get("webSocketDebuggerUrl"):return endpoint
        except Exception:pass
        if process.poll() is not None:raise RuntimeError("Chrome завершился до открытия CDP. Возможно, отдельный профиль уже используется.")
        time.sleep(.2)
    raise TimeoutError("Chrome не открыл локальный CDP-порт")


class OzonSession:
    def __init__(self,profile=None,chrome=None,cdp_url=None,wait=30,manual_wait=0,keep_open=False,on_event=None):
        self.profile=Path(profile or ROOT/"backend/data/ozon-chrome-session").resolve()
        self.chrome=chrome;self.endpoint=cdp_url;self.wait=wait;self.manual_wait=manual_wait;self.keep_open=keep_open;self.on_event=on_event
        self.process=None;self.browser=None;self.playwright=None;self.owns_browser=not bool(cdp_url)

    def emit(self,stage,**data):
        if self.on_event:self.on_event(stage,data)

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        if not self.endpoint:
            self.profile.mkdir(parents=True,exist_ok=True)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            args=[chrome_binary(self.chrome),f"--remote-debugging-port={port}","--remote-debugging-address=127.0.0.1",f"--user-data-dir={self.profile}","--no-first-run","--no-default-browser-check","--window-size=1440,1000","--lang=ru-RU","about:blank"]
            if os.environ.get("CHROME_NO_SANDBOX")=="1":args.insert(-1,"--no-sandbox")
            self.process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:self.endpoint=wait_endpoint(port,self.process)
            except Exception:
                if self.process.poll() is None:self.process.terminate()
                raise
        else:
            p=urlsplit(self.endpoint)
            if p.scheme!="http" or p.hostname not in ("localhost","127.0.0.1") or p.username or p.password:
                raise ValueError("CDP разрешён только на localhost без credentials")
        self.playwright=sync_playwright().start()
        try:
            self.browser=self.playwright.chromium.connect_over_cdp(self.endpoint,timeout=20000)
            self.context=self.browser.contexts[0]
            self.page=self.context.new_page()
            self.emit("browser.ready",transport="ordinary-chrome-cdp",endpoint=self.endpoint)
            return self
        except Exception:
            self.__exit__(None,None,None)
            raise

    def __exit__(self,*_):
        if self.browser and self.owns_browser and not self.keep_open:
            try:self.browser.close()
            except Exception:pass
        elif self.browser and not self.owns_browser:
            try:self.page.close()
            except Exception:pass
        if self.playwright:self.playwright.stop()
        if self.process and not self.keep_open and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill()

    def navigate(self,url,kind="listing"):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from backend.ozon_access import inspect_html
        valid_ozon_url(url);self.emit("page.loading",url=url)
        status=None
        try:
            response=self.page.goto(url,wait_until="domcontentloaded",timeout=45000)
            status=response.status if response else None
        except PlaywrightTimeout:pass
        deadline=time.monotonic()+self.wait
        manual_deadline=deadline+self.manual_wait
        announced=False
        while time.monotonic()<manual_deadline:
            valid_ozon_url(self.page.url)
            # Read live DOM after challenge scripts; an initial HTTP 403 may be replaced by a valid navigation.
            state=inspect_html(self.page.content(),self.page.url)
            if not state["blocked"]:
                if kind=="home" and state["product_links"]:return
                if kind=="listing" and self.links():return
                if kind=="product":
                    try:
                        self.item();return
                    except ValueError:pass
            if time.monotonic()>=deadline and not announced:
                if not self.manual_wait:break
                self.emit("access.manual_required",title=state["title"],seconds=self.manual_wait)
                announced=True
            self.page.wait_for_timeout(750)
        state=inspect_html(self.page.content(),self.page.url,status)
        self.emit("page.blocked" if state["blocked"] else "page.not_ready",**state)
        if state["blocked"]:
            raise RuntimeError(f"Ozon 403 / CAPTCHA: {state['title']}. Нужна доступная браузерная сессия; не удалось восстановить автоматически.")
        raise RuntimeError(f"Ozon: страница не готова или изменилась разметка: {state['title']}")

    def links(self):
        unique={}
        for href in self.page.locator("a[href]").evaluate_all("els => els.map(a => a.href)"):
            try:
                url,key=product_url(href,"ozon");unique[key]=url
            except ValueError:pass
        return list(unique.values())

    def item(self):
        from parsers.html import parse_product
        from datetime import datetime,timezone
        item=parse_product(self.page.content(),self.page.url,"ozon")
        item["observed_at"]=datetime.now(timezone.utc).isoformat()
        return normalize_item(item,"ozon")

    def collect(self,source,limit=1,warmup=True):
        url=valid_ozon_url(source) if source.startswith(("https:","http:")) else "https://www.ozon.ru/search/?"+urlencode({"text":source})
        if warmup:
            try:self.navigate("https://www.ozon.ru/","home")
            except RuntimeError:self.emit("access.warmup_incomplete")
        try:card,_=product_url(url,"ozon")
        except ValueError:card=None
        if card:
            self.navigate(card,"product");return [self.item()]
        self.navigate(url,"listing")
        links=self.links()[:limit]
        self.emit("listing.collected",links=len(links))
        result=[]
        for link in links:
            self.page.wait_for_timeout(2000)
            self.navigate(link,"product")
            item=self.item();result.append(item)
            self.emit("product.parsed",external_id=item["external_id"],name=item["name"])
        if not result:raise RuntimeError("Ozon: товары не получены")
        return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source",nargs="?",default="наушники")
    cli.add_argument("--limit",type=int,default=1)
    cli.add_argument("--chrome")
    cli.add_argument("--profile",type=Path)
    cli.add_argument("--cdp-url")
    cli.add_argument("--wait",type=int,default=20)
    cli.add_argument("--manual-wait",type=int,default=0,help="Seconds for optional manual challenge in the dedicated browser window")
    cli.add_argument("--keep-open",action="store_true")
    cli.add_argument("--no-warmup",action="store_true")
    cli.add_argument("--output",type=Path,default=ROOT/"backend/test-results/ozon-session-products.json")
    args=cli.parse_args()
    if not 1<=args.limit<=100 or not 1<=args.wait<=120 or not 0<=args.manual_wait<=600:cli.error("Параметры вне диапазона")
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    events=[]
    def event(stage,data):
        events.append({"stage":stage,**data});print(json.dumps(events[-1],ensure_ascii=False),flush=True)
    try:
        with OzonSession(profile=args.profile,chrome=args.chrome,cdp_url=args.cdp_url,wait=args.wait,manual_wait=args.manual_wait,keep_open=args.keep_open,on_event=event) as session:
            items=session.collect(args.source,args.limit,not args.no_warmup)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(dumps(items)+"\n",encoding="utf-8")
        print(dumps(items));return 0
    except Exception as error:
        event("collection.failed",{"error":str(error)});return 2
    finally:
        folder=ROOT/"backend/test-results";folder.mkdir(exist_ok=True)
        (folder/"ozon-session-report.json").write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":raise SystemExit(main())
