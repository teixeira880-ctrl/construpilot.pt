"""Prompt en langage courant → programme architectural (déterministe).

Le même texte donne toujours le même programme (règle ConstruPilot : un même pedido donne le même résultat).
Ce qui n'est pas dit est pris dans des valeurs types, écrites dans `hypotheses` pour que l'architecte les voie.

Typologie : en France T4 = 4 pièces principales (séjour + 3 chambres) ; au Portugal T3 / V3 = 3 quartos.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from engines.estudio_projeto import sitio

PAIS = sitio.PAIS

# clé → (FR, PT, EN, zone, surface type m²)
PIECES: Dict[str, tuple] = {
    "sejour": ("Séjour", "Sala", "Living room", "jour", 30.0),
    "sejour_cuisine": ("Séjour / cuisine", "Sala / cozinha", "Living / kitchen", "jour", 40.0),
    "cuisine": ("Cuisine", "Cozinha", "Kitchen", "jour", 11.0),
    "entree": ("Entrée", "Hall de entrada", "Entrance", "jour", 5.0),
    "wc": ("WC", "WC", "WC", "jour", 1.8),
    "bureau": ("Bureau", "Escritório", "Office", "jour", 9.0),
    "buanderie": ("Buanderie", "Lavandaria", "Laundry", "jour", 5.0),
    "chambre": ("Chambre", "Quarto", "Bedroom", "nuit", 11.0),
    "suite": ("Chambre parentale", "Suite", "Master bedroom", "nuit", 14.0),
    "sdb": ("Salle de bain", "Casa de banho", "Bathroom", "nuit", 6.0),
    "sde": ("Salle d'eau", "Casa de banho da suite", "Shower room", "nuit", 4.0),
    "dressing": ("Dressing", "Closet", "Walk-in closet", "nuit", 4.0),
    "garage": ("Garage", "Garagem", "Garage", "garage", 18.0),
}
HUMIDES = {"wc", "sdb", "sde", "buanderie"}

_NOMBRES = {"un": 1, "une": 1, "um": 1, "uma": 1, "one": 1, "a": 1, "deux": 2, "dois": 2, "duas": 2, "two": 2,
            "trois": 3, "tres": 3, "three": 3, "quatre": 4, "quatro": 4, "four": 4, "cinq": 5, "cinco": 5, "five": 5,
            "six": 6, "seis": 6}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def nom(cle: str, lang: Optional[str] = None, n: Optional[int] = None) -> str:
    lang = (lang or ("pt" if PAIS == "PT" else "fr")).lower()
    i = {"fr": 0, "pt": 1, "en": 2}.get(lang, 0)
    base = PIECES[cle][i]
    return f"{base} {n}" if n else base


def _compte(txt: str, mots: str) -> Optional[int]:
    m = re.search(rf"\b(\d{{1,2}}|{'|'.join(_NOMBRES)})\s+(?:grandes?\s+|petites?\s+)?(?:{mots})\b", txt)
    if not m:
        return None
    v = m.group(1)
    return int(v) if v.isdigit() else _NOMBRES.get(v)


def lire(prompt: str) -> Dict[str, Any]:
    """Analyse le prompt. Renvoie {"reconnu": bool, "chambres", "surface", "niveaux", "garage", ...}."""
    t = _fold(prompt)
    out: Dict[str, Any] = {"reconnu": False}
    typo = re.search(r"\b([tv])\s?([1-9])\b", t)
    if typo:
        n = int(typo.group(2))
        # France : T4 = séjour + 3 chambres ; Portugal : T3 / V3 = 3 quartos.
        out["chambres"] = n if (PAIS == "PT" or typo.group(1) == "v") else max(0, n - 1)
        out["typologie"] = typo.group(0).upper().replace(" ", "")
        out["reconnu"] = True
    ch = _compte(t, r"chambres?|quartos?|bedrooms?")
    if ch is not None:
        out["chambres"] = ch
        out["reconnu"] = True
    surf = [float(x.replace(",", ".")) for x in re.findall(r"(\d{2,4}(?:[.,]\d+)?)\s*(?:m2|m²|m\s?carr|metres? carr|metros? quadrados|sqm)", t)]
    if surf:
        out["surface"] = max(surf)
        out["reconnu"] = True
    if re.search(r"plain[- ]?pied|rez[- ]de[- ]chaussee seul|terrea|piso unico|um piso|single[- ]stor|bungalow", t):
        out["niveaux"] = 1
    if re.search(r"\br\s?\+\s?1\b|etage|deux niveaux|2 niveaux|duplex|dois pisos|2 pisos|\bandar\b|piso superior|r/c\s?\+\s?1|two[- ]stor|2[- ]stor", t):
        out["niveaux"] = 2
    if re.search(r"garage|garagem", t) and not re.search(r"sans garage|sem garagem|no garage", t):
        out["garage"] = True
    if re.search(r"double garage|garage double|garagem dupla|2 voitures|deux voitures|duas viaturas|(?:dois|2) (?:automoveis|carros|viaturas|lugares)|two[- ]car|2[- ]car", t):
        out["garage"] = True
        out["garage_double"] = True
    if re.search(r"bureau|escritorio|office", t):
        out["bureau"] = True
    if re.search(r"buanderie|cellier|lavandaria|laundry", t):
        out["buanderie"] = True
    if re.search(r"suite parentale|suite|master", t):
        out["suite"] = True
    if re.search(r"cuisine ouverte|cuisine americaine|cozinha aberta|open[- ]plan|open kitchen|kitchenette", t):
        out["cuisine_ouverte"] = True
    if re.search(r"cuisine fermee|cuisine separee|cozinha fechada|cozinha separada|separate kitchen", t):
        out["cuisine_ouverte"] = False
    nb_sdb = _compte(t, r"salles? de bains?|salles? d'eau|casas? de banho|wc'?s|bathrooms?")
    if nb_sdb:
        out["sdb"] = nb_sdb
    if re.search(r"toit[- ]terrasse|toit plat|toiture plate|cobertura plana|terraco|flat roof", t):
        out["toiture"] = "plana"
    elif re.search(r"4 pans|quatre pans|quatro aguas|hip roof", t):
        out["toiture"] = "quatro_aguas"
    elif re.search(r"1 pan|un pan|monopente|uma agua|mono[- ]?pitch|shed roof", t):
        out["toiture"] = "uma_agua"
    elif re.search(r"2 pans|deux pans|duas aguas|gable", t):
        out["toiture"] = "duas_aguas"
    if any(k in out for k in ("niveaux", "garage", "toiture", "bureau", "suite")):
        out["reconnu"] = out["reconnu"] or bool(re.search(r"maison|moradia|casa|house|villa|pavillon|habitation", t))
    return out


# ----------------------------------------------------------------------------------- programa detalhado
# Um prompt profissional dá muitas vezes a lista das divisões com a área de cada uma, por piso
# (« Sala de estar e jantar: 35 m² » sob « Rés do chão — 110 m² »). Essa lista é lida tal como foi
# escrita: as áreas pedidas são respeitadas (sem ajuste de escala) e a coerência é verificada.
_NIVEL = [
    (0, r"res[- ]do[- ]chao|\br\s?/\s?c\b|rez[- ]de[- ]chaussee|\brdc\b|ground floor|piso 0\b|piso terreo|\brez\b"),
    (1, r"primeiro andar|1\s?\.?\s?[oº]?\s*andar|\b1\s?[oº]?\s*piso\b|piso 1\b|premier etage|1er etage|\betage\b|first floor|upper floor|andar superior"),
    (2, r"segundo andar|2\s?\.?\s?[oº]?\s*andar|piso 2\b|deuxieme etage|2e etage|second floor"),
    (-1, r"\bcave\b|sous[- ]sol|basement|semi[- ]?cave"),
]
_LINHA = re.compile(r"^[\s*•·\-–—>]*(?P<nome>[^:\n]{2,90}?)\s*(?::|—|–|-)\s*(?P<a>\d{1,3}(?:[.,]\d+)?)\s*m\s?(?:2|²)\s*\.?\s*$")
# (regex sobre o nome normalizado, chave da divisão). A ordem conta: o mais específico primeiro.
_TIPOS = [
    (r"circulac|escadas?\b|paredes|degagement|circulation|couloir|corredor|dégagement|stairs|hallway and", "_circ"),
    (r"garag", "_garage"),
    (r"closet|dressing|walk[- ]in", "dressing"),
    (r"(casa de banho|instalac\w* sanit|salle d.eau|salle de bain|bathroom|wc).*(suite|privativ|parental|master)", "sde"),
    (r"\bsuite\b|parental|master", "suite"),
    (r"escritorio|bureau|office|gabinete|hospedes|invites|guest", "bureau"),
    (r"casa de banho|instalac\w* sanit|salle de bain|salle d.eau|bathroom|duche|douche", "sdb"),
    (r"\bwc\b|lavabo|toilet|sanitario", "wc"),
    (r"quarto|chambre|bedroom", "chambre"),
    (r"(cozinha|cuisine|kitchen).*(sala|sejour|living|estar)|(sala|sejour|living|estar).*(cozinha|cuisine|kitchen)", "sejour_cuisine"),
    (r"cozinha|cuisine|kitchen|kitchenette", "cuisine"),
    (r"\bsala\b|sejour|living|estar|jantar|salon|salle a manger", "sejour"),
    (r"\bhall\b|entrada|entree|entrance|vestibulo|foyer", "entree"),
    (r"lavandaria|buanderie|laundry|tecnica|technique|cellier|despensa|arrumos|storage|rangement|cellar", "buanderie"),
]
# divisões que o gerador sabe colocar no piso superior
_SUPERIOR = {"chambre", "suite", "sdb", "sde", "dressing", "wc"}


def _tipo(nome_fold: str) -> Optional[str]:
    for rx, cle in _TIPOS:
        if re.search(rx, nome_fold):
            return cle
    return None


def lista_detalhada(prompt: str) -> Dict[str, Any]:
    """Lê « divisão: área m² » por piso. Devolve {"divisoes": [...], "pisos": {nível: área indicada}, "circulacao": {...},
    "nao_reconhecidas": [...]} — vazio se o prompt não tiver lista."""
    nivel = 0
    divisoes: List[Dict[str, Any]] = []
    pisos: Dict[int, float] = {}
    circ: Dict[int, float] = {}
    nao: List[str] = []
    for bruta in (prompt or "").splitlines():
        linha = bruta.strip()
        if not linha:
            continue
        f = _fold(linha)
        cab = next((n for n, rx in _NIVEL if re.search(rx, f)), None)
        m = _LINHA.match(linha)
        nome_f = _fold(m.group("nome")) if m else ""
        if cab is not None and (not m or next((n for n, rx in _NIVEL if re.search(rx, nome_f)), None) is not None):
            nivel = cab
            if m:
                pisos[nivel] = float(m.group("a").replace(",", "."))
            continue
        if not m:
            continue
        area = float(m.group("a").replace(",", "."))
        if area <= 0 or area > 400:
            continue
        nome_txt = re.sub(r"\s+", " ", m.group("nome")).strip(" .*")
        cle = _tipo(nome_f)
        if cle == "_circ":
            circ[nivel] = circ.get(nivel, 0.0) + area
            continue
        if cle == "_garage":
            divisoes.append({"cle": "_garage", "nom": nome_txt, "surface": area, "niveau": nivel})
            continue
        if cle is None:
            nao.append(f"{nome_txt} ({area:g} m²)")
            continue
        divisoes.append({"cle": cle, "nom": nome_txt[:60], "surface": area, "niveau": nivel})
    if len([d for d in divisoes if d["cle"] != "_garage"]) < 3:
        return {"divisoes": [], "pisos": {}, "circulacao": {}, "nao_reconhecidas": []}
    return {"divisoes": divisoes, "pisos": pisos, "circulacao": circ, "nao_reconhecidas": nao}


# ----------------------------------------------------------------------------------- pedidos do prompt
# Tudo o que o prompt pede e que não é uma divisão fica registado — nada é ignorado em silêncio.
# Cada pedido diz se é feito aqui (Ateliê / Estúdio) ou em que app do ConstruPilot continua,
# no mesmo processo de obra (fluxo entre apps).
_APP_PT = {
    "atelier": ("Ateliê Arquiteto / Estúdio de Projeto", "/atelier-arquiteto"),
    "bim": ("BIM Studio", "/bim"),
    "eng": ("Estudos de Engenharia", "/estudos-engenharia"),
    "exec": ("Planos de execução (redes)", "/planos-execucao"),
    "assist": ("Assistente BTP (medições e orçamento)", "/assistant"),
    "plan": ("Planeamento", "/planning"),
    "img": ("Imagens & Renders 3D", "/estudio-imagens"),
    "lic": ("Licenciamento", "/licenciamento-automatico"),
}
_APP_FR = {
    "atelier": ("Atelier Architecte / Studio de projet", "/atelier-architecte"),
    "bim": ("BIM Studio", "/bim-studio"),
    "eng": ("Études d'ingénierie", "/etudes-ingenierie"),
    "exec": ("Plans d'exécution (réseaux)", "/plans-execution"),
    "assist": ("Assistant BTP (métré et chiffrage)", "/assistant"),
    "plan": ("Planning", "/planning"),
    "img": ("Images & rendus 3D", "/generateur-images"),
    "lic": ("Permis & urbanisme", "/urbanisme"),
}
_APP = _APP_PT if PAIS == "PT" else _APP_FR
# (tema, título FR, título PT, regex, app)
_PEDIDOS = [
    ("exterior", "Piscine", "Piscina", r"piscina|piscine|swimming pool|\bpool\b", "atelier"),
    ("exterior", "Aménagements extérieurs (jardin, terrasse, pergola, repas extérieur)", "Arranjos exteriores (jardim, terraço, pérgola, zona de refeições)",
     r"jardim|jardin|garden|terraco|terrasse|pergola|zona de refeic", "atelier"),
    ("exterior", "Façades et matériaux extérieurs", "Fachadas e materiais exteriores",
     r"fachada|facade|pedra natural|pierre naturelle|madeira|bois|aluminio|aluminium|platibanda|acrotere", "atelier"),
    ("exterior", "Baies toute hauteur / balcons à garde-corps vitrés", "Envidraçados do chão ao teto / varandas com guardas em vidro",
     r"envidracad|baie vitree|vitrage|do chao ao teto|toute hauteur|varanda|balcon|guardas? em vidro|garde[- ]corps", "atelier"),
    ("exterior", "Éclairage LED architectural", "Iluminação LED arquitetónica", r"\bled\b|iluminac|eclairage", "atelier"),
    ("interior", "Design intérieur (finitions, sols, mobilier, couleurs)", "Design interior (acabamentos, pavimentos, mobiliário, cores)",
     r"design interior|interieur|pavimento|revetement de sol|mobiliario|mobilier|tons |couleurs|pedra sinterizada|ceramica|carrelage", "atelier"),
    ("pecas", "Plans cotés, toiture, façades, coupes et plan de masse", "Plantas cotadas, cobertura, alçados, cortes e implantação",
     r"plantas?|plans? cotes?|alcados?|facades|cortes?|coupes?|implantac|plan de masse|planta de cobertura", "atelier"),
    ("eng", "Structure béton armé (Eurocodes, sismique, géotechnique)", "Estrutura em betão armado (Eurocódigos, sísmica, geotecnia)",
     r"betao armado|beton arme|estrutur|structure|eurocodig|eurocode|sism|geotecn|fundac|fondation|pilares|poteaux|vigas|poutres|lajes|dalles", "eng"),
    ("eng", "Thermique et acoustique (isolation, menuiseries, orientation)", "Térmica e acústica (isolamento, caixilharia, orientação solar)",
     r"termic|thermique|acustic|acoustique|isolamento|isolation|caixilharia|menuiserie|corte termico|eficiencia energetica|orientacao solar|re2020", "eng"),
    ("redes", "Réseaux : électricité, eau, assainissement, climatisation", "Redes: eletricidade, águas, esgotos, climatização",
     r"eletricidade|electricite|aguas|esgotos|assainissement|plomberie|climatizac|climatisation|redes|reseaux", "exec"),
    ("redes", "Pompe à chaleur, plancher chauffant, VMC double flux", "Bomba de calor, pavimento radiante, VMC de duplo fluxo",
     r"bomba de calor|pompe a chaleur|radiante|plancher chauffant|\bvmc\b|ventilac|double flux|duplo fluxo", "exec"),
    ("redes", "Photovoltaïque, domotique, récupération des eaux de pluie", "Fotovoltaico, domótica, recuperação de águas pluviais",
     r"fotovolta|photovolta|solares?|solaires?|domotic|domotique|pluvia|eaux de pluie", "exec"),
    ("bim", "Maquette BIM, détection des conflits, export IFC / DWG / PDF", "Modelo BIM, deteção de incompatibilidades, exportação IFC / DWG / PDF",
     r"\bbim\b|\bifc\b|\bdwg\b|incompatib|clash|conflits", "bim"),
    ("custos", "Métré et devis par lot", "Mapa de quantidades e orçamento por especialidade",
     r"mapa de quantidades|quantidades|metre|orcamento|devis|budget|dpgf|chiffrage", "assist"),
    ("obra", "Planning d'exécution du chantier", "Planeamento de execução da obra", r"planeamento|planning|cronograma|calendrier", "plan"),
    ("imagens", "Rendus 3D photoréalistes (extérieur, intérieur, aérien, nuit)", "Renders 3D fotorrealistas (exterior, interior, aérea, noturna)",
     r"render|rendu|fotorrealis|photorealis|4k|vista aerea|vue aerienne|noturna|nocturne|de nuit", "img"),
    ("regras", "Conformité réglementaire et urbanistique (validation par des professionnels habilités)",
     "Conformidade regulamentar e urbanística (validação por técnicos habilitados)",
     r"normas|normes|regulament|reglementaire|urbanistic|urbanisme|conformidade|conformite|tecnicos habilitados|plu\b", "lic"),
]


def exteriores(prompt: str) -> Dict[str, Any]:
    """Exteriores pedidos (piscina com medidas, terraço, pérgola, zona de refeições, jardim) — colocados pelo gerador
    como objetos editáveis do Estúdio."""
    t = _fold(prompt)
    out: Dict[str, Any] = {}
    if re.search(r"piscina|piscine|swimming pool|\bpool\b", t):
        dim = re.search(r"piscin\w*[^\n.]{0,40}?(\d{1,2}(?:[.,]\d+)?)\s*[x×]\s*(\d{1,2}(?:[.,]\d+)?)", _fold((prompt or "").replace("×", "x")))
        a, b = (float(v.replace(",", ".")) for v in dim.groups()) if dim else (8.0, 4.0)
        out["piscina"] = [max(a, b), min(a, b)]
        out["piscina_medidas_dadas"] = bool(dim)
        out["transbordo"] = bool(re.search(r"transbordo|debordement|infinity|infinita", t))
    if re.search(r"terraco|terrasse|terrace|deck|esplanada", t) or "piscina" in out:
        out["terraco"] = True
    if re.search(r"pergola", t):
        out["pergola"] = True
    if re.search(r"zona de refeic|refeicoes exterior|cuisine d.ete|coin repas|churrasqueira|barbecue|outdoor kitchen|outdoor dining", t):
        out["refeicoes"] = True
    if re.search(r"jardim|jardin|garden|paisagis|paysag|relvado|pelouse", t):
        out["jardim"] = True
    return out


def pedidos(prompt: str, lang: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista dos pedidos do prompt (fora das divisões) com a app onde cada um é tratado."""
    t = _fold(prompt)
    fr = (lang or ("pt" if PAIS == "PT" else "fr")) == "fr"
    out: List[Dict[str, Any]] = []
    for tema, titulo_fr, titulo_pt, rx, app in _PEDIDOS:
        titulo = titulo_fr if fr else titulo_pt
        if not re.search(rx, t):
            continue
        nome_app, rota = _APP[app]
        aqui = app == "atelier"
        modelado = tema == "pecas" or titulo_pt in ("Piscina", "Arranjos exteriores (jardim, terraço, pérgola, zona de refeições)")
        estado = ("gerado" if modelado else "estudio") if aqui else "continuar"
        item: Dict[str, Any] = {"tema": tema, "titulo": titulo, "app": nome_app, "rota": rota, "aqui": aqui, "estado": estado}
        if tema == "exterior" and titulo_pt == "Piscina":
            dim = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*[x×]\s*(\d{1,2}(?:[.,]\d+)?)\s*m", prompt or "")
            if dim:
                a, b = (float(v.replace(",", ".")) for v in dim.groups())
                item["dimensoes_m"] = [a, b]
                item["titulo"] = f"{titulo} {a:g} × {b:g} m"
        out.append(item)
    return out


