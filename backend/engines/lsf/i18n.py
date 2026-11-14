"""Textos do motor LSF em PT / FR / EN / UK (os nomes técnicos internos ficam em português; traduzidos à saída)."""
from __future__ import annotations

LANGS = ("pt", "fr", "en", "uk")

_T = {
    # tipos de peça
    "Montante": ("Montante", "Montant", "Stud", "Стійка"),
    "Montante de extremo": ("Montante de extremo", "Montant d'extrémité", "End stud", "Крайня стійка"),
    "Montante de canto": ("Montante de canto", "Montant d'angle", "Corner stud", "Кутова стійка"),
    "Montante de ligação": ("Montante de ligação", "Montant de liaison", "Junction stud", "Стійка примикання"),
    "Montante rei": ("Montante rei", "Montant principal (king)", "King stud", "Основна стійка"),
    "Montante de apoio": ("Montante de apoio", "Montant d'appui (jack)", "Jack stud", "Опорна стійка"),
    "Montante curto (sobre verga)": ("Montante curto (sobre verga)", "Montant court (sur linteau)", "Cripple stud (above header)", "Коротка стійка (над перемичкою)"),
    "Montante curto (sob peitoril)": ("Montante curto (sob peitoril)", "Montant court (sous allège)", "Cripple stud (below sill)", "Коротка стійка (під підвіконням)"),
    "Guia inferior": ("Guia inferior", "Rail bas", "Bottom track", "Нижня напрямна"),
    "Guia superior": ("Guia superior", "Rail haut", "Top track", "Верхня напрямна"),
    "Verga": ("Verga", "Linteau", "Header", "Перемичка"),
    "Guia de verga (inferior)": ("Guia de verga (inferior)", "Rail de linteau (bas)", "Header track (bottom)", "Напрямна перемички (нижня)"),
    "Guia de verga (superior)": ("Guia de verga (superior)", "Rail de linteau (haut)", "Header track (top)", "Напрямна перемички (верхня)"),
    "Guia de peitoril": ("Guia de peitoril", "Rail d'allège", "Sill track", "Напрямна підвіконня"),
    "Bloqueador": ("Bloqueador", "Entretoise", "Blocking", "Розпірка"),
    "Bloqueador (junta de placa)": ("Bloqueador (junta de placa)", "Entretoise (joint de panneau)", "Blocking (board joint)", "Розпірка (стик плит)"),
    "Fita de contraventamento": ("Fita de contraventamento", "Feuillard de contreventement", "Bracing strap", "Стрічка в'язей"),
    "Guia de bordadura (rim)": ("Guia de bordadura (rim)", "Rive de plancher", "Rim track", "Обв'язувальна напрямна"),
    "Viga de piso": ("Viga de piso", "Solive", "Floor joist", "Балка перекриття"),
    "Bloqueador de piso": ("Bloqueador de piso", "Entretoise de plancher", "Floor blocking", "Розпірка перекриття"),
    "Banzo inferior": ("Banzo inferior", "Entrait", "Bottom chord", "Нижній пояс"),
    "Banzo superior": ("Banzo superior", "Arbalétrier", "Top chord", "Верхній пояс"),
    "Diagonal": ("Diagonal", "Diagonale", "Web", "Розкіс"),
    # grupos / títulos
    "Paredes": ("Paredes", "Murs", "Walls", "Стіни"),
    "Pisos": ("Pisos", "Planchers", "Floors", "Перекриття"),
    "Cobertura": ("Cobertura", "Toiture", "Roof", "Покрівля"),
    "titulo": ("Estrutura em aço leve (LSF) — estudo, quantidades e corte", "Ossature acier léger (LSF) — étude, métré et débit",
               "Light steel frame (LSF) — study, quantities and cutting", "Легкий сталевий каркас (LSF) — розрахунок, кількості та розкрій"),
    "pre": ("PRÉ-DIMENSIONAMENTO E QUANTIDADES — a verificar e assinar por engenheiro de estruturas antes da execução",
            "PRÉ-DIMENSIONNEMENT ET MÉTRÉ — à viser par un ingénieur structure avant exécution",
            "PRELIMINARY DESIGN AND QUANTITIES — to be checked and signed by a structural engineer before construction",
            "ПОПЕРЕДНІЙ РОЗРАХУНОК І КІЛЬКОСТІ — перевіряє та підписує інженер-конструктор до початку робіт"),
    "kg_aco": ("Aço", "Acier", "Steel", "Сталь"),
    "pecas": ("Peças", "Pièces", "Members", "Елементи"),
    "parafusos": ("Parafusos", "Vis", "Screws", "Шурупи"),
    "kg_m2": ("Aço / m² de piso", "Acier / m² de plancher", "Steel / m² floor", "Сталь / м² площі"),
    "camadas": ("Camadas e vistas", "Calques et vues", "Layers and views", "Шари та види"),
    "estrutura": ("Estrutura", "Ossature", "Frame", "Каркас"),
    "gesso": ("Gesso", "Plâtre", "Gypsum", "Гіпсокартон"),
    "piso": ("Piso", "Plancher", "Floor", "Перекриття"),
    "cob": ("Cobertura", "Toiture", "Roof", "Покрівля"),
    "corte": ("Corte horizontal", "Coupe horizontale", "Horizontal section", "Горизонтальний переріз"),
    "frente": ("Frente", "Face", "Front", "Фасад"),
    "lado": ("Lado", "Côté", "Side", "Бік"),
    "topo": ("Topo", "Dessus", "Top", "Зверху"),
    "semCorte": ("sem corte", "sans coupe", "no section", "без перерізу"),
    "viewer_sub": ("Visualizador 3D — cada perfil com a secção real; toque numa peça para ver ID, perfil e comprimento",
                   "Visionneuse 3D — chaque profil avec sa section réelle ; touchez une pièce pour voir ID, profil et longueur",
                   "3D viewer — each member with its real section; tap a member to see ID, profile and length",
                   "3D-переглядач — кожен профіль із реальним перерізом; торкніться елемента, щоб побачити ID, профіль і довжину"),
}


def t(key: str, lang: str = "pt") -> str:
    v = _T.get(key)
    if not v:
        return key
    return v[LANGS.index(lang) if lang in LANGS else 0]


def num(x, d: int = 1, lang: str = "pt") -> str:
    s = f"{x:,.{d}f}"
    if lang == "en":
        return s
    return s.replace(",", " ").replace(".", ",")
