"""Modelo-tipo quando os documentos NÃO têm desenhos utilizáveis (só memórias, fichas, projetos de especialidades em texto).

Pedido do Martinho (12/11/2026): «faz o melhor que possas» — em vez de parar, o estudo corre sobre uma moradia-tipo dimensionada
com o que os textos dizem (área, tipologia, número de pisos, cobertura, concelho), com TODA a geometria marcada como hipótese
e o dossier identificado como ESTUDO INDICATIVO. Mesmos documentos → mesmo modelo (determinístico).
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

CASES = Path(__file__).resolve().parent / "cases"


def _text(docs, max_pages: int = 40) -> str:
    out = []
    for _name, data in docs or []:
        try:
            import pymupdf
            d = pymupdf.open(stream=data, filetype="pdf")
            out += [p.get_text() for i, p in enumerate(d) if i < max_pages]
        except Exception:  # noqa: BLE001 — imagem / formato não PDF
            continue
    return "\n".join(out)


def _num(s: str) -> float:
    return float(s.replace(" ", "").replace(".", "").replace(",", ".")) if "," in s else float(s.replace(" ", ""))


def facts(text: str, hypotheses: str = "") -> dict:
    t = (hypotheses or "") + "\n" + (text or "")
    low = t.lower()
    area = None
    for m in re.finditer(r"(?:área|area|surface|abc|a\.?\s?u\.?|construção|construction|habitable|útil|bruta)[^\d\n]{0,40}"
                         r"(\d{2,3}(?:[ .]\d{3})?(?:,\d{1,2})?|\d{2,3}\.\d{1,2})\s*m(?:²|2)", t, re.I):
        try:
            v = _num(m.group(1))
        except ValueError:
            continue
        if 30 <= v <= 900:
            area = v
            break
    if area is None:
        vals = []
        for m in re.finditer(r"(\d{2,3}(?:,\d{1,2})?)\s*m(?:²|2)\b", t):
            try:
                v = _num(m.group(1))
            except ValueError:
                continue
            if 50 <= v <= 600:
                vals.append(v)
        area = max(vals) if vals else None
    tip = re.search(r"\bT\s?([0-9])\b", t)
    floors = 1
    if re.search(r"\b(r/c\s*\+\s*1|rés[- ]do[- ]chão e (1|primeiro)|dois pisos|2 pisos|r\+1|deux niveaux)\b", low):
        floors = 2
    elif re.search(r"\b(1 piso|um piso|piso único|térre[ao]|plain[- ]pied|r\+0|rés[- ]do[- ]chão)\b", low):
        floors = 1
    flat = bool(re.search(r"cobertura (plana|em terraço)|laje de cobertura|terraço não acessível|toiture[- ]terrasse|toit plat", low))
    conc = re.search(r"concelho de ([A-ZÁ-Ú][\wÀ-ú]+(?: [A-ZÁ-Ú][\wÀ-ú]+)*)", t) or re.search(r"\b(Loures|Lisboa|Porto|Sintra|Cascais|Oeiras|"
                                                                                     r"Almada|Seixal|Braga|Coimbra|Setúbal|Amadora|Odivelas)\b", t)
    return {"area": area, "typology": int(tip.group(1)) if tip else None, "floors": floors, "flat": flat,
            "concelho": (conc.group(1).strip() if conc else None)}


def model(docs, hypotheses: str, country: str) -> tuple[dict, list[str]]:
    """→ (relevé bet_core, decisões). Moradia-tipo escalada sobre o caso de referência."""
    f = facts(_text(docs), hypotheses)
    tpl = json.loads((CASES / "moradia_pt_demo.json").read_text())
    raw = copy.deepcopy(tpl)
    floors = f["floors"]
    area = f["area"] or (40.0 + 25.0 * (f["typology"] or 3)) * (1.0 if floors == 1 else 1.0)
    L0, W0 = tpl["envelope"]["length_x"], tpl["envelope"]["width_y"]
    foot = area / floors * 1.12                                    # área útil → implantação (paredes)
    ratio = L0 / W0
    W = round(min(math.sqrt(foot / ratio), 7.6), 2)              # portée ≤ 7,6 m (poutrelles-hourdis sans refend)
    L = round(foot / W, 2)
    sx, sy = L / L0, W / W0
    raw["envelope"].update({"length_x": L, "width_y": W, "_source": "HIPÓTESE — modelo-tipo sem desenhos (área dos textos)"})
    for s in raw["sides"].values():
        s["pos"] = round(s["pos"] * (sx if s["axis"] == "x" else sy), 2)
    sides = raw["sides"]
    for o in raw["openings"]:
        k = sy if sides[o["side"]]["axis"] == "x" else sx
        o["from"], o["to"] = round(o["from"] * k, 2), round(o["from"] * k + (o["to"] - o["from"]), 2)
    for lv_rooms in raw["rooms"].values():
        for r in lv_rooms:
            for a, k in (("x0", sx), ("x1", sx), ("y0", sy), ("y1", sy)):
                r[a] = round(r[a] * k, 2)
            r["area_pc"] = round((r["x1"] - r["x0"]) * (r["y1"] - r["y0"]), 2)
    for lv_walls in raw["interior_walls"].values():
        for w in lv_walls:
            for a, k in (("x0", sx), ("x1", sx), ("y0", sy), ("y1", sy)):
                w[a] = round(w[a] * k, 2)
            if abs(w["x1"] - w["x0"]) < abs(w["y1"] - w["y0"]):
                w["x1"] = round(w["x0"] + 0.10, 2)
            else:
                w["y1"] = round(w["y0"] + 0.10, 2)
    st = raw["stair"]
    for a, k in (("x0", sx), ("x1", sx), ("y0", sy), ("y1", sy)):
        st[a] = round(st[a] * k, 2)
    st["x1"], st["y1"] = round(st["x0"] + 1.80, 2), round(st["y0"] + 2.30, 2)
    for c in st.get("cage_walls") or []:
        c["x"] = round(c["x"] * sx, 3)
        c["y0"], c["y1"] = st["y0"], st["y1"]
    if floors == 1:
        lv = raw["levels"][0]
        raw["levels"] = [lv]
        raw["openings"] = [o for o in raw["openings"] if o.get("level") == lv["id"]]
        for k in ("rooms", "interior_walls"):
            raw[k] = {kk: v for kk, v in raw[k].items() if kk == lv["id"]}
        raw.pop("stair", None)
    if f["flat"] or floors == 1 and not re.search(r"telha|deux pans|duas águas|tuile", (hypotheses or "").lower()):
        top = raw["levels"][-1]["floor_top"] + raw["levels"][-1]["ceiling_height"] + 0.25
        raw["roof"] = {"type": "terrasse", "eaves_level": round(top + 0.3, 2), "ridge_level": round(top + 0.3, 2),
                       "covering": "laje maciça BA com impermeabilização e isolamento", "_source": "HIPÓTESE"}
    pr = raw["project"]
    pr.update({"name": f"Moradia unifamiliar{(' T' + str(f['typology'])) if f['typology'] else ''} — ESTUDO INDICATIVO (sem desenhos)",
               "address": f["concelho"] or pr.get("address"), "country": country,
               "pc_ref": "Sem desenhos de arquitetura: modelo-tipo", "_typical_model": True})
    pr["address"] = f"{f['concelho']} (concelho)" if f["concelho"] else "Morada a indicar (sem documentos de arquitetura)"
    raw["geotech"]["source"] = "Sem estudo geotécnico: valores prudentes por defeito (HIPÓTESE)"
    raw["_typical"] = f
    dec = [f"ESTUDO INDICATIVO: os documentos não têm desenhos de arquitetura cotados; geometria estimada (modelo-tipo) com "
           f"{area:.0f} m² {'(lidos nos documentos)' if f['area'] else '(por defeito)'}, "
           f"{floors} piso(s){', T' + str(f['typology']) if f['typology'] else ''}"
           f"{', cobertura plana' if raw['roof']['type'] == 'terrasse' else ''}. Todas as medidas são HIPÓTESES — "
           "juntar as plantas, cortes e alçados cotados para o estudo definitivo."]
    raw.setdefault("_decisions", [])
    raw["_decisions"] += dec
    return raw, dec
