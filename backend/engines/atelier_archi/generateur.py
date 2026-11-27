"""Programme → maquette du Studio de projet (déterministe).

Plan « en trois bandes », le plus courant en maison individuelle :
- bande avant (façade d'entrée, y = 0) : entrée, WC + rangement, escalier, cuisine fermée, pièces d'eau, bureau… ;
- bande de circulation (hall / dégagement), sur toute la longueur ;
- bande arrière (côté jardin) : séjour, puis chambres.
Pièces de jour à gauche, pièces de nuit à droite ; garage accolé à gauche, porte de service dans l'entrée.
Chaque pièce a une porte sur la circulation et (sauf entrée, WC, escalier) une façade pour ses fenêtres.

Unités : mètres, axes des murs (comme le Studio). Coordonnées arrondies à 5 cm.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from engines import estudio_projeto as EP
from engines.estudio_projeto import modelo as M
from engines.estudio_projeto import sitio

PAIS = sitio.PAIS
G = 0.05
HALL = 1.20                     # axe à axe : 1,10 m net avec des cloisons de 10 cm
PROF_AVANT = 3.60
PROF_GARAGE = 6.00
WC_PROF = 1.90                  # profondeur du WC côté circulation (le reste de la colonne = rangement)
ESC_LARG = 2.10                 # colonne d'escalier (escalier en U ou droit, proposé par le Studio)
# éclairement naturel : surface vitrée ≥ 1/6 de la surface (pratique française) ; ≥ 1/10 (RGEU, art. 71) au Portugal
RATIO_VITRAGE = 0.10 if PAIS == "PT" else 1 / 6
PE_DIREITO = 2.70 if PAIS == "PT" else 2.50
LAJE = 0.20
LARG_MIN = {"wc": 1.05, "sdb": 1.90, "sde": 1.60, "dressing": 1.40, "entree": 1.60, "cuisine": 2.40, "buanderie": 1.60,
            "bureau": 2.40, "chambre": 2.70, "suite": 3.20, "sejour": 3.60, "sejour_cuisine": 4.20}
FENETRE = {  # largeur, hauteur, allège
    "chambre": (1.20, 1.25, 0.95), "suite": (1.40, 1.25, 0.95), "bureau": (1.20, 1.25, 0.95),
    "cuisine": (1.20, 1.10, 1.10), "sejour": (1.20, 1.25, 0.95), "sejour_cuisine": (1.20, 1.25, 0.95),
    "sdb": (0.60, 0.60, 1.50), "sde": (0.60, 0.60, 1.50), "buanderie": (0.60, 0.60, 1.50), "wc": (0.60, 0.60, 1.50),
}
BAIE = (2.40, 2.15)             # baie coulissante du séjour (porte-fenêtre)


def _n(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def R(x: float) -> float:
    return round(round(x / G) * G, 3)


def _txt(fr: str, pt: str) -> str:
    return pt if PAIS == "PT" else fr


HABITABLES = {"chambre", "suite", "bureau", "sejour", "sejour_cuisine"}


def _largeur(p: Dict[str, Any], prof: float) -> float:
    """Largeur d'axe à axe pour obtenir la surface nette demandée dans une bande de profondeur `prof`.
    Pièces principales : dimension minimale selon la surface (RGEU art. 69.º : 2,10 / 2,40 / 2,70 m ; au-delà de 15 m²,
    longueur ≤ 2 × largeur) — règle de bonne proportion appliquée aussi en France."""
    if p.get("ouvert"):                                  # séjour ouvert sur le hall : la bande du hall fait partie de la pièce
        prof = prof + HALL
    net = max(1.0, prof - 0.20)
    w = max(LARG_MIN.get(p["cle"], 1.6), p["surface"] / net + 0.10)
    if p["cle"] in HABITABLES:
        a = p["surface"] * 1.25                         # marge : la pièce peut s'élargir en fermant la bande
        mini = 2.10 if a < 9.5 else (2.40 if a < 12.0 else (2.70 if a < 15.0 else max(2.70, net / 2.0)))
        w = max(w, mini + 0.25)                       # axes → net : cloison 6 cm + mur extérieur 15 cm + arrondi
    elif p["cle"] == "cuisine":
        w = max(w, 1.70 + 0.25)
    return R(w)


def _repartir(nuit: List[Dict[str, Any]], avant: List[float], arriere: List[float], pa: float, pb: float) -> Tuple[list, list]:
    """Chambres : chaque pièce va dans la bande la plus courte (équilibre la longueur de la maison)."""
    fa, fb = [], []
    la, lb = sum(avant), sum(arriere)
    for p in sorted(nuit, key=lambda q: -q["surface"]):
        wa, wb = _largeur(p, pa), _largeur(p, pb)
        if p["cle"] == "suite" or lb + wb <= la + wa:
            fb.append(p)
            lb += wb
        else:
            fa.append(p)
            la += wa
    return fa, fb


def _equilibrar(flex: List[Dict[str, Any]], la: float, lb: float, pa: float, pb: float) -> Tuple[list, list]:
    """Toutes les pièces « libres » (cuisine, bureau, pièces d'eau, chambres…) vont dans la bande la plus courte : les deux
    façades ont la même longueur, la maison reste compacte et proche de la surface demandée (pas de grande « pièce à
    affecter » pour fermer une bande vide). La suite parentale reste côté jardin."""
    fa, fb = [], []
    for p in sorted(flex, key=lambda q: -_largeur(q, pa)):
        wa, wb = _largeur(p, pa), _largeur(p, pb)
        if p["cle"] == "suite" or lb + wb <= la + wa:
            fb.append(p)
            lb += wb
        else:
            fa.append(p)
            la += wa
    ordre = {"cuisine": 0}                              # côté jardin : la cuisine reste contre le séjour
    fb.sort(key=lambda q: ordre.get(q["cle"], 1))
    return fa, fb


def _ranger(items: List[Dict[str, Any]], prof: float, x0: float = 0.0) -> float:
    x = x0
    for p in items:
        w = p.get("w") or _largeur(p, prof)
        p["x0"], p["x1"] = R(x), R(x + w)
        x += w
    return R(x)


def _fermer(items: List[Dict[str, Any]], mobiles: List[Dict[str, Any]], W: float, fin: float, debut: float, prof: float,
            niv: int, avisos: List[str]) -> None:
    """Ferme la bande jusqu'à la longueur de la maison : chaque pièce étirable s'élargit d'au plus 25 % ; au-delà de
    1,8 m restants, une pièce « à affecter » est ajoutée en bout de bande plutôt que de gonfler une pièce."""
    reste = R(W - fin)
    if reste <= 0.0:
        return
    if not mobiles:
        items.append({"cle": "rangement", "nom": _txt("Pièce à affecter", "Divisão a definir"), "surface": 0, "niveau": niv,
                      "x0": fin, "x1": W})
        return
    cands = [p for p in mobiles if p["cle"] not in ("wc", "escalier", "rangement")] or mobiles
    larg = {id(p): p["x1"] - p["x0"] for p in mobiles}
    cap = sum(0.25 * larg[id(p)] for p in cands)
    donne = min(reste, cap)
    if reste - donne < 1.8:                           # petit reste : réparti, même au-delà de 25 %
        donne = reste
    tot = sum(larg[id(p)] for p in cands)
    for p in cands:
        larg[id(p)] += R(donne * larg[id(p)] / tot)
    x = debut
    for p in mobiles:
        p["x0"], p["x1"] = R(x), R(x + larg[id(p)])
        x += larg[id(p)]
    mobiles[-1]["x1"] = R(mobiles[-1]["x1"] + (min(W, fin + donne) - x)) if abs(min(W, fin + donne) - x) < 0.3 else mobiles[-1]["x1"]
    x = mobiles[-1]["x1"]
    if W - x > 0.05:
        if W - x >= 1.2:
            items.append({"cle": "bureau" if W - x >= 2.4 else "rangement",
                          "nom": _txt("Pièce à affecter", "Divisão a definir") if W - x >= 2.4 else _txt("Rangement", "Arrumos"),
                          "surface": 0, "niveau": niv, "x0": x, "x1": W})
            avisos.append(_txt(f"Niveau {niv} : {W - x:.2f} m de façade sans pièce au programme → « Pièce à affecter » (bureau, rangement…).",
                               f"Piso {niv}: {W - x:.2f} m de fachada sem divisão no programa → «Divisão a definir» (escritório, arrumos…)."))
        else:
            mobiles[-1]["x1"] = W


def generer(prog: Dict[str, Any]) -> Dict[str, Any]:
    """Renvoie {"modelo", "avisos", "pieces"} — modèle du Studio normalisé."""
    from engines.atelier_archi.programme import nom as nom_piece
    avisos: List[str] = list(prog.get("hypotheses") or [])
    niveaux = int(prog.get("niveaux") or 1)
    pcs = [dict(p) for p in prog["pieces"]]
    deux = niveaux == 2

    def de(niv: int, *cles: str) -> List[Dict[str, Any]]:
        return [p for p in pcs if p["niveau"] == niv and p["cle"] in cles]

    jour_salle = de(0, "sejour", "sejour_cuisine")
    sej = max([p["surface"] for p in jour_salle] or [0])
    PB = R(min(5.2, max(3.9, math.sqrt(max(sej, 1) / 1.7)))) if jour_salle else 3.90
    PA = PROF_AVANT
    D = R(PA + HALL + PB)
    y_hall0, y_hall1 = PA, R(PA + HALL)

    def disposer() -> Tuple[Dict[Tuple[int, str], List[Dict[str, Any]]], Dict[Tuple[int, str], float], Tuple[float, float]]:
        for p in pcs:
            p.pop("x0", None), p.pop("x1", None)
            if p["cle"] != "wc":
                p.pop("w", None)
        bandes: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
        fins: Dict[Tuple[int, str], float] = {}
        # Plan ouvert (open space) : maison à étage sans chambre au RDC → le séjour s'ouvre sur le hall, qui devient
        # l'entrée du séjour ; seul un court dégagement (avec porte) dessert les pièces au-delà. Moins de couloir.
        ouvert = deux and bool(jour_salle) and not de(0, "chambre", "suite") and plan["ouvert"]
        for p in jour_salle:
            p["ouvert"] = ouvert
        av0: List[Dict[str, Any]] = list(de(0, "entree"))
        wc0 = de(0, "wc")
        if wc0:
            wc0[0]["w"] = LARG_MIN["wc"]
            av0 += wc0[:1]
        if deux:
            av0.append({"cle": "escalier", "nom": _txt("Escalier", "Escada"), "surface": 0, "niveau": 0, "w": ESC_LARG})
        ar0 = list(jour_salle)
        libres0 = de(0, "cuisine", "buanderie", "bureau", "sdb", "sde", "dressing", "chambre", "suite")
        fa, fb = _equilibrar(libres0, sum(p.get("w") or _largeur(p, PA) for p in av0), sum(_largeur(p, PB) for p in ar0), PA, PB)
        av0, ar0 = av0 + fa, ar0 + fb
        bandes[(0, "av")], bandes[(0, "ar")] = av0, ar0
        fins[(0, "av")], fins[(0, "ar")] = _ranger(av0, PA), _ranger(ar0, PB)
        sx = (0.0, 0.0)
        if deux:
            esc = next(p for p in av0 if p["cle"] == "escalier")
            sx0, sx1 = esc["x0"], esc["x1"]
            sx = (sx0, sx1)
            eau1 = de(1, "sdb", "sde", "dressing", "wc")
            ordre = {"sdb": 0, "sde": 1, "dressing": 2, "wc": 3}
            gauche = sorted(eau1, key=lambda p: (ordre[p["cle"]], -p["surface"]))[:1] if sx0 >= 1.6 else []
            for p in gauche:
                p["w"], p["x0"], p["x1"] = sx0, 0.0, sx0
            if not gauche and sx0 > 0.3:
                gauche = [{"cle": "rangement", "nom": _txt("Rangement", "Arrumos"), "surface": 0, "niveau": 1, "w": sx0, "x0": 0.0, "x1": sx0}]
            palier = {"cle": "escalier", "nom": _txt("Escalier", "Escada"), "surface": 0, "niveau": 1, "w": ESC_LARG, "x0": sx0, "x1": sx1}
            libres1 = [p for p in eau1 if p not in gauche] + de(1, "chambre", "suite")
            fa1, fb1 = _equilibrar(libres1, sx1, 0.0, PA, PB)
            droite = fa1
            fins[(1, "av")] = _ranger(droite, PA, sx1)
            fins[(1, "ar")] = _ranger(fb1, PB)
            bandes[(1, "av")], bandes[(1, "ar")] = gauche + [palier] + droite, list(fb1)
        return bandes, fins, sx

    def essai(notes: List[str]) -> Tuple[Dict[Tuple[int, str], List[Dict[str, Any]]], Dict[Tuple[int, str], float], Tuple[float, float]]:
        bandes, fins, sx = disposer()
        if deux:
            # équilibre des niveaux : si l'étage est nettement plus long, une chambre descend au rez-de-chaussée
            while True:
                l0 = max(fins[(0, "av")], fins[(0, "ar")])
                l1 = max(fins[(1, "av")], fins[(1, "ar")])
                ch1 = [p for p in pcs if p["niveau"] == 1 and p["cle"] == "chambre"]
                if l1 - l0 <= 2.0 or len(ch1) <= 1:
                    break
                bas = min(ch1, key=lambda p: p["surface"])
                bas["niveau"] = 0
                notes.append(_txt(f"« {bas['nom']} » placée au rez-de-chaussée pour équilibrer les deux niveaux.",
                                  f"«{bas['nom']}» colocado no rés-do-chão para equilibrar os dois pisos."))
                bandes, fins, sx = disposer()
        return bandes, fins, sx

    def emprise(fins: Dict[Tuple[int, str], float], sx: Tuple[float, float]) -> float:
        """Surface construite approchée (axes) : RDC + étage (en retrait si plus court)."""
        w0 = max(max(fins.values()), 6.0)
        tot = w0 * D
        if deux:
            w1 = max(fins[(1, "av")], fins[(1, "ar")], sx[1] + 1.2, 6.0)
            tot += (w1 if w0 - w1 >= 1.8 else w0) * D
        return tot

    # Profondeurs des bandes : on essaie plusieurs couples (avant, jardin) et on garde la maison la plus compacte —
    # même programme, moins de couloir et de murs, surface construite plus proche de la demande.
    niv0 = [p["niveau"] for p in pcs]
    PB0 = PB
    pas_av = (3.6, 3.9, 4.2, 4.5) if deux else (3.0, 3.3, 3.6, 3.9, 4.2)
    pas_ar = sorted({R(max(3.6, PB0 + d)) for d in (-0.4, 0.0, 0.4, 0.8, 1.2)})
    meilleur = None
    plan = {"ouvert": True}
    for ouv in (True, False):
      for pa in pas_av:
        for pb in pas_ar:
            plan["ouvert"] = ouv
            PA, PB = pa, pb
            D = R(PA + HALL + PB)
            y_hall0, y_hall1 = PA, R(PA + HALL)
            for p, n in zip(pcs, niv0):
                p["niveau"] = n
            b_, f_, s_ = essai([])
            cout = emprise(f_, s_) + 0.01 * (abs(pa - PROF_AVANT) + abs(pb - PB0)) + (0.0 if ouv else 0.5)
            if meilleur is None or cout < meilleur[0] - 1e-6:
                meilleur = (cout, pa, pb, ouv)
    _, PA, PB, plan["ouvert"] = meilleur
    D = R(PA + HALL + PB)
    y_hall0, y_hall1 = PA, R(PA + HALL)
    for p, n in zip(pcs, niv0):
        p["niveau"] = n
    notes: List[str] = []
    bandes, fins, (sx0, sx1) = essai(notes)
    avisos += notes

    W = R(max(max(fins.values()), 6.0))
    # Étage nettement plus court que le rez-de-chaussée : l'étage est en retrait et le reste du RDC devient une terrasse
    # accessible (au lieu d'élargir les pièces de l'étage ou d'ajouter une « pièce à affecter »).
    Wn = {0: W, 1: W}
    terrasse = 0.0
    if deux:
        w1 = R(max(fins[(1, "av")], fins[(1, "ar")], sx1 + 1.2, 6.0))
        if W - w1 >= 1.8:
            Wn[1] = w1
            terrasse = R((W - w1) * D)
    for (niv, b), items in bandes.items():
        fixe = deux and b == "av"                      # l'escalier et ce qui est à sa gauche restent alignés d'un niveau à l'autre
        mobiles = [p for p in items if p["x0"] >= sx1 - 1e-6 and p["cle"] != "escalier"] if fixe else items
        debut = sx1 if fixe else 0.0
        _fermer(items, mobiles, Wn[niv], fins[(niv, b)], debut, PA if b == "av" else PB, niv, avisos)
    if terrasse:
        avisos.append(_txt(f"Étage en retrait : terrasse d'environ {terrasse:.0f} m² sur le rez-de-chaussée, accessible depuis le dégagement.",
                           f"1.º andar recuado: terraço de cerca de {terrasse:.0f} m² sobre o rés-do-chão, com acesso pelo corredor."))

    # ---- bandes → compartiments (y)
    comps: List[Dict[str, Any]] = []
    for (niv, b), items in bandes.items():
        for p in items:
            y0, y1 = (0.0, y_hall0) if b == "av" else (y_hall1, D)
            comps.append({**p, "niveau": niv, "bande": b, "y0": y0, "y1": y1})

    tipos = {"garage_20": {"nome": _txt("Mur de garage 20 cm (parpaing enduit)", "Parede de garagem 20 cm (bloco de betão rebocado)"), "exterior": True, "camadas": [
        {"material": "Bloco de betão normal", "esp_m": 0.20}, {"material": "Reboco monomassa", "esp_m": 0.015}]}}
    pisos, paredes, vaos, rotulos, escadas = [], [], [], [], []
    noms_niv = [_txt("Rez-de-chaussée", "Rés-do-chão"), _txt("Étage", "1.º andar")]
    W0 = W
    portes_hall: List[Tuple[str, float, float]] = []
    for niv in range(niveaux):
        pid = f"p{niv}"
        W = Wn[niv]
        pisos.append({"id": pid, "nome": noms_niv[niv], "pe_direito_m": PE_DIREITO, "laje_m": LAJE})
        for lado, a, b in (("avant", (0, 0), (W, 0)), ("droite", (W, 0), (W, D)), ("arriere", (W, D), (0, D)), ("gauche", (0, D), (0, 0))):
            paredes.append({"id": f"{pid}_{lado}", "piso": pid, "a": list(a), "b": list(b), "tipo": "ext_30"})
        mine = [c for c in comps if c["niveau"] == niv]
        vert, horiz = [], []
        esc_x = [(c["x0"], c["x1"]) for c in mine if c["cle"] == "escalier"]
        # murs de la circulation, interrompus devant l'escalier (trémie / départ ouvert sur le hall)
        segs = [(0.0, W)]
        for e0, e1 in esc_x:
            segs = [s for a_, b_ in segs for s in ((a_, min(b_, e0)), (max(a_, e1), b_)) if s[1] - s[0] > 0.05]
        for a_, b_ in segs:
            horiz.append((y_hall0, a_, b_))
        sala_o = next((c for c in mine if c.get("ouvert") and c["bande"] == "ar"), None) if niv == 0 else None
        xs1 = sala_o["x1"] if sala_o and sala_o["x0"] < 0.05 else None
        if xs1 is not None:
            if xs1 < W - 0.05:
                horiz.append((y_hall1, xs1, W))
                vert.append((xs1, y_hall0, y_hall1))
                portes_hall.append((pid, xs1, R((y_hall0 + y_hall1) / 2)))
        else:
            horiz.append((y_hall1, 0.0, W))
        for c in mine:
            for xx in (c["x0"], c["x1"]):
                if 0.05 < xx < W - 0.05:
                    vert.append((xx, c["y0"], c["y1"]))
            if c["cle"] == "wc" and c["bande"] == "av" and niv == 0:
                horiz.append((R(y_hall0 - WC_PROF), c["x0"], c["x1"]))
        n = 0
        for xx, t0, t1 in M._fundir(vert):
            n += 1
            paredes.append({"id": f"{pid}_v{n}", "piso": pid, "a": [xx, t0], "b": [xx, t1], "tipo": "int_12"})
        for yy, t0, t1 in M._fundir(horiz):
            n += 1
            paredes.append({"id": f"{pid}_h{n}", "piso": pid, "a": [t0, yy], "b": [t1, yy], "tipo": "int_12"})
        # étiquettes
        occupe = sorted([(c["x0"] + c["x1"]) / 2 for c in mine if c["cle"] != "escalier"] + [x for e in esc_x for x in e])
        x_deb = xs1 if xs1 is not None else 0.0
        bornes = [x_deb] + [x for x in occupe if x_deb < x < W] + [W]
        gaps = [(a_, b_) for a_, b_ in zip(bornes, bornes[1:]) if not any(e0 - 1e-6 <= a_ and b_ <= e1 + 1e-6 for e0, e1 in esc_x)]
        g0, g1 = max(gaps or [(x_deb, W)], key=lambda ab: ab[1] - ab[0])
        if W - x_deb > 0.5:
            rotulos.append({"piso": pid, "x": R((g0 + g1) / 2), "y": R((y_hall0 + y_hall1) / 2),
                            "nome": _txt("Dégagement" if niv else "Hall", "Corredor" if niv else "Hall")})
        for c in mine:
            if c["cle"] == "escalier":
                continue
            if c["cle"] == "wc" and c["bande"] == "av" and niv == 0:
                rotulos.append({"piso": pid, "x": R((c["x0"] + c["x1"]) / 2), "y": R(y_hall0 - WC_PROF / 2), "nome": c["nom"]})
                if y_hall0 - WC_PROF > 0.9:
                    rotulos.append({"piso": pid, "x": R((c["x0"] + c["x1"]) / 2), "y": R((y_hall0 - WC_PROF) / 2),
                                    "nome": _txt("Placard", "Arrumo")})
                continue
            rotulos.append({"piso": pid, "x": R((c["x0"] + c["x1"]) / 2), "y": R((c["y0"] + c["y1"]) / 2), "nome": c["nom"]})
        if niv == 0 and niveaux == 2 and esc_x:
            from engines.estudio_projeto.escadas import propor
            e0, e1 = esc_x[0]
            ti = M.espessura(M.TIPOS_BASE["int_12"])
            te = M.espessura(M.TIPOS_BASE["ext_30"])
            faces = (e0 + ti / 2, te / 2, e1 - ti / 2, y_hall0)
            pr = propor(faces, PE_DIREITO + LAJE, folga=0.02)
            if pr:
                escadas.append({"id": "e1", "piso": pid, **pr})
            else:
                avisos.append(_txt("L'escalier n'a pas pu être posé automatiquement : placez-le dans le Studio.",
                                   "Não coube uma escada automaticamente: coloque-a no Estúdio."))

    W = W0
    # ---- garage
    garage = prog.get("garage")
    if garage:
        gw = R(float(garage.get("largeur") or 3.0) + 0.30)
        gd = PROF_GARAGE
        paredes += [{"id": "g_avant", "piso": "p0", "a": [-gw, 0], "b": [0, 0], "tipo": "garage_20"},
                    {"id": "g_gauche", "piso": "p0", "a": [-gw, gd], "b": [-gw, 0], "tipo": "garage_20"},
                    {"id": "g_arriere", "piso": "p0", "a": [0, gd], "b": [-gw, gd], "tipo": "garage_20"}]
        rotulos.append({"piso": "p0", "x": R(-gw / 2), "y": R(gd / 2), "nome": garage.get("nom") or nom_piece("garage")})

    # ---- exteriores pedidos (objetos editáveis do Estúdio: posição, rotação e medidas)
    objetos: List[Dict[str, Any]] = []
    ext = prog.get("exteriores") or {}
    if ext:
        sala = next((c for c in comps if c["niveau"] == 0 and c["bande"] == "ar" and c["cle"] in ("sejour", "sejour_cuisine")), None)
        cx = R((sala["x0"] + sala["x1"]) / 2) if sala else R(W / 2)
        y = R(D + 0.15)                                  # face exterior da fachada de tardoz
        no = [0]

        def obj(tipo: str, x: float, yy: float, larg: float, prof: float, rot: float = 0.0) -> None:
            no[0] += 1
            objetos.append({"id": f"ext{no[0]}", "piso": "p0", "tipo": tipo, "x": R(x), "y": R(yy), "rot": rot,
                            "largura_m": R(larg), "prof_m": R(prof)})
        feitos = []
        larg_t = R(min(max(W * 0.6, 6.0), 12.0))
        if ext.get("terraco"):
            obj("terraco_pedra", cx, y + 1.75, larg_t, 3.5)
            feitos.append(_txt(f"terrasse {_n(larg_t)} × 3,5 m", f"terraço {_n(larg_t)} × 3,5 m"))
            if ext.get("pergola"):
                obj("pergola", cx - larg_t / 2 + 2.0, y + 1.75, 4.0, 3.0)
                feitos.append(_txt("pergola 4 × 3 m", "pérgola 4 × 3 m"))
            if ext.get("refeicoes"):
                obj("mesa_exterior", cx - larg_t / 2 + 2.0, y + 1.75, 1.6, 0.9)
                obj("cozinha_exterior", cx - larg_t / 2 + 2.0, y + 0.55, 3.0, 0.7)
                feitos.append(_txt("coin repas extérieur", "zona de refeições exterior"))
            y = R(y + 3.5)
        if ext.get("piscina"):
            a, b = ext["piscina"]
            y_p = y + 1.5 + b / 2
            obj("deck_piscina", cx, y + 0.75, a + 3.0, 1.5)
            obj("piscina_infinita" if ext.get("transbordo") else "piscina", cx, y_p, a, b)
            feitos.append(_txt(f"piscine {_n(a)} × {_n(b)} m", f"piscina {_n(a)} × {_n(b)} m")
                          + ("" if ext.get("piscina_medidas_dadas") else _txt(" (dimensions types)", " (medidas tipo)")))
            y = R(y_p + b / 2)
        if ext.get("jardim"):
            lw = R(max(W, 10.0))
            obj("relvado", R(W / 2), y + 1.0 + 3.0, lw, 6.0)
            obj("arvore", R(W / 2 - lw / 2 + 1.5), y + 1.0 + 4.5, 3.0, 3.0)
            obj("arvore", R(W / 2 + lw / 2 - 1.5), y + 1.0 + 4.5, 3.0, 3.0)
            feitos.append(_txt("pelouse et plantations", "relvado e árvores"))
        if feitos:
            avisos.append(_txt("Extérieurs posés comme objets modifiables du Studio (position, rotation, dimensions) : ",
                               "Exteriores colocados como objetos editáveis do Estúdio (posição, rotação, medidas): ") + ", ".join(feitos) + ".")

    # ---- ouvertures
    def mur(piso: str, x: float, y: float, larg: float) -> Optional[Tuple[str, float]]:
        best = None
        for w in paredes:
            if w["piso"] != piso:
                continue
            (ax, ay), (bx, by) = w["a"], w["b"]
            L = math.hypot(bx - ax, by - ay)
            if L < larg + 0.1:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            t = (x - ax) * ux + (y - ay) * uy
            d = abs((x - ax) * uy - (y - ay) * ux)
            if d < 0.02 and larg / 2 + 0.05 <= t <= L - larg / 2 - 0.05:
                if best is None or d < best[2]:
                    best = (w["id"], R(t), d)
        return (best[0], best[1]) if best else None

    nv = [0]
    manques: List[str] = []

    def vao(piso: str, x: float, y: float, tipo: str, larg: float, haut: Optional[float] = None, peit: Optional[float] = None,
            quoi: str = "") -> bool:
        m = mur(piso, x, y, larg)
        if not m:
            manques.append(quoi)
            return False
        nv[0] += 1
        v = {"id": f"v{nv[0]}", "parede": m[0], "tipo": tipo, "pos_m": m[1], "largura_m": larg}
        if haut is not None:
            v["altura_m"] = haut
        if peit is not None:
            v["peitoril_m"] = peit
        vaos.append(v)
        return True

    for c in comps:
        pid = f"p{c['niveau']}"
        cx = R((c["x0"] + c["x1"]) / 2)
        w = c["x1"] - c["x0"]
        y_porte = y_hall0 if c["bande"] == "av" else y_hall1
        if c["cle"] == "escalier":
            continue
        if c["cle"] == "rangement":
            vao(pid, cx, y_porte, "porta", min(0.80, w - 0.3), quoi=c["nom"])
            continue
        larg_p = 1.40 if c["cle"] in ("sejour", "sejour_cuisine") else (0.80 if c["cle"] in ("wc", "sde", "dressing") else 0.90)
        if not (c.get("ouvert") and c["niveau"] == 0 and c["bande"] == "ar" and c["x0"] < 0.05):
            vao(pid, cx, y_porte, "porta", min(larg_p, w - 0.3), quoi=c["nom"])
        if c["cle"] == "wc" and c["bande"] == "av" and c["niveau"] == 0:
            if y_hall0 - WC_PROF > 0.9:                # placard sous le WC, ouvert sur l'entrée
                vao(pid, c["x0"], R((y_hall0 - WC_PROF) / 2), "porta", min(0.70, y_hall0 - WC_PROF - 0.3), quoi=_txt("placard", "arrumo"))
            continue
        y_fac = 0.0 if c["bande"] == "av" else D
        if c["cle"] == "entree":
            vao(pid, cx, y_fac, "porta", min(1.00, w - 0.3), 2.15, 0.0, quoi=_txt("porte d'entrée", "porta de entrada"))
            continue
        f = FENETRE.get(c["cle"])
        if not f:
            continue
        surf = w * (c["y1"] - c["y0"] + (HALL if c.get("ouvert") and c["niveau"] == 0 else 0.0))  # par excès
        if c.get("ouvert") and c["niveau"] == 0:        # séjour ouvert : l'escalier (ouvert sur le hall) fait partie de la pièce
            surf += sum(max(0.0, min(e["x1"], c["x1"]) - max(e["x0"], c["x0"])) * PA
                        for e in comps if e["niveau"] == 0 and e["cle"] == "escalier")
        besoin = max(RATIO_VITRAGE * surf, 1.08 if PAIS == "PT" else 0.0) if c["cle"] not in ("sdb", "sde", "buanderie", "wc", "dressing") else 0
        ouv: List[Tuple[str, float, float, float]] = []
        if c["cle"] in ("sejour", "sejour_cuisine") and c["bande"] == "ar" and c["niveau"] == 0:
            ouv.append(("portada", BAIE[0], BAIE[1], 0.0))
        fl, fh, fp = f
        grande = c["cle"] in ("sejour", "sejour_cuisine") and c["niveau"] == 0 and c["bande"] == "ar"
        while sum(o[1] * o[2] for o in ouv) < besoin or not ouv:
            ouv.append(("portada", BAIE[0], BAIE[1], 0.0) if grande else ("janela", fl, fh, fp))   # séjour : baies plutôt que fenêtres
            if len(ouv) > 6:
                break
        # place disponible sur la façade de la pièce (30 cm aux extrémités, 40 cm entre ouvertures)
        while len(ouv) > 1 and sum(o[1] for o in ouv) + 0.4 * (len(ouv) - 1) > w - 0.6:
            ouv.pop()
        vit = sum(o[1] * o[2] for o in ouv)
        if besoin and vit < besoin:                    # moins de fenêtres, mais plus larges (2,40 m au plus chacune)
            dispo = w - 0.6 - 0.4 * (len(ouv) - 1)
            jan = [i for i, o in enumerate(ouv) if o[0] == "janela"]
            manque = besoin - vit
            for i in jan:
                t, lg, ht, pt = ouv[i]
                gagne = min(2.40 - lg, manque / ht / len(jan), max(0.0, dispo - sum(o[1] for o in ouv)))
                if gagne > 0:
                    ouv[i] = (t, R(lg + gagne + 0.049), ht, pt)
            vit = sum(o[1] * o[2] for o in ouv)
        if besoin and vit < besoin and ouv and ouv[0][0] == "portada":   # grand séjour : baie coulissante plus large (≤ 4,80 m)
            t, lg, ht, pt = ouv[0]
            dispo = w - 0.6 - 0.4 * (len(ouv) - 1) - sum(o[1] for o in ouv[1:])
            nl = R(min(4.80, max(lg, dispo), lg + (besoin - vit) / ht + 0.049))
            ouv[0] = (t, nl, ht, pt)
            vit = sum(o[1] * o[2] for o in ouv)
        if sum(o[1] for o in ouv) > w - 0.6 and ouv:
            t, lg, ht, pt = ouv[0]
            ouv = [(t, R(max(0.6, w - 0.6)), ht, pt)]
            vit = ouv[0][1] * ht
        if besoin and vit + 1e-6 < besoin:
            avisos.append(_txt(f"« {c['nom']} » : {vit:.2f} m² de vitrage pour {besoin:.2f} m² visés (façade trop courte).",
                               f"«{c['nom']}»: {vit:.2f} m² de envidraçado para {besoin:.2f} m² pretendidos (fachada curta)."))
        tot = sum(o[1] for o in ouv)
        gap = (w - tot) / (len(ouv) + 1) if ouv else 0
        x = c["x0"] + gap
        for tipo, lg, ht, pt in ouv:
            vao(pid, R(x + lg / 2), y_fac, tipo, lg, ht, pt, quoi=c["nom"])
            x += lg + gap
    if garage:
        gw = R(float(garage.get("largeur") or 3.0) + 0.30)
        portail = min(4.80 if gw > 5 else 2.40, gw - 0.6)
        vao("p0", R(-gw / 2), 0.0, "portao", portail, 2.10, 0.0, quoi=_txt("porte de garage", "portão da garagem"))
        vao("p0", 0.0, R(min(PA, PROF_GARAGE) / 2), "porta", 0.90, quoi=_txt("porte de service du garage", "porta de serviço da garagem"))
    for pid_, xh, yh in portes_hall:
        vao(pid_, xh, yh, "porta", 0.90, quoi=_txt("porte du dégagement", "porta do corredor"))
    if terrasse:
        vao("p1", Wn[1], R((y_hall0 + y_hall1) / 2), "porta", 0.90, quoi=_txt("porte-fenêtre de la terrasse", "porta do terraço"))
    if manques:
        avisos.append(_txt("Ouvertures non posées (mur trop court) : ", "Vãos não colocados (parede curta): ") + ", ".join(sorted(set(manques))))

    modelo = M.normalizar({"pisos": pisos, "tipos_parede": tipos, "paredes": paredes, "vaos": vaos, "rotulos": rotulos,
                           "escadas": escadas, "objetos": objetos, "cobertura": {"tipo": prog.get("toiture") or "duas_aguas", "inclinacao_graus": 35.0 if PAIS != "PT" else 25.0,
                                                             "beiral_m": 0.40, "laje_m": LAJE},
                           "origem": "atelier-prompt"})
    if (prog.get("toiture") or "duas_aguas") == "plana":
        modelo["cobertura"]["inclinacao_graus"] = 3.0
    der = EP.derivar(modelo)
    # contrôle : surface obtenue par pièce vs programme
    obt = {d["nome"]: d["area_m2"] for d in der["medicoes"]["divisoes"]}
    ecarts = []
    for p in pcs:
        a = obt.get(p["nom"])
        if a and p["surface"] and p["cle"] != "wc" and abs(a - p["surface"]) / p["surface"] > 0.25:
            ecarts.append(f"{p['nom']} {a:.1f} m² ({p['surface']:.1f} visés)")
    if ecarts:
        avisos.append(_txt("Surfaces à revoir : ", "Áreas a rever: ") + "; ".join(ecarts))
    tot = der["medicoes"]["totais"]
    nom_garage = (garage or {}).get("nom") or "§"
    habitable = round(sum(d["area_m2"] for d in der["medicoes"]["divisoes"] if d["nome"] != nom_garage), 2)
    cible = prog.get("surface_visee")
    if cible and abs(habitable - cible) / cible > 0.10:
        avisos.append(_txt(f"Surface habitable obtenue {habitable:.0f} m² pour {cible:.0f} m² demandés : réduisez ou supprimez des pièces "
                           f"dans le Studio, ou précisez le programme.",
                           f"Área útil obtida {habitable:.0f} m² para {cible:.0f} m² pedidos: reduza ou elimine divisões no Estúdio, "
                           f"ou precise o programa."))
    avisos.append(_txt(f"Hypothèses : hauteur sous plafond {PE_DIREITO:.2f} m, murs extérieurs et cloisons types du pays, "
                       f"vitrage ≥ 1/6 de la surface des pièces principales — tout est modifiable dans le Studio.",
                       f"Hipóteses: pé-direito {PE_DIREITO:.2f} m, paredes exteriores e divisórias correntes, envidraçado ≥ 1/10 "
                       f"da área dos compartimentos habitáveis (RGEU) — tudo editável no Estúdio."))
    return {"modelo": modelo, "avisos": avisos, "geo": {"W": W, "D": D, "PA": PA, "HALL": HALL, "niveaux": niveaux},
            "resume": {"longueur_m": W + (R(float(garage.get('largeur') or 3.0) + 0.30) if garage else 0), "profondeur_m": D,
                       "niveaux": niveaux, "surface_habitable_m2": habitable, "surface_utile_m2": tot["area_util_m2"], "surface_construite_m2": tot["area_bruta_construcao_m2"],
                       "pieces": [{"nom": d["nome"], "niveau": d["piso"], "surface_m2": d["area_m2"]} for d in der["medicoes"]["divisoes"]],
                       "erreurs": der.get("erros") or []}}


# Surfaces minimales retenues quand on réduit un programme (au-dessus du RGEU art. 66.º / 68.º et du logement décent).
MIN_AJUSTE = {"chambre": 9.5, "suite": 11.0, "sejour": 16.0, "sejour_cuisine": 20.0, "cuisine": 7.0, "bureau": 7.0, "sdb": 3.5,
              "sde": 3.5, "wc": 1.8, "entree": 3.0, "buanderie": 2.5, "dressing": 2.5}


def _construite_sans_garage(r: Dict[str, Any], prog: Dict[str, Any]) -> float:
    der = EP.derivar(r["modelo"])
    return der["medicoes"]["totais"]["area_bruta_construcao_m2"] - float((prog.get("garage") or {}).get("surface") or 0)


def ajustar_area(prog: Dict[str, Any], alvo: float, iteracoes: int = 8, tolerancia: float = 0.03) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ajuste à la surface construite voulue (hors garage) : toutes les pièces sont mises à l'échelle du même facteur,
    sans descendre sous les minimums, et la maquette est régénérée jusqu'à ±3 % (le générateur est déterministe et rapide).
    Renvoie (programme ajusté, résultat de `generer`)."""
    base = [dict(p) for p in prog["pieces"]]
    quartos = [p for p in base if p["cle"] in ("chambre", "suite")]
    principal = id(max(quartos, key=lambda p: p["surface"])) if quartos else None   # quarto de casal : ≥ 10,5 m² (RGEU art. 66.º)
    f = 1.0
    meilleur = None
    for _ in range(iteracoes):
        pieces = [{**p, "surface": round(max(11.0 if id(p) == principal else MIN_AJUSTE.get(p["cle"], 1.5), p["surface"] * f), 1)
                   if p["cle"] != "wc" else p["surface"]} for p in base]
        pg = {**prog, "pieces": pieces}
        r = generer(pg)
        b = _construite_sans_garage(r, pg)
        ecart = (b - alvo) / alvo
        if meilleur is None or abs(ecart) < abs(meilleur[0]):
            meilleur = (ecart, pg, r, b)
        if abs(ecart) <= tolerancia:
            break
        f *= (alvo / b) ** 0.9
    ecart, pg, r, b = meilleur
    r["avisos"].append(_txt(f"Surfaces des pièces ajustées pour viser {alvo:.0f} m² construits hors garage : obtenu {b:.0f} m² ({ecart:+.0%}).",
                            f"Áreas das divisões ajustadas para {alvo:.0f} m² de construção sem garagem: obtido {b:.0f} m² ({ecart:+.0%})."))
    return pg, r
