# Backend API и два режима расширения

Используются текущие `parsers/ozon.py`, `parsers/wildberries.py` и Selenium/undetected-chromedriver из `parsers/base.py`. HTTP API и браузерный worker работают раздельно.

Для отдельной проверки Ozon без Selenium добавлен [Python-парсер через обычный Google Chrome/CDP](OZON.md): `python -m backend.ozon_session "наушники" --limit 1`. Живой сбор подтверждён на установленном Chrome в Windows; Docker Chromium пока остаётся на CAPTCHA.

## Запуск

Из корня проекта:

```powershell
docker compose -f backend/compose.yaml up --build -d
```

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- БД и число активных worker: http://127.0.0.1:8000/health/ready
- Локальный token по умолчанию: `local-development-token`.

Настройки: переменные окружения либо копия `backend/.env.example` в `backend/.env`:

```powershell
docker compose --env-file backend/.env -f backend/compose.yaml up --build -d
```

Для рабочего сервера задайте собственные `API_TOKEN` и `POSTGRES_PASSWORD` до создания volume. Пароль включается в URL подключения, поэтому его спецсимволы необходимо URL-кодировать. Изменение переменной не меняет пароль уже созданной базы.

API опубликован только на loopback. PostgreSQL наружу не опубликован. Для удалённого доступа нужен HTTPS reverse proxy перед `api:8000`. Расширение запрашивает разрешение на конкретный HTTPS-origin. Один API token даёт доступ ко всем данным этого экземпляра; разграничения пользователей здесь нет.

## Клиент

```powershell
Set-Location JS
npm.cmd ci
npm.cmd start
```

Главный экран: выбор режима → запрос/URL → задания → журнал этапов → полученные данные. Для backend укажите `http://127.0.0.1:8000` и token. Пустой token означает локальный token по умолчанию. Credentials передаются заголовком Authorization, не в URL.

Локальный режим выполняет JS-парсеры в рабочих вкладках и сохраняет данные в SQLite OPFS. Хранилища двух режимов независимы. Предыдущий расширенный локальный интерфейс сохранён как `advanced.html`, ссылка есть внизу страницы.

## Ручки API

Кроме `/health/*`, документации и OpenAPI, требуется `Authorization: Bearer <token>`.

| Метод / путь | Назначение |
|---|---|
| `GET /health/live` | HTTP-процесс жив |
| `GET /health/ready` | БД и активные исполнители |
| `GET /api/v1/marketplaces` | Площадки и режимы |
| `POST /api/v1/jobs` | Создать задание, HTTP 202 |
| `GET /api/v1/jobs` | Список: status, limit, offset |
| `GET /api/v1/jobs/{id}` | Состояние и ошибка |
| `GET /api/v1/jobs/{id}/events` | Этапы после after_id, next_cursor |
| `GET /api/v1/jobs/{id}/results` | Опубликованные результаты |
| `POST /api/v1/jobs/{id}/cancel` | Отмена и остановка парсинга |
| `POST /api/v1/jobs/{id}/retry` | Отдельный повтор остановленного задания |
| `GET /api/v1/products` | Последние предложения: marketplace, search, limit, offset |
| `GET /api/v1/products/{id}` | Товар |
| `GET /api/v1/products/{id}/history` | Наблюдения с контекстами цены |
| `GET /api/v1/products/{id}/analogs` | Аналоги по подтверждённым характеристикам |
| `POST /api/v1/batches` | Проверка и транзакционный импорт пакета |
| `POST /api/v1/parse-html` | Разбор предоставленного HTML, без браузера и записи |
| `GET /api/v1/export?format=json` | Страница последних предложений |
| `GET /api/v1/export?format=csv` | CSV с защитой от формул |

Пример:

```powershell
$headers = @{ Authorization = 'Bearer local-development-token' }
$body = @{ marketplace='wb'; source='наушники'; limit=3; pages=1; mode='live' } | ConvertTo-Json
$job = Invoke-RestMethod http://127.0.0.1:8000/api/v1/jobs -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/jobs/$($job.id)/events" -Headers $headers
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/jobs/$($job.id)/results" -Headers $headers
```

`headed=true` рисует браузер внутри Xvfb контейнера. Это не видимое окно и не интерфейс удалённого прохождения CAPTCHA. В расширении рабочую вкладку можно открыть для ручной проверки. Параметр `headed=false` включает headless; доступность сайта может отличаться.

## Данные и очередь

