"""Construction systems and their quantity rules, the same for every company and every country.

The wall network (rede.py) gives the measured geometry of every wall: net and gross faces, openings, volume,
junctions and pieces. Each system turns that geometry into the quantities its trades buy and price. A rule only
multiplies measured geometry by parameters; every parameter has an origin:

- "standard": rule of the method when the plan is silent (heights RDC 3.00 m, other floors 2.50 m, opening head 2.10 m);
- "fabricante": published format of a product, with its source;
- "hipotese": default value to be confirmed by the company (editable, never presented as measured);
- "empresa": value set by the company in its parameters (replaces the default).

A quantity is "medido" when it comes only from the drawing, "regra" when it is measured geometry times a published
or company value, and "estimativa" as soon as one input is a hypothesis, a standard height or an inferred opening.

Out of scope, as for the CLT pilot: load calculations, footings and structural design. The steel ratio of a concrete
wall is a hypothesis for pricing, not a reinforcement design.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------------------------------------------
# Parameters

STANDARD_HEIGHTS = {
    "altura_standard_rdc_m": {"valor": 3.00, "unidade": "m", "origem": "standard", "grupo": "geometria",
                              "fonte": "regra ConstruPilot quando a planta não indica alturas: RDC 3,00 m"},
    "altura_standard_pisos_m": {"valor": 2.50, "unidade": "m", "origem": "standard", "grupo": "geometria",
                                "fonte": "regra ConstruPilot quando a planta não indica alturas: outros pisos 2,50 m"},
    "altura_vao_standard_m": {"valor": 2.10, "unidade": "m", "origem": "standard", "grupo": "geometria",
                              "fonte": "altura de vão standard quando a cota «LxH» não está escrita (mesma regra do leitor CLT)"},
    "vao_inferido_min_m": {"valor": 0.60, "unidade": "m", "origem": "hipotese", "grupo": "geometria",
                           "fonte": "menor intervalo entre troços lido como vão"},
    "vao_inferido_max_m": {"valor": 3.00, "unidade": "m", "origem": "hipotese", "grupo": "geometria",
                           "fonte": "maior intervalo entre troços lido como vão"},
    "tolerancia_verificacao_pct": {"valor": 2.0, "unidade": "%", "origem": "standard", "grupo": "geometria",
                                   "fonte": "erro máximo aceite entre dois métodos independentes"},
}

SYSTEMS = {
    "clt": {
        "nome": "CLT (painéis de madeira lamelada-colada cruzada)",
        "prefabricado": True,
        "parametros": {
            "clt_comprimento_max_m": {"valor": 18.0, "unidade": "m", "origem": "fabricante",
                                      "fonte": "Rezult, características técnicas (clt-rezult.com/en/technical-characteristics), lido em 2026-11-11"},
            "clt_largura_max_m": {"valor": 3.5, "unidade": "m", "origem": "fabricante",
                                  "fonte": "Rezult, características técnicas (clt-rezult.com/en/technical-characteristics), lido em 2026-11-11"},
            "clt_camadas": {"valor": 5, "unidade": "un", "origem": "hipotese", "fonte": "camadas por omissão quando a legenda não as indica"},
        },
    },
    "alvenaria_tijolo": {
        "nome": "Alvenaria de tijolo",
        "parametros": {
            "unidade_comprimento_mm": {"valor": 300, "unidade": "mm", "origem": "hipotese", "fonte": "formato do tijolo 30×20 (confirmar no catálogo do fabricante)"},
            "unidade_altura_mm": {"valor": 200, "unidade": "mm", "origem": "hipotese", "fonte": "formato do tijolo 30×20 (confirmar no catálogo do fabricante)"},
            "junta_mm": {"valor": 10, "unidade": "mm", "origem": "hipotese", "fonte": "junta de argamassa corrente"},
            "perdas_pct": {"valor": 5.0, "unidade": "%", "origem": "hipotese", "fonte": "quebras e cortes"},
            "argamassa_l_m2": {"valor": 15.0, "unidade": "L/m²", "origem": "hipotese", "fonte": "consumo de argamassa de assentamento (confirmar)"},
            "apoio_lintel_m": {"valor": 0.20, "unidade": "m", "origem": "hipotese", "fonte": "entrega do lintel de cada lado do vão"},
            "faces_revestidas": {"valor": 2, "unidade": "un", "origem": "hipotese", "fonte": "reboco/estuque nas duas faces"},
        },
    },
    "alvenaria_bloco": {
        "nome": "Alvenaria de bloco de betão",
        "parametros": {
            "unidade_comprimento_mm": {"valor": 500, "unidade": "mm", "origem": "hipotese", "fonte": "formato do bloco 50×20 (confirmar no catálogo do fabricante)"},
            "unidade_altura_mm": {"valor": 200, "unidade": "mm", "origem": "hipotese", "fonte": "formato do bloco 50×20 (confirmar no catálogo do fabricante)"},
            "junta_mm": {"valor": 10, "unidade": "mm", "origem": "hipotese", "fonte": "junta de argamassa corrente"},
            "perdas_pct": {"valor": 5.0, "unidade": "%", "origem": "hipotese", "fonte": "quebras e cortes"},
            "argamassa_l_m2": {"valor": 12.0, "unidade": "L/m²", "origem": "hipotese", "fonte": "consumo de argamassa de assentamento (confirmar)"},
            "apoio_lintel_m": {"valor": 0.20, "unidade": "m", "origem": "hipotese", "fonte": "entrega do lintel de cada lado do vão"},
            "faces_revestidas": {"valor": 2, "unidade": "un", "origem": "hipotese", "fonte": "reboco/estuque nas duas faces"},
        },
    },
    "betao_armado": {
        "nome": "Parede de betão armado",
        "parametros": {
            "aco_kg_m3": {"valor": 80.0, "unidade": "kg/m³", "origem": "hipotese",
                          "fonte": "taxa de armadura para orçamento; não é cálculo estrutural (fora do âmbito)"},
            "perdas_betao_pct": {"valor": 3.0, "unidade": "%", "origem": "hipotese", "fonte": "perdas de betonagem"},
        },
    },
    "ossatura_madeira": {
        "nome": "Ossatura de madeira",
        "prefabricado": True,
        "parametros": {
            "entre_eixo_m": {"valor": 0.60, "unidade": "m", "origem": "hipotese", "fonte": "afastamento dos montantes"},
            "faces_placa": {"valor": 2, "unidade": "un", "origem": "hipotese", "fonte": "placas (OSB/gesso) nas duas faces"},
            "comprimento_max_m": {"valor": 12.0, "unidade": "m", "origem": "hipotese", "fonte": "comprimento máximo de painel na mesa de pré-fabricação"},
        },
    },
    "ossatura_metalica": {
        "nome": "Ossatura metálica leve (LSF)",
        "prefabricado": True,
        "parametros": {
            "entre_eixo_m": {"valor": 0.60, "unidade": "m", "origem": "hipotese", "fonte": "afastamento dos montantes"},
            "faces_placa": {"valor": 2, "unidade": "un", "origem": "hipotese", "fonte": "placas nas duas faces"},
            "comprimento_max_m": {"valor": 12.0, "unidade": "m", "origem": "hipotese", "fonte": "comprimento máximo de painel"},
        },
    },
    "divisoria_gesso": {
        "nome": "Divisória de gesso cartonado",
        "parametros": {
            "entre_eixo_m": {"valor": 0.60, "unidade": "m", "origem": "hipotese", "fonte": "afastamento dos montantes"},
            "placas_por_face": {"valor": 1, "unidade": "un", "origem": "hipotese", "fonte": "uma placa por face"},
        },
    },
}


def defaults():
    """Every parameter with its default value and origin, keyed "sistema.chave" (or "geral.chave")."""
    out = {f"geral.{k}": dict(v) for k, v in STANDARD_HEIGHTS.items()}
    for sid, sysdef in SYSTEMS.items():
        for k, v in sysdef["parametros"].items():
            out[f"{sid}.{k}"] = {**v, "grupo": sid}
    return out


def merged(company: dict | None):
    """Defaults overlaid with the company's values. A company value keeps its own source and becomes "empresa"."""
    out = defaults()
    for key, value in (company or {}).items():
        if key not in out:
            continue
        if isinstance(value, dict):
            v = value.get("valor")
            fonte = value.get("fonte") or "valor da empresa"
        else:
            v, fonte = value, "valor da empresa"
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError(f"Valor inválido para {key}.")
        out[key] = {**out[key], "valor": v, "origem": "empresa", "fonte": fonte}
    return out


