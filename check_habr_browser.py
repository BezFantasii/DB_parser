"""Test the browser configuration from the user-provided Habr guide."""
import json
import argparse
from playwright.sync_api import sync_playwright

INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--mode", choices=["guide", "current_chromium", "installed_chrome"])
    args = parser.parse_args()
    with sync_playwright() as p:
        for mode in ([args.mode] if args.mode else ("guide", "current_chromium", "installed_chrome")):
            options = dict(headless=not args.headed, args=["--disable-blink-features=AutomationControlled"])
            if mode == "installed_chrome":
                options["channel"] = "chrome"
            try:
                browser = p.chromium.launch(**options)
            except Exception as exc:
                print(json.dumps({"mode": mode, "error": str(exc)}, ensure_ascii=True), flush=True)
                continue
            try:
                settings = dict(viewport={"width": 1920, "height": 1080}, locale="ru-RU")
                if mode == "guide":
                    settings["user_agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                else:
                    probe = browser.new_page()
                    settings["user_agent"] = probe.evaluate("navigator.userAgent").replace("HeadlessChrome/", "Chrome/")
                    probe.close()
                context = browser.new_context(**settings)
                if mode == "guide":
                    context.add_init_script(INIT_SCRIPT)
                else:
                    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                page = context.new_page()
                failures = []
                page.on("response", lambda r: failures.append({"status": r.status, "path": r.url.split('?')[0]}) if r.status >= 400 else None)
                response = page.goto("https://www.ozon.ru/search/?text=наушники&from_global=true", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                print(json.dumps({"mode": mode, "status": response.status if response else None,
                                  "title": page.title(), "product_links": page.locator("a[href*='/product/']").count(),
                                  "webdriver": page.evaluate("navigator.webdriver"), "failures": failures}, ensure_ascii=True), flush=True)
            except Exception as exc:
                print(json.dumps({"mode": mode, "error": str(exc)}, ensure_ascii=True), flush=True)
            finally:
                browser.close()


if __name__ == "__main__":
    main()
