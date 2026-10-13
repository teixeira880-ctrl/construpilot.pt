"""Étape 2 — Rapprochement CCTP ↔ DPGF/devis (déterministe, sourcé).

Produit des CONTRÔLES CROISÉS avec leurs deux sources :
- épaisseur / performance différente entre CCTP et devis ;
- ouvrage prescrit au CCTP mais aucune ligne de devis correspondante (omission possible) ;
- poste possiblement compté dans deux lots (double comptage).

Approche lexicale + dictionnaire FR/PT + attributs mesurables (épaisseur mm, R thermique).
Aucune équivalence n'est affirmée sur la seule proximité de vocabulaire : les écarts sont
présentés comme « à vérifier », jamais comme des certitudes. La mémoire des corrections
(Niveau A) permet de neutraliser un point déjà tranché, selon sa portée.
"""
from __future__ import annotations

import hashlib
import re

from engines.dpgf_engine import fold, _is_lot_title

# --- Dictionnaire métier FR/PT : familles → variantes/synonymes -------------
SYNONYMS = {
    "carrelage": ["carrelage", "carreau", "carreaux", "revetement carrele", "faience",
                  "ceramica", "azulejo", "revestimento ceramico", "ladrilho"],
    "cloison": ["cloison", "cloisonnement", "doublage", "divisoria", "tabique"],
    "platre": ["platre", "placo", "plaque de platre", "ba13", "ba 13", "gyproc", "gesso", "pladur"],
    "isolant": ["isolant", "isolation", "laine de verre", "laine de roche", "polystyrene",
                "pse", "pu", "isolamento", "la de rocha", "la de vidro"],
    "peinture": ["peinture", "peint", "tinta", "pintura"],
    "beton": ["beton", "betao", "dalle beton", "chape", "betonilha"],
    "parpaing": ["parpaing", "agglo", "bloc beton", "moellon", "bloco"],
    "enduit": ["enduit", "crepi", "reboco", "estuque"],
    "menuiserie": ["menuiserie", "fenetre", "porte", "chassis", "janela", "porta", "caixilho"],
    "etancheite": ["etancheite", "impermeabilisation", "sel", "impermeabilizacao"],
    "plancher": ["plancher", "dallage", "sol", "pavimento"],
    "toiture": ["toiture", "couverture", "cobertura", "telhado"],
}
_CANON = {}
for canon, variants in SYNONYMS.items():
    for v in variants:
        _CANON[fold(v)] = canon

_STOP = set(fold(w) for w in (
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "sur", "pour", "par",
    "avec", "au", "aux", "ml", "m2", "m3", "ht", "tva", "compris", "y", "fourniture",
    "pose", "ep", "epaisseur", "type", "ou", "a", "l", "d", "the", "com", "para", "do", "da"))


def _tokens(text: str) -> set:
    raw = re.findall(r"[a-z0-9]+", fold(text))
    out = set()
    for t in raw:
        if len(t) < 3 or t in _STOP or t.isdigit():
            continue
        out.add(_CANON.get(t, t))
    # bigrammes canoniques (ex. "plaque platre")
    words = [w for w in raw if len(w) >= 3]
    for i in range(len(words) - 1):
        bg = _CANON.get(fold(words[i] + " " + words[i + 1]))
        if bg:
            out.add(bg)
    return out


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / len(ta | tb)


def _thickness_mm(text: str) -> set:
    vals = set()
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(mm|cm)\b", fold(text)):
        v = float(m.group(1).replace(",", "."))
        vals.add(round(v * (10 if m.group(2) == "cm" else 1)))
    return vals


def _perf_R(text: str) -> set:
    vals = set()
    for m in re.finditer(r"\br\s*=?\s*(\d+(?:[.,]\d+)?)", fold(text)):
        vals.add(round(float(m.group(1).replace(",", ".")), 2))
    return vals


