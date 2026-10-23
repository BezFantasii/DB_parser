"""A browser per parser instance; loading and offline HTML parsing are separate."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from contracts import HOSTS, dumps, normalize_item, product_url


class Parser(ABC):
    site = None

    def __init__(self, link, *, headed=True, manual=False, channel=None,
                 profile=None, timeout=45, scrolls=3, delay=2, limit=5, pages=1, start_page=1, direct=False):
        parts = urlsplit(link)
        if (parts.scheme != "https" or parts.hostname not in HOSTS[self.site]
                or parts.username or parts.password or parts.port not in (None, 443)):
            raise ValueError("Недопустимая ссылка площадки")
        if manual and not headed:
            raise ValueError("Ручной режим требует видимого окна")
        self.link, self.headed, self.manual = link, headed, manual
        self.channel, self.profile = channel, profile
        self.timeout, self.scrolls, self.delay = timeout, scrolls, delay
        self.limit, self.pages, self.start_page, self.direct = limit, pages, start_page, direct
        self.errors = []

    @abstractmethod
    def _parse_data(self, source, url):
        """Return one WB-compatible product from HTML without network access."""

    @abstractmethod
    def read_specs(self, page):
        """Optional marketplace-specific expansion of product attributes."""

    def _load(self, page, url):
        parts = urlsplit(url)
        if parts.hostname not in HOSTS[self.site]:
            raise ValueError("Переход вне выбранной площадки")
        response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        if response and response.status >= 400 and not (response.status == 403 and self.manual):
            raise RuntimeError("%s: HTTP %s" % (self.site, response.status))
        if self.manual:
            input("Дождитесь товаров в браузере и нажмите Enter: ")
        page.wait_for_timeout(self.delay * 1000)
        if urlsplit(page.url).hostname not in HOSTS[self.site]:
            raise ValueError("Страница перенаправлена вне площадки")
        text = page.locator("body").inner_text()
        if "Похоже, нет соединения" in text and "Обратиться в поддержку" in text:
            raise RuntimeError("Ozon: страница отказа в доступе")

    def _parse_card(self, page, url):
        self._load(page, url)
        page.locator("h1, [class*='productTitle']").first.wait_for(timeout=self.timeout * 1000)
        specs = self.read_specs(page)
        item = self._parse_data(page.content(), url)
        if specs:
            from features import extract_all
            item["features"] = extract_all(item["name"], specs)
        item["observed_at"] = datetime.now(timezone.utc).isoformat()
        return normalize_item(item, self.site)

    def get_data(self):
        """Collect a card or search results; never connect to PostgreSQL here."""
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
        with sync_playwright() as p:
            options = {"headless": not self.headed}
            if self.channel:
                options["channel"] = self.channel
            if self.direct:
                options["args"] = ["--no-proxy-server"]
            settings = {"locale": "ru-RU", "viewport": {"width": 1440, "height": 1000}}
            browser = None
            if self.profile:
                context = p.chromium.launch_persistent_context(str(Path(self.profile).resolve()), **options, **settings)
            else:
                browser = p.chromium.launch(**options)
                context = browser.new_context(**settings)
            try:
                page = context.new_page()
                page.set_default_timeout(self.timeout * 1000)
                try:
                    direct_url, _ = product_url(self.link, self.site)
                except ValueError:
                    direct_url = None
                if direct_url:
                    return [self._parse_card(page, direct_url)]
                links = {}
                for number in range(self.start_page, self.start_page + self.pages):
                    from urllib.parse import parse_qsl, urlencode, urlunsplit
                    parts = urlsplit(self.link)
                    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"] + [("page", str(number))]
                    self._load(page, urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), "")))
                    for step in range(self.scrolls + 1):
                        soup = BeautifulSoup(page.content(), "html.parser")
                        for a in soup.select("a[href]"):
                            try:
                                url, key = product_url(urljoin(self.link, a["href"]), self.site)
                            except ValueError:
                                continue
                            links.setdefault(key, url)
                        if self.limit and len(links) >= self.limit:
                            break
                        if step < self.scrolls:
                            page.mouse.wheel(0, 1400)
                            page.wait_for_timeout(self.delay * 1000)
                    if self.limit and len(links) >= self.limit:
                        break
                if not links:
                    raise RuntimeError("Товарные ссылки не найдены: проверка доступа или изменение разметки")
                result = []
                for url in list(links.values())[:self.limit]:
                    try:
                        result.append(self._parse_card(page, url))
                    except Exception as exc:
                        self.errors.append({"url": url, "error": str(exc)})
                if not result:
                    raise RuntimeError("Не удалось прочитать карточки: " + str(self.errors))
                if self.errors:
                    raise RuntimeError("Сбор неполный: %s карточек не прочитано; пакет не публикуется. %s" % (len(self.errors), self.errors))
                return result
            finally:
                context.close()
                if browser:
                    browser.close()

    @staticmethod
    def writing_in_json(items, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(dumps(items) + "\n", encoding="utf-8")
        temporary.replace(path)
