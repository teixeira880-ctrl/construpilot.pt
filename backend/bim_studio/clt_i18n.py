"""English and Ukrainian versions of the CLT dossier (clt_study).

Keys are the Portuguese texts the dossier prints. Fixed texts and the standard library, parameters and sources are
translated whole; company-entered texts that have no translation stay as the company wrote them. Room and panel
names read on the plans are translated word by word (PHRASES).
"""
from __future__ import annotations

import re

# Portuguese text → (English, Ukrainian)
T = {
    # stages, categories, origins
    "Compra de matéria-prima": ("Raw material purchase", "Закупівля сировини"),
    "Fabrico": ("Fabrication", "Виготовлення"),
    "Produção (energia e mão de obra)": ("Production (energy and labour)", "Виробництво (енергія та праця)"),
    "Transporte": ("Transport", "Транспорт"),
    "Montagem": ("Assembly", "Монтаж"),
    "Revestimentos e isolamentos": ("Linings and insulation", "Облицювання та утеплення"),
    "Instalações e acabamentos": ("Services and finishes", "Інженерні мережі та оздоблення"),
    "Entrega": ("Handover", "Здача"),
    "Custos indiretos": ("Indirect costs", "Непрямі витрати"),
    "Venda": ("Sale", "Продаж"),
    "Matéria-prima": ("Raw material", "Сировина"),
    "Energia e água": ("Energy and water", "Енергія та вода"),
    "Colaboradores": ("Staff", "Персонал"),
    "Gruas e máquinas": ("Cranes and machinery", "Крани та техніка"),
    "Montagem em obra": ("Site assembly", "Монтаж на об'єкті"),
    "Revestimentos": ("Linings", "Облицювання"),
    "Isolamentos, impermeabilização e betão leve": ("Insulation, waterproofing and lightweight screed", "Утеплення, гідроізоляція та легка стяжка"),
    "Estrutura complementar": ("Additional structure", "Додаткова конструкція"),
    "Caixilharia e portas": ("Windows and doors", "Вікна та двері"),
    "Eletricidade": ("Electrical", "Електрика"),
    "Canalização e louças": ("Plumbing and sanitary ware", "Сантехніка та санфаянс"),
    "Pavimentos, cerâmica e acabamentos": ("Floors, tiles and finishes", "Підлоги, плитка та оздоблення"),
    "Engenharia, estaleiro e imprevistos": ("Engineering, site set-up and contingency", "Проєктування, будмайданчик та непередбачені"),
    "Venda do CLT": ("CLT sale", "Продаж CLT"),
    "empresa": ("company", "компанія"), "mercado": ("market", "ринок"), "HIPÓTESE": ("ASSUMPTION", "ПРИПУЩЕННЯ"), "norma": ("standard", "норма"),
    # fixed texts of the dossier
    "Estudo CLT completo": ("Complete CLT study", "Повне дослідження CLT"),
    "Custo total": ("Total cost", "Загальна вартість"),
    "Venda sem IVA": ("Sale excl. VAT", "Продаж без ПДВ"),
    "Venda com IVA": ("Sale incl. VAT", "Продаж з ПДВ"),
    "Margem": ("Margin", "Маржа"),
    "CLT fabricado": ("CLT produced", "Виготовлено CLT"),
    "Prazo": ("Duration", "Термін"),
    "dias": ("days", "днів"),
    "1. Síntese": ("1. Summary", "1. Підсумок"),
    "Âmbito: da compra da madeira e do fabrico dos painéis CLT até à entrega da chave: estrutura CLT, vigas de aço, revestimentos, isolamentos e estanquidade, caixilharia, eletricidade, canalização e acabamentos. Fora do âmbito: betão e lajes de betão, cálculo estrutural, projetos de especialidade e planos de execução. ": (
        "Scope: from timber purchase and CLT panel fabrication to key handover: CLT structure, steel beams, linings, insulation and "
        "airtightness, windows and doors, electrical, plumbing and finishes. Out of scope: concrete and concrete slabs, structural design, "
        "MEP design and construction drawings. ",
        "Обсяг: від закупівлі деревини та виготовлення панелей CLT до здачі «під ключ»: конструкція CLT, сталеві балки, облицювання, "
        "утеплення та герметичність, вікна та двері, електрика, сантехніка та оздоблення. Поза обсягом: бетон і бетонні плити, "
        "розрахунок конструкцій, проєкти інженерних мереж і робочі креслення. "),
    "Todos os valores vêm da empresa ou do mercado.": ("All values come from the company or the market.", "Усі значення від компанії або з ринку."),
    "ESTIMATIVA: {n} valores ainda são hipóteses (lista no capítulo 6). A empresa confirma-os em Parâmetros e Bibliotecas na página CLT e o dossier é refeito com os seus valores.": (
        "ESTIMATE: {n} values are still assumptions (list in chapter 6). The company confirms them under Parameters and Libraries on the "
        "CLT page and the dossier is regenerated with its values.",
        "КОШТОРИС: {n} значень ще є припущеннями (перелік у розділі 6). Компанія підтверджує їх у розділах «Параметри» та «Бібліотеки» "
        "на сторінці CLT, і досьє формується заново з її значеннями."),
    "Fase": ("Phase", "Етап"), "€": ("€", "€"), "% do custo": ("% of cost", "% вартості"),
    "IVA {p} %": ("VAT {p} %", "ПДВ {p} %"),
    "Venda com IVA (cliente final)": ("Sale incl. VAT (end client)", "Продаж з ПДВ (кінцевий клієнт)"),
    "Benefício (margem)": ("Profit (margin)", "Прибуток (маржа)"),
    "{p} % da venda": ("{p} % of sale", "{p} % від продажу"),
    "Custo por fase": ("Cost by phase", "Вартість за етапами"),
    "Custo direto e indireto por fase, a partir do orçamento linha a linha.": ("Direct and indirect cost by phase, from the line-by-line budget.",
                                                                               "Прямі та непрямі витрати за етапами, з порядкового кошторису."),
    "Rácio": ("Ratio", "Показник"), "Valor": ("Value", "Значення"),
    "Área útil (soma das divisões revistas)": ("Usable area (sum of reviewed rooms)", "Корисна площа (сума перевірених приміщень)"),
    "Custo por m² útil": ("Cost per usable m²", "Вартість за м² корисної площі"),
    "Venda com IVA por m² útil": ("Sale incl. VAT per usable m²", "Продаж з ПДВ за м² корисної площі"),
    "Custo por m³ de CLT fabricado": ("Cost per m³ of CLT produced", "Вартість за м³ виготовленого CLT"),
    "2. Medições (métrés)": ("2. Quantity take-off", "2. Обміри (кошторисні обсяги)"),
    "Medidas nos planos vetoriais revistos na página CLT: cada troço de parede, cada painel, vão e divisão tem a sua referência de leitura. Altura estrutural de cada piso = pé-direito acabado + pavimento + zona do teto falso, medidos no corte.": (
        "Measured on the vector drawings reviewed on the CLT page: every wall run, panel, opening and room carries its reading reference. "
        "Structural height of each floor = finished ceiling height + floor build-up + suspended-ceiling zone, measured on the section.",
        "Виміряно на перевірених векторних кресленнях на сторінці CLT: кожна ділянка стіни, панель, проріз і приміщення має своє "
        "посилання. Конструктивна висота поверху = чиста висота + конструкція підлоги + зона підвісної стелі, виміряні на розрізі."),
    "Piso {f} · altura estrutural {h} m": ("{f} · structural height {h} m", "{f} · конструктивна висота {h} м"),
    "Troço CLT (ref. de leitura)": ("CLT wall run (reading ref.)", "Ділянка CLT (посилання)"),
    "Espessura mm": ("Thickness mm", "Товщина мм"), "Comprimento m": ("Length m", "Довжина м"), "Área m²": ("Area m²", "Площа м²"),
    "Volume m³": ("Volume m³", "Об'єм м³"), "Total": ("Total", "Разом"),
    "Parede CLT {t} mm": ("CLT wall {t} mm", "Стіна CLT {t} мм"),
    "Total CLT do piso": ("Floor CLT total", "Разом CLT поверху"),
    "Elemento CLT": ("CLT element", "Елемент CLT"), "Camadas": ("Layers", "Шари"),
    "vão {n}": ("opening {n}", "проріз {n}"), "vão envidraçado": ("glazed bay", "засклений проріз"), "janela": ("window", "вікно"),
    "Vão exterior": ("External opening", "Зовнішній проріз"), "Tipo": ("Type", "Тип"), "Sob": ("Under", "Під"),
    "Largura m": ("Width m", "Ширина м"), "Altura m": ("Height m", "Висота м"),
    "Divisão": ("Room", "Приміщення"), "Perímetro m": ("Perimeter m", "Периметр м"), "Aparelhos desenhados": ("Fixtures drawn", "Прилади на кресленні"),
    "Revestimentos, isolamentos e estrutura complementar": ("Linings, insulation and additional structure", "Облицювання, утеплення та додаткова конструкція"),
    "Piso": ("Floor", "Поверх"), "Placa BA13 m²": ("BA13 board m²", "ГКЛ BA13 м²"), "Pintura m²": ("Paint m²", "Фарбування м²"),
    "Teto BA15 m²": ("BA15 ceiling m²", "Стеля BA15 м²"), "Fachada m²": ("Façade m²", "Фасад м²"), "Laje (isol.) m²": ("Slab (insul.) m²", "Плита (утепл.) м²"),
    "Cobertura m²": ("Roof m²", "Покрівля м²"), "Aço m": ("Steel m", "Сталь м"),
    "Instalações, caixilharia e acabamentos (motor RTIEBT por divisão e aparelhos DR 23/95)": (
        "Services, windows and finishes (RTIEBT engine per room, DR 23/95 fixtures)",
        "Інженерні мережі, вікна та оздоблення (модуль RTIEBT за приміщеннями, прилади DR 23/95)"),
    "Quantidade": ("Quantity", "Кількість"), "Un.": ("Unit", "Од."),
    "Matéria-prima e produção · {a} viagens de madeira e {b} de painéis": ("Raw material and production · {a} timber trips and {b} panel trips",
                                                                         "Сировина та виробництво · {a} рейсів деревини і {b} рейсів панелей"),
    "CLT m³": ("CLT m³", "CLT м³"), "Madeira m³": ("Timber m³", "Деревина м³"), "Cola kg": ("Glue kg", "Клей кг"),
    "Eletricidade kWh": ("Electricity kWh", "Електроенергія кВт·год"), "h fabrico": ("Fabrication h", "Год виготовлення"), "h montagem": ("Assembly h", "Год монтажу"),
    "3. Orçamento detalhado (quantidade × preço unitário)": ("3. Detailed budget (quantity × unit price)", "3. Детальний кошторис (кількість × ціна)"),
    "Código": ("Code", "Код"), "Designação": ("Description", "Найменування"), "Qtd.": ("Qty", "К-сть"), "€/un.": ("€/unit", "€/од."),
    "Custo €": ("Cost €", "Вартість €"), "Venda €": ("Sale €", "Продаж €"), "Origem": ("Origin", "Джерело"),
    "4. Custos, benefício e sensibilidade": ("4. Costs, profit and sensitivity", "4. Витрати, прибуток і чутливість"),
    "Benefício €": ("Profit €", "Прибуток €"), "Margem %": ("Margin %", "Маржа %"),
    "Madeira e matéria-prima +10 %": ("Timber and raw material +10 %", "Деревина та сировина +10 %"),
    "Montagem em obra +10 %": ("Site assembly +10 %", "Монтаж на об'єкті +10 %"),
    "Instalações e acabamentos +10 %": ("Services and finishes +10 %", "Інженерні мережі та оздоблення +10 %"),
    "Todos os preços HIPÓTESE +10 %": ("All ASSUMED prices +10 %", "Усі ціни-ПРИПУЩЕННЯ +10 %"),
    "Todos os preços HIPÓTESE −10 %": ("All ASSUMED prices −10 %", "Усі ціни-ПРИПУЩЕННЯ −10 %"),
    "Preços de venda −5 %": ("Sale prices −5 %", "Ціни продажу −5 %"),
    "Base (este dossier)": ("Base (this dossier)", "База (це досьє)"),
    "Sensibilidade: o mesmo cálculo refeito com a variação indicada (venda mantida quando só o custo muda).": (
        "Sensitivity: the same calculation re-run with the stated change (sale kept when only the cost changes).",
        "Чутливість: той самий розрахунок, повторений із зазначеною зміною (продаж незмінний, коли змінюється лише вартість)."),
    "Cenário": ("Scenario", "Сценарій"),
    "5. Plano de seguimento, da fabricação à montagem e à entrega": ("5. Tracking plan, from fabrication to assembly and handover",
                                                                  "5. План контролю: від виготовлення до монтажу та здачі"),
    "Fases sequenciais em dias de calendário; o lote de seguimento da página CLT parte deste plano.": (
        "Sequential phases in calendar days; the tracking lot on the CLT page starts from this plan.",
        "Послідовні етапи в календарних днях; контрольний лот на сторінці CLT базується на цьому плані."),
    "{a} → {b} · {d} dias de calendário": ("{a} → {b} · {d} calendar days", "{a} → {b} · {d} календарних днів"),
    "{q} m³ de madeira, {n} viagens": ("{q} m³ of timber, {n} trips", "{q} м³ деревини, {n} рейсів"),
    "{q} m³ de CLT a {r} m³/dia": ("{q} m³ of CLT at {r} m³/day", "{q} м³ CLT по {r} м³/день"),
    "{n} viagens de {q} m³": ("{n} trips of {q} m³", "{n} рейсів по {q} м³"),
    "{q} m² a {r} m²/dia ({c} pessoas × {h} h)": ("{q} m² at {r} m²/day ({c} people × {h} h)", "{q} м² по {r} м²/день ({c} осіб × {h} год)"),
    "{a} divisões, {b} vãos": ("{a} rooms, {b} openings", "{a} приміщень, {b} прорізів"),
    "Início": ("Start", "Початок"), "Fim (marco)": ("End (milestone)", "Кінець (віха)"), "Dias": ("Days", "Днів"),
    "Quantidade e ritmo previstos": ("Planned quantity and rate", "Плановий обсяг і темп"),
    "Custo planeado acumulado": ("Cumulative planned cost", "Накопичена планова вартість"),
    "Curva de custo planeado": ("Planned cost curve", "Крива планових витрат"), "semana": ("week", "тиждень"),
    "Cada fase de custo distribuída de forma uniforme pela fase do plano que a gasta; custos indiretos ao longo de toda a obra (hipótese de planeamento).": (
        "Each cost phase spread evenly over the plan phase that spends it; indirect costs over the whole job (planning assumption).",
        "Кожна стаття витрат рівномірно розподілена на етап плану, що її витрачає; непрямі — на весь об'єкт (планове припущення)."),
    "Semana": ("Week", "Тиждень"), "Até": ("Until", "До"), "Custo planeado acumulado €": ("Cumulative planned cost €", "Накопичена планова вартість €"),
    "% planeado": ("% planned", "% план"), "Custo real €": ("Actual cost €", "Фактична вартість €"), "% real": ("% actual", "% факт"),
    "Folha de controlo do lote de seguimento: o orçamento de cada artigo é a base; a página CLT regista as compras e o realizado e calcula o desvio e a previsão de fecho.": (
        "Control sheet of the tracking lot: each item's budget is the baseline; the CLT page records purchases and progress and computes the "
        "variance and the forecast at completion.",
        "Контрольний аркуш лоту: кошторис кожної позиції є базою; сторінка CLT фіксує закупівлі та виконання і розраховує відхилення "
        "та прогноз на завершення."),
    "Artigo": ("Item", "Позиція"), "Qtd. base": ("Baseline qty", "Базова к-сть"), "Orçamento €": ("Budget €", "Кошторис €"), "Real €": ("Actual €", "Факт €"),
    "Indicador a seguir": ("Indicator to track", "Показник контролю"), "Previsto": ("Planned", "План"), "Como medir": ("How to measure", "Як вимірювати"),
    "Entregas": ("Deliveries", "Поставки"), "Custo comprometido": ("Committed cost", "Зобов'язані витрати"), "Margem prevista": ("Forecast margin", "Прогнозна маржа"),
    "{r} m³/dia": ("{r} m³/day", "{r} м³/день"), "{r} m²/dia": ("{r} m²/day", "{r} м²/день"), "{n} viagens": ("{n} trips", "{n} рейсів"),
    "m³ de painéis aprovados por dia na linha": ("m³ of approved panels per day on the line", "м³ прийнятих панелей за день на лінії"),
    "m² de painéis aparafusados por dia de equipa": ("m² of panels screwed per crew day", "м² панелей, змонтованих за день бригади"),
    "guias de transporte": ("delivery notes", "транспортні накладні"),
    "encomendas e faturas por artigo do lote": ("orders and invoices per lot item", "замовлення та рахунки за позиціями лоту"),
    "venda − previsão de fecho do lote": ("sale − lot forecast at completion", "продаж − прогноз завершення лоту"),
    "6. Parâmetros, preços, origens e fontes": ("6. Parameters, prices, origins and sources", "6. Параметри, ціни, походження та джерела"),
    "Parâmetro": ("Parameter", "Параметр"), "Fonte ou como confirmar": ("Source or how to confirm", "Джерело або як підтвердити"),
    "Preço": ("Price", "Ціна"), "Custo": ("Cost", "Вартість"), "Fonte": ("Source", "Джерело"),
    "Troços medidos = paredes orçamentadas ({f})": ("Measured runs = budgeted walls ({f})", "Виміряні ділянки = стіни в кошторисі ({f})"),
    "Soma das linhas = custo total": ("Sum of lines = total cost", "Сума рядків = загальна вартість"),
    "IVA {p} % da venda": ("VAT {p} % of sale", "ПДВ {p} % від продажу"),
    "Controlos automáticos": ("Automatic checks", "Автоматичні перевірки"), "Controlo": ("Check", "Перевірка"), "Valores": ("Values", "Значення"),
    "Resultado": ("Result", "Результат"), "VERIFICAR": ("CHECK", "ПЕРЕВІРИТИ"),
    "Valores a confirmar pela empresa": ("Values to be confirmed by the company", "Значення для підтвердження компанією"),
    "nenhum": ("none", "немає"),
    "IVA aplicado: ": ("VAT applied: ", "Застосований ПДВ: "),
    "Depende do local da obra e do comprador: casa construída na Ucrânia → ПДВ 20 %; painéis exportados da Ucrânia → 0 % na Ucrânia e IVA do país de destino; obra em Portugal → IVA 23 %.": (
        "Depends on where the house is built and who buys: house built in Ukraine → VAT 20 %; panels exported from Ukraine → 0 % in Ukraine and the destination country's VAT; site in Portugal → VAT 23 %.",
        "Залежить від місця будівництва та покупця: будинок в Україні → ПДВ 20 %; панелі на експорт з України → 0 % в Україні та ПДВ країни призначення; об'єкт у Португалії → ПДВ 23 %."),
    "Medições, custos, benefício e plano de seguimento · motor ConstruPilot CLT": ("Take-off, costs, profit and tracking plan · ConstruPilot CLT engine",
                                                                                "Обміри, витрати, прибуток і план контролю · модуль ConstruPilot CLT"),
    "Dossier completo: medições, custos, benefício e plano de seguimento, da fabricação à entrega da chave.": (
        "Complete dossier: take-off, costs, profit and tracking plan, from fabrication to key handover.",
        "Повне досьє: обміри, витрати, прибуток і план контролю, від виготовлення до здачі «під ключ»."),
    "Início previsto {a} · entrega {b}": ("Planned start {a} · handover {b}", "Плановий початок {a} · здача {b}"),
    "Benefício": ("Profit", "Прибуток"), "€ · {p} % da venda": ("€ · {p} % of sale", "€ · {p} % від продажу"), "CLT": ("CLT", "CLT"),
    "m³ fabricados": ("m³ produced", "м³ виготовлено"), "Painéis": ("Panels", "Панелі"), "m² montados": ("m² assembled", "м² змонтовано"),
    "dias de calendário": ("calendar days", "календарних днів"), "Área útil": ("Usable area", "Корисна площа"), "m²": ("m²", "м²"),
    "Hipóteses": ("Assumptions", "Припущення"), "valores a confirmar": ("values to confirm", "значень для підтвердження"),
    "Índice": ("Contents", "Зміст"), "Capa": ("Cover", "Обкладинка"),
    "Estimativa por motores determinísticos ConstruPilot — a validar pelo responsável técnico da empresa.": (
        "Estimate by ConstruPilot deterministic engines — to be validated by the company's technical lead.",
        "Кошторис детермінованими модулями ConstruPilot — підлягає перевірці технічним керівником компанії."),
    "ConstruPilot — nota de cálculo gerada por motor determinístico; a validar pelo projetista / técnico responsável antes da execução.": (
        "ConstruPilot — report generated by deterministic engines; to be validated by the responsible engineer before execution.",
        "ConstruPilot — записка сформована детермінованими модулями; перевіряється відповідальним інженером до виконання."),
    "Anexo A · Modelo 3D (IFC) gerado das medições": ("Annex A · 3D model (IFC) generated from the take-off", "Додаток A · 3D-модель (IFC) з обмірів"),
    "Anexo B · Divisões revistas no RDC": ("Annex B · Reviewed rooms, ground floor", "Додаток B · Перевірені приміщення, перший поверх"),
    "Anexo C · Divisões revistas no +1": ("Annex C · Reviewed rooms, first floor", "Додаток C · Перевірені приміщення, другий поверх"),
    # floors, room types, fixtures, units
    "RDC": ("Ground floor", "1-й поверх"), "+1": ("First floor", "2-й поверх"),
    "sala": ("living", "вітальня"), "quarto": ("bedroom", "спальня"), "cozinha": ("kitchen", "кухня"), "casa de banho": ("bathroom", "санвузол"),
    "lavandaria": ("laundry", "пральня"), "corredor": ("circulation", "коридор"), "escritorio": ("office", "кабінет"), "arrumos": ("storage", "комора"),
    "exterior": ("exterior", "зовні"), "viga": ("beam", "балка"), "lintel": ("lintel", "перемичка"),
    "lavatorio": ("washbasin", "умивальник"), "autoclismo": ("WC", "унітаз"), "chuveiro": ("shower", "душ"), "banheira": ("bathtub", "ванна"),
    "lava_loica": ("kitchen sink", "мийка"), "maquina_lavar_loica": ("dishwasher", "посудомийна машина"), "maquina_lavar_roupa": ("washing machine", "пральна машина"),
    "bide": ("bidet", "біде"), "tanque": ("utility sink", "господарська мийка"), "torneira_exterior": ("outdoor tap", "зовнішній кран"),
    "compra": ("purchase", "закупівля"), "producao": ("production", "виробництво"), "transporte": ("transport", "транспорт"),
    "montagem": ("assembly", "монтаж"), "entrega": ("handover", "здача"),
    # fabrication annex (clt_study._fabrication, clt_drawings)
    "Anexo A — Desenhos de fabrico cotados (origem das cotas e medições)": (
        "Annex A — Dimensioned fabrication drawings (origin of dimensions and take-off)",
        "Додаток A — Виробничі креслення з розмірами (походження розмірів і обмірів)"),
    "Cada troço medido no take-off é desenhado com a mesma referência: a planta cota o comprimento de cada parede ao milímetro, "
    "os alçados cotam cada peça de produção (comprimento, altura e vãos) e o plano de corte mostra os painéis de prensa. "
    "As juntas resolvem-se sem contagem dupla: a parede mais comprida passa e a outra encosta.": (
        "Each run measured in the take-off is drawn with the same reference: the plan dimensions every wall length to the millimetre, "
        "the elevations dimension every production piece (length, height and openings) and the cutting plan shows the press panels. "
        "Junctions are resolved without double counting: the longer wall runs through and the other butts against it.",
        "Кожна ділянка з обмірів креслиться з тим самим позначенням: план дає довжину кожної стіни з точністю до міліметра, "
        "розгортки дають розміри кожної виробничої деталі (довжина, висота, отвори), а план розкрою показує пресові панелі. "
        "Вузли без подвійного підрахунку: довша стіна проходить, коротша примикає."),
    "Ref. take-off": ("Take-off ref.", "Позн. обміру"),
    "Medido m": ("Measured m", "Обміряно, м"),
    "Desenhado m": ("Drawn m", "Накреслено, м"),
    "Peças de produção m": ("Production pieces m", "Виробничі деталі, м"),
    "Controlo volume: peças / união das plantas": ("Volume check: pieces / union of plan outlines", "Контроль об'єму: деталі / об'єднання контурів"),
    "Plano de corte: {n} painéis de prensa, desperdício {d} % (formato de prensa {l} × {w} m, parâmetro da empresa).": (
        "Cutting plan: {n} press panels, waste {d} % (press format {l} × {w} m, company parameter).",
        "План розкрою: {n} пресових панелей, відходи {d} % (формат преса {l} × {w} м, параметр компанії)."),
    "Rede de paredes: cada extremo de troço que encosta a outra parede é levado ao eixo dessa parede "
    "(no máximo meia espessura), para reconhecer os cantos L, T e X. Dois troços alinhados dos dois lados "
    "de um lintel CLT passam a uma só peça com o vão recortado; o volume do lintel fica dentro da peça "
    "e é comparado com o painel de lintel da estimativa.": (
        "Wall network: each run end that butts against another wall is taken to that wall's axis (at most half a thickness), so L, T "
        "and X corners are recognised. Two aligned runs on both sides of a CLT lintel become one piece with the opening cut out; the "
        "lintel volume is inside the piece and is compared with the lintel measured like the estimate.",
        "Мережа стін: кожен кінець ділянки, що примикає до іншої стіни, доводиться до осі цієї стіни (не більше половини товщини), "
        "щоб розпізнати кути L, T і X. Дві ділянки по обидва боки перемички CLT стають однією деталлю з вирізаним отвором; об'єм "
        "перемички входить у деталь і порівнюється з перемичкою, обміряною як у кошторисі."),
    "Troços": ("Runs", "Ділянки"), "Peças-mãe": ("Parent pieces", "Основні деталі"), "Extremos ligados": ("Ends joined", "З'єднані кінці"),
    "Lintéis na peça": ("Lintels in a piece", "Перемички в деталі"), "Lintéis m³ (peças)": ("Lintels m³ (pieces)", "Перемички м³ (деталі)"),
    "Lintéis m³ (estimativa)": ("Lintels m³ (estimate)", "Перемички м³ (кошторис)"),
    "Sem geometria dos troços nesta estimativa: volte a calcular na página CLT a partir do PDF para juntar os desenhos cotados.": (
        "No run geometry in this estimate: recalculate on the CLT page from the PDF to attach the dimensioned drawings.",
        "У цьому кошторисі немає геометрії ділянок: перерахуйте на сторінці CLT з PDF, щоб додати креслення з розмірами."),
    "{r}: contorno não convertível em eixo; fica só na tabela de medições.": (
        "{r}: outline cannot be turned into an axis; it stays in the take-off table only.",
        "{r}: контур неможливо перетворити на вісь; лишається лише в таблиці обмірів."),
    "Anexo A · folha {i} / {n}": ("Annex A · sheet {i} / {n}", "Додаток A · аркуш {i} / {n}"),
    "Cotas em mm · desenho sem escala": ("Dimensions in mm · not to scale", "Розміри в мм · без масштабу"),
    "Origem: troços medidos no take-off (mesmas referências das tabelas)": (
        "Source: runs measured in the take-off (same references as the tables)",
        "Джерело: ділянки з обмірів (ті самі позначення, що й у таблицях)"),
    "Desenho de conferência de fabrico. Não substitui o projeto de execução.": (
        "Fabrication check drawing. It does not replace the construction design.",
        "Креслення для перевірки виробництва. Не замінює робочий проєкт."),
    "Desenho de conferência de fabrico gerado pela ConstruPilot. Não substitui o projeto de execução.": (
        "Fabrication check drawing generated by ConstruPilot. It does not replace the construction design.",
        "Креслення для перевірки виробництва, створене ConstruPilot. Не замінює робочий проєкт."),
    "planta dos eixos CLT, cotada (mm)": ("CLT wall axes plan, dimensioned (mm)", "план осей стін CLT з розмірами (мм)"),
    "alçados de fabrico das peças CLT, cotados (mm)": ("CLT piece fabrication elevations, dimensioned (mm)",
                                                       "виробничі розгортки деталей CLT з розмірами (мм)"),
    "Peça": ("Piece", "Деталь"), "Plano de corte": ("Cutting plan", "План розкрою"), "painéis": ("panels", "панелей"),
    "desperdício": ("waste", "відходи"), "Painel": ("Panel", "Панель"), "aproveitamento": ("yield", "використання"),
    "altura standard da empresa: a planta não marca alturas (editável)": (
        "company standard height: the plan gives no heights (editable)",
        "стандартна висота компанії: план не містить висот (можна змінити)"),
}
UNITS = {"dias": ("days", "днів"), "pessoas": ("people", "осіб"), "m³/dia": ("m³/day", "м³/день"), "h/dia": ("h/day", "год/день"),
         "m³/viagem": ("m³/trip", "м³/рейс"), "un": ("pcs", "шт"), "viagem": ("trip", "рейс"), "lote": ("lot", "лот"), "m": ("m", "м"),
         "m²": ("m²", "м²"), "m³": ("m³", "м³"), "kg": ("kg", "кг"), "h": ("h", "год"), "km": ("km", "км"), "kWh": ("kWh", "кВт·год"),
         "kWh/m³": ("kWh/m³", "кВт·год/м³"), "h/m³": ("h/m³", "год/м³"), "h/m²": ("h/m²", "год/м²"), "kg/m²": ("kg/m²", "кг/м²"),
         "m³/m³": ("m³/m³", "м³/м³"), "m2": ("m²", "м²"), "m3": ("m³", "м³"), "L": ("L", "л"), "%": ("%", "%")}
