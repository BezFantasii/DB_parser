# Альтернативный режим расширения: Backend

Версия расширения 0.3.0 добавляет выбор источника данных в popup. Браузерный способ сохранён и остаётся выбранным по умолчанию. В режиме Backend расширение передаёт тот же запрос на сервер, а сервер получает товары и сохраняет их в PostgreSQL. Вкладка Ozon в пользовательском Chrome для этого режима не нужна.

## Быстрое подключение

1. Соберите расширение: `npm.cmd --prefix JS run build` из корня проекта.
2. На `chrome://extensions` обновите распакованное расширение из `E:\Baumanka\parser\JS\dist` и перезагрузите страницы площадок.
3. Откройте значок расширения → «Источник данных» → «Через backend».
4. Укажите `http://127.0.0.1:8000` и API token. Пустое поле означает локальное значение `local-development-token`; при другом `API_TOKEN` сервера вставьте его явно.
5. Нажмите «Проверить сервер». Проверяются авторизация, PostgreSQL и число активных worker.
6. Нажмите «Сохранить» и выполните поиск на WB или Ozon. Этапы очереди и результата отображаются в том же виджете справа сверху.

Пользовательские вкладки не создаются и не перенаправляются. Backend работает отдельным процессом и использует собственный браузерный профиль, а не cookies расширения.

## Нативный backend на Windows: обычный Chrome + PostgreSQL в Docker

Этот вариант подходит для Ozon: Chrome работает на компьютере сервера с сохранённой отдельной сессией. Нужны Docker Desktop, установленный Google Chrome и Python-окружение проекта с `backend/requirements.txt`.

Из корня проекта один раз поднимите БД:

```powershell
Set-Location 'E:\Baumanka\parser'
docker compose -f backend/compose.yaml -f backend/compose.windows.yaml up -d db
```

БД доступна только через `127.0.0.1:5433`, её существующий Docker volume сохраняется. Если раньше запускали Docker API и worker, остановите их перед нативным запуском, чтобы освободить порт 8000 и не смешивать исполнителей:

```powershell
docker compose -f backend/compose.yaml stop api worker
```

Первый терминал — API:

```powershell
Set-Location 'E:\Baumanka\parser'
$env:DATABASE_URL = 'postgresql://parser:parser-local-development@127.0.0.1:5433/marketplace'
$env:API_TOKEN = 'local-development-token'
$env:API_PORT = '8000'
.\.venv\Scripts\python.exe -m backend.api
```

Второй терминал — worker:

```powershell
Set-Location 'E:\Baumanka\parser'
$env:DATABASE_URL = 'postgresql://parser:parser-local-development@127.0.0.1:5433/marketplace'
.\.venv\Scripts\python.exe -m backend.worker
```

Пароль в примере соответствует локальному compose по умолчанию. Если ваша БД уже создавалась с другим паролем, используйте его: изменение переменной не меняет пароль существующего volume. При отсутствии Python-зависимостей установите их: `.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`.

Оба терминала должны работать. Остановить процесс — `Ctrl+C`. Проверка: `http://127.0.0.1:8000/health/ready`, документация API — `http://127.0.0.1:8000/docs`.

При сборе Ozon сервер запускает отдельный обычный Chrome. Его окно может быть видно на компьютере сервера. Основной пользовательский профиль не используется. Профиль по умолчанию — `backend/data/ozon-chrome-session`. Если задан `PROFILE_ROOT`, используется его подпапка `ozon-session`. Доступ к профилю сериализуется межпроцессной блокировкой.

## Весь backend в Docker

```powershell
docker compose -f backend/compose.yaml up --build -d
```

API публикуется на `127.0.0.1:8000`, PostgreSQL и профили сохраняются в volumes. В контейнере используется Chromium под Xvfb. Его сессия независима от нативного Chrome, поэтому доступность Ozon в Docker может отличаться. 403/CAPTCHA передаются клиенту как серверная ошибка, учебные данные не подставляются вместо живых.

