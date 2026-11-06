import setuptools  # 🔥 Фикс distutils на Python 3.12+
import time
import random
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qsl, urlencode, urlunsplit

from bs4 import BeautifulSoup

from contracts import HOSTS, dumps, normalize_item, product_url


class Parser(ABC):
    site = None

    def __init__(self, link, *, headed=True, manual=False, channel=None,
                 profile=None, timeout=45, scrolls=3, delay=2, limit=5, pages=1, start_page=1, direct=False,
                 on_event=None):
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
        self.on_event = on_event

    def _emit(self, stage, **data):
        if self.on_event:
            self.on_event(stage, data)

    @abstractmethod
    def _parse_data(self, source, url):
        """Return one WB-compatible product from HTML without network access."""
        ...

    @abstractmethod
    def read_specs(self, page):
        """Optional marketplace-specific expansion of product attributes."""
        ...

    def _create_browser(self):
        import undetected_chromedriver as uc
        from selenium_stealth import stealth
        options = uc.ChromeOptions()
        
        if not self.headed:
            options.add_argument("--headless=new")
            
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        if self.direct:
            options.add_argument("--no-proxy-server")
            options.add_argument("--proxy-server='direct://'")
            options.add_argument("--proxy-bypass-list=*")

        options.page_load_strategy = 'eager'

        if self.profile:
            profile_path = str(Path(self.profile).resolve())
            options.add_argument(f"--user-data-dir={profile_path}")

        print("🛡️ Запуск undetected-chromedriver...")
        extra = {}
        if os.environ.get("CHROME_BINARY"):
            extra["browser_executable_path"] = os.environ["CHROME_BINARY"]
        if os.environ.get("CHROME_VERSION_MAIN"):
            extra["version_main"] = int(os.environ["CHROME_VERSION_MAIN"])
        driver_path = os.environ.get("CHROMEDRIVER_PATH")
        if driver_path:
            # UC patches the executable; never patch the system-wide driver or share it across jobs.
            self._driver_directory = tempfile.TemporaryDirectory(prefix="marketplace-driver-")
            target = Path(self._driver_directory.name) / Path(driver_path).name
            shutil.copy2(driver_path, target)
            extra["driver_executable_path"] = str(target)
        options.add_argument("--disable-dev-shm-usage")
        if os.environ.get("CHROME_NO_SANDBOX") == "1":
            options.add_argument("--no-sandbox")
        self._emit("browser.starting")
        driver = uc.Chrome(options=options, **extra)
        
        stealth(driver,
                languages=["ru-RU", "ru"],
                vendor="Google Inc.",
                platform="Win32" if os.name == "nt" else "Linux x86_64",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )
        
        driver.set_page_load_timeout(self.timeout)
        driver.set_script_timeout(self.timeout)
        self._emit("browser.ready")
        return driver

    def _load(self, driver, url):
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
        self._emit("page.loading", url=url)
        parts = urlsplit(url)
        if parts.hostname not in HOSTS[self.site]:
            raise ValueError("Переход вне выбранной площадки")
            
        try:
            driver.get(url)
        except TimeoutException:
            print(f"⚠️ Таймаут загрузки {url}.")
        except WebDriverException as e:
            raise RuntimeError(f"Сетевая ошибка: {e.msg}")

        time.sleep(random.uniform(self.delay, self.delay + 1.5))

        if self.manual:
            input("Дождитесь загрузки страницы и нажмите Enter: ")

        if urlsplit(driver.current_url).hostname not in HOSTS[self.site]:
            raise ValueError("Страница перенаправлена вне площадки")
            
        try:
            text = " ".join(driver.find_element(By.TAG_NAME, "body").text.split())
            if "Похоже, нет соединения" in text:
                raise RuntimeError("Отказ в доступе (403)")
            if "Доступ ограничен" in text or "Подозрительная активность" in text or "captcha" in driver.current_url.lower():
                raise RuntimeError("Сработала капча или блокировка (498)")
        except NoSuchElementException:
            pass
        self._emit("page.loaded", url=driver.current_url)
        self._check_access(driver)

    def _check_access(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        try:
            text = " ".join(driver.find_element(By.TAG_NAME, "body").text.split())
        except NoSuchElementException:
            text = ""
        combined = (str(driver.title) + " " + text[:6000]).lower()
        if any(marker in combined for marker in ("похоже, нет соединения", "доступ ограничен", "подозрительная активность", "access denied", "подтвердите, что вы не робот")):
            self._emit("page.blocked", title=driver.title, url=driver.current_url)
            raise RuntimeError("Отказ в доступе (403): " + driver.title)

    def _parse_card(self, driver, url):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        self._load(driver, url)
        
        try:
            WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, [class*='productTitle']"))
            )
        except TimeoutException:
            print(f"⚠️ Заголовок на странице {url} не появился.")

        self._check_access(driver)

        specs = self.read_specs(driver) 
        item = self._parse_data(driver.page_source, url)
        
        if specs:
            from features import extract_all
            item["features"] = extract_all(item["name"], specs)
            
        item["observed_at"] = datetime.now(timezone.utc).isoformat()
        normalized = normalize_item(item, self.site)
        self._emit("product.parsed", external_id=normalized["external_id"], name=normalized["name"])
        return normalized

    def get_data(self):
        driver = self._create_browser()
        try:
            driver.implicitly_wait(2) 
            
            try:
                direct_url, _ = product_url(self.link, self.site)
            except ValueError:
                direct_url = None
                
            if direct_url:
                return [self._parse_card(driver, direct_url)]
                
            links = {}
            for number in range(self.start_page, self.start_page + self.pages):
                parts = urlsplit(self.link)
                query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"] + [("page", str(number))]
                page_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
                
                self._load(driver, page_url)
                
                for step in range(self.scrolls + 1):
                    self._check_access(driver)
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    for a in soup.select("a[href]"):
                        try:
                            url, key = product_url(urljoin(self.link, a["href"]), self.site)
                        except ValueError:
                            continue
                        links.setdefault(key, url)
                    self._emit("listing.progress", page=number, links=len(links), scroll=step)
                        
                    if self.limit and len(links) >= self.limit:
                        break
                        
                    if step < self.scrolls:
                        scroll_y = random.randint(800, 1500)
                        driver.execute_script(f"window.scrollBy(0, {scroll_y});")
                        time.sleep(random.uniform(1.0, 2.0))
                        
                if self.limit and len(links) >= self.limit:
                    break
                    
            if not links:
                self._check_access(driver)
                self._emit("page.diagnostic", title=driver.title, url=driver.current_url, product_links=0)
                raise RuntimeError("Товарные ссылки не найдены: проверка доступа или изменение разметки")
                
            result = []
            for url in list(links.values())[:self.limit]:
                try:
                    result.append(self._parse_card(driver, url))
                except Exception as exc:
                    self.errors.append({"url": url, "error": str(exc)})
                    self._emit("product.error", url=url, error=str(exc))
                    
            if not result:
                raise RuntimeError("Не удалось прочитать карточки: " + str(self.errors))
            if self.errors:
                raise RuntimeError("Сбор неполный: %s карточек не прочитано. %s" % (len(self.errors), self.errors))
            return result
            
        finally:
            try:
                driver.quit()
            finally:
                if getattr(self, "_driver_directory", None):
                    self._driver_directory.cleanup()

    @staticmethod
    def writing_in_json(items, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(dumps(items) + "\n", encoding="utf-8")
        temporary.replace(path)
