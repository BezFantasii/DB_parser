import json
import unittest
from decimal import Decimal
from pydantic import ValidationError
from backend.api import JobRequest
from backend.ozon_search import parse_search


class OzonSearchTests(unittest.TestCase):
    def test_current_json_skips_original_price_duplicates_and_wrong_hosts(self):
        tile={"action":{"link":"/product/hudi-123/?at=tracking"},"mainState":[
            {"priceV2":{"price":[{"text":"9 999 ₽","textStyle":"ORIGINAL_PRICE"},{"text":"1\u2009234,50 ₽","textStyle":"PRICE"}],"priceStyle":{"styleType":"CARD_PRICE"}}},
            {"id":"name","textDS":{"text":"Худи мужское"}}]}
        payload={"widgetStates":{"tileGridDesktop-1":json.dumps({"items":[tile,tile,{"action":{"link":"https://evil.test/product/x-44/"}}]}),"recommendations-2":json.dumps({"items":[tile]})}}
        items=parse_search(payload)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["price"],Decimal("1234.50"))
        self.assertEqual(items[0]["price_kind"],"card")
        self.assertEqual(items[0]["url"],"https://www.ozon.ru/product/hudi-123/")
        self.assertEqual(parse_search({"widgetStates":{"tileGridDesktop-1":"not JSON"}}),[])

    def test_compatible_engine_selection_and_validation(self):
        self.assertEqual(JobRequest(marketplace="ozon",source="худи").engine,"selenium")
        self.assertEqual(JobRequest(marketplace="ozon",source="худи",engine="chrome-session").engine,"chrome-session")
        with self.assertRaises(ValidationError):JobRequest(marketplace="wb",source="худи",engine="chrome-session")
        with self.assertRaises(ValidationError):JobRequest(marketplace="ozon",source="https://evil.test/",engine="chrome-session")


if __name__=="__main__":unittest.main()
