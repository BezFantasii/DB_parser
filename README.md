# Парсеры Ozon / Wildberries: запуск и устройство проекта

В проекте есть несколько способов **получить товар**, несколько способов **сохранить результат** и два режима **Chrome-расширения**. Здесь описан текущий код, а не только план из ТЗ.

Команды рассчитаны на **PowerShell в Windows**. Если не указано иначе, рабочая папка:

```powershell
Set-Location 'E:\Baumanka\parser'
```

Запускайте команды в терминале, не в Python Console (`>>>`). Полный путь `.\.venv\Scripts\python.exe` позволяет работать без активации окружения.

## Содержание

1. [Какой вариант выбрать](#1-какой-вариант-выбрать)
2. [Архитектура и хранилища](#2-архитектура-и-хранилища)
3. [Подготовка окружения](#3-подготовка-окружения)
4. [Первые запуски](#4-первые-запуски)
5. [Отдельный Ozon через Chrome/CDP](#5-отдельный-ozon-через-chromecdp)
6. [Общий Python CLI](#6-общий-python-cli)
7. [Backend в Docker](#7-backend-в-docker)
8. [HTTP API на примерах](#8-http-api-на-примерах)
9. [Расширение](#9-расширение)
10. [Backend без Docker](#10-backend-без-docker)
11. [Старый сервер и прежняя БД](#11-старый-сервер-и-прежняя-бд)
12. [Другие программы и диагностика](#12-другие-программы-и-диагностика)
13. [Тесты](#13-тесты)
14. [Файлы и резервные копии](#14-файлы-и-резервные-копии)
15. [Ошибки и ограничения](#15-ошибки-и-ограничения)
16. [Важные функции](#16-важные-функции)
17. [Повседневный сценарий](#17-повседневный-сценарий)

## 1. Какой вариант выбрать

| Задача | Точка входа | Браузер | Сервер / БД |
|---|---|---|---|
| Изучить формат без интернета | `check_parsers.py --offline` | Не нужен | Не нужны |
| Проверить успешный Windows-вариант Ozon | `python -m backend.ozon_session` | Обычный Google Chrome, CDP | Не нужны; результат в JSON |
| Собрать стандартным Python-сборщиком | `main.py collect` | Selenium + undetected-chromedriver | Без сервера при `--no-send` |
| Разобрать готовый HTML | `main.py parse-html` | Не нужен | Без сервера при `--no-send` |
| Запустить API, задания, PostgreSQL | `backend/compose.yaml` | В worker-контейнере | API + worker + PostgreSQL |
| Управлять backend из браузера | Расширение, режим Backend | Клиентский Chrome/Chromium | Нужен backend |
| Собирать внутри браузера | Расширение, локальный режим | Рабочие вкладки | SQLite OPFS, сервер не нужен |
| Принимать JSON в прежнюю БД | `server.py` | Не нужен | Отдельная PostgreSQL |
| Импортировать JSON напрямую в прежнюю БД | `import_ozon.py` | Не нужен | Прежняя PostgreSQL-схема |
| Дозаполнить неизвестные признаки прежних товаров | `backfill_features.py` | Не нужен | Прежняя PostgreSQL-схема |

### Что реально проверялось

Журнал: [backend/VALIDATION.md](backend/VALIDATION.md).

- Обычный Google Chrome + Python/CDP на Windows дважды получил реальные товары Ozon.
- Docker/backend через Selenium получил реальный товар WB и записал его в PostgreSQL.
- Ozon внутри Docker оставался на 403/CAPTCHA, включая отдельную CDP-пробу с Chromium.
- Оба JS-парсера проверены на контрольных HTML; это не подтверждение успешного live-доступа в расширении.
- `live` — обращение к сайту, `fixture`/offline — учебный HTML, `import` — запись ранее полученных данных.

Windows/CDP-парсер **не подключён автоматически к Docker-worker**. Его JSON можно явно импортировать в API: раздел 5.

## 2. Архитектура и хранилища

```mermaid
flowchart TD
    U[Пользователь] --> EXT[Расширение: простой интерфейс]
    EXT -->|Backend: HTTP JSON| API[FastAPI]
    API <--> PG[(PostgreSQL: parser_api)]
    W[Docker worker] <-->|очередь и события| PG
    W --> CHILD[Процесс backend.collect]
    CHILD --> SEL[Selenium / Chromium]
    SEL --> M[Ozon / Wildberries]
    EXT -->|Локальный режим| SW[Service Worker]
    SW <--> CS[Content scripts]
    CS --> M
    SW --> OFF[Offscreen document + SQLite Worker]
    OFF <--> OPFS[(SQLite OPFS)]
    U --> CDP[Python OzonSession]
    CDP --> CHROME[Обычный Google Chrome]
    CHROME --> M
    CDP --> JSON[JSON-файл]
    JSON -->|явный main.py import| API
```

В проекте **три независимые структуры хранения**:

| Вариант | Где данные | Кто записывает |
|---|---|---|
| Новый backend | PostgreSQL, схема `parser_api`: jobs, events, products, observations, workers | `backend/store.py` |
| Прежний сервер / прямой импорт | Прежние таблицы, обычно схема public: marketplaces, products, parse_runs, price_history | `db.py` и `models_simple.py` |
| Локальное расширение | SQLite `/marketplace.sqlite3` в OPFS origin расширения | `JS/src/database.ts` |

`public.products` и `parser_api.products` имеют разные структуры. Данные SQLite не появляются в PostgreSQL автоматически. CDP-скрипт первоначально сохраняет только JSON.

## 3. Подготовка окружения

### 3.1. Python

Корневой код поддерживает Python 3.9+, для нового окружения рекомендуется 3.12; Docker использует 3.12.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Существующую `.venv` повторно создавать не нужно. Для FastAPI/worker или HTTP-проверок **вне Docker**:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Этот файл включает корневые зависимости. Для отдельного Ozon/CDP достаточно корневых зависимостей и Google Chrome.

Для диагностических скриптов, запускающих браузер Playwright:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Это не установка Google Chrome для CDP и не настройка Selenium. В Docker Chromium и chromedriver устанавливает образ. UC вне Docker может скачивать драйвер при первом запуске.

Активация `.venv\Scripts\Activate.ps1` необязательна. Если PowerShell её запрещает, используйте полный путь к `python.exe`.

### 3.2. Node.js

Для расширения нужен Node.js 24.5+:

```powershell
node --version
npm.cmd --version
Set-Location 'E:\Baumanka\parser\JS'
npm.cmd ci
Set-Location 'E:\Baumanka\parser'
```

`npm.cmd` не зависит от политики запуска `npm.ps1`. `npm ci` устанавливает версии из lock-файла.

### 3.3. Docker

Нужен Docker Desktop с Linux-контейнерами:

```powershell
docker version
docker compose version
docker info
```

Если Engine недоступен, запустите Docker Desktop; в поддерживаемой версии CLI есть `docker desktop start`. Для контейнерного backend не нужны локально установленные PostgreSQL и Chromium: они находятся в образах.

## 4. Первые запуски

### Без сети

```powershell
Set-Location 'E:\Baumanka\parser'
.\.venv\Scripts\python.exe check_parsers.py --offline
$LASTEXITCODE
```

Ожидайте отметку «Учебный HTML-пример», JSON Ozon/WB и код 0. Это проверка разбора, не доступности маркетплейса.

### Реальный Ozon без сервера

```powershell
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --limit 1
```

Ожидайте отдельное окно Chrome и этапы browser.ready → page.loading → listing.collected → product.parsed. Файл: `backend/test-results/ozon-session-products.json`.

### Backend и расширение

Терминал 1, корень проекта:

```powershell
docker compose -f backend/compose.yaml up --build -d
Invoke-RestMethod 'http://127.0.0.1:8000/health/ready'
```

После запуска ожидайте status=ok, database=ok, workers_online=1.

Терминал 2:

```powershell
Set-Location 'E:\Baumanka\parser\JS'
npm.cmd start
```

В клиенте выберите Backend, адрес `http://127.0.0.1:8000`, token `local-development-token`, сохраните подключение. Начните с WB и лимита 1. [Swagger API](http://127.0.0.1:8000/docs).

## 5. Отдельный Ozon через Chrome/CDP

Точка входа: `backend/ozon_session.py`; [дополнительная инструкция](backend/OZON.md).

```powershell
.\.venv\Scripts\python.exe -m backend.ozon_session "беспроводные наушники" --limit 3
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --chrome 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Вместо запроса можно передать настоящий HTTPS-URL карточки.

| Параметр | По умолчанию | Назначение |
|---|---|---|
| source | наушники | Запрос или URL Ozon |
| --limit | 1 | До 100 карточек |
| --wait | 20 | Ожидание готовности каждой страницы, 1–120 секунд |
| --manual-wait | 0 | Дополнительное время для проверки пользователем, до 600 секунд |
| --chrome | Автопоиск | Путь к обычному Chrome; также OZON_CHROME_BINARY / CHROME_BINARY |
| --profile | backend/data/ozon-chrome-session | Отдельный постоянный профиль |
| --cdp-url | Не задан | Подключение к отдельной сессии на localhost |
| --keep-open | Выключен | Оставить своё окно открытым |
| --no-warmup | Выключен | Не открывать главную страницу перед сбором |
| --output | backend/test-results/ozon-session-products.json | Файл товаров |

Для ручной проверки:

```powershell
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --manual-wait 120 --keep-open
```

Не открывайте второй Chrome с тем же профилем. Если окно оставлено, повторно подключитесь к адресу из browser.ready:

```powershell
# PORT замените портом из события browser.ready.
.\.venv\Scripts\python.exe -m backend.ozon_session "наушники" --cdp-url 'http://127.0.0.1:PORT'
```

Код возврата: 0 — товары получены, 2 — ошибка. Этапы сохраняются в `backend/test-results/ozon-session-report.json`. При ошибке существующий JSON товаров не заменяется CAPTCHA: проверяйте exit code и дату файла, чтобы не принять старый результат за новый.

Сборщик работает с одной выдачей и найденными ссылками, параметра `--pages` у него нет. В PostgreSQL он сам ничего не записывает.

### Загрузка его JSON в новый API

После успешного CDP-сбора и запуска Docker:

```powershell
$env:INGEST_API_TOKEN = 'local-development-token'
.\.venv\Scripts\python.exe main.py import ozon backend/test-results/ozon-session-products.json --server http://127.0.0.1:8000
```

`INGEST_API_TOKEN` — переменная Python HTTP-клиента. Значение должно совпадать с `API_TOKEN` сервера. В API это будет задание import: запись живого результата CDP, а не исполнение Docker-парсера.

## 6. Общий Python CLI

### 6.1. Посмотреть товары в терминале

```powershell
.\.venv\Scripts\python.exe check_parsers.py wb "наушники" --limit 3
.\.venv\Scripts\python.exe check_parsers.py ozon "наушники" --limit 1 --manual
.\.venv\Scripts\python.exe check_parsers.py both "игровые наушники" --limit 2
```

Показывает браузер, печатает JSON, не сохраняет файл и не обращается к БД. Сессии — `.wb-profile` и `.ozon-profile`. Enter в ручном режиме нажимается в терминале.

### 6.2. Собрать в файл без сервера

```powershell
.\.venv\Scripts\python.exe main.py collect wb "наушники" --limit 3 --no-send --output backend/data/wb-products.json
```

Без output результат no-send печатается в терминал. Один `--output` не отключает отправку: для работы только с файлом нужен `--no-send`.

### 6.3. Собрать на Windows и отправить пакет в API

```powershell
$env:INGEST_API_TOKEN = 'local-development-token'
.\.venv\Scripts\python.exe main.py collect wb "наушники" --limit 3 --server http://127.0.0.1:8000
```

Здесь браузер работает на Windows, сервер принимает импорт. Это отличается от POST /jobs, где браузер запускает worker.

### 6.4. Прочитать сохранённый HTML

```powershell
.\.venv\Scripts\python.exe main.py parse-html ozon tests/fixtures/ozon_product.html --url https://www.ozon.ru/product/test-123/ --no-send
.\.venv\Scripts\python.exe main.py parse-html wb tests/fixtures/wb_current.html --url https://www.wildberries.ru/catalog/456/detail.aspx --no-send
```

URL нужен для проверки карточки и артикула; перехода на сайт не будет.

### 6.5. Параметры main.py collect

| Параметр | По умолчанию | Значение |
|---|---|---|
| marketplace | Обязателен | ozon / wb |
| source | Обязателен | Запрос, URL карточки или выдачи |
| --limit | 5 | Верхняя граница карточек |
| --pages | 1 | Страницы выдачи |
| --scrolls | 3 | Прокрутки страницы |
| --timeout | 45 | Тайм-аут операций, секунды |
| --delay | 2 | Пауза; Selenium добавляет случайную задержку |
| --headless | Выключен | Без видимого окна |
| --manual | Выключен | Ждать Enter; несовместим с headless |
| --profile | Не задан | Отдельная папка профиля |
| --direct | Выключен | Отключить браузерный proxy, не системный VPN |
| --channel | Не задан | Старый аргумент; текущая Selenium-фабрика его не применяет |
| --no-send | Выключен | Не отправлять HTTP-пакет |
| --output | Не задан | Файл JSON |
| --server | http://127.0.0.1:8000 | Сервер приёма |

Числовые параметры CLI положительные: scrolls=0 здесь не разрешён, хотя API и JS допускают 0. Для прямой карточки поиск не используется. Лимит задаёт максимум, а не обещанное число товаров.

### 6.6. Отдельные совместимые точки входа

WB добавляет collect wb к аргументам общего CLI:

```powershell
.\.venv\Scripts\python.exe wildberries_parser.py "наушники" --limit 3 --no-send --output backend/data/wb-products.json
```

Прежний Ozon CLI требует URL, сохраняет JSON, не отправляет его серверу:

```powershell
.\.venv\Scripts\python.exe ozon_parser.py 'https://www.ozon.ru/search/?text=наушники' --headed --limit 1 --scrolls 3 --output backend/data/ozon-legacy.json
```

По умолчанию у него скрытое окно, 25 прокруток и нет заданного лимита — для проверки задавайте их явно. `--manual` требует `--headed`. Есть отдельная Playwright-ветка подготовки профиля:

```powershell
.\.venv\Scripts\python.exe ozon_parser.py 'https://www.ozon.ru/' --prepare-profile --profile .ozon-profile --channel chrome
```

После подготовки закройте её окно. В этой ветке channel действительно выбирает Playwright channel. Обычный сбор всё равно делегируется Selenium ParserOzon. Успешный Windows/CDP — другой путь, раздел 5.

## 7. Backend в Docker

### 7.1. Настройки

```powershell
Set-Location 'E:\Baumanka\parser'
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

Файл исключён из Git. Пример:

```dotenv
API_TOKEN=local-development-token
POSTGRES_PASSWORD=parser-local-development
API_PORT=8000
ALLOW_FIXTURE_JOBS=0
```

Для рабочего сервера задайте собственные credentials. Пароль входит в URL подключения, спецсимволы нужно URL-кодировать. Изменение переменной не меняет пароль уже созданной PostgreSQL-базы.

```powershell
docker compose --env-file backend/.env -f backend/compose.yaml up --build -d
docker compose -f backend/compose.yaml ps
```

Без собственного env-файла достаточно `docker compose -f backend/compose.yaml up --build -d`: применятся defaults Compose. При изменённых настройках продолжайте передавать --env-file последующим up.

### 7.2. Сервисы

| Сервис | Назначение | Доступ |
|---|---|---|
| db | PostgreSQL 16 | Только Docker-сеть |
| api | FastAPI, auth, валидация, ручки | localhost:8000 по умолчанию |
| worker | Очередь, процессы, Chromium | Без внешнего порта |
| test-api | Отдельный fixture-стенд с временной БД | Явный запуск, localhost:8001 |

API ждёт готовности БД, worker — API. Headed внутри Docker рисует на виртуальном дисплее Xvfb, не в окне Windows. VNC в проекте не реализован.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/health/live'
Invoke-RestMethod 'http://127.0.0.1:8000/health/ready'
docker compose -f backend/compose.yaml logs --tail 50 api worker
docker compose -f backend/compose.yaml logs -f worker
```

Ctrl+C у logs -f закрывает просмотр, не контейнеры. Workers_online=0 означает отсутствие свежего heartbeat; один HTTP status=ok не доказывает исполнение заданий.

### 7.3. Жизненный цикл задания

```mermaid
sequenceDiagram
    participant C as Клиент
    participant A as API
    participant D as PostgreSQL
    participant W as Worker
    participant P as Python-парсер
    C->>A: POST /jobs
    A->>D: INSERT queued
    A-->>C: 202 + job_id
    W->>D: claim, lease, attempt
    W->>P: backend.collect + JSON stdin
    loop Сбор и наблюдение
        P-->>W: NDJSON stdout
        W->>D: INSERT events
        C->>A: GET /events?after_id=cursor
        A->>D: Прочитать новые события
        A-->>C: Этапы + next_cursor
    end
    P-->>W: Полный массив товаров
    W->>D: Транзакция: товары + наблюдения + succeeded
    C->>A: GET /results
    A-->>C: Опубликованные результаты
```

HTTP создания не ждёт браузер. Закрытие клиента не отменяет сбор. При аварии backend может повторить весь запуск: частичные товары не сохраняются как готовый результат. В SQLite-режиме другая стратегия — промежуточные карточки сохраняются в staging.

## 8. HTTP API на примерах

[Swagger](http://127.0.0.1:8000/docs): нажмите Authorize и введите token. Health и документация доступны без token, остальные ручки требуют Bearer.

```powershell
$api = 'http://127.0.0.1:8000'
$headers = @{ Authorization = 'Bearer local-development-token' }
$body = @{
    marketplace = 'wb'
    source = 'наушники'
    limit = 1
    pages = 1
    scrolls = 2
    delay = 2
    timeout = 30
    headed = $true
    mode = 'live'
} | ConvertTo-Json
$job = Invoke-RestMethod "$api/api/v1/jobs" -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
$job
```

UTF-8-байты сохраняют кириллицу в Windows PowerShell. Переменные действуют в текущем терминале.

```powershell
Invoke-RestMethod "$api/api/v1/jobs/$($job.id)" -Headers $headers
Invoke-RestMethod "$api/api/v1/jobs/$($job.id)/events?after_id=0" -Headers $headers
Invoke-RestMethod "$api/api/v1/jobs/$($job.id)/results" -Headers $headers
Invoke-RestMethod "$api/api/v1/products?limit=100" -Headers $headers
```

До завершения результатов может не быть. Для следующей порции событий передайте предыдущий next_cursor как after_id.

```powershell
Invoke-RestMethod "$api/api/v1/jobs/$($job.id)/cancel" -Method Post -Headers $headers
# Для failed / blocked / cancelled retry создаёт НОВЫЙ id.
Invoke-RestMethod "$api/api/v1/jobs/$($job.id)/retry" -Method Post -Headers $headers
```

### Карта ручек

| Метод / путь | Результат |
|---|---|
| GET /health/live | Жив HTTP-процесс |
| GET /health/ready | БД и число worker |
| GET /api/v1/marketplaces | Площадки и разрешён ли fixture |
| POST /api/v1/jobs | Создать задание, HTTP 202 |
| GET /api/v1/jobs | Список: status, limit, offset |
| GET /api/v1/jobs/{id} | Состояние задания |
| GET /api/v1/jobs/{id}/events | Журнал: after_id, limit |
| GET /api/v1/jobs/{id}/results | Товары задания |
| POST /api/v1/jobs/{id}/cancel | Отмена queued/running |
| POST /api/v1/jobs/{id}/retry | Отдельный повтор |
| GET /api/v1/products | Последние предложения: marketplace, search, limit, offset |
| GET /api/v1/products/{id} | Товар |
| GET /api/v1/products/{id}/history | История: limit, offset |
| GET /api/v1/products/{id}/analogs | Подтверждённые аналоги другой площадки |
| POST /api/v1/batches | Атомарный импорт пакета |
| POST /api/v1/parse-html | HTML-разбор без записи |
| GET /api/v1/export?format=json | Страница последних предложений JSON |
| GET /api/v1/export?format=csv | Страница последних предложений CSV |

Тело POST /jobs: marketplace=wb/ozon, limit 1–100, pages 1–10, scrolls 0–10, delay 1–30, timeout 5–90. Неизвестные поля запрещены. Для URL площадка должна соответствовать домену.

Разбор учебного HTML через API:

```powershell
$htmlBody = @{
    marketplace = 'wb'
    url = 'https://www.wildberries.ru/catalog/456/detail.aspx'
    html = Get-Content tests/fixtures/wb_current.html -Raw -Encoding UTF8
} | ConvertTo-Json
Invoke-RestMethod "$api/api/v1/parse-html" -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($htmlBody))
```

Тело API ограничено 3 MB, поле HTML — 2 млн символов. JSON/CSV экспорт до 500 последних предложений за запрос, остальные через offset; это не полная копия истории.

## 9. Расширение

### 9.1. Отдельный Chromium

```powershell
Set-Location 'E:\Baumanka\parser\JS'
npm.cmd ci
# Если Chromium ещё нет:
npx.cmd playwright install chromium
npm.cmd start
```

Start собирает dist и открывает Chromium с расширением и профилем `JS/.browser-profile`. Терминал занят до закрытия браузера. Основной Chrome-профиль не используется.

По умолчанию клиент выбирает backend: сначала поднимите API либо после открытия переключитесь на локальный режим. Launcher ждёт успешного подключения до 45 секунд, тайм-аут не обязательно означает ошибку сборки.

Можно задать CHROMIUM_PATH к совместимому Chromium. Для обычного Google Chrome предпочтительна ручная установка расширения.

### 9.2. Ручная установка в Google Chrome

```powershell
npm.cmd run build
```

1. Открыть chrome://extensions и включить режим разработчика.
2. «Загрузить распакованное расширение» → **E:\Baumanka\parser\JS\dist**.
3. Нажать иконку расширения.

После изменений повторить build и обновить расширение на chrome://extensions. Удаление расширения для обычного обновления не требуется.

### 9.3. Использование

В Backend сохраните адрес и token, создайте задание. Клиент получает этапы polling-запросами примерно раз в две секунды; закрытие страницы не отменяет worker.

В локальном режиме сервер не нужен: Service Worker открывает рабочие вкладки, content script читает DOM, SQLite сохраняет результат. «Вкладка» открывает страницу для проверки; доступны пауза, продолжение, отмена.

Флажок учебных HTML относится только к backend, требует ALLOW_FIXTURE_JOBS=1. Ошибка 403 на создании fixture job может означать запрет учебного режима API, а не отказ Ozon/WB.

«Процесс и данные» и «Все сохранённые» — разные выборки. JSON-кнопка скачивает показанные данные. Полный локальный интерфейс с историей, графиками, наблюдением, SQL-отчётами и backup/restore доступен по ссылке **«Расширенный локальный интерфейс»**, advanced.html.

### 9.4. Внутренняя схема

```mermaid
flowchart LR
    UI[process.ts] --> BG[background.ts]
    BG -->|backend.request| HTTP[HTTP API]
    BG -->|локальный сбор| TAB[Рабочая вкладка]
    TAB --> CONTENT[content.ts / parser.ts]
    CONTENT -->|результат + token| BG
    BG --> OFF[offscreen.ts]
    OFF --> WORK[sqlite.worker.ts]
    WORK --> DB[(SQLite OPFS)]
```

Соединением SQLite владеет один Worker в скрытом Offscreen document. Service Worker может выгружаться: очередь и staging сохраняются на диск. При закрытом браузере сбор не работает. Chrome Alarms проверяет очередь, но не обеспечивает точное серверное расписание.

### 9.5. Команды из папки JS

| Команда | Назначение |
|---|---|
| npm.cmd ci | Установка по lock-файлу |
| npm.cmd run build | Сборка TypeScript и dist |
| npm.cmd start | Сборка и видимый отдельный Chromium |
| npm.cmd run typecheck | Проверка типов |
| npm.cmd test | Нормализация и признаки |
| npm.cmd run test:browser | Автономный режим, OPFS, очередь, backup; ответы сайтов подменяются |
| npm.cmd run test:client | Простой клиент: HTTP test-api и локальный JS |
| npm.cmd run check:live | Живые сайты, отдельный профиль и отчёт |
| run.cmd | Обёртка npm start |
| test.cmd | typecheck, test, test:browser; без test:client |

Check:live использует `.live-profile`, закрывает браузер и приостанавливает незавершённые задания. Running в отчёте на момент окончания интервала не означает успех.

## 10. Backend без Docker

Нужна доступная PostgreSQL. Создайте пустую БД parser_api_local через createdb/pgAdmin. **db/schema.sql сюда не запускайте**: новую схему parser_api создаёт Store.initialize.

Терминал API:

```powershell
Set-Location 'E:\Baumanka\parser'
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:DATABASE_URL = 'postgresql://postgres:YOUR_PASSWORD@127.0.0.1:5432/parser_api_local'
$env:API_TOKEN = 'local-development-token'
$env:API_HOST = '127.0.0.1'
$env:API_PORT = '8000'
.\.venv\Scripts\python.exe -m backend.api
```

Во втором терминале:

```powershell
Set-Location 'E:\Baumanka\parser'
$env:DATABASE_URL = 'postgresql://postgres:YOUR_PASSWORD@127.0.0.1:5432/parser_api_local'
.\.venv\Scripts\python.exe -m backend.worker
```

Chrome нужен worker, не API. При необходимости задайте CHROME_BINARY и CHROMEDRIVER_PATH. `python -m backend.worker --once` обрабатывает доступную очередь до первого отсутствия заданий — это не обязательно одно задание.

Не используйте `uvicorn backend.api:app`: глобального app нет, приложение создаёт create_app. Поддерживаемый запуск — python -m backend.api. Не занимайте один порт одновременно Docker/API и локальным API.

Native-worker тоже использует Selenium ParserOzon; он не включает CDP автоматически. Рабочий отдельный CDP-сценарий описан в разделе 5.

## 11. Старый сервер и прежняя БД

### 11.1. Установка в новую пустую БД

Пример для PostgreSQL 16:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\createdb.exe' -U postgres marketplace_db
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -d marketplace_db -v ON_ERROR_STOP=1 -f db/schema.sql
```

Если таблицы уже существуют, повторно схему не создавайте. Дамп db/marketplace_db_dump.sql содержит данные и создан PostgreSQL 18.6: это не чистая схема, нужны совместимые инструменты. docs/schema.sql и docs/schema_simple.sql — исторические проекты.

### 11.2. HTTP-приёмник на 8002

Порт 8002 не конфликтует с новым API 8000 и test-api 8001:

```powershell
$env:DATABASE_URL = 'postgresql://postgres:YOUR_PASSWORD@127.0.0.1:5432/marketplace_db'
$env:INGEST_API_TOKEN = 'YOUR_LOCAL_INGEST_TOKEN'
.\.venv\Scripts\python.exe server.py --port 8002
```

В другом терминале:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8002/health'
$env:INGEST_API_TOKEN = 'YOUR_LOCAL_INGEST_TOKEN'
.\.venv\Scripts\python.exe main.py collect wb "наушники" --limit 1 --server http://127.0.0.1:8002
```

У него только GET /health и POST /api/v1/batches, нет Swagger, очереди и чтения товаров. Health проверяет HTTP, не БД. Пакет ограничен 2 MB. Server.py сам .env сейчас не загружает: используйте env-переменные.

### 11.3. Прямой импорт и дозаполнение

С DATABASE_URL прежней БД:

```powershell
.\.venv\Scripts\python.exe import_ozon.py backend/test-results/ozon-session-products.json
.\.venv\Scripts\python.exe backfill_features.py
```

Import_ozon сохраняет построчно и пропускает ошибочные записи — частичный импорт возможен, в отличие от атомарного POST /batches. Backfill заполняет только неизвестные признаки через COALESCE, не ходит на сайт и не работает с parser_api.products.

### 11.4. CLI-алиасы

Необязательная установка в своё окружение:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\marketplace-parser.exe --help
.\.venv\Scripts\ozon-parser.exe --help
.\.venv\Scripts\marketplace-server.exe --help
```

Это алиасы main.py, ozon_parser.py, server.py. Для нового backend installed entry point в pyproject нет; запускайте его модули из checkout.

## 12. Другие программы и диагностика

| Программа | Команда | Назначение |
|---|---|---|
| check_browser.py | `.\.venv\Scripts\python.exe check_browser.py` | Headless Playwright: example.com, Wikipedia, Ozon/WB, обычный/direct режим. Не собирает товары, может занять несколько минут |
| check_habr_browser.py | `.\.venv\Scripts\python.exe check_habr_browser.py --mode installed_chrome --headed` | Сравнивает guide/current_chromium/installed_chrome; не гарантия обхода 403 |
| backend.check_live | `.\.venv\Scripts\python.exe -m backend.check_live --marketplace wb --wait 180` | Настоящие задания через API; нужен backend и httpx |
| backend.ozon_access | `.\.venv\Scripts\python.exe -m backend.ozon_access --engine tls --warmup` | Проба HTTP/TLS; дополнительно нужен curl_cffi |
| backend.ozon_access browser | `.\.venv\Scripts\python.exe -m backend.ozon_access --engine browser --warmup` | Диагностический UC/Chrome без selenium-stealth, не OzonSession/CDP |
| wb_ozon.py | Не часть обычного запуска | Старый прототип отзывов, адреса в коде, вывод CSV |

Для optional TLS-пробы:

```powershell
.\.venv\Scripts\python.exe -m pip install curl_cffi
.\.venv\Scripts\python.exe -m backend.ozon_access --engine tls --direct
```

Direct отключает proxy-переменные TLS-клиента, не VPN Windows. OZON_PROXY относится только к TLS-пробе, не к OzonSession.

Check_live принимает --base, --source, --marketplace, --wait, читает API_TOKEN и сохраняет backend/test-results/live-backend*.json. Незавершённые задания после интервала отменяются. Можно передать настоящий URL карточки с соответствующей marketplace.

Не импортируйте wb_ozon.py ради проверки зависимостей: в теле класса сразу создаётся Chrome. Это прототип отзывов, а не текущих товаров; в нём есть проблемы, включая зависимость от глобальной a. Его работа не подтверждается тестами API и он не включён в smoke-test.

## 13. Тесты

### 13.1. Python без живых сайтов

```powershell
Set-Location 'E:\Baumanka\parser'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\.venv\Scripts\python.exe -m unittest test_features
.\.venv\Scripts\python.exe -m unittest backend.tests.test_ozon_access
```

Проверяют контракты, признаки, прежний HTTP-сервер с подменённой БД и распознавание CAPTCHA. Последняя зафиксированная проверка: 24 + 26 + 4 теста. Это история проверки, не гарантия результатов после изменений.

### 13.2. Настоящая PostgreSQL и браузер Docker

```powershell
docker compose -f backend/compose.yaml exec -T api python -m backend.tests.integration
docker compose -f backend/compose.yaml exec -T worker xvfb-run -a python -m backend.tests.browser_smoke
```

Первый тест создаёт отдельную временную БД и удаляет только её. Проверяет auth, ручки, оба парсера в процессах, настоящий SQL rollback, историю, cancel/retry. Нужны права создавать тестовую БД; пользователь Compose ими обладает. Второй запускает Chromium на контрольных HTML и проверяет восстановление профиля. Live-доступ ими не подтверждается.

### 13.3. Расширение / SQLite

```powershell
Set-Location 'E:\Baumanka\parser\JS'
npm.cmd run typecheck
npm.cmd test
npm.cmd run test:browser
```

Ответы сайтов подменяются HTML. Проверяется настоящее расширение с OPFS, staging, паузой, перезапуском и backup/restore. Используются отдельные .test-profile-*.

### 13.4. Упрощённый клиент в двух режимах

```powershell
Set-Location 'E:\Baumanka\parser'
docker compose -f backend/compose.yaml --profile test up -d test-api
Set-Location 'E:\Baumanka\parser\JS'
npm.cmd run test:client
Set-Location 'E:\Baumanka\parser'
docker compose -f backend/compose.yaml stop test-api
```

Test-api на 8001 использует временную БД, fixture worker и test-token. Штатная остановка удаляет тестовую БД. Рабочая БД 8000 не заполняется тестовыми товарами. Артефакты: JS/test-results/client-*.

Если тестовых модулей нет в ранее собранном образе, пересоберите его. Новый файл на Windows сам по себе не появляется в контейнере.

### 13.5. Другие тестовые файлы

`tests/run_postgres_integration.py` проверяет старый сервер в отдельном временном локальном PostgreSQL-кластере. Нужны PostgreSQL binaries, по умолчанию C:/Program Files/PostgreSQL/16/bin; переопределение — PG_BIN:

```powershell
.\.venv\Scripts\python.exe tests/run_postgres_integration.py
```

Артефакты — tmp/db-tests, существующая пользовательская БД не используется.

`tests/verify_listing_dom.py` устарел: передаёт Playwright Page в _parse_card, который теперь ожидает Selenium WebDriver. Не включайте его в текущую проверку. Аналоги: backend.tests.browser_smoke и JS test:browser.

## 14. Файлы и резервные копии

### Карта исходников

```text
parser/
├── main.py / check_parsers.py       CLI и быстрые проверки
├── parsers/                        Получение страниц и разбор товаров
├── contracts.py / features.py       Формат и признаки
├── server.py / db.py                Прежний HTTP-приёмник и транзакции
├── models_simple.py / db/           Прежний SQL и схема
├── backend/
│   ├── api.py / store.py            FastAPI и PostgreSQL parser_api
│   ├── worker.py / collect.py       Очередь и процесс парсера
│   ├── profiles.py                 Владение профилями
│   ├── ozon_session.py             Обычный Chrome/CDP
│   ├── ozon_access.py              Диагностика доступа
│   ├── compose.yaml / Dockerfile   Контейнеры
│   └── data/ / test-results/        Локальные профили и результаты
├── JS/
│   ├── process.html / src/process.ts  Текущий простой клиент
│   ├── advanced.html / src/ui.ts      Расширенный локальный клиент
│   ├── src/background.ts              Координатор
│   ├── src/content.ts / parser.ts     Чтение страниц
│   ├── src/database.ts                SQLite-операции
│   ├── src/offscreen.ts / sqlite.worker.ts  Жизненный цикл БД
│   ├── scripts/                       Сборка и проверки
│   └── dist/                          Собранный пакет
└── tests/fixtures/                  Учебные HTML
```

Текущий главный экран собирается из **JS/process.html** в JS/dist/index.html. Корневой JS/index.html остался от прежнего интерфейса. Изменения в dist следующая сборка перезапишет.

### Где данные

| Данные | Место |
|---|---|
| Ozon/CDP товары и события | backend/test-results/ozon-session-products.json, ozon-session-report.json |
| Ozon/CDP профиль | backend/data/ozon-chrome-session |
| CLI JSON | --output |
| Проверочные Python-профили | .ozon-profile, .wb-profile |
| Docker PostgreSQL | marketplace-parser_postgres-data volume |
| Docker профили / логи | marketplace-parser_parser-data volume, /data/profiles и /data/logs |
| Лог попытки в worker | /data/logs/JOB_ID-ATTEMPT.log |
| Native backend | backend/data/profiles и backend/data/logs, если env не изменены |
| SQLite при npm start | OPFS внутри JS/.browser-profile |
| SQLite ручной установки | OPFS выбранного Chrome-профиля для origin расширения |
| Настройки расширения | chrome.storage.local |
| Временный ID browser-сессии | chrome.storage.session |
| Браузерные отчёты | JS/test-results |

OPFS — локальное хранилище на диске, не облако и не папка исходников. Логическое имя SQLite /marketplace.sqlite3, версия схемы сейчас 2. UnlimitedStorage снимает обычные квоты, но не ограничение свободного диска.

Разные профили/установки расширения имеют разные базы. Перезапуск сохраняет данные, удаление профиля/расширения может их удалить. Chrome Sync SQLite не переносит.

### Резервные копии

PostgreSQL Docker:

```powershell
docker compose -f backend/compose.yaml exec -T db pg_dump -U parser -d marketplace -Fc -f /tmp/marketplace.dump
docker compose -f backend/compose.yaml cp db:/tmp/marketplace.dump ./marketplace.dump
```

Копирование файла не повреждает бинарный dump перекодировкой PowerShell. Восстанавливайте pg_restore в отдельную новую БД и проверяйте до переключения API. Замена рабочей БД требует отдельного решения.

SQLite: advanced.html → Хранилище → Скачать SQLite. JSON/CSV там содержат последние предложения, полная история — в SQLite backup. Восстановление принимает копию этого расширения, проверяет отдельно и заменяет данные: сначала отмените незавершённые задания. JSON-импорт ограничен 20 MB, SQLite-восстановление — 200 MB, для снимка нужна дополнительная память.

## 15. Ошибки и ограничения

| Симптом | Проверка / действие |
|---|---|
| Перед командой >>> | Выйдите exit() из Python Console в PowerShell |
| ModuleNotFoundError | Используйте правильный .venv/python.exe и requirements |
| npm не нашёл package.json | Перейдите в папку JS |
| Playwright не нашёл Chromium | Установите browser командой Python или npx из соответствующего раздела |
| Docker daemon / named pipe недоступен | Запустите Desktop, проверьте docker info |
| Порт 8000 занят | Не запускайте два API; прежний server.py используйте на 8002 |
| HTTP 401 | Сверьте API_TOKEN сервера и Bearer; Python send_batch читает INGEST_API_TOKEN |
| Fixture job даёт 403 | Проверьте ALLOW_FIXTURE_JOBS; это может быть запрет режима самим API |
| Queued и workers_online=0 | Worker не работает, смотрите его logs |
| Ozon 403/CAPTCHA | Отказ до разбора; для проверенного Windows-пути используйте ozon_session |
| Профиль Chrome занят | Закройте отдельное окно либо используйте его --cdp-url |
| После ошибки остался JSON | Возможно, предыдущий результат; сверяйте exit code и дату |
| --channel msedge не изменяет Selenium | Аргумент пока не подключён к фабрике |
| Товар пропал при смене режима | PostgreSQL parser_api, прежняя public и OPFS независимы |
| Нет частичных данных пакета API | Ожидаемая атомарность; изучите ошибку задания |
| Нет уведомления о снижении | Нужны подтверждённые сопоставимые регион, валюта, тип цены и наличие |

Конфигурация рассчитана на один browser worker с постоянными профилями. Для нескольких исполнителей нужно разделять профили, а не только защищать очередь. Не снимайте блокировки активного Chrome вручную.

Один token даёт доступ ко всем данным экземпляра; отдельных аккаунтов нет. Compose публикует localhost. Для удалённого сервера нужны собственные credentials, HTTPS и управление доступом.

WB берёт вторую и третью из первых трёх сумм ₽ для поддерживаемой разметки. Это правило исходного кода, не гарантия любой будущей страницы; для другой разметки есть структурированный fallback. Null означает «неизвестно», не «нет».

Документы docs содержат также прошлые варианты и требования. Команд find/query/export в текущем main.py нет, даже если они есть в ТЗ. Новый API и расширение реализуют экспорт/запросы в своих компонентах.

## 16. Важные функции

Не каждый .py-файл — отдельная программа. Например, contracts.py, features.py, db.py и backend/store.py в основном предоставляют функции, которые импортируют точки входа. Запуск `python contracts.py` не начинает парсинг.

| Файл / функция | Назначение |
|---|---|
| contracts.py: product_url | Домен, HTTPS, артикул, канонический URL |
| contracts.py: normalize_item | Единый товар, типы, диапазоны, unknown/null |
| contracts.py: dumps / loads | Decimal без потери точности |
| contracts.py: validate_batch | Проверка пакета и повторов контекста |
| features.py: extract_features / extract_all | Признаки; характеристики продавца сильнее названия |
| parsers/base.py: get_data | Выдача → ссылки → карточки → полный результат |
| parsers/base.py: _create_browser / _load / _check_access | Браузер, навигация, распознавание отказа |
| parsers/html.py: parse_product | Ozon и HTML/JSON-LD fallback |
| parsers/wildberries.py: _parse_data / read_specs | WB-разбор и окно характеристик |
| backend/ozon_session.py: __enter__ / navigate / collect | Обычный Chrome, CDP, ожидание данных |
| backend/api.py: create_app / JobRequest | HTTP-приложение, auth, валидация |
| backend/store.py: claim / heartbeat / owns | Очередь, lease, владение попыткой |
| backend/worker.py: execute / terminate | Процесс, события, отмена, общий timeout |
| backend/collect.py: run | Исходный парсер и NDJSON протокол |
| backend/store.py: publish | Атомарная публикация |
| db.py: save_batch | Атомарный пакет прежней схемы |
| JS/src/process.ts: http / refresh / refreshSelected | Клиент, polling, этапы |
| JS/src/background.ts: pump / dispatch / db | Вкладки и сообщения |
| JS/src/parser.ts: collectPage / parseDocument | JS-порт разбора |
| JS/src/database.ts: claim / result / publish | Локальная очередь и staging |
| JS/src/sqlite.worker.ts | Единственное соединение, backup/restore |

Порядок чтения: **контракт → чистый HTML-разбор → браузер → API → worker → транзакции → клиент**. Так видно, какой этап действительно успешен, а какой ещё не выполнен.

### Переменные окружения

Одна и та же переменная в разных терминалах не передаётся автоматически. `.env` — не глобальная настройка Windows: Compose получает его при явном --env-file, Python в этом проекте обычно читает os.environ.

| Переменная | Кто читает | Назначение |
|---|---|---|
| DATABASE_URL | backend Store, прежний db.py | Строка подключения к нужной БД |
| API_TOKEN | Новый API, backend.check_live | Bearer token нового сервера / его диагностики |
| INGEST_API_TOKEN | Прежний server.py, ingest_client.py | Token старого приёмника или значение для отправки main.py в новый API |
| API_HOST / API_PORT | Native backend.api | Адрес и порт Python HTTP-сервера |
| API_PORT | Compose | Публикуемый порт Docker API на Windows |
| POSTGRES_PASSWORD | Compose | Пароль создаваемой контейнерной БД |
| ALLOW_FIXTURE_JOBS | Новый API | 1 разрешает учебные задания, default 0 |
| CORS_ORIGINS | Новый API | Список разрешённых web-origins через запятую |
| CHROME_BINARY | Selenium и OzonSession | Путь к браузеру |
| CHROMEDRIVER_PATH | Selenium | Совместимый системный драйвер; копируется перед патчем UC |
| CHROME_VERSION_MAIN | Selenium | Основная версия Chrome; Docker entrypoint определяет её сам |
| CHROME_NO_SANDBOX | Docker-браузер | 1 добавляет соответствующий параметр Chrome |
| PROFILE_ROOT / LOG_ROOT | backend | Папки профилей и журналов |
| MAX_JOB_SECONDS | worker | Общий предел задания, default 900 секунд |
| OZON_CHROME_BINARY | OzonSession | Специальный путь к обычному Chrome |
| OZON_PROXY | TLS-диагностика ozon_access | Не настраивает OzonSession или VPN |
| CHROMIUM_PATH | JS/scripts/browser.mjs | Совместимый Chromium для расширения |
| PG_BIN | Прежний PostgreSQL integration test | Каталог PostgreSQL binaries |

## 17. Повседневный сценарий

1. Поднять Docker/backend, проверить health/ready и worker.
2. Открыть расширение, Backend, проверить token.
3. Создать небольшой WB-сбор, посмотреть этапы и результаты.
4. Для Ozon на Windows использовать отдельный CDP; при необходимости явно импортировать JSON в API.
5. Для сравнения JS выбрать локальный режим и помнить о другой БД и другом способе доступа к сайту.

Штатная остановка:

```powershell
Set-Location 'E:\Baumanka\parser'
docker compose -f backend/compose.yaml stop
```

Volumes сохраняются. Закрытие отдельного Chromium завершает npm start. Native Python API/worker/server.py останавливаются Ctrl+C в своих терминалах. CDP Chrome закрывается сам, если не задан keep-open.

Для обычного обновления не удаляйте volumes, профили и установленное расширение: там находятся данные и сессии.

Предыдущий большой README сохранён в [docs/README_legacy.md](docs/README_legacy.md) как история. Его устаревшие указания не заменяют команды текущего руководства.
