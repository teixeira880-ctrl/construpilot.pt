"""CLT only: exact CLT quantities, cutting losses and production cost. Nothing else.

Scope: the CLT panels of the house (walls, floor slab, roof, lintels, panels over doors) and the cost of producing
them (timber, glue, factory energy and water, line labour, timber freight to the factory) with the company library.
Out of scope on purpose: steel or concrete structure, windows and doors as products, insulation, linings, MEP,
finishes, transport to site, erection, overheads, sale and VAT.

Method (every figure is measured, none is a ratio):
1. Walls: the measured runs are joined over the drawn CLT lintels into production pieces, and every window / door
   opening is cut out of its piece (clt_walls.connect + analyse). Gross m² = pressed rectangle; net m² = gross minus
   the openings. Pieces are cross-checked against the union of the plan footprints (GEOS).
2. Slab and roof: the measured outline is divided into strips no wider than the press; each strip is the rectangle
   that must be pressed, and what falls outside the outline (notches, stair opening) is a cutting loss.
3. Losses: all pieces are placed on press blanks (clt_nesting). Pressed volume − net volume = loss, from the layout.
   The solver answer is kept only when proven optimal; otherwise the deterministic heuristic, so the same drawing
   always gives the same figures.
4. Production cost: clt_economics.estimate on the PRESSED volume (what the factory really makes), with the library
   restricted to the production items.
"""
from __future__ import annotations

import hashlib
import math

from shapely.geometry import Polygon, box

from bim_studio import clt_nesting, clt_walls
from bim_studio.clt_economics import CATALOGUE, EstimateInput, estimate, standard_heights

PRODUCTION_CATEGORIES = ("materia_prima", "energia", "colaboradores")
INBOUND_CODES = ("TR-MATERIA-PRIMA",)                      # timber freight sawmill → factory (part of producing the panels)
PRODUCTION_PARAMS = ("timber_input_m3_per_m3", "adhesive_kg_m2", "fabrication_h_m3", "electricity_kwh_m3",
                     "materia_prima_km", "materia_prima_truck_m3", "press_length_m", "press_width_m")
FLOOR_KEYS = ("name", "height_m", "walls", "panels", "segments", "lintels")
KIND = {"laje": "Laje", "cobertura": "Cobertura", "lintel": "Lintel à parte", "parede": "Painel sobre porta"}
MIN_PANEL_M = 0.60                                         # a slab / roof rectangle narrower than this is not a panel on its own
JUNCTION_GAP_M = 0.30                                      # a gap this narrow at a crossing wall is a junction, not an opening
DOOR_HEAD_M = 2.30                                         # door head printed on the Home A plans (Opening 900x2300H)

EN = {"Madeira de lamelas C24 seca e aplainada": "C24 lamella timber, dried and planed", "Adesivo PUR monocomponente tipo I": "One-component PUR adhesive, type I",
      "Operador de linha CLT": "CLT line operator", "hipotese": "assumption", "mercado": "market", "empresa": "company", "fabricante": "manufacturer",
      "painel CLT sobre a porta": "CLT panel over the door", "Painel CLT fornecido": "CLT panel supplied",
      "Eletricidade da fábrica": "Factory electricity", "Água da fábrica": "Factory water",
      "Transporte da madeira até à fábrica": "Timber freight to the factory", "Distância serração–fábrica (ida e volta)": "Sawmill–factory distance (round trip)",
      "m³ de madeira por camião": "m³ of timber per truck", "Tempo de fabrico por m³ de CLT": "Fabrication time per m³ of CLT",
      "Paredes": "Walls", "Laje": "Floor slab", "Cobertura": "Roof", "Lintel à parte": "Separate lintel", "Painel sobre porta": "Panel over door",
      "Piso": "Floor", "Elemento": "Element", "Painel": "Build-up", "Total": "Total", "Custo de produção": "Production cost",
      "CLT líquido": "Net CLT", "CLT prensado": "Pressed CLT", "Perdas de corte": "Cutting losses", "Custo por m³ líquido": "Cost per net m³",
      "camadas": "layers", "Código": "Code", "Designação": "Item", "Quantidade": "Quantity", "Unidade": "Unit",
      "Preço unitário (€)": "Unit cost (€)", "Custo (€)": "Cost (€)", "Origem": "Origin",
      "Só CLT · quantidades exatas, perdas, custo de produção e venda": "CLT only · exact quantities, losses, production cost and sale",
      "1. Âmbito e método": "1. Scope and method", "2. Quantidades CLT por elemento": "2. CLT quantities per element",
      "3. Vãos (janelas e portas)": "3. Openings (windows and doors)", "4. Perdas de corte na prensa": "4. Cutting losses on the press",
      "5. Verificação cruzada": "5. Cross-check", "6. Consumos de produção": "6. Production inputs", "7. Custo de produção": "7. Production cost",
      "8. Lista de peças": "8. Piece list", "Valores a confirmar pela empresa": "Values the company must confirm", "nenhum": "none",
      "Madeira comprada": "Timber purchased", "Cola": "Adhesive", "Eletricidade": "Electricity", "Horas de fabrico": "Fabrication hours",
      "Viagens de madeira": "Timber truckloads", "Peça": "Piece", "Bruto m²": "Gross m²", "Vãos m²": "Openings m²", "Líquido m²": "Net m²",
      "Líquido m³": "Net m³", "Peças": "Pieces", "Painéis de prensa": "Press blanks", "Prensado m³": "Pressed m³", "Perda m³": "Loss m³",
      "Perda %": "Loss %", "Largura (m)": "Width (m)", "Altura (m)": "Height (m)", "Área (m²)": "Area (m²)", "Tipo": "Type", "Por cima": "Above",
      "Cortado no painel CLT": "Cut out of the CLT piece", "sim": "yes", "não": "no", "Comp. (m)": "Length (m)", "Larg. (m)": "Width (m)",
      "Esp. (mm)": "Thk (mm)", "janela": "window", "vao_envidracado": "glazed bay", "porta": "door", "vão": "opening",
      "lintel CLT": "CLT lintel", "viga de aço": "steel beam", "sem CLT por cima": "no CLT above", "Método": "Method", "Valor": "Value"}


# Walls drawn with the CLT hatch that a client declares NOT to be CLT panels, per floor: {"runs": refs, "lintels": refs,
# "door_panels": n}. Home A: none. Martinho confirmed on 14/11/2026 that every wall hatched as CLT on the plans IS a CLT
# panel (an earlier reading of his red marks had removed 7 interior runs by mistake: 66.2 m³ instead of 74.2 m³).
HOME_A_NOT_CLT: dict = {}


def _apply_not_clt(floors, geometry, rules):
    """Removes the runs the client excluded, with their lintels and door panels; returns what was removed."""
    removed = []
    for fl in floors:
        rule = rules.get(fl["name"])
        if not rule:
            continue
        gone = [s for s in fl["segments"] if s["ref"] in rule["runs"]]
        fl["segments"] = [s for s in fl["segments"] if s["ref"] not in rule["runs"]]
        by = {}
        for s in fl["segments"]:
            by[s["thickness_mm"]] = by.get(s["thickness_mm"], 0.0) + s["length_m"]
        fl["walls"] = [{"thickness_mm": t, "layers": 5, "length_m": round(length, 3)} for t, length in sorted(by.items())]
        keep, i_lintel, doors = [], 0, rule["door_panels"]
        for p in fl["panels"]:
            if p["kind"] == "lintel":
                ref = fl["lintels"][i_lintel]["ref"]
                i_lintel += 1
                if ref in rule["lintels"]:
                    continue
            elif p["kind"] == "parede" and doors:
                doors -= 1
                continue
            keep.append(p)
        fl["panels"] = keep
        fl["lintels"] = [li for li in fl["lintels"] if li["ref"] not in rule["lintels"]]
        geo = geometry.get(fl["name"]) or {}
        geo["portas"] = (geo.get("portas") or [])[rule["door_panels"]:]
        removed.append(f"{fl['name']}: {len(gone)} troços ({sum(s['length_m'] for s in gone):.2f} m)".replace(".", ","))
    return removed


