"""Texts of the common take-off dossier and drawings: Portuguese source, English, Ukrainian and French.

A text without translation is shown in Portuguese (never dropped), so a new rule cannot hide a number.
"""
from __future__ import annotations

# PT → (EN, UK, FR)
T = {
    # headings and table columns
    "Dossier de medições e orçamento": ("Take-off and estimate dossier", "Досьє обмірів і кошторису", "Dossier de métrés et de chiffrage"),
    "métodos ConstruPilot comuns a todas as construções": ("ConstruPilot methods common to every building", "методи ConstruPilot, спільні для всіх будівель", "méthodes ConstruPilot communes à toutes les constructions"),
    "página": ("page", "сторінка", "page"),
    "paredes, área líquida": ("walls, net area", "стіни, чиста площа", "murs, surface nette"),
    "paredes, volume": ("walls, volume", "стіни, об'єм", "murs, volume"),
    "vãos": ("openings", "прорізи", "baies"),
    "total sem IVA": ("total excl. VAT", "разом без ПДВ", "total HT"),
    "sem biblioteca de preços": ("no price library", "без бібліотеки цін", "sans bibliothèque de prix"),
    "Verificações cruzadas": ("Cross-checks", "Перехресні перевірки", "Contrôles croisés"),
    "todas dentro da tolerância": ("all within tolerance", "усі в межах допуску", "tous dans la tolérance"),
    "há verificações fora da tolerância: ver secção 4": ("some checks are out of tolerance: see section 4", "є перевірки поза допуском: див. розділ 4", "des contrôles sont hors tolérance : voir section 4"),
    "Cada número indica a sua origem: medido no desenho, regra com valor publicado ou da empresa, ou estimativa (hipótese, altura standard, vão inferido). O Anexo A mostra os desenhos cotados de onde vêm as medidas.":
        ("Every figure states its origin: measured on the drawing, rule with a published or company value, or estimate (hypothesis, standard height, inferred opening). Annex A shows the dimensioned drawings the measurements come from.",
         "Кожне число має походження: виміряно на кресленні, правило з опублікованим значенням або значенням компанії, чи оцінка (гіпотеза, стандартна висота, виведений проріз). Додаток A містить креслення з розмірами, з яких узято обміри.",
         "Chaque chiffre indique son origine : mesuré sur le plan, règle avec une valeur publiée ou de l'entreprise, ou estimation (hypothèse, hauteur standard, baie déduite). L'annexe A montre les plans cotés d'où viennent les mesures."),
    "Método": ("Method", "Метод", "Méthode"),
    "Alturas: as do projeto; sem alturas na planta, RDC 3,00 m e outros pisos 2,50 m, marcadas «standard».":
        ("Heights: those of the project; when the plan gives none, ground floor 3.00 m and other floors 2.50 m, marked \"standard\".",
         "Висоти: з проєкту; якщо на плані їх немає, перший поверх 3,00 м, інші поверхи 2,50 м, позначені «стандарт».",
         "Hauteurs : celles du projet ; sans hauteur sur le plan, RDC 3,00 m et autres niveaux 2,50 m, marquées « standard »."),
    "Rede de paredes: cada extremo que encosta a outra parede vai ao eixo dela; troços alinhados sob um lintel (desenhado ou inferido de um intervalo) passam a uma peça com o vão recortado.":
        ("Wall network: every end that meets another wall goes to its axis; aligned runs under a lintel (drawn, or inferred from a gap) become one piece with the opening cut out.",
         "Мережа стін: кожен кінець, що впирається в іншу стіну, доводиться до її осі; вирівняні ділянки під перемичкою (накресленою або виведеною з проміжку) стають однією деталлю з вирізаним прорізом.",
         "Réseau de murs : chaque extrémité qui bute sur un autre mur va à son axe ; les tronçons alignés sous un linteau (dessiné ou déduit d'un intervalle) deviennent une pièce avec la baie découpée."),
    "Peças: juntas L, T e X resolvidas sem contagem dupla (num T a parede que encosta é cortada; num L ou X a mais longa passa); divisão ao formato de produção nos sistemas pré-fabricados.":
        ("Pieces: L, T and X junctions resolved without double count (at a T the abutting wall is cut; at an L or X the longer one runs through); split at the production format for prefabricated systems.",
         "Деталі: з'єднання L, T і X без подвійного підрахунку (у T примикаюча стіна обрізається; у L чи X довша проходить); поділ за виробничим форматом для збірних систем.",
         "Pièces : jonctions L, T et X résolues sans double compte (en T le mur qui bute est coupé ; en L ou X le plus long passe) ; découpe au format de production pour les systèmes préfabriqués."),
    "Quantidades: regra de cada sistema construtivo aplicada à geometria medida; cada parâmetro tem origem e fonte e é editável pela empresa.":
        ("Quantities: the rule of each construction system applied to the measured geometry; every parameter has an origin and a source and is editable by the company.",
         "Кількості: правило кожної конструктивної системи, застосоване до виміряної геометрії; кожен параметр має походження і джерело та редагується компанією.",
         "Quantités : règle de chaque système constructif appliquée à la géométrie mesurée ; chaque paramètre a une origine et une source et est modifiable par l'entreprise."),
    "Verificações: dois métodos independentes têm de concordar dentro da tolerância (volume das peças vs união exata das plantas; área bruta − vãos vs área líquida).":
        ("Checks: two independent methods must agree within tolerance (piece volume vs exact union of the footprints; gross area − openings vs net area).",
         "Перевірки: два незалежні методи мають збігатися в межах допуску (об'єм деталей проти точного об'єднання контурів; площа брутто − прорізи проти чистої площі).",
         "Contrôles : deux méthodes indépendantes doivent concorder dans la tolérance (volume des pièces vs union exacte des emprises ; surface brute − baies vs surface nette)."),
    "Preços: biblioteca da empresa, cada preço com a sua fonte; quantidades sem preço ficam listadas.":
        ("Prices: the company library, each price with its source; quantities without a price are listed.",
         "Ціни: бібліотека компанії, кожна ціна з джерелом; кількості без ціни перелічено.",
         "Prix : bibliothèque de l'entreprise, chaque prix avec sa source ; les quantités sans prix sont listées."),
    "Origem": ("Origin", "Походження", "Origine"),
    "Significado": ("Meaning", "Значення", "Signification"),
    "Pisos e alturas": ("Floors and heights", "Поверхи і висоти", "Niveaux et hauteurs"),
    "Piso": ("Floor", "Поверх", "Niveau"),
    "Leitura": ("Reading", "Зчитування", "Lecture"),
    "Altura": ("Height", "Висота", "Hauteur"),
    "Fonte": ("Source", "Джерело", "Source"),
    "Quantidades por piso": ("Quantities per floor", "Кількості за поверхами", "Quantités par niveau"),
    "Designação": ("Item", "Позиція", "Désignation"),
    "Sistema": ("System", "Система", "Système"),
    "Quantidade": ("Quantity", "Кількість", "Quantité"),
    "Un.": ("Unit", "Од.", "U."),
    "Totais do projeto": ("Project totals", "Підсумки проєкту", "Totaux du projet"),
    "Verificação": ("Check", "Перевірка", "Contrôle"),
    "Método A": ("Method A", "Метод A", "Méthode A"),
    "Método B": ("Method B", "Метод B", "Méthode B"),
    "Erro": ("Error", "Похибка", "Écart"),
    "Resultado": ("Result", "Результат", "Résultat"),
    "informativo": ("for information", "довідково", "informatif"),
    "dentro da tolerância": ("within tolerance", "у межах допуску", "dans la tolérance"),
    "FORA da tolerância": ("OUT of tolerance", "ПОЗА допуском", "HORS tolérance"),
    "Orçamento": ("Estimate", "Кошторис", "Chiffrage"),
    "Qtd.": ("Qty", "К-сть", "Qté"),
    "Preço un.": ("Unit price", "Ціна од.", "Prix u."),
    "Total": ("Total", "Разом", "Total"),
    "Fonte do preço": ("Price source", "Джерело ціни", "Source du prix"),
    "Subtotal sem IVA": ("Subtotal excl. VAT", "Підсумок без ПДВ", "Sous-total HT"),
    "IVA": ("VAT", "ПДВ", "TVA"),
    "Total com IVA": ("Total incl. VAT", "Разом з ПДВ", "Total TTC"),
    "Parte do total que depende de estimativas": ("Part of the total that depends on estimates", "Частина суми, що залежить від оцінок", "Part du total qui dépend d'estimations"),
    "Quantidades sem preço na biblioteca (não incluídas no total)": ("Quantities without a library price (not in the total)", "Кількості без ціни в бібліотеці (не входять у суму)", "Quantités sans prix en bibliothèque (hors total)"),
    "Sem biblioteca de preços: o dossier apresenta só as quantidades. Importe a biblioteca da empresa para obter o orçamento.":
        ("No price library: the dossier shows quantities only. Import the company library to get the estimate.",
         "Без бібліотеки цін: досьє показує лише кількості. Імпортуйте бібліотеку компанії, щоб отримати кошторис.",
         "Sans bibliothèque de prix : le dossier ne présente que les quantités. Importez la bibliothèque de l'entreprise pour obtenir le chiffrage."),
    "Hipóteses e valores standard a confirmar": ("Hypotheses and standard values to confirm", "Гіпотези і стандартні значення для підтвердження", "Hypothèses et valeurs standard à confirmer"),
    "Parâmetro": ("Parameter", "Параметр", "Paramètre"),
    "Valor": ("Value", "Значення", "Valeur"),
    "Todos estes valores são editáveis pela empresa; um valor da empresa passa a «regra» com a fonte indicada.":
        ("All these values are editable by the company; a company value becomes a \"rule\" with the stated source.",
         "Усі ці значення редагує компанія; значення компанії стає «правилом» із зазначеним джерелом.",
         "Toutes ces valeurs sont modifiables par l'entreprise ; une valeur de l'entreprise devient « règle » avec la source indiquée."),
    "Medições por peça": ("Measurements per piece", "Обміри за деталями", "Métrés par pièce"),
    "Peça": ("Piece", "Деталь", "Pièce"),
    "Comp. m": ("Length m", "Довж. м", "Long. m"),
    "Alt. m": ("Height m", "Вис. м", "Haut. m"),
    "Esp. mm": ("Thick. mm", "Товщ. мм", "Ép. mm"),
    "Líquida m²": ("Net m²", "Чиста м²", "Nette m²"),
    "Volume m³": ("Volume m³", "Об'єм м³", "Volume m³"),
    "Vãos": ("Openings", "Прорізи", "Baies"),
    "Vãos inferidos de intervalos entre troços (a confirmar)": ("Openings inferred from gaps between runs (to confirm)", "Прорізи, виведені з проміжків між ділянками (підтвердити)", "Baies déduites des intervalles entre tronçons (à confirmer)"),
    "Anexo A · Desenhos cotados": ("Annex A · Dimensioned drawings", "Додаток A · Креслення з розмірами", "Annexe A · Plans cotés"),
    "Os desenhos seguintes foram gerados a partir da mesma geometria das medições: cada comprimento, altura e vão do dossier pode ser lido neles. Cotas em milímetros, escala indicada em cada folha.":
        ("The following drawings were generated from the same geometry as the measurements: every length, height and opening in the dossier can be read on them. Dimensions in millimetres, scale stated on each sheet.",
         "Наступні креслення створено з тієї самої геометрії, що й обміри: кожну довжину, висоту і проріз досьє можна на них прочитати. Розміри в міліметрах, масштаб зазначено на кожному аркуші.",
         "Les plans suivants sont générés à partir de la même géométrie que les métrés : chaque longueur, hauteur et baie du dossier peut y être lue. Cotes en millimètres, échelle indiquée sur chaque feuille."),
    "Folha": ("Sheet", "Аркуш", "Feuille"),
    "Conteúdo": ("Content", "Зміст", "Contenu"),
    "altura": ("height", "висота", "hauteur"),
    # drawings
    "planta das paredes, cotada (mm)": ("wall plan, dimensioned (mm)", "план стін з розмірами (мм)", "plan des murs coté (mm)"),
    "planta das paredes, cotada": ("wall plan, dimensioned", "план стін з розмірами", "plan des murs coté"),
    "alçados das paredes, cotados": ("wall elevations, dimensioned", "розгортки стін з розмірами", "élévations des murs cotées"),
    "Escala": ("Scale", "Масштаб", "Échelle"),
    "cotas em mm": ("dimensions in mm", "розміри в мм", "cotes en mm"),
    "folha": ("sheet", "аркуш", "feuille"),
    "líquida": ("net", "чиста", "nette"),
    "Desenho cotado gerado pela ConstruPilot a partir das medições. Não substitui o projeto de execução.":
        ("Dimensioned drawing generated by ConstruPilot from the measurements. It does not replace the execution drawings.",
         "Креслення з розмірами створене ConstruPilot з обмірів. Не замінює робочий проєкт.",
         "Plan coté généré par ConstruPilot à partir des métrés. Il ne remplace pas les plans d'exécution."),
    # rules (method column)
    "Σ comprimento das peças após resolução das juntas (sem contagem dupla)": ("Σ piece lengths after junction resolution (no double count)", "Σ довжин деталей після розв'язання з'єднань (без подвійного підрахунку)", "Σ longueurs des pièces après résolution des jonctions (sans double compte)"),
    "Σ comprimento × altura das peças": ("Σ piece length × height", "Σ довжина × висота деталей", "Σ longueur × hauteur des pièces"),
    "Σ largura × altura dos vãos": ("Σ opening width × height", "Σ ширина × висота прорізів", "Σ largeur × hauteur des baies"),
    "área bruta − vãos": ("gross area − openings", "площа брутто − прорізи", "surface brute − baies"),
    "Σ área líquida × espessura": ("Σ net area × thickness", "Σ чиста площа × товщина", "Σ surface nette × épaisseur"),
    "peças de produção (num T a parede que encosta é cortada)": ("production pieces (at a T the abutting wall is cut)", "виробничі деталі (у T примикаюча стіна обрізається)", "pièces de production (en T le mur qui bute est coupé)"),
    "volume líquido das peças CLT": ("net volume of the CLT pieces", "чистий об'єм деталей CLT", "volume net des pièces CLT"),
    "área líquida de alvenaria (vãos deduzidos)": ("net masonry area (openings deducted)", "чиста площа кладки (прорізи вираховано)", "surface nette de maçonnerie (baies déduites)"),
    "área líquida × 1/((C+j)×(A+j)) × (1 + perdas)": ("net area × 1/((L+j)×(H+j)) × (1 + waste)", "чиста площа × 1/((Д+ш)×(В+ш)) × (1 + втрати)", "surface nette × 1/((L+j)×(H+j)) × (1 + pertes)"),
    "área líquida × consumo": ("net area × consumption", "чиста площа × витрата", "surface nette × consommation"),
    "Σ (largura do vão + 2 × entrega)": ("Σ (opening width + 2 × bearing)", "Σ (ширина прорізу + 2 × опирання)", "Σ (largeur de baie + 2 × appui)"),
    "área líquida × faces revestidas": ("net area × finished faces", "чиста площа × оздоблені сторони", "surface nette × faces enduites"),
    "volume líquido × (1 + perdas)": ("net volume × (1 + waste)", "чистий об'єм × (1 + втрати)", "volume net × (1 + pertes)"),
    "2 faces × área líquida + contornos dos vãos × espessura": ("2 faces × net area + opening reveals × thickness", "2 сторони × чиста площа + укоси прорізів × товщина", "2 faces × surface nette + tableaux des baies × épaisseur"),
    "volume líquido × taxa de armadura (orçamento, não dimensionamento)": ("net volume × steel ratio (pricing, not design)", "чистий об'єм × норма армування (кошторис, не розрахунок)", "volume net × ratio d'acier (chiffrage, pas dimensionnement)"),
    "Σ (comprimento ÷ entre-eixo + 1) + 2 por vão": ("Σ (length ÷ spacing + 1) + 2 per opening", "Σ (довжина ÷ крок + 1) + 2 на проріз", "Σ (longueur ÷ entraxe + 1) + 2 par baie"),
    "montantes × altura da parede": ("studs × wall height", "стійки × висота стіни", "montants × hauteur du mur"),
    "2 × comprimento (guia inferior e superior) + padieiras e peitoris": ("2 × length (bottom and top track) + headers and sills", "2 × довжина (нижня і верхня напрямна) + перемички і підвіконня", "2 × longueur (lisse basse et haute) + linteaux et appuis"),
    "área líquida × faces com placa": ("net area × boarded faces", "чиста площа × обшиті сторони", "surface nette × faces parementées"),
    "área líquida (caixa entre montantes)": ("net area (cavity between studs)", "чиста площа (порожнина між стійками)", "surface nette (caisson entre montants)"),
    "Σ área das divisões (polígono)": ("Σ room areas (polygon)", "Σ площ приміщень (полігон)", "Σ surfaces des pièces (polygone)"),
    "igual ao pavimento (teto plano)": ("equal to the floor (flat ceiling)", "дорівнює підлозі (пласка стеля)", "égal au sol (plafond plat)"),
    "Σ perímetro das divisões (portas não deduzidas)": ("Σ room perimeters (doors not deducted)", "Σ периметрів приміщень (двері не вираховано)", "Σ périmètres des pièces (portes non déduites)"),
    "vãos contados nas peças": ("openings counted on the pieces", "прорізи, пораховані на деталях", "baies comptées sur les pièces"),
    # parameter sources
    "regra ConstruPilot quando a planta não indica alturas: RDC 3,00 m": ("ConstruPilot rule when the plan gives no height: ground floor 3.00 m", "правило ConstruPilot, коли план не дає висот: перший поверх 3,00 м", "règle ConstruPilot quand le plan n'indique pas de hauteur : RDC 3,00 m"),
    "regra ConstruPilot quando a planta não indica alturas: outros pisos 2,50 m": ("ConstruPilot rule when the plan gives no height: other floors 2.50 m", "правило ConstruPilot, коли план не дає висот: інші поверхи 2,50 м", "règle ConstruPilot quand le plan n'indique pas de hauteur : autres niveaux 2,50 m"),
    "altura de vão standard quando a cota «LxH» não está escrita (mesma regra do leitor CLT)": ("standard opening height when the \"WxH\" dimension is not written (same rule as the CLT reader)", "стандартна висота прорізу, якщо розмір «ШxВ» не написано (те саме правило, що й у зчитувача CLT)", "hauteur de baie standard quand la cote « LxH » n'est pas écrite (même règle que le lecteur CLT)"),
    "menor intervalo entre troços lido como vão": ("smallest gap between runs read as an opening", "найменший проміжок між ділянками, що читається як проріз", "plus petit intervalle entre tronçons lu comme baie"),
    "maior intervalo entre troços lido como vão": ("largest gap between runs read as an opening", "найбільший проміжок між ділянками, що читається як проріз", "plus grand intervalle entre tronçons lu comme baie"),
    "erro máximo aceite entre dois métodos independentes": ("maximum error accepted between two independent methods", "максимальна допустима похибка між двома незалежними методами", "écart maximal accepté entre deux méthodes indépendantes"),
    "camadas por omissão quando a legenda não as indica": ("default layers when the key does not state them", "шари за замовчуванням, якщо легенда їх не вказує", "plis par défaut quand la légende ne les indique pas"),
    "formato do tijolo 30×20 (confirmar no catálogo do fabricante)": ("30×20 brick format (confirm in the manufacturer's catalogue)", "формат цегли 30×20 (підтвердити в каталозі виробника)", "format de brique 30×20 (à confirmer au catalogue du fabricant)"),
    "formato do bloco 50×20 (confirmar no catálogo do fabricante)": ("50×20 block format (confirm in the manufacturer's catalogue)", "формат блока 50×20 (підтвердити в каталозі виробника)", "format de bloc 50×20 (à confirmer au catalogue du fabricant)"),
    "junta de argamassa corrente": ("usual mortar joint", "звичайний розчинний шов", "joint de mortier courant"),
    "quebras e cortes": ("breakage and cuts", "бій і підрізування", "casse et coupes"),
    "consumo de argamassa de assentamento (confirmar)": ("bedding mortar consumption (confirm)", "витрата кладкового розчину (підтвердити)", "consommation de mortier de pose (à confirmer)"),
    "entrega do lintel de cada lado do vão": ("lintel bearing on each side of the opening", "опирання перемички з кожного боку прорізу", "appui du linteau de chaque côté de la baie"),
    "reboco/estuque nas duas faces": ("render/plaster on both faces", "штукатурка з обох сторін", "enduit sur les deux faces"),
    "taxa de armadura para orçamento; não é cálculo estrutural (fora do âmbito)": ("steel ratio for pricing; not a structural calculation (out of scope)", "норма армування для кошторису; не конструктивний розрахунок (поза обсягом)", "ratio d'acier pour le chiffrage ; pas un calcul de structure (hors périmètre)"),
    "perdas de betonagem": ("concreting waste", "втрати при бетонуванні", "pertes de bétonnage"),
    "afastamento dos montantes": ("stud spacing", "крок стійок", "entraxe des montants"),
    "placas (OSB/gesso) nas duas faces": ("boards (OSB/gypsum) on both faces", "плити (OSB/гіпс) з обох сторін", "panneaux (OSB/plâtre) sur les deux faces"),
    "placas nas duas faces": ("boards on both faces", "плити з обох сторін", "plaques sur les deux faces"),
    "comprimento máximo de painel na mesa de pré-fabricação": ("maximum panel length on the prefabrication table", "максимальна довжина панелі на столі префабрикації", "longueur maximale de panneau sur la table de préfabrication"),
    "comprimento máximo de painel": ("maximum panel length", "максимальна довжина панелі", "longueur maximale de panneau"),
    "uma placa por face": ("one board per face", "одна плита на сторону", "une plaque par face"),
    "Rezult, características técnicas (clt-rezult.com/en/technical-characteristics), lido em 2026-11-11": ("Rezult, technical characteristics (clt-rezult.com/en/technical-characteristics), read 2026-11-11", "Rezult, технічні характеристики (clt-rezult.com/en/technical-characteristics), прочитано 2026-11-11", "Rezult, caractéristiques techniques (clt-rezult.com/en/technical-characteristics), lu le 2026-11-11"),
    "altura indicada no projeto": ("height given in the project", "висота, вказана в проєкті", "hauteur indiquée au projet"),
    "valor da empresa": ("company value", "значення компанії", "valeur de l'entreprise"),
}

