import unittest
from backend.ozon_access import inspect_html,check_url
from backend.ozon_session import valid_ozon_url


class OzonAccessTests(unittest.TestCase):
    def test_captcha_with_h1_is_not_a_product(self):
        state=inspect_html('<title>Antibot Captcha</title><h1>Проверка</h1>',"https://www.ozon.ru/",403)
        self.assertTrue(state["blocked"])
        self.assertTrue(inspect_html('<title>Antibot Captcha</title><h1>Проверка</h1>',"https://www.ozon.ru/")["blocked"])

    def test_nonbreaking_space_denial(self):
        self.assertTrue(inspect_html('<title>Ozon</title><div>Похоже, нет&nbsp;соединения</div>',"https://www.ozon.ru/")["blocked"])

    def test_valid_listing(self):
        state=inspect_html('<title>Наушники</title><a href="/product/test-123/">Товар</a>',"https://www.ozon.ru/search/",200)
        self.assertFalse(state["blocked"])
        self.assertEqual(state["product_links"],1)

    def test_target_validation(self):
        for validate in (check_url,valid_ozon_url):
            for url in ("http://www.ozon.ru/","https://evil.example/","https://user:password@www.ozon.ru/","https://www.ozon.ru:8443/"):
                with self.assertRaises(ValueError):validate(url)


if __name__=="__main__":unittest.main()
