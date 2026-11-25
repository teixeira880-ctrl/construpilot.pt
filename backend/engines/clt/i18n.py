"""Textos do motor CLT em PT / FR / EN / UK."""
from __future__ import annotations

from engines.lsf.i18n import num  # noqa: F401

LANGS = ("pt", "fr", "en", "uk")

_T = {
    "parede": ("Parede", "Mur", "Wall", "Стіна"),
    "laje": ("Laje", "Plancher", "Floor slab", "Перекриття"),
    "cobertura": ("Cobertura", "Toiture", "Roof", "Покрівля"),
    "empena": ("Empena", "Pignon", "Gable", "Фронтон"),
    "titulo": ("Estrutura em CLT — estudo, quantidades e fabrico", "Structure CLT — étude, métré et fabrication",
               "CLT structure — study, quantities and fabrication", "Конструкція CLT — розрахунок, кількості та виготовлення"),
    "pre": ("PRÉ-DIMENSIONAMENTO E QUANTIDADES — a verificar e assinar por engenheiro de estruturas (EN 1995-1-1) antes do fabrico",
            "PRÉ-DIMENSIONNEMENT ET MÉTRÉ — à viser par un ingénieur structure (EN 1995-1-1) avant fabrication",
            "PRELIMINARY DESIGN AND QUANTITIES — to be checked and signed by a structural engineer (EN 1995-1-1) before fabrication",
            "ПОПЕРЕДНІЙ РОЗРАХУНОК І КІЛЬКОСТІ — перевіряє та підписує інженер-конструктор (EN 1995-1-1) до виготовлення"),
    "m3liq": ("CLT líquido", "CLT net", "Net CLT", "CLT нетто"),
    "m3prensa": ("CLT de prensa", "CLT de presse", "Press CLT", "CLT з преса"),
    "perda": ("Perda de fabrico", "Chute de fabrication", "Fabrication waste", "Відходи виготовлення"),
    "paineis": ("Painéis", "Panneaux", "Panels", "Панелі"),
    "massa": ("Massa", "Masse", "Mass", "Маса"),
    "parafusos": ("Parafusos e pregos", "Vis et pointes", "Screws and nails", "Шурупи та цвяхи"),
    "conectores": ("Conectores", "Connecteurs", "Connectors", "З'єднувачі"),
    "m3m2": ("CLT / m² de piso", "CLT / m² de plancher", "CLT / m² floor", "CLT / м² площі"),
    "camadas": ("Camadas e vistas", "Calques et vues", "Layers and views", "Шари та види"),
    "estrutura": ("Painéis", "Panneaux", "Panels", "Панелі"),
    "gesso": ("Isolamento", "Isolant", "Insulation", "Утеплення"),
    "piso": ("Lajes", "Planchers", "Floors", "Перекриття"),
    "cob": ("Cobertura", "Toiture", "Roof", "Покрівля"),
    "corte": ("Corte horizontal", "Coupe horizontale", "Horizontal section", "Горизонтальний переріз"),
    "frente": ("Frente", "Face", "Front", "Фасад"),
    "lado": ("Lado", "Côté", "Side", "Бік"),
    "topo": ("Topo", "Dessus", "Top", "Зверху"),
    "semCorte": ("sem corte", "sans coupe", "no section", "без перерізу"),
    "viewer_sub": ("Visualizador 3D — cada painel CLT com a geometria real e os recortes; toque num painel para ver ID, composição e volume",
                   "Visionneuse 3D — chaque panneau CLT avec sa géométrie réelle et ses découpes ; touchez un panneau pour voir ID, composition et volume",
                   "3D viewer — each CLT panel with its real geometry and cut-outs; tap a panel to see ID, lay-up and volume",
                   "3D-переглядач — кожна панель CLT з реальною геометрією та вирізами; торкніться панелі, щоб побачити ID, склад і об'єм"),
}

TX = {
    "sumario": ("Síntese", "Synthèse", "Summary", "Підсумок"),
    "hip": ("Hipóteses adotadas (a validar)", "Hypothèses retenues (à valider)", "Assumptions (to be validated)", "Прийняті припущення (перевірити)"),
    "avisos": ("Pontos a verificar", "Points à vérifier", "Items to check", "Пункти для перевірки"),
    "mapa": ("Mapa de quantidades", "Métré quantitatif", "Bill of quantities", "Відомість кількостей"),
    "lista": ("Lista de painéis (fabrico)", "Liste des panneaux (fabrication)", "Panel list (fabrication)", "Перелік панелей (виготовлення)"),
    "vaos": ("Vãos medidos (recortes CNC)", "Baies mesurées (découpes CNC)", "Measured openings (CNC cut-outs)", "Виміряні прорізи (вирізи ЧПК)"),
    "regras": ("Regras de ligação aplicadas", "Règles d'assemblage appliquées", "Connection rules applied", "Застосовані правила з'єднань"),
    "prensa": ("Plano de prensa (nesting dos painéis nos brutos)", "Plan de presse (imbrication des panneaux)", "Press plan (panel nesting)",
               "План преса (розкладка панелей)"),
    "render": ("Estrutura CLT montada", "Structure CLT montée", "Assembled CLT structure", "Змонтована конструкція CLT"),
    "alcado": ("Alçado de fabrico", "Élévation de fabrication", "Fabrication elevation", "Креслення виготовлення"),
    "planta": ("Planta dos painéis de parede", "Plan des panneaux de murs", "Wall panel plan", "План стінових панелей"),
    "lajes": ("Implantação dos painéis de laje", "Calepinage des panneaux de plancher", "Floor panel layout", "Розкладка панелей перекриття"),
    "cobertura": ("Painéis de cobertura e empenas", "Panneaux de toiture et pignons", "Roof panels and gables", "Панелі покрівлі та фронтони"),
    "total": ("Total", "Total", "Total", "Разом"),
    "sem_preco": ("a orçamentar", "à chiffrer", "to be priced", "до розрахунку"),
}
_IDX = {"pt": 0, "fr": 1, "en": 2, "uk": 3}


def t(key: str, lang: str = "pt") -> str:
    v = _T.get(key)
    if not v:
        return key
    return v[_IDX.get(lang, 0)]


def tx(k, lang):
    return TX[k][_IDX.get(lang, 0)]
