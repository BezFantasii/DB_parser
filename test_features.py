import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from features import extract_all, extract_features, extract_from_specs


class FeatureTests(unittest.TestCase):
    def check(self, name, **expected):
        got = extract_features(name)
        for key in ("connection_type", "form_factor", "anc", "microphone", "battery_hours"):
            self.assertEqual(got[key], expected.get(key), "%s: %s" % (name, key))

    def test_wireless_only(self):
        self.check("Беспроводные наушники CMF by Nothing Buds 2a темно-серый", connection_type="bluetooth")

    def test_wireless_with_microphone(self):
        self.check("Наушники беспроводные с микрофоном для андроид и iphone",
                   connection_type="bluetooth", microphone=True)

    def test_not_headphones(self):
        self.check("Наушники меховые зимние утепленные")

    def test_anc_by_name(self):
        self.check("Наушники беспроводные AirPods 4 ANC для iPhone и Android",
                   connection_type="bluetooth", anc=True)

    def test_big_is_over_ear(self):
        self.check("Беспроводные наушники большие", connection_type="bluetooth", form_factor="over_ear")

    def test_on_ear_beats_big(self):
        self.check("Беспроводные наушники накладные большие W35",
                   connection_type="bluetooth", form_factor="on_ear")

    def test_bt_token(self):
        self.check("Tune 520 BT Наушники накладные беспроводные Оригинал",
                   connection_type="bluetooth", form_factor="on_ear")

    def test_clips_not_in_domain(self):
        self.check("Наушники беспроводные клипсы для айфона и андроид", connection_type="bluetooth")

    def test_anc_and_mic(self):
        self.check("Наушники беспроводные с ANC ,микрофоном для андроид и iphone",
                   connection_type="bluetooth", anc=True, microphone=True)

    def test_noise_cancelling_without_mic_in_title(self):
        self.check("Наушники беспроводные BP1 NC с шумоподавлением, белые",
                   connection_type="bluetooth", anc=True)

    def test_noise_cancelling_ambiguous_with_mic(self):
        # ТЗ: шумоподавление микрофона не равно ANC, поэтому anc остаётся неизвестным
        self.check("Наушники беспроводные с шумоподавлением и микрофоном",
                   connection_type="bluetooth", microphone=True)

    def test_wired_in_ear(self):
        self.check("Наушники проводные вкладыши с микрофоном",
                   connection_type="wired", form_factor="in_ear", microphone=True)

    def test_wireless_is_not_wired(self):
        self.assertEqual(extract_features("Беспроводные наушники")["connection_type"], "bluetooth")

    def test_explicit_negation(self):
        self.check("Наушники без микрофона и без шумоподавления", microphone=False, anc=False)

    def test_tws_and_battery(self):
        self.check("Наушники TWS 40 часов работы",
                   connection_type="bluetooth", form_factor="in_ear", battery_hours=40.0)

    def test_hours_not_confused_with_words(self):
        self.assertIsNone(extract_features("Наушники 2 чехла в комплекте")["battery_hours"])