KEYED = {
    "sistema.clt": ("CLT", "CLT", "CLT", "CLT"),
    "sistema.alvenaria_tijolo": ("Alvenaria de tijolo", "Brick masonry", "Цегляна кладка", "Maçonnerie de briques"),
    "sistema.alvenaria_bloco": ("Alvenaria de bloco", "Block masonry", "Блокова кладка", "Maçonnerie de blocs"),
    "sistema.betao_armado": ("Betão armado", "Reinforced concrete", "Залізобетон", "Béton armé"),
    "sistema.ossatura_madeira": ("Ossatura de madeira", "Timber frame", "Дерев'яний каркас", "Ossature bois"),
    "sistema.ossatura_metalica": ("Ossatura metálica leve", "Light steel frame", "Легкий сталевий каркас", "Ossature métallique légère"),
    "sistema.divisoria_gesso": ("Divisória de gesso cartonado", "Plasterboard partition", "Гіпсокартонна перегородка", "Cloison en plaques de plâtre"),
    "origem.medido": ("medido", "measured", "виміряно", "mesuré"),
    "origem.regra": ("regra", "rule", "правило", "règle"),
    "origem.estimativa": ("estimativa", "estimate", "оцінка", "estimation"),
    "origem.estimativa_imagem": ("estimativa de imagem", "image estimate", "оцінка із зображення", "estimation sur image"),
    "origem.empresa": ("regra", "rule", "правило", "règle"),
    "origem_desc.medido": ("lido no desenho (vetorial, DXF ou introduzido) e verificado por dois métodos", "read on the drawing (vector, DXF or entered) and checked by two methods", "зчитано з креслення (векторного, DXF або введеного) і перевірено двома методами", "lu sur le plan (vectoriel, DXF ou saisi) et vérifié par deux méthodes"),
    "origem_desc.regra": ("geometria medida × valor publicado (fabricante, lei) ou valor da empresa", "measured geometry × published value (manufacturer, law) or company value", "виміряна геометрія × опубліковане значення (виробник, закон) або значення компанії", "géométrie mesurée × valeur publiée (fabricant, loi) ou valeur de l'entreprise"),
    "origem_desc.estimativa": ("depende de uma hipótese editável, de uma altura standard ou de um vão inferido: a confirmar", "depends on an editable hypothesis, a standard height or an inferred opening: to confirm", "залежить від редагованої гіпотези, стандартної висоти або виведеного прорізу: підтвердити", "dépend d'une hypothèse modifiable, d'une hauteur standard ou d'une baie déduite : à confirmer"),
    "origem_desc.estimativa_imagem": ("lido numa imagem (JPG/PNG): nunca passa a medido", "read on an image (JPG/PNG): never becomes measured", "зчитано із зображення (JPG/PNG): ніколи не стає виміряним", "lu sur une image (JPG/PNG) : ne devient jamais mesuré"),
    "leitura.vetorial": ("PDF vetorial", "vector PDF", "векторний PDF", "PDF vectoriel"),
    "leitura.manual": ("introduzido", "entered", "введено", "saisi"),
    "leitura.imagem": ("imagem", "image", "зображення", "image"),
    "leitura.dxf": ("DXF/DWG", "DXF/DWG", "DXF/DWG", "DXF/DWG"),
    "verif.volume_pecas_vs_uniao": ("Volume das peças vs união exata das plantas (GEOS)", "Piece volume vs exact union of footprints (GEOS)", "Об'єм деталей проти точного об'єднання контурів (GEOS)", "Volume des pièces vs union exacte des emprises (GEOS)"),
    "verif.area_bruta_menos_vaos": ("Área bruta − vãos vs área líquida", "Gross area − openings vs net area", "Площа брутто − прорізи проти чистої площі", "Surface brute − baies vs surface nette"),
    "verif.eixos_vs_pecas": ("Eixos desenhados vs peças (contagem dupla nas juntas)", "Drawn axes vs pieces (double count at junctions)", "Накреслені осі проти деталей (подвійний підрахунок у з'єднаннях)", "Axes dessinés vs pièces (double compte aux jonctions)"),
}

