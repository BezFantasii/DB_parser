# Хранение результатов трёх маркетплейсов

Это проект модели, а не реализованное подключение. `schema.sql` не применялся к PostgreSQL. Текущий парсер пишет только JSON.

## Поток данных

Парсер площадки → единая запись наблюдения → валидация → транзакция PostgreSQL → запросы фильтрации.

У каждой площадки свои URL, селекторы, извлечение ID и правила цены. Сохранение в БД общее. Не нужно создавать отдельные таблицы ozon_products, wb_products и products третьей площадки: площадку определяет marketplace_id.

Для Python можно использовать SQLAlchemy и Alembic либо psycopg с SQL. Для начала достаточно синхронного доступа: Playwright в проекте уже синхронный. Эти зависимости пока не установлены и не добавлены.

## Модели

| Модель | Одна запись означает | Основные поля |
|---|---|---|
| Marketplace | Площадка | id, code, name, base_url |
| Brand | Нормализованный бренд | id, name |
| Category | Узел общей классификации | id, parent_id, name |
| Product | Точный вариант товара, общий для площадок | id, name, brand_id, category_id, gtin, manufacturer_sku, attributes |
| Listing | Карточка на конкретной площадке | id, marketplace_id, external_id, product_id, title, url, brand_id, category_id, attributes, first_seen_at, last_seen_at |
| ScrapeRun | Запуск одного парсера | id, marketplace_id, source_url, parser_version, started_at, finished_at, status, error_message |
| Observation | Наблюдение цены и состояния карточки | id, listing_id, run_id, marketplace_id, observed_at, region_key, price_kind, condition_key, currency, price, price_text, availability, rating, reviews_count, raw_data |

Связи: Marketplace 1→N Listing; Product 1→N Listing; Listing 1→N Observation; ScrapeRun 1→N Observation. Product необязателен: пока соответствие не доказано, listing.product_id = NULL.

Цена карточки не обязательно относится к одному известному продавцу. Поэтому эта схема не выдумывает seller_id. Если начнёте собирать продавцов и отдельные предложения, добавьте Seller и Offer, а наблюдения связывайте с Offer. Варианты размера/цвета и комплекты нельзя автоматически объединять только по похожему названию.

## Типы и ограничения

- Денежная сумма: NUMERIC(14,2), в Python — Decimal. Существующий parse_price возвращает int/float: для БД следует сделать отдельную нормализацию с Decimal из исходного текста, не через float.
- Время: TIMESTAMPTZ; записывать момент фактического извлечения с часовым поясом. Часовой пояс отображения выбирает приложение.
- Внешний ID: TEXT, поскольку разные площадки могут использовать разные форматы. Уникальность — (marketplace_id, external_id).
- region_key: стабильный код региона, а не произвольный текст. unknown означает, что регион не установлен; такие цены нельзя автоматически считать сопоставимыми с известным регионом.
- price_kind: regular/card/subscription/unknown. condition_key уточняет условие, например ozon_card; неизвестный тип не считать обычной ценой.
- Неизвестная цена — NULL, неизвестное наличие — unknown. Отсутствие карточки в ограниченной выдаче не означает out_of_stock.
- Разнообразные характеристики — JSONB с едиными ключами, типами и единицами. Часто фильтруемые диапазоны лучше вынести в типизированные колонки либо создать индекс по конкретному выражению после проверки запросов.
- Бренд и категория карточки доступны даже до сопоставления с Product. Исходные значения площадки можно сохранять в raw_data; общие категории назначать через явное сопоставление.
- Составные внешние ключи не позволяют записать наблюдение Ozon с запуском другой площадки.