# Реальные тексты окна «Характеристики и описание» (WB), без блока описания.
SPECS_W35 = 'Характеристики и описание\nОсновная информация\nЦвет\nсеребристый\nОбщие характеристики\nМодель\nW35\n\n\nВид наушников\nнакладные\nПитание\nЕмкость аккумулятора\n400 мА*ч\n\n\nВремя зарядки\n2 часа\n\n\nВремя работы от аккумулятора, до\n40 ч\nИнтерфейсы и разъемы\nРазъем подключения наушников\nJack 3.5 mm; USB Type-C\nТехнические особенности\nРадиус беспроводной связи\n10 метров\nМатериалы\nМатериал корпуса\nпластик\nДополнительная информация\nСовместимость\nApple IPhone; Android; ПК\n\n\nТип крепления наушников\nоголовье\n\n\nТип акустического оформления\nзакрытые\n\n\nСтрана производства\nКитай\n\n\nКомплектация\nнаушники hoco\nГабариты\nДлина упаковки\n24 см\n\n\nВысота упаковки\n5 см\n\n\nШирина упаковки\n21 см\n\n\nВес с упаковкой (кг)\n0.328 кг\n\n\nВес товара без упаковки (г)\n193 г'
SPECS_NEO = 'Характеристики и описание\nОсновная информация\nЦвет\nчерный\nОбщие характеристики\nМодель\nHUAWEI FreeBuds Neo\n\n\nВид наушников\nВкладыши (Earbuds)\n\n\nТип подключения\nбеспроводное\n\n\nСтепень пылевлагозащиты\nIP 55\n\n\nГарантийный срок\n1 год\nПитание\nВремя зарядки\n70 минут\n\n\nВремя работы от аккумулятора, до\n40 ч\nСвязь\nБеспроводные интерфейсы\nBluetooth 6.0\nИнтерфейсы и разъемы\nРазъем подключения наушников\nUSB Type-C\nТехнические особенности\nДиаметр мембраны\n11 мм\nАкустическая система\nМинимальная воспроизводимая частота\n20 Гц\n\n\nМаксимальная воспроизводимая частота\n40000 Гц\nМатериалы\nМатериал корпуса\nпластик\nДополнительная информация\nСовместимость\nAndroid; iOS; ПК\n\n\nТип крепления наушников\nв ушной раковине\n\n\nТип акустического оформления\nзакрытые\n\n\nДоп. опции наушников\nшумоподавление; регулятор громкости; микрофон\n\n\nСтрана производства\nКитай\n\n\nКомплектация\nНаушники; зарядный чехол; насадки; Краткое руководство пользователя; гарантийный талон\nГабариты\nДлина упаковки\n10 см\n\n\nВысота упаковки\n5 см\n\n\nШирина упаковки\n10 см\n\n\nВес с упаковкой (кг)\n0.2 кг\n\n\nВес товара без упаковки (г)\n42 г'
SPECS_A6 = 'Характеристики и описание\nОсновная информация\nЦвет\nчерный; серый\nОбщие характеристики\nМодель\nбеспроводные наушники A6\n\n\nВид наушников\nв ушной раковине\n\n\nТип подключения\nбеспроводные наушники; Беспроводная блютуз гарнитура с микрофоном\n\n\nСтепень пылевлагозащиты\nIPX5\n\n\nГарантийный срок\n1 год\nПитание\nЕмкость аккумулятора\n400 мА*ч\n\n\nВремя зарядки\n1 час\n\n\nВремя работы от аккумулятора, до\n8 ч\n\n\nДлина кабеля (м)\n0.25\nСвязь\nБеспроводные интерфейсы\nBluetooth 5.3; Bluetooth; Bluetooth 5.4; блютуз\nТехнические особенности\nЧувствительность\n96 дБ\n\n\nРадиус беспроводной связи\n10 метров\n\n\nДиаметр мембраны\n13 мм\nАкустическая система\nМинимальная воспроизводимая частота\n20 Гц\n\n\nМаксимальная воспроизводимая частота\n20000 Гц\nМатериалы\nМатериал корпуса\nпластик\nДополнительная информация\nСовместимость\nВсе устройства; Apple; Android; SAMSUNG; Honor; Xiaomi; Все устройства\n\n\nТип крепления наушников\nбеспроводное\n\n\nТип акустического оформления\nзакрытые\n\n\nДоп. опции наушников\nмикрофон; улучшенное звучание; активное шумоподавление\nГабариты\nДлина упаковки\n13 см\n\n\nВысота упаковки\n4 см\n\n\nШирина упаковки\n10 см\n\n\nВес с упаковкой (кг)\n0.137 кг\n\n\nВес товара без упаковки (г)\n42.4 г'


