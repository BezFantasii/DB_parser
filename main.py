"""Сбор товаров маркетплейсов в PostgreSQL (схема из ТЗ v2.0).

Команды (запускать из терминала PyCharm, не из Python Console):
  python main.py collect wb "наушники" --limit 5
  python main.py collect ozon "наушники" --limit 10
  python main.py import products.json

Нужна переменная окружения DATABASE_URL (см. db.py).
Для collect ozon рядом должен лежать ozon_parser.py напарника.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

import db
import import_ozon
from features import extract_all

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ======================= Wildberries =======================
def wb_search_url(query):
    return "https://www.wildberries.ru/catalog/0/search.aspx?search=" + quote(query)


def wb_product_url(nm_id):
    return "https://www.wildberries.ru/catalog/%s/detail.aspx" % nm_id


def new_browser_page(p):
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
    nm_ids = set()  # set убирает дубли

    with Stealth().use_sync(sync_playwright()) as p:
        browser, page = new_browser_page(p)
        page.goto(wb_search_url(query), timeout=30000)
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


def read_specs(page):
    """Открывает окно 'Характеристики и описание' и возвращает его текст.

    На странице несколько элементов role=dialog (часть служебные, например плеера),
    поэтому окно выбирается по заголовку. Если открыть не удалось, возвращает None:
    тогда признаки берутся только из названия товара.
    """
    try:
        for _ in range(4):  # кнопка появляется после прокрутки
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(500)
        page.get_by_text("Характеристики и описание", exact=True).first.click(timeout=5000)
        dialog = page.locator("[role='dialog']", has_text="Характеристики и описание").first
        dialog.wait_for(timeout=5000)
        page.wait_for_timeout(1500)
        text = dialog.inner_text(timeout=3000)
        page.keyboard.press("Escape")
        return text
    except Exception as exc:
        print("  характеристики не прочитаны (%s), признаки только из названия" % str(exc).splitlines()[0])
        return None


def parse_card(page, nm_id):
    page.goto(wb_product_url(nm_id), timeout=30000)
    page.wait_for_timeout(1500)
    close_phishing_banner(page)

    name = page.locator("[class*='productTitle']").first.inner_text()
    all_text = page.locator("body").inner_text()

    # три цены на странице: [0] вероятно с кошельком WB (догадка), [1] цена покупателя, [2] до скидки
    price_matches = re.findall(r"(\d[\d\s\xa0]*\d|\d)\s*₽", all_text)
    prices = [int(re.sub(r"\D", "", x)) for x in price_matches[:3]]
    if len(prices) < 3:
        raise ValueError("найдено цен: %s, нужно 3" % len(prices))

    brand = re.findall(r"^(\S+)\s*/", all_text, re.MULTILINE)
    # число с возможными пробелами перед словом 'оценок'/'оценка'/'оценки'
    feedbacks = re.findall(r"^(\d[\d \xa0\u2009]*)оцен", all_text, re.MULTILINE)
    rating = re.findall(r"^(\d,\d)\s*", all_text, re.MULTILINE)

    # окно характеристик открываем ПОСЛЕ чтения цен: в нём тоже есть цена
    specs_text = read_specs(page)

    return {
        "features": extract_all(name, specs_text),
        "external_id": str(nm_id),
        "name": name,
        "url": wb_product_url(nm_id),
        "brand": brand[0] if brand else None,
        "price": prices[1],
        "old_price": prices[2],  # в схеме v2.0 колонки нет, в базу не пишется
        "rating": float(rating[0].replace(",", ".")) if rating else None,
        "reviews_count": int(re.sub(r"\D", "", feedbacks[0])) if feedbacks else None,
    }


def parse_and_save_wb(conn, marketplace_id, run_id, nm_ids):
    saved = 0
    with Stealth().use_sync(sync_playwright()) as p:
        browser, page = new_browser_page(p)
        for nm_id in nm_ids:
            try:
                item = parse_card(page, nm_id)
                db.save_item(conn, marketplace_id, run_id, item)
                saved += 1
                print("Готово: %s - %s" % (nm_id, item["name"]))
            except Exception as exc:
                print("Ошибка на %s: %s" % (nm_id, exc))
                conn.rollback()
            page.wait_for_timeout(4000)  # пауза между товарами
        browser.close()
    return saved


def collect_wb(conn, query, max_scrolls, limit):
    marketplace_id = db.get_marketplace_id(conn, "wb")
    run_id = db.start_run(conn, marketplace_id, wb_search_url(query))
    try:
        ids = get_ids_from_search(query, max_scrolls)
        print("Найдено ID: %s" % len(ids))
        if not ids:
            raise RuntimeError("ID не найдены: поиск пуст или WB закрыл доступ")
        saved = parse_and_save_wb(conn, marketplace_id, run_id, ids[:limit])
        if saved == 0:
            raise RuntimeError("ни один товар не сохранён")
    except Exception as exc:
        conn.rollback()
        db.finish_run(conn, run_id, "failed", str(exc))
        raise
    db.finish_run(conn, run_id, "succeeded")
    print("Запуск %s завершён, сохранено товаров: %s" % (run_id, saved))


# ======================= Ozon =======================
def ozon_search_url(query):
    return "https://www.ozon.ru/search/?text=%s&from_global=true" % quote(query)


def collect_ozon(conn, query, limit, channel, profile):
    """Запускает парсер напарника (ozon_parser.py), затем грузит его JSON в базу.

    Парсер Ozon не меняется: он работает отдельным процессом. В режиме --manual
    он ждёт Enter в терминале, когда на странице появятся товары.
    """
    parser_path = Path(__file__).with_name("ozon_parser.py")
    if not parser_path.exists():
        raise FileNotFoundError("Не найден %s (парсер напарника)" % parser_path)

    marketplace_id = db.get_marketplace_id(conn, "ozon")
    url = ozon_search_url(query)
    run_id = db.start_run(conn, marketplace_id, url)
    out_path = Path("products_ozon.json")
    out_path.unlink(missing_ok=True)  # чтобы не загрузить старый файл, если парсер упадёт

    cmd = [sys.executable, str(parser_path), url, "--output", str(out_path),
           "--headed", "--manual", "--channel", channel, "--profile", profile,
           "--limit", str(limit)]
    try:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError("парсер Ozon завершился с кодом %s (причина выше, в консоли)" % result.returncode)
        items = import_ozon.load_items(out_path)
        saved, skipped = import_ozon.save_items(conn, marketplace_id, run_id, items)
        if saved == 0:
            raise RuntimeError("ни одна запись не загружена")
    except Exception as exc:
        conn.rollback()
        db.finish_run(conn, run_id, "failed", str(exc))
        raise
    db.finish_run(conn, run_id, "succeeded")
    print("Запуск %s завершён, загружено %s, пропущено %s" % (run_id, saved, skipped))


# ======================= командная строка =======================
def build_parser():
    parser = argparse.ArgumentParser(description="Сбор товаров маркетплейсов в PostgreSQL")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="собрать товары площадки по поисковому запросу")
    collect.add_argument("marketplace", choices=["wb", "ozon"])
    collect.add_argument("query")
    collect.add_argument("--limit", type=int, default=5, help="сколько карточек обработать")
    collect.add_argument("--scrolls", type=int, default=3, help="только wb: сколько раз прокрутить выдачу")
    collect.add_argument("--channel", default="msedge", choices=["chrome", "msedge"], help="только ozon: браузер")
    collect.add_argument("--profile", default=".ozon-profile", help="только ozon: папка профиля браузера")

    imp = sub.add_parser("import", help="загрузить готовый JSON парсера Ozon")
    imp.add_argument("path")
    return parser


def main():
    args = build_parser().parse_args()
    conn = db.get_connection()
    try:
        if args.command == "collect":
            if args.marketplace == "wb":
                collect_wb(conn, args.query, args.scrolls, args.limit)
            else:
                collect_ozon(conn, args.query, args.limit, args.channel, args.profile)
        else:
            import_ozon.import_file(conn, args.path)
    except Exception as exc:
        print("Ошибка: %s" % exc)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
