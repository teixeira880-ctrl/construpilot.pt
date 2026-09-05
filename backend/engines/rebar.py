"""Bordereau acier : poids théoriques + conversion « quantités chantier → commandables »."""

# Poids théorique acier HA (kg par mètre linéaire)
STEEL_KG_PER_M = {
    "HA6": 0.222, "HA8": 0.395, "HA10": 0.617, "HA12": 0.888, "HA14": 1.208,
    "HA16": 1.578, "HA20": 2.466, "HA25": 3.854, "HA32": 6.313,
}
DEFAULT_BAR_LENGTH_M = 12.0     # barre commerciale standard
DEFAULT_LOSS_PCT = 7.0          # pertes + chutes + recouvrements par défaut


def normalize_dia(d: str) -> str:
    s = str(d or "").upper().replace(" ", "").replace("Ø", "").replace("HA", "")
    return f"HA{s}" if s.isdigit() else str(d or "").upper()


def enrich_lines(lines: list[dict]) -> list[dict]:
    """Ajoute poids kg (= ml × poids/ml) et normalise le diamètre."""
    out = []
    for ln in lines or []:
        dia = normalize_dia(ln.get("diameter"))
        ml = round(float(ln.get("ml") or 0), 1)
        kg_m = STEEL_KG_PER_M.get(dia, 0)
        out.append({**ln, "diameter": dia, "ml": ml,
                    "kg": round(ml * kg_m, 1), "kg_per_m": kg_m})
    return out


def summary(lines: list[dict], treillis: list[dict]) -> dict:
    by_dia: dict = {}
    for ln in lines:
        d = by_dia.setdefault(ln["diameter"], {"diameter": ln["diameter"], "ml": 0.0, "kg": 0.0})
        d["ml"] += ln.get("ml", 0); d["kg"] += ln.get("kg", 0)
    for d in by_dia.values():
        d["ml"] = round(d["ml"], 1); d["kg"] = round(d["kg"], 1)
    tonnage = round(sum(d["kg"] for d in by_dia.values()) / 1000.0, 3)
    panels = sum(int(t.get("panels") or 0) for t in (treillis or []))
    return {"by_diameter": sorted(by_dia.values(), key=lambda x: x["diameter"]),
            "tonnage_t": tonnage, "treillis_panels": panels}


def to_commandable(lines: list[dict], treillis: list[dict], params: dict | None = None) -> dict:
    """Convertit les quantités théoriques en quantités réellement commandables."""
    p = params or {}
    loss = float(p.get("loss_pct", DEFAULT_LOSS_PCT)) / 100.0
    bar_len = float(p.get("bar_length_m", DEFAULT_BAR_LENGTH_M)) or DEFAULT_BAR_LENGTH_M
    s = summary(lines, treillis)
    items = []
    for d in s["by_diameter"]:
        ml_net = d["ml"]
        ml_corr = ml_net * (1 + loss)
        bars = int(-(-ml_corr // bar_len)) if bar_len > 0 else 0  # arrondi supérieur
        kg_corr = round(ml_corr * STEEL_KG_PER_M.get(d["diameter"], 0), 1)
        items.append({
            "designation": f"Acier {d['diameter']} en barres de {bar_len:g} m",
            "diameter": d["diameter"], "ml_net": ml_net,
            "ml_commande": round(ml_corr, 1), "loss_pct": round(loss * 100, 1),
            "bar_length_m": bar_len, "bars": bars, "kg": kg_corr, "unit": "barre",
            "qty": bars,
        })
    for t in (treillis or []):
        panels = int(t.get("panels") or 0)
        panels_corr = int(-(-(panels * (1 + loss)) // 1)) if panels else 0
        items.append({
            "designation": f"Treillis soudé {t.get('ref', '')}".strip(),
            "ref": t.get("ref"), "area_m2": t.get("area_m2"),
            "loss_pct": round(loss * 100, 1), "unit": "panneau",
            "qty": panels_corr, "panels": panels_corr,
        })
    return {"items": items, "loss_pct": round(loss * 100, 1), "bar_length_m": bar_len}


def to_csv(items: list[dict]) -> str:
    rows = ["Designation;Reference;Quantite;Unite;ML_commande;Poids_kg"]
    for it in items:
        rows.append(";".join(str(x) for x in [
            it.get("designation", ""), it.get("ref") or it.get("diameter") or "",
            it.get("qty", ""), it.get("unit", ""),
            it.get("ml_commande", ""), it.get("kg", ""),
        ]))
    return "\n".join(rows)
