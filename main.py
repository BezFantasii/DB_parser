"""One CLI for both product parsers, offline HTML and HTTP ingestion."""
import argparse
from pathlib import Path
from urllib.parse import quote

from contracts import dumps, loads
from ingest_client import send_batch


def search_url(marketplace, query):
    if marketplace == "wb":
        return "https://www.wildberries.ru/catalog/0/search.aspx?search=" + quote(query)
    return "https://www.ozon.ru/search/?text=" + quote(query)


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Ожидается положительное число")
    return number


def build_parser():
    parser = argparse.ArgumentParser(description="Парсеры товаров Ozon и Wildberries без ORM")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "parse-html", "import"):
        child = sub.add_parser(command)
        child.add_argument("marketplace", choices=["wb", "ozon"])
        child.add_argument("source", help="Запрос/URL для collect, путь для parse-html/import")
        child.add_argument("--server", default="http://127.0.0.1:8000")
        if command != "import":
            child.add_argument("--output", type=Path)
            child.add_argument("--no-send", action="store_true", help="Только JSON, без сервера")
        if command == "parse-html":
            child.add_argument("--url", required=True, help="Исходный URL сохранённой карточки")
        if command == "collect":
            child.add_argument("--limit", type=positive, default=5)
            child.add_argument("--scrolls", type=positive, default=3)
            child.add_argument("--pages", type=positive, default=1)
            child.add_argument("--timeout", type=positive, default=45)
            child.add_argument("--delay", type=positive, default=2)
            child.add_argument("--headless", action="store_true")
            child.add_argument("--manual", action="store_true")
            child.add_argument("--channel", choices=["chrome", "msedge"])
            child.add_argument("--profile")
            child.add_argument("--direct", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "import":
            items = loads(Path(args.source).read_text(encoding="utf-8"))
            source_url = "import:" + Path(args.source).name
        else:
            from parsers import ParserOzon, ParserWildberries
            factory = ParserWildberries if args.marketplace == "wb" else ParserOzon
            if args.command == "parse-html":
                source_url = args.url
                parser = factory(source_url)
                items = [parser._parse_data(Path(args.source).read_text(encoding="utf-8"))]
            else:
                source_url = args.source if args.source.startswith("https://") else search_url(args.marketplace, args.source)
                parser = factory(source_url, headed=not args.headless, manual=args.manual,
                                 channel=args.channel, profile=args.profile, direct=args.direct,
                                 limit=args.limit, pages=args.pages, scrolls=args.scrolls,
                                 timeout=args.timeout, delay=args.delay)
                items = parser.get_data()
            if args.output:
                parser.writing_in_json(items, args.output)
            if args.no_send:
                if not args.output:
                    print(dumps(items))
                return 0
        result = send_batch({"marketplace": args.marketplace, "source_url": source_url, "items": items}, args.server)
        print(dumps(result))
        return 0
    except Exception as exc:
        print("Ошибка: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