# English for the sentences this module writes itself (whole sentences; the dynamic parts are the groups)
EN_SENTENCES = [
    (r"PDF vetorial revisto da Home A: contornos CLT, tracejados de lintéis e vigas, corte e contornos da laje e da cobertura medidos na planta 1:50\.",
     "reviewed vector PDF of Home A: CLT outlines, dashed lintels and beams, section and slab / roof outlines measured on the 1:50 plans."),
    (r"Alturas das paredes = pé-direito acabado \+ pavimento \+ teto falso, medidos no corte\.",
     "Wall heights = finished ceiling height + floor build-up + ceiling void, measured on the section."),
    (r"Vãos sob lintel CLT: cortados no painel até 2,30 m \(topo das portas cotadas\)\. As plantas não têm alçados: os peitoris das janelas não estão desenhados, por isso não há CLT contado por baixo das janelas\. Confirmar com os alçados\.",
     "Openings under a CLT lintel: cut out of the panel up to 2.30 m (head of the dimensioned doors). The plans have no elevations: window sills are not drawn, so no CLT is counted under the windows. Confirm with the elevations."),
    (r"Vãos sob viga de aço ou sem lintel desenhado: abertura em toda a altura, sem CLT\.",
     "Openings under a steel beam or with no lintel drawn: open over the full height, no CLT."),
    (r"Paredes 160 mm = 2 × 80 mm de 3 camadas \(parede meeira\): 4 juntas coladas, como um painel de 5 camadas\.",
     "160 mm walls = 2 × 80 mm 3-layer panels (party wall): 4 glued joints, like a 5-layer panel."),
    (r"Laje do \+1 pelas faces exteriores das paredes, com a abertura da escada cortada \(medida entre as paredes da escada, a confirmar\)\.",
     "First-floor slab to the outer faces of the walls, with the stair opening cut out (measured between the stair walls, to be confirmed)."),
    (r"O RDC assenta sobre a cave em betão: não tem laje CLT\. Piso −1 fora do âmbito, por indicação do cliente\.",
     "The ground floor stands on the concrete basement: it has no CLT slab. Basement out of scope, as instructed by the client."),
    (r"Paredes interiores com trama CLT no plano mas que não são painéis CLT, por indicação do cliente em 14/11/2026 \(com os seus lintéis e painéis sobre portas\): RDC: (\d+) troços \(([\d,]+) m\); \+1: (\d+) troços \(([\d,]+) m\)\.",
     "Interior walls hatched as CLT on the plans that are not CLT panels, as instructed by the client on 14/11/2026 (with their lintels and panels over doors): ground floor: {0} runs ({1} m); first floor: {2} runs ({3} m)."),
    (r"(.+) · Laje (\d+) mm: (\d+) faixas de largura ≤ ([\d.]+) m ao longo de ([xy]) \(sentido que prensa menos; o sentido estrutural é do projeto de estabilidade\)\.",
     "{0} · floor slab {1} mm: {2} strips no wider than {3} m along {4} (the direction that presses least; the structural direction is set by the structural design)."),
    (r"(.+) · Cobertura (\d+) mm: (\d+) faixas de largura ≤ ([\d.]+) m ao longo de ([xy]) \(sentido que prensa menos; o sentido estrutural é do projeto de estabilidade\)\.",
     "{0} · roof {1} mm: {2} strips no wider than {3} m along {4} (the direction that presses least; the structural direction is set by the structural design)."),
    (r"(.+): sem contorno medido; conta pela área, sem perdas de corte\.", "{0}: no measured outline; counted by area, without cutting losses."),
    (r"(.+) · (lintel-\d+): lintel de (\d+) mm com espessura diferente das paredes; fica como painel à parte\.",
     "{0} · {1}: {2} mm lintel, thicker than the walls; it stays a separate panel."),
    (r"VENDA-CLT · preço de venda do CLT ([\d.]+) €/m³: referência de mercado, não é o preço da empresa\.",
     "VENDA-CLT · CLT sale price {0} €/m³: market reference, not the company's price."),
    (r"VENDA-CLT · a biblioteca não tem preço de venda do CLT: a venda e a margem não foram calculadas\.",
     "VENDA-CLT · the library has no CLT sale price: sale and margin were not calculated."),
    (r"Como a fábrica prensa: cada peça à sua medida \(valor principal\) ou painéis de formato fixo ([\d.]+) × ([\d.]+) m com corte de 10 mm \(segundo cenário\)\.",
     "How the factory presses: each piece to measure (main figure) or fixed-format blanks {0} × {1} m with a 10 mm kerf (second scenario)."),
    # cross-check with what is written on the plans
    (r"Paredes CLT \(corte\)", "CLT walls (section)"), (r"Laje \(corte\)", "Floor slab (section)"), (r"Cobertura \(corte\)", "Roof (section)"),
    (r"Altura das paredes · Rés-do-chão", "Wall height · ground floor"), (r"Altura das paredes · 1\.º andar", "Wall height · first floor"),
    (r"Portas escritas · Rés-do-chão", "Doors written · ground floor"), (r"Portas escritas · 1\.º andar", "Doors written · first floor"),
    (r"Terraço coberto \(área escrita\)", "Covered terrace (written area)"), (r"Lintéis CLT \(legenda\)", "CLT lintels (key)"),
    (r"Pilares de lamelado e vigas de aço \(legenda\)", "Glulam columns and steel beams (key)"),
    (r"Paredes com trama CLT retiradas", "Walls hatched as CLT that were removed"),
    (r"Laje e cobertura CLT", "CLT slab and roof"), (r"Paredes CLT", "CLT walls"), (r"Alturas", "Heights"), (r"Portas escritas", "Doors written"),
    (r"(Ceiling height [\d /]+ mm) \(teto acabado\)", "{0} (finished ceiling)"),
    (r"(\d+) portas: (.+)", "{0} doors: {1}"), (r"CLT lintel \(tracejado\)", "CLT lintel (dashed)"),
    (r"trama «CLT wall 100mm» no plano", "«CLT wall 100mm» hatch on the plans"),
    (r"(\d+) mm, (\d+) camadas", "{0} mm, {1} layers"),
    (r"([\d,]+) m \(teto \+ pavimento \+ teto falso do corte\)", "{0} m (ceiling + floor build-up + ceiling void from the section)"),
    (r"(\d+) em parede CLT \(as outras estão em divisórias\)", "{0} in CLT walls (the others are in partitions)"),
    (r"([\d,]+) m² entre as paredes medidas", "{0} m² between the measured walls"), (r"(\d+) lintéis contados", "{0} lintels counted"),
    (r"fora do cálculo: não são painéis CLT", "out of the calculation: they are not CLT panels"),
    (r"(\d+) troços retirados por indicação do cliente", "{0} runs removed as instructed by the client"),
    (r"a altura estrutural tem de ser maior do que o teto acabado", "the structural height must exceed the finished ceiling"),
    (r"tolerância 2 %", "2 % tolerance"),
    (r"o plano e a indicação do cliente não coincidem: prevalece a indicação", "the plans and the client's instruction differ: the instruction prevails"),
    (r"não está escrito", "not written"), (r"sem texto no plano para conferir", "no text on the plans to check against"),
    (r"as portas em parede CLT são cortadas no painel; as outras estão em divisórias", "doors in CLT walls are cut out of the panel; the others are in partitions"),
    (r"a parede vai do pavimento em tosco à laje: é mais alta do que o teto acabado", "the wall runs from the structural floor to the slab: it is taller than the finished ceiling"),
]


def to_english(text):
    """English for one printed text: this module's own sentences, then the CLT dictionary of the platform."""
    import re
    from bim_studio import clt_i18n
    if text is None:
        return text
    text = str(text)
    if text in EN:
        return EN[text]
    for pattern, out in EN_SENTENCES:
        m = re.fullmatch(pattern, text)
        if m:
            return re.sub(r"(?<=\d),(?=\d)", ".", out.format(*m.groups()))
    return clt_i18n.tr(text, "en")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# geometry of the reviewed Home A PDF
# ---------------------------------------------------------------------------------------------------------------------
def floors_from_reviewed_pdf(data: bytes, client_rules: bool = True):
    """Floors of the reviewed Home A PDF (vector take-off), CLT only, with the slab / roof outlines and the openings.
    client_rules: leaves out the walls the client says are not CLT (HOME_A_NOT_CLT). None for any other file."""
    from bim_studio import home_a_takeoff as H
    if _sha(data) != H.SOURCE_SHA256:
        return None
    import fitz
    from bim_studio.clt_pdf import inspect_pdf
    report = inspect_pdf(data)
    extras = (report.get("estimate_extras") or {}).get("floors") or {}
    pages = [p for p in report["pages"] if (p.get("review") or {}).get("in_scope")]
    floors, geometry = [], {}
    for page, key in zip(pages, ("RDC", "+1")):
        more, review = extras[key], page["review"]
        runs = [m for m in review["markers"] if m.get("length_m")]
        by = {}
        for m in runs:
            t = round(m["drawing_width_mm"] / 10) * 10
            by[t] = by.get(t, 0.0) + m["length_m"]
        floors.append({"name": key, "height_m": more["height_m"],
                       "walls": [{"thickness_mm": t, "layers": 5, "length_m": round(length, 3)} for t, length in sorted(by.items())],
                       "panels": more["panels"],
                       "segments": [{"ref": m["id"], "thickness_mm": round(m["drawing_width_mm"] / 10) * 10,
                                     "length_m": round(m["length_m"], 3), "rect_m": m.get("plan_rect_m")} for m in runs],
                       "lintels": [{"ref": m["id"], "rect_m": m["plan_rect_m"], "head_m": m["head_m"], "thickness_mm": m.get("thickness_mm")}
                                   for m in review["markers"] if m["id"].startswith("lintel-") and m.get("plan_rect_m")]})
        h = more["height_m"]
        geometry[key] = {
            "vaos": [{"tipo": o["tipo"], "largura_m": o["largura_m"],
                      "por_cima": {"lintel": "lintel CLT", "viga": "viga de aço"}.get(o["sobre"], "sem CLT por cima"),
                      "altura_m": DOOR_HEAD_M if o["sobre"] == "lintel" else h, "exterior": True} for o in review["openings"]["exterior"]]
                    + [{"tipo": "porta", "largura_m": d["width_m"], "por_cima": "lintel CLT" if d["under_lintel"] else "painel CLT sobre a porta",
                        "altura_m": d["height_m"] or DOOR_HEAD_M, "exterior": False} for d in review["openings"]["doors_in_clt"]],
            "portas": [{"largura_m": d["width_m"], "altura_m": d["height_m"]} for d in review["openings"]["doors_in_clt"]
                       if not d["under_lintel"] and d["height_m"]],
            "placas": []}
    with fitz.open(stream=data, filetype="pdf") as doc:
        page = doc[2]
        k, markers, _polys = H._wall_geometry(page)
        plate, void, outline = H.upper_plate(page, markers)
    sec = next(p for p in report["pages"] if (p.get("review") or {}).get("structural_offsets"))["review"]["structural_offsets"]["panels"]
    to_m = lambda g: [(round(x * k, 4), round(-y * k, 4)) for x, y in g.exterior.coords]
    geometry["+1"]["placas"] = [
        {"kind": "laje", "contorno_m": to_m(plate), "vazios_m": [to_m(void)], **sec["laje"]},
        {"kind": "cobertura", "contorno_m": to_m(plate), "vazios_m": [], **sec["cobertura"]}]
    roof_only = outline.difference(plate)
    geometry["RDC"]["placas"] = [{"kind": "cobertura", "contorno_m": to_m(g), "vazios_m": [], **sec["cobertura"]}
                                 for g in getattr(roof_only, "geoms", [roof_only]) if g.area * k * k > 0.01]
    import copy
    floors_plan = copy.deepcopy(floors)
    geometry["RDC"]["origem_m"], geometry["+1"]["origem_m"] = (2.216, -18.747), (2.456, -18.747)     # sheets drawn 0.24 m apart
    geometry["RDC"]["origem_placas_m"] = (2.456, -18.747)                                               # its roof outline is on the 1st-floor sheet
    removed = _apply_not_clt(floors, geometry, HOME_A_NOT_CLT) if client_rules else []
    with fitz.open(stream=data, filetype="pdf") as doc:
        written = _written_on_plans(doc, report, floors_plan, floors, geometry)
    return {"floors": floors, "geometria": geometry, "retirado": removed, "cruzamento": written,
            "origem": "PDF vetorial revisto da Home A: contornos CLT, tracejados de lintéis e vigas, corte e contornos da laje e da cobertura medidos na planta 1:50.",
            "notas": ["Alturas das paredes = pé-direito acabado + pavimento + teto falso, medidos no corte.",
                      "Vãos sob lintel CLT: cortados no painel até 2,30 m (topo das portas cotadas). As plantas não têm alçados: os peitoris das janelas não estão desenhados, por isso não há CLT contado por baixo das janelas. Confirmar com os alçados.",
                      "Vãos sob viga de aço ou sem lintel desenhado: abertura em toda a altura, sem CLT.",
                      "Paredes 160 mm = 2 × 80 mm de 3 camadas (parede meeira): 4 juntas coladas, como um painel de 5 camadas.",
                      "Laje do +1 pelas faces exteriores das paredes, com a abertura da escada cortada (medida entre as paredes da escada, a confirmar).",
                      "O RDC assenta sobre a cave em betão: não tem laje CLT. Piso −1 fora do âmbito, por indicação do cliente."]
                     + (["Paredes interiores com trama CLT no plano mas que não são painéis CLT, por indicação do cliente em 14/11/2026 "
                         "(com os seus lintéis e painéis sobre portas): " + "; ".join(removed) + "."] if removed else [])}


