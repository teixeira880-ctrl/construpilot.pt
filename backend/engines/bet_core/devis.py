"""Métré → devis chiffré (lots gros œuvre, charpente-couverture, électricité, plomberie).

Les quantités viennent toutes des moteurs (structure, charpente, MEP). Les prix unitaires
sont une bibliothèque indicative Île-de-France 2026, HT, fourni-posé, à remplacer par la
bibliothèque de prix de l'entreprise (cellules bleues du fichier Excel).
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .profiles import price as _price, profile as _profile

PRICES = {   # clé : (unité, PU € HT)
    "terr_masse": ("m³", 38.0), "blindage": ("m²", 185.0), "fouille_rigole": ("m³", 48.0), "evac": ("m³", 36.0),
    "semelle": ("m³", 430.0), "proprete": ("m²", 19.0), "voile20": ("m³", 520.0), "coffrage": ("m²", 42.0),
    "voile15": ("m³", 780.0), "gnt": ("m²", 24.0), "dallage": ("m³", 290.0), "impermea": ("ml", 95.0),
    "plancher": ("m²", 98.0), "porotherme": ("m²", 74.0), "pignon": ("m²", 88.0),
    "ch_h": ("ml", 44.0), "ch_v": ("ml", 39.0), "ch_r": ("ml", 48.0), "linteau": ("ml", 125.0), "poteau": ("u", 380.0),
    "escalier": ("u", 3300.0), "enduit": ("m²", 39.0), "inst_chantier": ("ft", 6500.0),
    "panne": ("ml", 96.0), "chevron": ("ml", 14.5), "sabliere": ("ml", 24.0), "sommier": ("u", 140.0), "lucarne": ("u", 2900.0),
    "couverture": ("m²", 69.0), "gouttiere": ("ml", 56.0), "descente": ("ml", 46.0), "isol_rampant": ("m²", 52.0),
    "pc": ("u", 78.0), "pl": ("u", 88.0), "inter": ("u", 58.0), "rj45": ("u", 98.0), "spec": ("u", 185.0),
    "tableau": ("ft", 1550.0), "gtl": ("ft", 680.0), "terre": ("ft", 480.0), "vmc": ("ft", 1150.0), "volet_circ": ("u", 140.0),
    "wc": ("u", 690.0), "lavabo": ("u", 560.0), "lave_mains": ("u", 360.0), "douche": ("u", 1250.0), "baignoire": ("u", 1150.0),
    "evier": ("u", 470.0), "attente": ("u", 160.0), "robinet_ext": ("u", 190.0), "cet": ("u", 2650.0),
    "nourrice": ("ft", 1850.0), "multicouche": ("ml", 9.5), "chute": ("ml", 39.0), "collecteur": ("ml", 48.0),
    "relevage": ("u", 1450.0), "branchement": ("ft", 950.0),
    "visa_bet": ("ft", 3600.0), "g2pro": ("ft", 2400.0), "decap": ("m³", 8.0),
}


def build_lines(m, r: dict, tim: dict, e: dict, p: dict) -> list[dict]:
    q = {i["item"]: i for i in r["quantities"]["items"]}
    L, W = m.L, m.W
    lines = []
    country = m.raw["project"].get("country", "FR")
    vat = _profile(country)["vat"]
    bsmt = m.levels[0].floor_top < -1.0
    mit = any(d["type"] == "mitoyen" for d in m.raw["sides"].values())

    def add(lot, label, key, qty, note=""):
        u, pu = PRICES[key]
        pu = _price(country, key, pu)
        lines.append({"lot": lot, "label": label, "unit": u, "qty": round(qty, 2), "pu": pu, "key": key, "note": note, "vat": vat})

    lot = "01 — Installation, études, terrassement"
    add(lot, "Installation de chantier, clôture, base vie, panneau", "inst_chantier", 1)
    add(lot, "Mission G2 PRO (géotechnicien) — exigée par la G2 AVP", "g2pro", 1)
    add(lot, "Note de calcul et visa d'un ingénieur structure (signature du dossier)", "visa_bet", 1)
    for it in r["quantities"]["items"]:
        if it["lot"] == "Terrassement":
            key = {"Décapage": "terr_masse" if bsmt else "decap", "Blindage": "blindage", "Fouilles": "fouille_rigole", "Évacuation": "evac"}[it["item"].split()[0]]
            add(lot, it["item"], key, it["qty"])
    lot = "02 — Fondations et sous-sol" if bsmt else "02 — Fondations et dallage"
    for it in r["quantities"]["items"]:
        if it["lot"] == "Fondations":
            add(lot, it["item"], "proprete" if "propreté" in it["item"] else "semelle", it["qty"])
        elif it["lot"] in ("Sous-sol", "Dallage"):
            key = ("coffrage" if "Coffrage" in it["item"] else "voile20" if "Voiles" in it["item"] else
                   "gnt" if "GNT" in it["item"] else "dallage" if "Dallage" in it["item"] else "impermea")
            add(lot, it["item"], key, it["qty"])
    lot = "03 — Gros œuvre en élévation"
    for it in r["quantities"]["items"]:
        if it["lot"] == "Gros œuvre":
            add(lot, it["item"], "voile15", it["qty"])
        elif it["lot"] == "Planchers":
            add(lot, it["item"], "plancher", it["qty"])
        elif it["lot"] == "Maçonnerie":
            add(lot, it["item"], "pignon" if "Pignons" in it["item"] else "porotherme", it["qty"])
        elif it["lot"] == "Béton armé":
            if it["item"].startswith("Chaînages horizontaux"):
                add(lot, it["item"], "ch_h", it["qty"])
            elif it["item"].startswith("Chaînages verticaux"):
                add(lot, it["item"], "ch_v", it["qty"])
            elif it["item"].startswith("Chaînages rampants"):
                add(lot, it["item"], "ch_r", it["qty"])
            elif it["item"].startswith("Linteau"):
                Lm = float(it["item"].split("L = ")[1].replace(",", "."))
                add(lot, it["item"], "linteau", Lm)
            elif it["item"].startswith("Poteau"):
                add(lot, it["item"], "poteau", 1)
        elif it["lot"] == "Escalier":
            add(lot, it["item"], "escalier", it["qty"])
    if mit:
        facade_area = 2 * W * m.roof["eaves_level"] - sum(o.width * o.height for o in m.openings)
        add(lot, "Enduit monocouche gratté façades rue et arrière (RAL 1013)", "enduit", facade_area)
    else:
        gab = len(m.roof.get("gables", [])) * L * (m.roof["ridge_level"] - m.roof["eaves_level"]) / 2
        facade_area = 2 * (L + W) * m.roof["eaves_level"] + gab - sum(o.width * o.height for o in m.openings)
        add(lot, "Enduit monocouche gratté toutes façades et pignons", "enduit", facade_area)
    lot = "04 — Charpente, couverture, zinguerie"
    n_p = len(tim["pannes"])
    add(lot, f"Pannes lamellé-collé GL24h {tim['panne_section']['label']} (×{n_p})", "panne", n_p * (tim["panne_span"] + 0.1))
    add(lot, "Sommiers BA d'appui des pannes dans les pignons", "sommier", len(m.roof.get("gables", [])) * n_p)
    add(lot, f"Chevrons C24 {tim['chevron_section']['label']} entraxe 0,60", "chevron", tim["chevron_count"] * (tim["rafter_length"] + 0.4))
    add(lot, "Sablières 75 × 200 sur arases de façade", "sabliere", 2 * W)
    if m.roof.get("dormers"):
        add(lot, "Lucarnes jacobines 1,80 m (ossature, chevêtres, couverture, habillage)", "lucarne", len(m.roof["dormers"]))
    roof_area = 2 * (tim["rafter_length"] + 0.35) * W
    add(lot, "Couverture tuile mécanique terre cuite + liteaux, contre-liteaux, écran HPV", "couverture", roof_area)
    if tim.get("insulation", "").startswith("Isolation sous rampants"):
        add(lot, "Isolation sous rampants R ≥ 8 + pare-vapeur (hors plaques)", "isol_rampant", roof_area * 0.92)
    else:
        add(lot, "Isolation du plancher de comble perdu R ≥ 7 (laine soufflée)", "isol_rampant", (L - 0.4) * (W - 0.4))
    add(lot, "Gouttières zinc demi-rondes 33", "gouttiere", 2 * W)
    add(lot, "Descentes EP zinc Ø80 + dauphins fonte côté rue" if mit else "Descentes EP zinc Ø80 + dauphins fonte", "descente", 4 * (m.roof["eaves_level"] + 0.2))
    lot = f"05 — Électricité ({_profile(country)['electrical_short']})"
    t = e["totals"]
    add(lot, "Prises de courant 16 A (encastrées, appareillage standard)", "pc", t["pc"])
    add(lot, "Points lumineux (DCL + douille)", "pl", t["pl"])
    add(lot, "Commandes (interrupteurs / va-et-vient)", "inter", t["inter"])
    add(lot, "Prises RJ45 grade 2TV", "rj45", t["rj45"])
    add(lot, "Circuits spécialisés (plaque, four, LV, LL, SL, CET, PAC, VMC, SS, porte garage)", "spec", t["spec"])
    add(lot, "Circuits volets roulants (par niveau)", "volet_circ", len([c for c in e["circuits"] if c["kind"] == "volets"]))
    add(lot, f"Tableau {e['panel']['rows']} rangées équipé ({len(e['rcds'])} ID 40 A 30 mA + disjoncteurs)", "tableau", 1)
    add(lot, "GTL + coffret de communication", "gtl", 1)
    add(lot, "Prise de terre à fond de fouille + liaisons équipotentielles", "terre", 1)
    add(lot, "VMC simple flux hygroréglable B (caisson + bouches + gaines)", "vmc", 1)
    lot = f"06 — Plomberie sanitaire ({_profile(country)['plumbing_short']})"
    counts = {}
    for f in p["fixtures"]:
        counts[f["fixture"]] = counts.get(f["fixture"], 0) + 1
    labels = {"wc": "WC suspendus avec bâti", "lavabo": "Lavabos + meubles + mitigeurs", "lave_mains": "Lave-mains",
              "douche": "Douches (receveur extra-plat, paroi, mitigeur thermostatique)", "baignoire": "Baignoire acrylique 170 + mitigeur",
              "evier": "Éviers (cuisine, buanderie) — robinetterie", "lave_vaisselle": "Attente lave-vaisselle", "lave_linge": "Attente lave-linge",
              "robinet_ext": "Robinet de puisage extérieur antigel"}
    for k, n in counts.items():
        add(lot, labels[k], "attente" if k in ("lave_vaisselle", "lave_linge") else k, n)
    add(lot, "Chauffe-eau thermodynamique 200 L + groupe de sécurité", "cet", 1)
    add(lot, "Nourrices EF/ECS, réducteur de pression, filtre, clapet EA, vannes", "nourrice", 1)
    add(lot, "Distribution multicouche sous fourreau (EF + ECS)", "multicouche", sum(f["supply_m"] * (2 if f["ecs"] else 1) for f in p["fixtures"]))
    add(lot, "Chutes EU/EV PVC Ø100 + ventilation primaire hors toiture", "chute", len(p["stacks"]) * (m.roof["ridge_level"] + 0.5 - max(0.0, m.levels[0].floor_top)))
    add(lot, "Collecteur Ø100 en plafond du sous-sol + évacuations Ø32/40/100 des appareils" if bsmt else
        "Collecteur Ø100 enterré sous dallage + évacuations Ø32/40/100 des appareils", "collecteur",
        6.0 + sum(f["horiz_m"] for f in p["fixtures"]))
    if p["relevage"]["needed"]:
        add(lot, "Poste de relevage du sous-sol (buanderie)", "relevage", 1)
    add(lot, "Raccordement au réseau en limite (hors frais concessionnaire)", "branchement", 1)
    return lines


def totals(lines: list[dict], vat: float | None = None) -> dict:
    by = {}
    for l in lines:
        by[l["lot"]] = by.get(l["lot"], 0) + l["qty"] * l["pu"]
    ht = sum(by.values())
    if vat is None:
        vat = lines[0].get("vat", 0.20) if lines else 0.20
    return {"lots": {k: round(v, 2) for k, v in by.items()}, "ht": round(ht, 2), "tva": round(ht * vat, 2), "ttc": round(ht * (1 + vat), 2), "vat": vat}


def write_xlsx(path, m, r: dict, tim: dict, e: dict, p: dict, lines: list[dict], lang: str = "fr"):
    from .i18n import protect, tr
    protect(m)
    wb = _build_xlsx(m, r, tim, e, p, lines)
    if lang != "fr":
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and not c.value.startswith("="):
                        c.value = tr(c.value, lang)
            ws.title = tr(ws.title, lang)[:31]
    wb.save(path)


def _build_xlsx(m, r: dict, tim: dict, e: dict, p: dict, lines: list[dict]):
    prof = _profile(m.raw["project"].get("country"))
    vat = lines[0].get("vat", 0.20) if lines else 0.20
    from . import brand as _brand
    br = _brand.get()
    wb = Workbook()
    F = "Arial"
    hdr_fill = PatternFill("solid", fgColor=br.hex)
    t = br.tint
    lot_fill = PatternFill("solid", fgColor="%02X%02X%02X" % (round(t.red * 255), round(t.green * 255), round(t.blue * 255)))
    thin = Side(style="thin", color="BBBBBB")
    bord = Border(left=thin, right=thin, top=thin, bottom=thin)
    blue = Font(name=F, color="0000FF", size=10)
    norm = Font(name=F, size=10)
    bold = Font(name=F, size=10, bold=True)
    white = Font(name=F, size=10, bold=True, color="FFFFFF")

    ws = wb.active
    ws.title = "Devis"
    ws["A1"] = (br.name + " — " if br.is_client else "") + "DEVIS ESTIMATIF — " + m.raw["project"]["name"]
    ws["A1"].font = Font(name=F, size=14, bold=True, color=br.hex)
    if br.logo_bytes:
        try:
            import io as _io
            from openpyxl.drawing.image import Image as _XImg
            img = _XImg(_io.BytesIO(br.logo_bytes))
            k = 48 / max(img.height, 1)
            img.width, img.height = int(img.width * k), int(img.height * k)
            ws.add_image(img, "G1")
        except Exception:  # noqa: BLE001 — logo facultatif dans l'Excel
            pass
    ws["A2"] = m.raw["project"]["address"] + " — quantités issues du dossier d'étude ConstruPilot (pré-dimensionnement)"
    ws["A2"].font = norm
    ws["A3"] = f"Cellules bleues = prix unitaires indicatifs {prof['price_ref']} HT fourni-posé, à remplacer par la bibliothèque de prix de l'entreprise. Toutes les autres cellules sont des formules."
    ws["A3"].font = Font(name=F, size=9, italic=True)
    ws["A4"] = "Taux de TVA"
    ws["B4"] = vat
    ws["B4"].font = blue
    ws["B4"].number_format = "0.0%"
    ws["C4"] = prof["vat_note"]
    ws["C4"].font = Font(name=F, size=9, italic=True)
    head = ["Lot", "Désignation", "Unité", "Quantité", "PU € HT", "Total € HT"]
    for j, h in enumerate(head, 1):
        c = ws.cell(row=6, column=j, value=h)
        c.font, c.fill, c.border = white, hdr_fill, bord
        c.alignment = Alignment(horizontal="center", vertical="center")
    row = 7
    lot_rows = {}
    current = None
    first_line = row
    for l in lines:
        if l["lot"] != current:
            current = l["lot"]
            ws.cell(row=row, column=1, value=current).font = bold
            for j in range(1, 7):
                ws.cell(row=row, column=j).fill = lot_fill
            row += 1
        ws.cell(row=row, column=1, value="L" + l["lot"][:2]).font = norm
        ws.cell(row=row, column=2, value=l["label"]).font = norm
        ws.cell(row=row, column=3, value=l["unit"]).font = norm
        cq = ws.cell(row=row, column=4, value=l["qty"])
        cq.font, cq.number_format = norm, "#,##0.00"
        cp = ws.cell(row=row, column=5, value=l["pu"])
        cp.font, cp.number_format = blue, "#,##0.00 €"
        ct = ws.cell(row=row, column=6, value=f"=D{row}*E{row}")
        ct.font, ct.number_format = norm, "#,##0.00 €"
        for j in range(1, 7):
            ws.cell(row=row, column=j).border = bord
        lot_rows.setdefault(l["lot"], []).append(row)
        row += 1
    last_line = row - 1
    row += 1
    ws.cell(row=row, column=2, value="RÉCAPITULATIF PAR LOT").font = bold
    row += 1
    for lot in lot_rows:
        ws.cell(row=row, column=2, value=lot).font = norm
        c = ws.cell(row=row, column=6, value=f'=SUMIF($A${first_line}:$A${last_line},"L{lot[:2]}",$F${first_line}:$F${last_line})')
        c.font, c.number_format = norm, "#,##0.00 €"
        row += 1
    ht_row = row
    ws.cell(row=row, column=2, value="TOTAL HT").font = bold
    c = ws.cell(row=row, column=6, value=f"=SUM(F{first_line}:F{last_line})")
    c.font, c.number_format = bold, "#,##0.00 €"
    row += 1
    ws.cell(row=row, column=2, value="TVA").font = norm
    c = ws.cell(row=row, column=6, value=f"=F{ht_row}*$B$4")
    c.font, c.number_format = norm, "#,##0.00 €"
    row += 1
    ws.cell(row=row, column=2, value="TOTAL TTC").font = bold
    c = ws.cell(row=row, column=6, value=f"=F{ht_row}+F{ht_row+1}")
    c.font, c.number_format = bold, "#,##0.00 €"
    row += 1
    sp = m.raw["project"].get("surface_plancher")
    if isinstance(sp, dict) and sp:
        tot_sp = round(sum(sp.values()), 2)
        lab = "Ratio € HT / m² de surface de plancher (PC : " + " + ".join(f"{v:.2f}".replace(".", ",") for v in sp.values()) + f" = {tot_sp:.2f} m²)".replace(".", ",")
    elif m.raw["project"].get("pc_ref", "").startswith("PCMI01 du 11/12/2024"):
        tot_sp, lab = 170.93, "Ratio € HT / m² de surface de plancher (PC : 50,40 + 64,80 + 55,73 = 170,93 m²)"
    else:
        tot_sp = round(e["habitable_area"], 2)
        lab = f"Ratio € HT / m² de surface habitable relevée ({tot_sp:.2f} m²)".replace(".", ",")
    ws.cell(row=row, column=2, value=lab).font = norm
    c = ws.cell(row=row, column=6, value=f"=F{ht_row}/{tot_sp}")
    c.font, c.number_format = norm, "#,##0 €"
    row += 2
    for t in ["Hors lots : menuiseries extérieures, plâtrerie-isolation des murs, chape, revêtements, peinture, chauffage (émetteurs + PAC), VRD extérieurs, branchements concessionnaires.",
              "Prix indicatifs non contractuels : ConstruPilot ne garantit pas les prix ; remplacer par la bibliothèque de l'entreprise avant tout envoi au client."]:
        ws.cell(row=row, column=2, value=t).font = Font(name=F, size=9, italic=True)
        row += 1
    for col, w in zip("ABCDEF", (6, 92, 8, 12, 13, 16)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A7"

    # ---- Métré structure + nomenclature
    ws2 = wb.create_sheet("Métré structure")
    for j, h in enumerate(["Lot", "Ouvrage", "Unité", "Quantité", "Acier estimé (kg)"], 1):
        c = ws2.cell(row=1, column=j, value=h)
        c.font, c.fill = white, hdr_fill
    for i, it in enumerate(r["quantities"]["items"], 2):
        for j, v in enumerate([it["lot"], it["item"], it["unit"], it["qty"], it["steel_kg"]], 1):
            ws2.cell(row=i, column=j, value=v).font = norm
    n = len(r["quantities"]["items"]) + 1
    ws2.cell(row=n + 1, column=2, value="TOTAL acier estimé (kg)").font = bold
    ws2.cell(row=n + 1, column=5, value=f"=SUM(E2:E{n})").font = bold
    ws2.cell(row=n + 2, column=2, value="Hypothèse acier : ratios par élément calculés à partir des sections d'armatures du dossier (+10 % recouvrements).").font = Font(name=F, size=9, italic=True)
    for col, w in zip("ABCDE", (14, 80, 8, 12, 18)):
        ws2.column_dimensions[col].width = w

    ws3 = wb.create_sheet("Linteaux et poteaux")
    hd = ["Repère", "Niveau", "Façade", "Portée (m)", "b × h", "M_Ed (kN.m)", "V_Ed (kN)", "Aciers inf.", "Aciers sup.", "Cadres"]
    for j, h in enumerate(hd, 1):
        c = ws3.cell(row=1, column=j, value=h)
        c.font, c.fill = white, hdr_fill
    for i, l in enumerate(r["lintels"]["lintels"], 2):
        vals = [l["id"], l["level"], l["side"], l["span"], f"{l['b']:.2f} × {l['h']:.2f}", l["M_Ed"], l["V_Ed"], l["bottom"], l["top"], l["stirrups"]]
        for j, v in enumerate(vals, 1):
            ws3.cell(row=i, column=j, value=v).font = norm
    k = len(r["lintels"]["lintels"]) + 3
    for j, h in enumerate(["Poteau", "Niveau", "Façade", "Hauteur", "Section", "N_Ed (kN)", "N_Rd (kN)", "Aciers"], 1):
        c = ws3.cell(row=k, column=j, value=h)
        c.font, c.fill = white, hdr_fill
    for i, pp in enumerate(r["lintels"]["posts"], k + 1):
        for j, v in enumerate([pp["id"], pp["level"], pp["side"], pp["height"], pp["section"], pp["N_Ed"], pp["N_Rd"], pp["steel"]], 1):
            ws3.cell(row=i, column=j, value=v).font = norm
    for j in range(1, 11):
        ws3.column_dimensions[get_column_letter(j)].width = 16

    ws4 = wb.create_sheet("Électricité")
    for j, h in enumerate(["Niveau", "Circuit", "Disjoncteur (A)", "Section (mm²)", "Points", "Différentiel"], 1):
        c = ws4.cell(row=1, column=j, value=h)
        c.font, c.fill = white, hdr_fill
    for i, c_ in enumerate(e["circuits"], 2):
        for j, v in enumerate([c_["level"], c_["name"], c_["breaker"], c_["section"], c_["points"], c_.get("rcd", "")], 1):
            ws4.cell(row=i, column=j, value=v).font = norm
    for col, w in zip("ABCDEF", (8, 52, 14, 14, 8, 12)):
        ws4.column_dimensions[col].width = w

    ws5 = wb.create_sheet("Plomberie")
    for j, h in enumerate(["Niveau", "Pièce", "Appareil", "Alimentation", "ECS", "Évacuation", "Chute", "Longueur évac. (m)"], 1):
        c = ws5.cell(row=1, column=j, value=h)
        c.font, c.fill = white, hdr_fill
    for i, f in enumerate(p["fixtures"], 2):
        for j, v in enumerate([f["level"], f["room"], f["label"], f["alim"], "oui" if f["ecs"] else "non", f["evac"], f["stack"], f["horiz_m"]], 1):
            ws5.cell(row=i, column=j, value=v).font = norm
    for col, w in zip("ABCDEFGH", (8, 20, 28, 20, 6, 14, 8, 16)):
        ws5.column_dimensions[col].width = w
    return wb