def programme(prompt: str, lang: Optional[str] = None) -> Dict[str, Any]:
    """Programme complet : liste des pièces par niveau, surfaces, toiture ; hypothèses écrites."""
    lu = lire(prompt)
    hyp: List[str] = []
    fr = (lang or ("pt" if PAIS == "PT" else "fr")) == "fr"

    def H(f: str, p: str) -> None:
        hyp.append(f if fr else p)

    det = lista_detalhada(prompt)
    if det["divisoes"]:
        return _programme_detalhado(prompt, lu, det, lang, hyp, H)

    chambres = lu.get("chambres")
    if chambres is None:
        chambres = 3
        H("Nombre de chambres non précisé : 3 chambres retenues.", "Número de quartos não indicado: 3 quartos considerados.")
    chambres = max(0, min(int(chambres), 6))
    niveaux = lu.get("niveaux") or (2 if chambres >= 5 else 1)
    if "niveaux" not in lu:
        H(f"Niveaux non précisés : {'plain-pied' if niveaux == 1 else 'R+1'} retenu.",
          f"Pisos não indicados: {'piso único' if niveaux == 1 else 'R/C + 1'} considerado.")
    ouverte = lu.get("cuisine_ouverte", True)
    if "cuisine_ouverte" not in lu:
        H("Cuisine ouverte sur le séjour retenue (non précisé).", "Cozinha aberta para a sala considerada (não indicado).")
    nb_sdb = lu.get("sdb") or (2 if chambres >= 4 else 1)

    pieces: List[Dict[str, Any]] = []

    def add(cle: str, niveau: int, n: Optional[int] = None) -> None:
        pieces.append({"cle": cle, "nom": nom(cle, lang, n), "zone": PIECES[cle][3], "surface": PIECES[cle][4], "niveau": niveau})

    nuit = 1 if niveaux == 2 else 0
    add("entree", 0)
    if ouverte:
        add("sejour_cuisine", 0)
    else:
        add("sejour", 0)
        add("cuisine", 0)
    add("wc", 0)
    if niveaux == 2:
        add("wc", 1)
    if lu.get("bureau"):
        add("bureau", 0)
    if lu.get("buanderie"):
        add("buanderie", 0)
    suite = bool(lu.get("suite")) and chambres >= 1
    k0 = 1
    if suite:
        add("suite", nuit)
        add("sde", nuit)
        k0 = 2
        nb_sdb = max(1, nb_sdb - 1)
    for k in range(k0, chambres + 1):
        add("chambre", nuit, k - (1 if suite else 0) if chambres - (1 if suite else 0) > 1 else None)
    for k in range(nb_sdb):
        add("sdb", nuit, (k + 1) if nb_sdb > 1 else None)
    garage = None
    if lu.get("garage"):
        garage = {"nom": nom("garage", lang), "surface": 36.0 if lu.get("garage_double") else 18.0,
                  "largeur": 6.0 if lu.get("garage_double") else 3.0}

    # Surface habitable demandée : les surfaces types sont mises à l'échelle (circulations ≈ 8 %).
    cible = lu.get("surface")
    somme = sum(p["surface"] for p in pieces)
    if cible:
        circ = (0.16 if niveaux == 2 else 0.08) * cible     # deux niveaux : hall + dégagement + escalier
        f = max(0.6, min(1.8, (cible - circ) / somme))
        for p in pieces:
            if p["cle"] not in ("wc",):
                p["surface"] = round(p["surface"] * f, 1)
        if abs(f - 1) > 0.25:
            H(f"Surfaces types ajustées (×{f:.2f}) pour viser {cible:.0f} m² habitables.",
              f"Áreas tipo ajustadas (×{f:.2f}) para {cible:.0f} m² de área útil.")
    else:
        H("Surface non précisée : surfaces types par pièce (modifiables dans le Studio).",
          "Área não indicada: áreas tipo por divisão (editáveis no Estúdio).")
    toiture = lu.get("toiture") or "duas_aguas"
    if "toiture" not in lu:
        H("Toiture deux pans retenue (non précisé).", "Cobertura de duas águas considerada (não indicado).")
    return {"pieces": pieces, "niveaux": niveaux, "garage": garage, "toiture": toiture, "surface_visee": cible,
            "chambres": chambres, "reconnu": lu["reconnu"], "lu": lu, "hypotheses": hyp, "pedidos": pedidos(prompt, lang), "exteriores": exteriores(prompt)}


