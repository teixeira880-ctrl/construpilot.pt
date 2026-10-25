"""Plans d'exécution électricité / plomberie / ventilation / chauffage PAR LOGEMENT TYPE d'un immeuble.

Chaque fraction distincte (typologie + dimensions) est convertie en « logement » du moteur maison ConstruPilot (bet_core) :
pièces (relevées sur les plans d'architecte — units[].rooms — ou, à défaut, zonage indicatif déduit de la typologie, de la
façade et du palier), baies sur les façades, chute EU de l'immeuble. Les moteurs éprouvés du moteur maison font ensuite le
travail : NF C 15-100 / RTIEBT (points par pièce, circuits numérotés, différentiels, schéma unifilaire du tableau), NF DTU 60.11
/ RGSPPDADAR (appareils cotés, attentes, nourrices EF/ECS, évacuations Ø et pentes vers la chute), ventilation et chauffage.
"""
from __future__ import annotations

import copy
import math
import re

from . import mep as fmep
from .lang import _
from .model import Frame

ROOM_LBL = {"entree": ("Entrée", "Hall"), "circulation": ("Dégagement", "Corredor"), "salle_eau": ("Salle de bains", "Instalação sanitária"),
            "salle_eau2": ("Salle d'eau", "I.S. 2"), "cuisine": ("Cuisine", "Cozinha"), "buanderie": ("Buanderie", "Lavandaria"),
            "sejour": ("Séjour", "Sala"), "chambre": ("Chambre", "Quarto"), "annexe_seche": ("Rangement", "Arrumos"),
            "bureau": ("Bureau", "Escritório")}
FIX_MAP = {"wc": "wc", "lavatorio": "lavabo", "duche": "douche", "banheira": "baignoire", "pia": "evier", "mll": "lave_vaisselle", "mlr": "lave_linge"}


def _lbl(k):
    return _(*ROOM_LBL[k])


def _ntyp(un) -> int:
    t = (un.typology or "T2").upper()
    return int(t[1]) if len(t) > 1 and t[1].isdigit() else 2


def _entry_side(m: Frame, un, sides) -> str:
    """Côté du palier : contre un noyau (cage d'escalier), sinon côté intérieur au bâtiment le plus proche d'un noyau."""
    core = [s for s, L, nat in sides if nat == "core"]
    if core:
        return max(core, key=lambda s: next(L for s_, L, n in sides if s_ == s))
    ext = {s for s, L, nat in sides if nat == "ext"}
    cand = [s for s in ("y0", "y1", "x0", "x1") if s not in ext] or ["y0", "y1", "x0", "x1"]
    if not m.cores:
        return cand[0]
    c = min(m.cores, key=lambda c: math.hypot((c["x0"] + c["x1"]) / 2 - un.center[0], (c["y0"] + c["y1"]) / 2 - un.center[1]))
    cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
    dist = {"y0": abs(cy - un.y0), "y1": abs(cy - un.y1), "x0": abs(cx - un.x0), "x1": abs(cx - un.x1)}
    return min(cand, key=lambda s: dist[s])