def _written_on_plans(doc, report, floors_plan, floors, geometry):
    """Rows (item, written on the plans, measured / used, verdict): every figure the calculation uses is set against
    what the drawings say in writing, and everything the legend calls CLT is accounted for."""
    import re
    text = [doc[i].get_text() for i in range(len(doc))]
    whole = " ".join(text)
    rows = []

    def row(item, written, used, ok, note=""):
        rows.append({"item": item, "escrito": written, "usado": used, "ok": ok, "nota": note})

    thick = sorted({int(s["thickness_mm"]) for fl in floors_plan for s in fl["segments"]})
    walls_written = sorted(set(re.findall(r"CLT 5s ([\d/]+) wall", whole)))
    row("Paredes CLT (corte)", " · ".join(f"CLT 5s {w} wall" for w in walls_written) or "—", " · ".join(f"{t} mm" for t in thick),
        bool(walls_written) and {str(t) for t in thick} <= {v for w in walls_written for v in w.split("/")})
    for kind, label, pattern in (("laje", "Laje (corte)", r"CLT\s*Panel\s*(\d+)-(\d)s"), ("cobertura", "Cobertura (corte)", r"CLT\s*Panel\s*(\d+)-(\d)s")):
        found = {(int(a), int(b)) for a, b in re.findall(pattern, whole)}
        used = {(int(p["thickness_mm"]), int(p["layers"])) for fl in floors for p in fl["panels"] if p["kind"] == kind}
        row(label, " · ".join(f"CLT Panel{a}-{b}s" for a, b in sorted(found)) or "—", " · ".join(f"{a} mm, {b} camadas" for a, b in sorted(used)),
            bool(used) and used <= found)
    extras = (report.get("estimate_extras") or {}).get("floors") or {}
    for i, key, name in ((1, "RDC", "Rés-do-chão"), (2, "+1", "1.º andar")):
        heights = sorted({int(h) for h in re.findall(r"Ceiling height (\d{4}) mm", text[i])})
        h = extras[key]["height_m"]
        row(f"Altura das paredes · {name}", "Ceiling height " + " / ".join(str(v) for v in heights) + " mm (teto acabado)",
            f"{h:.3f} m (teto + pavimento + teto falso do corte)".replace(".", ","), bool(heights) and h * 1000 > max(heights),
            "a altura estrutural tem de ser maior do que o teto acabado")
        doors = re.findall(r"(?:Opening|Aperture)\s*(\d{3,4})x(\d{4})\s*H", text[i].replace("\n", " "))
        counted = [o for o in geometry[key]["vaos"] if o["tipo"] == "porta"]
        row(f"Portas escritas · {name}", f"{len(doors)} portas: " + ", ".join(sorted({f'{a}x{b}H' for a, b in doors})),
            f"{len(counted)} em parede CLT (as outras estão em divisórias)", len(counted) <= len(doors))
    m = re.search(r"TERRACO\s+COBERTO\s+([\d.]+)\s*m", text[1])
    if m:
        runs = {s["ref"]: s["rect_m"] for s in floors_plan[0]["segments"]}
        try:
            west, east, wall = runs["clt-2894"], runs["clt-2907"], runs["clt-2905"]
            area = (east[0] - west[2]) * (max(west[3], east[3]) - wall[3])
            row("Terraço coberto (área escrita)", f"{float(m.group(1)):.2f} m²".replace(".", ","), f"{area:.2f} m² entre as paredes medidas".replace(".", ","),
                abs(area - float(m.group(1))) <= 0.02 * float(m.group(1)), "tolerância 2 %")
        except KeyError:
            pass
    row("Lintéis CLT (legenda)", "CLT lintel (tracejado)", f"{sum(len(fl['lintels']) for fl in floors)} lintéis contados", True)
    row("Pilares de lamelado e vigas de aço (legenda)", "Glulam column GL24h · Steel beam", "fora do cálculo: não são painéis CLT", True)
    removed = sum(len(fp["segments"]) - len(f["segments"]) for fp, f in zip(floors_plan, floors))
    if removed:
        row("Paredes com trama CLT retiradas", "trama «CLT wall 100mm» no plano", f"{removed} troços retirados por indicação do cliente", True,
            "o plano e a indicação do cliente não coincidem: prevalece a indicação")
    return rows


def written_on_any_plan(data: bytes, floors: list) -> list:
    """Cross-check for any vector PDF (not only the reviewed Home A): what the sheets say in writing about the CLT
    (panel build-ups, wall thicknesses, ceiling heights, door openings) against what the calculation uses."""
    import re
    import fitz
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            whole = " ".join(pg.get_text() for pg in doc).replace("\n", " ")
    except Exception:
        return []
    rows = []

    def row(item, written, used, ok, note=""):
        rows.append({"item": item, "escrito": written, "usado": used, "ok": ok, "nota": note})

    panels = {(int(a), int(b)) for a, b in re.findall(r"CLT\s*Panel\s*(\d{2,3})\s*-\s*(\d)\s*s", whole)}
    used = {(int(float(p["thickness_mm"])), int(p["layers"])) for fl in floors for p in fl.get("panels") or [] if p["kind"] in ("laje", "cobertura")}
    if panels or used:
        row("Laje e cobertura CLT", " · ".join(f"CLT Panel{a}-{b}s" for a, b in sorted(panels)) or "não está escrito",
            " · ".join(f"{a} mm, {b} camadas" for a, b in sorted(used)) or "nenhuma", bool(panels) and used <= panels,
            "" if panels else "sem texto no plano para conferir")
    walls = sorted({int(v) for w in re.findall(r"CLT\s*\d?s?\s*([\d/]+)\s*(?:mm)?\s*wall", whole) + re.findall(r"CLT wall\s*([\d+]+)\s*mm", whole)
                    for v in re.split(r"[/+]", w) if v})
    thick = sorted({int(float(w["thickness_mm"])) for fl in floors for w in fl.get("walls") or []})
    if walls or thick:
        row("Paredes CLT", " · ".join(f"{v} mm" for v in walls) or "não está escrito", " · ".join(f"{t} mm" for t in thick),
            bool(walls) and all(t in walls or t in {2 * v for v in walls} for t in thick), "" if walls else "sem texto no plano para conferir")
    ceilings = sorted({int(v) for v in re.findall(r"Ceiling height\s*(\d{4})\s*mm", whole)})
    heights = sorted({round(float(fl["height_m"]), 3) for fl in floors if fl.get("height_m")})
    if ceilings and heights:
        row("Alturas", "tetos acabados " + " / ".join(str(v) for v in ceilings) + " mm", "paredes " + " / ".join(f"{h:.3f} m".replace(".", ",") for h in heights),
            max(heights) * 1000 >= min(ceilings), "a parede vai do pavimento em tosco à laje: é mais alta do que o teto acabado")
    doors = re.findall(r"(?:Opening|Aperture)\s*(\d{3,4})\s*x\s*(\d{4})\s*H", whole)
    if doors:
        row("Portas escritas", f"{len(doors)}: " + ", ".join(sorted({f'{a}x{b}H' for a, b in doors})),
            "as portas em parede CLT são cortadas no painel; as outras estão em divisórias", True)
    return rows


