"""Métré et estimation du lot structure bois + gros œuvre (Excel à formules : quantité × PU, prix modifiables).

Prix unitaires indicatifs 2026 (fourni-posé, hors taxes) ; PT et UA = prix FR × coefficient de marché. Ce sont des
ordres de grandeur pour la décision : la consultation des entreprises (charpentier CLT, maçon) reste indispensable.
"""
from __future__ import annotations

from .lang import t
from .norms import VAT

BASE = {"clt_m3": 820.0, "clt_pose_m2": 32.0, "gl_m3": 1150.0, "gl_pose_m3": 260.0, "hanger": 95.0, "screw": 3.2, "base": 210.0,
        "splice": 160.0, "spline_m": 14.0, "steel_kg": 6.5, "brace": 380.0, "excav_m3": 32.0, "conc_fnd_m3": 175.0, "conc_slab_m2": 58.0,
        "conc_plinth_m3": 240.0, "rebar_kg": 1.85, "membrane_m": 9.0, "wall_m3": 900.0, "bracket": 28.0, "holddown": 65.0, "crane_day": 1450.0}
FACTOR = {"FR": 1.0, "PT": 0.78, "UA": 0.62}
CURRENCY = "€"


def prices(country: str) -> dict:
    f = FACTOR.get(country, 1.0)
    return {k: round(v * (f if k not in ("clt_m3", "gl_m3") else (1.0 if country == "FR" else 0.92)), 2) for k, v in BASE.items()}


