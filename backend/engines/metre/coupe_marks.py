"""Section marks (« coupes ») of a formwork plan, read from the PDF itself: each head = a large numeral (title-size font) next to a thick
L-shaped bracket with a dot. Two heads of the same number facing each other (join line ⟂ text direction) form one section trace.
Coordinates are PDF page points in the UNROTATED page space (same as page.get_text / get_drawings)."""
import math
import re

HEAD_FONT_MIN, HEAD_FONT_MAX = 13.0, 17.0
PERP_TOL = 0.12
MAX_PAIR_PT = 1800.0


def _spans(page):
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                text = "".join(c["c"] for c in s["chars"]).strip()
                if HEAD_FONT_MIN <= s["size"] <= HEAD_FONT_MAX and re.fullmatch(r"\d{1,2}", text):
                    yield text, s["bbox"], line["dir"]


def _dark(fill) -> bool:
    return bool(fill) and max(fill[:3]) < 0.35


def _brackets(page):
    """Filled dark ⌐ (10–40 pt legs) with its filled view-side dot (≤ 3 pt) nearby: the Revit/BEGT section head."""
    fills = [d for d in page.get_drawings() if d["type"] == "f" and _dark(d.get("fill"))]
    dots = [d["rect"] for d in fills if d["rect"].width <= 3.5 and d["rect"].height <= 3.5]
    out = []
    for d in fills:
        r = d["rect"]
        if not (8 <= r.width <= 40 and 8 <= r.height <= 40):
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if not any(math.hypot((k.x0 + k.x1) / 2 - cx, (k.y0 + k.y1) / 2 - cy) <= 25 for k in dots):
            continue
        out.append({"cx": cx, "cy": cy, "rect": [r.x0, r.y0, r.x1, r.y1]})
    return out


def find_heads(page) -> list[dict]:
    brackets = _brackets(page)
    heads = []
    for text, bbox, direction in _spans(page):
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        near = min(brackets, key=lambda b: math.hypot(b["cx"] - cx, b["cy"] - cy), default=None)
        dist = math.hypot(near["cx"] - cx, near["cy"] - cy) if near else None
        if near is None or dist > 45:
            continue
        heads.append({"number": int(text), "x": round(cx, 1), "y": round(cy, 1), "dir": [round(direction[0], 3), round(direction[1], 3)],
                      "bracket_dist_pt": round(dist, 1), "bbox": [round(v, 1) for v in bbox]})
    return heads


def pair_heads(heads: list[dict]) -> dict:
    """Greedy pairing per number: closest two heads whose join line is perpendicular to the text direction."""
    coupes, used = [], set()
    by_num = {}
    for i, h in enumerate(heads):
        by_num.setdefault(h["number"], []).append(i)
    for num, idxs in sorted(by_num.items()):
        cands = []
        for a in idxs:
            for b in idxs:
                if a >= b:
                    continue
                ha, hb = heads[a], heads[b]
                dx, dy = hb["x"] - ha["x"], hb["y"] - ha["y"]
                dist = math.hypot(dx, dy)
                if dist < 20 or dist > MAX_PAIR_PT:
                    continue
                dot = abs(dx * ha["dir"][0] + dy * ha["dir"][1]) / dist
                if dot <= PERP_TOL and abs(ha["dir"][0] * hb["dir"][0] + ha["dir"][1] * hb["dir"][1]) > 0.98:
                    cands.append((dist, a, b))
        for dist, a, b in sorted(cands):
            if a in used or b in used:
                continue
            used.update((a, b))
            n = sum(1 for c in coupes if c["number"] == num) + 1
            coupes.append({"number": num, "name": f"{num}-{num}", "instance": n, "a_pt": [heads[a]["x"], heads[a]["y"]], "b_pt": [heads[b]["x"], heads[b]["y"]],
                           "length_pt": round(dist, 1), "midpoint_pt": [round((heads[a]["x"] + heads[b]["x"]) / 2, 1), round((heads[a]["y"] + heads[b]["y"]) / 2, 1)]})
    unpaired = [h for i, h in enumerate(heads) if i not in used]
    return {"coupes": coupes, "unpaired_heads": unpaired}


def locate_coupe_marks(page, pt_per_m: float | None = None) -> dict:
    heads = find_heads(page)
    res = pair_heads(heads)
    if pt_per_m:
        for c in res["coupes"]:
            c["length_m"] = round(c["length_pt"] / pt_per_m, 2)
    names = sorted({c["name"] for c in res["coupes"]}, key=lambda s: int(s.split("-")[0]))
    res.update(heads_count=len(heads), names=names,
               note="Têtes de coupe = numéral (police de titre) + équerre épaisse ; deux têtes de même numéro face à face (ligne ⟂ au texte) = un tracé. "
                    "Une coupe répétée (ex. 11 ×3) désigne des zones identiques du plan. Rien n'est déduit du texte du cartouche ni des adresses.")
    return res