def _entry_pos(m: Frame, un, side: str) -> float:
    """Abscisse (le long du côté d'entrée, repère local) de la porte palière : face au noyau / à la colonne la plus proche."""
    pts = [((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2) for c in m.cores] + [(float(r["x"]), float(r["y"])) for r in m.risers]
    L = (un.x1 - un.x0) if side in ("y0", "y1") else (un.y1 - un.y0)
    if not pts:
        return L / 2
    px, py = min(pts, key=lambda p: math.hypot(p[0] - un.center[0], p[1] - un.center[1]))
    v = (px - un.x0) if side in ("y0", "y1") else (py - un.y0)
    return min(max(v, 1.2), L - 1.2)


def zoning(m: Frame, un) -> tuple[list[dict], bool]:
    """Pièces du logement (repère local, origine au coin bas-gauche de la fraction). (pièces, indicatif ?)"""
    L, W = un.x1 - un.x0, un.y1 - un.y0
    if getattr(un, "rooms", None):
        out = []
        for r in un.rooms:
            out.append({"name": str(r.get("name") or r.get("type")), "type": r.get("type") or "annexe_seche",
                        "x0": float(r["x0"]) - un.x0, "y0": float(r["y0"]) - un.y0, "x1": float(r["x1"]) - un.x0, "y1": float(r["y1"]) - un.y0})
        return out, False
    from .thermal import _sides
    sides = _sides(m, un)
    es = _entry_side(m, un, sides)
    # repère (u le long du côté d'entrée, v vers l'intérieur) → (x, y) local
    Lu, D = (L, W) if es in ("y0", "y1") else (W, L)

    def R(u0, u1, v0, v1):
        u0, u1, v0, v1 = max(0.0, u0), min(Lu, u1), max(0.0, v0), min(D, v1)
        if es == "y0":
            return u0, v0, u1, v1
        if es == "y1":
            return u0, W - v1, u1, W - v0
        if es == "x0":
            return v0, u0, v1, u1
        return L - v1, u0, L - v0, u1

    n = _ntyp(un)
    ds = min(max(0.36 * D, 2.6), 3.4)
    if D - ds < 3.0:
        ds = max(2.2, D - 3.0)
    dc = 1.1 if D >= 7.0 else 0.0              # couloir entre pièces de service et pièces de vie
    dsr = ds - dc
    ue = _entry_pos(m, un, es)
    hw = 1.8
    h0, h1 = max(0.0, ue - hw / 2), min(Lu, ue + hw / 2)
    if h0 < 1.2:                                    # bande résiduelle trop étroite : le hall va jusqu'au mur
        h0 = 0.0
    if Lu - h1 < 1.2:
        h1 = Lu
    left, right = h0, Lu - h1
    big_right = right >= left
    rooms = [{"k": "entree", "r": R(h0, h1, 0, ds)}]
    # pièces de service (côté le plus long, depuis le hall) ; cuisine au bout, contre la salle
    seq = [("salle_eau", 2.3)] + ([("salle_eau2", 1.9)] if n >= 3 else []) + [("cuisine", 3.2)]
    span = right if big_right else left
    need = sum(w for _k, w in seq)
    k = min(1.0, span / need) if need else 1.0
    if span - need > 2.0 and n >= 2:
        seq.insert(len(seq) - 1, ("buanderie", min(1.8, span - need - 0.2)))
        need += seq[-2][1]
        k = min(1.0, span / need)
    cur = h1 if big_right else h0
    for kk, w in seq:
        w2 = w * k if kk != "cuisine" else (span - sum(x[1] * k for x in seq[:-1]))
        extra = 0.0
        if kk == "cuisine" and w2 > 5.1:            # cuisine ≤ 4,2 m : le reste devient bureau / arrumos
            extra, w2 = w2 - 4.2, 4.2
        if extra and big_right:                     # la cuisine reste au bout, contre la salle
            a, b = cur, cur + extra
            rooms.append({"k": "bureau" if extra >= 2.4 else "annexe_seche", "r": R(a, b, 0, dsr)})
            cur = b
        elif extra:
            a, b = cur - extra, cur
            rooms.append({"k": "bureau" if extra >= 2.4 else "annexe_seche", "r": R(a, b, 0, dsr)})
            cur = a
        a, b = (cur, cur + w2) if big_right else (cur - w2, cur)
        rooms.append({"k": kk, "r": R(a, b, 0, dsr)})
        cur = b if big_right else a
    other = left if big_right else right
    if other >= 1.2:
        a, b = (0, h0) if big_right else (h1, Lu)
        rooms.append({"k": "buanderie" if n >= 2 and not any(r["k"] == "buanderie" for r in rooms) and other <= 2.4 else "annexe_seche",
                      "r": R(a, b, 0, dsr)})
    # bande de vie : salle côté cuisine, chambres de l'autre côté
    sala_w = min(max(3.8, 0.38 * Lu), Lu - 2.7 * max(n, 1) if n else Lu)
    sala_w = max(sala_w, min(3.8, Lu))
    if big_right:
        sala = (Lu - sala_w, Lu)
        qa, qb = 0.0, Lu - sala_w
    else:
        sala = (0.0, sala_w)
        qa, qb = sala_w, Lu
    sala_v0 = dsr if (dc and (sala[1] <= h0 + 1e-6 or sala[0] >= h1 - 1e-6)) else ds
    rooms.append({"k": "sejour", "r": R(sala[0], sala[1], sala_v0, D)})
    nq = n
    while nq > 0 and (qb - qa) / nq < 2.6:
        nq -= 1
    if nq:
        w = (qb - qa) / nq
        for i in range(nq):
            rooms.append({"k": "chambre", "i": i + 1, "r": R(qa + i * w, qa + (i + 1) * w, ds, D)})
    elif qb - qa > 0.5:
        rooms[-1]["r"] = R(min(sala[0], qa), max(sala[1], qb), ds, D)
    if dc:                                          # couloir sous les pièces de service, du hall aux chambres (hors hall)
        lo, hi = (min(qa, sala[0]), max(qb, sala[1])) if sala_v0 == ds else (qa, qb)
        for a, b in ((lo, min(hi, h0)), (max(lo, h1), hi)):
            if b - a > 0.6:
                rooms.append({"k": "circulation", "r": R(a, b, dsr, ds)})
    out = []
    for r in rooms:
        x0, y0, x1, y1 = r["r"]
        if x1 - x0 < 0.6 or y1 - y0 < 0.6:
            continue
        typ = {"salle_eau2": "salle_eau", "bureau": "chambre"}.get(r["k"], r["k"])
        nm = _lbl(r["k"]) + (f" {r['i']}" if r.get("i") else "")
        out.append({"name": nm, "type": typ, "x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2), "y1": round(y1, 2),
                    "_k": r["k"]})
    return out, True


def _fixtures(un, rooms):
    fx = fmep.fixtures_of(un)
    is_ = [r for r in rooms if r["type"] == "salle_eau"]
    kit = next((r for r in rooms if r["type"] == "cuisine"), None)
    lav = next((r for r in rooms if r["type"] == "buanderie"), None)
    for r in rooms:
        r["fixtures"] = []
    wc, lb = fx.get("wc", 1), fx.get("lavatorio", 1)
    bath = fx.get("banheira", 0)
    sh = fx.get("duche", 0) + (0 if bath else 1 if not fx.get("duche") else 0)
    for i, r in enumerate(is_):
        f = []
        if i == 0:
            f.append("baignoire" if bath else "douche")
        elif sh or bath:
            f.append("douche")
        if lb > i:
            f.append("lavabo")
        if wc > i:
            f.append("wc")
        r["fixtures"] = f
    if kit is not None:
        kit["fixtures"] = ["evier"] + (["lave_vaisselle"] if fx.get("mll") else []) + (["lave_linge"] if fx.get("mlr") and lav is None else [])
    return rooms


def house_raw(m: Frame, un, rooms: list[dict], indicative: bool) -> dict:
    from .thermal import _sides
    L, W = round(un.x1 - un.x0, 3), round(un.y1 - un.y0, 3)
    ext = {s for s, Ls, nat in _sides(m, un) if nat == "ext"}
    lv = m.level(un.level)
    ch = round(max(2.40, lv.height - m.slab_h(lv.id) - 0.12), 2)
    pos = {"y0": ("y", 0.0), "y1": ("y", W), "x0": ("x", 0.0), "x1": ("x", L)}
    sides = {}
    for s, (ax, p) in pos.items():
        sides[f"S_{s}"] = {"axis": ax, "pos": p, "type": "facade" if s in ext else "mitoyen",
                           "label": _("Façade", "Fachada") + f" ({s})" if s in ext else _("Mur séparatif / palier", "Parede de separação / patamar") + f" ({s})"}
    openings = []
    for r in rooms:
        if r["type"] not in ("sejour", "chambre", "cuisine"):
            continue
        for s in ext:
            ax, p = pos[s]
            if ax == "y" and abs((r["y0"] if p == 0 else r["y1"]) - p) < 0.05:
                a, b = r["x0"], r["x1"]
            elif ax == "x" and abs((r["x0"] if p == 0 else r["x1"]) - p) < 0.05:
                a, b = r["y0"], r["y1"]
            else:
                continue
            w = min(b - a - 0.6, 2.4 if r["type"] == "sejour" else 1.4 if r["type"] == "chambre" else 1.2)
            if w < 0.6:
                continue
            c = (a + b) / 2
            openings.append({"id": f"V{len(openings) + 1}", "level": "F", "side": f"S_{s}", "from": round(c - w / 2, 2), "to": round(c + w / 2, 2),
                             "sill": 0.0 if r["type"] == "sejour" else 0.9, "height": 2.2 if r["type"] == "sejour" else 1.3,
                             "kind": _("porte-fenêtre", "porta-janela") if r["type"] == "sejour" else _("fenêtre", "janela")})
            break
    walls = []
    t = 0.08
    for r in rooms:                                  # cloisons sur les limites intérieures des pièces
        for (x0, y0, x1, y1) in ((r["x0"], r["y0"], r["x1"], r["y0"]), (r["x1"], r["y0"], r["x1"], r["y1"])):
            if (x0 == x1 and (x0 <= 0.05 or x0 >= L - 0.05)) or (y0 == y1 and (y0 <= 0.05 or y0 >= W - 0.05)):
                continue
            if x0 == x1:
                walls.append({"x0": x0 - t / 2, "y0": y0, "x1": x0 + t / 2, "y1": y1})
            else:
                walls.append({"x0": x0, "y0": y0 - t / 2, "x1": x1, "y1": y0 + t / 2})
    # chute EU de l'immeuble la plus proche (dans la fraction ou en gaine adjacente) ; sinon implantation automatique
    eu = [r for r in m.risers if str(r.get("kind", "")).upper() == "EU"]
    stacks = []
    for r in eu:
        x, y = float(r["x"]) - un.x0, float(r["y"]) - un.y0
        if -1.2 <= x <= L + 1.2 and -1.2 <= y <= W + 1.2:
            stacks.append({"id": str(r["id"]), "x": round(min(max(x, 0.2), L - 0.2), 2), "y": round(min(max(y, 0.2), W - 0.2), 2), "d": 100,
                           "serves": _("pièces humides du logement", "compartimentos húmidos da fração")})
    hall = next((r for r in rooms if r["type"] == "entree"), rooms[0])
    mep_cfg = {}
    if stacks:
        st = stacks[0]
        mep_cfg = {"stacks": stacks, "collector": {"path": [(st["x"], st["y"]), (st["x"], st["y"])],
                                                    "exit": _("raccordement à la chute collective de l'immeuble", "ligação ao tubo de queda coletivo do edifício")},
                   "nourrice": {"x": round(hall["x0"] + 0.4, 2), "y": round(hall["y1"] - 0.3, 2), "level": "F", "room": hall["name"]},
                   "outdoor_tap": {"level": "F", "room": hall["name"], "x": round(hall["x0"] + 0.3, 2), "y": round(hall["y0"] + 0.3, 2)}}
    for r in rooms:
        r["area_pc"] = round((r["x1"] - r["x0"]) * (r["y1"] - r["y0"]), 2)
    proj = dict(m.project or {})
    from .mep import power_kva
    proj["subscribed_kva"] = power_kva(un.typology, m.country)
    proj["name"] = f"{proj.get('name') or ''} — {un.name}".strip(" —")
    return {"project": proj, "user_hypotheses": copy.deepcopy(m.raw.get("user_hypotheses") or {}),
            "envelope": {"length_x": L, "width_y": W, "wall_total_thickness": 0.12, "wall_structural_thickness": 0.10, "lining_thickness": 0.02},
            "sides": sides, "levels": [{"id": "F", "name": f"{un.name} ({un.typology}) — {lv.name}", "floor_top": 0.0, "slab_thickness": m.slab_h(lv.id),
                                        "ceiling_height": ch, "use": "habitation"}],
            "roof": {"type": "terrasse", "eaves_level": ch + 0.3, "ridge_level": ch + 0.3, "ridge_axis": "y", "ridge_x": L / 2, "covering": "terrasse",
                     "gables": [], "eaves_sides": [], "dormers": []},
            "openings": openings,
            "stair": {"x0": -80.0, "x1": -79.0, "y0": -80.0, "y1": -79.0, "type": "—", "flights": [], "cage_walls": []},
            "interior_walls": {"F": walls}, "rooms": {"F": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rooms]},
            "geotech": {}, "mep": mep_cfg, "_indicative": indicative}


