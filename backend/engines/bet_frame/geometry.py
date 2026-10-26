"""Contrôles de géométrie du relevé IA contre les plans d'architecte (lot 19).

Le moteur calcule et dessine sur la trame relevée : si la trame, l'emprise ou les fractions ne sont pas celles des plans,
les plans cotés produits ne valent rien. Ces contrôles sont déterministes et tournent dans la boucle de relecture du lecteur :
une anomalie bloquante renvoie le relevé à l'IA avec le motif, puis, si elle persiste, arrête l'étude par une question.

- GEO-00 : cotes extérieures de l'implantation non relevées (geometry.overall).
- GEO-01 : trame (files extrêmes) incompatible avec les cotes extérieures relevées.
- GEO-02 : cote extérieure introuvable dans le texte vectoriel des plans (valeur inventée ?).
- GEO-03 : portées de trame absentes des cotes des plans (trame « idéalisée »).
- GEO-04 : surface d'une fraction ≠ surface du quadro / tableau des surfaces de l'architecte.
- GEO-05 : fractions qui se chevauchent sur un même niveau.
- GEO-06 : somme des fractions d'un niveau > surface de plancher.
- GEO-07 : typologies différentes avec des rectangles identiques (relevé schématique).
- GEO-08 : cotes extérieures « déduites / ajustées / estimées » (des surfaces, d'une hypothèse) au lieu d'être lues.
- GEO-09 : cotes extérieures ≠ celles d'une lecture indépendante des cotes des planches (relevé fabriqué).
- GEO-10 : emprise d'un niveau (ex. cave plus grande que les étages, étage en retrait) ≠ cotes de sa planta.
"""
from __future__ import annotations

import re

from . import model
from .lang import _

_TOK = re.compile(r"(?<![\d.,])\d{1,6}(?:[.,]\d{1,3})?(?![\d.,])")


def cotes(pages: list[dict]) -> list[float]:
    """Toutes les valeurs lisibles comme des cotes en mètres (m décimaux, cm ou mm entiers) dans le texte vectoriel."""
    out = set()
    for p in pages:
        for t in _TOK.findall((p.get("text") or "") + " " + (p.get("words") or "")):
            if "," in t or "." in t:
                v = float(t.replace(",", "."))
                if 0.3 <= v <= 300:
                    out.add(round(v, 2))
            else:
                v = int(t)
                if 30 <= v <= 30000:
                    out.add(round(v / 100, 2))       # cm
                if 300 <= v <= 300000:
                    out.add(round(v / 1000, 2))      # mm
    return sorted(out)


def _has(cs: list[float], v: float, tol: float = 0.02) -> bool:
    return any(abs(c - v) <= tol for c in cs)


_INVENTED = re.compile(r"dedu|déduit|estim|ajust|recalcul|adot|adopt|suppos|supost|assum|hypoth|hipót|quadro de áreas|tableau des surfaces|coerência|cohérence", re.I)


def storey_bbox(m, lid: str) -> tuple[float, float] | None:
    """Longueur × largeur du rectangle englobant les cases pleines de l'étage."""
    with m.at_storey(lid):
        cells = [(i, j) for j in range(len(m.gy) - 1) for i in range(len(m.gx) - 1) if m.cell_in(i, j)]
    if not cells:
        return None
    i0, i1 = min(c[0] for c in cells), max(c[0] for c in cells) + 1
    j0, j1 = min(c[1] for c in cells), max(c[1] for c in cells) + 1
    return m.gx[i1] - m.gx[i0], m.gy[j1] - m.gy[j0]


_NUM_LV = re.compile(r"(?<![\d.,])(-?\d{1,2})(?![\d.,])")


def _level_no(name: str) -> int | None:
    n = (name or "").lower()
    if re.search(r"cave|sous-sol|subsolo|garagem|estacionamento|parking", n) and not _NUM_LV.search(n):
        return -1
    if re.search(r"\br/?c\b|rés-do-chão|rdc|rez", n) and not _NUM_LV.search(n):
        return 0
    mo = _NUM_LV.search(n)
    return int(mo.group(1)) if mo else None