def _programme_detalhado(prompt: str, lu: Dict[str, Any], det: Dict[str, Any], lang: Optional[str], hyp: List[str], H) -> Dict[str, Any]:
    """Programa a partir da lista de divisões escrita no prompt: áreas respeitadas, coerência verificada."""
    divs = [d for d in det["divisoes"] if d["cle"] != "_garage"]
    gar = next((d for d in det["divisoes"] if d["cle"] == "_garage"), None)
    niv_pedidos = sorted({d["niveau"] for d in divs})
    niveaux = 2 if max(niv_pedidos) >= 1 else 1           # a lista por piso manda (« lavandaria » não é « andar »)
    pieces: List[Dict[str, Any]] = []
    for d in divs:
        niv = d["niveau"]
        if niv < 0 or niv > 1:
            H(f"« {d['nom']} » : niveau {niv} non géré par l'esquisse automatique — placée au RDC, à déplacer dans le Studio.",
              f"« {d['nom']} »: piso {niv} não gerido pelo esboço automático — colocada no R/C, a mover no Estúdio.")
            niv = 0
        if niv == 1 and d["cle"] not in _SUPERIOR:
            H(f"« {d['nom']} » demandée à l'étage : placée au RDC par l'esquisse automatique — à remonter dans le Studio.",
              f"« {d['nom']} » pedida no 1.º andar: colocada no R/C pelo esboço automático — a subir no Estúdio.")
            niv = 0
        pieces.append({"cle": d["cle"], "nom": d["nom"], "zone": PIECES[d["cle"]][3], "surface": d["surface"], "niveau": niv})
    if niveaux == 2 and not any(p["cle"] == "wc" for p in pieces if p["niveau"] == 0) and not any(p["cle"] in ("sdb",) for p in pieces if p["niveau"] == 0):
        pieces.append({"cle": "wc", "nom": nom("wc", lang), "zone": "jour", "surface": PIECES["wc"][4], "niveau": 0})
        H("WC ajouté au RDC (aucune pièce d'eau demandée à ce niveau).", "WC acrescentado no R/C (nenhuma instalação sanitária pedida neste piso).")
    H(f"Programme détaillé lu dans le prompt : {len(pieces)} pièces avec les surfaces demandées (aucune mise à l'échelle).",
      f"Programa detalhado lido do prompt: {len(pieces)} divisões com as áreas pedidas (sem ajuste de escala).")
    # coerência das áreas por piso
    for niv, total in sorted(det["pisos"].items()):
        soma = sum(d["surface"] for d in divs if d["niveau"] == niv) + det["circulacao"].get(niv, 0.0)
        rotulo = {0: ("RDC", "R/C"), 1: ("Étage", "1.º andar")}.get(niv, (f"Niveau {niv}", f"Piso {niv}"))
        if abs(soma - total) <= 0.5:
            H(f"{rotulo[0]} : somme des pièces + circulations = {soma:g} m², conforme aux {total:g} m² indiqués.",
              f"{rotulo[1]}: soma das divisões + circulações = {soma:g} m², coerente com os {total:g} m² indicados.")
        else:
            H(f"{rotulo[0]} : somme des pièces + circulations = {soma:g} m² ≠ {total:g} m² indiqués (écart {soma - total:+g} m²).",
              f"{rotulo[1]}: soma das divisões + circulações = {soma:g} m² ≠ {total:g} m² indicados (diferença {soma - total:+g} m²).")
    if det["pisos"] and lu.get("surface"):
        tot = sum(det["pisos"].values())
        if abs(tot - lu["surface"]) > 0.5 and lu["surface"] > max(det["pisos"].values()):
            H(f"Total des niveaux {tot:g} m² ≠ {lu['surface']:g} m² annoncés.", f"Total dos pisos {tot:g} m² ≠ {lu['surface']:g} m² anunciados.")
        elif abs(tot - lu["surface"]) <= 0.5:
            H(f"Total des niveaux {tot:g} m² = surface annoncée.", f"Total dos pisos {tot:g} m² = área anunciada.")
    for x in det["nao_reconhecidas"]:
        H(f"Pièce non reconnue : {x} — à ajouter dans le Studio.", f"Divisão não reconhecida: {x} — a acrescentar no Estúdio.")
    garage = None
    if gar or lu.get("garage"):
        double = bool(lu.get("garage_double")) or bool(gar and gar["surface"] >= 30)
        surf = gar["surface"] if gar else (36.0 if double else 18.0)
        garage = {"nom": (gar or {}).get("nom") or nom("garage", lang), "surface": surf, "largeur": 6.0 if double else 3.0}
    toiture = lu.get("toiture") or "duas_aguas"
    if "toiture" not in lu:
        H("Toiture deux pans retenue (non précisé).", "Cobertura de duas águas considerada (não indicado).")
    habitavel = round(sum(p["surface"] for p in pieces), 1)
    return {"pieces": pieces, "niveaux": niveaux, "garage": garage, "toiture": toiture, "surface_visee": None,
            "surface_pieces_m2": habitavel, "pisos_indicados": det["pisos"], "circulacao_indicada": det["circulacao"],
            "chambres": sum(1 for p in pieces if p["cle"] in ("chambre", "suite")), "reconnu": True, "lu": lu,
            "hypotheses": hyp, "pedidos": pedidos(prompt, lang), "detalhado": True, "exteriores": exteriores(prompt)}


def programme_depuis_ia(data: Any, lang: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Programme renvoyé par l'IA (repli si le prompt n'est pas reconnu) → même structure, valeurs bornées."""
    if not isinstance(data, dict):
        return None
    texte = []
    if data.get("chambres") is not None:
        texte.append(f"{int(data['chambres'])} chambres")
    if data.get("surface"):
        texte.append(f"{float(data['surface']):.0f} m2")
    if data.get("niveaux") == 2:
        texte.append("r+1")
    elif data.get("niveaux") == 1:
        texte.append("plain-pied")
    for k, mot in (("garage", "garage"), ("bureau", "bureau"), ("buanderie", "buanderie"), ("suite", "suite parentale")):
        if data.get(k):
            texte.append(mot)
    if data.get("cuisine_ouverte") is False:
        texte.append("cuisine fermée")
    if data.get("toiture") in ("plana", "quatro_aguas", "uma_agua", "duas_aguas"):
        texte.append({"plana": "toit plat", "quatro_aguas": "4 pans", "uma_agua": "monopente", "duas_aguas": "2 pans"}[data["toiture"]])
    if not texte:
        return None
    p = programme("maison " + " ".join(texte), lang)
    p["source"] = "ia"
    return p
