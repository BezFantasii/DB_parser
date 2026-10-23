import copy
from decimal import Decimal
import http.client
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts import ITEM_KEYS, dumps, loads, normalize_item, validate_batch
from parsers import ParserOzon, ParserWildberries
import db
from server import create_server

OZON = "https://www.ozon.ru/product/headphones-123/"
WB = "https://www.wildberries.ru/catalog/456/detail.aspx"
HTML = '''<html><h1>Беспроводные наушники с ANC и микрофоном</h1>
<script type="application/ld+json">{
 "@type":"Product", "name":"Title", "brand":{"name":"Test"},
 "offers":{"@type":"Offer","price":"1299.50","priceCurrency":"RUB"},
 "aggregateRating":{"ratingValue":"4.8","reviewCount":1200}}
</script><div class="recommendations"><span>99 ₽</span></div></html>'''


def batch():
    item = ParserOzon(OZON)._parse_data(HTML)
    return {"marketplace": "ozon", "source_url": OZON, "items": [item]}


class ProductContractTests(unittest.TestCase):
    def test_two_parsers_have_identical_wb_format_and_values(self):
        ozon = ParserOzon(OZON)._parse_data(HTML)
        wb = ParserWildberries(WB)._parse_data(HTML)
        self.assertEqual(set(ozon), set(ITEM_KEYS))
        self.assertEqual(set(wb), set(ozon))
        for key in set(ITEM_KEYS) - {"external_id", "url"}:
            self.assertEqual(ozon[key], wb[key])
        self.assertEqual(ozon["price"], Decimal("1299.50"))
        self.assertEqual(ozon["reviews_count"], 1200)
        self.assertTrue(ozon["features"]["anc"])

    def test_unknown_price_not_taken_from_recommendations(self):
        with self.assertRaisesRegex(ValueError, "цена"):
            ParserOzon(OZON)._parse_data('<h1>Наушники</h1><aside>99 ₽</aside>')

    def test_dom_price_does_not_require_three_prices(self):
        html = '<h1>Наушники</h1><div data-widget="webPrice"><span>1 299 ₽</span><del>2 000 ₽</del></div>'
        item = ParserOzon(OZON)._parse_data(html)
        self.assertEqual(item["price"], 1299)
        self.assertEqual(item["old_price"], 2000)

    def test_multi_digit_count_and_decimal_roundtrip(self):
        payload = loads(dumps(batch()))
        item = validate_batch(payload)[2][0]
        self.assertEqual(item["price"], Decimal("1299.50"))

    def test_product_jsonld_ignores_recommendations(self):
        html = HTML.replace('"@type":"Product",', '"@type":"Product", "url":"https://www.ozon.ru/product/other-999/",')
        with self.assertRaises(ValueError):
            ParserOzon(OZON)._parse_data(html)

    def test_validation_rejects_invalid_database_values(self):
        valid = batch()["items"][0]
        for patch_value in ({"price":"NaN"}, {"price":-1}, {"rating":6},
                            {"reviews_count":True}, {"external_id":"999"},
                            {"features":{"anc":"false"}}, {"features":{"battery_hours":"1000"}},
                            {"currency":"usd"}, {"observed_at":"2026-10-23T10:00:00"},
                            {"url":"https://evil.com/product/test-123/"}):
            with self.subTest(patch_value=patch_value), self.assertRaises(ValueError):
                normalize_item(dict(valid, **patch_value), "ozon")

    def test_duplicate_batch_rejected(self):
        payload = batch()
        payload["items"] *= 2
        with self.assertRaisesRegex(ValueError, "Повтор"):
            validate_batch(payload)


class TransactionTests(unittest.TestCase):
    def test_atomic_batch_commit(self):
        conn = MagicMock()
        with patch.object(db, "get_marketplace_id", return_value=2), patch.object(db, "start_run", return_value=7), \
             patch.object(db, "save_item", return_value=11) as save, patch.object(db, "finish_run") as finish:
            result = db.save_batch(conn, batch())
        self.assertEqual(result["saved"], 1)
        self.assertFalse(save.call_args.kwargs["commit"])
        finish.assert_called_once_with(conn, 7, "succeeded")

    def test_failure_rolls_back_and_records_failed_run(self):
        conn = MagicMock()
        with patch.object(db, "get_marketplace_id", return_value=2), patch.object(db, "start_run", return_value=7), \
             patch.object(db, "save_item", side_effect=RuntimeError("SQL failure")), patch.object(db, "finish_run") as finish:
            with self.assertRaises(RuntimeError):
                db.save_batch(conn, batch())
        conn.rollback.assert_called_once()
        self.assertEqual(finish.call_args.args[2], "failed")

class HttpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"INGEST_API_TOKEN": "test-token"}):
            cls.server = create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, token="test-token"):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {"Content-Type":"application/json", "Authorization":"Bearer " + token}
        try:
            connection.request(method, path, dumps(body).encode("utf-8") if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    def test_health_without_database(self):
        self.assertEqual(self.request("GET", "/health")[0], 200)

    def test_success_closes_connection(self):
        conn = MagicMock()
        with patch.object(db, "get_connection", return_value=conn), patch.object(db, "save_batch", return_value={"saved":1}):
            status, data = self.request("POST", "/api/v1/batches", batch())
        self.assertEqual((status, data["saved"]), (201, 1))
        conn.close.assert_called_once()

    def test_invalid_batch_never_connects_to_database(self):
        payload = batch()
        payload["items"][0]["rating"] = 7
        with patch.object(db, "get_connection") as connect:
            self.assertEqual(self.request("POST", "/api/v1/batches", payload)[0], 400)
        connect.assert_not_called()

    def test_missing_token_never_connects_to_database(self):
        with patch.object(db, "get_connection") as connect:
            self.assertEqual(self.request("POST", "/api/v1/batches", batch(), token="wrong")[0], 401)
        connect.assert_not_called()

    def test_database_unavailable_returns_503(self):
        with patch.object(db, "get_connection", side_effect=RuntimeError("secret")):
            status, response = self.request("POST", "/api/v1/batches", batch())
        self.assertEqual(status, 503)
        self.assertNotIn("secret", dumps(response))


if __name__ == "__main__":
    unittest.main()
