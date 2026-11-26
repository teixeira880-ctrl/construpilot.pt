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


def R(x: float) -> float:
    return round(round(x / G) * G, 3)


def _txt(fr: str, pt: str) -> str:
    return pt if PAIS == "PT" else fr


def _largeur(p: Dict[str, Any], prof: float) -> float:
    """Largeur d'axe à axe pour obtenir la surface nette demandée dans une bande de profondeur `prof`."""
    net = max(1.0, prof - 0.20)
    return R(max(LARG_MIN.get(p["cle"], 1.6), p["surface"] / net + 0.10))


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
        av0: List[Dict[str, Any]] = list(de(0, "entree"))
        wc0 = de(0, "wc")
        if wc0:
            wc0[0]["w"] = LARG_MIN["wc"]
            av0 += wc0[:1]
        if deux:
            av0.append({"cle": "escalier", "nom": _txt("Escalier", "Escada"), "surface": 0, "niveau": 0, "w": ESC_LARG})
        av0 += de(0, "cuisine", "buanderie", "bureau") + de(0, "sdb", "sde", "dressing")
        ar0 = list(jour_salle)
        fa, fb = _repartir(de(0, "chambre", "suite"), [_largeur(p, PA) for p in av0], [_largeur(p, PB) for p in ar0], PA, PB)
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
            droite = [p for p in eau1 if p not in gauche]
            fa1, fb1 = _repartir(de(1, "chambre", "suite"), [_largeur(p, PA) for p in droite], [], PA, PB)
            droite += fa1
            fins[(1, "av")] = _ranger(droite, PA, sx1)
            fins[(1, "ar")] = _ranger(fb1, PB)
            bandes[(1, "av")], bandes[(1, "ar")] = gauche + [palier] + droite, list(fb1)
        return bandes, fins, sx

    bandes, fins, (sx0, sx1) = disposer()
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
            avisos.append(_txt(f"« {bas['nom']} » placée au rez-de-chaussée pour équilibrer les deux niveaux.",
                               f"«{bas['nom']}» colocado no rés-do-chão para equilibrar os dois pisos."))
            bandes, fins, (sx0, sx1) = disposer()

    W = R(max(max(fins.values()), 6.0))
    for (niv, b), items in bandes.items():
        fixe = deux and b == "av"                      # l'escalier et ce qui est à sa gauche restent alignés d'un niveau à l'autre
        mobiles = [p for p in items if p["x0"] >= sx1 - 1e-6 and p["cle"] != "escalier"] if fixe else items
        debut = sx1 if fixe else 0.0
        _fermer(items, mobiles, W, fins[(niv, b)], debut, PA if b == "av" else PB, niv, avisos)

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
    for niv in range(niveaux):
        pid = f"p{niv}"
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
        bornes = [0.0] + [x for x in occupe if 0 < x < W] + [W]
        gaps = [(a_, b_) for a_, b_ in zip(bornes, bornes[1:]) if not any(e0 - 1e-6 <= a_ and b_ <= e1 + 1e-6 for e0, e1 in esc_x)]
        g0, g1 = max(gaps or [(0.0, W)], key=lambda ab: ab[1] - ab[0])
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

    # ---- garage
    garage = prog.get("garage")
    if garage:
        gw = R(float(garage.get("largeur") or 3.0) + 0.30)
        gd = PROF_GARAGE
        paredes += [{"id": "g_avant", "piso": "p0", "a": [-gw, 0], "b": [0, 0], "tipo": "garage_20"},
                    {"id": "g_gauche", "piso": "p0", "a": [-gw, gd], "b": [-gw, 0], "tipo": "garage_20"},
                    {"id": "g_arriere", "piso": "p0", "a": [0, gd], "b": [-gw, gd], "tipo": "garage_20"}]
        rotulos.append({"piso": "p0", "x": R(-gw / 2), "y": R(gd / 2), "nome": garage.get("nom") or nom_piece("garage")})

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
        surf = (w - 0.2) * (c["y1"] - c["y0"] - 0.2)
        besoin = RATIO_VITRAGE * surf if c["cle"] not in ("sdb", "sde", "buanderie", "wc", "dressing") else 0
        ouv: List[Tuple[str, float, float, float]] = []
        if c["cle"] in ("sejour", "sejour_cuisine") and c["bande"] == "ar" and c["niveau"] == 0:
            ouv.append(("portada", BAIE[0], BAIE[1], 0.0))
        fl, fh, fp = f
        while sum(o[1] * o[2] for o in ouv) < besoin or not ouv:
            ouv.append(("janela", fl, fh, fp))
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
    if manques:
        avisos.append(_txt("Ouvertures non posées (mur trop court) : ", "Vãos não colocados (parede curta): ") + ", ".join(sorted(set(manques))))

    modelo = M.normalizar({"pisos": pisos, "tipos_parede": tipos, "paredes": paredes, "vaos": vaos, "rotulos": rotulos,
                           "escadas": escadas, "cobertura": {"tipo": prog.get("toiture") or "duas_aguas", "inclinacao_graus": 35.0 if PAIS != "PT" else 25.0,
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
    return {"modelo": modelo, "avisos": avisos,
            "resume": {"longueur_m": W + (R(float(garage.get('largeur') or 3.0) + 0.30) if garage else 0), "profondeur_m": D,
                       "niveaux": niveaux, "surface_habitable_m2": habitable, "surface_utile_m2": tot["area_util_m2"], "surface_construite_m2": tot["area_bruta_construcao_m2"],
                       "pieces": [{"nom": d["nome"], "niveau": d["piso"], "surface_m2": d["area_m2"]} for d in der["medicoes"]["divisoes"]],
                       "erreurs": der.get("erros") or []}}