def value(params, key):
    return params[key]["valor"]


# ---------------------------------------------------------------------------------------------------------------
# Quantity rows

UNCERTAIN = {"hipotese", "standard", "inferido", "estimativa_imagem", "estimativa"}


def combine(*origins):
    """Origin of a quantity computed from several inputs: the weakest input wins."""
    o = set(origins)
    if "estimativa_imagem" in o:
        return "estimativa_imagem"
    if o & UNCERTAIN:
        return "estimativa"
    if o & {"fabricante", "empresa", "regra"}:
        return "regra"
    return "medido"


def row(codigo, quantidade, unidade, origem, metodo, *, fontes=(), sistema=None, piso=None, detalhe=None):
    return {"codigo": codigo, "quantidade": round(quantidade, 4), "unidade": unidade, "origem": origem, "metodo": metodo,
            "fontes": [f for f in fontes if f], "sistema": sistema, "piso": piso, "detalhe": detalhe or {}}


def _p(params, sid, key):
    item = params[f"{sid}.{key}"]
    return item["valor"], item["origem"], f"{key} = {item['valor']:g} {item['unidade']} ({item['origem']}: {item['fonte']})"


def wall_rows(sid, pieces, walls, params, piso, geo_origin):
    """Quantities of one system on one floor. pieces: production pieces of the network (rede.pieces) of this system;
    walls: the WallAxis objects of this system (openings, lengths); geo_origin: worst origin of the geometry
    (medido, standard height, inferred opening, image estimate)."""
    rows = []
    if not pieces:
        return rows
    gross = sum(p["area_bruta_m2"] for p in pieces)
    holes = sum(p["area_vaos_m2"] for p in pieces)
    net = sum(p["area_liquida_m2"] for p in pieces)
    vol = sum(p["volume_liquido_m3"] for p in pieces)
    length = sum(p["comprimento_m"] for p in pieces)
    openings = [o for p in pieces for o in p["vaos"]]
    by_thickness = {}
    for p in pieces:
        by_thickness.setdefault(p["espessura_mm"], 0.0)
        by_thickness[p["espessura_mm"]] += p["area_liquida_m2"]
    detail = {"espessuras_mm": {f"{k:g}": round(v, 3) for k, v in sorted(by_thickness.items())}}
    common = dict(sistema=sid, piso=piso)
    rows.append(row("parede_comprimento", length, "m", geo_origin, "Σ comprimento das peças após resolução das juntas (sem contagem dupla)", **common))
    rows.append(row("parede_area_bruta", gross, "m²", geo_origin, "Σ comprimento × altura das peças", **common))
    rows.append(row("parede_area_vaos", holes, "m²", geo_origin, "Σ largura × altura dos vãos", **common))
    rows.append(row("parede_area_liquida", net, "m²", geo_origin, "área bruta − vãos", detalhe=detail, **common))
    rows.append(row("parede_volume", vol, "m³", geo_origin, "Σ área líquida × espessura", **common))

    if sid == "clt":
        rows.append(row("clt_pecas", len(pieces), "un", geo_origin, "peças de produção (num T a parede que encosta é cortada)", **common))
        cl, o_cl, s_cl = _p(params, sid, "clt_comprimento_max_m")
        rows.append(row("clt_volume", vol, "m³", combine(geo_origin, o_cl), "volume líquido das peças CLT", fontes=[s_cl], **common))
    elif sid in ("alvenaria_tijolo", "alvenaria_bloco"):
        L, oL, sL = _p(params, sid, "unidade_comprimento_mm")
        H, oH, sH = _p(params, sid, "unidade_altura_mm")
        j, oj, sj = _p(params, sid, "junta_mm")
        loss, ol, sl = _p(params, sid, "perdas_pct")
        mort, om, sm = _p(params, sid, "argamassa_l_m2")
        bearing, ob, sb = _p(params, sid, "apoio_lintel_m")
        faces, of, sf = _p(params, sid, "faces_revestidas")
        per_m2 = 1 / (((L + j) / 1000) * ((H + j) / 1000))
        rows.append(row("alvenaria_area", net, "m²", geo_origin, "área líquida de alvenaria (vãos deduzidos)", **common))
        rows.append(row("alvenaria_unidades", math.ceil(net * per_m2 * (1 + loss / 100)), "un", combine(geo_origin, oL, oH, oj, ol),
                        "área líquida × 1/((C+j)×(A+j)) × (1 + perdas)", fontes=[sL, sH, sj, sl],
                        detalhe={"un_m2": round(per_m2, 3)}, **common))
        rows.append(row("alvenaria_argamassa", net * mort / 1000, "m³", combine(geo_origin, om), "área líquida × consumo", fontes=[sm], **common))
        lintel = sum(o["width_m"] + 2 * bearing for o in openings)
        rows.append(row("lintel_comprimento", lintel, "m", combine(geo_origin, ob), "Σ (largura do vão + 2 × entrega)", fontes=[sb],
                        detalhe={"vaos": len(openings)}, **common))
        rows.append(row("reboco_area", net * faces, "m²", combine(geo_origin, of), "área líquida × faces revestidas", fontes=[sf], **common))
    elif sid == "betao_armado":
        steel, os_, ss = _p(params, sid, "aco_kg_m3")
        loss, ol, sl = _p(params, sid, "perdas_betao_pct")
        reveal = sum(2 * (o["width_m"] + o["height_m"]) * p["espessura_mm"] / 1000 for p in pieces for o in p["vaos"])
        rows.append(row("betao_volume", vol * (1 + loss / 100), "m³", combine(geo_origin, ol), "volume líquido × (1 + perdas)", fontes=[sl], **common))
        rows.append(row("cofragem_area", 2 * net + reveal, "m²", geo_origin, "2 faces × área líquida + contornos dos vãos × espessura",
                        detalhe={"contornos_vaos_m2": round(reveal, 3)}, **common))
        rows.append(row("aco_massa", vol * steel, "kg", combine(geo_origin, os_), "volume líquido × taxa de armadura (orçamento, não dimensionamento)",
                        fontes=[ss], **common))
    elif sid in ("ossatura_madeira", "ossatura_metalica", "divisoria_gesso"):
        e, oe, se = _p(params, sid, "entre_eixo_m")
        studs = sum(math.ceil(p["comprimento_m"] / e - 1e-9) + 1 for p in pieces) + 2 * len(openings)
        stud_m = sum((math.ceil(p["comprimento_m"] / e - 1e-9) + 1 + 2 * len(p["vaos"])) * p["altura_m"] for p in pieces)
        rails = 2 * length + sum(o["width_m"] * (2 if o["sill_m"] > 0 else 1) for o in openings)
        key = "placas_por_face" if sid == "divisoria_gesso" else "faces_placa"
        faces, of, sf = _p(params, sid, key)
        sheets = net * (2 * faces if sid == "divisoria_gesso" else faces)
        rows.append(row("montantes_un", studs, "un", combine(geo_origin, oe), "Σ (comprimento ÷ entre-eixo + 1) + 2 por vão", fontes=[se], **common))
        rows.append(row("montantes_comprimento", stud_m, "m", combine(geo_origin, oe), "montantes × altura da parede", fontes=[se], **common))
        rows.append(row("travessas_comprimento", rails, "m", geo_origin, "2 × comprimento (guia inferior e superior) + padieiras e peitoris", **common))
        rows.append(row("placas_area", sheets, "m²", combine(geo_origin, of), "área líquida × faces com placa", fontes=[sf], **common))
        rows.append(row("isolamento_parede_area", net, "m²", geo_origin, "área líquida (caixa entre montantes)", **common))
    return rows


