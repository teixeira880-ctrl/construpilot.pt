"""Traduções das peças desenhadas de gros-œuvre (planos GO-xx) — ucraniano e inglês.
Chaves = textos portugueses gerados por gros_oeuvre.py (substituição da chave mais longa para a mais curta)."""

_UK = {
    # títulos das folhas
    "PLANTA DE FUNDAÇÕES COTADA": "ПЛАН ФУНДАМЕНТІВ З РОЗМІРАМИ",
    "PLANTA ESTRUTURAL DO PAVIMENTO": "ПЛАН КОНСТРУКЦІЙ ПЕРЕКРИТТЯ",
    "PLANTA DE ESTRUTURA DA COBERTURA": "ПЛАН КОНСТРУКЦІЙ ПОКРИТТЯ",
    "CORTES CONSTRUTIVOS COTADOS": "КОНСТРУКТИВНІ РОЗРІЗИ З РОЗМІРАМИ",
    "QUADROS DE ELEMENTOS, VERIFICAÇÕES E AJUSTES": "ВІДОМОСТІ ЕЛЕМЕНТІВ, ПЕРЕВІРКИ ТА КОРИГУВАННЯ",
    "Sapatas isoladas e contínuas, muros de fundação, lajes térreas": "Окремі та стрічкові фундаменти, фундаментні стіни, плити по ґрунту",
    "Vigas, pilares, lajes / painéis e paredes de apoio": "Балки, колони, плити / панелі та опорні стіни",
    "Sapatas, muros, pilares, vigas, lajes / painéis com níveis absolutos": "Фундаменти, стіни, колони, балки, плити / панелі з абсолютними позначками",
    "Resultados dos motores ConstruPilot (NP EN 1992 / 1995 / 1997) — secções adotadas = secções desenhadas":
        "Результати розрахунку ConstruPilot (ДСТУ-Н Б EN 1992 / 1995 / 1997) — прийняті перерізи = накреслені перерізи",
    "cotas em mm, níveis em m": "розміри в мм, позначки в м",
    "escala": "масштаб",
    # cartucho
    "Gabinete de projeto digital · Portugal": "Цифрове проєктне бюро · Україна",
    "Projeto de execução — pré-dimensionamento por motores ConstruPilot, a validar pelo projetista de estruturas.":
        "Робоча документація — попередній розрахунок ConstruPilot, підлягає перевірці інженером-конструктором.",
    "Obra:": "Об'єкт:", "Local:": "Місце:", "Escala": "Масштаб", "Desenho": "Креслення", "Folha": "Аркуш", "Data": "Дата", "Formato": "Формат",
    "Gros-œuvre — planta de fundações": "Несучі конструкції — план фундаментів",
    "Gros-œuvre — planta estrutural do pavimento": "Несучі конструкції — план перекриття",
    "Gros-œuvre — planta de estrutura da cobertura": "Несучі конструкції — план покриття",
    "Gros-œuvre — cortes construtivos": "Несучі конструкції — розрізи",
    "Gros-œuvre — quadros e verificações": "Несучі конструкції — відомості та перевірки",
    # quadros
    "Dimensões (m)": "Розміри (м)", "Armadura inferior A500": "Нижня арматура A500C", "Secção original (se ajustada)": "Початковий переріз (якщо змінено)",
    "Secção adotada": "Прийнятий переріз", "Secção": "Переріз", "Elemento": "Елемент", "Estado": "Статус", "Taxa": "Викор.", "Tipo": "Тип",
    "Ref.": "Марка", "h (m)": "h (м)",
    "NÃO conforme": "НЕ відповідає", "conforme": "відповідає",
    "Ajustes automáticos": "Автоматичні коригування",
    "Nenhum: todos os elementos verificam com as secções do projeto.": "Немає: усі елементи задовольняють перевірки з проєктними перерізами.",
    "Hipóteses / a validar": "Припущення / для перевірки",
    "Pré-dimensionamento por motores determinísticos — a validar pelo projetista de estruturas antes da execução.":
        "Попередній розрахунок детермінованими модулями — підлягає перевірці інженером-конструктором до будівництва.",
    "Secções ajustadas pelo motor (desenhadas aqui):": "Перерізи, змінені розрахунком (показані на кресленні):",
    # notas da planta de fundações
    "Notas: betão C25/30 XC2, recobrimento 50 mm (75 mm contra o terreno), betão de limpeza C12/15 50 mm. ":
        "Примітки: бетон C25/30, захисний шар 50 мм (75 мм біля ґрунту), бетонна підготовка C12/15 товщ. 50 мм. ",
    "Tensão admissível do terreno": "Розрахунковий опір ґрунту",
    "(a confirmar pelo estudo geotécnico).": "(підтвердити інженерно-геологічними вишукуваннями).",
    "Topo das sapatas:": "Верх фундаментів:",
    "Sapatas centradas nos eixos dos pilares e muros salvo cota em contrário.": "Фундаменти центровані по осях колон і стін, якщо не вказано інше.",
    # cortes e etiquetas
    "CORTE": "РОЗРІЗ", "LONGITUDINAL": "ПОЗДОВЖНІЙ", "TRANSVERSAL": "ПОПЕРЕЧНИЙ",
    "laje térrea": "плита по ґрунту", "laje BA": "з/б плита", "vigas I": "двотаврові балки", "T.O.S.": "верх плити", "topo ": "верх ",
    "c/ direção": "в кожному напрямку", "contínuos": "безперервні", "contínua": "стрічковий", "long.": "поздовж.", "transv.": "попер.",
    "(mínimo)": "(мінімум)", "nível 1": "рівень 1",
    # elementos e secções (motores)
    "Viga de madeira": "Дерев'яна балка", "Viga de betão armado": "Залізобетонна балка", "Pilar de madeira": "Дерев'яна колона",
    "Pilar de betão armado": "Залізобетонна колона", "Laje de BA armada em duas direções": "З/б плита, армована у двох напрямках",
    "Sapata contínua (por metro)": "Стрічковий фундамент (на 1 м)", "Sapata isolada": "Окремий фундамент",
    "sapata contínua": "стрічк. фундамент", "Sapata contínua": "Стрічковий фундамент", "sapata": "фундамент", "Sapata": "Фундамент",
    "viga": "балка", "Viga": "Балка", "pilar": "колона", "Pilar": "Колона", "laje": "плита",
    "vão": "проліт", "taxa": "викор.",
    "Painel CLT (motor bet_clt_ua)": "Панель CLT (модуль bet_clt_ua)", "painel CLT": "панель CLT", "Painel CLT": "Панель CLT",
    " camadas": " шарів",
    "Painéis CLT: propriedades C24 típicas (EN 338 / EN 16351, f_r,k 1,1 MPa, G_R 50 MPa) — substituir pelos valores da ETA do fabricante; vibração dos pavimentos (NP EN 1995-1-1 §7.3), ligações, estabilidade lateral e fogo não verificados aqui":
        "Панелі CLT: типові властивості C24 (EN 338 / EN 16351, f_r,k 1,1 МПа, G_R 50 МПа) — замінити значеннями ETA виробника; вібрацію перекриттів (EN 1995-1-1 §7.3), вузли, просторову стійкість і вогнестійкість тут не перевірено",
    "; vibração, ligações, estabilidade lateral, integridade e isolamento ao fogo (E, I) não verificados aqui":
        "; вібрацію, вузли, просторову стійкість, цілісність і теплоізоляцію при пожежі (E, I) тут не перевірено",
    ": valores declarados na ": ": задекларовані значення за ", "f_R,k pela figura 3 da ETA": "f_R,k за рис. 3 ETA",
    "carbonização": "обвуглювання", "Painéis ": "Панелі ", " MPa": " МПа",
    "PLANTA DE PAREDES PORTANTES": "ПЛАН НЕСУЧИХ СТІН", "Paredes estruturais com espessura, material e comprimento de cada troço":
        "Несучі стіни: товщина, матеріал і довжина кожної ділянки", "ALÇADOS ESTRUTURAIS COTADOS": "ФАСАДИ З ПОЗНАЧКАМИ",
    "Volumes das paredes portantes, lajes e coberturas, com níveis absolutos": "Об'єми несучих стін, перекриттів і покриттів з абсолютними позначками",
    "ALÇADO ": "ФАСАД ", "SUL / ПІВДЕНЬ": "ПІВДЕННИЙ", "NORTE / ПІВНІЧ": "ПІВНІЧНИЙ", "OESTE / ЗАХІД": "ЗАХІДНИЙ", "ESTE / СХІД": "СХІДНИЙ",
    "Gros-œuvre — paredes ": "Несучі конструкції — стіни ", "Gros-œuvre — alçados": "Несучі конструкції — фасади",
    "Comprimento total de paredes": "Загальна довжина стін", "Área bruta de paredes": "Площа стін (брутто)", "Volume bruto": "Об'єм (брутто)",
    "Grandeza": "Показник", "Valor": "Значення", "Altura": "Висота", "base ": "низ ", " · topo ": " · верх ", "Alvenaria": "Кладка",
    "Notas: vãos de portas e janelas conforme o projeto de arquitetura (não representados); ligações parede / laje e parede / fundação com cantoneiras e chapas perfuradas conforme ETA dos ligadores; juntas entre painéis com tira de contraplacado e parafusos.":
        "Примітки: дверні та віконні прорізи — за архітектурним проєктом (не показані); вузли стіна / перекриття і стіна / фундамент — кутики та перфоровані пластини за ETA кріплень; стики панелей — смуга фанери та шурупи.",
    "(alçados a 1:": "(фасади в масштабі 1:",
}