def clt_only(entrada: dict) -> dict:
    """Keeps only the CLT of each floor: walls, panels and their traceability; drops rooms, windows and every lining."""
    return {"floors": [{k: v for k, v in fl.items() if k in FLOOR_KEYS} for fl in entrada["floors"]], "vat_regime": "pt"}


def production_library(library: dict) -> dict:
    return {code: item for code, item in library.items()
            if item.get("category") in PRODUCTION_CATEGORIES or code in INBOUND_CODES}


# ---------------------------------------------------------------------------------------------------------------------
# walls: pieces with the openings cut out
# ---------------------------------------------------------------------------------------------------------------------
def _gap_box(w, o):
    ux, uy = w.direction()
    nx, ny = -uy, ux
    t = w.thickness_m / 2
    a, b = o.offset_m, o.offset_m + o.width_m
    pts = [(w.x1 + ux * s + nx * d, w.y1 + uy * s + ny * d) for s, d in ((a, -t), (b, -t), (b, t), (a, t))]
    return Polygon(pts)


def _drop_junction_gaps(walls):
    """A gap under a lintel that is filled by a crossing wall is that wall's thickness, not an opening."""
    feet = {w.id: w.footprint() for w in walls}
    out = []
    for w in walls:
        keep = []
        for o in w.openings:
            gap = _gap_box(w, o)
            crossing = any(v.id != w.id and abs(v.direction()[0] * w.direction()[0] + v.direction()[1] * w.direction()[1]) < 0.5
                           and feet[v.id].buffer(0.03).intersects(gap) for v in walls)
            # narrower than any door or window and touched by a crossing wall: the thickness of that wall
            if not (o.kind == "vao" and o.width_m < JUNCTION_GAP_M and crossing):
                keep.append(o)
        out.append(w if len(keep) == len(w.openings) else clt_walls.WallAxis.model_validate({**w.model_dump(), "openings": [o.model_dump() for o in keep]}))
    return out


def _wall_pieces(fl):
    """(analysis, bridged lintel refs, notes, walls) from the measured run rectangles; None when the floor has no run geometry."""
    segs = [s for s in fl.segments if s.rect_m]
    if not segs or len(segs) != len(fl.segments):
        return None, set(), [], []
    layers = {float(w.thickness_mm): w.layers for w in fl.walls}
    walls = []
    for s in segs:
        x0, y0, x1, y1 = s.rect_m
        found, _rej = clt_walls.rectangles_to_axes([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], height_m=float(fl.height_m),
                                                  layers=int(layers.get(float(s.thickness_mm), 5)),
                                                  nominal_mm=(float(s.thickness_mm),), tolerance_mm=6)
        if not found:
            return None, set(), [f"{fl.name} · {s.ref}: contorno não convertível em eixo."], []
        walls.append(found[0].model_copy(update={"id": s.ref}))
    walls, net = clt_walls.connect(walls, lintels=[li.model_dump() for li in fl.lintels])
    walls = _drop_junction_gaps(walls)
    analysis = clt_walls.analyse(clt_walls.Floor(name=fl.name, walls=walls))
    return analysis, {r["lintel"] for r in net["linteis"]}, [f"{fl.name} · {n}" for n in net["notas"]], walls


# ---------------------------------------------------------------------------------------------------------------------
# slab and roof: strips no wider than the press
# ---------------------------------------------------------------------------------------------------------------------
def _rectangles(part: Polygon, along: str):
    """Maximal rectangles of a rectilinear band part: cut at every vertex along the strip, then rejoin equal sections.
    A part that is not rectilinear keeps its bounding rectangle (the excess is a cutting loss)."""
    i = 0 if along == "x" else 1
    cuts = sorted({round(c[i], 4) for c in part.exterior.coords})
    x0, y0, x1, y1 = part.bounds
    cells = []
    for s0, s1 in zip(cuts, cuts[1:]):
        cell = part.intersection(box(s0, y0, s1, y1) if along == "x" else box(x0, s0, x1, s1))
        for g in getattr(cell, "geoms", [cell]):
            if not isinstance(g, Polygon) or g.area < 1e-4:
                continue
            if g.area < 0.999 * box(*g.bounds).area:
                return [part.bounds]
            b = g.bounds
            cells.append((s0, s1, round(b[1 - i], 4), round(b[3 - i], 4)))
    merged = []
    for s0, s1, c0, c1 in sorted(cells, key=lambda c: (c[2], c[3], c[0])):
        if merged and merged[-1][2:] == (c0, c1) and abs(merged[-1][1] - s0) < 1e-6:
            merged[-1] = (merged[-1][0], s1, c0, c1)
        else:
            merged.append((s0, s1, c0, c1))
    return [(s0, c0, s1, c1) if along == "x" else (c0, s0, c1, s1) for s0, s1, c0, c1 in merged]


def _strips(poly: Polygon, max_width: float, max_length: float):
    """Rectangles to press for a plate outline. The outer outline is divided into equal strips no wider than the press
    and each strip into rectangles, so nothing is pressed outside the outline (a rectangle narrower than MIN_PANEL_M is
    not made on its own: the strip is then one rectangle with the notch cut out); an opening inside the plate (stair)
    is cut out of its strip and is a loss. Both strip directions are tried and the one
    that presses less is kept (ties: fewer pieces, then strips along x). Returns [(length, width, net area, rectangle)], direction."""
    outer = Polygon(poly.exterior)
    x0, y0, x1, y1 = outer.bounds
    best = None
    for along in ("x", "y"):
        lo, hi = (y0, y1) if along == "x" else (x0, x1)
        count = max(1, math.ceil((hi - lo) / max_width - 1e-9))
        edges = [lo + (hi - lo) * i / count for i in range(count + 1)]
        pieces = []
        for a, b in zip(edges, edges[1:]):
            band = box(x0, a, x1, b) if along == "x" else box(a, y0, b, y1)
            part = outer.intersection(band)
            for g in getattr(part, "geoms", [part]):
                if not isinstance(g, Polygon) or g.area < 1e-4:
                    continue
                rects = _rectangles(g, along)
                if any(min(r[2] - r[0], r[3] - r[1]) < MIN_PANEL_M for r in rects):
                    rects = [g.bounds]                       # a sliver is not a panel: one rectangle, the notch is cut out
                for rx0, ry0, rx1, ry1 in rects:
                    length, width = (rx1 - rx0, ry1 - ry0) if along == "x" else (ry1 - ry0, rx1 - rx0)
                    k = max(1, math.ceil(length / max_length - 1e-9))
                    for j in range(k):
                        cut = box(rx0 + j * (rx1 - rx0) / k, ry0, rx0 + (j + 1) * (rx1 - rx0) / k, ry1) if along == "x" else \
                            box(rx0, ry0 + j * (ry1 - ry0) / k, rx1, ry0 + (j + 1) * (ry1 - ry0) / k)
                        net = poly.intersection(cut).area
                        if net > 1e-4:
                            pieces.append((round(length / k, 4), round(width, 4), net, tuple(round(v, 4) for v in cut.bounds)))
        score = (round(sum(p[0] * p[1] for p in pieces), 6), len(pieces), along)
        if best is None or score < best[0]:
            best = (score, pieces, along)
    return best[1], best[2]


def _nest(pieces, blank, variable_width=False):
    """Blanks for the pieces, with the solver in deterministic mode: the same drawing always gives the same layout."""
    return clt_nesting.plan(clt_nesting.NestingInput(pieces=pieces, blank_length_m=blank[0], blank_width_m=blank[1], time_limit_s=4,
                                                     variable_width=variable_width, deterministic=True))


