import setuptools  # 🔥 ОБЯЗАТЕЛЬНО: Фиксит ошибку distutils в Python 3.12+ для undetected-chromedriver
import time
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qsl, urlencode, urlunsplit

import undetected_chromedriver as uc
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from bs4 import BeautifulSoup

from contracts import HOSTS, dumps, normalize_item, product_url
# from features import extract_all  # Раскомментируйте, если используете


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
        ...

    @abstractmethod
    def read_specs(self, page):
        """Optional marketplace-specific expansion of product attributes."""
        ...

    def _create_browser(self):
        """Создание браузера с максимальной маскировкой от Ozon и WB"""
        options = uc.ChromeOptions()
        
        # Ozon (DataDome) и WB (Cloudflare) очень не любят Headless-режим.
        # Если ловите 403/498, лучше запускать с видимым окном (headed=True).
        if not self.headed:
            options.add_argument("--headless=new")
            
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Если включен direct, жестко отключаем любые прокси
        if self.direct:
            options.add_argument("--no-proxy-server")
            options.add_argument("--proxy-server='direct://'")
            options.add_argument("--proxy-bypass-list=*")

        # Стратегия eager: не ждем картинки, чтобы не висло
        options.page_load_strategy = 'eager'

        if self.channel:
            options.add_argument(f"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Настройка профиля (для сохранения куки и обхода капчи)
        if self.profile:
            profile_path = str(Path(self.profile).resolve())
            options.add_argument(f"--user-data-dir={profile_path}")

        print("🛡️ Запуск undetected-chromedriver (обход защиты)...")
        
        # Если используем профиль, undetected_chromedriver требует передачи его в аргументах
        driver = uc.Chrome(options=options)
        
        # 🔥 SELENIUM STEALTH: Маскируем оставшиеся следы
        stealth(driver,
                languages=["ru-RU", "ru"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )
        
        driver.set_page_load_timeout(self.timeout)
        driver.set_script_timeout(self.timeout)
        
        return driver

    def _load(self, driver, url):
        """Загрузка страницы с защитой от зависаний и блокировок"""
        parts = urlsplit(url)
        if parts.hostname not in HOSTS[self.site]:
            raise ValueError("Переход вне выбранной площадки")
            
        try:
            driver.get(url)
        except TimeoutException:
            print(f"⚠️ Таймаут загрузки {url}. Пробуем работать с тем, что загрузилось...")
        except WebDriverException as e:
            raise RuntimeError(f"Сетевая ошибка: {e.msg}")

        # Случайная задержка (имитация человека)
        time.sleep(random.uniform(self.delay, self.delay + 2))

        if self.manual:
            input("Дождитесь загрузки страницы и нажмите Enter: ")

        if urlsplit(driver.current_url).hostname not in HOSTS[self.site]:
            raise ValueError("Страница перенаправлена вне площадки")
            
        try:
            text = driver.find_element(By.TAG_NAME, "body").text
            if "Похоже, нет соединения" in text and "Обратиться в поддержку" in text:
                raise RuntimeError("Ozon: страница отказа в доступе (403)")
            if "Доступ ограничен" in text or "captcha" in driver.current_url.lower():
                raise RuntimeError("Сработала капча или блокировка (498)")
        except NoSuchElementException:
            pass

    def _parse_card(self, driver, url):
        """Парсинг карточки товара"""
        self._load(driver, url)
        
        try:
            WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, [class*='productTitle']"))
            )
        except TimeoutException:
            print(f"⚠️ Заголовок на странице {url} не появился.")

        # read_specs теперь принимает driver
        specs = self.read_specs(driver) 
        
        item = self._parse_data(driver.page_source, url)
        
        if specs:
            from features import extract_all
            item["features"] = extract_all(item["name"], specs)
            
        item["observed_at"] = datetime.now(timezone.utc).isoformat()
        return normalize_item(item, self.site)

    def get_data(self):
        """Основной метод сбора данных"""
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
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    for a in soup.select("a[href]"):
                        try:
                            url, key = product_url(urljoin(self.link, a["href"]), self.site)
                        except ValueError:
                            continue
                        links.setdefault(key, url)
                        
                    if self.limit and len(links) >= self.limit:
                        break
                        
                    if step < self.scrolls:
                        # Имитация человеческого скролла
                        scroll_y = random.randint(800, 1500)
                        driver.execute_script(f"window.scrollBy(0, {scroll_y});")
                        time.sleep(random.uniform(1.0, 2.5))
                        
                if self.limit and len(links) >= self.limit:
                    break
                    
            if not links:
                raise RuntimeError("Товарные ссылки не найдены: проверка доступа или изменение разметки")
                
            result = []
            for url in list(links.values())[:self.limit]:
                try:
                    result.append(self._parse_card(driver, url))
                except Exception as exc:
                    self.errors.append({"url": url, "error": str(exc)})
                    
            if not result:
                raise RuntimeError("Не удалось прочитать карточки: " + str(self.errors))
            if self.errors:
                raise RuntimeError("Сбор неполный: %s карточек не прочитано. %s" % (len(self.errors), self.errors))
            return result
            
        finally:
            driver.quit()

    @staticmethod
    def writing_in_json(items, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(dumps(items) + "\n", encoding="utf-8")
        temporary.replace(path)