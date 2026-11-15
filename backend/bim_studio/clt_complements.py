"""Approximate complements of the complete CLT study: what a finished house needs and the library does not price yet
(ventilation, heating, covered terrace, roof edges, stair, connectors) and the build-ups of the section split layer by
layer. Requested by Martinho on 14/11/2026: «calcula tudo aproximado e mete no cálculo completo».

Every line is an APPROXIMATION and says so: the quantity comes from the measured areas, lengths and rooms of the study
with a stated rule; the unit price is a placeholder the company replaces. Nothing here changes clt_economics.estimate:
the complements are shown in their own chapter and added to the totals there.
"""
from __future__ import annotations

import math

SALE = 1.15            # same cost → sale ratio as the placeholder items of the library

WET, DRY = ("casa_de_banho", "cozinha", "lavandaria"), ("sala", "quarto", "escritorio")


def _f(v):
    return float(v or 0)


def lines(entrada: dict, *, terrace_m2: float = 0.0, roof_edge_m: float = 0.0, storeys_above_ground: int | None = None,
          ligacoes: list[dict] | None = None) -> list[dict]:
    """entrada: the EstimateInput JSON of the study. Returns [{capitulo, nome{pt,en}, quantidade, unidade, custo_un, regra{pt,en}, so_quantidade}].
    so_quantidade: a layer already priced inside a combined line of the study (shown for the material list, cost 0).
    ligacoes: the connector lines counted piece by piece (clt_ligacoes.linhas) when the wall axes and the slab strips are
    measured; they then replace the ratio lines of the connectors chapter."""
    floors = entrada["floors"]
    rooms = [r for fl in floors for r in fl.get("rooms") or []]
    wet = sum(1 for r in rooms if r["tipo"] in WET) + sum(1 for r in rooms if r["tipo"] == "sala" and "lava_loica" in (r.get("aparelhos") or []))
    dry = sum(1 for r in rooms if r["tipo"] in DRY)
    useful = sum(_f(r["area_m2"]) for r in rooms if r["tipo"] != "exterior")
    roof = sum(_f(fl.get("roof_buildup_m2")) for fl in floors)
    slab = sum(_f(fl.get("slab_buildup_m2")) for fl in floors)
    facade = sum(_f(fl.get("facade_m2")) for fl in floors)
    ceiling = sum(_f(fl.get("ceiling_m2")) for fl in floors)
    wall_m = sum(_f(w["length_m"]) for fl in floors for w in fl.get("walls") or [])
    storeys = storeys_above_ground or len(floors)
    out = []

    def add(chapter, pt, en, qty, unit, cost, rule_pt, rule_en, only_quantity=False):
        if qty and qty > 0:
            qty = math.ceil(qty - 1e-9) if unit == "un" else qty                # whole pieces
            out.append({"capitulo": chapter, "nome": {"pt": pt, "en": en}, "quantidade": round(qty, 2), "unidade": unit, "custo_un": 0.0 if only_quantity else cost,
                        "regra": {"pt": rule_pt, "en": rule_en}, "so_quantidade": only_quantity})

    # ventilation (not drawn; the plans only note the ventilation riser)
    terminals = wet + dry
    add("vmc", "Unidade de ventilação mecânica (tipo a definir)", "Mechanical ventilation unit (type to be defined)", 1, "un", 1800,
        "1 por casa", "1 per house")
    add("vmc", "Bocas de extração (zonas húmidas)", "Extract terminals (wet rooms)", wet, "un", 45, "1 por casa de banho, cozinha e lavandaria", "1 per bathroom, kitchen and laundry")
    add("vmc", "Bocas de insuflação / entradas de ar (salas e quartos)", "Supply terminals / air inlets (living rooms and bedrooms)", dry, "un", 45,
        "1 por sala e quarto", "1 per living room and bedroom")
    add("vmc", "Condutas de ventilação isoladas, com acessórios", "Insulated ventilation ducts with fittings", terminals * 6.0, "m", 14,
        "6 m por boca (aproximação: sem traçado no plano)", "6 m per terminal (approximation: no routing on the plans)")
    add("vmc", "Saída de cobertura e tomada de ar exterior", "Roof outlet and outdoor air intake", 2, "un", 150, "1 saída + 1 tomada", "1 outlet + 1 intake")
    # heating (not drawn)
    add("aquecimento", "Aquecimento da casa (sistema a definir: piso radiante ou radiadores, com bomba de calor)",
        "House heating (system to be defined: underfloor or radiators, with heat pump)", useful, "m²", 75,
        "área útil das divisões", "useful area of the rooms")
    # flat roof, layer by layer (section: PVC, gravel, lightweight concrete to falls, XPS 100, vapour membrane)
    for pt, en, k, unit, rp, re_ in (
            ("Membrana de impermeabilização em PVC", "PVC waterproofing membrane", 1.10, "m²", "área da cobertura + 10 % de remates e sobreposições", "roof area + 10 % for upstands and laps"),
            ("Seixo rolado de proteção", "Rolled gravel ballast", 0.05, "m³", "área × 5 cm (espessura não cotada)", "area × 5 cm (thickness not dimensioned)"),
            ("Betão leve de pendentes (± 100 mm)", "Lightweight concrete to falls (± 100 mm)", 0.10, "m³", "área × 10 cm médios", "area × 10 cm average"),
            ("Painel XPS 100 mm", "XPS board 100 mm", 1.05, "m²", "área + 5 % de cortes", "area + 5 % cutting"),
            ("Membrana pára-vapor", "Vapour control membrane", 1.10, "m²", "área + 10 % de sobreposições", "area + 10 % laps")):
        add("cobertura", pt, en, roof * k, unit, 0, rp, re_, True)
    add("cobertura", "Rufo de platibanda em chapa lacada", "Parapet capping in coated steel", roof_edge_m, "m", 38, "perímetro das coberturas", "perimeter of the roofs")
    add("cobertura", "Ralos de cobertura com tubo de queda", "Roof outlets with downpipe", max(2, round(roof / 80)) if roof else 0, "un", 220,
        "1 por 80 m², mínimo 2", "1 per 80 m², at least 2")
    # floor build-up on the CLT slab (section: acoustic membrane, lightweight concrete 100 mm)
    add("laje", "Membrana acústica compactada", "Compacted acoustic membrane", slab * 1.05, "m²", 0, "área da laje + 5 %", "slab area + 5 %", True)
    add("laje", "Betão leve 100 mm", "Lightweight concrete 100 mm", slab * 0.10, "m³", 0, "área × 10 cm", "area × 10 cm", True)
    # façade, layer by layer (section: mineral wool 100 mm, vapour membrane, wind barrier)
    add("fachada", "Lã mineral 100 mm", "Mineral wool 100 mm", facade * 1.05, "m²", 0, "face exterior das paredes + 5 %", "outer face of the walls + 5 %", True)
    add("fachada", "Membrana de vapor / corta-vento", "Vapour membrane / wind barrier", facade * 1.10, "m²", 0, "face exterior + 10 % de sobreposições", "outer face + 10 % laps", True)
    add("fachada", "Estrutura de fixação do revestimento exterior (ripado)", "Battens for the exterior cladding", facade / 0.6, "m", 2.2,
        "1 ripa a cada 60 cm", "1 batten every 60 cm")
    # interior linings (section: BA13 double on metal profile 48 mm with acoustic insulation)
    board = sum(_f(fl.get("board_layers_m2")) for fl in floors) / 2
    add("interior", "Perfis metálicos 48 mm das contra-paredes", "48 mm metal studs of the wall linings", board / 0.6, "m", 1.9, "1 montante a cada 60 cm de face forrada", "1 stud every 60 cm of lined face")
    add("interior", "Isolamento acústico em lã de rocha nas contra-paredes", "Rock-wool acoustic insulation in the wall linings", board, "m²", 6.5, "faces forradas", "lined faces")
    add("interior", "Membrana de base das paredes (corte de capilaridade)", "Wall-base membrane (capillary break)", wall_m, "m", 4.5, "comprimento das paredes CLT", "length of the CLT walls")
    # connectors (section: angle brackets for shear and tension, perforated plates, M16 bars, wood screws)
    if ligacoes:                                              # counted connector by connector from the measured geometry
        out.extend(ligacoes)
    else:                                                     # no wall axes measured: stated ratios
        add("ligacoes", "Cantoneiras de corte parede–base e parede–laje", "Shear angle brackets wall–base and wall–slab", wall_m * 1.0, "un", 9, "1 por metro de parede", "1 per metre of wall")
        add("ligacoes", "Ancoragens de tração (hold-down) com varão M16", "Hold-downs with M16 rod", wall_m / 3.0, "un", 28, "1 por 3 m de parede", "1 per 3 m of wall")
        add("ligacoes", "Parafusos de madeira estruturais", "Structural wood screws", (roof + slab) * 4 + wall_m * 6, "un", 0.45,
            "4 por m² de laje e cobertura + 6 por metro de parede", "4 per m² of slab and roof + 6 per metre of wall")
        add("ligacoes", "Fita de estanquidade ao ar nas juntas", "Air-tightness tape on the joints", wall_m * 2 + (roof + slab) / 2.4, "m", 1.6,
            "2 × comprimento das paredes + juntas das faixas", "2 × wall length + strip joints")
    # covered terrace and stair
    add("terraco", "Deck de madeira do terraço coberto, com estrutura", "Timber deck of the covered terrace, with substructure", terrace_m2, "m²", 95, "área medida do terraço", "measured terrace area")
    add("terraco", "Impermeabilização sob o deck do terraço", "Waterproofing under the terrace deck", terrace_m2 * 1.10, "m²", 24, "área + 10 % de remates", "area + 10 % upstands")
    add("escada", "Escada interior de madeira entre pisos", "Interior timber stair between floors", max(0, storeys - 1), "un", 3500, "1 por piso acima do rés-do-chão", "1 per floor above ground")
    add("interior", "Teto falso: perfis e suspensões", "Suspended ceiling: profiles and hangers", ceiling, "m²", 0, "área de teto falso", "suspended ceiling area", True)
    return out


CHAPTERS = {"vmc": ("Ventilação mecânica", "Mechanical ventilation"), "aquecimento": ("Aquecimento", "Heating"),
            "cobertura": ("Cobertura plana, camada a camada", "Flat roof, layer by layer"), "laje": ("Pavimento sobre a laje CLT", "Floor build-up on the CLT slab"),
            "fachada": ("Fachada, camada a camada", "Façade, layer by layer"), "interior": ("Forros interiores", "Interior linings"),
            "ligacoes": ("Ligações e estanquidade ao ar", "Connectors and air-tightness"), "terraco": ("Terraço coberto", "Covered terrace"),
            "escada": ("Escada", "Stair")}


def totals(rows: list[dict]) -> dict:
    cost = sum(r["quantidade"] * r["custo_un"] for r in rows)
    return {"custo_eur": round(cost, 2), "venda_eur": round(cost * SALE, 2)}