CODES = {
    "parede_comprimento": ("Paredes, comprimento", "Walls, length", "Стіни, довжина", "Murs, longueur"),
    "parede_area_bruta": ("Paredes, área bruta", "Walls, gross area", "Стіни, площа брутто", "Murs, surface brute"),
    "parede_area_vaos": ("Paredes, área dos vãos", "Walls, opening area", "Стіни, площа прорізів", "Murs, surface des baies"),
    "parede_area_liquida": ("Paredes, área líquida", "Walls, net area", "Стіни, чиста площа", "Murs, surface nette"),
    "parede_volume": ("Paredes, volume", "Walls, volume", "Стіни, об'єм", "Murs, volume"),
    "clt_pecas": ("Peças CLT", "CLT pieces", "Деталі CLT", "Pièces CLT"),
    "clt_volume": ("Painéis CLT, volume", "CLT panels, volume", "Панелі CLT, об'єм", "Panneaux CLT, volume"),
    "alvenaria_area": ("Alvenaria", "Masonry", "Кладка", "Maçonnerie"),
    "alvenaria_unidades": ("Tijolos/blocos", "Bricks/blocks", "Цегла/блоки", "Briques/blocs"),
    "alvenaria_argamassa": ("Argamassa de assentamento", "Bedding mortar", "Кладковий розчин", "Mortier de pose"),
    "lintel_comprimento": ("Lintéis", "Lintels", "Перемички", "Linteaux"),
    "reboco_area": ("Reboco/estuque", "Render/plaster", "Штукатурка", "Enduit"),
    "betao_volume": ("Betão", "Concrete", "Бетон", "Béton"),
    "cofragem_area": ("Cofragem", "Formwork", "Опалубка", "Coffrage"),
    "aco_massa": ("Aço (taxa)", "Steel (ratio)", "Арматура (норма)", "Acier (ratio)"),
    "montantes_un": ("Montantes", "Studs", "Стійки", "Montants"),
    "montantes_comprimento": ("Montantes, comprimento", "Studs, length", "Стійки, довжина", "Montants, longueur"),
    "travessas_comprimento": ("Guias, padieiras e peitoris", "Tracks, headers and sills", "Напрямні, перемички, підвіконня", "Lisses, linteaux et appuis"),
    "placas_area": ("Placas", "Boards", "Плити", "Plaques/panneaux"),
    "isolamento_parede_area": ("Isolamento de parede", "Wall insulation", "Утеплення стін", "Isolation des murs"),
    "vaos_janela": ("Janelas", "Windows", "Вікна", "Fenêtres"),
    "vaos_porta": ("Portas", "Doors", "Двері", "Portes"),
    "vaos_vao": ("Vãos (sob lintel)", "Openings (under lintel)", "Прорізи (під перемичкою)", "Baies (sous linteau)"),
    "pavimento_area": ("Pavimento", "Floor finish", "Підлога", "Revêtement de sol"),
    "teto_area": ("Teto", "Ceiling", "Стеля", "Plafond"),
    "rodape_comprimento": ("Rodapé", "Skirting", "Плінтус", "Plinthes"),
}