APART = [("Arrivée Enedis (CCPI en limite de propriété)", "Arrivée depuis la colonne montante — compteur en gaine palière"),
         ("Arrivée E-REDES (CCPI en limite de propriété)", "Chegada da coluna montante — contador no patamar / quadro de colunas"),
         ("GTL dans le hall RDC (près de l'entrée)", "GTL dans l'entrée du logement"), ("GTL em o hall RDC (près de l'entrée)", "QE no hall da fração"),
         ("Prise de terre : boucle à fond de fouille en câblette Cu 25 mm² sous les semelles, barrette de mesure en LT, R ≤ 100 Ω",
          "Terre : conducteur principal de protection depuis la colonne montante (prise de terre de l'immeuble en fond de fouille)"),
         ("Terra de proteção : anel de cobre 25 mm² no fundo das valas das sapatas, ligador amovível de medição, R ≤ 100 Ω",
          "Terra de proteção : condutor de proteção desde a coluna montante (elétrodo de terra do edifício em anel nas fundações)")]
PT_MS = [   # textes des planches détaillées du moteur maison → português (projeto PT : RTIEBT, RGSPPDADAR, NP 1037-1)
    (r"^Arrivée depuis la colonne montante — compteur en gaine palière$", "Chegada da coluna montante — contador no patamar / quadro de colunas"),
    (r"^Arrêté du 24/03/1982 : (\d+) pièces principales → cuisine (\d+)/(\d+) m³/h, total mini (\d+) m³/h\.$",
     r"NP 1037-1 : \1 compartimentos principais → cozinha \2/\3 m³/h, total mínimo \4 m³/h."),
    (r"^Attentes cotées, alimentation EF/ECS en pieuvre \(multicouche sous fourreau\), évacuations PVC avec pentes, chutes Ø100$",
     "Pontos de alimentação cotados, distribuição AF/AQS por coletores (multicamada em manga), esgotos em PVC com inclinação, tubos de queda Ø110"),
    (r"^Bande périphérique 8 mm$", "Banda perimetral 8 mm"),
    (r"^Bande périphérique 8 mm sur tout le pourtour ; joints de fractionnement > 40 m² ou côté > 8 m et au droit des portes\.$",
     "Banda perimetral 8 mm em todo o contorno ; juntas de fracionamento > 40 m² ou lado > 8 m e nas portas."),
    (r"^Bouche d'extraction$", "Boca de extração"), (r"^Bouche de soufflage$", "Boca de insuflação"), (r"^Boucle \(aller / retour\)$", "Circuito (ida / retorno)"),
    (r"^Boucles ≤ 100 m liaisons comprises ; ≤ 12 départs par collecteur ; débitmètres et vannes d'équilibrage sur chaque départ\.$",
     "Circuitos ≤ 100 m incluindo ligações ; ≤ 12 saídas por coletor ; caudalímetros e válvulas de equilíbrio em cada saída."),
    (r"^Caisson VMC hygro B$", "Ventilador VMC higrorregulável"),
    (r"^Coffret (\d+) rangées × (\d+) modules — (\d+) modules utilisés \+ 20 % de réserve — GTL dans l'entrée du logement, largeur ≥ 0,60 m$",
     r"Quadro de \1 filas × \2 módulos — \3 módulos utilizados + 20 % de reserva — QE no hall da fração, largura ≥ 0,60 m"),
    (r"^Collecteur / nourrice$", "Coletor"), (r"^Collecteur (\S+) — (\d+) départs$", r"Coletor \1 — \2 saídas"),
    (r"^Commande \(interrupteur\)$", "Comando (interruptor)"), (r"^Conduit d'extraction$", "Conduta de extração"), (r"^Conduit de soufflage$", "Conduta de insuflação"),
    (r"^Conduits en volume chauffé \(sinon isolés 50 mm\) ; trappes d'accès au caisson et aux plénums ; détalonnage des portes 2 cm\.$",
     "Condutas no volume aquecido (senão isoladas 50 mm) ; alçapões de acesso ao ventilador e aos plenos ; folga inferior das portas 2 cm."),
    (r"^Conduits souples isolés Ø80 \(pièces d'eau\) et Ø125 \(cuisine\) vers le caisson, rejet Ø160 en toiture$",
     "Condutas flexíveis isoladas Ø80 (instalações sanitárias) e Ø125 (cozinha) até ao ventilador, rejeição Ø160 na cobertura"),
    (r"^Contacteur HC$", "Contactor bi-horário"),
    (r"^Cotes d'implantation des attentes depuis les nus finis des murs ; hauteurs des attentes selon fiches fabricants\.$",
     "Cotas de implantação dos pontos a partir das faces acabadas das paredes ; alturas segundo as fichas dos fabricantes."),
    (r"^Différentiels type A : plaque de cuisson, lave-linge, PAC, IRVE \(type F ou A-EV\) ; parafoudre obligatoire si PAC/équipement de sécurité \(NF C 15-100 §443\)\.$",
     "Diferenciais tipo A : placa, máquina de lavar roupa, bomba de calor, carregamento VE (tipo F ou A-EV) ; descarregador de sobretensões (RTIEBT secção 443)."),
    (r"^Distribution en pieuvre depuis nourrices EF et ECS \(multicouche sous fourreau dans les dalles de compression et doublages\) ; une vanne d'arrêt par pièce d'eau$",
     "Distribuição por coletores AF e AQS (multicamada em manga no enchimento e nos panos interiores) ; uma válvula de seccionamento por compartimento húmido"),
    (r"^Départ \(aller\)$", "Ida"), (r"^Départ divisionnaire$", "Saída de circuito"), (r"^Eau chaude sanitaire \(ECS\)$", "Água quente sanitária (AQS)"),
    (r"^Eau froide \(EF\)$", "Água fria (AF)"),
    (r"^Essai d'étanchéité 6 bar 24 h avant coulage \(PV\) ; première mise en chauffe 7 jours après coulage, montée 5 °C/jour\.$",
     "Ensaio de estanquidade 6 bar 24 h antes da betonagem (auto) ; primeiro aquecimento 7 dias após a betonagem, subida 5 °C/dia."),
    (r"^GTL — tableau \+ coffret de communication$", "QE — quadro elétrico + ATI (ITED)"), (r"^Gaine technique$", "Courette técnica"),
    (r"^Hauteurs \(axe\) : prises 0,30 ; cuisine plan de travail 1,10 ; commandes et thermostats 0,90 à 1,30 ; salles d'eau hors volumes 0-1-2\.$",
     "Alturas (eixo) : tomadas 0,30 ; cozinha bancada 1,10 ; comandos e termóstatos 0,90 a 1,30 ; instalações sanitárias fora dos volumes 0-1-2 (RTIEBT 701)."),
    (r"^Jeu de barres$", "Barramento"), (r"^Liaison de commande$", "Ligação de comando"),
    (r"^NF C 15-100 : circuits numérotés, cheminements sous fourreaux ICTA, hauteurs de pose$", "RTIEBT : circuitos numerados, traçados em tubo VD/ICTA, alturas de montagem"),
    (r"^Niveau : (\d+) boucles, (\d+) m de tube ; collecteur avec débitmètres, vannes motorisées et purgeurs\.$",
     r"Piso : \1 circuitos, \2 m de tubo ; coletor com caudalímetros, válvulas motorizadas e purgadores."),
    (r"^Niveau : extraction (\d+) m³/h — total logement (\d+) m³/h \(cuisine pointe (\d+) m³/h\)\.$",
     r"Piso : extração \1 m³/h — total da fração \2 m³/h (cozinha em ponta \3 m³/h)."),
    (r"^PAC air/eau (\d+) kW \(Tbase (-?\d+) °C\) : Alimentation dédiée depuis le tableau, disjoncteur courbe D, interrupteur de proximité \(NF C 15-100\)$",
     r"Bomba de calor \1 kW (θ projeto \2 °C) : circuito dedicado desde o quadro, disjuntor curva D, interruptor de proximidade (RTIEBT)"),
    (r"^Parafoudre type 2$", "Descarregador de sobretensões tipo 2"), (r"^Prise 2P\+T 16 A$", "Tomada 2P+T 16 A"), (r"^Prise RJ45 grade 2TV$", "Tomada RJ45 (ITED)"),
    (r"^Rejet en toiture par sortie de toit Ø160 ; entrées d'air hygroréglables dans les menuiseries des pièces principales\.$",
     "Rejeição na cobertura Ø160 ; entradas de ar autorreguláveis nas caixilharias dos compartimentos principais."),
    (r"^Retour$", "Retorno"), (r"^Robinet d'arrêt à l'attente$", "Válvula de seccionamento no ponto"), (r"^Réservation dans le plancher$", "Negativo na laje"),
    (r"^Sortie de câble / circuit spécialisé$", "Saída de cabo / circuito dedicado"),
    (r"^Terre : conducteur principal de protection depuis la colonne montante \(prise de terre de l'immeuble en fond de fouille\)$",
     "Terra : condutor de proteção desde a coluna montante (elétrodo de terra do edifício em anel nas fundações)"),
    (r"^Thermostat d'ambiance$", "Termóstato ambiente"),
    (r"^VMC simple flux hygroréglable type B \(entrées d'air hygro en menuiseries\)$", "Ventilação mecânica simples fluxo higrorregulável (entradas de ar nas caixilharias)"),
    (r"^jeu de barres / peignes$", "barramento / pentes"), (r"^larg\. 0,60 · h 1,80 maxi organes de commande$", "larg. 0,60 · h máx. 1,80 dos órgãos de comando"),
    (r"^réglage selon abonnement \(à confirmer Enedis\)$", "regulação segundo a potência contratada (a confirmar E-REDES)"),
    (r"^sèche-serv\.$", "toalheiro"),
]
USE_MS_PT = [True]          # planches « BET » détaillées (circuits tirés, unifilaire dessiné) aussi pour les projets portugais


