"""Browser fixture checks for listing selectors; no network requests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ozon_parser import EXTRACT_CARDS, WAIT_FOR_CARDS
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        page = browser.new_page()
        for widget in ("searchResultsV2", "searchResults", "catalogResults", "tileGrid"):
            page.set_content(f'''<div data-widget="{widget}"><div>
                <a href="https://www.ozon.ru/product/test-123/">Наушники</a>
                <span>1 299 ₽</span></div></div>''')
            assert page.evaluate(WAIT_FOR_CARDS), widget
            cards = page.evaluate(EXTRACT_CARDS)
            assert len(cards) == 1 and cards[0]["price_raw"] == "1 299 ₽", (widget, cards)
        page.set_content('<a href="https://www.ozon.ru/product/test-123/">Рекомендация</a>')
        assert not page.evaluate(WAIT_FOR_CARDS)
        assert page.evaluate(EXTRACT_CARDS) == []
        print("PASS: four listing widgets and unrelated product link")
    finally:
        browser.close()
