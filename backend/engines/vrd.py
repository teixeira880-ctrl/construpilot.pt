"""Métré VRD (Voirie & Réseaux Divers) → réseaux + tranchées → quantités commandables.
Module « Analyse technique & Approvisionnement IA » — Phase 3 (VRD)."""
import math

# Réseaux : dimensions de tranchée par défaut (m), fourniture type, couleur grillage
NETWORKS = {
    "EP": {"label": "Eaux pluviales (EP)", "prof": 0.80, "larg": 0.40,
           "pipe": "Tuyau PVC CR8 Ø200", "grillage": "marron"},
    "EU": {"label": "Águas residuais domésticas", "prof": 0.80, "larg": 0.40,
           "pipe": "Tuyau PVC CR8 Ø160", "grillage": "marron"},
    "AEP": {"label": "Eau potable (AEP)", "prof": 0.90, "larg": 0.40,
            "pipe": "Tuyau PEHD Ø40 (couronne)", "grillage": "bleu"},
    "telecom": {"label": "Telecomunicações / Eletricidade", "prof": 0.70, "larg": 0.40,
                "pipe": "Tubo corrugado Ø63", "grillage": "vert/rouge"},
    "gaz": {"label": "Gaz", "prof": 0.80, "larg": 0.40,
            "pipe": "Tubo PE gás Ø63 (banda amarela)", "grillage": "jaune"},
}

DEFAULTS = {
    "sable_assise_m": 0.10,     # lit de pose
    "sable_enrobage_m": 0.20,   # enrobage au-dessus génératrice
    "grillage_roll_m": 100.0,   # rouleau grillage avertisseur
    "loss_pct": 5.0,
}


def compute(networks: list, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    loss = 1 + float(p["loss_pct"]) / 100.0
    items = []
    tot_deblai = tot_sable = tot_remblai = tot_refection = 0.0

    def add(desig, unit, qty, cu=None, cq=None, conf=0.8, bbox=None, network=None):
        items.append({"designation": desig, "unit": unit, "qty": round(qty, 2),
                      "commandable_unit": cu, "commandable_qty": cq,
                      "confidence": conf, "bbox": bbox, "network": network})

    for n in networks or []:
        key = n.get("key")
        cfg = NETWORKS.get(key, {})
        label = cfg.get("label", key or "Rede")
        L = max(0.0, float(n.get("length_ml") or 0))
        larg = float(n.get("larg_m") or cfg.get("larg", 0.40))
        prof = float(n.get("prof_m") or cfg.get("prof", 0.80))
        conf = float(n.get("confidence") or 0.8)
        bbox = n.get("bbox")
        if L <= 0:
            continue
        deblai = L * larg * prof
        sable = L * larg * (p["sable_assise_m"] + p["sable_enrobage_m"])
        remblai = max(0.0, deblai - sable)
        refection = L * larg
        tot_deblai += deblai; tot_sable += sable
        tot_remblai += remblai; tot_refection += refection

        add(f"{label} — {cfg.get('pipe', 'Tuyau/gaine')}", "ml", L, "ml",
            math.ceil(L * loss), conf, bbox, key)
        add(f"{label} — rede sinalizadora ({cfg.get('grillage', '')})", "ml", L,
            "rouleau", math.ceil(L * loss / p["grillage_roll_m"]), conf, bbox, key)
        add(f'{label} — vala {larg:g}×{prof:g} m (escavação)', "m³", deblai, "m³",
            math.ceil(deblai), conf, bbox, key)

    if tot_sable:
        add("Areia de assentamento/envolvimento (leito + envolvimento)", "m³", tot_sable, "m³",
            math.ceil(tot_sable * loss), 0.85, None, "tranchee")
    if tot_remblai:
        add("Aterro / tout-venant compactado", "m³", tot_remblai, "m³",
            math.ceil(tot_remblai * loss), 0.85, None, "tranchee")
    if tot_refection:
        add("Reposição de pavimento (betuminoso/lajeado)", "m²", tot_refection, "m²",
            math.ceil(tot_refection), 0.8, None, "tranchee")

    return {"items": items,
            "totals": {"deblai_m3": round(tot_deblai, 2), "sable_m3": round(tot_sable, 2),
                       "remblai_m3": round(tot_remblai, 2), "refection_m2": round(tot_refection, 2)},
            "loss_pct": p["loss_pct"]}


def to_csv(items: list) -> str:
    rows = ["Rede;Designacao;Quantidade;Unidade;Qtd_encomendavel;Unidade_encomendavel;Confianca"]
    for it in items:
        rows.append(";".join(str(x) for x in [
            it.get("network", ""), it.get("designation", ""), it.get("qty", ""),
            it.get("unit", ""), it.get("commandable_qty", ""),
            it.get("commandable_unit", ""), it.get("confidence", ""),
        ]))
    return "\n".join(rows)
