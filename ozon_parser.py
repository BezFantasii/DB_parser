"""Ozon CLI compatibility and shared ParserOzon product collection."""
import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# Historical CLI utility functions below are retained for existing callers.
# Product collection is implemented by parsers.ozon.ParserOzon.


def listing_diagnostics(page):
    return page.evaluate("""() => ({
        url: location.origin + location.pathname,
        title: document.title,
        product_links: document.querySelectorAll('a[href*="/product/"]').length,
        widgets: Array.from(new Set(Array.from(document.querySelectorAll('[data-widget]')),
            el => el.getAttribute('data-widget')))
    })""")


def parse_price(raw):
    """Return rubles as a JSON number; never turn an invalid price into zero."""
    cleaned = re.sub(r"[\s\u00a0\u202f]", "", raw).removesuffix("₽")
    if not re.fullmatch(r"\d+(?:[,.]\d{1,2})?", cleaned):
        raise ValueError("Нераспознанная цена: " + repr(raw))
    try:
        value = Decimal(cleaned.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Некорректная цена") from exc
    return int(value) if value == value.to_integral_value() else float(value)


def validate_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {"ozon.ru", "www.ozon.ru"} or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("Нужна HTTPS-ссылка на ozon.ru или www.ozon.ru")
    return value


def page_url(url, number):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
    query.append(("page", str(number)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def normalize_card(card):
    parts = urlsplit(card["url"])
    if parts.hostname not in {"ozon.ru", "www.ozon.ru"}:
        raise ValueError("Ссылка товара вне Ozon")
    url = urlunsplit(("https", "www.ozon.ru", parts.path, "", ""))
    match = re.search(r"-(\d+)/?$", parts.path)
    key = match.group(1) if match else url
    name = " ".join(card["name"].split())
    if not name:
        raise ValueError("Пустое название")
    return key, {"name": name, "price": parse_price(card["price_raw"]),
                 "currency": "RUB", "price_text": card["price_text"], "url": url}


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Значение должно быть больше нуля")
    return number


def open_listing(page, url, number, manual):
    response = page.goto(page_url(url, number), wait_until="domcontentloaded")
    status = response.status if response is not None else None
    if status is not None and status >= 400:
        if status != 403 or not manual:
            hint = "; попробуйте --headed --manual --profile .ozon-profile" if status == 403 else ""
            raise RuntimeError("Ozon вернул HTTP %s на странице %s%s" % (status, number, hint))
        print("Ozon вернул HTTP 403. Окно оставлено открытым для ручной проверки доступа.", file=sys.stderr)
    if manual:
        input("Выберите регион/пройдите проверку в браузере. Если нужно, обновите страницу. Когда появятся товары, нажмите Enter здесь: ")
    # After manual navigation the initial HTTP status is stale. The caller
    # verifies that listing cards are actually present in the current page.


def check_access_page(page):
    text = page.locator("body").inner_text(timeout=5000)
    if "Похоже, нет соединения" in text and "Обратиться в поддержку" in text:
        incident = re.search(r"Инцидент:\s*(\S+)", text)
        detail = " Инцидент: " + incident.group(1) if incident else ""
        raise RuntimeError(
            "Ozon показывает страницу отказа в доступе, а не товары. "
            "Проверьте эту ссылку в обычном браузере; если ошибка та же, "
            "попробуйте отключить VPN или использовать другую сеть. "
            "--direct отключает только браузерный прокси, но не системный VPN."
            + detail)


def prepare_profile(args):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        options = {"headless": False, "channel": args.channel or "chrome",
                   "locale": "ru-RU", "viewport": {"width": 1440, "height": 1000}}
        if args.direct:
            options["args"] = ["--no-proxy-server"]
        context = p.chromium.launch_persistent_context(str(args.profile.resolve()), **options)
        closed = False

        def on_close(*_):
            nonlocal closed
            closed = True

        context.on("close", on_close)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=args.timeout * 1000)
            print("Подготовка профиля: откройте товары, при необходимости войдите в Ozon. "
                  "Затем закройте все окна этого отдельного Chrome. Пароли вводите только в браузере.", flush=True)
            while not closed:
                if not context.pages:
                    break
                try:
                    context.pages[0].wait_for_timeout(500)
                except Exception:
                    if closed or not context.pages:
                        break
                    raise
        finally:
            if not closed:
                context.close()
    print("Профиль сохранён: %s" % args.profile.resolve())
    return 0


def scrape(args):
    """Ozon now uses the same card pipeline and output contract as WB."""
    from parsers.ozon import ParserOzon
    parser = ParserOzon(args.url, headed=args.headed, manual=args.manual,
                        channel=args.channel, profile=args.profile, direct=args.direct,
                        timeout=args.timeout, scrolls=args.scrolls, delay=args.delay,
                        limit=args.limit, pages=args.pages, start_page=args.start_page)
    return parser.get_data()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Названия и видимые цены товаров Ozon в JSON")
    parser.add_argument("url", type=validate_url, help="Ссылка на карточку, поиск или категорию Ozon")
    parser.add_argument("--output", type=Path, default=Path("products.json"))
    parser.add_argument("--pages", type=positive_int, default=1)
    parser.add_argument("--start-page", type=positive_int, default=1)
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--scrolls", type=positive_int, default=25)
    parser.add_argument("--delay", type=positive_int, default=2, help="Пауза между прокрутками/страницами, секунды")
    parser.add_argument("--timeout", type=positive_int, default=45)
    parser.add_argument("--headed", action="store_true", help="Показать окно браузера")
    parser.add_argument("--manual", action="store_true", help="Ждать ручного подтверждения после открытия каждой страницы")
    parser.add_argument("--profile", type=Path, help="Отдельная папка профиля для сохранения cookies и сессии")
    parser.add_argument("--channel", choices=["chrome", "msedge"], help="Использовать установленный Chrome или Edge")
    parser.add_argument("--direct", action="store_true", help="Отключить браузерный прокси (не отключает системный VPN)")
    parser.add_argument("--prepare-profile", action="store_true", help="Открыть отдельный Chrome для ручной подготовки сессии; закрытие окна сохраняет профиль")
    args = parser.parse_args()
    if args.manual and not args.headed:
        parser.error("--manual используется вместе с --headed")
    if args.prepare_profile and not args.profile:
        parser.error("--prepare-profile требует --profile с отдельной папкой профиля")
    try:
        if args.prepare_profile:
            return prepare_profile(args)
        products = scrape(args)
        if not products:
            raise RuntimeError("Товары не найдены; JSON не записан")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        from contracts import dumps
        temporary.write_text(dumps(products) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (RuntimeError, ValueError, OSError) as exc:
        print("Ошибка: " + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Includes browser startup/navigation errors; preserve any existing JSON.
        print("Ошибка браузера: " + str(exc), file=sys.stderr)
        return 1
    print("Сохранено %s товаров: %s" % (len(products), args.output.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
