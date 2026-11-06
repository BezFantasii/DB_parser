# Проверка Ozon без Selenium

Обычный установленный Google Chrome запускается с отдельным постоянным профилем. Python подключается через CDP и использует существующий HTML-парсер товаров. WebDriver, Selenium и подмена User-Agent/WebGL не используются.

Из корня проекта:

```powershell
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --limit 1
```

Можно передать настоящий URL карточки вместо запроса. Результаты записываются в `backend/test-results/ozon-session-products.json`, этапы — в `backend/test-results/ozon-session-report.json`. Профиль — `backend/data/ozon-chrome-session`, основной профиль пользователя не читается.

Собственный Chrome:

```powershell
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --chrome 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Необязательное время для ручной проверки в открытом окне:

```powershell
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --manual-wait 120
```

`--keep-open` оставляет отдельное окно открытым. К нему можно подключиться повторно через `--cdp-url http://127.0.0.1:PORT`, адрес выводится событием browser.ready. При подключении к существующему окну скрипт закрывает только свою вкладку. CDP-порт предназначен исключительно для localhost; не публикуйте его наружу.

Без успешного чтения реальной карточки скрипт завершится с ненулевым кодом и не перезапишет JSON результатом страницы CAPTCHA. Успешная проверка на Windows/Google Chrome повторена дважды 6 ноября 2026: получен товар 5914808027, цена 2436 RUB, рейтинг 5.0, 1750 отзывов. Это подтверждение проверенной конфигурации, а не гарантия будущего доступа с любого IP/браузера.

Диагностический `backend.ozon_access` позволяет отдельно сравнить Selenium-free Chromium и curl_cffi. Для TLS-пробы дополнительно нужен `pip install curl_cffi`. В проверенном окружении TLS-имперсонация и чистый Chromium/UC оставались на CAPTCHA; успешен именно обычный установленный Chrome/CDP. Системные proxy-настройки и VPN скрипт сбора не изменяет.
