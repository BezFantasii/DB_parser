# Построчный разбор текущего проекта parser

Номера относятся к версии файлов на момент подготовки этого документа. Исходные файлы не изменены. Здесь разобраны все строки пяти Python-файлов, pyproject.toml и requirements.txt, включая служебные и пустые строки.

## Структура

- ozon_parser.py — исполняемый парсер Ozon: CLI → браузер → DOM → нормализация → JSON.
- check_browser.py — проверка доступности разных сайтов через Chromium.
- check_habr_browser.py — отдельный эксперимент с настройками браузера из статьи; основной парсер его не импортирует.
- tests/test_ozon_parser.py — десять unittest-проверок Python-функций без сети.
- tests/verify_listing_dom.py — проверка JavaScript на локальных HTML-примерах в Chromium.
- requirements.txt и pyproject.toml — зависимости и установка пакета.
- README.md — инструкции; выполняемого кода нет.
- products.json — полученный массив товаров; выполняемого кода нет. Объекты содержат name, price, currency, price_text, url. Содержимое не копируется сюда.
- .gitignore — исключает окружение, кеши, сборку, выходной JSON и папку .ozon-profile из Git.
- .ozon-profile/ — данные отдельного Chrome, а не исходный код. Их содержимое не требуется для объяснения программы.
- docs/schema.sql и docs/database_design.md — предложенная модель PostgreSQL и объяснение; с парсером пока не соединены.

## Общий ход программы

При прямом запуске Python доходит до sys.exit(main()). main разбирает аргументы, вызывает scrape, получает список и пишет JSON. scrape управляет страницами и прокрутками. Код в строках LISTING_ROOTS_JS/EXTRACT_CARDS исполняется браузером как JavaScript, а не Python. normalize_card и parse_price работают уже над результатом, возвращённым в Python.

Объект browser — процесс браузера, context — отдельная сессия, page — вкладка. Persistent context сохраняет данные в profile; обычный context временный. Сейчас HTML не скачивается отдельным файлом: извлечение идёт из живого DOM после JavaScript.

## Ограничения, которые следует учитывать

1. Резервный main/#layoutPage может включать рекомендации; его корректность для реальной выдачи ещё нужно проверять.
2. Название из alt изображения может быть менее точным, чем название карточки.
3. Выбирается первая незачёркнутая цена, которая может требовать карту/подписку. Тип цены отдельно не определяется.
4. setdefault оставляет первую цену даже при последующем изменении. Для истории наблюдений в БД это нужно изменить.
5. Три неизменных набора не доказывают, что закончилась вся выдача: динамическая загрузка может быть медленнее.
6. Снимок JS хранит только карточки с распознанными названием и ценой. Это не полный каталог.
7. Тесты на локальной разметке не подтверждают актуальные селекторы Ozon и не проверяют обход 403.
8. Профиль не поддерживает одновременный запуск нескольких Chrome; общий output также не рассчитан на конкурентную запись.

## ozon_parser.py

**Строка 1.** Документация модуля: сбор видимых карточек Ozon; требуется Python 3.9+.

```python
"""Collect visible Ozon search/category cards. Python 3.9+."""
```

**Строка 2.** Импорт argparse для аргументов командной строки.

```python
import argparse
```

**Строка 3.** Импорт json для сериализации результатов и диагностики.

```python
import json
```

**Строка 4.** Импорт re для регулярных выражений: цены и ID.

```python
import re
```

**Строка 5.** Импорт sys: потоки вывода и код завершения.

```python
import sys
```

**Строка 6.** Decimal даёт точный десятичный разбор; InvalidOperation перехватывает ошибки преобразования.

```python
from decimal import Decimal, InvalidOperation
```

**Строка 7.** Path представляет пути к JSON и профилю браузера.

```python
from pathlib import Path
```