Справочные материалы: [типы PostgreSQL](https://www.postgresql.org/docs/current/datatype.html), [JSONB и индексы](https://www.postgresql.org/docs/current/datatype-json.html), [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html).

## Запись в БД

1. Создать ScrapeRun со статусом running и зафиксировать транзакцию.
2. Получить и проверить данные вне транзакции БД; не держать её открытой во время загрузки браузера.
3. Пакетом выполнить INSERT INTO listing ... ON CONFLICT (marketplace_id, external_id) DO UPDATE ... RETURNING id. last_seen_at обновлять по фактическому наблюдению; при конкурентных запусках не заменять более новые данные старыми.
4. Вставить Observation. При повторной доставке одной и той же записи использовать тот же run_id и уникальный ключ наблюдения; новый самостоятельный запуск получает новый run_id.
5. Сохранить пакет и завершить запуск со статусом succeeded. При ошибке — failed и error_message; отметить, что ранее сохранённые пакеты могут быть частичными.

Для небольшого запуска можно сохранить все результаты одной короткой транзакцией после сбора. При больших запусках сохранять пакетами. Успешные наблюдения из частично завершившегося запуска можно использовать, но полноту выдачи нельзя считать подтверждённой. Для атомарной публикации всего запуска добавьте промежуточное хранение либо выбирайте latest только из succeeded запусков.

Строку подключения читать из переменной окружения DATABASE_URL. SQL-значения передавать параметрами. Поля сортировки выбирать из фиксированного списка, а не вставлять произвольный пользовательский SQL.

## Фильтрация

Пример: свежие обычные цены на доступные наушники в заданном регионе, на выбранных площадках. Параметры вида :region для SQLAlchemy, не готовый синтаксис psql.

```sql
SELECT m.code, l.external_id, l.title, o.price, o.currency,
       o.rating, o.observed_at, l.url
FROM listing AS l
JOIN marketplace AS m ON m.id = l.marketplace_id
JOIN latest_observation AS o ON o.listing_id = l.id
WHERE m.code IN (:marketplace_1, :marketplace_2, :marketplace_3)
  AND l.title ILIKE :title_pattern
  AND o.region_key = :region
  AND o.price_kind = 'regular'
  AND o.condition_key = 'regular'
  AND o.currency = 'RUB'
  AND o.price BETWEEN :min_price AND :max_price
  AND o.availability = 'in_stock'
  AND o.observed_at >= :freshness_cutoff
ORDER BY o.price, l.id
LIMIT :limit;
```

Текущий парсер не определяет наличие и тип цены достоверно: его импортированные строки получат unknown и не попадут в этот строгий запрос. Это ожидаемо. Нужные поля должны собирать новые адаптеры площадок.

Другие фильтры: l.brand_id = :brand; l.category_id = :category; o.rating >= :rating; o.reviews_count >= :reviews; l.attributes @> '{"wireless":true}'::jsonb. Для категории вместе с подкатегориями нужен рекурсивный CTE по category.parent_id. CHECK запрещает только прямую ссылку категории на себя; длинные циклы и дубли в дереве нужно исключать при записи.

История одного товара:

```sql
SELECT observed_at, price, availability
FROM observation
WHERE listing_id = :listing_id AND region_key = :region
  AND price_kind = :price_kind AND condition_key = :condition
  AND currency = 'RUB'
ORDER BY observed_at, id;
```

Сначала выбрать последнее наблюдение, затем фильтровать цену. Если сперва отфильтровать историю по цене, можно показать старую дешёвую цену вместо текущей дорогой. Аналогично нельзя пропускать последнее наблюдение out_of_stock или NULL price и возвращать прежнее in_stock.

## Индексы и рост

Начальные индексы перечислены в schema.sql: уникальность карточки, бренд/категория, JSONB, связь с Product, история и запуск. Для ILIKE '%наушники%' предусмотрен опциональный pg_trgm. Обычный B-tree не является заменой этому индексу для поиска с ведущим %.

latest_observation — обычное представление, данные оно не кеширует. Если фильтры по текущим ценам станут медленными, заведите таблицу current_observation с тем же ключом контекста и индексами (region_key, price_kind, currency, price), обновляя её в одной транзакции с историей и только более новым наблюдением. Сначала измерять запросы через EXPLAIN (ANALYZE, BUFFERS), потом выбирать дополнительные индексы и секционирование истории по времени.

HTML при необходимости хранить файлами или в объектном хранилище, а в БД — ссылку, контрольную сумму, run_id и observed_at. Сохранённый HTML после JavaScript отличается от исходного HTTP HTML. Не переносить cookies и данные профиля в raw_data.

## Что изменить в текущем парсере для интеграции

- Возвращать external_id отдельно: сейчас normalize_card возвращает его только как внутренний ключ, а JSON его теряет.
- Добавить marketplace_code и observed_at; не выводить регион и условие цены из предположений.
- Расширить выходную модель полями region_key, price_kind, condition_key, availability и, если доступны, рейтингом/отзывами.
- Оставить site-specific извлечение в ozon/wb/third адаптерах; общий repository должен принимать одну нормализованную модель.
- Сохранить JSON-экспорт как отдельный вариант вывода. Блокировки браузера и ошибки селекторов слой БД не решает.
