"""Cohérence plan ARCHI ↔ plan BET (coffrage / structure) — moteur DÉTERMINISTE.

Pourquoi ce moteur : la comparaison « à l'IA » lisait les cotes en vrac (texte du PDF sans orientation ni position),
comparait des cotes horizontales à des cotes verticales et prenait des cotes de terrasse pour la profondeur du bâtiment.

Règles appliquées ici (jamais contournées) :
  1. Chaque cote garde son ORIENTATION (sens du texte) et sa POSITION ; on ne compare jamais une cote horizontale à une
     cote verticale.
  2. Les cotes sont regroupées en CHAÎNES (cotes jointives sur une même ligne de cote), contrôlées par la géométrie :
     deux cotes voisines ne sont chaînées que si leur écart sur le dessin correspond à leurs valeurs à l'échelle du plan.
  3. Pour chaque orientation, la chaîne de référence du BET (la plus longue, ≥ 2 travées) est rapprochée de la chaîne de
     l'archi qui couvre les MÊMES travées ; les chaînes hors emprise (terrasse, parcelle, pièces) ne servent pas à comparer
     et sont listées comme « non comparées ».
  4. Contrôles internes de chaque plan : cote écrite ≠ longueur dessinée, chaînes opposées (haut/bas, gauche/droite)
     qui ne disent pas la même chose sur la même emprise.
  5. Superposition des deux plans calée sur les axes communs (échelle + translation, sans déformation) → PNG annoté.

Plans vectoriels (PDF) : lecture 100 % déterministe du texte natif. Plans raster (JPG/PNG, PDF scanné) : l'IA vision ne fait
QUE relever les chaînes de cotes (valeurs + position des traits d'attache) ; tout le reste est calculé ici.
"""
from __future__ import annotations

import io
import math
import re

import numpy as np

NUM_RE = re.compile(r"^\d{1,2}[.,]\d{2}$")
LINK_TOL = 0.025         # écart relatif toléré entre l'échelle locale de 2 cotes voisines et l'échelle du plan
OK_MM, WARN_MM = 20, 60  # archi ↔ BET : ≤ 2 cm conforme, ≤ 6 cm à vérifier, au-delà incohérence
LABEL_TOL = 0.03         # cote écrite vs longueur dessinée : 3 % …
LABEL_MIN_M = 0.05       # … et au moins 5 cm
TITLE_RE = re.compile(r"^(PH|PB|PLAN|PLANCHER|RDC|R\+\d|R-\d|VS|TOITURE|TERRASSE|[ÉE]TAGE|SOUS-SOL|NIVEAU|COMBLES|FONDATIONS?|PLANTA|PISO|R/C|R\.C\.|CAVE|COBERTURA|S/CAVE|LAJE|FUNDA[ÇC][ÕO]ES|PAVIMENTO|N[ÍI]VEL)\b", re.I)


# ----------------------------------------------------------------------------------------------- statuts
def status_mm(delta_mm: float) -> str:
    a = abs(delta_mm)
    return "conforme" if a <= OK_MM else "a_verifier" if a <= WARN_MM else "incoherence"