**Строка 8.** Функции разбора URL, его параметров и обратной сборки.

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
```

**Строка 9.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 10.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 11.** Комментарий: избегать генерируемых CSS-классов; часть селекторов всё же зависит от разметки.

```python
# Avoid generated CSS class names. These selectors may still need updating
```

**Строка 12.** Комментарий: код рассчитан на карточки выдачи, а не страницы отдельных товаров.

```python
# when Ozon changes its markup. Only listing cards are supported.
```

**Строка 13.** Начало raw-строки с JavaScript-функцией. raw сохраняет обратные слеши регулярных выражений.

```python
LISTING_ROOTS_JS = r"""() => {
```

**Строка 14.** querySelectorAll ищет DOM-узлы; Array.from превращает NodeList в массив.

```python
    const roots = Array.from(document.querySelectorAll(
```

**Строка 15.** Четыре известных селектора контейнера выдачи. Запятая в CSS означает альтернативы.

```python
        '[data-widget="searchResultsV2"], [data-widget="searchResults"], [data-widget="catalogResults"], [data-widget="tileGrid"]'));
```

**Строка 16.** Если известные контейнеры найдены, возвращает их.

```python
    if (roots.length) return roots;
```

**Строка 17.** Резервный поиск разрешён только на пути /search/ или /category/.

```python
    if (/^\/(search|category)\//.test(location.pathname)) {
```

**Строка 18.** Находит main или #layoutPage как резервный контейнер.

```python
        const main = document.querySelector('main, #layoutPage');
```

**Строка 19.** Возвращает найденный контейнер в массиве.

```python
        if (main) return [main];
```

**Строка 20.** Закрывает текущий блок JavaScript.

```python
    }
```

**Строка 21.** Возвращает пустой массив, если подходящий контейнер не найден.

```python
    return [];
```

**Строка 22.** Закрывает JavaScript-функцию и Python-строку.

```python
}"""
```

**Строка 23.** Собирает JS-предикат ожидания: хотя бы один контейнер должен содержать товарную ссылку.

```python
WAIT_FOR_CARDS = "() => (" + LISTING_ROOTS_JS + ")().some(root => root.querySelector('a[href*=\"/product/\"]'))"
```

**Строка 24.** Начало JS-функции извлечения, хранящейся в Python-строке.

```python
EXTRACT_CARDS = r"""() => {
```

**Строка 25.** Пустой массив результатов.

```python
    const result = [];
```

**Строка 26.** Место подстановки LISTING_ROOTS_JS; вызывается функция поиска контейнеров.

```python
    const roots = (__LISTING_ROOTS__)();
```

**Строка 27.** Перебирает контейнеры.

```python
    for (const root of roots) {
```

**Строка 28.** Перебирает ссылки, href которых содержит /product/.

```python
        for (const link of root.querySelectorAll('a[href*="/product/"]')) {
```

**Строка 29.** Ищет название внутри ссылки по data-widget либо классу span.tsBody500Medium.

```python
            const titleNode = link.querySelector('[data-widget="webProductHeading"], [data-widget="webProductTitle"], span.tsBody500Medium');
```

**Строка 30.** Название берёт из найденного узла, текста ссылки, aria-label либо alt изображения; ?. допускает отсутствие узла, || выбирает первое непустое значение.

```python
            const name = (titleNode?.innerText || link.innerText || link.getAttribute('aria-label') || link.querySelector('img')?.alt || '').trim();
```

**Строка 31.** Пропускает пустые названия и ссылки, текст которых содержит знак цены.

```python
            if (!name || /₽/.test(name)) continue;
```

**Строка 32.** Начинает поиск карточки с самой ссылки.

```python
            let card = link;
```

**Строка 33.** Пока блок цены не найден.

```python
            let priceBlock = null;
```

**Строка 34.** Комментарий: нужен ближайший предок с одним товаром и ценой.

```python
            // Stop at the smallest ancestor containing this product and a price.
```

**Строка 35.** Поднимается по родителям максимум семь раз, не заходя в корень выдачи.

```python
            for (let depth = 0; depth < 7 && card && card !== root; depth++, card = card.parentElement) {
```

**Строка 36.** Собирает множество идентификаторов товаров в текущем предке.

```python
                const ids = new Set(Array.from(card.querySelectorAll('a[href*="/product/"]'))
```

**Строка 37.** Извлекает числовой ID из конца пути; если формат неизвестен, использует путь.

```python
                    .map(a => a.pathname.match(/-(\d+)\/?$/)?.[1] || a.pathname));
```

**Строка 38.** Если предок содержит несколько товаров, останавливает поиск, чтобы не приписать чужую цену.

```python
                if (ids.size > 1) break;
```

**Строка 39.** Ищет предпочтительный блок webPrice.

```python
                priceBlock = card.querySelector('[data-widget="webPrice"]');
```

**Строка 40.** Если его нет, начинает резервный поиск.

```python
                if (!priceBlock) {
```

**Строка 41.** Ищет первый подходящий span в карточке.

```python
                    priceBlock = Array.from(card.querySelectorAll('span')).find(el => {
```

**Строка 42.** Получает вычисленные CSS-стили span.

```python
                        const style = getComputedStyle(el);
```

**Строка 43.** Проверяет, что текст целиком похож на число с пробелами, необязательной дробью и ₽.

```python
                        return /^\s*\d[\d\s\u00a0\u202f]*(?:[,.]\d{1,2})?\s*₽\s*$/.test(el.innerText)
```

**Строка 44.** Исключает элементы внутри del/s и цены с зачёркиванием через CSS.

```python
                            && !el.closest('del, s') && !style.textDecorationLine.includes('line-through');
```

**Строка 45.** Завершает функцию-предикат find.

```python
                    });
```

**Строка 46.** Закрывает текущий блок JavaScript.

```python
                }
```

**Строка 47.** Останавливает подъём по DOM после обнаружения блока цены.

```python
                if (priceBlock) break;
```

**Строка 48.** Закрывает текущий блок JavaScript.

```python
            }
```

**Строка 49.** Пропускает товар, если цена не найдена.

```python
            if (!priceBlock) continue;
```

**Строка 50.** Сохраняет полный видимый текст блока цены для контекста.

```python
            const priceText = priceBlock.innerText.trim();
```

**Строка 51.** Получает вложенные span — кандидаты на текущую цену.

```python
            const candidates = Array.from(priceBlock.querySelectorAll('span'));
```

**Строка 52.** Если сам priceBlock — span, добавляет его в начало кандидатов.

```python
            if (priceBlock.matches('span')) candidates.unshift(priceBlock);
```

**Строка 53.** Начинает выбор первого подходящего кандидата.

```python
            const current = candidates.find(el => {
```

**Строка 54.** Получает стили кандидата.

```python
                const style = getComputedStyle(el);
```

**Строка 55.** Проверяет формат цены кандидата.

```python
                return /^\s*\d[\d\s\u00a0\u202f]*(?:[,.]\d{1,2})?\s*₽\s*$/.test(el.innerText)
```

**Строка 56.** Отбрасывает зачёркнутую старую цену.

```python
                    && !el.closest('del, s') && !style.textDecorationLine.includes('line-through');
```

**Строка 57.** Заканчивает выбор кандидата.

```python
            });
```

**Строка 58.** Комментарий: не угадывать цену, если однозначный текущий элемент не найден.

```python
            // Do not guess if the price block has no identifiable current price.
```

**Строка 59.** Пропускает товар без подходящей цены.

```python
            if (!current) continue;
```

**Строка 60.** Добавляет объект с названием, сырым текстом цены, полным блоком цены и абсолютной ссылкой.

```python
            result.push({name, price_raw: current.innerText.trim(), price_text: priceText, url: link.href});
```

**Строка 61.** Закрывает текущий блок JavaScript.

```python
        }
```

**Строка 62.** Закрывает текущий блок JavaScript.

```python
    }
```

**Строка 63.** Возвращает массив карточек из браузера в Python.

```python
    return result;
```

**Строка 64.** Закрывает строку и вставляет JS поиска контейнеров вместо маркера.

```python
}""".replace("__LISTING_ROOTS__", LISTING_ROOTS_JS)
```

**Строка 65.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 66.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 67.** Определяет функцию диагностики текущей страницы.

```python
def listing_diagnostics(page):
```

**Строка 68.** Исполняет JS в браузере; возвращает объект.

```python
    return page.evaluate("""() => ({
```

**Строка 69.** Адрес без query-параметров и fragment: origin плюс pathname.

```python
        url: location.origin + location.pathname,
```

**Строка 70.** Заголовок страницы.

```python
        title: document.title,
```

**Строка 71.** Количество всех товарных ссылок; это ещё не количество распознанных карточек.

```python
        product_links: document.querySelectorAll('a[href*="/product/"]').length,
```

**Строка 72.** Начинает сбор уникальных значений data-widget через Set.

```python
        widgets: Array.from(new Set(Array.from(document.querySelectorAll('[data-widget]')),
```

**Строка 73.** Берёт значение data-widget у каждого найденного элемента.

```python
            el => el.getAttribute('data-widget')))
```

**Строка 74.** Заканчивает JS и возвращает диагностический словарь.

```python
    })""")
```

**Строка 75.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 76.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 77.** Определяет преобразование текста цены.

```python
def parse_price(raw):
```

**Строка 78.** Документация: неверную цену нельзя превращать в ноль.

```python
    """Return rubles as a JSON number; never turn an invalid price into zero."""
```

**Строка 79.** Удаляет обычные и неразрывные пробелы и завершающий знак ₽.

```python
    cleaned = re.sub(r"[\s\u00a0\u202f]", "", raw).removesuffix("₽")
```

**Строка 80.** Проверяет всю строку: целая цена либо до двух знаков после запятой/точки.

```python
    if not re.fullmatch(r"\d+(?:[,.]\d{1,2})?", cleaned):
```

**Строка 81.** Сообщает исходное неподходящее значение.

```python
        raise ValueError("Нераспознанная цена: " + repr(raw))
```

**Строка 82.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
    try:
```

**Строка 83.** Заменяет запятую точкой и создаёт Decimal.

```python
        value = Decimal(cleaned.replace(",", "."))
```

**Строка 84.** Перехватывает некорректное десятичное число.

```python
    except InvalidOperation as exc:
```

**Строка 85.** Поднимает понятную ошибку, сохраняя исходную причину через from exc.

```python
        raise ValueError("Некорректная цена") from exc
```

**Строка 86.** Для JSON возвращает int либо float. Для денежной модели БД нужно сохранять Decimal.

```python
    return int(value) if value == value.to_integral_value() else float(value)
```

**Строка 87.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 88.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 89.** Проверяет входной URL ещё при разборе CLI.

```python
def validate_url(value):
```

**Строка 90.** Разбивает URL на компоненты.

```python
    parsed = urlsplit(value)
```

**Строка 91.** Требует HTTPS, разрешённый хост Ozon и отсутствие логина/пароля в URL.

```python
    if parsed.scheme != "https" or parsed.hostname not in {"ozon.ru", "www.ozon.ru"} or parsed.username or parsed.password:
```

**Строка 92.** Ошибка argparse для недопустимого адреса.

```python
        raise argparse.ArgumentTypeError("Нужна HTTPS-ссылка на ozon.ru или www.ozon.ru")
```

**Строка 93.** Определяет ссылку на отдельный товар по пути.

```python
    if parsed.path.startswith("/product/"):
```

**Строка 94.** Отклоняет её: поддерживаются поиск и категории.

```python
        raise argparse.ArgumentTypeError("Передайте выдачу поиска или категорию, а не отдельный товар")
```

**Строка 95.** Возвращает проверенную исходную ссылку.

```python
    return value
```

**Строка 96.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 97.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 98.** Определяет построение URL нужной страницы выдачи.

```python
def page_url(url, number):
```

**Строка 99.** Разбирает исходный URL.

```python
    parts = urlsplit(url)
```