class SpecsTests(unittest.TestCase):
    def test_w35_on_ear_and_battery(self):
        got = extract_from_specs(SPECS_W35)
        self.assertEqual(got["form_factor"], "on_ear")
        self.assertEqual(got["battery_hours"], 40.0)
        # у W35 нет полей про подключение и опции: неизвестное остаётся None
        self.assertIsNone(got["connection_type"])
        self.assertIsNone(got["anc"])
        self.assertIsNone(got["microphone"])

    def test_neo_earbuds_anc_mic(self):
        got = extract_from_specs(SPECS_NEO)
        self.assertEqual(got, {"connection_type": "bluetooth", "form_factor": "in_ear",
                               "anc": True, "microphone": True, "battery_hours": 40.0})

    def test_a6_ear_canal_wording(self):
        got = extract_from_specs(SPECS_A6)
        self.assertEqual(got, {"connection_type": "bluetooth", "form_factor": "in_ear",
                               "anc": True, "microphone": True, "battery_hours": 8.0})

    def test_specs_fill_what_title_lacks(self):
        got = extract_all("Беспроводные наушники FreeBuds Neo Космический черный", SPECS_NEO)
        self.assertEqual(got["form_factor"], "in_ear")  # в названии формы нет
        self.assertIs(got["anc"], True)

    def test_title_used_when_specs_silent(self):
        got = extract_all("Беспроводные накладные наушники большие W35", SPECS_W35)
        self.assertEqual(got["connection_type"], "bluetooth")  # из названия
        self.assertEqual(got["form_factor"], "on_ear")

    def test_no_specs_equals_title_only(self):
        name = "Наушники беспроводные с микрофоном"
        self.assertEqual(extract_all(name, None), extract_features(name))

    def test_listed_options_without_mic_is_not_false(self):
        text = "Доп. опции наушников\nрегулятор громкости\n"
        self.assertIsNone(extract_from_specs(text)["microphone"])