def _loc(t: str, pt: bool) -> str:
    import re
    for a, b in APART:
        if a in t:
            t = t.replace(a, b)
    if pt:
        for rx, rep in PT_MS:
            t2 = re.sub(rx, rep, t)
            if t2 != t:
                from .sheets import NAT
                NAT.add(t2)
                return t2
    return t


def _apartment_texts(sh, pt: bool = False):
    """Textes du moteur maison adaptés au logement en immeuble (arrivée par la colonne montante, terre de l'immeuble) et,
    pour un projet portugais, rédigés en português (normes portugaises)."""
    for i, it in enumerate(sh.items):
        if it and it[0] == "text":
            t = _loc(it[3], pt)
            if t != it[3]:
                sh.items[i] = it[:3] + (t,) + it[4:]
    sh.notes = [_loc(n, pt) for n in sh.notes]
    sh.subtitle = _loc(sh.subtitle, pt)
    if getattr(sh, "legend", None):
        sh.legend = [(k, _loc(v, pt)) for k, v in sh.legend]


def unit_types(m: Frame) -> list[tuple]:
    """Fractions distinctes (typologie + dimensions) → (fraction représentative, [noms des fractions identiques])."""
    groups = []
    for un in m.units:
        key = ((un.typology or "").upper(), round(un.x1 - un.x0, 1), round(un.y1 - un.y0, 1))
        g = next((g for g in groups if g[0] == key), None)
        lab = f"{un.name} ({m.level(un.level).name})"
        if g:
            g[2].append(lab)
        else:
            groups.append([key, un, [lab]])
    return [(g[1], g[2]) for g in groups]