**Строка 100.** Парсит список параметров, сохраняет повторы и пустые значения, исключает старый page.

```python
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
```

**Строка 101.** Добавляет новый номер страницы.

```python
    query.append(("page", str(number)))
```

**Строка 102.** Собирает URL с закодированными параметрами без fragment.

```python
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
```

**Строка 103.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 104.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 105.** Определяет нормализацию сырой карточки.

```python
def normalize_card(card):
```

**Строка 106.** Разбирает ссылку карточки.

```python
    parts = urlsplit(card["url"])
```

**Строка 107.** Проверяет принадлежность домену Ozon.

```python
    if parts.hostname not in {"ozon.ru", "www.ozon.ru"}:
```

**Строка 108.** Отклоняет стороннюю ссылку.

```python
        raise ValueError("Ссылка товара вне Ozon")
```

**Строка 109.** Собирает канонический HTTPS URL на www.ozon.ru без query и fragment.

```python
    url = urlunsplit(("https", "www.ozon.ru", parts.path, "", ""))
```

**Строка 110.** Ищет числовой ID после дефиса в конце пути.

```python
    match = re.search(r"-(\d+)/?$", parts.path)
```

**Строка 111.** Ключ дедупликации — ID; резервный ключ — URL.

```python
    key = match.group(1) if match else url
```

**Строка 112.** Схлопывает переносы строк и повторяющиеся пробелы в названии.

```python
    name = " ".join(card["name"].split())
```

**Строка 113.** Проверяет, осталось ли название после очистки.

```python
    if not name:
```

**Строка 114.** Поднимает ошибку для пустого названия.

```python
        raise ValueError("Пустое название")
```

**Строка 115.** Возвращает ключ и словарь с названием и числовой ценой.

```python
    return key, {"name": name, "price": parse_price(card["price_raw"]),
```

**Строка 116.** Дополняет словарь валютой RUB, исходным блоком цены и ссылкой.

```python
                 "currency": "RUB", "price_text": card["price_text"], "url": url}
```

**Строка 117.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 118.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 119.** Преобразователь положительных целых аргументов CLI.

```python
def positive_int(value):
```

**Строка 120.** Преобразует строку в int; нечисловое значение вызывает ValueError, который обработает argparse.

```python
    number = int(value)
```

**Строка 121.** Проверяет нижнюю границу.

```python
    if number <= 0:
```

**Строка 122.** Сообщает ошибку для нуля и отрицательных значений.

```python
        raise argparse.ArgumentTypeError("Значение должно быть больше нуля")
```

**Строка 123.** Возвращает положительное число.

```python
    return number
```

**Строка 124.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 125.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 126.** Открывает страницу выдачи, при необходимости оставляет время для ручных действий.

```python
def open_listing(page, url, number, manual):
```

**Строка 127.** Строит URL и открывает его до события domcontentloaded; товары могут загрузиться позже.

```python
    response = page.goto(page_url(url, number), wait_until="domcontentloaded")
```

**Строка 128.** Берёт статус ответа; при отсутствии ответа — None.

```python
    status = response.status if response is not None else None
```

**Строка 129.** Обрабатывает HTTP-ошибки от 400.

```python
    if status is not None and status >= 400:
```

**Строка 130.** Все ошибки кроме 403 в ручном режиме считаются немедленным отказом.

```python
        if status != 403 or not manual:
```

**Строка 131.** Для 403 добавляет подсказку о ручном режиме и профиле.

```python
            hint = "; попробуйте --headed --manual --profile .ozon-profile" if status == 403 else ""
```

**Строка 132.** Поднимает ошибку с HTTP-статусом и номером страницы.

```python
            raise RuntimeError("Ozon вернул HTTP %s на странице %s%s" % (status, number, hint))
```

**Строка 133.** При ручном 403 сообщает, что окно останется открытым.

```python
        print("Ozon вернул HTTP 403. Окно оставлено открытым для ручной проверки доступа.", file=sys.stderr)
```

**Строка 134.** Проверяет ручной режим.

```python
    if manual:
```

**Строка 135.** Блокирует выполнение до Enter в терминале, позволяя действия в браузере.

```python
        input("Выберите регион/пройдите проверку в браузере. Если нужно, обновите страницу. Когда появятся товары, нажмите Enter здесь: ")
```

**Строка 136.** Комментарий: после ручных переходов исходный HTTP-статус может уже не описывать страницу.

```python
    # After manual navigation the initial HTTP status is stale. The caller
```

**Строка 137.** Комментарий: фактическое наличие карточек проверяет вызывающая функция.

```python
    # verifies that listing cards are actually present in the current page.
```

**Строка 138.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 139.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 140.** Определяет распознавание известной страницы отказа Ozon.

```python
def check_access_page(page):
```

**Строка 141.** Читает видимый текст body, ожидая его максимум пять секунд.

```python
    text = page.locator("body").inner_text(timeout=5000)
```

**Строка 142.** Считает страницу отказом только при наличии двух характерных сообщений.

```python
    if "Похоже, нет соединения" in text and "Обратиться в поддержку" in text:
```

**Строка 143.** Извлекает номер инцидента из текста.

```python
        incident = re.search(r"Инцидент:\s*(\S+)", text)
```

**Строка 144.** Формирует дополнение с номером, если он найден.

```python
        detail = " Инцидент: " + incident.group(1) if incident else ""
```

**Строка 145.** Начинает формирование RuntimeError.

```python
        raise RuntimeError(
```

**Строка 146.** Первая часть сообщения: вместо товаров открыта страница отказа.

```python
            "Ozon показывает страницу отказа в доступе, а не товары. "
```

**Строка 147.** Предлагает сравнить доступ с обычным браузером.

```python
            "Проверьте эту ссылку в обычном браузере; если ошибка та же, "
```

**Строка 148.** Продолжает подсказку о возможной сетевой проблеме.

```python
            "попробуйте отключить VPN или использовать другую сеть. "
```

**Строка 149.** Уточняет, что --direct не отключает системный VPN.

```python
            "--direct отключает только браузерный прокси, но не системный VPN."
```

**Строка 150.** Добавляет инцидент и завершает исключение.

```python
            + detail)
```

**Строка 151.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 152.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 153.** Режим подготовки сохраняемого профиля без сбора товаров.

```python
def prepare_profile(args):
```

**Строка 154.** Импортирует синхронный Playwright внутри функции.

```python
    from playwright.sync_api import sync_playwright
```

**Строка 155.** Контекстный менеджер запускает и завершает драйвер Playwright.

```python
    with sync_playwright() as p:
```

**Строка 156.** Настраивает видимое окно; по умолчанию установленный Chrome.

```python
        options = {"headless": False, "channel": args.channel or "chrome",
```

**Строка 157.** Задаёт локаль и размер области страницы.

```python
                   "locale": "ru-RU", "viewport": {"width": 1440, "height": 1000}}
```

**Строка 158.** Проверяет флаг прямого подключения.

```python
        if args.direct:
```

**Строка 159.** Отключает браузерный прокси через аргумент Chrome.

```python
            options["args"] = ["--no-proxy-server"]
```

**Строка 160.** Запускает сохраняемый профиль по абсолютному пути; **options раскрывает словарь аргументов.

```python
        context = p.chromium.launch_persistent_context(str(args.profile.resolve()), **options)
```

**Строка 161.** Флаг закрытия браузерного контекста.

```python
        closed = False
```

**Строка 162.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 163.** Определяет обработчик события закрытия, игнорируя аргументы события.

```python
        def on_close(*_):
```

**Строка 164.** Разрешает менять переменную closed из внешней функции.

```python
            nonlocal closed
```

**Строка 165.** Помечает контекст закрытым.

```python
            closed = True
```

**Строка 166.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 167.** Подписывает обработчик на событие close.

```python
        context.on("close", on_close)
```

**Строка 168.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
        try:
```

**Строка 169.** Использует первую вкладку или создаёт новую.

```python
            page = context.pages[0] if context.pages else context.new_page()