# ---------------------------------------------------------------------------------------------------------------------
# quantities, losses and cost
# ---------------------------------------------------------------------------------------------------------------------
def compute(entrada: dict, parametros: dict, biblioteca: dict, geometria: dict | None = None) -> dict:
    body = EstimateInput.model_validate(clt_only(entrada))
    body, notes = standard_heights(body, parametros)
    geometria = geometria or {}
    press = (float(parametros["press_length_m"]["value"]), float(parametros["press_width_m"]["value"]))
    pieces, elements, checks, openings, area_only, staged = [], [], [], [], [], []
    uid = iter(range(1, 10_000))
    n_strip, plate_log, n_small = [0], [], [0, 0]

    def add(floor, element, ident, length, width, t, layers, opening=0.0, vaos=()):
        pid = f"{floor}·{ident}"[:54] + f"#{next(uid)}"
        opening = max(0.0, opening)
        pieces.append({"id": pid, "piso": floor, "elemento": element, "rotulo": ident, "comprimento_m": round(length, 4), "largura_m": round(width, 4),
                       "espessura_mm": float(t), "camadas": int(layers), "bruto_m2": length * width, "vaos_m2": opening,
                       "liquido_m2": length * width - opening, "vaos": list(vaos)})

    for fl in body.floors:
        h = float(fl.height_m)
        geo = geometria.get(fl.name) or {}
        analysis, bridged, wall_notes, walls = _wall_pieces(fl)
        notes += wall_notes
        if analysis:
            staged.append((fl.name, walls, analysis["pecas"]))
            for p in analysis["pecas"]:
                add(fl.name, "Paredes", p["id"], p["comprimento_m"], p["altura_m"], p["espessura_mm"], p["camadas"], p["area_vaos_m2"],
                    [{"largura_m": round(o["width_m"], 3), "altura_m": o["height_m"], "peitoril_m": o["sill_m"]} for o in p["vaos"]])
            table = sum(float(w.length_m) * h * float(w.thickness_mm) / 1000 for w in fl.walls)
            m = analysis["metodos"]
            checks.append({"piso": fl.name, "trocos_medidos_m3": round(table, 4), "pecas_bruto_m3": m["volume_pecas_m3"],
                           "uniao_planta_m3": m["volume_uniao_planta_m3"], "ok": bool(analysis["verificacao_volume"]["passed"])})
        else:
            for w in fl.walls:
                area_only.append((fl.name, "Paredes", f"{float(w.length_m):.3f} m", float(w.length_m) * h, float(w.thickness_mm), w.layers))
        lintel_panels = [p for p in fl.panels if p.kind == "lintel"]
        matched = len(lintel_panels) == len(fl.lintels)
        doors = list(geo.get("portas") or [])
        for p in fl.panels:
            area, t = float(p.area_m2), float(p.thickness_mm)
            if p.kind == "lintel":
                li = fl.lintels[lintel_panels.index(p)] if matched else None
                if li and li.ref in bridged:
                    continue                                  # this lintel is inside its wall piece, with the opening cut out
                depth = h - li.head_m if li else None
                if depth and depth > 0.05:
                    n_small[0] += 1
                    add(fl.name, KIND["lintel"], f"LT{n_small[0]} · {t:g} mm", area / depth, depth, t, p.layers)
                else:
                    area_only.append((fl.name, KIND["lintel"], p.label, area, t, p.layers))
            elif p.kind == "parede":
                d = doors.pop(0) if doors else None
                if d and abs(d["largura_m"] * (h - d["altura_m"]) - area) < 0.01:
                    n_small[1] += 1
                    add(fl.name, KIND["parede"], f"PD{n_small[1]} · {t:g} mm", d["largura_m"], h - d["altura_m"], t, p.layers)
                else:
                    area_only.append((fl.name, KIND["parede"], p.label, area, t, p.layers))
            else:
                plates = [g for g in geo.get("placas") or [] if g["kind"] == p.kind and float(g["thickness_mm"]) == t]
                polys = [Polygon(g["contorno_m"], [v for v in g.get("vazios_m") or []]) for g in plates]
                if polys and abs(sum(q.area for q in polys) - area) < 0.02 * area:
                    for q in polys:
                        strips, along = _strips(q, press[1], press[0])
                        for length, width, net, rect in strips:
                            n_strip[0] += 1
                            add(fl.name, KIND[p.kind], f"{'L' if p.kind == 'laje' else 'C'}{n_strip[0]} · {t:g} mm", length, width, t, p.layers,
                                length * width - net)
                            pieces[-1]["ret_m"] = rect
                        plate_log.append({"piso": fl.name, "elemento": KIND[p.kind], "espessura_mm": t, "contorno_m": list(q.exterior.coords),
                                       "vazios_m": [list(r.coords) for r in q.interiors]})
                        notes.append(f"{fl.name} · {KIND[p.kind]} {t:g} mm: {len(strips)} faixas de largura ≤ {press[1]:g} m ao longo de {along} "
                                     "(sentido que prensa menos; o sentido estrutural é do projeto de estabilidade).")
                else:
                    area_only.append((fl.name, KIND[p.kind], p.label, area, t, p.layers))
        for o in geo.get("vaos") or []:
            openings.append({"piso": fl.name, **o, "area_m2": round(o["largura_m"] * o["altura_m"], 3)})

    by = {}
    for p in pieces:
        e = by.setdefault((p["piso"], p["elemento"], p["espessura_mm"], p["camadas"]),
                          {"piso": p["piso"], "elemento": p["elemento"], "espessura_mm": p["espessura_mm"], "camadas": p["camadas"], "pecas": 0,
                           "bruto_m2": 0.0, "vaos_m2": 0.0, "liquido_m2": 0.0, "liquido_m3": 0.0})
        e["pecas"] += 1
        for k in ("bruto_m2", "vaos_m2", "liquido_m2"):
            e[k] += p[k]
        e["liquido_m3"] += p["liquido_m2"] * p["espessura_mm"] / 1000
    elements = list(by.values())
    for floor, element, label, area, t, layers in area_only:       # no outline: pressed = net, loss not measurable
        elements.append({"piso": floor, "elemento": element, "espessura_mm": t, "camadas": layers, "pecas": 0, "bruto_m2": area, "vaos_m2": 0.0,
                         "liquido_m2": area, "liquido_m3": area * t / 1000})
        notes.append(f"{floor} · {element} {label}: sem contorno medido; conta pela área, sem perdas de corte.")

    nest_in = [clt_nesting.Piece(id=p["id"], length_m=p["comprimento_m"], width_m=p["largura_m"], thickness_mm=p["espessura_mm"],
                                 layers=p["camadas"], opening_area_m2=p["vaos_m2"]) for p in pieces]
    library = production_library(biblioteca)
    sale_item = biblioteca.get("VENDA-CLT") or {}
    sale_m3 = float(sale_item.get("sale_eur") or 0)

    plan = _nest(nest_in, press) if nest_in else None

    def scenario(fixed_format):
        """Pressed volume, losses and production cost. fixed_format: the pieces are cut from press blanks of the full
        format (layout from the nesting engine). Otherwise each piece is pressed as its own rectangle, so only what is
        cut out of it (windows, doors, stair, notches) is lost."""
        groups = {}
        for p in pieces:
            g = groups.setdefault((p["espessura_mm"], p["camadas"]), {"espessura_mm": p["espessura_mm"], "camadas": p["camadas"], "paineis_prensa": 0,
                                                                     "prensado_m2": 0.0, "liquido_m2": 0.0, "pecas": 0})
            g["liquido_m2"] += p["liquido_m2"]
            g["pecas"] += 1
            if not fixed_format:
                g["prensado_m2"] += p["bruto_m2"]
        if fixed_format:
            for x in plan["grupos"]:
                g = groups[(x["espessura_mm"], x["camadas"])]
                g["paineis_prensa"] = x["paineis"]
                g["prensado_m2"] = sum(b["comprimento_usado_m"] * b["largura_m"] for b in x["layout"])
        for _floor, _element, _label, area, t, layers in area_only:
            g = groups.setdefault((t, layers), {"espessura_mm": t, "camadas": layers, "paineis_prensa": 0, "prensado_m2": 0.0, "liquido_m2": 0.0, "pecas": 0})
            g["prensado_m2"] += area
            g["liquido_m2"] += area
        losses = []
        for key in sorted(groups):
            g = groups[key]
            t = g["espessura_mm"] / 1000
            losses.append({**{k: g[k] for k in ("espessura_mm", "camadas", "paineis_prensa", "pecas")},
                           "prensado_m2": round(g["prensado_m2"], 3), "prensado_m3": round(g["prensado_m2"] * t, 4),
                           "liquido_m3": round(g["liquido_m2"] * t, 4), "perda_m3": round((g["prensado_m2"] - g["liquido_m2"]) * t, 4),
                           "perda_percent": round((1 - g["liquido_m2"] / g["prensado_m2"]) * 100, 2) if g["prensado_m2"] else 0.0})
        net_m3 = sum(x["liquido_m3"] for x in losses)
        pressed_m3 = sum(x["prensado_m3"] for x in losses)
        factory = {"floors": [{"name": "Produção", "height_m": 3,
                               "panels": [{"kind": "parede", "label": f"CLT {x['espessura_mm']:g} mm", "thickness_mm": x["espessura_mm"],
                                           "layers": x["camadas"], "area_m2": round(x["prensado_m2"], 4)} for x in losses]}], "vat_regime": "pt"}
        r = estimate(EstimateInput.model_validate(factory), parametros, library)
        tot, row = r["total"], r["pisos"][0]
        cost = tot["custo_total_eur"]
        revenue = round(net_m3 * sale_m3, 2)                  # the company sells the CLT that goes into the house
        sale = {"venda_eur_m3": sale_m3, "venda_eur": revenue, "margem_eur": round(revenue - cost, 2) if sale_m3 else None,
                "margem_percent": round((revenue - cost) / revenue * 100, 2) if revenue else None,
                "venda_origem": sale_item.get("origin"), "venda_fonte": sale_item.get("source", "")}
        return {**sale, "perdas": losses, "clt_liquido_m3": round(net_m3, 3), "clt_prensado_m3": round(pressed_m3, 3),
                "perda_m3": round(pressed_m3 - net_m3, 3), "perda_percent": round((1 - net_m3 / pressed_m3) * 100, 2) if pressed_m3 else 0.0,
                "consumos": {"madeira_comprada_m3": row["madeira_comprada_m3"], "adesivo_kg": row["adesivo_kg"], "eletricidade_kwh": row["eletricidade_kwh"],
                             "horas_fabrico": tot["horas_fabrico"], "viagens_materia_prima": tot["viagens_materia_prima"]},
                "linhas": [l for l in r["linhas"] if l["fase"] != "venda"], "custo_producao_eur": cost,
                "custo_por_m3_liquido_eur": round(cost / net_m3, 2) if net_m3 else None,
                "custo_por_m3_prensado_eur": round(cost / pressed_m3, 2) if pressed_m3 else None, "_r": r}

    main = scenario(False)
    fixed = scenario(True) if plan else None
    # façade walls pressed as whole panels: the exterior openings that have no CLT lintel are then cut out of the panel too
    whole = None
    ext_open = [o for o in openings if o.get("exterior") and o.get("por_cima") != "lintel CLT"]
    ext_t = min((p["espessura_mm"] for p in pieces if p["elemento"] == "Paredes"), default=None)
    if ext_open and ext_t:
        extra_m2 = sum(o["area_m2"] for o in ext_open)
        # same pieces, plus the opening rectangles, which are pressed and entirely cut away
        save = [dict(p) for p in pieces]
        pieces.append({"id": "vaos-exteriores", "piso": "", "elemento": "Paredes", "rotulo": "vãos exteriores", "comprimento_m": extra_m2, "largura_m": 1.0,
                       "espessura_mm": ext_t, "camadas": next(p["camadas"] for p in pieces if p["espessura_mm"] == ext_t), "bruto_m2": extra_m2,
                       "vaos_m2": extra_m2, "liquido_m2": 0.0, "vaos": []})
        whole = scenario(False)
        whole["vaos_exteriores_m2"] = round(extra_m2, 2)
        pieces[:] = save
    r = main.pop("_r")
    if fixed:
        fixed.pop("_r")
    if whole:
        whole.pop("_r")
    labels = {v[1] for k, v in CATALOGUE.items() if k in PRODUCTION_PARAMS and parametros.get(k, {}).get("origin") == "hipotese"}
    hyp = sorted(h for h in r["hipoteses_por_confirmar"] if h in labels or any(h.startswith(l["codigo"] + " ·") for l in main["linhas"]))
    if sale_m3 and sale_item.get("origin") != "empresa":
        hyp.append(f"VENDA-CLT · preço de venda do CLT {sale_m3:g} €/m³: referência de mercado, não é o preço da empresa.")
    if not sale_m3:
        hyp.append("VENDA-CLT · a biblioteca não tem preço de venda do CLT: a venda e a margem não foram calculadas.")
    hyp += [f"Como a fábrica prensa: cada peça à sua medida (valor principal) ou painéis de formato fixo {press[0]:g} × {press[1]:g} m com corte de 10 mm (segundo cenário)."]
    return {"elementos": elements, "pecas": pieces, "vaos": openings, "verificacao": checks,
            "clt_liquido_m2": round(sum(e["liquido_m2"] for e in elements), 2), "clt_bruto_m2": round(sum(e["bruto_m2"] for e in elements), 2),
            "vaos_cortados_m2": round(sum(e["vaos_m2"] for e in elements), 2), "formato_prensa_m": list(press),
            **main, "formato_fixo": fixed, "fachadas_inteiras": whole, "hipoteses": hyp, "notas": notes, "placas": plate_log, "_desenhos": (staged, plan)}