_EN = {
    "PLANTA DE FUNDAÇÕES COTADA": "DIMENSIONED FOUNDATION PLAN",
    "PLANTA ESTRUTURAL DO PAVIMENTO": "FLOOR FRAMING PLAN",
    "PLANTA DE ESTRUTURA DA COBERTURA": "ROOF FRAMING PLAN",
    "CORTES CONSTRUTIVOS COTADOS": "DIMENSIONED STRUCTURAL SECTIONS",
    "QUADROS DE ELEMENTOS, VERIFICAÇÕES E AJUSTES": "ELEMENT SCHEDULES, CHECKS AND ADJUSTMENTS",
    "Sapatas isoladas e contínuas, muros de fundação, lajes térreas": "Pad and strip footings, foundation walls, ground slabs",
    "Vigas, pilares, lajes / painéis e paredes de apoio": "Beams, columns, slabs / panels and bearing walls",
    "Sapatas, muros, pilares, vigas, lajes / painéis com níveis absolutos": "Footings, walls, columns, beams, slabs / panels with absolute levels",
    "Resultados dos motores ConstruPilot (NP EN 1992 / 1995 / 1997) — secções adotadas = secções desenhadas":
        "ConstruPilot engine results (EN 1992 / 1995 / 1997) — adopted sections = drawn sections",
    "cotas em mm, níveis em m": "dimensions in mm, levels in m", "escala": "scale",
    "Gabinete de projeto digital · Portugal": "Digital design office",
    "Projeto de execução — pré-dimensionamento por motores ConstruPilot, a validar pelo projetista de estruturas.":
        "Construction drawings — ConstruPilot preliminary design, to be checked by the structural engineer.",
    "Obra:": "Project:", "Local:": "Site:", "Escala": "Scale", "Desenho": "Drawing", "Folha": "Sheet", "Data": "Date", "Formato": "Size",
    "Gros-œuvre — planta de fundações": "Structure — foundation plan", "Gros-œuvre — planta estrutural do pavimento": "Structure — floor framing",
    "Gros-œuvre — planta de estrutura da cobertura": "Structure — roof framing", "Gros-œuvre — cortes construtivos": "Structure — sections",
    "Gros-œuvre — quadros e verificações": "Structure — schedules and checks",
    "Dimensões (m)": "Size (m)", "Armadura inferior A500": "Bottom rebar B500", "Secção original (se ajustada)": "Original section (if adjusted)",
    "Secção adotada": "Adopted section", "Secção": "Section", "Elemento": "Element", "Estado": "Status", "Taxa": "Util.", "Tipo": "Type",
    "Ref.": "Mark", "h (m)": "h (m)", "NÃO conforme": "NOT compliant", "conforme": "compliant",
    "Ajustes automáticos": "Automatic adjustments",
    "Nenhum: todos os elementos verificam com as secções do projeto.": "None: all elements pass with the design sections.",
    "Hipóteses / a validar": "Assumptions / to be confirmed",
    "Pré-dimensionamento por motores determinísticos — a validar pelo projetista de estruturas antes da execução.":
        "Preliminary design by deterministic engines — to be checked by the structural engineer before construction.",
    "Secções ajustadas pelo motor (desenhadas aqui):": "Sections adjusted by the engine (drawn here):",
    "Notas: betão C25/30 XC2, recobrimento 50 mm (75 mm contra o terreno), betão de limpeza C12/15 50 mm. ":
        "Notes: concrete C25/30, cover 50 mm (75 mm against soil), C12/15 blinding 50 mm. ",
    "Tensão admissível do terreno": "Allowable soil pressure", "(a confirmar pelo estudo geotécnico).": "(to be confirmed by the geotechnical survey).",
    "Topo das sapatas:": "Top of footings:", "Sapatas centradas nos eixos dos pilares e muros salvo cota em contrário.": "Footings centred on column and wall axes unless dimensioned otherwise.",
    "CORTE": "SECTION", "LONGITUDINAL": "LONGITUDINAL", "TRANSVERSAL": "TRANSVERSE",
    "laje térrea": "ground slab", "laje BA": "RC slab", "vigas I": "I-joists", "T.O.S.": "T.O.S.", "topo ": "top ",
    "c/ direção": "each way", "contínuos": "continuous", "contínua": "strip", "long.": "long.", "transv.": "transv.", "(mínimo)": "(minimum)",
    "nível 1": "level 1",
    "Viga de madeira": "Timber beam", "Viga de betão armado": "RC beam", "Pilar de madeira": "Timber column", "Pilar de betão armado": "RC column",
    "Laje de BA armada em duas direções": "Two-way RC slab", "Sapata contínua (por metro)": "Strip footing (per metre)", "Sapata isolada": "Pad footing",
    "sapata contínua": "strip footing", "Sapata contínua": "Strip footing", "sapata": "footing", "Sapata": "Footing",
    "viga": "beam", "Viga": "Beam", "pilar": "column", "Pilar": "Column", "laje": "slab", "vão": "span", "taxa": "util.",
    "Painel CLT (motor bet_clt_ua)": "CLT panel (bet_clt_ua engine)", "painel CLT": "CLT panel", "Painel CLT": "CLT panel",
    " camadas": " layers",
    "Painéis CLT: propriedades C24 típicas (EN 338 / EN 16351, f_r,k 1,1 MPa, G_R 50 MPa) — substituir pelos valores da ETA do fabricante; vibração dos pavimentos (NP EN 1995-1-1 §7.3), ligações, estabilidade lateral e fogo não verificados aqui":
        "CLT panels: typical C24 properties (EN 338 / EN 16351, f_r,k 1.1 MPa, G_R 50 MPa) — replace with the manufacturer's ETA values; floor vibration (EN 1995-1-1 §7.3), connections, lateral stability and fire not checked here",
    "; vibração, ligações, estabilidade lateral, integridade e isolamento ao fogo (E, I) não verificados aqui":
        "; vibration, connections, lateral stability, fire integrity and insulation (E, I) not checked here",
    ": valores declarados na ": ": declared values from ", "f_R,k pela figura 3 da ETA": "f_R,k from ETA figure 3",
    "carbonização": "charring", "Painéis ": "Panels ",
    "PLANTA DE PAREDES PORTANTES": "LOAD-BEARING WALL PLAN", "ALÇADOS ESTRUTURAIS COTADOS": "DIMENSIONED STRUCTURAL ELEVATIONS", "ALÇADO ": "ELEVATION ",
    "Gros-œuvre — paredes ": "Structure — walls ", "Gros-œuvre — alçados": "Structure — elevations",
    "SUL / ПІВДЕНЬ": "SOUTH", "NORTE / ПІВНІЧ": "NORTH", "OESTE / ЗАХІД": "WEST", "ESTE / СХІД": "EAST",
    "Paredes estruturais com espessura, material e comprimento de cada troço": "Load-bearing walls: thickness, material and length of each segment",
    "Volumes das paredes portantes, lajes e coberturas, com níveis absolutos": "Load-bearing walls, floors and roofs with absolute levels",
    "Comprimento total de paredes": "Total wall length", "Área bruta de paredes": "Gross wall area", "Volume bruto": "Gross volume",
    "Grandeza": "Quantity", "Valor": "Value", "Altura": "Height", "base ": "base ", " · topo ": " · top ", "Alvenaria": "Masonry", "Газобетон": "AAC",
    "Notas: vãos de portas e janelas conforme o projeto de arquitetura (não representados); ligações parede / laje e parede / fundação com cantoneiras e chapas perfuradas conforme ETA dos ligadores; juntas entre painéis com tira de contraplacado e parafusos.":
        "Notes: door and window openings per the architectural design (not shown); wall / floor and wall / foundation connections with angle brackets and perforated plates per the fasteners' ETA; panel joints with plywood spline and screws.",
    "(alçados a 1:": "(elevations at 1:",
}