```

**Строка 170.** Открывает главную Ozon; секунды CLI переводит в миллисекунды.

```python
            page.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=args.timeout * 1000)
```

**Строка 171.** Начинает сообщение с ручной инструкцией.

```python
            print("Подготовка профиля: откройте товары, при необходимости войдите в Ozon. "
```

**Строка 172.** Завершает сообщение; flush=True сразу выводит его в терминал.

```python
                  "Затем закройте все окна этого отдельного Chrome. Пароли вводите только в браузере.", flush=True)
```

**Строка 173.** Ждёт закрытия контекста циклом.

```python
            while not closed:
```

**Строка 174.** Проверяет отсутствие вкладок.

```python
                if not context.pages:
```

**Строка 175.** Выходит, если все вкладки закрыты.

```python
                    break
```

**Строка 176.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
                try:
```

**Строка 177.** Ждёт полсекунды через Playwright, позволяя обработку событий браузера.

```python
                    context.pages[0].wait_for_timeout(500)
```

**Строка 178.** Обрабатывает исключение во время ожидания.

```python
                except Exception:
```

**Строка 179.** Проверяет, вызвано ли исключение обычным закрытием.

```python
                    if closed or not context.pages:
```

**Строка 180.** Если да — завершает цикл.

```python
                        break
```

**Строка 181.** Если причина другая, повторно поднимает исключение.

```python
                    raise
```

**Строка 182.** Блок освобождения ресурсов: выполняется при успехе и при исключении.

```python
        finally:
```

**Строка 183.** Если контекст ещё открыт, его нужно закрыть.

```python
            if not closed:
```

**Строка 184.** Закрывает контекст и браузер, завершая работу с профилем.

```python
                context.close()
```

**Строка 185.** Сообщает расположение сохранённого профиля; это не доказательство доступа к товарам.

```python
    print("Профиль сохранён: %s" % args.profile.resolve())
```

**Строка 186.** Успешный код завершения подготовки.

```python
    return 0
```

**Строка 187.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 188.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 189.** Основной сбор товаров.

```python
def scrape(args):
```

**Строка 190.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
    try:
```

**Строка 191.** Импортирует Playwright и даёт его TimeoutError отдельное имя.

```python
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
```

**Строка 192.** Обрабатывает отсутствие установленной библиотеки.

```python
    except ImportError as exc:
```

**Строка 193.** Показывает команду установки и сохраняет первопричину исключения.

```python
        raise RuntimeError("Установите Playwright: python -m pip install playwright") from exc
```

**Строка 194.** Словарь товаров по уникальным ключам — одновременно накопитель и дедупликация.

```python
    products = {}
```

**Строка 195.** Запускает драйвер Playwright внутри контекстного менеджера.

```python
    with sync_playwright() as p:
```

**Строка 196.** Скрытый режим включён, если --headed отсутствует.

```python
        launch_options = {"headless": not args.headed}
```

**Строка 197.** Проверяет явно выбранный браузер.

```python
        if args.channel:
```

**Строка 198.** Добавляет канал chrome либо msedge в параметры запуска.

```python
            launch_options["channel"] = args.channel
```

**Строка 199.** Проверяет --direct.

```python
        if args.direct:
```

**Строка 200.** Добавляет запрет браузерного прокси.

```python
            launch_options["args"] = ["--no-proxy-server"]
```

**Строка 201.** Задаёт настройки контекста: локаль и viewport.

```python
        context_options = {"locale": "ru-RU", "viewport": {"width": 1440, "height": 1000}}
```

**Строка 202.** browser=None отличает сохраняемый контекст от обычного браузера ниже.

```python
        browser = None
```

**Строка 203.** Выбирает режим с сохраняемым профилем.

```python
        if args.profile:
```

**Строка 204.** Начинает запуск persistent context.

```python
            context = p.chromium.launch_persistent_context(
```

**Строка 205.** Передаёт абсолютный путь и оба набора параметров.

```python
                str(args.profile.resolve()), **launch_options, **context_options)
```

**Строка 206.** Альтернативная ветвь предыдущего if.

```python
        else:
```

**Строка 207.** В обычном режиме запускает браузер.

```python
            browser = p.chromium.launch(**launch_options)
```

**Строка 208.** Создаёт временный изолированный контекст без сохранения сессии.

```python
            context = browser.new_context(**context_options)
```

**Строка 209.** Открывает новую вкладку; оставшиеся вкладки профиля для сбора не использует.

```python
        page = context.new_page()
```

**Строка 210.** Задаёт стандартный таймаут операций в миллисекундах.

```python
        page.set_default_timeout(args.timeout * 1000)
```

**Строка 211.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
        try:
```

**Строка 212.** Перебирает страницы начиная со start_page; правая граница range не включается.

```python
            for number in range(args.start_page, args.start_page + args.pages):
```

**Строка 213.** Открывает выдачу и, если нужен manual, ждёт Enter.

```python
                open_listing(page, args.url, number, args.manual)
```

**Строка 214.** Проверяет известную страницу отказа.

```python
                check_access_page(page)
```

**Строка 215.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
                try:
```

**Строка 216.** Ждёт истинности JS-предиката: должны появиться ссылки в контейнере выдачи.

```python
                    page.wait_for_function(WAIT_FOR_CARDS)
```

**Строка 217.** Обрабатывает превышение таймаута ожидания.

```python
                except PlaywrightTimeout as exc:
```

**Строка 218.** Собирает сведения о текущей странице.

```python
                    info = listing_diagnostics(page)
```

**Строка 219.** Начинает понятное сообщение об отсутствии выдачи.

```python
                    raise RuntimeError("Не найдена выдача товаров. Откройте поиск/категорию с товарами перед Enter. "
```

**Строка 220.** Добавляет JSON-диагностику и связывает исключение с таймаутом.

```python
                                       "Диагностика: " + json.dumps(info, ensure_ascii=False)) from exc
```

**Строка 221.** Запоминает количество товаров до этой страницы.

```python
                before = len(products)
```

**Строка 222.** Счётчик повторений одинакового набора видимых товаров.

```python
                stable = 0
```

**Строка 223.** Пустой предыдущий набор ключей.

```python
                previous_keys = set()
```

**Строка 224.** Цикл не более scrolls итераций; каждая итерация сначала извлекает карточки.

```python
                for _ in range(args.scrolls):
```

**Строка 225.** Исполняет EXTRACT_CARDS в DOM браузера и получает список Python-словарей.

```python
                    raw_cards = page.evaluate(EXTRACT_CARDS)
```

**Строка 226.** Создаёт набор ключей текущей итерации.

```python
                    keys = set()
```

**Строка 227.** Перебирает сырые карточки.

```python
                    for card in raw_cards:
```

**Строка 228.** Нормализует название, цену и URL; получает ключ дедупликации.

```python
                        key, product = normalize_card(card)
```

**Строка 229.** Добавляет ключ в текущий набор.

```python
                        keys.add(key)
```

**Строка 230.** Комментарий: сохраняется первая встреченная цена товара.

```python
                        # Keep the first displayed price for repeated products.
```

**Строка 231.** setdefault добавляет новый товар; уже известный ключ не обновляется.

```python
                        products.setdefault(key, product)
```

**Строка 232.** Увеличивает stable при неизменном наборе; иначе сбрасывает в ноль.

```python
                    stable = stable + 1 if keys == previous_keys else 0
```

**Строка 233.** Запоминает текущий набор для следующего сравнения.

```python
                    previous_keys = keys
```

**Строка 234.** Проверяет достижение заданного общего лимита.

```python
                    if args.limit and len(products) >= args.limit:
```

**Строка 235.** Останавливает цикл извлечения/прокрутки по лимиту.

```python
                        break
```

**Строка 236.** Проверяет три повторения одинакового набора.

```python
                    if stable >= 3:
```

**Строка 237.** Останавливает прокрутку как предположительно исчерпанную.

```python
                        break
```

**Строка 238.** Прокручивает вниз на 80% высоты окна, минимум на 600 пикселей.

```python
                    page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.8, 600))")
```

**Строка 239.** Даёт странице время загрузить следующие карточки.

```python
                    page.wait_for_timeout(args.delay * 1000)
```

**Строка 240.** Проверяет наличие распознанных карточек в последней итерации.

```python
                if not previous_keys:
```

**Строка 241.** Если их нет, начинает сообщение об ошибке извлечения.

```python
                    raise RuntimeError("Ссылки товаров есть, но названия/цены не распознаны. Диагностика: "
```

**Строка 242.** Добавляет диагностику страницы.

```python
                                       + json.dumps(listing_diagnostics(page), ensure_ascii=False))
```

**Строка 243.** Выводит номер страницы и количество новых уникальных товаров в stderr.

```python
                print("Страница %s: новых товаров %s" % (number, len(products) - before), file=sys.stderr)
```

**Строка 244.** Повторно проверяет общий лимит после завершения страницы.

```python
                if args.limit and len(products) >= args.limit:
```

**Строка 245.** Останавливает цикл страниц.

```python
                    break
```

**Строка 246.** Если впереди ещё одна запрошенная страница, нужна пауза.

```python
                if number < args.start_page + args.pages - 1:
```

**Строка 247.** Ждёт заданную задержку перед следующим переходом.

```python
                    page.wait_for_timeout(args.delay * 1000)
```

**Строка 248.** Блок освобождения ресурсов: выполняется при успехе и при исключении.

```python
        finally:
```

**Строка 249.** Закрывает контекст даже при ошибке.

```python
            context.close()
```

**Строка 250.** В обычном режиме существует отдельный объект браузера.

```python
            if browser is not None:
```

**Строка 251.** Закрывает его; persistent context сам закрывает свой браузер.

```python
                browser.close()
```

**Строка 252.** Превращает значения словаря в список результатов.

```python
    result = list(products.values())
```

**Строка 253.** Обрезает список до лимита либо возвращает полностью.

```python
    return result[:args.limit] if args.limit else result
```

**Строка 254.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 255.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 256.** Точка входа командной строки.

```python
def main():
```

**Строка 257.** Перебирает стандартные потоки stdout и stderr.

```python
    for stream in (sys.stdout, sys.stderr):
```

**Строка 258.** Проверяет поддержку изменения кодировки/обработки ошибок потока.

```python
        if hasattr(stream, "reconfigure"):
```

**Строка 259.** Непредставимые символы заменяются вместо аварии; это не гарантирует правильный показ кириллицы в любой консоли.

```python
            stream.reconfigure(errors="replace")
```

**Строка 260.** Создаёт argparse с описанием программы.

```python
    parser = argparse.ArgumentParser(description="Названия и видимые цены товаров Ozon в JSON")
```

**Строка 261.** Обязательный позиционный URL проверяется validate_url.

```python
    parser.add_argument("url", type=validate_url, help="Ссылка на поиск или категорию Ozon")
```

**Строка 262.** Путь результата; по умолчанию products.json в текущей рабочей папке.

```python
    parser.add_argument("--output", type=Path, default=Path("products.json"))
```

**Строка 263.** Число страниц; по умолчанию одна.

```python
    parser.add_argument("--pages", type=positive_int, default=1)
```

**Строка 264.** Начальная страница; по умолчанию первая.

```python
    parser.add_argument("--start-page", type=positive_int, default=1)
```

**Строка 265.** Необязательный положительный лимит товаров; без флага None.

```python
    parser.add_argument("--limit", type=positive_int)
```

**Строка 266.** Максимум итераций извлечения/прокрутки — 25.

```python
    parser.add_argument("--scrolls", type=positive_int, default=25)
```

**Строка 267.** Задержка в целых положительных секундах — 2; дроби и ноль запрещены.

```python
    parser.add_argument("--delay", type=positive_int, default=2, help="Пауза между прокрутками/страницами, секунды")
```

**Строка 268.** Таймаут в секундах — 45.

```python
    parser.add_argument("--timeout", type=positive_int, default=45)
```

**Строка 269.** Булев флаг видимого окна.

```python
    parser.add_argument("--headed", action="store_true", help="Показать окно браузера")
```

**Строка 270.** Булев флаг ручного подтверждения каждой страницы.

```python
    parser.add_argument("--manual", action="store_true", help="Ждать ручного подтверждения после открытия каждой страницы")
```

**Строка 271.** Необязательная папка сохраняемого профиля.

```python
    parser.add_argument("--profile", type=Path, help="Отдельная папка профиля для сохранения cookies и сессии")
```

**Строка 272.** Канал браузера ограничен chrome и msedge.

```python
    parser.add_argument("--channel", choices=["chrome", "msedge"], help="Использовать установленный Chrome или Edge")
```

**Строка 273.** Булев флаг отключения браузерного прокси.

```python
    parser.add_argument("--direct", action="store_true", help="Отключить браузерный прокси (не отключает системный VPN)")
```

**Строка 274.** Булев флаг подготовки профиля вместо сбора.

```python
    parser.add_argument("--prepare-profile", action="store_true", help="Открыть отдельный Chrome для ручной подготовки сессии; закрытие окна сохраняет профиль")
```

**Строка 275.** Разбирает argv и формирует объект args.

```python
    args = parser.parse_args()
```

**Строка 276.** Проверяет недопустимое сочетание manual без видимого окна.

```python
    if args.manual and not args.headed:
```

**Строка 277.** Выводит ошибку использования и завершает программу через argparse.

```python
        parser.error("--manual используется вместе с --headed")
```

**Строка 278.** Проверяет наличие папки для режима подготовки.

```python
    if args.prepare_profile and not args.profile:
```

**Строка 279.** Сообщает ошибку, если profile отсутствует.

```python
        parser.error("--prepare-profile требует --profile с отдельной папкой профиля")
```

**Строка 280.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
    try:
```

**Строка 281.** Выбирает подготовку профиля.

```python
        if args.prepare_profile:
```

**Строка 282.** Возвращает её код, пропуская сбор и запись JSON.

```python
            return prepare_profile(args)
```

**Строка 283.** Запускает сбор и получает список товаров.

```python
        products = scrape(args)
```

**Строка 284.** Проверяет, что список непустой.

```python
        if not products:
```

**Строка 285.** Запрещает запись пустого результата как успешного.

```python
            raise RuntimeError("Товары не найдены; JSON не записан")
```

**Строка 286.** Создаёт родительские папки результата, если их нет.

```python
        args.output.parent.mkdir(parents=True, exist_ok=True)
```

**Строка 287.** Выбирает временный файл рядом с целевым, с суффиксом .tmp.

```python
        temporary = args.output.with_name(args.output.name + ".tmp")
```

**Строка 288.** Записывает форматированный UTF-8 JSON без экранирования кириллицы и с переводом строки в конце.

```python
        temporary.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

**Строка 289.** Заменяет итоговый файл временным только после успешной записи. Одновременные запуски с одним output могут конфликтовать.

```python
        temporary.replace(args.output)
```

**Строка 290.** Обрабатывает известные ошибки данных, доступа и файлов.

```python
    except (RuntimeError, ValueError, OSError) as exc:
```

**Строка 291.** Печатает понятное сообщение в stderr.

```python
        print("Ошибка: " + str(exc), file=sys.stderr)
```

**Строка 292.** Код 1 означает неуспех.

```python
        return 1
```

**Строка 293.** Ловит прочие исключения, включая ошибки браузера.

```python
    except Exception as exc:
```

**Строка 294.** Комментарий: прежний JSON сохраняется при ошибке сборки/навигации.

```python
        # Includes browser startup/navigation errors; preserve any existing JSON.
```

**Строка 295.** Печатает сообщение с общей меткой «Ошибка браузера»; причина может быть и иной.

```python
        print("Ошибка браузера: " + str(exc), file=sys.stderr)
