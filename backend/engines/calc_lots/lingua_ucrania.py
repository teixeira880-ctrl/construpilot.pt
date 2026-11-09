"""Tradução da nota Ucrânia (calc_lots.ucrania) para português — substituição de fragmentos, do mais longo para o mais curto.
As normas mantêm a referência oficial transliterada (ДБН → DBN, ДСТУ → DSTU)."""

PT = {
    # títulos e secções
    "Україна / Ukraine — ": "Ucrânia — ",
    "Теплотехніка, тепловтрати, навантаження та несучі конструкції · ДБН / ДСТУ · ": "Térmica, perdas, ações e estrutura · normas DBN / DSTU · ",
    "Розрахунок за нормами України · Calculation to Ukrainian norms": "Cálculo segundo as normas ucranianas",
    "1. Кліматичні параметри": "1. Parâmetros climáticos",
    "2. Теплотехнічний розрахунок огороджувальних конструкцій": "2. Cálculo térmico da envolvente",
    "3. Розрахункові тепловтрати та потреба в теплі": "3. Perdas térmicas de projeto e necessidades de aquecimento",
    "4. Снігове та вітрове навантаження (ДБН В.1.2-2:2006)": "4. Ações da neve e do vento (DBN V.1.2-2:2006)",
    "5. Несучі конструкції (ДСТУ-Н Б EN 1992 / 1995 / 1997)": "5. Estrutura (DSTU-N B EN 1992 / 1995 / 1997)",
    "6. Кошторисна оцінка (несучі конструкції, оболонка, опалення) з ПДВ 20 %": "6. Estimativa orçamental (estrutura, envolvente, aquecimento) com IVA ucraniano 20 %",
    "Автоматичні коригування перерізів": "Secções ajustadas automaticamente",
    "Припущення / для перевірки": "Hipóteses / a validar",
    "Візуалізації 3D / 3D views": "Visualizações 3D",
    "Обкладинка / Cover": "Capa", "Зміст / Contents": "Índice",
    "ConstruPilot — розрахунок детермінованими модулями; підлягає перевірці відповідальним проєктувальником.":
        "ConstruPilot — cálculo por motores determinísticos; a validar pelo projetista responsável.",
    "Попередній розрахунок детермінованими модулями — підлягає перевірці відповідальним інженером. / Preliminary design — to be checked by the responsible engineer.":
        "Pré-dimensionamento por motores determinísticos — a validar pelo engenheiro responsável.",
    # KPIs
    "Місто / City": "Cidade", "θe розрахункова / design": "θe de projeto", "θe розрахункова": "θe de projeto",
    "Тепловтрати / heat loss": "Perdas térmicas", "Потреба в теплі / heating need": "Necessidade de aquecimento",
    "Огородження ДБН В.2.6-31": "Envolvente DBN V.2.6-31", "Оболонка ДБН В.2.6-31": "Envolvente DBN V.2.6-31",
    "Сніг Sm / snow": "Neve Sm", "Конструкції / structure": "Estrutura", "Вартість з ПДВ / incl. VAT": "Custo com IVA",
    "≈ EUR з ПДВ": "≈ EUR com IVA", "€ (курс НБУ)": "€ (câmbio BNU)", "На 1 м² опалюваної площі": "Por m² de área aquecida", "На 1 м²": "Por m²",
    "Без ПДВ / excl. VAT": "Sem IVA", "ПДВ 20 % / VAT": "IVA 20 %", "З ПДВ / incl. VAT": "Com IVA",
    "грн/м² з ПДВ": "UAH/m² com IVA", "млн грн": "milhões UAH", " млн": " M", " тис. €": " mil €", " тис.": " mil", "кВт / kW": "kW",
    "кВт·год/м² рік": "kWh/m²·ano", "посилити": "reforçar", "перевірити": "verificar", "Rq,min зона ": "Rq,min zona ",
    " ел., ": " elem., ", " коригув.": " ajustes", "EN 12831 (спрощено)": "EN 12831 (simplificado)",
    # clima
    "Параметр": "Parâmetro", "Значення": "Valor", "Джерело ціни": "Fonte do preço", "Джерело": "Fonte",
    "Розрахункова температура зовнішнього повітря θe": "Temperatura exterior de projeto θe",
    "ДСТУ-Н Б В.1.1-27:2010 (п'ятиденка 0,92)": "DSTU-N B V.1.1-27:2010 (5 dias mais frios, 0,92)",
    "Градусо-доби опалювального періоду": "Graus-dia da estação de aquecimento", "довідково (база 18 °C)": "referência (base 18 °C)",
    "Температурна зона": "Zona térmica", "Внутрішня температура / вологість": "Temperatura / humidade interior",
    "Характеристичне снігове навантаження S0": "Neve característica S0", "Характеристичний тиск вітру W0": "Pressão característica do vento W0",
    # envolvente
    "Опір теплопередачі R∑ = Rsi + Σ(d/λ) + Rse порівнюється з мінімально допустимим Rq,min (ДБН В.2.6-31:2021, табл. 1); ":
        "A resistência térmica R∑ = Rsi + Σ(d/λ) + Rse é comparada com o mínimo admissível Rq,min (DBN V.2.6-31:2021, quadro 1); ",
    "перевіряються перепад температур Δθ (табл. 3) і відсутність конденсації в товщі конструкції.":
        "verificam-se a diferença de temperatura Δθ (quadro 3) e a ausência de condensação no interior do elemento.",
    "Конструкція": "Elemento", "R∑, м²·К/Вт": "R∑, m²·K/W", "U, Вт/(м²·К)": "U, W/(m²·K)", "Статус": "Estado",
    "R∑ / Rq,min (≥ 1,0 — відповідає)": "R∑ / Rq,min (≥ 1,0 — conforme)", "Шар (зсередини назовні)": "Camada (do interior para o exterior)",
    "d, мм": "d, mm", "λ, Вт/(м·К)": "λ, W/(m·K)", "R, м²·К/Вт": "R, m²·K/W", "Sd, м": "Sd, m",
    "Приведений опір з тепловими містками (ψ, χ)": "Resistência com pontes térmicas (ψ, χ)", "Rпр = 1/Uеф": "Ref = 1/Uef", "Uеф": "Uef",
    "Конденсація в товщі (метод Глейзера, θ = ": "Condensação interna (método de Glaser, θ = ", "середня січня": "média de janeiro",
    "розрахункова θe": "θe de projeto", "немає зони конденсації": "sem zona de condensação", "немає": "nenhuma",
    "можлива конденсація: ": "condensação possível: ", "г/м² на добу": "g/m² por dia", "перевірити вологісний режим за ДСТУ Б В.2.6-189": "verificar o balanço de humidade (DSTU B V.2.6-189)",
    "після ": "após ",
    # perdas
    "Розподіл тепловтрат, кВт": "Repartição das perdas, kW", "Теплові містки": "Pontes térmicas", "Вентиляція": "Ventilação",
    "Рекомендована потужність теплогенератора ≈ ": "Potência recomendada do gerador ≈ ", " Річна потреба ≈ ": " Necessidade anual ≈ ",
    "кВт·год/м² на рік": "kWh/m² por ano", "кВт·год": "kWh", " при θe = ": " para θe = ", "Вт/К": "W/K",
    # neve e vento
    "Величина": "Grandeza", "S0 (характеристичне)": "S0 (característico)", "γfm (термін експлуатації)": "γfm (período de vida útil)",
    "μ (форма покрівлі)": "μ (forma da cobertura)", "Calt (висота)": "Calt (altitude)", "Sm = γfm·S0·μ·Calt (граничне)": "Sm = γfm·S0·μ·Calt (valor último)",
    "Se = 0,49·S0·C (експлуатаційне)": "Se = 0,49·S0·C (valor de serviço)", "W0 (характеристичне)": "W0 (característico)",
    "Wm ≈ γfm·W0·C (C = 0,7, будинок до 10 м)": "Wm ≈ γfm·W0·C (C = 0,7, edifício até 10 m)",
    # estrutura
    "Перевірено ": "Verificados ", " елементів; снігове навантаження на покриття Sm = ": " elementos; neve na cobertura Sm = ",
    ". Робочі креслення ГО-01…ГО-05 (масштаб ": ". Planos de execução GO-01… (escala ", ") додані до записки.": ") anexos à nota.",
    "Прийнятий переріз": "Secção adotada", "Тип": "Tipo", "Марка": "Ref.", "Викор.": "Taxa",
    "НЕ відповідає": "NÃO conforme", "відповідає": "conforme", "OK ✓": "OK ✓",
    # orçamento
    "Позиція": "Artigo", "Од.": "Un.", "К-сть": "Quant.", "Ціна, грн": "Preço, UAH", "Сума, грн": "Total, UAH",
    "Разом без ПДВ": "Total sem IVA", "РАЗОМ З ПДВ": "TOTAL COM IVA", "(ПКУ, ст. 193)": "(Código Fiscal da Ucrânia, art. 193)",
    "Структура вартості, млн грн без ПДВ": "Estrutura do custo, milhões UAH sem IVA",
    "Кількості обчислені з розрахункової моделі (бетон, арматура за питомими витратами, об'єм CLT, площі оболонки). Ціни без ПДВ: ":
        "Quantidades calculadas a partir do modelo (betão, armaduras por rácio, volume de CLT, áreas da envolvente). Preços sem IVA: ",
    "«✓» — опубліковані ціни постачальників із датою, «≈» — орієнтири ConstruPilot, які слід замінити комерційними пропозиціями ":
        "«✓» — preços publicados por fornecedores, com data; «≈» — referências ConstruPilot a substituir por propostas comerciais ",
    "(зокрема ціну Rezult CLT). Не включено: внутрішнє оздоблення, інженерні мережі (крім теплового насоса), благоустрій, проєктні роботи.":
        "(em particular o preço Rezult CLT). Não incluído: acabamentos interiores, redes (exceto a bomba de calor), arranjos exteriores, projeto.",
    "Фундаменти й підвал (з/б)": "Fundações e cave (BA)", "Каркас Rezult CLT": "Estrutura Rezult CLT", "Оболонка (фасад, покрівля, вікна)": "Envolvente (fachada, cobertura, vãos)",
    "Опалення": "Aquecimento",
    "Розробка ґрунту котлована з вивезенням": "Escavação da cave com transporte a vazadouro",
    "Бетон C20/25 (B25) з доставкою": "Betão C20/25 (B25) com entrega", "Бетон C25/30 (B30) з доставкою": "Betão C25/30 (B30) com entrega",
    "Арматура A500C Ø12–16": "Aço A500C Ø12–16", "Бетонні роботи (опалубка, армування, укладання)": "Mão de obra de betão (cofragem, armação, betonagem)",
    "Гідроізоляція і утеплення XPS стін підвалу": "Impermeabilização e XPS das paredes da cave",
    "Панелі Rezult CLT (виготовлення, ЧПК-обробка, доставка)": "Painéis Rezult CLT (fabrico, corte CNC, transporte)",
    "Монтаж CLT (кран, кріплення, ущільнення стиків)": "Montagem CLT (grua, ligadores, juntas)",
    "Фасадна система: мінвата + вітрозахист + оздоблення": "Fachada: lã mineral + barreira de vento + acabamento",
    "Плоска покрівля: пароізоляція, XPS, ухил, мембрана ПВХ, гравій": "Cobertura plana: pára-vapor, XPS, pendente, membrana PVC, seixo",
    "Вікна та двері тераси (енергоефективні, з монтажем)": "Janelas e portas do terraço (eficientes, com montagem)",
    "Тепловий насос повітря–вода з монтажем": "Bomba de calor ar-água com instalação",
    "dbn.co.ua, Київ 2026: 2 900–3 350 грн/м³ з доставкою (середнє)": "dbn.co.ua, Kyiv 2026: 2 900–3 350 UAH/m³ com entrega (média)",
    "dbn.co.ua, Київ 2026: 3 100–3 650 грн/м³ з доставкою (середнє)": "dbn.co.ua, Kyiv 2026: 3 100–3 650 UAH/m³ com entrega (média)",
    "Метінвест-СМЦ Київ, 09.11.2026: 50 000 грн/т": "Metinvest-SMC Kyiv, 09.11.2026: 50 000 UAH/t",
    "ринок ЄС ≥ 500 €/м³ (Holzkurier, 2025) + обробка й доставка → 650 €/м³; запитати ціну Rezult":
        "mercado UE ≥ 500 €/m³ (Holzkurier, 2025) + corte e transporte → 650 €/m³; pedir preço à Rezult",
    "орієнтир ConstruPilot": "referência ConstruPilot", "ціна користувача": "preço do utilizador", "НБУ ": "BNU ", "грн/€": "UAH/€",
    # hipóteses
    "кліматичні дані обласного центру (ДСТУ-Н Б В.1.1-27:2010, ДБН В.1.2-2:2006 дод. Е) — для конкретної ділянки перевірити за чинними нормами":
        "dados climáticos da capital de região (DSTU-N B V.1.1-27:2010, DBN V.1.2-2:2006 anexo E) — confirmar para o terreno concreto",
    "температурна зона за картою дод. А ДБН В.2.6-31:2021 — перевірити для конкретного населеного пункту":
        "zona térmica pelo mapa do anexo A do DBN V.2.6-31:2021 — confirmar para a localidade",
    "розрахункові λ матеріалів — довідкові (умови експлуатації Б); у проєкті використовувати значення з декларацій виробників / ДСТУ Б В.2.6-189":
        "λ de cálculo dos materiais de referência (condições B); no projeto usar os valores das declarações dos fabricantes / DSTU B V.2.6-189",
    "; перевірка конденсації методом Глейзера при розрахунковій θe (консервативно)": "; condensação verificada pelo método de Glaser",
    "теплові містки: надбавка ΔU = ": "pontes térmicas: acréscimo ΔU = ", " до всієї оболонки (спрощено); вентиляція ": " a toda a envolvente (simplificado); ventilação ",
    ", рекуперація η = ": ", recuperação η = ", "год⁻¹": "h⁻¹",
    "річна потреба в теплі = (H_T + H_V) × ГД × 24 — без сонячних і внутрішніх теплонадходжень (верхня оцінка); ":
        "necessidade anual = (H_T + H_V) × GD × 24 — sem ganhos solares e internos (estimativa por excesso); ",
    "енергетичний клас визначається за Методикою (наказ Мінрегіону) та ДСТУ EN ISO 52016":
        "a classe energética é determinada pela Metodologia oficial (Ministério do Desenvolvimento Regional) e DSTU EN ISO 52016",
    "перерізи несучих конструкцій — попередній розрахунок, підлягає перевірці ": "secções estruturais — pré-dimensionamento, a validar pelo ",
    "інженером-конструктором; ДБН В.1.2-14 (надійність) і ДБН В.2.1-10 (основи)": "engenheiro de estruturas; DBN V.1.2-14 (fiabilidade) e DBN V.2.1-10 (fundações)",
    "Панелі ": "Painéis ", ": задекларовані значення за ": ": valores declarados na ", "f_R,k за рис. 3 ETA": "f_R,k da figura 3 da ETA",
    "обвуглювання": "carbonização", "; вібрацію, вузли, просторову стійкість, цілісність і теплоізоляцію при пожежі (E, I) тут не перевірено":
        "; vibração, ligações, estabilidade lateral, integridade e isolamento ao fogo (E, I) não verificados aqui",
    "Панель CLT (модуль bet_clt_ua)": "Painel CLT (motor bet_clt_ua)", "Панель CLT": "Painel CLT", "панель CLT": "painel CLT", " шарів": " camadas",
    "проліт": "vão", "викор.": "taxa", "стрічк. фундамент": "sapata contínua", "Стрічковий фундамент (на 1 м)": "Sapata contínua (por metro)",
    "З/б плита, армована у двох напрямках": "Laje de BA armada em duas direções", "з/б плита": "laje BA", "плита": "laje",
    # elementos / materiais
    "Зовнішня стіна": "Parede exterior", "Суміщене покриття": "Cobertura plana", "Горищне перекриття": "Esteira do desvão",
    "Перекриття над холодним підвалом / проїздом": "Pavimento sobre espaço não aquecido", "Вікна (світлопрозорі)": "Janelas",
    "Зенітні ліхтарі": "Claraboias", "Зовнішні двері": "Portas exteriores", "Підлога по ґрунту": "Pavimento térreo",
    "Вікна та двері тераси": "Janelas e portas do terraço", "Вікна (двокамерний склопакет)": "Janelas (vidro triplo)", "Вхідні двері": "Porta de entrada",
    "Стіна: ": "Parede: ", "Покрівля: ": "Cobertura: ", "Підлога над підвалом: ": "Pavimento sobre a cave: ", "Покриття: ": "Cobertura: ",
    "мінвата": "lã mineral", "легкий бетон": "betão leve", "з/б": "BA", "Гіпсокартон": "Gesso cartonado", "Панель CLT ": "Painel CLT ",
    "Пароізоляція бітумна з алюмінієвою фольгою (Sd ≈ 1500 м)": "Pára-vapor betuminoso com alumínio (Sd ≈ 1500 m)",
    "Пароізоляція (Sd ≥ 18 м)": "Pára-vapor (Sd ≥ 18 m)", "Вітрозахисна мембрана (Sd ≤ 0,2 м)": "Barreira de vento (Sd ≤ 0,2 m)",
    "Покрівельна мембрана ПВХ/ТПО": "Membrana de cobertura PVC/TPO", "Мінеральна вата (фасадна)": "Lã mineral (fachada)",
    "Мінеральна вата (покрівельна)": "Lã mineral (cobertura)", "Екструдований пінополістирол (XPS)": "Poliestireno extrudido (XPS)",
    "Пінополістирол (EPS)": "Poliestireno expandido (EPS)", "Поліізоціанурат (PIR)": "Poliisocianurato (PIR)", "Цементна стяжка": "Betonilha",
    "Залізобетон": "Betão armado", "Керамзитовий гравій": "Argila expandida", "Газобетон": "Betão celular", "Деревина (сосна)": "Madeira (pinho)",
    "Гіпсова штукатурка": "Estuque", "Тонкошарова фасадна штукатурка": "Reboco delgado", "Цементно-піщана штукатурка": "Reboco de cimento",
    # normas e unidades
    "ДБН В.": "DBN V.", "ДСТУ-Н Б В.": "DSTU-N B V.", "ДСТУ-Н Б EN": "DSTU-N B EN", "ДСТУ Б В.": "DSTU B V.", "ДСТУ EN": "DSTU EN",
    "табл. Б.2": "quadro B.2", "табл.": "quadro", "дод. А": "anexo A", "дод. Е": "anexo E", "(зона ": "(zona ", "зона ": "zona ",
    "м²·К/Вт": "m²·K/W", "Вт/(м²·К)": "W/(m²·K)", "кВт": "kW", "кПа": "kPa", " Па": " Pa", "м³": "m³", "м²": "m²", " мм": " mm", " грн": " UAH",
    "ПДВ": "IVA", "Україна": "Ucrânia", "тис.": "mil", "МПа": "MPa",
}
EXATO = {"т": "t", "грн": "UAH", "млн": "M", "кВт": "kW", "м": "m", "шт": "un."}
_ORD = sorted(PT, key=len, reverse=True)