def check(raw: dict, pages: list[dict] | None = None, ref: dict | None = None) -> list[dict]:
    """ref : lecture indépendante des planches {"overall": {"length", "width"}, "cotes": [m…]} (cf. reader._read_cotes)."""
    out = []

    def a(code, level, fr, pt, fix_fr="", fix_pt=""):
        out.append({"code": code, "level": level, "message": _(fr, pt), "fix": _(fix_fr, fix_pt)})

    try:
        m = model.from_dict(raw)
    except Exception:  # noqa: BLE001 — déjà signalé par model.check
        return out
    vector = [p for p in (pages or []) if len((p.get("text") or "").strip()) > 200]
    cs = cotes(vector) if vector else []
    ref = ref or {}
    cs = sorted(set(cs) | {round(float(v), 2) for v in ref.get("cotes") or [] if isinstance(v, (int, float)) and 0.3 <= v <= 300})
    L, W = m.gx[-1] - m.gx[0], m.gy[-1] - m.gy[0]
    ov = (raw.get("geometry") or {}).get("overall") or {}
    oL, oW = ov.get("length"), ov.get("width")
    if not (oL and oW):
        a("GEO-00", model.BLOCK, "Cotes extérieures de l'implantation non relevées (geometry.overall).",
          "Cotas exteriores da implantação não relevadas (geometry.overall).",
          "Relever sur la planta la cote totale en x et en y (geometry.overall.length / width, source = planche et cote lue).",
          "Relevar na planta a cota total em x e em y (geometry.overall.length / width, source = desenho e cota lida).")
    else:
        oL, oW = float(oL), float(oW)
        src = " ".join(str(x) for x in (ov.get("source"), *((raw.get("_decisions") or [])[:8])) if x)
        if _INVENTED.search(str(ov.get("source") or "")) or re.search(r"(dimens|malha|trama|grille|largura|comprimento).{0,60}(recalcul|deduz|ajust|adot)", src, re.I):
            a("GEO-08", model.BLOCK, "Cotes extérieures / trame déduites ou ajustées au lieu d'être lues sur les planches.",
              "Cotas exteriores / trama deduzidas ou ajustadas em vez de lidas nos desenhos.",
              "Recopier les cotes écrites sur les plans ; ne JAMAIS modifier la géométrie pour coller aux surfaces : signaler l'écart.",
              "Copiar as cotas escritas nas plantas; NUNCA alterar a geometria para acertar as áreas: assinalar a diferença.")
        rov = ref.get("overall") or {}
        for nm, o, r_ in (("x", oL, rov.get("length")), ("y", oW, rov.get("width"))):
            if isinstance(r_, (int, float)) and r_ > 1 and abs(o - r_) > max(0.30, 0.02 * r_):
                a("GEO-09", model.BLOCK, f"Cote extérieure {nm} relevée {o:.2f} m, mais les planches portent {r_:.2f} m.",
                  f"Cota exterior {nm} relevada {o:.2f} m, mas os desenhos indicam {r_:.2f} m.",
                  f"Reprendre la trame sur {r_:.2f} m (lecture des chaînes de cotes extérieures).",
                  f"Refazer a trama sobre {r_:.2f} m (leitura das cadeias de cotas exteriores).")
        off = float(ov.get("facade_to_axis") or 0.0)          # nu de façade → axe des files de rive (demi-poteau, isolant…)
        for nm, g, o in (("x", L, oL), ("y", W, oW)):
            if abs(g + 2 * off - o) > max(0.40, 0.015 * o):
                a("GEO-01", model.BLOCK,
                  f"Trame {nm} = {g:.2f} m entre files de rive, mais cote extérieure relevée = {o:.2f} m.",
                  f"Trama {nm} = {g:.2f} m entre alinhamentos extremos, mas a cota exterior relevada = {o:.2f} m.",
                  "Recaler les files de rive sur les façades et les files intermédiaires sur les cotes du plan.",
                  "Acertar os alinhamentos extremos pelas fachadas e os intermédios pelas cotas da planta.")
        rov0 = (ref or {}).get("overall") or {}
        if cs:
            # une cote totale obtenue en additionnant une chaîne écrite est admise si la lecture indépendante trouve la même
            miss = [f"{v:.2f}" for v, r_ in ((oL, rov0.get("length")), (oW, rov0.get("width")))
                    if not _has(cs, v) and not (isinstance(r_, (int, float)) and abs(r_ - v) <= max(0.10, 0.005 * v))]
            if miss:
                a("GEO-02", model.BLOCK, f"Cote(s) extérieure(s) {', '.join(miss)} m introuvable(s) dans les plans joints.",
                  f"Cota(s) exterior(es) {', '.join(miss)} m não encontrada(s) nos desenhos.",
                  "Recopier la cote écrite sur la planche (chaîne de cotes extérieure), ne pas l'estimer.",
                  "Copiar a cota escrita no desenho (cadeia de cotas exterior), não a estimar.")
    for rl in ref.get("per_level") or []:
        try:
            rL, rW, no = float(rl.get("length")), float(rl.get("width")), _level_no(str(rl.get("level") or ""))
        except (TypeError, ValueError):
            continue
        lv = next((l for l in m.levels if no is not None and _level_no(l.name) == no), None)
        if lv is None or rL < 2 or rW < 2:
            continue
        bb = storey_bbox(m, lv.id)
        if not bb:
            continue
        gL, gW = sorted(bb, reverse=True)
        rL, rW = sorted((rL, rW), reverse=True)
        if abs(gL - rL) > max(0.6, 0.04 * rL) or abs(gW - rW) > max(0.6, 0.04 * rW):
            a("GEO-10", model.BLOCK, f"{lv.name} : emprise relevée {gL:.2f} × {gW:.2f} m, mais sa planta est cotée {rL:.2f} × {rW:.2f} m.",
              f"{lv.name}: implantação relevada {gL:.2f} × {gW:.2f} m, mas a sua planta tem {rL:.2f} × {rW:.2f} m.",
              "La trame couvre le plus grand niveau (souvent la cave) ; les niveaux plus petits reçoivent leurs void_cells.",
              "A trama cobre o maior piso (muitas vezes a cave); os pisos menores recebem as suas void_cells.")
    if cs:
        spans = [round(b - a_, 2) for g in (m.gx, m.gy) for a_, b in zip(g, g[1:])]
        found = sum(1 for s in spans if _has(cs, s, 0.03))
        if spans and found < 0.5 * len(spans):
            a("GEO-03", model.BLOCK,
              f"Trame idéalisée : {found}/{len(spans)} portées seulement figurent dans les cotes des plans ({', '.join(f'{s:.2f}' for s in spans)}).",
              f"Trama idealizada: só {found}/{len(spans)} vãos constam das cotas das plantas ({', '.join(f'{s:.2f}' for s in spans)}).",
              "Placer chaque file sur un mur / une cote réelle du plan et recopier les cotes (pas de valeurs rondes estimées).",
              "Colocar cada alinhamento numa parede / cota real da planta e copiar as cotas (sem valores redondos estimados).")
    by_lv: dict[str, list] = {}
    for u in m.units:
        by_lv.setdefault(u.level, []).append(u)
    decl = {}
    for u in raw.get("units") or []:
        if u.get("area_declared"):
            decl[str(u.get("name") or u["id"])] = float(u["area_declared"])
    for u in raw.get("units") or []:
        d = u.get("area_declared")
        if d:
            ar = (float(u["x1"]) - float(u["x0"])) * (float(u["y1"]) - float(u["y0"]))
            if abs(ar - float(d)) > max(5.0, 0.20 * float(d)):
                a("GEO-04", model.WARN,       # avertissement : l'IA ne doit pas déformer le bâtiment pour coller aux surfaces
                  f"{u.get('name') or u['id']} : rectangle relevé {ar:.1f} m² ≠ {float(d):.1f} m² du tableau des surfaces.",
                  f"{u.get('name') or u['id']}: retângulo relevado {ar:.1f} m² ≠ {float(d):.1f} m² do quadro de áreas.",
                  "Relever les limites réelles de la fraction (murs séparatifs, palier).",
                  "Relevar os limites reais da fração (paredes de separação, patamar).")
    for lid, us in by_lv.items():
        for i, p in enumerate(us):
            for q in us[i + 1:]:
                ix = min(p.x1, q.x1) - max(p.x0, q.x0)
                iy = min(p.y1, q.y1) - max(p.y0, q.y0)
                if ix > 0.3 and iy > 0.3 and ix * iy > 2.0:
                    a("GEO-05", model.BLOCK, f"{p.name} et {q.name} se chevauchent ({ix * iy:.1f} m², {m.level(lid).name}).",
                      f"{p.name} e {q.name} sobrepõem-se ({ix * iy:.1f} m², {m.level(lid).name}).",
                      "Relever les limites des fractions sur la planta.", "Relevar os limites das frações na planta.")
        with m.at_storey(lid):
            fp = m.footprint
        tot = sum(u.area for u in us)
        if tot > 1.02 * fp:
            a("GEO-06", model.BLOCK, f"{m.level(lid).name} : fractions {tot:.0f} m² > plancher {fp:.0f} m².",
              f"{m.level(lid).name}: frações {tot:.0f} m² > piso {fp:.0f} m².",
              "Vérifier l'emprise (void_cells, retraits) et les rectangles des fractions.",
              "Verificar a implantação (void_cells, recuos) e os retângulos das frações.")
        shapes = {}
        for u in us:
            shapes.setdefault((round(u.x1 - u.x0, 1), round(u.y1 - u.y0, 1)), set()).add((u.typology or "").upper())
        odd = [k for k, t in shapes.items() if len(t) > 1]
        if odd:
            a("GEO-07", model.WARN, f"{m.level(lid).name} : typologies différentes sur des rectangles identiques {odd} — relevé schématique.",
              f"{m.level(lid).name}: tipologias diferentes em retângulos idênticos {odd} — levantamento esquemático.")
    return out
