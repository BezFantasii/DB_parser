"""Collect visible Ozon search/category cards. Python 3.9+."""
import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# Avoid generated CSS class names. These selectors may still need updating
# when Ozon changes its markup. Only listing cards are supported.
LISTING_ROOTS_JS = r"""() => {
    const roots = Array.from(document.querySelectorAll(
        '[data-widget="searchResultsV2"], [data-widget="searchResults"], [data-widget="catalogResults"], [data-widget="tileGrid"]'));
    if (roots.length) return roots;
    if (/^\/(search|category)\//.test(location.pathname)) {
        const main = document.querySelector('main, #layoutPage');
        if (main) return [main];
    }
    return [];
}"""
WAIT_FOR_CARDS = "() => (" + LISTING_ROOTS_JS + ")().some(root => root.querySelector('a[href*=\"/product/\"]'))"
EXTRACT_CARDS = r"""() => {
    const result = [];
    const roots = (__LISTING_ROOTS__)();
    for (const root of roots) {
        for (const link of root.querySelectorAll('a[href*="/product/"]')) {
            const titleNode = link.querySelector('[data-widget="webProductHeading"], [data-widget="webProductTitle"], span.tsBody500Medium');
            const name = (titleNode?.innerText || link.innerText || link.getAttribute('aria-label') || link.querySelector('img')?.alt || '').trim();
            if (!name || /₽/.test(name)) continue;
            let card = link;
            let priceBlock = null;
            // Stop at the smallest ancestor containing this product and a price.
            for (let depth = 0; depth < 7 && card && card !== root; depth++, card = card.parentElement) {
                const ids = new Set(Array.from(card.querySelectorAll('a[href*="/product/"]'))
                    .map(a => a.pathname.match(/-(\d+)\/?$/)?.[1] || a.pathname));
                if (ids.size > 1) break;
                priceBlock = card.querySelector('[data-widget="webPrice"]');
                if (!priceBlock) {
                    priceBlock = Array.from(card.querySelectorAll('span')).find(el => {
                        const style = getComputedStyle(el);
                        return /^\s*\d[\d\s\u00a0\u202f]*(?:[,.]\d{1,2})?\s*₽\s*$/.test(el.innerText)
                            && !el.closest('del, s') && !style.textDecorationLine.includes('line-through');
                    });
                }
                if (priceBlock) break;
            }
            if (!priceBlock) continue;
            const priceText = priceBlock.innerText.trim();
            const candidates = Array.from(priceBlock.querySelectorAll('span'));
            if (priceBlock.matches('span')) candidates.unshift(priceBlock);
            const current = candidates.find(el => {
                const style = getComputedStyle(el);
                return /^\s*\d[\d\s\u00a0\u202f]*(?:[,.]\d{1,2})?\s*₽\s*$/.test(el.innerText)
                    && !el.closest('del, s') && !style.textDecorationLine.includes('line-through');
            });
            // Do not guess if the price block has no identifiable current price.
            if (!current) continue;
            result.push({name, price_raw: current.innerText.trim(), price_text: priceText, url: link.href});
        }
    }
    return result;
}""".replace("__LISTING_ROOTS__", LISTING_ROOTS_JS)


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
    if parsed.path.startswith("/product/"):
        raise argparse.ArgumentTypeError("Передайте выдачу поиска или категорию, а не отдельный товар")
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
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError as exc:
        raise RuntimeError("Установите Playwright: python -m pip install playwright") from exc
    products = {}
    with sync_playwright() as p:
        launch_options = {"headless": not args.headed}
        if args.channel:
            launch_options["channel"] = args.channel
        if args.direct:
            launch_options["args"] = ["--no-proxy-server"]
        context_options = {"locale": "ru-RU", "viewport": {"width": 1440, "height": 1000}}
        browser = None
        if args.profile:
            context = p.chromium.launch_persistent_context(
                str(args.profile.resolve()), **launch_options, **context_options)
        else:
            browser = p.chromium.launch(**launch_options)
            context = browser.new_context(**context_options)
        page = context.new_page()
        page.set_default_timeout(args.timeout * 1000)
        try:
            for number in range(args.start_page, args.start_page + args.pages):
                open_listing(page, args.url, number, args.manual)
                check_access_page(page)
                try:
                    page.wait_for_function(WAIT_FOR_CARDS)
                except PlaywrightTimeout as exc:
                    info = listing_diagnostics(page)
                    raise RuntimeError("Не найдена выдача товаров. Откройте поиск/категорию с товарами перед Enter. "
                                       "Диагностика: " + json.dumps(info, ensure_ascii=False)) from exc
                before = len(products)
                stable = 0
                previous_keys = set()
                for _ in range(args.scrolls):
                    raw_cards = page.evaluate(EXTRACT_CARDS)
                    keys = set()
                    for card in raw_cards:
                        key, product = normalize_card(card)
                        keys.add(key)
                        # Keep the first displayed price for repeated products.
                        products.setdefault(key, product)
                    stable = stable + 1 if keys == previous_keys else 0
                    previous_keys = keys
                    if args.limit and len(products) >= args.limit:
                        break
                    if stable >= 3:
                        break
                    page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.8, 600))")
                    page.wait_for_timeout(args.delay * 1000)
                if not previous_keys:
                    raise RuntimeError("Ссылки товаров есть, но названия/цены не распознаны. Диагностика: "
                                       + json.dumps(listing_diagnostics(page), ensure_ascii=False))
                print("Страница %s: новых товаров %s" % (number, len(products) - before), file=sys.stderr)
                if args.limit and len(products) >= args.limit:
                    break
                if number < args.start_page + args.pages - 1:
                    page.wait_for_timeout(args.delay * 1000)
        finally:
            context.close()
            if browser is not None:
                browser.close()
    result = list(products.values())
    return result[:args.limit] if args.limit else result


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Названия и видимые цены товаров Ozon в JSON")
    parser.add_argument("url", type=validate_url, help="Ссылка на поиск или категорию Ozon")
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
        temporary.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
