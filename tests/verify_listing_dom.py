"""Browser smoke test with routed fixtures: no requests to marketplace servers."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parsers import ParserOzon, ParserWildberries
from playwright.sync_api import sync_playwright


def main():
    fixtures = Path(__file__).with_name("fixtures")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            result = []
            for factory, url, filename in (
                (ParserOzon, "https://www.ozon.ru/product/test-123/", "ozon_product.html"),
                (ParserWildberries, "https://www.wildberries.ru/catalog/456/detail.aspx", "wb_product.html"),
            ):
                html = (fixtures / filename).read_text(encoding="utf-8")
                page.route("**/*", lambda route, request, html=html: route.fulfill(status=200, body=html, content_type="text/html"))
                parser = factory(url, headed=False, delay=0)
                result.append(parser._parse_card(page, url))
                page.unroute("**/*")
            assert result[0].keys() == result[1].keys()
            assert result[0]["price"] == result[1]["price"]
            assert result[0]["observed_at"]
            print("PASS: browser DOM -> shared WB product format, two marketplaces, no network")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