FIT = {"Tomadas": ("Sockets", "Розетки"), "Pontos de luz": ("Light points", "Світлові точки"), "Interruptores": ("Switches", "Вимикачі"),
       "Circuitos": ("Circuits", "Кола"), "Cabo": ("Cable", "Кабель"), "Tubo elétrico": ("Electrical conduit", "Гофротруба"),
       "Quadro elétrico": ("Distribution board", "Електрощит"), "Diferenciais 30 mA": ("30 mA RCDs", "ПЗВ 30 мА"),
       "Pontos de água (fria + quente)": ("Water points (cold + hot)", "Точки водопостачання (холодна + гаряча)"), "Tubo de água": ("Water pipe", "Водопровідна труба"),
       "Pontos de esgoto": ("Drain points", "Точки каналізації"), "Tubo de esgoto": ("Drain pipe", "Каналізаційна труба"), "Sanitas": ("WCs", "Унітази"),
       "Lavatórios": ("Washbasins", "Умивальники"), "Bases de duche": ("Shower trays", "Душові піддони"), "Banheiras": ("Bathtubs", "Ванни"),
       "Lava-loiças": ("Kitchen sinks", "Мийки"), "Produção de AQS": ("Hot-water production", "Приготування ГВП"),
       "Caixilharia exterior": ("External windows", "Зовнішні вікна"), "Vãos exteriores": ("External openings", "Зовнішні прорізи"),
       "Portas interiores": ("Internal doors", "Внутрішні двері"), "Porta de entrada": ("Entrance door", "Вхідні двері"),
       "Pavimento flutuante": ("Floating floor", "Плаваюча підлога"), "Pavimento cerâmico": ("Ceramic floor", "Керамічна підлога"),
       "Cerâmica de parede": ("Wall tiles", "Настінна плитка"), "Rodapé": ("Skirting", "Плінтус")}