_UK.update({'Coberturas sem sobrecarga indicada: ': 'Покриття без заданого корисного навантаження: ', ' kN/m² (EN 1991-1-1, categoria H — não acessível, ψ2 = 0)': ' кН/м² (EN 1991-1-1, категорія H — неексплуатоване, ψ2 = 0)', 'Terraços sem sobrecarga indicada: ': 'Експлуатовані покрівлі (тераси) без заданого навантаження: ', ' kN/m² (EN 1991-1-1, categoria I — acessível, uso habitacional, ψ2 = 0,3)': ' кН/м² (EN 1991-1-1, категорія I — експлуатована, житлове призначення, ψ2 = 0,3)', 'Coberturas: a neve condiciona a sobrecarga (não combinada com a sobrecarga de utilização, EN 1991-1-1 §3.3.2)': 'Покриття: визначальне навантаження — сніг (не поєднується з корисним навантаженням на покрівлю, EN 1991-1-1 §3.3.2)', 'Neve na cobertura: ': 'Сніг на покритті: ', ' kN/m² (valor de cálculo do local)': ' кН/м² (розрахункове значення для місця будівництва)'})
_EN.update({'Coberturas sem sobrecarga indicada: ': 'Roofs without a specified imposed load: ', ' kN/m² (EN 1991-1-1, categoria H — não acessível, ψ2 = 0)': ' kN/m² (EN 1991-1-1, category H — not accessible, ψ2 = 0)', 'Terraços sem sobrecarga indicada: ': 'Roof terraces without a specified load: ', ' kN/m² (EN 1991-1-1, categoria I — acessível, uso habitacional, ψ2 = 0,3)': ' kN/m² (EN 1991-1-1, category I — accessible, residential use, ψ2 = 0.3)', 'Coberturas: a neve condiciona a sobrecarga (não combinada com a sobrecarga de utilização, EN 1991-1-1 §3.3.2)': 'Roofs: snow governs (not combined with the roof imposed load, EN 1991-1-1 §3.3.2)', 'Neve na cobertura: ': 'Snow on roof: ', ' kN/m² (valor de cálculo do local)': ' kN/m² (design value for the site)'})
TRADUCOES = {"uk": _UK, "en": _EN}