def build_lines(m, r: dict) -> list[dict]:
    P = prices(r["country"])
    q = r["quantities"]
    L = []

    def add(lot, des, unit, qty, pu):
        if qty and qty > 0:
            L.append({"lot": lot, "des": des, "unit": unit, "qty": round(qty, 2), "pu": pu})
    l1 = t("1. Terrassements et fondations (gros œuvre)", "1. Movimento de terras e fundações", "1. Earthworks and foundations",
           "1. Земляні роботи та фундаменти")
    add(l1, t("Fouilles en rigoles / trous des semelles", "Escavação de sapatas", "Footing excavation", "Розробка котлованів під фундаменти"), "m³", q["excav_m3"], P["excav_m3"])
    add(l1, t(f"Béton {r['foundations']['mt']['concrete']} des semelles (coffrage compris)", f"Betão {r['foundations']['mt']['concrete']} em sapatas (com cofragem)",
              f"{r['foundations']['mt']['concrete']} concrete in footings (incl. formwork)", f"Бетон {r['foundations']['mt']['concrete']} фундаментів (з опалубкою)"),
        "m³", q["conc_fnd_m3"], P["conc_fnd_m3"])
    add(l1, t("Dallage / plancher bas BA sur hérisson et polyane", "Laje térrea BA sobre enrocamento e filme", "RC ground slab on hardcore and membrane",
              "З/б плита по ґрунту на щебеневій підготовці"), "m²", q["slab_area"] if r["foundations"]["ground_slab"]["on_grade"] else 0, P["conc_slab_m2"])
    add(l1, t("Soubassement BA h=30 cm (protection du bois, arase étanche)", "Murete BA h=30 cm (proteção da madeira, corte de capilaridade)",
              "RC upstand h=30 cm (timber protection, damp-proof course)", "З/б цоколь h=30 см (захист деревини, гідроізоляція)"), "m³", q["conc_plinth_m3"], P["conc_plinth_m3"])
    add(l1, t("Aciers HA façonnés", "Aço A500 moldado", "Reinforcing steel", "Арматура"), "kg", q["rebar_kg"], P["rebar_kg"])
    add(l1, t("Membrane d'arase sous lisses / platines", "Membrana de corte sob soleiras / chapas", "Damp-proof membrane under sole plates / base plates",
              "Гідроізоляційна мембрана під лежнями / пластинами"), "m", r["foundations"]["plinth"]["L"], P["membrane_m"])
    l2 = t("2. Structure bois massif CLT / lamellé-collé", "2. Estrutura em madeira maciça CLT / lamelado-colado", "2. Mass timber structure CLT / glulam",
           "2. Конструкції з масивної деревини CLT / клеєний брус")
    add(l2, t("Panneaux CLT de plancher et toiture, usinés CNC (fourniture)", "Painéis CLT de pavimento e cobertura, maquinados CNC (fornecimento)",
              "CLT floor and roof panels, CNC machined (supply)", "Панелі CLT перекриттів і покрівлі, обробка ЧПК (постачання)"), "m³", q["clt_m3"], P["clt_m3"])
    add(l2, t("Pose des panneaux CLT (levage, calage, vissage)", "Montagem dos painéis CLT (elevação, calços, aparafusamento)", "CLT panel installation (lifting, shimming, screwing)",
              "Монтаж панелей CLT (підйом, вирівнювання, кріплення)"), "m²", q["clt_m2"], P["clt_pose_m2"])
    add(l2, t("Murs CLT porteurs (fourniture et pose)", "Paredes CLT resistentes (fornecimento e montagem)", "Load-bearing CLT walls (supply and install)",
              "Несучі стіни CLT (постачання та монтаж)"), "m³", q["wall_m3"], P["wall_m3"])
    add(l2, t("Poutres, pannes et sommiers lamellé-collé GL24h/GL28h", "Vigas, madres e vigas principais lamelado-colado GL24h/GL28h",
              "Glulam beams, purlins and girders GL24h/GL28h", "Балки, прогони та ригелі з клеєного бруса GL24h/GL28h"), "m³", q["gl_beams_m3"], P["gl_m3"] + P["gl_pose_m3"])
    add(l2, t("Poteaux lamellé-collé GL24h/GL28h", "Pilares lamelado-colado GL24h/GL28h", "Glulam columns GL24h/GL28h", "Колони з клеєного бруса GL24h/GL28h"),
        "m³", q["gl_cols_m3"], P["gl_m3"] + P["gl_pose_m3"])
    l3 = t("3. Assemblages et quincaillerie", "3. Ligações e ferragens", "3. Connections and hardware", "3. Вузли та кріплення")
    add(l3, t("Étriers cachés poutre / poteau et poutre / poutre", "Ligadores ocultos viga / pilar e viga / viga", "Concealed beam hangers", "Приховані опори балок"),
        "u", q["hangers"], P["hanger"])
    add(l3, t("Vis entièrement filetées Ø8 des étriers", "Parafusos Ø8 de rosca total dos ligadores", "Ø8 fully threaded hanger screws", "Шурупи Ø8 з повною різьбою"),
        "u", q["hanger_screws"], P["screw"])
    add(l3, t("Pieds de poteaux : platine S355, tiges d'ancrage, calage mortier", "Bases de pilares: chapa S355, chumbadouros, argamassa de selagem",
              "Column bases: S355 plate, anchor rods, grout", "Опори колон: пластина S355, анкери, підливка"), "u", q["bases"], P["base"])
    add(l3, t("Aboutages de poteaux au droit des planchers (platines S355)", "Emendas de pilares nos pisos (chapas S355)", "Column splices at floors (S355 plates)",
              "Стики колон на рівні перекриттів (пластини S355)"), "u", q["splices"], P["splice"])
    add(l3, t("Éclissages des joints CLT (LVL 27×100 + vis Ø6)", "Juntas CLT (LVL 27×100 + parafusos Ø6)", "CLT joint splines (LVL 27×100 + Ø6 screws)",
              "Накладки стиків CLT (LVL 27×100 + шурупи Ø6)"), "m", q["spline_m"], P["spline_m"])
    if r["lateral"].get("braces"):
        add(l3, t("Palées de stabilité en croix (tirants acier S355 + ridoirs)", "Contraventamentos em cruz (tirantes S355 + esticadores)",
                  "Cross bracing (S355 tie rods + turnbuckles)", "Хрестові в'язі (тяжі S355 + талрепи)"), "u", q["braces"], P["brace"])
    if r["lateral"].get("walls"):
        nb = sum(v["brackets"] for v in r["lateral"]["walls"].values())
        nh = sum(v["holddowns"] for v in r["lateral"]["walls"].values())
        add(l3, t("Équerres de cisaillement murs CLT", "Esquadros de corte das paredes CLT", "CLT wall shear brackets", "Кутики зсуву стін CLT"), "u", nb * len(m.levels), P["bracket"])
        add(l3, t("Ancrages d'about (hold-down)", "Ancoragens de extremidade (hold-down)", "Hold-downs", "Анкери відриву (hold-down)"), "u", nh * len(m.levels), P["holddown"])
    l4 = t("4. Installation de chantier et levage", "4. Estaleiro e elevação", "4. Site set-up and lifting", "4. Облаштування майданчика та підйом")
    days = max(5, round((q["clt_m2"] / 180 + (q["gl_beams_m3"] + q["gl_cols_m3"]) / 8)))
    add(l4, t("Grue mobile + équipe de levage (jours)", "Grua móvel + equipa de elevação (dias)", "Mobile crane + lifting crew (days)", "Автокран + бригада (днів)"),
        "j" if r["country"] == "FR" else "d", days, P["crane_day"])
    return L


