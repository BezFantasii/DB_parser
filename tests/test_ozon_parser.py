import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("ozon_parser", Path(__file__).resolve().parents[1] / "ozon_parser.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ParserTests(unittest.TestCase):
    def test_access_denied_page_reports_incident(self):
        page = Mock()
        page.locator.return_value.inner_text.return_value = (
            "Похоже, нет соединения\nОбратиться в поддержку\nИнцидент: fab_chlg_test")
        with self.assertRaisesRegex(RuntimeError, "Инцидент: fab_chlg_test"):
            module.check_access_page(page)

    def test_listing_is_not_mistaken_for_access_denied_page(self):
        page = Mock()
        page.locator.return_value.inner_text.return_value = "Наушники 1 299 ₽"
        module.check_access_page(page)

    def test_manual_403_allows_user_to_open_listing(self):
        page = Mock()
        page.goto.return_value.status = 403
        with patch("builtins.input", return_value="") as prompt:
            module.open_listing(page, "https://www.ozon.ru/search/?text=test", 1, True)
        prompt.assert_called_once()

    def test_automatic_403_reports_recovery_options(self):
        page = Mock()
        page.goto.return_value.status = 403
        with patch("builtins.input") as prompt:
            with self.assertRaisesRegex(RuntimeError, "HTTP 403.*--profile"):
                module.open_listing(page, "https://www.ozon.ru/search/", 1, False)
        prompt.assert_not_called()

    def test_manual_mode_does_not_ignore_other_http_errors(self):
        page = Mock()
        page.goto.return_value.status = 500
        with patch("builtins.input") as prompt:
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                module.open_listing(page, "https://www.ozon.ru/search/", 1, True)
        prompt.assert_not_called()

    def test_prices(self):
        for raw, expected in [("1 299 ₽", 1299), ("12\u00a0999\u202f₽", 12999), ("99,50 ₽", 99.5), ("0 ₽", 0)]:
            self.assertEqual(module.parse_price(raw), expected)

    def test_ambiguous_prices_rejected(self):
        for raw in ["от 100 ₽", "100 ₽ 200 ₽", "нет цены", "-10 ₽"]:
            with self.assertRaises(ValueError):
                module.parse_price(raw)

    def test_pagination_preserves_filters(self):
        self.assertEqual(module.page_url("https://www.ozon.ru/search/?text=test&page=8&brand=1&brand=2", 3),
                         "https://www.ozon.ru/search/?text=test&brand=1&brand=2&page=3")

    def test_product_normalization(self):
        key, product = module.normalize_card({"name": " Наушники\n  test ", "price_raw": "1 000 ₽",
                                             "price_text": "1 000 ₽ с картой", "url": "https://ozon.ru/product/test-123/?from=search"})
        self.assertEqual(key, "123")
        self.assertEqual(product["name"], "Наушники test")
        self.assertEqual(product["price"], 1000)
        self.assertEqual(product["url"], "https://www.ozon.ru/product/test-123/")

    def test_foreign_url_rejected(self):
        import argparse
        for url in ["https://ozon.ru.evil.com/search/", "http://ozon.ru/search/", "https://user@ozon.ru/search/"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                module.validate_url(url)


if __name__ == "__main__":
    unittest.main()