PARAMS = {
    "altura_standard_rdc_m": ("Altura standard do RDC", "Standard ground floor height", "Стандартна висота першого поверху", "Hauteur standard du RDC"),
    "altura_standard_pisos_m": ("Altura standard dos outros pisos", "Standard height of other floors", "Стандартна висота інших поверхів", "Hauteur standard des autres niveaux"),
    "altura_vao_standard_m": ("Altura standard do vão", "Standard opening height", "Стандартна висота прорізу", "Hauteur standard de baie"),
    "vao_inferido_min_m": ("Vão inferido, mínimo", "Inferred opening, minimum", "Виведений проріз, мінімум", "Baie déduite, minimum"),
    "vao_inferido_max_m": ("Vão inferido, máximo", "Inferred opening, maximum", "Виведений проріз, максимум", "Baie déduite, maximum"),
    "tolerancia_verificacao_pct": ("Tolerância das verificações", "Check tolerance", "Допуск перевірок", "Tolérance des contrôles"),
    "clt_comprimento_max_m": ("CLT, comprimento máximo", "CLT, maximum length", "CLT, макс. довжина", "CLT, longueur maximale"),
    "clt_largura_max_m": ("CLT, largura máxima", "CLT, maximum width", "CLT, макс. ширина", "CLT, largeur maximale"),
    "clt_camadas": ("CLT, camadas", "CLT, layers", "CLT, шари", "CLT, plis"),
    "unidade_comprimento_mm": ("Comprimento da unidade", "Unit length", "Довжина елемента", "Longueur de l'élément"),
    "unidade_altura_mm": ("Altura da unidade", "Unit height", "Висота елемента", "Hauteur de l'élément"),
    "junta_mm": ("Junta", "Joint", "Шов", "Joint"),
    "perdas_pct": ("Perdas", "Waste", "Втрати", "Pertes"),
    "argamassa_l_m2": ("Argamassa por m²", "Mortar per m²", "Розчин на м²", "Mortier par m²"),
    "apoio_lintel_m": ("Entrega do lintel", "Lintel bearing", "Опирання перемички", "Appui du linteau"),
    "faces_revestidas": ("Faces revestidas", "Finished faces", "Оздоблені сторони", "Faces enduites"),
    "aco_kg_m3": ("Taxa de aço", "Steel ratio", "Норма армування", "Ratio d'acier"),
    "perdas_betao_pct": ("Perdas de betão", "Concrete waste", "Втрати бетону", "Pertes de béton"),
    "entre_eixo_m": ("Entre-eixo dos montantes", "Stud spacing", "Крок стійок", "Entraxe des montants"),
    "faces_placa": ("Faces com placa", "Boarded faces", "Обшиті сторони", "Faces parementées"),
    "comprimento_max_m": ("Comprimento máximo de painel", "Maximum panel length", "Макс. довжина панелі", "Longueur maximale de panneau"),
    "placas_por_face": ("Placas por face", "Boards per face", "Плит на сторону", "Plaques par face"),
}

_IDX = {"pt": 0, "en": 1, "uk": 2, "fr": 3}


def tr(text, lang="pt"):
    if not isinstance(text, str):
        return text
    if text in KEYED:
        return KEYED[text][_IDX.get(lang, 0)]
    if text.startswith("param."):
        group, _, key = text[6:].partition(".")
        label = PARAMS.get(key)
        name = label[_IDX.get(lang, 0)] if label else key
        return name if group == "geral" else f"{name} ({tr('sistema.' + group, lang)})"
    if lang == "pt" or text not in T:
        return text
    return T[text][_IDX[lang] - 1]


def code_label(code, lang="pt"):
    row = CODES.get(code)
    return row[_IDX.get(lang, 0)] if row else code
