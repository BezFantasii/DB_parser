from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from urllib.parse import quote
import re
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="Ozon_parser",
    user="postgres",
    password="postgres123",
)
cursor = conn.cursor()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def new_browser_page(p):
    """Открывает браузер и возвращает (browser, page) с одинаковыми настройками."""
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="ru-RU",
    )
    return browser, context.new_page()


def close_phishing_banner(page):
    """Закрывает баннер про 'фишинговый сайт', если он появился."""
    try:
        page.locator("button:has-text('Закрыть')").first.click(timeout=2000)
    except Exception:
        pass


def get_ids_from_search(query, max_scrolls=5):
    url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote(query)}"
    nm_ids = set()

    with Stealth().use_sync(sync_playwright()) as p:
        browser, page = new_browser_page(p)
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2000)
        close_phishing_banner(page)

        for _ in range(max_scrolls):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)

        for link in page.locator("a[href*='/catalog/']").all():
            href = link.get_attribute("href")
            match = re.search(r"/catalog/(\d+)/detail", href or "")
            if match:
                nm_ids.add(int(match.group(1)))

        if not nm_ids:
            with open("search_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("ID не найдены, HTML страницы поиска сохранён в search_page.html")

        browser.close()

    return list(nm_ids)

def parse_multiple_products(nm_ids):
    results = []

    with Stealth().use_sync(sync_playwright()) as p:
        browser, page = new_browser_page(p)

        for nm_id in nm_ids:
            try:
                url = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
                page.goto(url, timeout=30000)
                page.wait_for_timeout(1500)
                close_phishing_banner(page)

                name = page.locator("[class*='productTitle']").first.inner_text()
                all_text = page.locator("body").inner_text()

                price_matches = re.findall(r"(\d[\d\s\xa0]*\d|\d)\s*₽", all_text)
                prices = [
                    int(x.replace(" ", "").replace("\u2009", "").replace("\xa0", ""))
                    for x in price_matches[:3]
                ]
                if len(prices) < 3:
                    raise ValueError(f"найдено цен: {len(prices)}, нужно 3 - пропускаем")

                brand_match = re.findall(r"^(\S+)\s*/", all_text, re.MULTILINE)
                feedbacks = re.findall(r"^(\d+)\s*оцен", all_text, re.MULTILINE)
                seller_name = re.findall(r"^(.+)\n^\d,\d", all_text, re.MULTILINE)
                rating = re.findall(r"^(\d,\d)\s*", all_text, re.MULTILINE)

                product_data = {
                    "product_id": nm_id,
                    "name": name,
                    "price": prices[1],
                    "basic_price": prices[2],
                    "brand": brand_match[0] if brand_match else None,
                    "feedbacks": int(re.sub(r"\D", "", feedbacks[0])) if feedbacks else None,
                    "seller_name": seller_name[0] if seller_name else None,
                    "rating": float(rating[0].replace(",", ".")) if rating else None,
                }

                save_products(product_data)
                results.append(product_data)
                print(f"Готово: {nm_id} - {name}")

            except Exception as e:
                print(f"Ошибка на {nm_id}: {e}")
                conn.rollback()  # без этого одна ошибка ломает все следующие вставки
                continue

            page.wait_for_timeout(4000)  # пауза между товарами

        browser.close()

    return results

def save_products(product_data):
    cursor.execute(
        """INSERT INTO products(product_id, name, brand, feedbacks_count, seller_name, rating)
        VALUES(%s,%s,%s,%s,%s,%s)
        ON CONFLICT (product_id) DO UPDATE SET
        name = EXCLUDED.name,
        seller_name = EXCLUDED.seller_name,
        brand = EXCLUDED.brand,
        rating = EXCLUDED.rating,
        feedbacks_count = EXCLUDED.feedbacks_count
        """,
        (
            product_data["product_id"],
            product_data["name"],
            product_data["brand"],
            product_data["feedbacks"],
            product_data["seller_name"],
            product_data["rating"],
        ),
    )
    cursor.execute(
        """INSERT INTO price_history(product_id, price, discount_price)
        VALUES(%s, %s, %s)""",
        (
            product_data["product_id"],
            product_data["basic_price"],
            product_data["price"],
        ),
    )
    conn.commit()

def run_pipeline(queries, max_scrolls=5, limit=30):
    for query in queries:
        print(f"=== Запрос: {query} ===")
        ids = get_ids_from_search(query, max_scrolls=max_scrolls)
        print(f"Найдено ID: {len(ids)}")
        parse_multiple_products(ids[:limit])

conn.rollback()
run_pipeline(["iPhone 16"], max_scrolls=3, limit=5)