def opening_rows(pieces, piso):
    """Openings (joinery) counted the same way for every system."""
    out = []
    groups = {}
    for p in pieces:
        for o in p["vaos"]:
            kind = o.get("kind") or "vao"
            inferred = str(o.get("label", "")).startswith("inferido")
            g = groups.setdefault(kind, {"n": 0, "area": 0.0, "inferidos": 0})
            g["n"] += 1
            g["area"] += o["width_m"] * o["height_m"]
            g["inferidos"] += int(inferred)
    for kind, g in sorted(groups.items()):
        origin = "estimativa" if g["inferidos"] else "medido"
        out.append(row(f"vaos_{kind}", g["n"], "un", origin, "vãos contados nas peças" + (f" ({g['inferidos']} inferidos)" if g["inferidos"] else ""),
                       piso=piso, detalhe={"area_m2": round(g["area"], 3)}))
    return out


def room_rows(rooms, piso):
    """Floor, ceiling and skirting of the rooms drawn on the plan (same rules as the CLT fit-out)."""
    from shapely.geometry import Polygon

    out = []
    total_area = total_perim = 0.0
    for r in rooms:
        poly = Polygon(r["poligono"])
        if not poly.is_valid or poly.area <= 0:
            raise ValueError(f"A divisão {r.get('nome', '?')} tem um contorno inválido.")
        total_area += poly.area
        total_perim += poly.length
    if rooms:
        out.append(row("pavimento_area", total_area, "m²", "medido", "Σ área das divisões (polígono)", piso=piso, detalhe={"divisoes": len(rooms)}))
        out.append(row("teto_area", total_area, "m²", "medido", "igual ao pavimento (teto plano)", piso=piso))
        out.append(row("rodape_comprimento", total_perim, "m", "medido", "Σ perímetro das divisões (portas não deduzidas)", piso=piso))
    return out