Для перехода обратно с нативной БД на Docker-клиенты уберите привязку host-порта, пересоздав только db с базовым compose; volume удалять не нужно. Не запускайте одновременно нативный API и контейнер API на одном порту.

## Как проходит запрос

```mermaid
sequenceDiagram
    participant W as Виджет в расширении
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Worker as Backend worker
    participant Shop as Ozon / WB
    W->>API: POST /api/v1/jobs (тот же запрос, другая площадка)
    API->>DB: сохранить queued job
    API-->>W: 202 + job id
    Worker->>DB: claim + lease
    Worker->>Shop: отдельная серверная сессия браузера
    loop ожидание результата
        W->>API: GET /api/v1/jobs/{id}
        API-->>W: queued / running / succeeded / blocked / failed
    end
    Worker->>DB: атомарно сохранить товары и наблюдения цен
    W->>API: GET /api/v1/jobs/{id}/results
    API-->>W: сохранённые товары
    W->>W: показать до 5 цен и ссылок
```

Расширение использует существующий API, отдельная синхронная ручка для виджета не требуется. Для Ozon отправляется `engine: "chrome-session"`, для WB — `engine: "selenium"`. У прежних клиентов параметр `engine` необязателен; его значение по умолчанию остаётся `selenium`.

Режим Ozon `chrome-session` получает JSON Composer API через браузер, разбирает `tileGridDesktop` / `textDS`, выбирает текущую цену вместо `ORIGINAL_PRICE` и нормализует товары в общий контракт БД. Он не требует обхода каждой карточки ради цены из выдачи. Для прямого URL карточки сохраняется прежний CDP-сбор карточки.

Во время ожидания показаны очередь и выполнение. На backend-запрос отведено 180 секунд. При смене запроса, закрытии исходной вкладки или смене режима клиент прерывает polling и отправляет `POST /api/v1/jobs/{id}/cancel`; worker завершает принадлежащий заданию процесс браузера. Отмена при потере связи выполняется по возможности. Записи заданий и результатов остаются в PostgreSQL; при аварийном закрытии браузера серверное задание может завершиться независимо.

Результаты принимаются только от нужного job id и площадки с `mode=live`. Учебные задания `fixture`, неверные ссылки и цены не показываются как живые результаты.

## Настройки и удалённый сервер

Адрес, token и выбранный режим хранятся в `chrome.storage.local` под ключом `comparisonBackend`. Доступ к ним разрешён только доверенным контекстам расширения; content script получает результаты, а не token. Авторизация передаётся заголовком `Authorization: Bearer ...`, не в URL.

Локальный HTTP разрешён для localhost/127.0.0.1. Для удалённого сервера нужен HTTPS; popup запрашивает разрешение Chrome на соответствующий адрес при сохранении. Укажите origin сервера без `/api/v1` в конце. API должен быть доступен по корневым маршрутам `/health/*` и `/api/v1/*`.

## Проверки

```powershell
npm.cmd --prefix JS run typecheck
npm.cmd --prefix JS test
npm.cmd --prefix JS run test:widget
.\.venv\Scripts\python.exe -m unittest backend.tests.test_ozon_search backend.tests.test_ozon_access
```

`test:widget` проверяет настройки, авторизацию, polling, отображение наблюдений, серверную блокировку, отклонение fixture-данных и отмену задания на контролируемом тестовом API. Он не выдаёт тестовые ответы за живую выдачу.

Для настоящего API, worker и PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m backend.tests.live_search
npm.cmd --prefix JS run check:backend:live
```

Первая команда создаёт одно живое задание Ozon и сохраняет отчёт в `backend/test-results/backend-search-live.json`. Вторая использует тестовую исходную страницу WB, но **настоящий API, настоящий worker, живой Ozon и PostgreSQL**: отчёт и снимок виджета — `JS/test-results/backend-live-widget.*`. Такие проверки создают реальные записи в БД. Для другого API можно задать `API_URL` и `API_TOKEN` для JS-проверки.