def extract_prescriptions(pdf_lines: list[dict]) -> list[dict]:
    """Sélectionne les lignes CCTP porteuses d'un attribut mesurable ou d'une famille."""
    out = []
    for ln in pdf_lines or []:
        text = (ln.get("text") or "").strip()
        if len(text) < 6:
            continue
        # Ignorer les titres de lot / sections (pas des ouvrages à chiffrer)
        if _is_lot_title(text, None, None):
            continue
        th = _thickness_mm(text)
        rp = _perf_R(text)
        toks = _tokens(text)
        family = next((t for t in toks if t in SYNONYMS), None)
        # Attribut mesurable → toujours retenu ; sinon famille + libellé un peu descriptif
        if not (th or rp or (family and len(text) >= 15 and len(toks) >= 2)):
            continue
        out.append({
            "prescription_id": "cctp_" + hashlib.sha1(f"{ln.get('page')}:{text}".encode()).hexdigest()[:10],
            "text": text[:400], "page": ln.get("page"), "bbox": ln.get("bbox"),
            "thickness_mm": sorted(th), "perf_R": sorted(rp), "family": family,
        })
    return out


def _sig(kind: str, *parts: str) -> str:
    return "rec_" + hashlib.sha1((kind + "|" + "|".join(fold(p) for p in parts)).encode()).hexdigest()[:12]


def reconcile(devis_lines: list[dict], prescriptions: list[dict],
              corrections: list[dict] | None = None, threshold: float = 0.34,
              vectors: dict | None = None, embed_min: float = 0.45) -> dict:
    """Rapproche chaque ligne de devis à la meilleure prescription et lève les écarts.

    `vectors` (optionnel) : {texte: embedding} pour un appoint SÉMANTIQUE. Il ne
    remplace jamais le lexical : score combiné = max(lexical, cosinus si ≥ embed_min).
    Chaque rapprochement indique la méthode retenue (lexical / sémantique)."""
    corr = {c.get("signature"): c for c in (corrections or []) if c.get("active", True)}
    details = [l for l in devis_lines if l.get("kind") == "detail"]
    matches, anomalies = [], []
    matched_prescriptions = set()
    semantic_used = False

    def _combined(a: str, b: str) -> tuple[float, str]:
        lex = similarity(a, b)
        if vectors:
            va, vb = vectors.get(a), vectors.get(b)
            if va and vb:
                from engines.doc_embeddings import cosine as _cos
                emb = _cos(va, vb)
                if emb >= embed_min and emb > lex:
                    return emb, "sémantique"
        return lex, "lexical"

    for l in details:
        des = l.get("designation") or ""
        best, best_s, best_method = None, 0.0, "lexical"
        for p in prescriptions:
            s, method = _combined(des, p["text"])
            if s > best_s:
                best, best_s, best_method = p, s, method
        l_th = _thickness_mm(des)
        if best and best_s >= threshold:
            if best_method == "sémantique":
                semantic_used = True
            matched_prescriptions.add(best["prescription_id"])
            entry = {"line_id": l["line_id"], "designation": des,
                     "devis_source": l["provenance"].get("designation"),
                     "prescription_id": best["prescription_id"], "cctp_text": best["text"],
                     "cctp_page": best["page"], "score": round(best_s, 2),
                     "method": best_method}
            matches.append(entry)
            # Écart d'épaisseur (les deux connues et disjointes)
            p_th = set(best["thickness_mm"])
            if l_th and p_th and l_th.isdisjoint(p_th):
                sig = _sig("thickness", des, best["text"])
                if corr.get(sig, {}).get("resolution") not in ("resolved", "ignored"):
                    anomalies.append({
                        "signature": sig, "type": "thickness_mismatch",
                        "message": f"Épaisseur CCTP {sorted(p_th)} mm vs devis {sorted(l_th)} mm — à vérifier",
                        "cctp": {"text": best["text"], "page": best["page"], "value_mm": sorted(p_th)},
                        "devis": {"designation": des, "source": l["provenance"].get("designation"),
                                  "value_mm": sorted(l_th)},
                    })

    # Ouvrage prescrit mais aucune ligne de devis rapprochée
    for p in prescriptions:
        if p["prescription_id"] in matched_prescriptions:
            continue
        if not (p["thickness_mm"] or p["perf_R"] or p["family"]):
            continue
        sig = _sig("missing", p["text"])
        if corr.get(sig, {}).get("resolution") in ("resolved", "ignored"):
            continue
        anomalies.append({
            "signature": sig, "type": "prescribed_not_found",
            "message": "Ouvrage prescrit au CCTP sans ligne de devis rapprochée — omission possible (à confirmer)",
            "cctp": {"text": p["text"], "page": p["page"],
                     "value_mm": p["thickness_mm"], "family": p["family"]},
            "devis": None,
        })

    # Poste possiblement compté dans deux lots
    seen = {}
    for l in details:
        key = frozenset(_tokens(l.get("designation") or ""))
        if not key:
            continue
        prev = seen.get(key)
        if prev and prev.get("lot") != l.get("lot"):
            sig = _sig("duplicate", l.get("designation") or "", prev.get("lot") or "", l.get("lot") or "")
            if corr.get(sig, {}).get("resolution") not in ("resolved", "ignored"):
                anomalies.append({
                    "signature": sig, "type": "duplicate_lot",
                    "message": f"Poste similaire présent dans « {prev.get('lot')} » et « {l.get('lot')} » — double comptage possible",
                    "cctp": None,
                    "devis": {"designation": l.get("designation"),
                              "source": l["provenance"].get("designation"),
                              "other_source": prev["provenance"].get("designation"),
                              "lots": [prev.get("lot"), l.get("lot")]},
                })
        else:
            seen[key] = l

    summary = {
        "devis_lines": len(details), "prescriptions": len(prescriptions),
        "matched": len(matches),
        "semantic_used": semantic_used,
        "anomalies": len(anomalies),
        "thickness_mismatch": sum(1 for a in anomalies if a["type"] == "thickness_mismatch"),
        "prescribed_not_found": sum(1 for a in anomalies if a["type"] == "prescribed_not_found"),
        "duplicate_lot": sum(1 for a in anomalies if a["type"] == "duplicate_lot"),
    }
    return {"matches": matches, "anomalies": anomalies, "summary": summary}