Три сервиса: PostgreSQL 16, FastAPI, последовательный browser worker. Данные PostgreSQL находятся в volume `marketplace-parser_postgres-data`; профили браузеров и журналы worker — в `marketplace-parser_parser-data`, каталог `/data`.

Таблицы находятся в отдельной схеме **parser_api**: jobs, events, products, observations, workers; представление current_prices. Существующие таблицы учебного проекта не меняются. Деньги сохраняются в нормализованных JSON как десятичные строки. История разделяется по региону, валюте и типу цены; последнее отсутствие товара не заменяется старой ценой.

Очередь использует `FOR UPDATE SKIP LOCKED`, lease и номер попытки. Каждое задание запускается отдельным процессом; отмена завершает его дерево процессов. После аварии возможен повтор всего сбора, после трёх аварий нужен явный retry. Этапы сохраняются в events, товары публикуются целым пакетом одной транзакцией. Отменённый/устаревший worker не может опубликовать пакет.

Текущая конфигурация рассчитана на **один browser worker**. Для масштабирования нужно разделить постоянные профили между исполнителями: защита очереди не предотвращает одновременное открытие одного профиля Chrome.

Перед открытием профиля backend берёт отдельную файловую блокировку. Устаревшие ссылки SingletonLock/Socket/Cookie от остановленного контейнера удаляются без удаления профиля; активная блокировка текущего процесса не снимается. Это позволяет сохранять сессию при пересоздании worker.

Режимы live, fixture и import различаются в заданиях и результатах. Fixture jobs по умолчанию отключены; включаются `ALLOW_FIXTURE_JOBS=1`. Они не обращаются к живым сайтам. JSON/CSV экспортирует последние предложения постранично, полная история находится в PostgreSQL.

Остановка с сохранением volumes:

```powershell
docker compose -f backend/compose.yaml stop
```

Резервная копия:

```powershell
docker compose -f backend/compose.yaml exec -T db pg_dump -U parser -d marketplace -Fc -f /tmp/marketplace.dump
docker compose -f backend/compose.yaml cp db:/tmp/marketplace.dump ./marketplace.dump
```

Восстанавливайте через pg_restore в отдельную новую БД. Перед заменой рабочей БД остановите API/worker. Не удаляйте volumes для обычного обновления.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
docker compose -f backend/compose.yaml exec -T api python -m backend.tests.integration
docker compose -f backend/compose.yaml exec -T worker xvfb-run -a python -m backend.tests.browser_smoke
```

Интеграционный тест создаёт отдельную временную PostgreSQL-базу и удаляет только её. Проверяет auth, параметры, оба парсера в дочерних процессах, события, историю, cancel/retry, настоящий rollback при SQL-ошибке и запрет публикации устаревшим worker. Browser smoke запускает настоящий Chromium на учебных HTML, но не подтверждает live-доступ.

Сквозной тест упрощённого клиента:

```powershell
docker compose -f backend/compose.yaml --profile test up -d test-api
Set-Location JS
npm.cmd run test:client
Set-Location ..
docker compose -f backend/compose.yaml stop test-api
```

Тестовый HTTP API на localhost:8001 использует отдельную временную БД и fixture worker. Штатная остановка удаляет эту БД. В автономном JS-тесте ответы сайтов подменяются HTML через Playwright. Скриншоты и отчёт: JS/test-results/client-*.

Живые проверки выполняются отдельно:

```powershell
.\.venv\Scripts\python.exe -u -m backend.check_live
Set-Location JS
npm.cmd run check:live
```

Отчёты: backend/test-results/live-backend*.json и JS/test-results/live-report.json. По сохранённому реальному URL можно проверить карточку отдельно: `backend.check_live --marketplace ozon --source HTTPS_URL`.

## Перенос нового кода

Сохранён алгоритм WB: productTitle, вторая из первых трёх сумм ₽ как цена, третья как старая цена, регулярные выражения бренда/рейтинга/оценок. Он перенесён в TypeScript. Для иного оформления предусмотрен структурированный fallback через HTML/JSON-LD. Соответствие первых трёх сумм нужному предложению зависит от разметки; тесты проверяют перенос правила, а не любую будущую страницу.

Selenium/UC невозможно запустить как обычный content script. В расширении перенесено извлечение данных, а браузерное управление заменено вкладками и DOM. Поэтому сетевой доступ двух вариантов может различаться. CAPTCHA и отказ сайта не выдаются за успешный сбор.

wb_ozon.py — отдельный старый прототип отзывов с запуском браузера при импорте; API товаров его не импортирует.