# Ещё три реальных карточки WB (проблемные случаи).
SPECS_WIRED_LIAR = 'Характеристики и описание\nОсновная информация\nЦвет\nбелый\nОбщие характеристики\nМодель\ntype-c\n\n\nТип подключения\nпроводные\n\n\nГарантийный срок\n1 месяц\nПитание\nДлина кабеля, м\n1.1 м\nИнтерфейсы и разъемы\nРазъем подключения наушников\nUSB Type-C\nТехнические особенности\nЧувствительность\n111 дБ\nАкустическая система\nМинимальная воспроизводимая частота\n20 Гц\n\n\nМаксимальная воспроизводимая частота\n20000 Гц\nМатериалы\nМатериал корпуса\nпластик\nДополнительная информация\nСовместимость\nсмартфон Android; Honor; Xiaomi; SAMSUNG; iphone 15; На все устройства разъемом Type-C\n\n\nТип крепления наушников\nв ушной раковине; вкладыши\n\n\nДоп. опции наушников\nмикрофон; регулятор громкости\n\n\nСтрана производства\nКитай\n\n\nКомплектация\nнаушники, коробка.\nГабариты\nДлина упаковки\n9 см\n\n\nВысота упаковки\n3 см\n\n\nШирина упаковки\n8 см\n\n\nВес с упаковкой (кг)\n0.04 кг'   # в названии 'беспроводные Airpods', в характеристиках 'проводные'
SPECS_STUDIO = 'Характеристики и описание\nОсновная информация\nЦвет\nчерный\nПитание\nДлина кабеля (м)\n1,2 м; 1.2 м; 3 м\nОбщие характеристики\nВид наушников\nпроводные накладные\n\n\nМодель\nONEODIO Studio Pro 10 black\n\n\nГарантийный срок\n1 год\nТехнические особенности\nДиаметр мембраны\n50 мм\n\n\nЧувствительность\n110 дБ\nИнтерфейсы и разъемы\nРазъем подключения наушников\n3,5 мм; 6,3 мм\nМатериалы\nМатериал корпуса\nпластик\nАкустическая система\nМаксимальная воспроизводимая частота\n40000 Гц\n\n\nМинимальная воспроизводимая частота\n20 Гц\n\n\nИмпеданс\n32 Ом\nДополнительная информация\nТип акустического оформления\nзакрытые\n\n\nТип крепления наушников\nс оголовьем; с креплением на ушах; с затылочной дужкой\n\n\nДоп. опции наушников\nскладная конструкция; микрофон\n\n\nСрок эксплуатации\n2 года\n\n\nСовместимость\nAndroid; iOS; windows\n\n\nСтрана производства\nКитай\n\n\nКомплектация\nНаушники; инструкция; чехол; AUX кабель 2 шт\nГабариты\nВес с упаковкой (кг)\n0.419 кг\n\n\nВес товара без упаковки (г)\n240 г'       # 'Вид наушников: проводные накладные'
SPECS_FREECLIP = 'Характеристики и описание\nОсновная информация\nЦвет\nсиреневый; фиолетовый\nОбщие характеристики\nМодель\nHuawei FreeClip 2\n\n\nТип подключения\nбеспроводное\n\n\nСтепень пылевлагозащиты\nIP57\n\n\nГарантийный срок\n1 год\nПитание\nЕмкость аккумулятора\n537 мА*ч (кейса), 60 мА*ч(наушников)\n\n\nВремя зарядки\nТолько зарядный чехол: около 50 минут; Зарядка наушников через чехол: около 40 минут; Наушники и зарядный чехол: около 60 минут\n\n\nВремя работы от аккумулятора, до\n9ч; 38ч с кейсом\nСвязь\nБеспроводные интерфейсы\nBluetooth\nТехнические особенности\nРадиус беспроводной связи\n10 метров\n\n\nДиаметр мембраны\n10.8 мм\nАкустическая система\nМинимальная воспроизводимая частота\n20 Гц\n\n\nМаксимальная воспроизводимая частота\n20000 Гц\nМатериалы\nМатериал корпуса\nпластик; силикон\nДополнительная информация\nСовместимость\nAndroid, iOS\n\n\nТип крепления наушников\nклипса (на ухе)\n\n\nТип акустического оформления\nоткрытые\n\n\nДоп. опции наушников\nвлагозащищенный корпус; Система активного подавления шума; управление воспроизведением\n\n\nСтрана производства\nКитай\n\n\nКомплектация\nНаушники; футляр; Документация\nГабариты\nДлина упаковки\n12 см\n\n\nВысота упаковки\n4 см\n\n\nШирина упаковки\n10 см\n\n\nВес с упаковкой (кг)\n0.2 кг\n\n\nВес товара без упаковки (г)\n48 г'     # клипсы: форм-фактор вне ТЗ; 'Система активного подавления шума'


class RealCardTests(unittest.TestCase):
    def test_specs_beat_misleading_title(self):
        got = extract_all("Наушники беспроводные Airpods Pro 3 для iPhone Android", SPECS_WIRED_LIAR)
        self.assertEqual(got["connection_type"], "wired")
        self.assertEqual(got["form_factor"], "in_ear")
        self.assertIs(got["microphone"], True)

    def test_connection_from_kind_field(self):
        got = extract_from_specs(SPECS_STUDIO)
        self.assertEqual(got["connection_type"], "wired")
        self.assertEqual(got["form_factor"], "on_ear")
        self.assertIs(got["microphone"], True)

    def test_clip_form_stays_none_but_anc_found(self):
        got = extract_from_specs(SPECS_FREECLIP)
        self.assertIsNone(got["form_factor"])
        self.assertIs(got["anc"], True)
        self.assertEqual(got["connection_type"], "bluetooth")
        self.assertEqual(got["battery_hours"], 9.0)  # первое число: время работы самих наушников


if __name__ == "__main__":
    unittest.main()
