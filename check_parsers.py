"""Show parser results in the terminal without the ingest server or PostgreSQL."""
import argparse
from pathlib import Path
import sys

from contracts import dumps
from main import positive, search_url


def main(argv=None):
    cli = argparse.ArgumentParser(description="Проверка парсеров: данные сразу в терминале, без БД")
    cli.add_argument("marketplace", nargs="?", choices=["ozon", "wb", "both"], default="both")
    cli.add_argument("source", nargs="?", default="наушники", help="Поисковый запрос или URL карточки")
    cli.add_argument("--limit", type=positive, default=3)
    cli.add_argument("--manual", action="store_true", help="Дождаться Enter после загрузки страницы")
    cli.add_argument("--channel", choices=["chrome", "msedge", "chromium"], default="chrome")
    cli.add_argument("--offline", action="store_true", help="Прочитать учебные HTML-примеры вместо живых сайтов")
    args = cli.parse_args(argv)
    if args.marketplace == "both" and args.source.startswith("https://") and not args.offline:
        cli.error("Для URL укажите одну площадку: ozon или wb")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from parsers import ParserOzon, ParserWildberries
    selected = ("ozon", "wb") if args.marketplace == "both" else (args.marketplace,)
    failures = 0
    for code in selected:
        print("\n=== %s ===" % ("Ozon" if code == "ozon" else "Wildberries"), flush=True)
        try:
            factory = ParserOzon if code == "ozon" else ParserWildberries
            if args.offline:
                print("Учебный HTML-пример; это не свежие данные сайта.", flush=True)
                url = "https://www.ozon.ru/product/test-123/" if code == "ozon" else "https://www.wildberries.ru/catalog/456/detail.aspx"
                fixture = Path(__file__).parent / "tests/fixtures" / ("ozon_product.html" if code == "ozon" else "wb_product.html")
                items = [factory(url)._parse_data(fixture.read_text(encoding="utf-8"))]
            else:
                url = args.source if args.source.startswith("https://") else search_url(code, args.source)
                print("Открываю: " + url, flush=True)
                items = factory(url, limit=args.limit, headed=True, manual=args.manual,
                                channel=None if args.channel == "chromium" else args.channel,
                                profile=".ozon-profile" if code == "ozon" else ".wb-profile").get_data()
            print("Получено товаров: %s" % len(items), flush=True)
            print(dumps(items), flush=True)
        except Exception as exc:
            failures += 1
            print("Ошибка: " + str(exc), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