def fmt(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


# ----------------------------------------------------------------------------------------------- lecture vectorielle
def vector_numbers(pdf_bytes: bytes, page_index: int = 0, dpi: int = 150) -> dict:
    """Nombres « cote » d'une page PDF avec orientation + position (pixels de l'image rendue à `dpi`, rotation de page
    appliquée), titres de vues et rendu PNG de la page."""
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        mat = page.rotation_matrix * pymupdf.Matrix(zoom, zoom)
        rot = page.rotation_matrix
        nums, titles, words = [], [], 0
        raw = page.get_text("rawdict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                d = pymupdf.Point(line["dir"]) * rot - pymupdf.Point(0, 0) * rot
                orient = "h" if abs(d.x) >= abs(d.y) else "v"
                line_text = ""
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    cur, box = "", None
                    for ch in chars + [None]:
                        c = ch["c"] if ch else " "
                        if c.strip():
                            cur += c
                            r = pymupdf.Rect(ch["bbox"])
                            box = r if box is None else box | r
                            continue
                        if cur:
                            words += 1
                            line_text += cur + " "
                            if NUM_RE.match(cur):
                                rr = box * mat
                                nums.append({"value_m": float(cur.replace(",", ".")), "text": cur, "o": orient,
                                             "cx": (rr.x0 + rr.x1) / 2, "cy": (rr.y0 + rr.y1) / 2,
                                             "size": min(rr.width, rr.height), "box": [rr.x0, rr.y0, rr.x1, rr.y1]})
                        cur, box = "", None
                t = line_text.strip()
                if t and TITLE_RE.match(t) and len(t) <= 24:
                    r = pymupdf.Rect(line["bbox"]) * mat
                    titles.append({"text": t, "cx": (r.x0 + r.x1) / 2, "cy": (r.y0 + r.y1) / 2, "h": r.height})
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)  # la rotation de page est appliquée par MuPDF
        png = pix.tobytes("png")
        return {"numbers": nums, "titles": titles, "png": png, "width": pix.width, "height": pix.height,
                "native_words": words, "dpi": dpi}
    finally:
        doc.close()


# ----------------------------------------------------------------------------------------------- chaînes (vectoriel)
def _local_scales(line: list[dict], o: str) -> list[float | None]:
    out = []
    for a, b in zip(line, line[1:]):
        dist = (b["cx"] - a["cx"]) if o == "h" else (b["cy"] - a["cy"])
        half = (a["value_m"] + b["value_m"]) / 2
        out.append(dist / half if half > 0 and dist > 0 else None)
    return out


def _lines(nums: list[dict], o: str) -> list[list[dict]]:
    perp, along = ("cy", "cx") if o == "h" else ("cx", "cy")
    items = sorted((n for n in nums if n["o"] == o), key=lambda n: n[perp])
    groups: list[list[dict]] = []
    for n in items:
        if groups and abs(n[perp] - groups[-1][-1][perp]) <= max(2.0, 0.45 * n["size"]):
            groups[-1].append(n)
        else:
            groups.append([n])
    return [sorted(g, key=lambda n: n[along]) for g in groups]


def plan_scale(nums: list[dict]) -> float | None:
    """Échelle du plan (px par mètre) = mode des échelles locales entre cotes voisines d'une même ligne."""
    vals = []
    for o in ("h", "v"):
        for line in _lines(nums, o):
            # cotes de travée seulement (0,5 à 9 m) : les épaisseurs sont imprécises, les totaux isolés trompeurs
            vals += [s for s, a, b in zip(_local_scales(line, o), line, line[1:])
                     if s and 0.5 <= a["value_m"] <= 9 and 0.5 <= b["value_m"] <= 9]
    if len(vals) < 3:
        return None
    logs = np.log(np.array(vals))
    win = 0.02
    best, best_n = None, 0
    for c in logs:
        n = int(np.sum(np.abs(logs - c) <= win))
        if n > best_n:
            best, best_n = c, n
    sel = logs[np.abs(logs - best) <= win]
    return float(math.exp(float(np.median(sel))))


def chains_from_numbers(nums: list[dict], scale: float) -> list[dict]:
    """Chaînes = cotes voisines d'une ligne dont l'écart dessiné est cohérent avec l'échelle du plan.
    Bornes (traits d'attache) déduites des centres de texte, sans réutiliser les valeurs écrites → la longueur dessinée
    de chaque cote reste une mesure indépendante de son texte."""
    chains = []
    for o in ("h", "v"):
        along, perp = ("cx", "cy") if o == "h" else ("cy", "cx")
        for line in _lines(nums, o):
            sc = _local_scales(line, o)
            run = [line[0]]
            runs = []
            for k, s in enumerate(sc):
                if s and abs(s / scale - 1) <= LINK_TOL:
                    run.append(line[k + 1])
                else:
                    runs.append(run)
                    run = [line[k + 1]]
            runs.append(run)
            for r in runs:
                if len(r) < 2:
                    continue
                c = [n[along] for n in r]
                bounds = [c[0] - scale * r[0]["value_m"] / 2]
                for i in range(len(r) - 1):
                    w = r[i]["value_m"] / (r[i]["value_m"] + r[i + 1]["value_m"])
                    bounds.append(c[i] + (c[i + 1] - c[i]) * w)
                bounds.append(c[-1] + scale * r[-1]["value_m"] / 2)
                chains.append(_chain(o, [n["value_m"] for n in r], bounds, sum(n[perp] for n in r) / len(r), scale,
                                     measured_from_ticks=False, items=r))
    return chains


def _chain(o, values, bounds, pos, scale, measured_from_ticks, items=None, tag=None):
    seg = []
    for i, v in enumerate(values):
        drawn = (bounds[i + 1] - bounds[i]) / scale
        seg.append({"value_m": round(v, 3), "drawn_m": round(drawn, 3), "a": bounds[i], "b": bounds[i + 1]})
    return {"orientation": "horizontal" if o == "h" else "vertical", "o": o, "pos": pos, "bounds": bounds,
            "values": [round(v, 3) for v in values], "sum_m": round(sum(values), 3), "segments": seg,
            "span_px": [bounds[0], bounds[-1]], "measured_from_ticks": measured_from_ticks, "tag": tag,
            "bbox": _chain_bbox(o, bounds, pos, items)}


def _chain_bbox(o, bounds, pos, items):
    if items:
        xs = [n["box"][0] for n in items] + [n["box"][2] for n in items]
        ys = [n["box"][1] for n in items] + [n["box"][3] for n in items]
        return [min(xs + ([bounds[0], bounds[-1]] if o == "h" else [])), min(ys + ([bounds[0], bounds[-1]] if o == "v" else [])),
                max(xs + ([bounds[0], bounds[-1]] if o == "h" else [])), max(ys + ([bounds[0], bounds[-1]] if o == "v" else []))]
    return [bounds[0], pos, bounds[-1], pos] if o == "h" else [pos, bounds[0], pos, bounds[-1]]


# ----------------------------------------------------------------------------------------------- vues d'une planche
def split_views(chains: list[dict], titles: list[dict], scale: float, gap_m: float = 2.0) -> list[dict]:
    """Une planche BET porte souvent plusieurs vues (PH VS, PH RDC, PH R+1, toiture). Regroupe les chaînes par proximité
    (≤ gap_m) et nomme chaque groupe avec le titre le plus proche au-dessus de lui."""
    n = len(chains)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    g = gap_m * scale
    for i in range(n):
        a = chains[i]["bbox"]
        for j in range(i + 1, n):
            b = chains[j]["bbox"]
            dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
            dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
            if max(dx, dy) <= g:
                parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(chains[i])
    views = []
    for members in groups.values():
        x0 = min(c["bbox"][0] for c in members); y0 = min(c["bbox"][1] for c in members)
        x1 = max(c["bbox"][2] for c in members); y1 = max(c["bbox"][3] for c in members)
        best, bd = None, None
        for t in titles:
            if x0 - 2 * scale <= t["cx"] <= x1 + 2 * scale and y0 - 4 * scale <= t["cy"] <= y1:
                d = abs(t["cy"] - y0)
                if bd is None or d < bd:
                    best, bd = t["text"], d
        longest = max((c["sum_m"] for c in members if len(c["values"]) >= 2), default=0)
        views.append({"title": best, "bbox": [x0, y0, x1, y1], "chains": members, "longest_m": longest})
    views = [v for v in views if v["longest_m"] >= 4.0 and any(len(c["values"]) >= 2 for c in v["chains"])]
    views.sort(key=lambda v: (v["bbox"][1], v["bbox"][0]))
    return views


def pick_view(views: list[dict], level: str | None) -> dict | None:
    if not views:
        return None
    if level:
        lv = level.strip().upper().replace(" ", "")
        for v in views:
            t = (v["title"] or "").upper().replace(" ", "")
            if t and (t == lv or t.endswith(lv) or lv in t.split("PH")[-1:]):
                return v
        for v in views:
            if lv in (v["title"] or "").upper().replace(" ", ""):
                return v
    return max(views, key=lambda v: (v["bbox"][2] - v["bbox"][0]) * (v["bbox"][3] - v["bbox"][1]))


# ----------------------------------------------------------------------------------------------- lecture raster (IA)
VISION_PROMPT = """Planta de arquitetura ou de estruturas fornecida em imagem ({w} × {h} píxeis; origem no canto superior esquerdo).
Lê APENAS as CADEIAS DE COTAS (linhas de cota com várias cotas contíguas) tal como impressas.
Para cada cadeia:
- "orientation": "horizontal" se a linha de cota é horizontal (texto legível da esquerda para a direita), "vertical" caso contrário;
- "values": os valores em metros, por ordem (da esquerda para a direita, ou de cima para baixo), EXATAMENTE como escritos;
- "ticks_px": a posição [x, y] em píxeis de CADA traço de chamada, pela mesma ordem (len(values) + 1 pontos);
- "objet": "batiment" se a cadeia cota o edifício (fachadas, eixos, paredes), "terrasse" (terraço), "parcelle" (lote), "piece" (divisão) ou "autre".
Não calcules nada, não somes nada, não completes um valor ilegível (põe null). Nunca mistures duas linhas de cota.
Responde em JSON estrito: {{"chains": [{{"orientation": "...", "values": [..], "ticks_px": [[x, y], ..], "objet": "..."}}]}}"""


def _ink_mask(img_rgb: np.ndarray) -> np.ndarray:
    """Pixels dessinés (noir OU couleur), fond blanc exclu."""
    mn = img_rgb.min(axis=2).astype(int)
    mx = img_rgb.max(axis=2).astype(int)
    return (mn < 225) | ((mx - mn) > 14)   # inclut les traits de cote rouges / pâles


def snap_ticks(img_rgb: np.ndarray, o: str, ticks: list[list[float]], frac: float = 0.004) -> list[float]:
    """Recale chaque trait d'attache sur le trait réellement dessiné le plus proche (profil d'encre dans une bande autour
    de la ligne de cote). Renvoie les positions le long de la ligne."""
    H, W = img_rgb.shape[:2]
    ink = _ink_mask(img_rgb)
    out = []
    pos = float(np.median([t[1] if o == "h" else t[0] for t in ticks]))
    half = 3
    if o == "h":
        band = ink[max(0, int(pos) - half):min(H, int(pos) + half + 1), :]
    else:
        band = ink[:, max(0, int(pos) - half):min(W, int(pos) + half + 1)].T
    prof = band.mean(axis=0) if band.size else np.zeros(W if o == "h" else H)
    win = max(4, int(frac * (W if o == "h" else H)))   # simple affinage : jamais de saut vers un autre trait
    for t in ticks:
        p = t[0] if o == "h" else t[1]
        lo, hi = int(max(0, p - win)), int(min(len(prof) - 1, p + win))
        seg = prof[lo:hi + 1]
        cand = np.nonzero(seg >= 0.55)[0]
        out.append(float(cand[np.argmin(np.abs(cand + lo - p))] + lo) if cand.size else float(p))
    return out


def chains_from_vision(data: dict, img_rgb: np.ndarray) -> tuple[list[dict], float | None, list[str]]:
    """Chaînes relevées par l'IA → chaînes contrôlées : orientation vérifiée sur la géométrie des traits, traits recalés,
    échelle déduite (médiane), chaînes incohérentes avec l'échelle écartées (et signalées)."""
    notes, raw = [], []
    for ch in (data or {}).get("chains") or []:
        vals, ticks = ch.get("values") or [], ch.get("ticks_px") or []
        if len(vals) < 1 or len(ticks) != len(vals) + 1 or any(v is None for v in vals):
            continue
        try:
            vals = [float(str(v).replace(",", ".")) for v in vals]
            ticks = [[float(t[0]), float(t[1])] for t in ticks]
        except (TypeError, ValueError, IndexError):
            continue
        dx, dy = abs(ticks[-1][0] - ticks[0][0]), abs(ticks[-1][1] - ticks[0][1])
        o = "h" if dx >= dy else "v"
        declared = "h" if str(ch.get("orientation", "")).startswith("h") else "v"
        if o != declared:
            notes.append(f"Cadeia {'/'.join(fmt(v) for v in vals)}: orientação corrigida segundo o desenho ({'horizontal' if o == 'h' else 'vertical'}).")
        along = snap_ticks(img_rgb, o, ticks)
        if any(b <= a for a, b in zip(along, along[1:])):
            along = sorted(along)
        pos = float(np.median([t[1] if o == "h" else t[0] for t in ticks]))
        raw.append((o, vals, along, pos, ch.get("objet")))
    ratios = [(b[-1] - b[0]) / sum(v) for _o, v, b, _p, _t in raw if len(v) >= 2 and sum(v) > 0]
    if not ratios:
        return [], None, notes + ["Nenhuma cadeia de cotas utilizável lida na imagem."]
    scale = float(np.median(ratios))
    chains = []
    for o, vals, along, pos, tag in raw:
        r = (along[-1] - along[0]) / sum(vals)
        if abs(r / scale - 1) > 0.12:
            notes.append(f"Cadeia {'/'.join(fmt(v) for v in vals)} descartada: comprimento desenhado incoerente com a escala da planta.")
            continue
        chains.append(_chain(o, vals, along, pos, scale, measured_from_ticks=True, tag=tag))
    return chains, scale, notes


# ----------------------------------------------------------------------------------------------- comparaisons
def _best_window(a_vals: list[float], b_vals: list[float]) -> tuple[float, int, bool] | None:
    """Fenêtre contiguë de `a` (même nombre de travées que `b`) la plus proche de `b`, sens direct ou inversé."""
    n = len(b_vals)
    if len(a_vals) < n:
        return None
    best = None
    for rev in (False, True):
        bb = b_vals[::-1] if rev else b_vals
        for i in range(len(a_vals) - n + 1):
            cost = sum(abs(x - y) for x, y in zip(a_vals[i:i + n], bb))
            if best is None or cost < best[0]:
                best = (cost, i, rev)
    return best


def reference_chain(chains: list[dict], o: str) -> dict | None:
    """Chaîne de référence d'un plan dans une orientation : la plus longue chaîne d'au moins 2 travées dont aucune n'est
    une épaisseur de mur (≥ 0,50 m) — les chaînes d'axes / de façades."""
    cand = [c for c in chains if c["o"] == o and len(c["values"]) >= 2 and min(c["values"]) >= 0.5]
    return max(cand, key=lambda c: (c["sum_m"], -abs(c["pos"]))) if cand else None


def match_reference(chains_a: list[dict], ref_b: dict) -> tuple[dict, int, bool, float] | None:
    best = None
    for c in chains_a:
        if c["o"] != ref_b["o"]:
            continue  # règle 1 : jamais horizontal ↔ vertical
        w = _best_window(c["values"], ref_b["values"])
        if w is None:
            continue
        cost, i, rev = w
        rel = cost / max(ref_b["sum_m"], 1e-6)
        if best is None or rel < best[3]:
            best = (c, i, rev, rel)
    return best if best and best[3] <= 0.25 else None


def internal_checks(chains: list[dict], label: str, scale: float) -> list[dict]:
    out = []
    # cote écrite ≠ longueur dessinée : seulement quand les traits d'attache ont été relevés (plans image) ; en vectoriel
    # la position du texte ne mesure pas la cote
    for c in chains:
        if len(c["values"]) < 2 or not c["measured_from_ticks"]:
            continue
        for s in c["segments"]:
            d = s["drawn_m"] - s["value_m"]
            if s["value_m"] >= 0.8 and abs(d) > max(0.15, 0.05 * s["value_m"]):
                out.append({"type": "cote_vs_dessin", "plan": label, "orientation": c["orientation"],
                            "valeur_ecrite_m": s["value_m"], "longueur_dessinee_m": round(s["drawn_m"], 2),
                            "ecart_mm": round(d * 1000), "statut": "a_verifier",
                            "at": (s["a"] + s["b"]) / 2, "pos": c["pos"], "o": c["o"],
                            "detail": f"{label}: cota {fmt(s['value_m'])} m, o desenho mede ≈ {fmt(s['drawn_m'])} m "
                                      f"({'horizontal' if c['o'] == 'h' else 'vertical'}) — cota ou desenho a verificar."})
    # chaînes parallèles sur la même emprise (ex. cotes de tête vs cotes de pied) : mêmes traits d'attache aux deux bouts
    for o in ("h", "v"):
        cs = [c for c in chains if c["o"] == o and len(c["values"]) >= 2 and min(c["values"]) >= 0.5]
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a, b = cs[i], cs[j]
                if a.get("tag") and b.get("tag") and a["tag"] != b["tag"]:
                    continue  # ex. chaîne de terrasse face à une chaîne du bâtiment
                tol = (0.15 if a["measured_from_ticks"] or b["measured_from_ticks"] else 0.05) * scale
                for sa in a["segments"]:
                    for sb in b["segments"]:
                        if abs(sa["a"] - sb["a"]) <= tol and abs(sa["b"] - sb["b"]) <= tol:
                            d = sb["value_m"] - sa["value_m"]
                            if abs(d) * 1000 > OK_MM:
                                out.append({"type": "chaines_opposees", "plan": label, "orientation": a["orientation"],
                                            "valeur_a_m": sa["value_m"], "valeur_b_m": sb["value_m"], "ecart_mm": round(d * 1000),
                                            "statut": status_mm(d * 1000), "at": (sb["a"] + sb["b"]) / 2, "pos": b["pos"], "o": o,
                                            "detail": f"{label}: o mesmo vão está cotado {fmt(sa['value_m'])} m numa cadeia "
                                                      f"e {fmt(sb['value_m'])} m na cadeia paralela."})
                same_start = abs(a["span_px"][0] - b["span_px"][0]) <= tol
                if same_start and OK_MM < abs(a["sum_m"] - b["sum_m"]) * 1000 <= 500:
                    d = b["sum_m"] - a["sum_m"]
                    out.append({"type": "totaux_opposes", "plan": label, "orientation": a["orientation"],
                                "valeur_a_m": a["sum_m"], "valeur_b_m": b["sum_m"], "ecart_mm": round(d * 1000),
                                "statut": status_mm(d * 1000), "at": b["span_px"][1], "pos": b["pos"], "o": o,
                                "detail": f"{label}: duas cadeias paralelas que partem do mesmo eixo dão "
                                          f"{fmt(a['sum_m'])} m e {fmt(b['sum_m'])} m ({d * 1000:+.0f} mm) — fachada não paralela ou cota errada."})
    return out


def compare(archi: dict, bet: dict) -> dict:
    """archi / bet = {chains, scale, label}. → rapprochements par orientation + constats + données de calage."""
    findings, matches, unused = [], {}, []
    for o, name in (("h", "largura, cotas horizontais"), ("v", "profundidade, cotas verticais")):
        ref = reference_chain(bet["chains"], o)
        if not ref:
            findings.append({"type": "lecture", "statut": "a_verifier", "detail": f"Estruturas: nenhuma cadeia de referência legível para a {name}."})
            continue
        m = match_reference(archi["chains"], ref)
        if not m:
            findings.append({"type": "lecture", "statut": "a_verifier",
                             "detail": f"Arquitetura: nenhuma cadeia cobre os mesmos vãos que a planta de estruturas ({' / '.join(fmt(v) for v in ref['values'])} m) para a {name}."})
            continue
        ca, i, rev, _rel = m
        n = len(ref["values"])
        segs_a = ca["segments"][i:i + n]
        segs_b = ref["segments"][::-1] if rev else ref["segments"]
        rows = []
        for k, (sa, sb) in enumerate(zip(segs_a, segs_b)):
            d = sb["value_m"] - sa["value_m"]
            st = status_mm(d * 1000)
            rows.append({"travee": k + 1, "archi_m": sa["value_m"], "bet_m": sb["value_m"], "ecart_mm": round(d * 1000), "statut": st})
            if st != "conforme":
                findings.append({"type": "archi_vs_bet", "orientation": ref["orientation"], "statut": st,
                                 "archi_m": sa["value_m"], "bet_m": sb["value_m"], "ecart_mm": round(d * 1000),
                                 "at": (sa["a"] + sa["b"]) / 2, "pos": ca["pos"], "o": o,
                                 "detail": f"Vão {k + 1} ({name}): arquitetura {fmt(sa['value_m'])} m / estruturas {fmt(sb['value_m'])} m "
                                           f"({d * 1000:+.0f} mm)."})
        tot_a, tot_b = sum(s["value_m"] for s in segs_a), sum(s["value_m"] for s in segs_b)
        matches[o] = {"archi_chain": ca["values"], "archi_window": [i, i + n], "bet_chain": ref["values"], "reversed": rev,
                      "rows": rows, "total_archi_m": round(tot_a, 3), "total_bet_m": round(tot_b, 3),
                      "ecart_total_mm": round((tot_b - tot_a) * 1000), "statut_total": status_mm((tot_b - tot_a) * 1000),
                      "bounds_archi": [segs_a[0]["a"]] + [s["b"] for s in segs_a],
                      "bounds_bet": ([s["b"] for s in ref["segments"]][::-1] + [ref["segments"][0]["a"]]) if rev else [ref["segments"][0]["a"]] + [s["b"] for s in ref["segments"]]}
    used = {id(c) for c in archi["chains"] for mm in matches.values() if c["values"] == mm["archi_chain"]}
    for c in archi["chains"]:
        if id(c) not in used and len(c["values"]) >= 2 and min(c["values"]) >= 0.5:
            unused.append({"orientation": c["orientation"], "values": c["values"], "objet": c.get("tag"),
                           "raison": "não cobre os mesmos vãos que a cadeia de referência de estruturas (terraço, envolvente, divisões…): não comparada, controlada internamente"})
    findings += internal_checks(archi["chains"], "Arquitetura", archi["scale"])
    findings += internal_checks(bet["chains"], "Estruturas", bet["scale"])
    order = {"incoherence": 0, "a_verifier": 1, "conforme": 2}
    findings.sort(key=lambda f: (order.get(f.get("statut"), 3), f.get("type") != "archi_vs_bet"))
    return {"matches": matches, "findings": findings, "unused_archi_chains": unused,
            "rules": ["Cotas comparadas orientação a orientação (nunca horizontal ↔ vertical).",
                      "Só são comparadas as cadeias que cobrem os mesmos vãos que a cadeia de referência de estruturas.",
                      f"Limites arquitetura ↔ estruturas: ≤ {OK_MM} mm conforme, ≤ {WARN_MM} mm a verificar, acima disso incoerência."]}


# ----------------------------------------------------------------------------------------------- superposition
def calibration(matches: dict) -> dict | None:
    """Calage BET → archi : x' = s·x + tx, y' = s·y + ty (moindres carrés sur les bornes des travées rapprochées)."""
    if "h" not in matches or "v" not in matches or matches["h"]["reversed"] or matches["v"]["reversed"]:
        return None
    A, b = [], []
    for p, q in zip(matches["h"]["bounds_bet"], matches["h"]["bounds_archi"]):
        A.append([p, 1, 0]); b.append(q)
    for p, q in zip(matches["v"]["bounds_bet"], matches["v"]["bounds_archi"]):
        A.append([p, 0, 1]); b.append(q)
    sol, *_ = np.linalg.lstsq(np.array(A, float), np.array(b, float), rcond=None)
    s, tx, ty = (float(x) for x in sol)
    if s <= 0:
        return None
    res = np.array(A, float) @ sol - np.array(b, float)
    return {"s": s, "tx": tx, "ty": ty, "residual_px": float(np.sqrt(np.mean(res ** 2)))}


def render_overlay(archi_png: bytes, bet_png: bytes, cal: dict, markers: list[dict], title: str, legend: list[str],
                   ok_note: str | None = None, bet_clip: list[float] | None = None) -> bytes:
    from PIL import Image, ImageDraw
    K = 2.0 if Image.open(io.BytesIO(archi_png)).width < 1800 else 1.0
    arch = Image.open(io.BytesIO(archi_png)).convert("RGB")
    arch = arch.resize((int(arch.width * K), int(arch.height * K)), Image.LANCZOS)
    bet = Image.open(io.BytesIO(bet_png)).convert("L")
    if bet_clip:  # planche multi-vues : seule la vue comparée est superposée
        x0c, y0c, x1c, y1c = (int(max(0, v)) for v in bet_clip)
        keep = Image.new("L", bet.size, 255)
        keep.paste(bet.crop((x0c, y0c, min(x1c, bet.width), min(y1c, bet.height))), (x0c, y0c))
        bet = keep
    s2 = cal["s"] * K
    bs = np.array(bet.resize((max(1, int(bet.width * s2)), max(1, int(bet.height * s2))), Image.LANCZOS)).astype(float)
    ag = np.array(arch.convert("L")).astype(float)
    base = 255 - (255 - ag) * 0.9
    out = np.stack([base] * 3, -1)
    ox, oy = int(round(cal["tx"] * K)), int(round(cal["ty"] * K))
    H, W = ag.shape
    ink = (255 - bs) / 255.0
    h, w = ink.shape
    x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + w, W), min(oy + h, H)
    if x1 > x0 and y1 > y0:
        sub = ink[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        a = np.clip(sub * 0.85, 0, 1)[..., None]
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + np.array([230, 0, 40], float) * a
    img = Image.fromarray(out.astype(np.uint8))
    d = ImageDraw.Draw(img)
    font = _font(max(18, int(15 * K)), bold=True)
    blue = (0, 90, 200)
    placed: list[tuple[float, float]] = []
    for m in markers:
        x, y, r = m["x"] * K, m["y"] * K, int(13 * K)
        while any(abs(x - px) < 2.2 * r and abs(y - py) < 2.2 * r for px, py in placed):
            x += 2.3 * r  # deux constats au même endroit : pastilles côte à côte
        placed.append((x, y))
        d.ellipse((x - r, y - r, x + r, y + r), fill=blue, outline="white", width=max(2, int(2 * K)))
        d.text((x, y), str(m["n"]), font=font, fill="white", anchor="mm")
    fs, ft = _font(int(13.5 * K)), _font(int(20 * K), bold=True)
    line_h = int(31 * K)
    head = int(75 * K)
    foot = int(25 * K) + line_h * (len(legend) + (2 if ok_note else 0)) + int(40 * K)
    page = Image.new("RGB", (img.width, img.height + head + foot), "white")
    page.paste(img, (0, head))
    d = ImageDraw.Draw(page)
    d.text((int(15 * K), int(12 * K)), title, font=ft, fill="black")
    d.rectangle((int(15 * K), int(46 * K), int(35 * K), int(59 * K)), fill=(140, 140, 140))
    d.text((int(40 * K), int(45 * K)), "Planta de arquitetura", font=fs, fill="black")
    d.rectangle((int(160 * K), int(46 * K), int(180 * K), int(59 * K)), fill=(230, 0, 40))
    d.text((int(185 * K), int(45 * K)), "Planta de estruturas (alinhada pelos eixos comuns)", font=fs, fill="black")
    y = img.height + head + int(15 * K)
    for i, t in enumerate(legend, 1):
        d.ellipse((int(15 * K), y, int(37 * K), y + int(22 * K)), fill=blue)
        d.text((int(26 * K), y + int(11 * K)), str(i), font=_font(int(13 * K), bold=True), fill="white", anchor="mm")
        for k, chunk in enumerate(_wrap(t, int((page.width - 60 * K) / (7.2 * K)))[:1]):
            d.text((int(46 * K), y + int(3 * K)), chunk, font=fs, fill="black")
        y += line_h
    if ok_note:
        d.text((int(15 * K), y + int(8 * K)), ok_note, font=fs, fill=(0, 120, 60))
    d.text((int(15 * K), page.height - int(22 * K)), "ConstruPilot — sobreposição calculada (não é uma imagem gerada por IA). Controlo a confirmar pelo projetista de estruturas / arquiteto.",
           font=_font(int(11 * K)), fill=(90, 90, 90))
    buf = io.BytesIO()
    page.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _wrap(t: str, n: int) -> list[str]:
    return [t if len(t) <= n else t[:n - 1] + "…"]


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for p in (f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


# ----------------------------------------------------------------------------------------------- orchestration
def prepare_vector(pdf_bytes: bytes, page_index: int, level: str | None, label: str) -> dict:
    v = vector_numbers(pdf_bytes, page_index)
    if len(v["numbers"]) < 4:
        return {"ok": False, "raster_fallback": True, "png": v["png"],
                "note": f"{label}: sem cotas em texto nativo — leitura visual necessária."}
    scale = plan_scale(v["numbers"])
    if not scale:
        return {"ok": False, "raster_fallback": True, "png": v["png"], "note": f"{label}: escala da planta não encontrada."}
    chains = chains_from_numbers(v["numbers"], scale)
    views = split_views(chains, v["titles"], scale)
    view = pick_view(views, level)
    if not view:
        return {"ok": False, "raster_fallback": True, "png": v["png"], "note": f"{label}: nenhuma vista cotada detetada."}
    m = 1.5 * scale
    x0, y0, x1, y1 = view["bbox"]
    return {"ok": True, "label": label, "png": v["png"], "chains": view["chains"], "scale": scale, "source": "vetorial",
            "view": view["title"], "views": [x["title"] for x in views], "clip": [x0 - m, y0 - m, x1 + m, y1 + m]}


def prepare_raster(png: bytes, vision_data: dict | None, label: str) -> dict:
    from PIL import Image
    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    chains, scale, notes = chains_from_vision(vision_data or {}, img)
    if not chains or not scale:
        return {"ok": False, "label": label, "png": png, "notes": notes, "note": f"{label}: cotas ilegíveis."}
    return {"ok": True, "label": label, "png": png, "chains": chains, "scale": scale, "source": "imagem (leitura IA controlada)",
            "notes": notes, "view": None, "views": []}


def finalize(archi: dict, bet: dict, title: str) -> dict:
    res = compare(archi, bet)
    cal = calibration(res["matches"])
    markers, legend = [], []
    for f in res["findings"]:
        if f.get("statut") == "conforme" or len(legend) >= 9:
            continue
        legend.append(f["detail"])
        if "at" in f and f.get("plan") != "Estruturas":
            xy = (f["at"], f["pos"]) if f["o"] == "h" else (f["pos"], f["at"])
            markers.append({"n": len(legend), "x": xy[0], "y": xy[1]})
        elif "at" in f and cal:  # constat BET : position ramenée sur le plan archi
            px, py = (f["at"], f["pos"]) if f["o"] == "h" else (f["pos"], f["at"])
            markers.append({"n": len(legend), "x": px * cal["s"] + cal["tx"], "y": py * cal["s"] + cal["ty"]})
    overlay = None
    if cal and cal["residual_px"] <= 0.25 * archi["scale"]:
        ok = [f"{'Largura' if o == 'h' else 'Profundidade'}: arquitetura {fmt(m['total_archi_m'])} m / estruturas {fmt(m['total_bet_m'])} m"
              for o, m in res["matches"].items()]
        overlay = render_overlay(archi["png"], bet["png"], cal, markers, title, legend or ["Nenhuma incoerência de cotas detetada nas cadeias comparadas."],
                                 ok_note=" · ".join(ok), bet_clip=bet.get("clip"))
    for f in res["findings"]:
        for k in ("at", "pos", "o"):
            f.pop(k, None)
    for m in res["matches"].values():
        m.pop("bounds_archi", None); m.pop("bounds_bet", None)
    return {"ok": True, **res, "calibration": ({k: round(v, 4) for k, v in cal.items()} if cal else None),
            "overlay_png": overlay,
            "sources": {"archi": {"lecture": archi["source"], "vue": archi.get("view"), "notes": archi.get("notes", [])},
                        "bet": {"lecture": bet["source"], "vue": bet.get("view"), "vues_detectees": bet.get("views", []), "notes": bet.get("notes", [])}},
            "overlay_note": None if overlay else "Sobreposição não produzida: alinhamento pelos eixos impossível ou pouco fiável (orientação diferente, cadeia em falta)."}
