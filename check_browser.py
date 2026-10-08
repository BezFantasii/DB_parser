"""Compare browser connectivity without collecting product data."""
import json
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        for direct in (False, True):
            options = {"headless": True}
            if direct:
                options["args"] = ["--no-proxy-server"]
            browser = p.chromium.launch(**options)
            try:
                context = browser.new_context(locale="ru-RU", viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                for url in ("https://example.com", "https://www.wikipedia.org", "https://www.ozon.ru/", "https://www.wildberries.ru/", "https://www.wildberries.ru/catalog/0/search.aspx?search=iphone "):
                    result = {"url": url, "direct": direct}
                    try:
                        response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        result.update(status=response.status if response else None,
                                      title=page.title(), final_url=page.url)
                    except Exception as exc:
                        result["error"] = str(exc)
                    print(json.dumps(result, ensure_ascii=True), flush=True)
            finally:
                browser.close()


if __name__ == "__main__":
    main()