# ============ RAPPROCHEMENT PLAN (métré) ↔ DEVIS/DPGF ============

def _dev_family(unit: str | None) -> str | None:
    u = (unit or "").strip().lower()
    if u in ("m²", "m2", "m^2"):
        return "area"
    if u in ("ml", "m", "mètre", "metre", "ml."):
        return "length"
    return None


def _measure_quantities(m: dict) -> list[tuple]:
    """Quantités comparables d'une mesure de plan : (famille, valeur, unité)."""
    out: list[tuple] = []
    kind = m.get("kind")
    if kind in ("polygon", "cumulative_area"):
        if m.get("area_m2"):
            out.append(("area", float(m["area_m2"]), "m²"))
    else:  # cote linéaire (mur/distance)
        if m.get("wall_area_net_m2"):
            out.append(("area", float(m["wall_area_net_m2"]), "m²"))
        v = m.get("value_m") if m.get("value_m") is not None else m.get("length_m")
        if v:
            out.append(("length", float(v), "ml"))
    return out


def dxf_pseudo_measurements(metre: dict | None) -> list[dict]:
    """Convertit un métré CAO/DXF (structural_metre) en cotes comparables (source=dxf).
    Longueurs en ml (murs/cloisons/poutres), surfaces en m² (dalle, escaliers)."""
    out: list[dict] = []
    if not metre:
        return out

    def add_len(mid, label, val):
        if val and float(val) > 0:
            out.append({"measurement_id": mid, "label": label, "kind": "cumulative",
                        "source": "dxf", "value_m": float(val)})

    def add_area(mid, label, val):
        if val and float(val) > 0:
            out.append({"measurement_id": mid, "label": label, "kind": "cumulative_area",
                        "source": "dxf", "area_m2": float(val)})

    add_len("dxf_murs", "Murs / voiles béton (CAO)", metre.get("walls_ml"))
    add_len("dxf_cloisons", "Cloisons (CAO)", metre.get("partitions_ml"))
    add_len("dxf_poutres", "Poutres (CAO)", metre.get("beams_ml"))
    add_len("dxf_linteaux", "Linteaux (CAO)", metre.get("linteaux_ml"))
    add_area("dxf_dalle", "Dalle / plancher (CAO)",
             metre.get("slab_area_m2") or metre.get("footprint_m2"))
    add_area("dxf_escaliers", "Escaliers (CAO)", metre.get("escaliers_area_m2"))
    return out