def tr(s):
    if not isinstance(s, str):
        return s
    if s.strip() in EXATO:
        return EXATO[s.strip()]
    for k in _ORD:
        if k in s:
            s = s.replace(k, PT[k])
    return s


def deep(x):
    if isinstance(x, str):
        return tr(x)
    if isinstance(x, tuple):
        return tuple(deep(v) for v in x)
    if isinstance(x, list):
        return [deep(v) for v in x]
    if isinstance(x, dict):
        return {k: deep(v) for k, v in x.items()}
    return x


# ================================================================================================ inglês (dossier EN completo)
EN = {
    "Візуалізація 3D": "3D visualisation", "Загальний вигляд": "General view", "Вигляд з боку тераси": "Terrace side", "Вигляд з висоти": "Aerial view",
    "Згенеровано з моделі робочих креслень (Mitsuba 3, трасування шляхів, фізичне сонце й небо). Геометрія — за кресленнями; фасади, прорізи та озеленення — орієнтовні.":
        "Generated from the construction-drawing model (Mitsuba 3 path tracing, physical sun and sky). Geometry from the drawings; facades, openings and landscaping are indicative.",
    "Україна / Ukraine — ": "Ukraine — ",
    "Теплотехніка, тепловтрати, навантаження та несучі конструкції · ДБН / ДСТУ · ": "Thermal, heat loss, actions and structure · DBN / DSTU norms · ",
    "Розрахунок за нормами України · Calculation to Ukrainian norms": "Calculation to Ukrainian norms (DBN / DSTU)",
    "1. Кліматичні параметри": "1. Climate parameters",
    "2. Теплотехнічний розрахунок огороджувальних конструкцій": "2. Thermal design of the building envelope",
    "3. Розрахункові тепловтрати та потреба в теплі": "3. Design heat loss and heating demand",
    "4. Снігове та вітрове навантаження (ДБН В.1.2-2:2006)": "4. Snow and wind actions (DBN V.1.2-2:2006)",
    "5. Несучі конструкції (ДСТУ-Н Б EN 1992 / 1995 / 1997)": "5. Structure (DSTU-N B EN 1992 / 1995 / 1997)",
    "6. Кошторисна оцінка (несучі конструкції, оболонка, опалення) з ПДВ 20 %": "6. Cost estimate (structure, envelope, heating) incl. Ukrainian VAT 20 %",
    "Автоматичні коригування перерізів": "Automatic section adjustments", "Припущення / для перевірки": "Assumptions / to be confirmed",
    "Візуалізації 3D / 3D views": "3D visualisations", "Обкладинка / Cover": "Cover", "Зміст / Contents": "Contents",
    "ConstruPilot — розрахунок детермінованими модулями; підлягає перевірці відповідальним проєктувальником.":
        "ConstruPilot — deterministic engine calculation; to be checked by the responsible designer.",
    "Попередній розрахунок детермінованими модулями — підлягає перевірці відповідальним інженером. / Preliminary design — to be checked by the responsible engineer.":
        "Preliminary design by deterministic engines — to be checked by the responsible engineer.",
    "Summary (English)": "Summary",
    "Місто / City": "City", "θe розрахункова / design": "Design θe", "θe розрахункова": "Design θe", "Тепловтрати / heat loss": "Heat loss",
    "Потреба в теплі / heating need": "Heating demand", "Огородження ДБН В.2.6-31": "Envelope DBN V.2.6-31", "Оболонка ДБН В.2.6-31": "Envelope DBN V.2.6-31",
    "Сніг Sm / snow": "Snow Sm", "Конструкції / structure": "Structure", "Вартість з ПДВ / incl. VAT": "Cost incl. VAT", "≈ EUR з ПДВ": "≈ EUR incl. VAT",
    "€ (курс НБУ)": "€ (NBU rate)", "На 1 м² опалюваної площі": "Per m² heated floor area", "На 1 м²": "Per m²", "Без ПДВ / excl. VAT": "Excl. VAT",
    "ПДВ 20 % / VAT": "VAT 20 %", "З ПДВ / incl. VAT": "Incl. VAT", "грн/м² з ПДВ": "UAH/m² incl. VAT", "млн грн": "million UAH", " млн": " M",
    " тис. €": " k€", " тис.": " k", "кВт / kW": "kW", "кВт·год/м² рік": "kWh/m²·yr", "посилити": "upgrade", "перевірити": "check",
    "Rq,min зона ": "Rq,min zone ", " ел., ": " elem., ", " коригув.": " adjustments", "EN 12831 (спрощено)": "EN 12831 (simplified)",
    "Параметр": "Parameter", "Значення": "Value", "Джерело ціни": "Price source", "Джерело": "Source",
    "Розрахункова температура зовнішнього повітря θe": "Design outdoor temperature θe",
    "ДСТУ-Н Б В.1.1-27:2010 (п'ятиденка 0,92)": "DSTU-N B V.1.1-27:2010 (coldest 5 days, 0.92)",
    "Градусо-доби опалювального періоду": "Heating degree-days", "довідково (база 18 °C)": "reference (base 18 °C)", "Температурна зона": "Temperature zone",
    "Внутрішня температура / вологість": "Indoor temperature / humidity", "Характеристичне снігове навантаження S0": "Characteristic snow load S0",
    "Характеристичний тиск вітру W0": "Characteristic wind pressure W0",
    "Опір теплопередачі R∑ = Rsi + Σ(d/λ) + Rse порівнюється з мінімально допустимим Rq,min (ДБН В.2.6-31:2021, табл. 1); ":
        "The thermal resistance R∑ = Rsi + Σ(d/λ) + Rse is compared with the minimum Rq,min (DBN V.2.6-31:2021, table 1); ",
    "перевіряються перепад температур Δθ (табл. 3) і відсутність конденсації в товщі конструкції.":
        "the surface temperature difference Δθ (table 3) and interstitial condensation are also checked.",
    "Конструкція": "Element", "R∑, м²·К/Вт": "R∑, m²·K/W", "U, Вт/(м²·К)": "U, W/(m²·K)", "Статус": "Status",
    "R∑ / Rq,min (≥ 1,0 — відповідає)": "R∑ / Rq,min (≥ 1.0 — compliant)", "Шар (зсередини назовні)": "Layer (inside to outside)",
    "d, мм": "d, mm", "λ, Вт/(м·К)": "λ, W/(m·K)", "R, м²·К/Вт": "R, m²·K/W", "Sd, м": "Sd, m",
    "Приведений опір з тепловими містками (ψ, χ)": "Resistance incl. thermal bridges (ψ, χ)", "Rпр = 1/Uеф": "Reff = 1/Ueff", "Uеф": "Ueff",
    "Конденсація в товщі (метод Глейзера, θ = ": "Interstitial condensation (Glaser method, θ = ", "середня січня": "January mean",
    "розрахункова θe": "design θe", "немає зони конденсації": "no condensation zone", "немає": "none", "можлива конденсація: ": "possible condensation: ",
    "г/м² на добу": "g/m² per day", "перевірити вологісний режим за ДСТУ Б В.2.6-189": "check the moisture balance (DSTU B V.2.6-189)", "після ": "after ",
    "Розподіл тепловтрат, кВт": "Heat loss breakdown, kW", "Теплові містки": "Thermal bridges", "Вентиляція": "Ventilation",
    "Рекомендована потужність теплогенератора ≈ ": "Recommended heat generator ≈ ", " Річна потреба ≈ ": " Annual demand ≈ ",
    "кВт·год/м² на рік": "kWh/m² per year", "кВт·год": "kWh", " при θe = ": " at θe = ", "Вт/К": "W/K",
    "Величина": "Quantity", "S0 (характеристичне)": "S0 (characteristic)", "γfm (термін експлуатації)": "γfm (design working life)",
    "μ (форма покрівлі)": "μ (roof shape)", "Calt (висота)": "Calt (altitude)", "Sm = γfm·S0·μ·Calt (граничне)": "Sm = γfm·S0·μ·Calt (ultimate)",
    "Se = 0,49·S0·C (експлуатаційне)": "Se = 0.49·S0·C (serviceability)", "W0 (характеристичне)": "W0 (characteristic)",
    "Wm ≈ γfm·W0·C (C = 0,7, будинок до 10 м)": "Wm ≈ γfm·W0·C (C = 0.7, building up to 10 m)",
    "Перевірено ": "Checked: ", " елементів; снігове навантаження на покриття Sm = ": " elements; roof snow load Sm = ",
    ". Робочі креслення ГО-01…ГО-05 (масштаб ": ". Construction drawings GO-01… (scale ", ") додані до записки.": ") attached.",
    "Прийнятий переріз": "Adopted section", "Тип": "Type", "Марка": "Mark", "Викор.": "Util.", "НЕ відповідає": "NOT compliant", "відповідає": "compliant",
    "Позиція": "Item", "Од.": "Unit", "К-сть": "Qty", "Ціна, грн": "Rate, UAH", "Сума, грн": "Amount, UAH", "Разом без ПДВ": "Total excl. VAT",
    "РАЗОМ З ПДВ": "TOTAL INCL. VAT", "(ПКУ, ст. 193)": "(Tax Code of Ukraine, art. 193)", "Структура вартості, млн грн без ПДВ": "Cost breakdown, million UAH excl. VAT",
    "Кількості обчислені з розрахункової моделі (бетон, арматура за питомими витратами, об'єм CLT, площі оболонки). Ціни без ПДВ: ":
        "Quantities computed from the design model (concrete, rebar by ratio, CLT volume, envelope areas). Prices excl. VAT: ",
    "«✓» — опубліковані ціни постачальників із датою, «≈» — орієнтири ConstruPilot, які слід замінити комерційними пропозиціями ":
        "«✓» — published supplier prices with date; «≈» — ConstruPilot reference rates to be replaced by commercial quotes ",
    "(зокрема ціну Rezult CLT). Не включено: внутрішнє оздоблення, інженерні мережі (крім теплового насоса), благоустрій, проєктні роботи.":
        "(in particular the Rezult CLT price). Excluded: interior finishes, MEP networks (except the heat pump), external works, design fees.",
    "Фундаменти й підвал (з/б)": "Foundations and basement (RC)", "Каркас Rezult CLT": "Rezult CLT structure", "Оболонка (фасад, покрівля, вікна)": "Envelope (facade, roof, glazing)",
    "Опалення": "Heating", "Розробка ґрунту котлована з вивезенням": "Basement excavation incl. disposal",
    "Бетон C20/25 (B25) з доставкою": "Concrete C20/25 (B25) delivered", "Бетон C25/30 (B30) з доставкою": "Concrete C25/30 (B30) delivered",
    "Арматура A500C Ø12–16": "Rebar A500C Ø12–16", "Бетонні роботи (опалубка, армування, укладання)": "Concrete works (formwork, fixing, pouring)",
    "Гідроізоляція і утеплення XPS стін підвалу": "Basement waterproofing and XPS", "Панелі Rezult CLT (виготовлення, ЧПК-обробка, доставка)": "Rezult CLT panels (manufacture, CNC, delivery)",
    "Монтаж CLT (кран, кріплення, ущільнення стиків)": "CLT erection (crane, fasteners, joint sealing)",
    "Фасадна система: мінвата + вітрозахист + оздоблення": "Facade system: mineral wool + wind barrier + finish",
    "Плоска покрівля: пароізоляція, XPS, ухил, мембрана ПВХ, гравій": "Flat roof: vapour barrier, XPS, falls, PVC membrane, gravel",
    "Вікна та двері тераси (енергоефективні, з монтажем)": "Windows and terrace doors (energy-efficient, installed)",
    "Тепловий насос повітря–вода з монтажем": "Air-to-water heat pump, installed",
    "dbn.co.ua, Київ 2026: 2 900–3 350 грн/м³ з доставкою (середнє)": "dbn.co.ua, Kyiv 2026: 2,900–3,350 UAH/m³ delivered (mean)",
    "dbn.co.ua, Київ 2026: 3 100–3 650 грн/м³ з доставкою (середнє)": "dbn.co.ua, Kyiv 2026: 3,100–3,650 UAH/m³ delivered (mean)",
    "Метінвест-СМЦ Київ, 09.11.2026: 50 000 грн/т": "Metinvest-SMC Kyiv, 09.11.2026: 50,000 UAH/t",
    "ринок ЄС ≥ 500 €/м³ (Holzkurier, 2025) + обробка й доставка → 650 €/м³; запитати ціну Rezult":
        "EU market ≥ 500 €/m³ (Holzkurier, 2025) + CNC and delivery → 650 €/m³; ask Rezult for a quote",
    "орієнтир ConstruPilot": "ConstruPilot reference", "ціна користувача": "user price", "НБУ ": "NBU ", "грн/€": "UAH/€",
    "кліматичні дані обласного центру (ДСТУ-Н Б В.1.1-27:2010, ДБН В.1.2-2:2006 дод. Е) — для конкретної ділянки перевірити за чинними нормами":
        "climate data of the oblast centre (DSTU-N B V.1.1-27:2010, DBN V.1.2-2:2006 annex E) — confirm for the actual site",
    "температурна зона за картою дод. А ДБН В.2.6-31:2021 — перевірити для конкретного населеного пункту":
        "temperature zone from the map in annex A of DBN V.2.6-31:2021 — confirm for the locality",
    "розрахункові λ матеріалів — довідкові (умови експлуатації Б); у проєкті використовувати значення з декларацій виробників / ДСТУ Б В.2.6-189":
        "material λ values are reference values (service conditions B); use the manufacturers' declared values / DSTU B V.2.6-189 in the design",
    "; перевірка конденсації методом Глейзера при розрахунковій θe (консервативно)": "; condensation checked with the Glaser method",
    "теплові містки: надбавка ΔU = ": "thermal bridges: ΔU = ", " до всієї оболонки (спрощено); вентиляція ": " on the whole envelope (simplified); ventilation ",
    ", рекуперація η = ": ", heat recovery η = ", "год⁻¹": "h⁻¹",
    "річна потреба в теплі = (H_T + H_V) × ГД × 24 — без сонячних і внутрішніх теплонадходжень (верхня оцінка); ":
        "annual heating demand = (H_T + H_V) × HDD × 24 — without solar and internal gains (upper bound); ",
    "енергетичний клас визначається за Методикою (наказ Мінрегіону) та ДСТУ EN ISO 52016":
        "the energy class is determined with the official Methodology (Ministry of Regional Development) and DSTU EN ISO 52016",
    "перерізи несучих конструкцій — попередній розрахунок, підлягає перевірці ": "structural sections — preliminary design, to be checked by the ",
    "інженером-конструктором; ДБН В.1.2-14 (надійність) і ДБН В.2.1-10 (основи)": "structural engineer; DBN V.1.2-14 (reliability) and DBN V.2.1-10 (foundations)",
    "Панелі ": "Panels ", ": задекларовані значення за ": ": declared values from ", "f_R,k за рис. 3 ETA": "f_R,k from ETA figure 3", "обвуглювання": "charring",
    "; вібрацію, вузли, просторову стійкість, цілісність і теплоізоляцію при пожежі (E, I) тут не перевірено":
        "; vibration, connections, lateral stability, fire integrity and insulation (E, I) not checked here",
    "Панель CLT (модуль bet_clt_ua)": "CLT panel (bet_clt_ua engine)", "Панель CLT": "CLT panel", "панель CLT": "CLT panel", " шарів": " layers",
    "проліт": "span", "викор.": "util.", "стрічк. фундамент": "strip footing", "Стрічковий фундамент (на 1 м)": "Strip footing (per metre)",
    "З/б плита, армована у двох напрямках": "Two-way RC slab", "з/б плита": "RC slab", "плита": "slab",
    "Зовнішня стіна": "External wall", "Суміщене покриття": "Flat roof", "Горищне перекриття": "Attic floor",
    "Перекриття над холодним підвалом / проїздом": "Floor over unheated space", "Вікна (світлопрозорі)": "Windows", "Зенітні ліхтарі": "Skylights",
    "Зовнішні двері": "External doors", "Підлога по ґрунту": "Ground floor slab", "Вікна та двері тераси": "Windows and terrace doors",
    "Вікна (двокамерний склопакет)": "Windows (triple glazing)", "Вхідні двері": "Entrance door", "Стіна: ": "Wall: ", "Покрівля: ": "Roof: ",
    "Підлога над підвалом: ": "Floor over basement: ", "Покриття: ": "Roof: ", "мінвата": "mineral wool", "легкий бетон": "lightweight concrete", "з/б": "RC",
    "Гіпсокартон": "Plasterboard", "Пароізоляція бітумна з алюмінієвою фольгою (Sd ≈ 1500 м)": "Bituminous vapour barrier with aluminium (Sd ≈ 1500 m)",
    "Пароізоляція (Sd ≥ 18 м)": "Vapour barrier (Sd ≥ 18 m)", "Вітрозахисна мембрана (Sd ≤ 0,2 м)": "Wind barrier (Sd ≤ 0.2 m)",
    "Покрівельна мембрана ПВХ/ТПО": "Roof membrane PVC/TPO", "Мінеральна вата (фасадна)": "Mineral wool (facade)", "Мінеральна вата (покрівельна)": "Mineral wool (roof)",
    "Екструдований пінополістирол (XPS)": "Extruded polystyrene (XPS)", "Пінополістирол (EPS)": "Expanded polystyrene (EPS)", "Поліізоціанурат (PIR)": "Polyisocyanurate (PIR)",
    "Цементна стяжка": "Cement screed", "Залізобетон": "Reinforced concrete", "Керамзитовий гравій": "Expanded clay", "Газобетон": "Aerated concrete",
    "Деревина (сосна)": "Timber (pine)", "Гіпсова штукатурка": "Gypsum plaster", "Тонкошарова фасадна штукатурка": "Thin-coat render", "Цементно-піщана штукатурка": "Cement render",
    "ДБН В.": "DBN V.", "ДСТУ-Н Б В.": "DSTU-N B V.", "ДСТУ-Н Б EN": "DSTU-N B EN", "ДСТУ Б В.": "DSTU B V.", "ДСТУ EN": "DSTU EN",
    "табл. Б.2": "table B.2", "табл.": "table", "дод. А": "annex A", "дод. Е": "annex E", "(зона ": "(zone ", "зона ": "zone ",
    "м²·К/Вт": "m²·K/W", "Вт/(м²·К)": "W/(m²·K)", "кВт": "kW", "кПа": "kPa", " Па": " Pa", "м³": "m³", "м²": "m²", " мм": " mm", " грн": " UAH",
    "ПДВ": "VAT", "Україна": "Ukraine", "тис.": "k", "МПа": "MPa",
}
EN.update({
    "з/б плита 250 над підвалом": "RC slab 250 over the basement", "верх фундаментів": "top of footings", "над підвалом": "over the basement",
    "1-й поверх": "ground floor", "2-й поверх": "first floor", "3-й поверх": "second floor", "підвал": "basement",
    "легкий бетон": "lightweight concrete", "гравій": "gravel", "покрівля": "roof", "Житловий будинок": "Residential house",
    "секція": "unit", "з/б": "RC",
})
_TRANSLIT = dict(zip("АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯабвгґдеєжзиіїйклмнопрстуфхцчшщьюя",
                     ["A", "B", "V", "H", "G", "D", "E", "Ye", "Zh", "Z", "Y", "I", "Yi", "Y", "K", "L", "M", "N", "O", "P", "R", "S", "T", "U", "F",
                      "Kh", "Ts", "Ch", "Sh", "Shch", "", "Yu", "Ya",
                      "a", "b", "v", "h", "g", "d", "e", "ie", "zh", "z", "y", "i", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
                      "kh", "ts", "ch", "sh", "shch", "", "iu", "ia"]))