T.update(FIT)
ITEMS = {
    "MP-LAMELA": ("C24 lamella timber, kiln-dried and planed", "Ламелі C24, висушені та стругані"),
    "MP-COLA-PUR": ("One-component PUR adhesive, type I", "Однокомпонентний клей PUR, тип I"),
    "EN-ELETRICIDADE": ("Factory electricity", "Електроенергія заводу"), "EN-AGUA": ("Factory water", "Вода заводу"),
    "COL-OPERADOR": ("CLT line operator", "Оператор лінії CLT"),
    "TR-MATERIA-PRIMA": ("Timber transport to the factory", "Доставка деревини на завод"),
    "TR-OBRA": ("Panel transport to site", "Доставка панелей на об'єкт"),
    "MAQ-GRUA": ("Mobile crane 30 t", "Автокран 30 т"),
    "MONT-PAINEL-M2": ("Subcontracted CLT panel assembly", "Субпідрядний монтаж панелей CLT"),
    "MONT-ACESSORIOS": ("Connectors, EPDM tape and fixings", "З'єднувачі, стрічка EPDM та кріплення"),
    "REV-PLACA-BA13": ("BA13 plasterboard (material)", "ГКЛ BA13 (матеріал)"), "REV-FIXACOES": ("Fixings, tape and filler", "Кріплення, стрічка та шпаклівка"),
    "REV-PLACA-SUB": ("Subcontracted board installation", "Субпідрядний монтаж ГКЛ"), "REV-TINTA": ("Paint, two coats", "Фарба, два шари"),
    "REV-PINTURA-SUB": ("Subcontracted painting", "Субпідрядне фарбування"),
    "REV-PLACA-BA15": ("BA15 ceiling plasterboard (material)", "ГКЛ BA15 для стелі (матеріал)"),
    "REV-TETO-SUB": ("Subcontracted suspended ceiling (profiles and installation)", "Субпідрядна підвісна стеля (профілі та монтаж)"),
    "ISO-LAJE": ("Acoustic membrane and 100 mm lightweight screed on the slab", "Акустична мембрана та легка стяжка 100 мм на плиті"),
    "ISO-COBERTURA": ("Flat roof: 100 mm XPS, lightweight screed, PVC and gravel", "Плоска покрівля: XPS 100 мм, легка стяжка, ПВХ та гравій"),
    "ISO-FACHADA": ("Façade: 100 mm mineral wool and vapour membrane (no external finish)", "Фасад: мінвата 100 мм і пароізоляція (без зовнішнього оздоблення)"),
    "EST-VIGA-ACO": ("Steel beam (profile not on the drawing), supplied and installed", "Сталева балка (профіль не вказано), постачання та монтаж"),
    "CX-CAIXILHARIA": ("Thermally broken aluminium windows with double glazing, installed", "Алюмінієві вікна з терморозривом і склопакетом, встановлені"),
    "CX-REMATES": ("Sills, thresholds and opening trims", "Підвіконня, пороги та обрамлення прорізів"),
    "CX-PORTA-ENTRADA": ("Security entrance door, installed", "Броньовані вхідні двері, встановлені"),
    "CX-PORTA-INTERIOR": ("Lacquered internal door with frame and hardware, installed", "Внутрішні лаковані двері з коробкою та фурнітурою"),
    "EL-TOMADA": ("Socket with box, device and labour", "Розетка з коробкою, механізмом і роботою"),
    "EL-PONTO-LUZ": ("Light point with box and labour", "Світлова точка з коробкою і роботою"),
    "EL-INTERRUPTOR": ("Switch with box and device", "Вимикач з коробкою та механізмом"),
    "EL-CABO": ("H07V cable (3-conductor equivalent)", "Кабель H07V (еквівалент 3 жил)"),
    "EL-TUBO": ("Corrugated conduit in the service wall", "Гофротруба в інсталяційній стіні"),
    "EL-QUADRO": ("Distribution board with breakers, installed", "Електрощит з автоматами, змонтований"),
    "EL-DIFERENCIAL": ("30 mA residual-current device", "ПЗВ 30 мА"),
    "CN-PONTO-AGUA": ("Water point (multilayer, fittings and labour)", "Точка водопостачання (металопластик, фітинги, робота)"),
    "CN-TUBO-AGUA": ("Insulated multilayer pipe", "Утеплена металопластикова труба"),
    "CN-PONTO-ESGOTO": ("PVC drain point with trap", "Точка каналізації ПВХ із сифоном"), "CN-TUBO-ESGOTO": ("PVC drain pipe", "Каналізаційна труба ПВХ"),
    "CN-SANITA": ("Wall-hung WC with concealed cistern, installed", "Підвісний унітаз з інсталяцією, встановлений"),
    "CN-LAVATORIO": ("Washbasin with mixer, installed", "Умивальник зі змішувачем, встановлений"),
    "CN-DUCHE": ("Shower tray, screen and mixer", "Душовий піддон, шторка та змішувач"),
    "CN-BANHEIRA": ("Bathtub with mixer, installed", "Ванна зі змішувачем, встановлена"),
    "CN-LAVA-LOICA": ("Kitchen sink with mixer, installed", "Мийка зі змішувачем, встановлена"),
    "CN-AQS": ("200 L heat-pump water heater, installed", "Тепловий насос для ГВП 200 л, встановлений"),
    "AC-PAVIMENTO": ("Floating floor with acoustic underlay and trim", "Плаваюча підлога з акустичною підкладкою"),
    "AC-PAV-CERAMICO": ("Ceramic floor with waterproofing, laid", "Керамічна підлога з гідроізоляцією"),
    "AC-CERAMICA-PAREDE": ("10×10 wall tiles with waterproofing, laid", "Настінна плитка 10×10 з гідроізоляцією"),
    "AC-RODAPE": ("Lacquered timber skirting", "Лакований дерев'яний плінтус"),
    "AC-FACHADA": ("External façade finish (system to be defined)", "Зовнішнє оздоблення фасаду (система визначається)"),
    "IND-ENGENHARIA": ("Structural design and fabrication drawings", "Розрахунок конструкцій і виробничі креслення"),
    "IND-ESTALEIRO": ("Site set-up, insurance and safety", "Будмайданчик, страхування та безпека"),
    "IND-IMPREVISTOS": ("Contingency", "Непередбачені витрати"), "VENDA-CLT": ("CLT panel supplied", "Поставлена панель CLT"),
}
PARAMS = {
    "timber_input_m3_per_m3": ("Timber bought per m³ of CLT (losses included)", "Закуплена деревина на м³ CLT (з втратами)"),
    "adhesive_kg_m2": ("Glue per m² of glued joint", "Клей на м² клейового шва"),
    "fabrication_h_m3": ("Fabrication time per m³ of CLT", "Час виготовлення на м³ CLT"),
    "electricity_kwh_m3": ("Electricity per m³ of CLT", "Електроенергія на м³ CLT"), "factory_m3_day": ("Factory capacity", "Потужність заводу"),
    "materia_prima_km": ("Sawmill–factory distance (round trip)", "Відстань пилорама–завод (туди й назад)"),
    "materia_prima_truck_m3": ("m³ of timber per truck", "м³ деревини на вантажівку"),
    "obra_km": ("Factory–site distance (round trip)", "Відстань завод–об'єкт (туди й назад)"), "truck_m3": ("m³ of CLT per truck", "м³ CLT на вантажівку"),
    "assembly_h_m2": ("Assembly hours per m² of panel", "Години монтажу на м² панелі"), "assembly_crew": ("Assembly crew size", "Склад монтажної бригади"),
    "work_hours_day": ("Working hours per day", "Робочих годин на день"), "purchase_days": ("Timber purchase and receipt time", "Термін закупівлі та приймання деревини"),
    "transport_days": ("Delivery time to site", "Термін доставки на об'єкт"),
    "fitout_days": ("Services and finishes time to key handover", "Термін інженерних мереж і оздоблення до здачі"),
    "press_length_m": ("Maximum press panel length", "Максимальна довжина пресової панелі"),
    "press_width_m": ("Maximum press panel width", "Максимальна ширина пресової панелі"),
    "standard_height_ground_m": ("Standard ground-floor height (when the plan gives no heights)",
                                 "Стандартна висота першого поверху (коли план не містить висот)"),
    "standard_height_upper_m": ("Standard height of the other floors (when the plan gives no heights)",
                                "Стандартна висота інших поверхів (коли план не містить висот)"),
    "iva_percent": ("VAT on sale (Portugal)", "ПДВ на продаж (Португалія)"),
    "iva_ua_percent": ("Ukrainian VAT (ПДВ) on sale", "ПДВ України на продаж"),
}
SOURCES = {
    "Formato de prensa de referência: Rezult, comprimento ≤ 18,00 m e largura ≤ 3,50 m "
    "(clt-rezult.com/en/technical-characteristics, lido em 2026-11-11). Indique o formato da sua prensa.": (
        "Reference press format: Rezult, length ≤ 18.00 m and width ≤ 3.50 m (clt-rezult.com/en/technical-characteristics, read "
        "2026-11-11). Enter your own press format.",
        "Еталонний формат преса: Rezult, довжина ≤ 18,00 м і ширина ≤ 3,50 м (clt-rezult.com/en/technical-characteristics, "
        "переглянуто 2026-11-11). Вкажіть формат свого преса."),
    "Standard da empresa: RDC 3,00 m quando a planta não indica altura.": (
        "Company standard: ground floor 3.00 m when the plan gives no height.",
        "Стандарт компанії: перший поверх 3,00 м, коли план не містить висоти."),
    "Standard da empresa: 2,50 m nos pisos acima do RDC quando a planta não indica altura.": (
        "Company standard: 2.50 m on the floors above the ground floor when the plan gives no height.",
        "Стандарт компанії: 2,50 м на поверхах вище першого, коли план не містить висоти."),
    'Código Tributário da Ucrânia (Податковий кодекс України), art. 193.1 a): taxa base de ПДВ 20 %. A primeira venda de habitação nova é tributada; o art. 197.1.14 isenta só as vendas seguintes.': (
        "Tax Code of Ukraine (Податковий кодекс України), art. 193.1(a): base VAT rate 20 %. The first sale of new housing is taxed; art. 197.1.14 exempts only later sales.",
        "Податковий кодекс України, ст. 193.1 «а»: базова ставка ПДВ 20 %. Перше постачання нового житла оподатковується; п. 197.1.14 звільняє лише наступні продажі."),
    'Código Tributário da Ucrânia, art. 195.1.1: taxa 0 % na exportação de bens (painéis enviados para fora da Ucrânia); aplica-se o IVA do país de destino.': (
        "Tax Code of Ukraine, art. 195.1.1: 0 % rate on export of goods (panels shipped outside Ukraine); the destination country's VAT applies there.",
        "Податковий кодекс України, п. 195.1.1: ставка 0 % на експорт товарів (панелі, вивезені за межі України); застосовується ПДВ країни призначення."),
    "Brandt et al. 2019, BioResources 14(4): perda de 15% na madeira, 1,18 m³ de lamela por m³ de CLT": (
        "Brandt et al. 2019, BioResources 14(4): 15% timber loss, 1.18 m³ of lamella per m³ of CLT",
        "Brandt et al. 2019, BioResources 14(4): втрати деревини 15%, 1,18 м³ ламелей на м³ CLT"),
    "CNR, transporte rodoviário português: 1,13 €/km para um camião de 40 t": ("CNR, Portuguese road haulage: 1.13 €/km for a 40 t truck",
                                                                              "CNR, автоперевезення в Португалії: 1,13 €/км для вантажівки 40 т"),
    "Capacidade real da linha.": ("Actual line capacity.", "Фактична потужність лінії."), "Carga habitual do fornecedor.": ("Supplier's usual load.", "Звичайне завантаження постачальника."),
    "Código do IVA, art. 18.º: taxa normal de 23% no continente. A taxa de 6% só se aplica a obras específicas (verba 2.27 e 2.32 da lista I).": (
        "Portuguese VAT Code, art. 18: standard rate 23% on the mainland. The 6% rate applies only to specific works (items 2.27 and 2.32 of list I).",
        "Кодекс ПДВ Португалії, ст. 18: базова ставка 23% на материку. Ставка 6% лише для окремих робіт (п. 2.27 і 2.32 переліку I)."),
    "Depende do formato dos painéis e do limite de peso.": ("Depends on panel format and weight limit.", "Залежить від формату панелей і граничної ваги."),
    "Equipa do subempreiteiro.": ("Subcontractor's crew.", "Бригада субпідрядника."),
    "Eurostat nrg_pc_205, Portugal, não doméstico 500–1999 MWh, sem impostos, 1.º semestre 2026: 0,1086 €/kWh": (
        "Eurostat nrg_pc_205, Portugal, non-household 500–1999 MWh, excl. taxes, H1 2026: 0.1086 €/kWh",
        "Eurostat nrg_pc_205, Португалія, непобутові 500–1999 МВт·год, без податків, I півріччя 2026: 0,1086 €/кВт·год"),
    "Eurostat, 2025: custo médio da mão de obra em Portugal 19,4 €/h": ("Eurostat, 2025: average labour cost in Portugal 19.4 €/h",
                                                                       "Eurostat, 2025: середня вартість праці в Португалії 19,4 €/год"),
    "Gerador de preços CYPE, EMD010 parede CLT: 1,543 h/m² de mão de obra (38,52 €/m²), grua 0,058 h/m² a 75,04 €/h, 128,71 €/m² montado": (
        "CYPE price generator, EMD010 CLT wall: 1.543 h/m² labour (38.52 €/m²), crane 0.058 h/m² at 75.04 €/h, 128.71 €/m² installed",
        "Генератор цін CYPE, EMD010 стіна CLT: 1,543 год/м² праці (38,52 €/м²), кран 0,058 год/м² по 75,04 €/год, 128,71 €/м² змонтовано"),
    "Gerador de preços CYPE, EMD010: banda EPDM 5,86 + reforço de juntas 2,04 + ligações 2,10 + fixações 1,50 €/m²": (
        "CYPE price generator, EMD010: EPDM tape 5.86 + joint reinforcement 2.04 + connectors 2.10 + fixings 1.50 €/m²",
        "Генератор цін CYPE, EMD010: стрічка EPDM 5,86 + підсилення швів 2,04 + з'єднувачі 2,10 + кріплення 1,50 €/м²"),
    "Holzkurier, abril 2025: CLT a cerca de 500 €/m³ à porta da fábrica (timber-online.net)": (
        "Holzkurier, April 2025: CLT at about 500 €/m³ ex works (timber-online.net)", "Holzkurier, квітень 2025: CLT близько 500 €/м³ франко-завод (timber-online.net)"),
    "Holzkurier, lamelas da Europa Central, 2.º trimestre 2025: 305–325 €/m³ (timber-online.net)": (
        "Holzkurier, Central European lamellas, Q2 2025: 305–325 €/m³ (timber-online.net)", "Holzkurier, ламелі Центральної Європи, II кв. 2025: 305–325 €/м³ (timber-online.net)"),
    "Horário da obra.": ("Site working hours.", "Графік роботи об'єкта."), "Indicar a distância real da obra.": ("Enter the actual site distance.", "Вказати фактичну відстань до об'єкта."),
    "Indicar o fornecedor.": ("Enter the supplier.", "Вказати постачальника."),
    "Kiilto Kestopur G 10 (PUR para CLT): 140–200 g/m² por junta colada": ("Kiilto Kestopur G 10 (PUR for CLT): 140–200 g/m² per glued joint",
                                                                          "Kiilto Kestopur G 10 (PUR для CLT): 140–200 г/м² на клейовий шов"),
    "O perfil não está no desenho. Preencher após o cálculo estrutural.": ("The profile is not on the drawing. Fill in after structural design.",
                                                                          "Профіль не вказано на кресленні. Заповнити після розрахунку конструкцій."),
    "Percentagem do custo direto, faturada ao custo. Preencher com o valor da empresa.": ("Percentage of direct cost, billed at cost. Enter the company value.",
                                                                                         "Відсоток прямих витрат, виставляється за собівартістю. Вказати значення компанії."),
    "Planeamento da empresa e dos subempreiteiros.": ("Company and subcontractor planning.", "Планування компанії та субпідрядників."),
    "Planeamento logístico.": ("Logistics planning.", "Логістичне планування."), "Prazo do fornecedor.": ("Supplier lead time.", "Термін постачальника."),
    "Preencher com a fatura do fornecedor.": ("Fill in from the supplier invoice.", "Заповнити за рахунком постачальника."),
    "Venda = custo + 15% (hipótese)": ("Sale = cost + 15% (assumption)", "Продаж = вартість + 15% (припущення)"),
    "Preencher com o preço da tinta e o rendimento.": ("Enter the paint price and coverage.", "Вказати ціну фарби та витрату."),
    "Preencher com o preço do fornecedor ou subempreiteiro.": ("Enter the supplier or subcontractor price.", "Вказати ціну постачальника або субпідрядника."),
    "Sem dado público. Medir na fábrica: horas totais da linha ÷ m³ produzidos.": ("No public data. Measure at the factory: total line hours ÷ m³ produced.",
                                                                                  "Публічних даних немає. Виміряти на заводі: години лінії ÷ вироблені м³."),
    "Sem preço público. Preencher com a fatura do fornecedor.": ("No public price. Fill in from the supplier invoice.", "Публічної ціни немає. Заповнити за рахунком постачальника."),
    "Södra, EPD CLT 2025: 222 kWh de eletricidade por m³ no fabrico (A3)": ("Södra, CLT EPD 2025: 222 kWh of electricity per m³ in fabrication (A3)",
                                                                          "Södra, EPD CLT 2025: 222 кВт·год електроенергії на м³ при виготовленні (A3)"),
    "Tarifa municipal (ERSAR não publica uma média nacional por API). Indicar a tarifa do concelho da fábrica.": (
        "Municipal tariff (ERSAR publishes no national average by API). Enter the tariff of the factory's municipality.",
        "Муніципальний тариф (ERSAR не публікує середній по країні через API). Вказати тариф муніципалітету заводу."),
    "Zaask Portugal: pintura interior, média 7 €/m² de mão de obra": ("Zaask Portugal: interior painting, average 7 €/m² labour",
                                                                      "Zaask Portugal: внутрішнє фарбування, у середньому 7 €/м² праці"),
    "Zaask Portugal: placa de gesso 1,90–5,03 €/m² de material, instalação média 25 €/m²": (
        "Zaask Portugal: plasterboard 1.90–5.03 €/m² material, average installation 25 €/m²",
        "Zaask Portugal: ГКЛ 1,90–5,03 €/м² матеріал, монтаж у середньому 25 €/м²"),
}
PHRASES = {  # room and panel names read on the plans, longest first
    "Sala e cozinha": ("Living and kitchen", "Вітальня з кухнею"), "Nicho entre I.S.": ("Niche between bathrooms", "Ніша між санвузлами"),
    "Nicho técnico": ("Technical niche", "Технічна ніша"), "Roupeiro Quarto": ("Wardrobe bedroom", "Гардероб спальні"),
    "roupeiro": ("wardrobe", "гардероб"), "entrada": ("entrance", "вхід"), "passagem": ("passage", "прохід"),
    "Quarto": ("Bedroom", "Спальня"), "Escada": ("Stair", "Сходи"), "Hall": ("Hall", "Хол"), "I.S.": ("Bathroom", "Санвузол"), "RDC": ("GF", "1-й пов."),
    "Painel sobre porta": ("Panel over door", "Панель над дверима"), "Lintel": ("Lintel", "Перемичка"), "vão": ("span", "проліт"),
    "Cobertura do RDC fora do +1": ("Ground-floor roof outside the first floor", "Покрівля 1-го поверху поза 2-м"),
    "Laje do +1": ("First-floor slab", "Плита 2-го поверху"), "sem a abertura da escada": ("without the stair opening", "без сходового прорізу"),
    "Cobertura do +1": ("First-floor roof", "Покрівля 2-го поверху"),
}
_PH = sorted(PHRASES, key=len, reverse=True)
NOTES = [
    (r"(.+) · (.+): sem parede alinhada; fica como painel à parte\.", ("{0} · {1}: no aligned wall; stays a separate panel.",
                                                                       "{0} · {1}: немає співвісної стіни; лишається окремою панеллю.")),
    (r"(.+) · (.+): lintel de ([\d.]+) mm com espessura diferente das paredes; fica como painel à parte\.",
     ("{0} · {1}: {2} mm lintel, thickness differs from the walls; stays a separate panel.",
      "{0} · {1}: перемичка {2} мм, товщина відрізняється від стін; лишається окремою панеллю.")),
    (r"(.+): altura não marcada na planta, usada a altura standard de ([\d.]+) m \(editável\)\.",
     ("{0}: no height on the plan, company standard height {1} m used (editable).",
      "{0}: висоту на плані не вказано, застосовано стандартну висоту {1} м (можна змінити).")),
    (r"Eletricidade \(RTIEBT, motor instalacoes\): (\d+) tomadas, (\d+) pontos de luz, (\d+) circuitos, (\d+) diferenciais; potência a contratar ([\d.]+) kVA\.",
     ("Electrical (RTIEBT, services engine): {0} sockets, {1} light points, {2} circuits, {3} RCDs; supply to contract {4} kVA.",
      "Електрика (RTIEBT, модуль мереж): {0} розеток, {1} світлових точок, {2} кіл, {3} ПЗВ; потужність підключення {4} кВА.")),
    (r"Canalização: .*", ("Plumbing: fixtures drawn on the plans (DR 23/95); pipe runs by the plan distance from each room to the technical riser + "
                          "storey height + 1.5 m drop, hot water only to the fixtures that use it, +10 % fittings.",
                          "Сантехніка: прилади з креслень (DR 23/95); труби за відстанню в плані від приміщення до технічного стояка + висота "
                          "поверху + 1,5 м спуску, гаряча вода лише до приладів, що її потребують, +10 % фітингів.")),
    (r"Caixilharia: .*", ("Windows: openings measured on the envelope (breaks in the CLT walls). Height: under a beam = finished ceiling height; under a "
                          "lintel = 2.30 m (top of dimensioned doors); window without lintel 1.20 m and glazed bay 2.10 m (assumptions).",
                          "Вікна: прорізи виміряні по оболонці (розриви стін CLT). Висота: під балкою = чиста висота; під перемичкою = 2,30 м "
                          "(верх дверей з розмірами); вікно без перемички 1,20 м, засклений проріз 2,10 м (припущення).")),
    (r"Uma porta de entrada .*", ("One entrance door (the plan does not identify it). Internal doors = numbered Dv doors on the plan.",
                                  "Одні вхідні двері (на плані не позначені). Внутрішні двері = пронумеровані двері Dv на плані.")),
]