def _num(v) -> float:
    if isinstance(v, dict):
        v = v.get("value")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def reconcile_plan(measurements: list[dict], devis_lines: list[dict], plan_id: str = "",
                   vectors: dict | None = None, threshold: float = 0.34,
                   tol_pct: float = 5.0, embed_min: float = 0.45) -> dict:
    """Compare les quantités MESURÉES sur plan (métré) aux quantités du devis/DPGF,
    par libellé (lexical + appoint sémantique), et signale les écarts SOURCÉS.

    Sourcé des deux côtés : côté plan = libellé + id de mesure ; côté devis =
    provenance cellule. Déterministe : aucun prix ni équivalence inventés."""
    details = [l for l in devis_lines if l.get("kind") == "detail"]

    def _combined(a: str, b: str) -> tuple[float, str]:
        lex = similarity(a, b)
        if vectors:
            va, vb = vectors.get(a), vectors.get(b)
            if va and vb:
                from engines.doc_embeddings import cosine as _cos
                emb = _cos(va, vb)
                if emb >= embed_min and emb > lex:
                    return emb, "sémantique"
        return lex, "lexical"

    comparisons, unmatched = [], []
    semantic_used = False
    for m in measurements:
        label = (m.get("label") or "").strip()
        qs = _measure_quantities(m)
        if not label or not qs:
            continue
        best = None
        best_s, best_method, best_fam, best_val, best_unit = 0.0, "lexical", None, None, None
        for (fam, val, unit) in qs:
            for l in details:
                if _dev_family(l.get("unit")) != fam:
                    continue
                s, method = _combined(label, l.get("designation") or "")
                if s > best_s:
                    best, best_s, best_method = l, s, method
                    best_fam, best_val, best_unit = fam, val, unit
        if best and best_s >= threshold:
            if best_method == "sémantique":
                semantic_used = True
            dq = _num(best.get("qty"))
            delta_pct = round((dq / best_val - 1) * 100, 1) if best_val else None
            comparisons.append({
                "measurement_id": m.get("measurement_id"),
                "label": label, "family": best_fam, "unit": best_unit,
                "source": m.get("source") or "cote",
                "measured": round(best_val, 3), "devis_qty": round(dq, 3),
                "devis_line_id": best.get("line_id"),
                "delta_pct": delta_pct, "score": round(best_s, 2), "method": best_method,
                "flag": bool(delta_pct is not None and abs(delta_pct) > tol_pct),
                "plan": {"plan_id": plan_id, "measurement_id": m.get("measurement_id"),
                         "label": label},
                "devis": {"designation": best.get("designation"),
                          "source": best["provenance"].get("designation") if best.get("provenance") else None,
                          "lot": best.get("lot"), "unit": best.get("unit"), "qty": dq},
            })
        else:
            unmatched.append({
                "measurement_id": m.get("measurement_id"), "label": label,
                "quantities": [{"family": f, "value": round(v, 3), "unit": u} for (f, v, u) in qs],
            })

    summary = {
        "measured_items": sum(1 for m in measurements if (m.get("label") or "").strip() and _measure_quantities(m)),
        "compared": len(comparisons),
        "ecarts": sum(1 for c in comparisons if c["flag"]),
        "unmatched": len(unmatched),
        "semantic_used": semantic_used,
    }
    return {"comparisons": comparisons, "unmatched": unmatched, "summary": summary}