```

**Строка 296.** Возвращает код ошибки.

```python
        return 1
```

**Строка 297.** Сообщает число сохранённых товаров и абсолютный путь файла.

```python
    print("Сохранено %s товаров: %s" % (len(products), args.output.resolve()))
```

**Строка 298.** Возвращает успешный код 0.

```python
    return 0
```

**Строка 299.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 300.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 301.** Запускает main только при прямом выполнении файла, не при импорте.

```python
if __name__ == "__main__":
```

**Строка 302.** Передаёт возвращённый main код операционной системе.

```python
    sys.exit(main())
```

## check_browser.py

**Строка 1.** Диагностический модуль: сравнивает доступ к сайтам, товары не извлекает.

```python
"""Compare browser connectivity without collecting product data."""
```

**Строка 2.** JSON для машиночитаемого вывода.

```python
import json
```

**Строка 3.** Синхронный интерфейс Playwright.

```python
from playwright.sync_api import sync_playwright
```

**Строка 4.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 5.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 6.** Функция проверки.

```python
def main():
```

**Строка 7.** Запуск и автоматическое завершение драйвера.

```python
    with sync_playwright() as p:
```

**Строка 8.** Два режима: настройки по умолчанию и без браузерного прокси.

```python
        for direct in (False, True):
```

**Строка 9.** В обоих случаях браузер скрыт.

```python
            options = {"headless": True}
```

**Строка 10.** Дополнительные параметры только для direct=True.

```python
            if direct:
```

**Строка 11.** Chrome-флаг отключения прокси.

```python
                options["args"] = ["--no-proxy-server"]
```

**Строка 12.** Запускает Chromium с выбранными параметрами.

```python
            browser = p.chromium.launch(**options)
```

**Строка 13.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
            try:
```

**Строка 14.** Создаёт временный контекст с русской локалью и заданным viewport.

```python
                context = browser.new_context(locale="ru-RU", viewport={"width": 1440, "height": 1000})
```

**Строка 15.** Создаёт вкладку.

```python
                page = context.new_page()
```

**Строка 16.** Список тестируемых ресурсов, включая изменённые пользователем адреса Wildberries; один URL содержит завершающий пробел.

```python
                for url in ("https://example.com", "https://www.wikipedia.org", "https://www.ozon.ru/", "https://www.wildberries.ru/", "https://www.wildberries.ru/catalog/0/search.aspx?search=iphone "):
```

**Строка 17.** Начальные поля отчёта: URL и режим direct.

```python
                    result = {"url": url, "direct": direct}
```

**Строка 18.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
                    try:
```

**Строка 19.** Открывает адрес до DOMContentLoaded с таймаутом 20 секунд.

```python
                        response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
```

**Строка 20.** Добавляет HTTP-статус, если ответ существует.

```python
                        result.update(status=response.status if response else None,
```

**Строка 21.** Добавляет заголовок и адрес после перенаправлений.

```python
                                      title=page.title(), final_url=page.url)
```

**Строка 22.** Перехватывает ошибку конкретного адреса.

```python
                    except Exception as exc:
```

**Строка 23.** Записывает текст ошибки в отчёт.

```python
                        result["error"] = str(exc)
```

**Строка 24.** Выводит отдельную JSON-строку сразу; ensure_ascii экранирует кириллицу.

```python
                    print(json.dumps(result, ensure_ascii=True), flush=True)
```

**Строка 25.** Блок освобождения ресурсов: выполняется при успехе и при исключении.

```python
            finally:
```

**Строка 26.** Закрывает браузер независимо от результата проверок.

```python
                browser.close()
```

**Строка 27.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 28.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 29.** Условие прямого запуска.

```python
if __name__ == "__main__":
```

**Строка 30.** Вызывает диагностику.

```python
    main()
```

## check_habr_browser.py

**Строка 1.** Описание диагностического эксперимента с настройками статьи Habr.

```python
"""Test the browser configuration from the user-provided Habr guide."""
```

**Строка 2.** JSON для отчётов.

```python
import json
```

**Строка 3.** CLI-параметры.

```python
import argparse
```

**Строка 4.** Синхронный Playwright.

```python
from playwright.sync_api import sync_playwright
```

**Строка 5.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 6.** Строка JavaScript, исполняемая до скриптов сайта.

```python
INIT_SCRIPT = """
```

**Строка 7.** Переопределяет navigator.webdriver, возвращая undefined.

```python
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
```

**Строка 8.** Возвращает искусственный массив plugins. Это эксперимент, не настоящее PluginArray браузера.

```python
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
```

**Строка 9.** Закрывает JS-строку.

```python
"""
```

**Строка 10.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 11.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 12.** Основная функция эксперимента.

```python
def main():
```

**Строка 13.** Создаёт разборщик CLI.

```python
    parser = argparse.ArgumentParser()
```

**Строка 14.** Флаг видимого окна.

```python
    parser.add_argument("--headed", action="store_true")
```

**Строка 15.** Разрешённые варианты эксперимента.

```python
    parser.add_argument("--mode", choices=["guide", "current_chromium", "installed_chrome"])
```

**Строка 16.** Разбирает аргументы.

```python
    args = parser.parse_args()
```

**Строка 17.** Запускает Playwright.

```python
    with sync_playwright() as p:
```

**Строка 18.** Проверяет один выбранный режим либо все три.

```python
        for mode in ([args.mode] if args.mode else ("guide", "current_chromium", "installed_chrome")):
```

**Строка 19.** Настраивает видимость и отключает Blink-признак AutomationControlled.

```python
            options = dict(headless=not args.headed, args=["--disable-blink-features=AutomationControlled"])
```

**Строка 20.** Выбирает установленный Chrome для соответствующего режима.

```python
            if mode == "installed_chrome":
```

**Строка 21.** Передаёт channel=chrome.

```python
                options["channel"] = "chrome"
```

**Строка 22.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
            try:
```

**Строка 23.** Пробует запустить браузер.

```python
                browser = p.chromium.launch(**options)
```

**Строка 24.** Обрабатывает ошибку запуска, например отсутствие Chrome.

```python
            except Exception as exc:
```

**Строка 25.** Печатает режим и ошибку.

```python
                print(json.dumps({"mode": mode, "error": str(exc)}, ensure_ascii=True), flush=True)
```

**Строка 26.** Переходит к следующему режиму.

```python
                continue
```

**Строка 27.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
            try:
```

**Строка 28.** Настраивает размер окна и русскую локаль.

```python
                settings = dict(viewport={"width": 1920, "height": 1080}, locale="ru-RU")
```

**Строка 29.** Ветвь буквального User-Agent из статьи.

```python
                if mode == "guide":