def tr(text, lang):
    """Translate one printed text (PT → en/uk); unknown company texts stay unchanged."""
    if lang not in ("en", "uk") or text is None:
        return text
    i = 0 if lang == "en" else 1
    text = str(text)
    if text in T:
        return T[text][i]
    if text in SOURCES:
        return SOURCES[text][i]
    for pattern, out in NOTES:
        m = re.fullmatch(pattern, text)
        if m:
            return out[i].format(*m.groups())
    if " · " in text and all(p in SOURCES for p in text.split(" · ")):
        return " · ".join(SOURCES[p][i] for p in text.split(" · "))
    out = text
    for k in _PH:
        out = out.replace(k, PHRASES[k][i])
    return out


def unit(u, lang):
    return UNITS[u][0 if lang == "en" else 1] if lang in ("en", "uk") and u in UNITS else u


def item_name(code, name, lang, standard):
    if lang in ("en", "uk") and code in ITEMS and name == standard:
        return ITEMS[code][0 if lang == "en" else 1]
    return name


def param_label(key, label, lang, standard):
    if lang in ("en", "uk") and key in PARAMS and label == standard:
        return PARAMS[key][0 if lang == "en" else 1]
    return label


def page_dictionary(lang):
    """Portuguese text → translation for the CLT page: fixed dossier texts, parameter labels, standard library item
    names, categories and sources (the page shows the same labels the dossier prints)."""
    if lang not in ("en", "uk"):
        return {}
    from bim_studio.clt_economics import CATALOGUE, CATEGORIES, library_defaults

    i = 0 if lang == "en" else 1
    out = {k: v[i] for table in (T, FIT, UNITS, SOURCES) for k, v in table.items()}
    out.update({label: PARAMS[key][i] for key, (_g, label, *_rest) in CATALOGUE.items() if key in PARAMS})
    out.update({item["name"]: ITEMS[code][i] for code, item in library_defaults().items() if code in ITEMS})
    out.update({label: T[label][i] for label in CATEGORIES.values() if label in T})
    return out