def _piece_label(label, en):
    if not en:
        return label
    for pt, e in (("Laje", "Slab"), ("Cobertura", "Roof"), ("Lintel", "Lintel"), ("vão", "span"), ("Painel sobre porta", "Panel over door")):
        label = label.replace(pt, e)
    return label


def _plate_sheets(doc, q, title, n, en=False):
    """One A3 sheet per floor: the slab / roof outlines with every strip numbered and dimensioned (same numbers as the
    piece list), the cut-outs hatched."""
    import pymupdf
    W, H = 1190.55, 841.89
    for floor in dict.fromkeys(p["piso"] for p in q["placas"]):
        plates = [p for p in q["placas"] if p["piso"] == floor]
        strips = [p for p in q["pecas"] if p["piso"] == floor and p.get("ret_m")]
        pg = doc.new_page(width=W, height=H)
        pg.insert_text((30, 40), f"{title} · {floor} · " + ("CLT slab and roof: numbered strips, dimensions in m" if en else
                                                              "laje e cobertura CLT: faixas numeradas, cotas em m"), fontsize=13)
        pg.insert_text((30, 58), ("Each strip is a piece of the list (same number). Dashed: cut-out that is lost (stair, notches)." if en else
                                  "Cada faixa é uma peça da lista (mesmo número). Tracejado: recorte que se perde (escada, recantos)."), fontsize=8.5)
        cell = (W - 60) / len(plates)
        for i, plate in enumerate(plates):
            mine = [s for s in strips if s["elemento"] == plate["elemento"] and s["espessura_mm"] == plate["espessura_mm"]
                    and pymupdf.Rect(*s["ret_m"]).intersects(pymupdf.Rect(min(x for x, _y in plate["contorno_m"]), min(y for _x, y in plate["contorno_m"]),
                                                                           max(x for x, _y in plate["contorno_m"]), max(y for _x, y in plate["contorno_m"])))]
            xs = [x for x, _y in plate["contorno_m"]]
            ys = [y for _x, y in plate["contorno_m"]]
            k = min((cell - 50) / (max(xs) - min(xs)), (H - 150) / (max(ys) - min(ys)))
            ox, oy = 30 + i * cell + 20, 90
            T = lambda x, y: pymupdf.Point(ox + (x - min(xs)) * k, oy + (max(ys) - y) * k)
            pg.insert_text((ox, 82), f"{to_english(plate['elemento']) if en else plate['elemento']} {plate['espessura_mm']:g} mm", fontsize=10)
            for s in mine:
                x0, y0, x1, y1 = s["ret_m"]
                r = pymupdf.Rect(T(x0, y1), T(x1, y0))
                pg.draw_rect(r, color=(0.1, 0.35, 0.75), fill=(0.86, 0.92, 1.0), width=0.8)
                label = s["rotulo"].split(" · ")[0]
                text = f"{label}\n{n(s['comprimento_m'], 3)} × {n(s['largura_m'], 3)}"
                if r.width >= 62:
                    pg.insert_textbox(pymupdf.Rect(r.x0 + 2, (r.y0 + r.y1) / 2 - 12, r.x1 - 2, (r.y0 + r.y1) / 2 + 14), text, fontsize=7.5, align=1)
                else:                                        # narrow strip: the label runs along it
                    pg.insert_textbox(pymupdf.Rect((r.x0 + r.x1) / 2 - 12, r.y0 + 2, (r.x0 + r.x1) / 2 + 14, r.y1 - 2), text, fontsize=7.5, align=1, rotate=90)
                if s["vaos_m2"] > 0.005:
                    pg.insert_textbox(pymupdf.Rect(r.x0 + 2, r.y1 - 12, r.x1 - 2, r.y1 - 1), f"{'cut-out' if en else 'recorte'} {n(s['vaos_m2'], 2)} m²", fontsize=6.5,
                                      color=(0.7, 0, 0), align=1)
            pg.draw_polyline([T(x, y) for x, y in plate["contorno_m"]], color=(0, 0, 0), width=1.6)
            for void in plate["vazios_m"]:
                pts = [T(x, y) for x, y in void]
                pg.draw_polyline(pts, color=(0.8, 0, 0), width=1.0, dashes="[3 2] 0", fill=(1.0, 0.9, 0.9))
                c = pymupdf.Rect(min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts))
                pg.insert_textbox(pymupdf.Rect(c.x0, (c.y0 + c.y1) / 2 - 5, c.x1, (c.y0 + c.y1) / 2 + 8), "cut-out" if en else "recorte", fontsize=7, color=(0.7, 0, 0), align=1)