def totals(lines: list[dict], country: str) -> dict:
    ht = sum(x["qty"] * x["pu"] for x in lines)
    vat = VAT.get(country, 0.20)
    return {"ht": round(ht, 2), "vat": vat, "ttc": round(ht * (1 + vat), 2)}


def write_xlsx(path, m, lines: list[dict], country: str):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = t("Devis", "Orçamento", "Estimate", "Кошторис")[:30]
    hdr = [t("Lot", "Capítulo", "Package", "Розділ"), t("Désignation", "Designação", "Description", "Найменування"), t("Unité", "Un.", "Unit", "Од."),
           t("Quantité", "Quantidade", "Quantity", "Кількість"), t("PU € HT", "PU € s/IVA", "Unit € excl. VAT", "Ціна € без ПДВ"),
           t("Total € HT", "Total € s/IVA", "Total € excl. VAT", "Сума € без ПДВ")]
    ws.append([m.project.get("name", "")])
    ws.append([t("Estimation structure bois massif + gros œuvre — prix unitaires modifiables (indicatifs)",
                 "Estimativa estrutura de madeira maciça + fundações — preços unitários editáveis (indicativos)",
                 "Mass timber structure + foundations estimate — editable (indicative) unit prices",
                 "Кошторис конструкцій з масивної деревини та фундаментів — орієнтовні ціни, можна змінювати")])
    ws.append([])
    ws.append(hdr)
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4D3A")
    ws["A1"].font = Font(bold=True, size=13)
    row = first = 5
    for x in lines:
        ws.append([x["lot"], x["des"], x["unit"], x["qty"], x["pu"], f"=D{row}*E{row}"])
        ws[f"E{row}"].number_format = "#,##0.00"
        ws[f"F{row}"].number_format = "#,##0.00"
        row += 1
    last = row - 1
    vat = VAT.get(country, 0.20)
    ws.append([])
    row += 1
    ws.append(["", t("TOTAL HT", "TOTAL s/IVA", "TOTAL excl. VAT", "РАЗОМ без ПДВ"), "", "", "", f"=SUM(F{first}:F{last})"])
    ws.append(["", t("TVA", "IVA", "VAT", "ПДВ") + f" {int(vat * 100)} %", "", "", "", f"=F{row}*{vat}"])
    ws.append(["", t("TOTAL TTC", "TOTAL c/IVA", "TOTAL incl. VAT", "РАЗОМ з ПДВ"), "", "", "", f"=F{row}+F{row + 1}"])
    for rr in (row, row + 1, row + 2):
        ws[f"B{rr}"].font = Font(bold=True)
        ws[f"F{rr}"].font = Font(bold=True)
        ws[f"F{rr}"].number_format = "#,##0.00"
    for col, w in zip("ABCDEF", (38, 72, 7, 12, 14, 16)):
        ws.column_dimensions[col].width = w
    for r_ in ws.iter_rows(min_row=5, max_row=last):
        r_[1].alignment = Alignment(wrap_text=True)
    ws.freeze_panes = "A5"
    wb.save(str(path))
    try:                                  # totais visíveis em qualquer pré-visualização
        from engines.xlsx_cache import preencher as _preencher_xlsx
        _preencher_xlsx(str(path))
    except Exception:  # noqa: BLE001 — o Excel recalcula ao abrir
        pass
