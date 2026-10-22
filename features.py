"""Признаки наушников, извлекаемые из названия товара.

Правило проекта (ТЗ v2.0): неизвестное хранится как None (NULL в базе), а не как False или 0.
Признак ставится только если он прямо назван в тексте. False ставится только при явном
отрицании ('без микрофона'). По названию модели ('AirPods', 'FreeBuds') ничего не угадываем.
"""
import re


def _tok(word):
    """Латинское слово как отдельный токен, а не часть другого слова."""
    return r"(?<![a-z0-9])" + word + r"(?![a-z0-9])"


def connection_type(t):
    if re.search(r"радиоканал|2[.,]4\s?g", t):
        return "radio"
    if re.search(r"беспровод|bluetooth|блютуз|блютус|" + _tok("bt") + "|" + _tok("tws"), t):
        return "bluetooth"
    if "проводн" in t:  # 'беспроводные' уже обработаны выше
        return "wired"
    return None


def form_factor(t):
    # Порядок важен: явные слова сильнее слабых ('накладные большие' = накладные).
    if "накладн" in t:
        return "on_ear"
    if re.search(r"полноразмер|мониторн", t):
        return "over_ear"
    # 'tws' считаем вкладышами: допущение, не все TWS-модели вкладные
    if re.search(r"вкладыш|внутриканал|вакуумн|капельк|" + _tok("tws"), t):
        return "in_ear"
    # слабый признак: 'большие наушники'
    if "больш" in t:
        return "over_ear"
    # 'клипсы', 'открытые' и другое в три значения ТЗ не укладывается -> None
    return None


def anc(t):
    if re.search(r"без\s+(?:активного\s+)?шумоподавл|без\s+" + _tok("anc"), t):
        return False
    if re.search(_tok("anc") + r"|активн\w*\s+(?:шумоподавл|подавлени\w*\s+шум)|active\s+noise", t):
        return True
    # ТЗ: 'шумоподавление микрофона' не равно ANC. Если в названии есть и микрофон, не решаем.
    if "шумоподавл" in t and not re.search(r"микрофон|" + _tok("mic"), t):
        return True
    return None


def microphone(t):
    if re.search(r"без\s+микрофон", t):
        return False
    if "микрофон" in t or re.search(_tok("mic"), t):
        return True
    return None


def battery_hours(t):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:часов|часа|час|ч|hours?|h)(?![a-zа-я])", t)
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return value if 0 < value < 1000 else None  # NUMERIC(4,1) вмещает до 999.9


def extract_features(name):
    """Возвращает словарь признаков для столбцов products. Неизвестное - None."""
    t = name.lower().replace("ё", "е")
    return {
        "connection_type": connection_type(t),
        "form_factor": form_factor(t),
        "anc": anc(t),
        "microphone": microphone(t),
        "battery_hours": battery_hours(t),
    }


# ---------- признаки из окна «Характеристики и описание» на карточке WB ----------
# Формат текста: строка с названием поля, следующая непустая строка - значение.
# Заголовки разделов ('Питание', 'Связь') без значения нас не интересуют: мы ищем
# только известные названия полей.
SPEC_LABELS = {
    "вид наушников",
    "тип крепления наушников",
    "тип подключения",
    "беспроводные интерфейсы",
    "время работы от аккумулятора, до",
    "доп. опции наушников",
}


def parse_specs(text):
    """Текст окна характеристик -> словарь {название поля в нижнем регистре: значение}."""
    lines = [ln.strip() for ln in text.replace("\xa0", " ").split("\n") if ln.strip()]
    specs = {}
    for i, line in enumerate(lines[:-1]):
        key = line.lower()
        if key in SPEC_LABELS and key not in specs:
            specs[key] = lines[i + 1].lower().replace("ё", "е")
    return specs


def extract_from_specs(text):
    """Признаки из характеристик продавца. Поля нет в карточке -> None, как и везде."""
    sp = parse_specs(text)
    result = {"connection_type": None, "form_factor": None, "anc": None,
              "microphone": None, "battery_hours": None}

    link = " ".join(sp.get(k, "") for k in ("тип подключения", "беспроводные интерфейсы", "вид наушников"))
    if link:
        result["connection_type"] = connection_type(link)

    for key in ("вид наушников", "тип крепления наушников"):
        value = sp.get(key, "")
        ff = form_factor(value)
        if ff is None and re.search(r"ушной раковин|earbud", value):
            ff = "in_ear"  # 'в ушной раковине' и 'Вкладыши (Earbuds)' - это вкладыши
        if ff is not None:
            result["form_factor"] = ff
            break

    options = sp.get("доп. опции наушников", "")
    if options:
        # В списке опций самих наушников 'шумоподавление' относится к наушникам,
        # а не к микрофону. Исключение: явно написано 'шумоподавление микрофона'.
        if re.search(r"шумоподавлени\w*\s+микрофон", options):
            pass
        elif re.search(r"шумоподавл|подавлени\w*\s+шум", options) and "без" not in options:
            result["anc"] = True
        if "микрофон" in options and not re.search(r"без\s+микрофон", options):
            result["microphone"] = True
        # Если опции перечислены, а микрофона там нет, это не значит 'микрофона нет':
        # продавцы часто перечисляют не всё. Поэтому здесь None, а не False.

    result["battery_hours"] = battery_hours(sp.get("время работы от аккумулятора, до", ""))
    return result


def extract_all(name, specs_text=None):
    """Название + (если есть) характеристики. Характеристики продавца сильнее названия."""
    title = extract_features(name)
    if not specs_text:
        return title
    spec = extract_from_specs(specs_text)
    return {k: (spec[k] if spec[k] is not None else title[k]) for k in title}