```

**Строка 30.** User-Agent с macOS и WebKit; он неполный и может не соответствовать реальному браузеру.

```python
                    settings["user_agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
```

**Строка 31.** Альтернативная ветвь предыдущего if.

```python
                else:
```

**Строка 32.** Создаёт временную вкладку для получения фактического User-Agent.

```python
                    probe = browser.new_page()
```

**Строка 33.** Удаляет маркер HeadlessChrome из полученного User-Agent, сохраняя фактическую версию.

```python
                    settings["user_agent"] = probe.evaluate("navigator.userAgent").replace("HeadlessChrome/", "Chrome/")
```

**Строка 34.** Закрывает временную вкладку.

```python
                    probe.close()
```

**Строка 35.** Создаёт контекст с выбранными настройками.

```python
                context = browser.new_context(**settings)
```

**Строка 36.** В буквальном режиме статьи нужны оба переопределения.

```python
                if mode == "guide":
```

**Строка 37.** Добавляет INIT_SCRIPT перед скриптами сайта.

```python
                    context.add_init_script(INIT_SCRIPT)
```

**Строка 38.** Альтернативная ветвь предыдущего if.

```python
                else:
```

**Строка 39.** В остальных режимах меняет только webdriver.

```python
                    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
```

**Строка 40.** Создаёт рабочую вкладку.

```python
                page = context.new_page()
```

**Строка 41.** Накопитель неуспешных HTTP-ответов.

```python
                failures = []
```

**Строка 42.** Подписывает обработчик: для статусов от 400 сохраняет статус и URL без query.

```python
                page.on("response", lambda r: failures.append({"status": r.status, "path": r.url.split('?')[0]}) if r.status >= 400 else None)
```

**Строка 43.** Открывает поиск наушников с таймаутом 20 секунд.

```python
                response = page.goto("https://www.ozon.ru/search/?text=наушники&from_global=true", wait_until="domcontentloaded", timeout=20000)
```

**Строка 44.** Ждёт три секунды для загрузки клиентских запросов.

```python
                page.wait_for_timeout(3000)
```

**Строка 45.** Начинает печать отчёта: режим и первоначальный HTTP-статус.

```python
                print(json.dumps({"mode": mode, "status": response.status if response else None,
```

**Строка 46.** Добавляет заголовок и число любых товарных ссылок.

```python
                                  "title": page.title(), "product_links": page.locator("a[href*='/product/']").count(),
```

**Строка 47.** Добавляет фактическое значение webdriver и ошибки запросов; undefined сериализуется как null.

```python
                                  "webdriver": page.evaluate("navigator.webdriver"), "failures": failures}, ensure_ascii=True), flush=True)
```

**Строка 48.** Перехватывает ошибку навигации или оценки страницы.

```python
            except Exception as exc:
```

**Строка 49.** Печатает ошибку этого режима.

```python
                print(json.dumps({"mode": mode, "error": str(exc)}, ensure_ascii=True), flush=True)
```

**Строка 50.** Блок освобождения ресурсов: выполняется при успехе и при исключении.

```python
            finally:
```

**Строка 51.** Всегда закрывает браузер после режима.

```python
                browser.close()
```

**Строка 52.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 53.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 54.** Условие прямого запуска.

```python
if __name__ == "__main__":
```

**Строка 55.** Вызывает main.

```python
    main()
```

## tests/test_ozon_parser.py

**Строка 1.** Позволяет импортировать модуль по пути к файлу.

```python
import importlib.util
```

**Строка 2.** Утилита путей.

```python
from pathlib import Path
```

**Строка 3.** Стандартная библиотека тестирования.

```python
import unittest
```

**Строка 4.** Mock имитирует браузерные объекты; patch временно заменяет функции.

```python
from unittest.mock import Mock, patch
```

**Строка 5.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 6.** Создаёт описание импорта ozon_parser.py из родительской папки tests.

```python
spec = importlib.util.spec_from_file_location("ozon_parser", Path(__file__).resolve().parents[1] / "ozon_parser.py")
```

**Строка 7.** Создаёт модуль по описанию импорта.

```python
module = importlib.util.module_from_spec(spec)
```

**Строка 8.** Исполняет импортируемый модуль; main не запускается благодаря __name__.

```python
spec.loader.exec_module(module)
```

**Строка 9.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 10.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 11.** Класс независимых проверок unittest.

```python
class ParserTests(unittest.TestCase):
```

**Строка 12.** Проверка распознавания страницы отказа и инцидента.

```python
    def test_access_denied_page_reports_incident(self):
```

**Строка 13.** Фальшивый объект страницы вместо настоящего браузера.

```python
        page = Mock()
```

**Строка 14.** Задаёт результат цепочки locator().inner_text().

```python
        page.locator.return_value.inner_text.return_value = (
```

**Строка 15.** Текст страницы отказа с тестовым инцидентом.

```python
            "Похоже, нет соединения\nОбратиться в поддержку\nИнцидент: fab_chlg_test")
```

**Строка 16.** Ожидает RuntimeError с конкретным номером инцидента.

```python
        with self.assertRaisesRegex(RuntimeError, "Инцидент: fab_chlg_test"):
```

**Строка 17.** Вызывает проверяемую функцию.

```python
            module.check_access_page(page)
```

**Строка 18.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 19.** Проверка, что обычная карточка не считается отказом.

```python
    def test_listing_is_not_mistaken_for_access_denied_page(self):
```

**Строка 20.** Создаёт имитацию страницы.

```python
        page = Mock()
```

**Строка 21.** Текст нормальной страницы.

```python
        page.locator.return_value.inner_text.return_value = "Наушники 1 299 ₽"
```

**Строка 22.** Вызов должен завершиться без исключения.

```python
        module.check_access_page(page)
```

**Строка 23.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 24.** Проверка, что ручной режим допускает действие пользователя при 403.

```python
    def test_manual_403_allows_user_to_open_listing(self):
```

**Строка 25.** Имитирует страницу.

```python
        page = Mock()
```

**Строка 26.** goto возвращает ответ со статусом 403.

```python
        page.goto.return_value.status = 403
```

**Строка 27.** Заменяет input, имитируя Enter без ручного ввода.

```python
        with patch("builtins.input", return_value="") as prompt:
```

**Строка 28.** Открывает выдачу в ручном режиме на имитации страницы.

```python
            module.open_listing(page, "https://www.ozon.ru/search/?text=test", 1, True)
```

**Строка 29.** Проверяет единственный вызов приглашения к вводу.

```python
        prompt.assert_called_once()
```

**Строка 30.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 31.** Проверка ошибки 403 в автоматическом режиме.

```python
    def test_automatic_403_reports_recovery_options(self):
```

**Строка 32.** Имитирует страницу.

```python
        page = Mock()
```

**Строка 33.** Задаёт статус 403.

```python
        page.goto.return_value.status = 403
```

**Строка 34.** Перехватывает возможный вызов input.

```python
        with patch("builtins.input") as prompt:
```

**Строка 35.** Ожидает исключение с HTTP 403 и подсказкой --profile.

```python
            with self.assertRaisesRegex(RuntimeError, "HTTP 403.*--profile"):
```

**Строка 36.** Вызывает open_listing без manual.

```python
                module.open_listing(page, "https://www.ozon.ru/search/", 1, False)
```

**Строка 37.** Убеждается, что автоматический режим не запросил Enter.

```python
        prompt.assert_not_called()
```

**Строка 38.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 39.** Проверка, что manual не игнорирует HTTP 500.

```python
    def test_manual_mode_does_not_ignore_other_http_errors(self):
```

**Строка 40.** Имитирует страницу.

```python
        page = Mock()
```

**Строка 41.** Задаёт серверную ошибку 500.

```python
        page.goto.return_value.status = 500
```

**Строка 42.** Перехватывает input.

```python
        with patch("builtins.input") as prompt:
```

**Строка 43.** Ожидает RuntimeError со статусом 500.

```python
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
```

**Строка 44.** Вызывает функцию в ручном режиме.

```python
                module.open_listing(page, "https://www.ozon.ru/search/", 1, True)
```

**Строка 45.** Подтверждает отсутствие запроса Enter.

```python
        prompt.assert_not_called()
```

**Строка 46.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 47.** Проверка допустимых цен.

```python
    def test_prices(self):
```

**Строка 48.** Примеры с обычными/неразрывными пробелами, дробной частью и нулём.

```python
        for raw, expected in [("1 299 ₽", 1299), ("12\u00a0999\u202f₽", 12999), ("99,50 ₽", 99.5), ("0 ₽", 0)]:
```

**Строка 49.** Сравнивает преобразование с ожидаемым числом.

```python
            self.assertEqual(module.parse_price(raw), expected)
```

**Строка 50.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 51.** Проверка отказа от неоднозначных цен.

```python
    def test_ambiguous_prices_rejected(self):
```

**Строка 52.** Цена «от», несколько цен, текст и отрицательная цена.

```python
        for raw in ["от 100 ₽", "100 ₽ 200 ₽", "нет цены", "-10 ₽"]:
```

**Строка 53.** Для каждого примера ожидает ValueError.

```python
            with self.assertRaises(ValueError):
```

**Строка 54.** Вызывает parse_price.

```python
                module.parse_price(raw)
```

**Строка 55.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 56.** Проверка URL пагинации и сохранения повторяющихся фильтров.

```python
    def test_pagination_preserves_filters(self):
```

**Строка 57.** Исходная страница 8, новая страница 3; фильтр brand задан дважды.

```python
        self.assertEqual(module.page_url("https://www.ozon.ru/search/?text=test&page=8&brand=1&brand=2", 3),
```

**Строка 58.** Ожидаемый URL сохраняет оба brand.

```python
                         "https://www.ozon.ru/search/?text=test&brand=1&brand=2&page=3")
```

**Строка 59.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 60.** Проверка нормализации карточки.

```python
    def test_product_normalization(self):
```

**Строка 61.** Карточка с переносом строки в названии и пробелом в цене.

```python
        key, product = module.normalize_card({"name": " Наушники\n  test ", "price_raw": "1 000 ₽",
```

**Строка 62.** Полный price_text и ссылка с query-параметром.

```python
                                             "price_text": "1 000 ₽ с картой", "url": "https://ozon.ru/product/test-123/?from=search"})
```

**Строка 63.** Проверяет числовой внешний ID как строку.

```python
        self.assertEqual(key, "123")
```

**Строка 64.** Проверяет очистку названия.

```python
        self.assertEqual(product["name"], "Наушники test")
```

**Строка 65.** Проверяет число цены.

```python
        self.assertEqual(product["price"], 1000)
```

**Строка 66.** Проверяет канонический URL без query.

```python
        self.assertEqual(product["url"], "https://www.ozon.ru/product/test-123/")
```

**Строка 67.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 68.** Проверка отклонения неподходящих URL.

```python
    def test_foreign_url_rejected(self):
```

**Строка 69.** Импортирует тип ошибки argparse.

```python
        import argparse
```

**Строка 70.** Примеры: поддельный поддомен, HTTP вместо HTTPS и логин в URL.

```python
        for url in ["https://ozon.ru.evil.com/search/", "http://ozon.ru/search/", "https://user@ozon.ru/search/"]:
```

**Строка 71.** Ожидает ArgumentTypeError.

```python
            with self.assertRaises(argparse.ArgumentTypeError):
```

**Строка 72.** Вызывает валидатор.

```python
                module.validate_url(url)
```

**Строка 73.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 74.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 75.** Условие прямого запуска тестового файла.

```python
if __name__ == "__main__":
```

**Строка 76.** Запускает тесты unittest.

```python
    unittest.main()
```

**Строка 77.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

## tests/verify_listing_dom.py

**Строка 1.** Описание локальной проверки JS-извлечения без сетевых запросов.

```python
"""Browser fixture checks for listing selectors; no network requests."""
```

**Строка 2.** sys для путей импорта.

```python
import sys
```

**Строка 3.** Path для вычисления корня проекта.

```python
from pathlib import Path
```

**Строка 4.** Добавляет родительскую папку tests в sys.path.

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

**Строка 5.** Импортирует настоящие JS-функции из парсера.

```python
from ozon_parser import EXTRACT_CARDS, WAIT_FOR_CARDS
```

**Строка 6.** Импортирует Playwright.

```python
from playwright.sync_api import sync_playwright
```

**Строка 7.** Пустая строка для визуального разделения блоков; не выполняет действий.

```python
# пустая строка
```

**Строка 8.** Запускает драйвер; скрипт выполняется и при импорте, поэтому это отдельная проверка, не unittest-модуль.

```python
with sync_playwright() as p:
```

**Строка 9.** Запускает скрытый Chromium.

```python
    browser = p.chromium.launch()
```

**Строка 10.** Начинает блок, ошибки которого обрабатываются соответствующим except или finally.

```python
    try:
```

**Строка 11.** Создаёт вкладку.

```python
        page = browser.new_page()
```

**Строка 12.** Перебирает четыре поддержанных контейнера.

```python
        for widget in ("searchResultsV2", "searchResults", "catalogResults", "tileGrid"):
```

**Строка 13.** Начинает подстановку локального HTML прямо в DOM, без goto.

```python
            page.set_content(f'''<div data-widget="{widget}"><div>
```

**Строка 14.** Товарная ссылка с названием.

```python
                <a href="https://www.ozon.ru/product/test-123/">Наушники</a>
```

**Строка 15.** Цена и закрывающие HTML-теги.

```python
                <span>1 299 ₽</span></div></div>''')
```

**Строка 16.** Проверяет, что предикат ожидания видит ссылку.

```python
            assert page.evaluate(WAIT_FOR_CARDS), widget
```

**Строка 17.** Запускает реальный JS извлечения.

```python
            cards = page.evaluate(EXTRACT_CARDS)
```

**Строка 18.** Проверяет одну карточку с ожидаемым текстом цены.

```python
            assert len(cards) == 1 and cards[0]["price_raw"] == "1 299 ₽", (widget, cards)
```

**Строка 19.** Заменяет HTML ссылкой без контейнера выдачи.

```python
        page.set_content('<a href="https://www.ozon.ru/product/test-123/">Рекомендация</a>')
```

**Строка 20.** Убеждается, что такая ссылка не удовлетворяет ожиданию.

```python
        assert not page.evaluate(WAIT_FOR_CARDS)
```

**Строка 21.** Убеждается, что извлечение не вернуло товар.

```python
        assert page.evaluate(EXTRACT_CARDS) == []
```

**Строка 22.** Сообщает успешный результат пяти сценариев.

```python
        print("PASS: four listing widgets and unrelated product link")
```

**Строка 23.** Блок освобождения ресурсов: выполняется при успехе и при исключении.

```python
    finally:
```

**Строка 24.** Всегда закрывает браузер.

```python
        browser.close()
```

## pyproject.toml

**Строка 1.** Раздел системы сборки Python-пакета.

```toml
[build-system]
```

**Строка 2.** Для сборки нужен setuptools версии не ниже 61.

```toml
requires = ["setuptools>=61"]
```

**Строка 3.** Выбирает backend setuptools.

```toml
build-backend = "setuptools.build_meta"
```

**Строка 4.** Пустая строка для визуального разделения блоков; не выполняет действий.

```toml
# пустая строка
```

**Строка 5.** Метаданные пакета.

```toml
[project]
```

**Строка 6.** Имя устанавливаемого проекта.

```toml
name = "ozon-parser"
```

**Строка 7.** Версия пакета.

```toml
version = "0.1.0"
```

**Строка 8.** Описание проекта.

```toml
description = "Collect Ozon product names and displayed prices into JSON"
```

**Строка 9.** Минимальная версия Python — 3.9.

```toml
requires-python = ">=3.9"
```

**Строка 10.** Зависимость Playwright с диапазоном версий от 1.40 до 2, не включая 2.

```toml
dependencies = ["playwright>=1.40,<2"]
```

**Строка 11.** Пустая строка для визуального разделения блоков; не выполняет действий.

```toml
# пустая строка
```

**Строка 12.** Раздел команд после установки пакета.

```toml
[project.scripts]
```

**Строка 13.** Команда ozon-parser вызывает main из ozon_parser.

```toml
ozon-parser = "ozon_parser:main"
```

**Строка 14.** Пустая строка для визуального разделения блоков; не выполняет действий.

```toml
# пустая строка
```

**Строка 15.** Настройки setuptools.

```toml
[tool.setuptools]
```

**Строка 16.** В пакет включается один Python-модуль ozon_parser; диагностические скрипты не перечислены.

```toml
py-modules = ["ozon_parser"]
```

## requirements.txt

**Строка 1.** Зависимость pip: Playwright >=1.40 и <2. Chromium устанавливается отдельной командой playwright install chromium.

```text
playwright>=1.40,<2
```