def note(entrada: dict, parametros: dict, biblioteca: dict, titulo: str | None = None, empresa: str | None = None,
         lingua: str = "pt", origem: str = "", notas: list | None = None, geometria: dict | None = None,
         cruzamento: list | None = None, imagens: bool = True) -> dict:
    import pymupdf
    from reportlab.lib.units import mm as W
    from engines.calc_lots import premium, rendu

    en = lingua == "en"
    _ = to_english if en else (lambda s: s)
    n = (lambda v, d=2: "—" if v is None else f"{float(v):,.{d}f}") if en else \
        (lambda v, d=2: "—" if v is None else f"{float(v):,.{d}f}".replace(",", " ").replace(".", ","))
    q = compute(entrada, parametros, biblioteca, geometria)

    def item(code, name):                                     # library item names and parameter labels in the dossier language
        from bim_studio import clt_i18n
        return (EN.get(name) or clt_i18n.item_name(code, name, "en", True)) if en else name

    def hyp_text(h):
        if not en:
            return h
        from bim_studio import clt_i18n
        code, sep, name = h.partition(" · ")
        if sep and code in biblioteca and not h.startswith("VENDA-CLT"):
            return f"{code} · {item(code, name)}"
        key = next((k for k, v in CATALOGUE.items() if v[1] == h), None)
        return EN.get(h) or (clt_i18n.param_label(key, h, "en", True) if key else _(h))

    def source_text(src):
        if not en:
            return src
        base, sep, why = str(src).partition(" (sem preço público")
        return _(base) + (" (no public price in Ukraine; the European reference is kept)" if sep else "")
    titre = titulo or ("CLT only" if en else "Só CLT")
    sub = _("Só CLT · quantidades exatas, perdas, custo de produção e venda")
    kp = [(_("CLT líquido"), n(q["clt_liquido_m3"], 3), "m³"), (_("CLT prensado"), n(q["clt_prensado_m3"], 3), "m³"),
          (_("Perdas de corte"), n(q["perda_percent"], 1), "%"), (_("Custo de produção"), n(q["custo_producao_eur"], 0), "€"),
          (_("Custo por m³ líquido"), n(q["custo_por_m3_liquido_eur"], 0), "€/m³")]
    # prices that are not the company's own are said loud and clear, at the top and next to every amount
    priced = q["linhas"] + ([{"origem": q["venda_origem"]}] if q["venda_eur_m3"] else [])
    foreign = [l for l in priced if l["origem"] != "empresa"]
    who = premium.marca(empresa)["nome"] if empresa and premium.marca(empresa) else ("the company" if en else "a empresa")
    warn = None
    if foreign:
        every = len(foreign) == len(priced)
        fact = (("none of the prices used is the company's own" if every else f"{len(foreign)} of the {len(priced)} prices used are not the company's own")
                if en else ("nenhum dos preços usados é da empresa" if every else f"{len(foreign)} dos {len(priced)} preços usados não são da empresa"))
        warn = ((f"FICTITIOUS PRICES. We do not have the price library of {who}: {fact}. They are market references and assumptions, used only to "
                 "show the method. The cost, sale and margin figures are NOT real until the company enters its prices in the library. Quantities, "
                 "openings and losses do not depend on prices.") if en else
                (f"PREÇOS FICTÍCIOS. Não temos a biblioteca de preços de {who}: {fact}. São referências de mercado e hipóteses, usadas só para "
                 "mostrar o método. Os valores de custo, venda e margem NÃO são reais enquanto a empresa não puser os seus preços na biblioteca. "
                 "As quantidades, os vãos e as perdas não dependem dos preços."))
        tag = " (fictitious prices)" if en else " (preços fictícios)"
        kp = [(a + tag if c.startswith("€") else a, b, c) for a, b, c in kp]
    B = [("kpis", [{"label": a, "value": b, "unit": c} for a, b, c in kp])]
    if warn:
        B.append(("hyp", [warn]))
    B.append(("h2", _("1. Âmbito e método")))
    B.append(("p", ("Only the CLT panels (walls, floor slab, roof, lintels, panels over doors) and the cost of producing them: timber, adhesive, factory "
                    "energy and water, line labour and timber freight to the factory, with the company's library. Windows and doors are measured only to "
                    "cut them out of the panels: gross m² is what is pressed, net m² is what stays in the house, the difference is the cutting loss, read "
                    "from the press layout. Excluded: steel or concrete structure, joinery, insulation, linings, services, finishes, transport to site, "
                    "erection, overheads, sale price and VAT.") if en else
              ("Só os painéis CLT (paredes, laje, cobertura, lintéis, painéis sobre portas) e o custo de os produzir: madeira, cola, energia e água da "
               "fábrica, mão de obra da linha e transporte da madeira até à fábrica, com a biblioteca da empresa. As janelas e portas são medidas só "
               "para as cortar nos painéis: m² bruto é o que se prensa, m² líquido é o que fica na casa, a diferença é a perda de corte, lida no plano "
               "de corte da prensa. Fora: estrutura de aço ou betão, caixilharia, isolamentos, revestimentos, instalações, acabamentos, transporte "
               "para a obra, montagem, custos indiretos, venda e IVA.")))
    if origem:
        B.append(("p", ("Geometry: " if en else "Geometria: ") + _(origem)))
    views = []
    if imagens:
        from bim_studio import clt_render
        import io
        from reportlab.platypus import Image
        views = clt_render.views(entrada, parametros, geometria)
        if views:
            B.append(("h2", "3D views of the assembled CLT" if en else "Vistas 3D do CLT montado"))
            B.append(("p", ("Only the CLT, as calculated: wall pieces with their openings cut out, lintels, slab and roof strips. No cladding, "
                            "joinery or finishes.") if en else
                      ("Só o CLT, tal como foi calculado: peças de parede com os vãos cortados, lintéis, faixas da laje e da cobertura. Sem "
                       "revestimentos, caixilharia nem acabamentos.")))
            names = {"frente": ("entrance side", "lado da entrada"), "tras": ("terrace side", "lado do terraço"), "cima": ("from above", "vista de cima")}
            for name, png in views:
                pix = pymupdf.Pixmap(png)
                width = 170 * W
                B.append(("figure", Image(io.BytesIO(png), width=width, height=width * pix.height / pix.width), names.get(name, (name, name))[0 if en else 1]))
    build = lambda e: f"{n(e['espessura_mm'], 0)} mm · {e['camadas']} {_('camadas')}"
    B.append(("h2", _("2. Quantidades CLT por elemento")))
    rows = [[e["piso"], _(e["elemento"]), build(e), str(e["pecas"] or "—"), n(e["bruto_m2"], 3), n(e["vaos_m2"], 3), n(e["liquido_m2"], 3), n(e["liquido_m3"], 3)]
            for e in q["elementos"]]
    rows.append([_("Total"), "", "", str(len(q["pecas"])), n(q["clt_bruto_m2"], 3), n(q["vaos_cortados_m2"], 3), n(q["clt_liquido_m2"], 3), n(q["clt_liquido_m3"], 3)])
    B.append(("table", [_("Piso"), _("Elemento"), _("Painel"), _("Peças"), _("Bruto m²"), _("Vãos m²"), _("Líquido m²"), _("Líquido m³")], rows,
              [14 * W, 36 * W, 32 * W, 13 * W, 22 * W, 20 * W, 22 * W, 21 * W]))
    if q["vaos"]:
        B.append(("h2", _("3. Vãos (janelas e portas)")))
        B.append(("table", [_("Piso"), _("Tipo"), _("Largura (m)"), _("Altura (m)"), _("Área (m²)"), _("Por cima")],
                  [[o["piso"], _(o["tipo"]) if en else o["tipo"].replace("vao_envidracado", "vão envidraçado"), n(o["largura_m"]), n(o["altura_m"], 3), n(o["area_m2"], 3), _(o["por_cima"])] for o in q["vaos"]]
                  + [[_("Total"), "", "", "", n(sum(o["area_m2"] for o in q["vaos"]), 3), ""]],
                  [16 * W, 34 * W, 26 * W, 26 * W, 26 * W, 52 * W]))
    B.append(("h2", _("4. Perdas de corte na prensa")))
    B.append(("table", [_("Painel"), _("Peças"), _("Prensado m³"), _("Líquido m³"), _("Perda m³"), _("Perda %")],
              [[build(x), str(x["pecas"]), n(x["prensado_m3"], 3), n(x["liquido_m3"], 3), n(x["perda_m3"], 3), n(x["perda_percent"], 1)]
               for x in q["perdas"]] + [[_("Total"), str(len(q["pecas"])), n(q["clt_prensado_m3"], 3), n(q["clt_liquido_m3"], 3), n(q["perda_m3"], 3),
                                         n(q["perda_percent"], 1)]], [44 * W, 20 * W, 30 * W, 30 * W, 28 * W, 28 * W]))
    B.append(("p", ("Each piece is pressed as its own rectangle; the loss is what is cut out of it: windows and doors under CLT lintels, the stair "
                    "opening and the notches of the slab and roof.") if en else
              ("Cada peça é prensada no seu retângulo; a perda é o que se corta dela: janelas e portas sob lintel CLT, a abertura da escada e os "
               "recortes da laje e da cobertura.")))
    fx = q["formato_fixo"]
    if fx:
        wf = q["fachadas_inteiras"]
        B.append(("table", ["Scenario" if en else "Cenário", _("Painéis de prensa"), _("Prensado m³"), _("Perda m³"), _("Perda %"), _("Custo (€)"), "€/m³"],
                  [["Pieces pressed to measure" if en else "Peças prensadas à medida", "—", n(q["clt_prensado_m3"], 3), n(q["perda_m3"], 3), n(q["perda_percent"], 1),
                    n(q["custo_producao_eur"]), n(q["custo_por_m3_liquido_eur"])],
                   [(f"Fixed blanks {q['formato_prensa_m'][0]:g} × {q['formato_prensa_m'][1]:g} m, 10 mm kerf" if en else
                     f"Painéis fixos {q['formato_prensa_m'][0]:g} × {q['formato_prensa_m'][1]:g} m, corte 10 mm"), str(sum(x["paineis_prensa"] for x in fx["perdas"])),
                    n(fx["clt_prensado_m3"], 3), n(fx["perda_m3"], 3), n(fx["perda_percent"], 1), n(fx["custo_producao_eur"]), n(fx["custo_por_m3_liquido_eur"])]]
                  + ([[("Whole façade panels, every exterior opening cut out" if en else "Fachadas em painéis inteiros, todos os vãos exteriores cortados"), "—",
                       n(wf["clt_prensado_m3"], 3), n(wf["perda_m3"], 3), n(wf["perda_percent"], 1), n(wf["custo_producao_eur"]), n(wf["custo_por_m3_liquido_eur"])]]
                     if wf else []),
                  [52 * W, 22 * W, 24 * W, 22 * W, 18 * W, 24 * W, 18 * W]))
        B.append(("p", ("The second line is the layout of every piece on full-format press blanks (cutting plan in the annex). The third assumes the "
                        "façade walls are pressed as whole panels, so the windows and bays with no CLT lintel are cut out of them as well "
                        f"({n(wf['vaos_exteriores_m2']) if wf else '—'} m² of openings). The company states which is its way of pressing; €/m³ is per net m³ in the house.") if en else
                  ("A segunda linha é o plano de corte de todas as peças em painéis de prensa de formato inteiro (no anexo). A terceira assume que as "
                   "fachadas são prensadas em painéis inteiros, e que as janelas e vãos sem lintel CLT também são cortados deles "
                   f"({n(wf['vaos_exteriores_m2']) if wf else '—'} m² de vãos). A empresa indica qual é a sua forma de prensar; €/m³ é por m³ líquido na casa.")))
    if q["verificacao"]:
        B.append(("h2", _("5. Verificação cruzada")))
        B.append(("table", [_("Piso"), "Troços medidos m³" if not en else "Measured runs m³", "Peças (bruto) m³" if not en else "Pieces (gross) m³",
                            "União da planta m³" if not en else "Plan union m³", "OK"],
                  [[c["piso"], n(c["trocos_medidos_m3"], 3), n(c["pecas_bruto_m3"], 3), n(c["uniao_planta_m3"], 3), "OK" if c["ok"] else "DIVERGE"]
                   for c in q["verificacao"]], [20 * W, 40 * W, 40 * W, 40 * W, 25 * W]))
    if cruzamento:
        B.append(("h2", "Cross-check with what is written on the plans" if en else "Cruzamento com o que está escrito nos planos"))
        B.append(("table", ["Item", "Written on the plans" if en else "Escrito nos planos", "Measured / used" if en else "Medido / usado", "OK"],
                  [[_(r["item"]), _(r["escrito"]), _(r["usado"]) + (f" — {_(r['nota'])}" if r["nota"] else ""),
                    "OK" if r["ok"] else ("DIFFERS" if en else "DIVERGE")] for r in cruzamento],
                  [42 * W, 50 * W, 70 * W, 18 * W]))
    c = q["consumos"]
    B.append(("h2", _("6. Consumos de produção")))
    B.append(("table", [_("Designação"), _("Quantidade")],
              [[_("CLT prensado"), f"{n(q['clt_prensado_m3'], 3)} m³"], [_("Madeira comprada"), f"{n(c['madeira_comprada_m3'], 3)} m³"],
               [_("Cola"), f"{n(c['adesivo_kg'])} kg"], [_("Eletricidade"), f"{n(c['eletricidade_kwh'], 0)} kWh"],
               [_("Horas de fabrico"), f"{n(c['horas_fabrico'])} h"], [_("Viagens de madeira"), str(c["viagens_materia_prima"])]], [100 * W, 60 * W]))
    B.append(("h2", _("7. Custo de produção")))
    if warn:
        B.append(("hyp", [warn]))
    B.append(("table", [_("Código"), _("Designação"), _("Quantidade"), _("Unidade"), _("Preço unitário (€)"), _("Custo (€)"), _("Origem")],
              [[l["codigo"], item(l["codigo"], l["designacao"]), n(l["quantidade"], 3), l["unidade"], n(l["custo_unitario_eur"], 4), n(l["custo_eur"]), _(l["origem"])]
               for l in q["linhas"]] + [["", _("Total"), "", "", "", n(q["custo_producao_eur"]), ""]],
              [26 * W, 58 * W, 20 * W, 14 * W, 22 * W, 22 * W, 18 * W]))
    B.append(("p", (f"Per net m³ (in the house): {n(q['custo_por_m3_liquido_eur'])} €/m³ · per pressed m³: {n(q['custo_por_m3_prensado_eur'])} €/m³." if en else
                    f"Por m³ líquido (na casa): {n(q['custo_por_m3_liquido_eur'])} €/m³ · por m³ prensado: {n(q['custo_por_m3_prensado_eur'])} €/m³.")))
    if q["venda_eur_m3"]:
        B.append(("h2", "Sale and margin" if en else "Venda e margem"))
        if warn:
            B.append(("hyp", [warn.split(". ")[0] + (": see the notice in the production cost section." if en else ": ver o aviso na secção do custo de produção.")]))
        rows_v = [[("Pieces pressed to measure" if en else "Peças prensadas à medida"), n(q["clt_liquido_m3"], 3), n(q["venda_eur_m3"]), n(q["venda_eur"]),
                   n(q["custo_producao_eur"]), n(q["margem_eur"]), n(q["margem_percent"], 1)]]
        if fx:
            rows_v.append([("Fixed press blanks" if en else "Painéis de prensa fixos"), n(fx["clt_liquido_m3"], 3), n(fx["venda_eur_m3"]), n(fx["venda_eur"]),
                           n(fx["custo_producao_eur"]), n(fx["margem_eur"]), n(fx["margem_percent"], 1)])
        B.append(("table", ["Scenario" if en else "Cenário", "m³ sold" if en else "m³ vendidos", "€/m³", "Sale (€)" if en else "Venda (€)",
                            "Production cost (€)" if en else "Custo de produção (€)", "Margin (€)" if en else "Margem (€)", "%"], rows_v,
                  [44 * W, 22 * W, 18 * W, 26 * W, 30 * W, 24 * W, 16 * W]))
        B.append(("p", (("Sale price from the library: " if en else "Preço de venda da biblioteca: ")
                        + ("company price" if en and q["venda_origem"] == "empresa" else "preço da empresa" if q["venda_origem"] == "empresa"
                           else ("market reference — " if en else "referência de mercado — ") + source_text(q["venda_fonte"]))
                        + (". Margin over the production cost only: transport to site, erection and overheads are not in it." if en else
                           ". Margem só sobre o custo de produção: transporte para a obra, montagem e custos indiretos não estão incluídos."))))
    B.append(("h2", _("8. Lista de peças")))
    B.append(("table", [_("Piso"), _("Peça"), _("Comp. (m)"), _("Larg. (m)"), _("Esp. (mm)"), _("Bruto m²"), _("Vãos m²"), _("Líquido m²")],
              [[p["piso"], f"{_(p['elemento'])} · {_piece_label(p['rotulo'], en)}"[:46], n(p["comprimento_m"], 3), n(p["largura_m"], 3), n(p["espessura_mm"], 0),
                n(p["bruto_m2"], 3), n(p["vaos_m2"], 3), n(p["liquido_m2"], 3)] for p in q["pecas"]],
              [13 * W, 62 * W, 19 * W, 19 * W, 17 * W, 18 * W, 16 * W, 18 * W]))
    for t in (notas or []) + q["notas"]:
        B.append(("p", _(t)))
    labels = __import__("engines.calc_lots.lingua_ucrania", fromlist=["EN_RENDU"]).EN_RENDU if en else None
    body_pdf = rendu.build_pdf(titre, sub, B + [("h2", _("Valores a confirmar pela empresa")), ("hyp", [hyp_text(h) for h in q["hipoteses"]] or [_("nenhum")])],
                               footer=_("ConstruPilot — nota de cálculo gerada por motor determinístico; a validar pelo projetista / técnico responsável antes da execução."),
                               lang=labels)
    doc = pymupdf.open(stream=body_pdf, filetype="pdf")
    png = doc[0].get_pixmap(dpi=110).tobytes("png")
    n_note = len(doc)
    staged, plan = q.pop("_desenhos")
    if staged:                                               # dimensioned plan, piece elevations and cutting plan: where every figure comes from
        from bim_studio import clt_drawings, clt_i18n, clt_study
        token = clt_study._LANG.set("en" if en else "pt")
        try:
            drawings = clt_drawings.build(staged, plan, title=titre, tr=(lambda t: clt_i18n.tr(t, "en")) if en else None)
            doc.insert_pdf(clt_study._annex_pages(drawings, titre))
        finally:
            clt_study._LANG.reset(token)
        body_pdf = doc.tobytes()
    capa = {"titulo": titre, "subtitulo": sub, "local": "", "data": "", "kpis": kp, "indice": [], "miniatura_pagina": None, "capa_imagem": None}
    if q["placas"]:
        doc = pymupdf.open(stream=body_pdf, filetype="pdf")
        _plate_sheets(doc, q, titre, n, en)
        body_pdf = doc.tobytes()
    pdf = premium.embelezar(body_pdf, capa, premium.marca(empresa) if empresa else None, n_nota=n_note)
    resumo = [f"{titre}: CLT líquido {n(q['clt_liquido_m3'], 3)} m³ ({n(q['clt_liquido_m2'])} m²; bruto {n(q['clt_bruto_m2'])} m² menos {n(q['vaos_cortados_m2'])} m² de vãos cortados). "
              f"Prensado {n(q['clt_prensado_m3'], 3)} m³, perdas de corte {n(q['perda_m3'], 3)} m³ ({n(q['perda_percent'], 1)} %). "
              f"Custo de produção {n(q['custo_producao_eur'])} € ({n(q['custo_por_m3_liquido_eur'])} €/m³ líquido)."]
    resumo += [f"{e['piso']} · {e['elemento']} {n(e['espessura_mm'], 0)} mm: líquido {n(e['liquido_m2'], 3)} m², {n(e['liquido_m3'], 3)} m³" for e in q["elementos"]]
    if q["venda_eur_m3"]:
        resumo.append(f"Venda: {n(q['clt_liquido_m3'], 3)} m³ × {n(q['venda_eur_m3'])} €/m³ = {n(q['venda_eur'])} €; margem sobre o custo de produção "
                      f"{n(q['margem_eur'])} € ({n(q['margem_percent'], 1)} %). Preço de venda: "
                      + ("da empresa." if q["venda_origem"] == "empresa" else "referência de mercado, a confirmar pela empresa."))
    else:
        resumo.append("Venda não calculada: a biblioteca da empresa não tem preço de venda do CLT.")
    resumo.append("Custo: " + "; ".join(f"{l['designacao']} {n(l['quantidade'], 2)} {l['unidade']} → {n(l['custo_eur'])} €" for l in q["linhas"]))
    resumo += [f"Verificação {c_['piso']}: troços {n(c_['trocos_medidos_m3'], 3)} m³, peças {n(c_['pecas_bruto_m3'], 3)} m³, união {n(c_['uniao_planta_m3'], 3)} m³ "
               f"({'OK' if c_['ok'] else 'DIVERGE'})" for c_ in q["verificacao"]]
    if foreign:
        resumo.insert(1, "PREÇOS FICTÍCIOS: a biblioteca não tem os preços da empresa" + ("" if len(foreign) == len(priced) else f" em {len(foreign)} de {len(priced)} linhas")
                      + "; custo, venda e margem servem só para mostrar o método e têm de ser ditos como fictícios ao utilizador.")
    resumo.append("Âmbito: só CLT. Sem estrutura, caixilharia, isolamentos, acabamentos, transporte para a obra, montagem, venda nem IVA.")
    resumo.append("Valores ainda por confirmar pela empresa: " + "; ".join(q["hipoteses"]))
    data = {k: q[k] for k in ("clt_liquido_m3", "clt_liquido_m2", "clt_bruto_m2", "vaos_cortados_m2", "clt_prensado_m3", "perda_m3", "perda_percent",
                              "custo_producao_eur", "custo_por_m3_liquido_eur", "venda_eur", "margem_eur", "margem_percent")}
    data["verificacao_ok"] = all(c_["ok"] for c_ in q["verificacao"]) if q["verificacao"] else None
    return {"titre": titre, "pdf": pdf, "png": png, "resumo": resumo, "data": data, "q": q, "vistas": views}