def sheets_for(m: Frame, kinds: set | None = None) -> list:
    """Planches des logements types : électricité (plan + unifilaire), plomberie (plan), ventilation et chauffage (FR)."""
    from engines.bet_core import mep as hmep
    from engines.bet_core import model as hmodel
    from engines.bet_core import sheets as hs
    from engines.bet_core.i18n import protect
    out = []
    pt = m.country == "PT"
    old_scale, old_shift = hs.PLAN_SCALE[0], hs.PLAN_SHIFT[0]
    try:
        for k, (un, same) in enumerate(unit_types(m)):
            rooms, ind = zoning(m, un)
            rooms = _fixtures(un, rooms)
            raw = house_raw(m, un, rooms, ind)
            raw["project"]["country"] = m.country
            hm = hmodel.from_dict(raw)
            protect(hm)
            L, W = hm.L, hm.W
            sc = next((s for s in (50, 75, 100, 125) if (L + 3.6) * 1000 / s <= 272 and (W + 4.2) * 1000 / s <= 250), 125)
            hs.PLAN_SCALE[0] = sc
            hs.PLAN_SHIFT[0] = max(0.0, ((hs.PLAN_AREA[3] - hs.PLAN_AREA[1]) * sc / 1000 - (W + 4.4)) / 2 - 0.4) if sc != 50 else 0.0
            e, p = hmep.electrical(hm), hmep.plumbing(hm)
            p["fixtures"] = [f for f in p["fixtures"] if f["fixture"] != "robinet_ext"]     # logement en étage : pas de robinet extérieur
            tag = str(k + 1)     # numéro de type : les lettres se confondaient avec les noms des fractions (A, B, …)
            same_txt = ", ".join(same[:8]) + (f" (+{len(same) - 8})" if len(same) > 8 else "")
            note = [_(f"Logement type {tag} : {same_txt}.", f"Fração tipo {tag} : {same_txt}."),
                    _("Cloisonnement indicatif déduit de la typologie, de la façade et du palier — à remplacer par les plans de l'architecte.",
                      "Compartimentação indicativa deduzida da tipologia, da fachada e do patamar — a substituir pelas plantas da arquitetura.") if ind else ""]
            made = []
            if pt and not USE_MS_PT[0]:
                made += [(hs.elec_level(hm, e, "F", f"ELE-{tag}"), "elec"), (hs.elec_panel(hm, e), "elec_uni"),
                         (hs.plumb_level(hm, p, "F", f"RED-{tag}"), "plumb_unit")]
                made[1][0].code = f"ELE-{tag}U"
            else:
                from engines.bet_core import hvac as hhv
                from engines.bet_core import mep_sheets as MS
                hv = hhv.hvac(hm, p["stacks"], p["fixtures"])
                made += [(MS.elec_level(hm, e, hv, "F", f"ELE-{tag}"), "elec"), (MS.elec_unifilaire(hm, e, hv, f"ELE-{tag}U"), "elec_uni"),
                         (MS.plumb_level(hm, p, hv, "F", f"PLB-{tag}"), "plumb_unit"), (MS.vmc_level(hm, hv, "F", f"VMC-{tag}"), "hvac_unit")]
                if hv.get("pc") and not pt:
                    made.append((MS.pc_level(hm, hv, "F", f"CHF-{tag}"), "hvac_unit"))
            for sh, kd in made:
                _apartment_texts(sh, _('fr', 'pt') == 'pt')
                if kinds is not None and kd not in kinds:
                    continue
                sh.kind = kd
                sh.level = None
                from engines.bet_core.i18n import tr
                t0 = sh.title
                if _("fr", "pt") == "pt":
                    for a, b in (("^Plancher chauffant", "Piso radiante"), ("^Schéma unifilaire du tableau de répartition", "Esquema unifilar do quadro elétrico"),
                                 ("^Ventilation", "Ventilação mecânica"), ("^Électricité", "Eletricidade"), ("^Plomberie sanitaire", "Águas e esgotos")):
                        t0 = re.sub(a, b, t0)
                sh.title = f"{tr(t0, _('fr', 'pt'))} — {_('logement type', 'fração tipo')} {tag}"
                from .sheets import NAT
                NAT.add(sh.title)
                sh.notes = [x for x in note if x] + list(sh.notes)
                sh._house = True
                out.append(sh)
    finally:
        hs.PLAN_SCALE[0], hs.PLAN_SHIFT[0] = old_scale, old_shift
    return out
