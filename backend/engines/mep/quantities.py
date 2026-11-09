"""Nomenclature (quantités) — AUCUN prix inventé : les prix viennent de la bibliothèque de
prix de l'entreprise (`engines.price_library.match_price`) ; une ligne sans
correspondance reste « à chiffrer »."""
from __future__ import annotations

import math
from collections import Counter

D = {  # code: (FR, PT, unité)
    "EL-PRISE": ("Socle de prise de courant 2P+T 16 A, encastré, y.c. boîte", "Tomada 2P+T 16 A encastrada, c/ caixa", "u"),
    "EL-PRISE-PT": ("Socle 2P+T 16 A plan de travail, y.c. boîte", "Tomada 2P+T 16 A bancada, c/ caixa", "u"),
    "EL-PRISE-SPE": ("Prise spécialisée 2P+T 16/20 A, y.c. boîte", "Tomada dedicada 2P+T, c/ caixa", "u"),
    "EL-SORTIE-32": ("Sortie de câble 32 A (plaque de cuisson)", "Saída de cabo 32 A (placa)", "u"),
    "EL-SORTIE-20": ("Sortie de câble 20 A (chauffe-eau / VMC / IRVE)", "Saída de cabo (termoacumulador / VMC / VE)", "u"),
    "EL-DCL": ("Point lumineux DCL plafond, y.c. boîte et douille", "Ponto de luz no teto, c/ caixa e casquilho", "u"),
    "EL-APPLIQUE-EXT": ("Point lumineux extérieur étanche IP44", "Ponto de luz exterior IP44", "u"),
    "EL-INTER": ("Interrupteur simple allumage, y.c. boîte", "Interruptor simples, c/ caixa", "u"),
    "EL-VV": ("Interrupteur va-et-vient, y.c. boîte", "Comutador de escada, c/ caixa", "u"),
    "EL-RJ45": ("Prise RJ45 catégorie 6, y.c. boîte", "Tomada RJ45 cat. 6, c/ caixa", "u"),
    "EL-CAT6": ("Câble de communication catégorie 6 sous conduit", "Cabo de telecomunicações cat. 6 em tubo", "m"),
    "EL-COFFRET": ("Coffret de communication (grade 2TV)", "ATI — armário de telecomunicações", "u"),
    "EL-TABLEAU": ("Tableau électrique {rows} rangée(s) de 13 modules, y.c. peigne", "Quadro elétrico {rows} fila(s) de 13 módulos", "u"),
    "EL-DDR-A": ("Interrupteur différentiel 30 mA type A {a} A", "Interruptor diferencial 30 mA tipo A {a} A", "u"),
    "EL-DDR-F": ("Interrupteur différentiel 30 mA type F {a} A", "Interruptor diferencial 30 mA tipo F {a} A", "u"),
    "EL-DDR-AC": ("Interrupteur différentiel 30 mA type AC {a} A", "Interruptor diferencial 30 mA tipo AC {a} A", "u"),
    "EL-DISJ": ("Disjoncteur divisionnaire phase + neutre {a} A", "Disjuntor fase + neutro {a} A", "u"),
    "EL-CONTACTEUR": ("Contacteur jour/nuit 20 A (chauffe-eau)", "Contactor 20 A (termoacumulador)", "u"),
    "EL-CABLE": ("Gaine ICTA préfilée / câble 3G{s} mm²", "Tubo VD pré-cablado / cabo 3G{s} mm²", "m"),
    "EL-DAAF": ("Détecteur avertisseur autonome de fumée (DAAF) NF EN 14604", "Detetor autónomo de fumo EN 14604", "u"),
    "EL-LES": ("Liaison équipotentielle supplémentaire salle d'eau", "Ligação equipotencial suplementar", "u"),
    "PL-NOURRICE": ("Nourrice EF/ECS {n} départs, y.c. vannes d'isolement", "Coletor AF/AQ {n} saídas, c/ válvulas", "u"),
    "PL-TUBE": ("Tube {mat} Ø{d} prégainé, y.c. raccords", "Tubo {mat} Ø{d} em manga, c/ acessórios", "m"),
    "PL-PVC": ("Tube PVC évacuation Ø{d}, y.c. raccords", "Tubo PVC esgoto Ø{d}, c/ acessórios", "m"),
    "PL-CHUTE": ("Chute PVC Ø{d} avec ventilation primaire en toiture", "Tubo de queda PVC Ø{d} c/ ventilação primária", "m"),
    "PL-SIPHON": ("Siphon / raccordement d'appareil", "Sifão / ligação de aparelho", "u"),
    "PL-ROBINET": ("Robinet d'arrêt + limiteur de pression + clapet anti-retour", "Válvula de corte + redutor de pressão + válvula de retenção", "u"),
    "PL-GS": ("Groupe de sécurité chauffe-eau", "Grupo de segurança do termoacumulador", "u"),
    "PL-GS-EVAC": ("Entonnoir siphonné + évacuation PVC Ø32 du groupe de sécurité", "Funil com sifão + esgoto PVC Ø32 do grupo de segurança", "u"),
    "PL-COLLIER": ("Collier PVC Ø{d} monté sans serrage", "Abraçadeira PVC Ø{d}", "u"),
    "PL-COULISSANT": ("Manchon coulissant à bague d'étanchéité Ø{d}", "União deslizante com anel Ø{d}", "u"),
    "PL-APPAREIL": ("Raccordement {name} (alimentation + évacuation)", "Ligação {name} (abastecimento + esgoto)", "u"),
    "PL-REGARD": ("Regard de visite en sortie (pied de chute)", "Caixa de visita (saída)", "u"),
}


