"""Croquis à main levée → murs droits, raccordés, à l'échelle → maquette du Studio de projet.

Entrée (mètres, repère de la feuille) :
    traits   : [{"type": "mur" | "mur_ext" | "cloison" | "porte" | "fenetre" | "baie" | "portail", "points": [[x, y], …]}]
    textes   : [{"x", "y", "nom"}]                 noms des pièces écrits sur le croquis
    cotes    : [{"a": [x, y], "b": [x, y], "m": 12.4}]   longueurs réelles connues → échelle du dessin
    y_bas    : True si l'axe y de la feuille descend (écran, photo) : retourné pour le Studio (y vers le fond)

Méthode (déterministe, le même dessin donne toujours le même plan) :
1. échelle : médiane des cotes (écart > 5 % entre cotes signalé) ; sans cote, la grille de la feuille fait foi ;
2. chaque trait de mur est simplifié (Ramer-Douglas-Peucker) en segments ;
3. redressement : un segment à moins de 12° de l'horizontale ou de la verticale est rendu orthogonal ;
4. alignement : les abscisses des murs verticaux et les ordonnées des murs horizontaux proches (< 35 cm) sont unifiées ;
5. raccords : une extrémité proche d'un autre mur (< 35 cm) y est prolongée ou ramenée (angles et T) ;
6. grille de 5 cm, segments colinéaires fusionnés, segments < 25 cm supprimés ;
7. murs extérieurs = contour de l'emprise (sauf si le trait a été dessiné avec l'outil « mur extérieur » / « cloison ») ;
8. portes et fenêtres : posées sur le mur le plus proche, largeur = longueur du trait projetée sur le mur.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from engines.estudio_projeto import modelo as M
from engines.estudio_projeto import sitio

G = 0.05
TOL = 0.35
ANGLE = math.radians(12)
PAIS = sitio.PAIS
OUVERTURES = {"porte": ("porta", 0.90, 2.15, 0.0), "fenetre": ("janela", 1.20, 1.25, 0.95), "baie": ("portada", 2.40, 2.15, 0.0),
              "portail": ("portao", 2.40, 2.10, 0.0)}


class ErreurCroquis(ValueError):
    pass


def _r(x: float) -> float:
    return round(round(x / G) * G, 3)


def _txt(fr: str, pt: str) -> str:
    return pt if PAIS == "PT" else fr


def _rdp(pts: List[Tuple[float, float]], eps: float) -> List[Tuple[float, float]]:
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    L = math.hypot(bx - ax, by - ay)
    dmax, k = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / L if L > 1e-9 else math.hypot(px - ax, py - ay)
        if d > dmax:
            dmax, k = d, i
    if dmax > eps:
        return _rdp(pts[:k + 1], eps)[:-1] + _rdp(pts[k:], eps)
    return [pts[0], pts[-1]]


def _pts(v: Any) -> List[Tuple[float, float]]:
    out = []
    for p in v or []:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            x, y = float(p[0]), float(p[1])
            if math.isfinite(x) and math.isfinite(y):
                out.append((x, y))
    return out


def echelle(cotes: List[Dict[str, Any]], avis: List[str]) -> float:
    ratios = []
    for c in cotes or []:
        try:
            m = float(c.get("m"))
        except (TypeError, ValueError):
            continue
        pa = _pts([c.get("a")])
        pb = _pts([c.get("b")])
        if not pa or not pb or m <= 0:
            continue
        d = math.dist(pa[0], pb[0])
        if d > 1e-6:
            ratios.append(m / d)
    if not ratios:
        return 1.0
    ratios.sort()
    med = ratios[len(ratios) // 2]
    if len(ratios) > 1 and (ratios[-1] - ratios[0]) / med > 0.05:
        avis.append(_txt(f"Les cotes ne sont pas cohérentes entre elles (écart {100 * (ratios[-1] - ratios[0]) / med:.0f} %) : "
                         f"échelle médiane retenue, vérifiez le croquis.",
                         f"As cotas não são coerentes entre si (diferença {100 * (ratios[-1] - ratios[0]) / med:.0f} %): "
                         f"escala mediana considerada, verifique o esboço."))
    return med


def _cluster(vals: List[float], tol: float) -> Dict[float, float]:
    """Valeurs 1D proches (< tol) → leur moyenne. Renvoie {valeur: valeur unifiée}."""
    out: Dict[float, float] = {}
    s = sorted(set(vals))
    grp: List[float] = []
    for v in s + [math.inf]:
        if grp and v - grp[-1] > tol:
            m = sum(grp) / len(grp)
            for g in grp:
                out[g] = m
            grp = []
        grp.append(v)
    return out


def _proj(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float, float]:
    """(t en mètres depuis a, distance au segment prolongé, longueur)."""
    L = math.dist(a, b)
    if L < 1e-9:
        return 0.0, math.dist(p, a), 0.0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    t = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
    d = abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux)
    return t, d, L


def nettoyer(traits: List[Dict[str, Any]], textes: Optional[List[Dict[str, Any]]] = None, cotes: Optional[List[Dict[str, Any]]] = None,
             y_bas: bool = True, pe_direito: Optional[float] = None, toiture: Optional[str] = None) -> Dict[str, Any]:
    avis: List[str] = []
    if not isinstance(traits, list) or not traits:
        raise ErreurCroquis(_txt("Dessinez au moins un mur.", "Desenhe pelo menos uma parede."))
    if len(traits) > 800:
        raise ErreurCroquis(_txt("Croquis trop chargé (800 traits au plus).", "Esboço demasiado carregado (máx. 800 traços)."))
    k = echelle(cotes or [], avis)
    sy = -1.0 if y_bas else 1.0

    def tr(p: Tuple[float, float]) -> Tuple[float, float]:
        return p[0] * k, p[1] * k * sy

    murs: List[Dict[str, Any]] = []      # {"a", "b", "force": None|"ext"|"int"}
    ouv_in: List[Tuple[str, List[Tuple[float, float]]]] = []
    for t in traits:
        typ = str((t or {}).get("type") or "mur")
        pts = [tr(p) for p in _pts((t or {}).get("points"))][:4000]
        if len(pts) < 1:
            continue
        if typ in OUVERTURES:
            ouv_in.append((typ, pts))
            continue
        if len(pts) < 2:
            continue
        force = "ext" if typ == "mur_ext" else ("int" if typ == "cloison" else None)
        ferme = len(pts) > 3 and math.dist(pts[0], pts[-1]) < 0.6
        simp = _rdp(pts, 0.12)
        if ferme:
            simp[-1] = simp[0]
        for a, b in zip(simp, simp[1:]):
            if math.dist(a, b) >= 0.15:
                murs.append({"a": list(a), "b": list(b), "force": force})
    if not murs:
        raise ErreurCroquis(_txt("Aucun mur lisible dans le croquis.", "Nenhuma parede legível no esboço."))

    # 3. redressement
    for w in murs:
        (ax, ay), (bx, by) = w["a"], w["b"]
        ang = math.atan2(by - ay, bx - ax) % math.pi
        if ang < ANGLE or ang > math.pi - ANGLE:
            ym = (ay + by) / 2
            w["a"][1] = w["b"][1] = ym
            w["o"] = "h"
        elif abs(ang - math.pi / 2) < ANGLE:
            xm = (ax + bx) / 2
            w["a"][0] = w["b"][0] = xm
            w["o"] = "v"
        else:
            w["o"] = "d"
    # 4. alignement des axes (murs h : y ; murs v : x), puis extrémités sur ces axes
    cx = _cluster([w["a"][0] for w in murs if w["o"] == "v"], TOL)
    cy = _cluster([w["a"][1] for w in murs if w["o"] == "h"], TOL)
    for w in murs:
        if w["o"] == "v":
            w["a"][0] = w["b"][0] = cx[w["a"][0]]
        elif w["o"] == "h":
            w["a"][1] = w["b"][1] = cy[w["a"][1]]
    xs = sorted(set(cx.values()))
    ys = sorted(set(cy.values()))
    for w in murs:
        for e in ("a", "b"):
            p = w[e]
            if w["o"] == "h" and xs:
                x = min(xs, key=lambda v: abs(v - p[0]))
                if abs(x - p[0]) < TOL:
                    p[0] = x
            if w["o"] == "v" and ys:
                y = min(ys, key=lambda v: abs(v - p[1]))
                if abs(y - p[1]) < TOL:
                    p[1] = y
    # 5. raccords : extrémité près d'un autre mur → sur ce mur (T), y compris par prolongement court
    for w in murs:
        for e in ("a", "b"):
            p = tuple(w[e])
            best = None
            for o in murs:
                if o is w:
                    continue
                t, d, L = _proj(p, tuple(o["a"]), tuple(o["b"]))
                if d < TOL and -TOL <= t <= L + TOL and (best is None or d < best[0]):
                    best = (d, o, max(0.0, min(L, t)), L)
            if best and best[0] > 1e-6:
                d, o, t, L = best
                (ax, ay), (bx, by) = o["a"], o["b"]
                q = [ax + (bx - ax) * t / L, ay + (by - ay) * t / L]
                if w["o"] == "h":
                    w[e][0] = q[0]
                elif w["o"] == "v":
                    w[e][1] = q[1]
                else:
                    w[e] = q
    # 6. grille, fusion des colinéaires, suppression des petits bouts
    for w in murs:
        w["a"] = [_r(w["a"][0]), _r(w["a"][1])]
        w["b"] = [_r(w["b"][0]), _r(w["b"][1])]
    h = [(w["a"][1], w["a"][0], w["b"][0], w["force"]) for w in murs if w["o"] == "h"]
    v = [(w["a"][0], w["a"][1], w["b"][1], w["force"]) for w in murs if w["o"] == "v"]
    diag = [w for w in murs if w["o"] == "d" and math.dist(w["a"], w["b"]) >= 0.25]
    segs: List[Dict[str, Any]] = []
    for c, t0, t1 in M._fundir([(c, a, b) for c, a, b, _ in h]):
        f = next((ff for cc, a, b, ff in h if abs(cc - c) < 1e-6 and min(a, b) < t1 and max(a, b) > t0 and ff), None)
        segs.append({"a": [t0, c], "b": [t1, c], "force": f})
    for c, t0, t1 in M._fundir([(c, a, b) for c, a, b, _ in v]):
        f = next((ff for cc, a, b, ff in v if abs(cc - c) < 1e-6 and min(a, b) < t1 and max(a, b) > t0 and ff), None)
        segs.append({"a": [c, t0], "b": [c, t1], "force": f})
    segs += [{"a": w["a"], "b": w["b"], "force": w["force"]} for w in diag]
    segs = [s for s in segs if math.dist(s["a"], s["b"]) >= 0.25]
    if len(segs) < 3:
        raise ErreurCroquis(_txt("Il faut au moins 3 murs pour fermer une pièce.", "São precisas pelo menos 3 paredes para fechar uma divisão."))
    if len(segs) > M.LIM["paredes"]:
        raise ErreurCroquis(_txt("Trop de murs.", "Demasiadas paredes."))
    # origine : coin bas-gauche de l'emprise
    x0 = min(min(s["a"][0], s["b"][0]) for s in segs)
    y0 = min(min(s["a"][1], s["b"][1]) for s in segs)
    for s in segs:
        s["a"] = [_r(s["a"][0] - x0), _r(s["a"][1] - y0)]
        s["b"] = [_r(s["b"][0] - x0), _r(s["b"][1] - y0)]

    # 7. murs extérieurs = contour de l'emprise
    try:
        from shapely.geometry import LineString
        from shapely.ops import polygonize, unary_union
        lignes = unary_union([LineString([tuple(s["a"]), tuple(s["b"])]) for s in segs])
        polys = list(polygonize(lignes))
        emprise = unary_union(polys) if polys else None
    except Exception:  # noqa: BLE001
        emprise = None
    if emprise is None or emprise.is_empty:
        avis.append(_txt("Le croquis ne forme pas de pièce fermée : vérifiez les angles (les murs doivent se toucher).",
                         "O esboço não forma uma divisão fechada: verifique os cantos (as paredes têm de se tocar)."))
    bord = emprise.boundary if emprise is not None and not emprise.is_empty else None
    paredes = []
    for i, s in enumerate(segs):
        ext = s["force"] == "ext"
        if s["force"] is None and bord is not None:
            from shapely.geometry import Point
            mx, my = (s["a"][0] + s["b"][0]) / 2, (s["a"][1] + s["b"][1]) / 2
            ext = bord.distance(Point(mx, my)) < 0.05
        paredes.append({"id": f"w{i + 1}", "piso": "p0", "a": s["a"], "b": s["b"], "tipo": "ext_30" if ext else "int_12"})

    # 8. ouvertures
    vaos = []
    for j, (typ, pts) in enumerate(ouv_in):
        tipo, l0, h0, p0 = OUVERTURES[typ]
        pts = [(p[0] - x0, p[1] - y0) for p in pts]
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        best = None
        for w in paredes:
            t, d, L = _proj((mx, my), tuple(w["a"]), tuple(w["b"]))
            if d < 0.8 and 0 <= t <= L and (best is None or d < best[0]):
                best = (d, w, t, L)
        if not best:
            avis.append(_txt(f"Une {typ} dessinée loin de tout mur a été ignorée.", f"Um vão ({typ}) desenhado longe das paredes foi ignorado."))
            continue
        _, w, t, L = best
        ts = [_proj(p, tuple(w["a"]), tuple(w["b"]))[0] for p in pts]
        larg = max(ts) - min(ts)
        larg = l0 if larg < 0.4 else _r(max(0.6, larg))
        larg = min(larg, L - 0.2)
        if larg < 0.3:
            continue
        t = (max(ts) + min(ts)) / 2 if (max(ts) - min(ts)) >= 0.4 else t
        t = max(larg / 2 + 0.05, min(L - larg / 2 - 0.05, t))
        if w["tipo"] == "int_12" and tipo != "porta":
            tipo = "porta"
        vaos.append({"id": f"v{j + 1}", "parede": w["id"], "tipo": tipo, "pos_m": _r(t), "largura_m": larg,
                     "altura_m": h0, "peitoril_m": p0})
    rotulos = []
    for tx in textes or []:
        p = _pts([[tx.get("x"), tx.get("y")]]) if isinstance(tx, dict) else []
        if p and str(tx.get("nom") or "").strip():
            q = tr(p[0])
            rotulos.append({"piso": "p0", "x": _r(q[0] - x0), "y": _r(q[1] - y0), "nome": str(tx["nom"])[:40]})
    pd = pe_direito or (2.70 if PAIS == "PT" else 2.50)
    modelo = M.normalizar({"pisos": [{"id": "p0", "pe_direito_m": pd, "laje_m": 0.20}], "paredes": paredes, "vaos": vaos,
                           "rotulos": rotulos, "cobertura": {"tipo": toiture or "duas_aguas"}, "origem": "atelier-croquis"})
    if k != 1.0:
        avis.append(_txt(f"Échelle tirée des cotes : 1 unité du dessin = {k:.3f} m.", f"Escala tirada das cotas: 1 unidade do desenho = {k:.3f} m."))
    diag_n = sum(1 for s in segs if s["a"][0] != s["b"][0] and s["a"][1] != s["b"][1])
    if diag_n:
        avis.append(_txt(f"{diag_n} mur(s) en biais conservé(s) tel(s) que dessiné(s).", f"{diag_n} parede(s) oblíqua(s) mantida(s) como desenhada(s)."))
    return {"modelo": modelo, "avisos": avis, "stats": {"murs": len(paredes), "ouvertures": len(vaos), "echelle": k}}
