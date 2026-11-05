import re
import time
from bs4 import BeautifulSoup
from .base import Parser
from features import extract_all


class ParserWildberries(Parser):
    site = "wb"

    def _parse_data(self, source, url):
        soup = BeautifulSoup(source, "html.parser")
        
        # 1. Название
        title_elem = soup.select_one("[class*='productTitle']")
        if not title_elem:
            raise ValueError("Не найдено название товара")
        name = title_elem.get_text(strip=True)

        # 2. Текст всей страницы для поиска цен и рейтинга
        all_text = soup.body.get_text("\n", strip=True) if soup.body else ""
        
        # 3. Цены
        price_matches = re.findall(r"(\d[\d\s\xa0]*\d|\d)\s*₽", all_text)
        prices = [int(re.sub(r"\D", "", x)) for x in price_matches[:3]]
        if len(prices) < 3:
            raise ValueError("найдено цен: %s, нужно 3" % len(prices))

        # 4. Бренд, отзывы, рейтинг
        brand = re.findall(r"^(\S+)\s*/", all_text, re.MULTILINE)
        feedbacks = re.findall(r"^(\d[\d \xa0\u2009]*)оцен", all_text, re.MULTILINE)
        rating = re.findall(r"^(\d,\d)\s*", all_text, re.MULTILINE)
        
        # 5. Извлечение nm_id из url
        m = re.search(r"/catalog/(\d+)/detail", url)
        nm_id = m.group(1) if m else "unknown"

        return {
            "external_id": nm_id,
            "name": name,
            "url": url,
            "brand": brand[0] if brand else None,
            "price": prices[1],
            "old_price": prices[2],
            "rating": float(rating[0].replace(",", ".")) if rating else None,
            "reviews_count": int(re.sub(r"\D", "", feedbacks[0])) if feedbacks else None,
        }

    def read_specs(self, driver):
        """Открывает окно 'Характеристики и описание' и возвращает его текст."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
        
        try:
            for _ in range(4):
                driver.execute_script("window.scrollBy(0, 1200);")
                time.sleep(0.5)
                
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[text()='Характеристики и описание']"))
            )
            btn.click()
            
            dialog = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//*[@role='dialog' and contains(., 'Характеристики и описание')]"))
            )
            time.sleep(1.5)
            text = dialog.text
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            return text
        except Exception:
            return None