def _line(lang, code, qty, **kw):
    fr, pt, unit = D[code]
    text = (pt if lang == "pt" else fr).format(**kw)
    return {"code": code + ("-" + "-".join(str(v) for v in kw.values()) if kw else ""),
            "category": "electricite" if code.startswith("EL") else "plomberie",
            "designation": text, "unit": unit, "qty": round(qty, 1) if unit == "m" else int(qty)}


def build(points, elec, plumb, equipment, options, rules, lang) -> list[dict]:
    pr = rules["plumbing"]
    c = Counter(p["kind"] for p in points)
    out = []
    add = lambda code, q, **kw: out.append(_line(lang, code, q, **kw)) if q else None  # noqa: E731
    add("EL-PRISE", c["prise"])
    add("EL-PRISE-PT", c["prise_plan_travail"])
    add("EL-PRISE-SPE", c["prise_specialisee"])
    s32 = sum(1 for p in points if p["kind"] == "sortie_cable" and p.get("use") in ("plaque",))
    s20 = sum(1 for p in points if p["kind"] == "sortie_cable" and p.get("use") not in ("plaque",))
    add("EL-SORTIE-32", s32)
    add("EL-SORTIE-20", s20)
    add("EL-DCL", c["point_lumineux"])
    add("EL-APPLIQUE-EXT", c["point_lumineux_ext"])
    add("EL-INTER", c["interrupteur"])
    add("EL-VV", c["va_et_vient"])
    add("EL-RJ45", c["rj45"])
    add("EL-CAT6", elec["cables"]["rj45_cat6_m"])
    add("EL-COFFRET", c["coffret_com"])
    add("EL-TABLEAU", 1, rows=elec["panel"]["rows_13"])
    rc = Counter((r["type"], r["rating_a"]) for r in elec["rcds"])
    for (t, a), n in sorted(rc.items()):
        add({"A": "EL-DDR-A", "F": "EL-DDR-F"}.get(t, "EL-DDR-AC"), n, a=a)
    bc = Counter(cc["breaker_a"] for cc in elec["circuits"])
    for a, n in sorted(bc.items()):
        add("EL-DISJ", n, a=a)
    if elec["panel"]["contactor_hc"]:
        add("EL-CONTACTEUR", 1)
    for s, L in elec["cables"]["by_section_m"].items():
        sv = float(s)
        add("EL-CABLE", L, s=str(sv).rstrip("0").rstrip(".").replace(".", ","))
    add("EL-DAAF", c["daaf"])
    add("EL-LES", c["les"])
    # plomberie
    for m in plumb["manifolds"]:
        add("PL-NOURRICE", 1, n=m["outlets_ef"] + m["outlets_ecs"])
    tubes = Counter()
    for s in plumb["supplies"] + plumb["risers"]:
        tubes[s["pipe_ext_mm"]] += s["length_m"]
    if plumb.get("main") and plumb["main"].get("length_in_building_m"):
        tubes[plumb["main"]["pipe_ext_mm"]] += plumb["main"]["length_in_building_m"]
    if plumb.get("heater_link"):
        tubes[plumb["heater_link"]["pipe_ext_mm"]] += 2 * plumb["heater_link"]["length_m"]
    for d, L in sorted(tubes.items()):
        add("PL-TUBE", L, mat=pr["pipe_material"].split(" ")[0], d=d)
    pvc = Counter()
    for d in plumb["drains"]:
        pvc[d["diameter_mm"]] += d["length_m"]
    if plumb.get("collector"):
        pvc[plumb["collector"]["diameter_mm"]] += plumb["collector"]["length_m"]
    for d, L in sorted(pvc.items()):
        add("PL-PVC", L * (1 + options.get("pipe_slack", 0.10)), d=d)
    for st in plumb["stacks"]:
        add("PL-CHUTE", st["height_m"] + 1.5, d=st["diameter_mm"])
    # NF DTU 60.33 : colliers et assemblages coulissants des parties apparentes (étages, chutes)
    clamps, slides = Counter(), Counter()
    for el in plumb["drains"] + plumb["stacks"]:
        sup = el.get("supports")
        if sup:
            clamps[el["diameter_mm"]] += sup["colliers"]
            slides[el["diameter_mm"]] += sup["coulissants"]
    for d, n in sorted(clamps.items()):
        add("PL-COLLIER", n, d=d)
    for d, n in sorted(slides.items()):
        add("PL-COULISSANT", n, d=d)
    fx_rules = pr["fixtures"]
    fk = Counter(f["kind"] for f in equipment if f["kind"] in fx_rules)
    for k, n in sorted(fk.items()):
        add("PL-APPAREIL", n, name=fx_rules[k]["label"])
    add("PL-SIPHON", sum(fk.values()))
    if plumb.get("main"):
        add("PL-ROBINET", 1)
    if plumb.get("heater"):
        add("PL-GS", 1)
        if pr.get("dtu"):
            add("PL-GS-EVAC", 1)          # NF DTU 60.1 P1-1-3 §5.2.2 et §5.2.3
    if plumb.get("exit"):
        add("PL-REGARD", 1)
    return out


def price(lines: list[dict], library: list[dict] | None) -> dict:
    """Associe les prix de la bibliothèque de l'entreprise. Jamais de prix par défaut."""
    from engines.price_library import match_price  # import tardif : moteur testable seul
    priced = 0
    total = 0.0
    for ln in lines:
        ln["unit_price"] = None
        ln["total"] = None
        ln["price_source"] = None
        if library:
            m = match_price(ln["designation"], ln["unit"], library)
            if m:
                ln["unit_price"] = round(float(m[0]), 2)
                ln["total"] = round(ln["unit_price"] * ln["qty"], 2)
                ln["price_source"] = {"library_designation": m[1], "score": m[2]}
                priced += 1
                total += ln["total"]
    return {"priced_lines": priced, "unpriced_lines": len(lines) - priced,
            "total_ht": round(total, 2) if priced else None}


def ceil_int(x):
    return int(math.ceil(x))