def translit(s: str) -> str:
    """Transliteração oficial (KMU 2010) — para referências/rótulos de dados que não têm tradução (ФС-1 → FS-1)."""
    return "".join(_TRANSLIT.get(ch, ch) for ch in s)


def modelo_en(m):
    """Modelo estrutural com os textos de dados em inglês (níveis, descrições) e referências em latim — dossier EN sem cirílico."""
    if isinstance(m, str):
        return translit(tr_en(m))
    if isinstance(m, list):
        return [modelo_en(v) for v in m]
    if isinstance(m, dict):
        return {k: modelo_en(v) for k, v in m.items()}
    return m


_ORD_EN = sorted(EN, key=len, reverse=True)
EXATO_EN = {"т": "t", "грн": "UAH", "млн": "M", "кВт": "kW", "м": "m", "шт": "pcs"}


def tr_en(s):
    if not isinstance(s, str):
        return s
    if s.strip() in EXATO_EN:
        return EXATO_EN[s.strip()]
    for k in _ORD_EN:
        if k in s:
            s = s.replace(k, EN[k])
    return s


def deep_en(x):
    if isinstance(x, str):
        return tr_en(x)
    if isinstance(x, tuple):
        return tuple(deep_en(v) for v in x)
    if isinstance(x, list):
        return [deep_en(v) for v in x]
    if isinstance(x, dict):
        return {k: deep_en(v) for k, v in x.items()}
    return x


EN_RENDU = {"note": "Calculation report", "page": "page", "ref": "Ref.", "synthese": "Summary of checks", "conformes": "compliant",
            "non_conformes": "not compliant", "a_verifier": "to check", "verdict_ok": "COMPLIANT", "verdict_ko": "NOT COMPLIANT", "verdict_na": "TO CHECK",
            "verdict_glob_ok": "All calculated checks are satisfied", "verdict_glob_ko": "At least one check is not satisfied",
            "verdict_glob_na": "No non-compliance — some items to check", "head": ["Standard", "Requirement", "Value", "Result"],
            "hyp": "Assumptions / to be confirmed", "brand_sub": "Digital design office"}
