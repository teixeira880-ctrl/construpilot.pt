"""Complete CLT dossier: take-offs, prices, cost and profit, tracking plan, hypotheses and sources, in one premium PDF.

The numbers come only from clt_economics.estimate (and the fit-out engine it calls) with the account's own parameters
and library, and from the floors the company reviewed on the CLT page (the last estimate it ran there) or passed
explicitly. The sensitivity cases re-run the same estimate with the stated price change. Every hypothesis is listed.
Languages: Portuguese (default), English and Ukrainian (bim_studio.clt_i18n); the numbers are the same in all three.
"""
from __future__ import annotations

import contextvars
import copy
import io
from datetime import date, timedelta
from decimal import Decimal

from bim_studio import clt_fitout
from bim_studio import clt_i18n as I
from bim_studio.clt_economics import (CATALOGUE, CATEGORIES, STAGE_ORDER, EstimateInput, estimate, fitout_floors,
                                      library_defaults, lot_from_estimate, standard_heights)

STAGE_NAMES = {"compra": "Compra de matéria-prima", "fabrico": "Fabrico", "producao": "Produção (energia e mão de obra)",
               "transporte": "Transporte", "montagem": "Montagem", "revestimentos": "Revestimentos e isolamentos",
               "acabamentos": "Instalações e acabamentos", "entrega": "Entrega", "indiretos": "Custos indiretos", "venda": "Venda"}
ORIGINS = {"empresa": "empresa", "mercado": "mercado", "hipotese": "HIPÓTESE", "norma": "norma"}
# planning hypothesis for the cost curve: which phase spends each cost stage (indirect costs spread over the whole job)
SPEND_PHASE = {"compra": "compra", "producao": "fabrico", "fabrico": "fabrico", "transporte": "transporte", "montagem": "montagem",
               "revestimentos": "acabamentos", "acabamentos": "acabamentos", "entrega": "acabamentos"}
FIT_LABELS = {"un_tomada": ("Tomadas", "un"), "un_ponto_luz": ("Pontos de luz", "un"), "un_interruptor": ("Interruptores", "un"),
              "un_circuito": ("Circuitos", "un"), "m_cabo": ("Cabo", "m"), "m_tubo_eletrico": ("Tubo elétrico", "m"),
              "un_quadro": ("Quadro elétrico", "un"), "un_diferencial": ("Diferenciais 30 mA", "un"),
              "un_ponto_agua": ("Pontos de água (fria + quente)", "un"), "m_tubo_agua": ("Tubo de água", "m"),
              "un_ponto_esgoto": ("Pontos de esgoto", "un"), "m_tubo_esgoto": ("Tubo de esgoto", "m"),
              "un_sanita": ("Sanitas", "un"), "un_lavatorio": ("Lavatórios", "un"), "un_base_duche": ("Bases de duche", "un"),
              "un_banheira": ("Banheiras", "un"), "un_lava_loica": ("Lava-loiças", "un"), "un_aqs": ("Produção de AQS", "un"),
              "m2_caixilharia": ("Caixilharia exterior", "m²"), "un_vao_exterior": ("Vãos exteriores", "un"),
              "un_porta_interior": ("Portas interiores", "un"), "un_porta_entrada": ("Porta de entrada", "un"),
              "m2_pavimento": ("Pavimento flutuante", "m²"), "m2_pavimento_ceramico": ("Pavimento cerâmico", "m²"),
              "m2_ceramica_parede": ("Cerâmica de parede", "m²"), "m_rodape": ("Rodapé", "m")}
LANGS = ("pt", "en", "uk")
_LANG = contextvars.ContextVar("clt_study_lang", default="pt")


def _(text, **values):
    out = I.tr(text, _LANG.get())
    return out.format(**values) if values else out


def _u(unit):
    return I.unit(unit, _LANG.get())


def _n(value, digits=2):
    if value is None:
        return "—"
    text = f"{float(value):,.{digits}f}"
    return text if _LANG.get() == "en" else text.replace(",", " ").replace(".", ",")


def _tr(text):
    if text.startswith("Попередній"):
        return _("Estimativa por motores determinísticos ConstruPilot — a validar pelo responsável técnico da empresa.")
    return _({"Зміст / Contents": "Índice", "Обкладинка / Cover": "Capa"}.get(text, text))


def _scenario(body, parametros, biblioteca, change):
    lib = copy.deepcopy(biblioteca)
    for item in lib.values():
        change(item)
    return estimate(body, parametros, lib)["total"]


def _gantt(plan, w):
    from engines.calc_lots import graficos as G
    from reportlab.graphics.shapes import Drawing, Line, Rect
    fases = plan["fases"]
    start, end = date.fromisoformat(plan["inicio"]), date.fromisoformat(plan["fim"])
    span = max(1, (end - start).days + 1)
    row, top, x0 = 16, 18, 150
    h = top + row * len(fases) + 22
    d = Drawing(w, h)
    x1 = w - 6
    fx = lambda day: x0 + (day - start).days / span * (x1 - x0)
    weeks = 0
    while start + timedelta(days=7 * weeks) <= end:
        wx = fx(start + timedelta(days=7 * weeks))
        d.add(Line(wx, 14, wx, h - top + 4, strokeColor=G.GRID, strokeWidth=0.4))
        if weeks % 2 == 0:
            d.add(G._s(wx + 1, 4, f"S{weeks + 1}", 5.5, G.MUTED))
        weeks += 1
    for i, f in enumerate(fases):
        y = h - top - row * (i + 1)
        a, b = date.fromisoformat(f["inicio"]), date.fromisoformat(f["fim"]) + timedelta(days=1)
        d.add(G._s(4, y + 4, _(STAGE_NAMES.get(f["fase"], f["fase"]))[:34], 6.6, G.INK))
        d.add(Rect(fx(a), y + 1, max(2, fx(b) - fx(a)), row - 5, fillColor=G.SERIES[i % 8], strokeColor=None, rx=2, ry=2))
        d.add(G._s(min(fx(b) + 3, x1 - 40), y + 4, f"{f['dias']} d", 6, G.INK2))
    d.add(G._s(x0, h - 10, _("{a} → {b} · {d} dias de calendário", a=plan["inicio"], b=plan["fim"], d=plan["dias"]), 7, G.INK2, bold=True))
    return d


def _s_curve(plan, stages):
    """Planned cumulative cost per week: each stage spread evenly over the phase that spends it."""
    start, end = date.fromisoformat(plan["inicio"]), date.fromisoformat(plan["fim"])
    total_days = (end - start).days + 1
    daily = {}
    phases = {f["fase"]: f for f in plan["fases"]}
    for stage, value in stages.items():
        if not value:
            continue
        phase = phases.get(SPEND_PHASE.get(stage, ""))
        a, b = (date.fromisoformat(phase["inicio"]), date.fromisoformat(phase["fim"])) if phase else (start, end)
        n = (b - a).days + 1
        for k in range(n):
            day = a + timedelta(days=k)
            daily[day] = daily.get(day, 0) + value / n
    rows, cum, week = [], 0.0, 0
    while week * 7 < total_days:
        for k in range(7):
            cum += daily.get(start + timedelta(days=week * 7 + k), 0)
        rows.append((week + 1, (start + timedelta(days=week * 7 + 6)).isoformat(), cum))
        week += 1
    return rows


def _fabrication(body, title, press=(18.0, 3.5)):
    """Dimensioned fabrication drawings from the plan rectangles of the measured runs (segments with rect_m).

    Each run keeps its take-off reference as wall id, so a quantity line, the plan dimension and the
    production piece carry the same name. Returns None when no floor has run geometry."""
    from bim_studio import clt_drawings, clt_nesting, clt_walls

    staged, rows, notes, network = [], [], [], []
    for fl in body.floors:
        segs = [s for s in fl.segments if s.rect_m]
        if not segs:
            continue
        layers = {w.thickness_mm: w.layers for w in fl.walls}
        walls = []
        for seg in segs:
            x0, y0, x1, y1 = seg.rect_m
            found, _rej = clt_walls.rectangles_to_axes([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], height_m=float(fl.height_m),
                                                     layers=int(layers.get(seg.thickness_mm, 5)),
                                                     nominal_mm=(float(seg.thickness_mm),), tolerance_mm=5)
            if found:
                walls.append(found[0].model_copy(update={"id": seg.ref, "source": f"take-off {seg.ref}"}))
            else:
                notes.append(_("{r}: contorno não convertível em eixo; fica só na tabela de medições.", r=seg.ref))
        if not walls:
            continue
        runs = {w.id: w for w in walls}
        try:
            walls, net = clt_walls.connect(walls, lintels=[li.model_dump() for li in fl.lintels])
            analysis = clt_walls.analyse(clt_walls.Floor(name=fl.name, walls=walls))
        except ValueError as exc:
            notes.append(f"{_(fl.name)}: {exc}")
            continue
        staged.append((_(fl.name), walls, analysis))
        notes.extend(f"{_(fl.name)} · {n}" for n in net["notas"])
        by_wall = {}
        for piece in analysis["pecas"]:
            by_wall.setdefault(piece["parede"], []).append(piece)
        measured = {s.ref: s for s in segs}
        seen = set()
        for ref, run in runs.items():
            wall = net["membros"].get(ref, ref)
            ps = by_wall.get(wall, [])
            # a piece made of several runs (joined over a lintel) shows its volume once, on its first run
            rows.append([_(fl.name), ref, _n(run.thickness_mm, 0), _n(measured[ref].length_m, 3), _n(run.length, 3),
                         ", ".join(f"{p['id']} {_n(p['comprimento_m'], 3)}" for p in ps) or "—",
                         "↑" if wall in seen else _n(sum(p["volume_liquido_m3"] for p in ps), 3)])
            seen.add(wall)
        kinds = {}
        for j in analysis["juntas"]:
            kinds[j["tipo"]] = kinds.get(j["tipo"], 0) + 1
        # CLT over the lintel openings, measured on the final pieces (after the junctions cut them at the faces)
        bridged = {r["lintel"] for r in net["linteis"]}
        lintel_volume = sum(o["width_m"] * (p["altura_m"] - o["sill_m"] - o["height_m"]) * p["espessura_mm"] / 1000
                            for p in analysis["pecas"] for o in p["vaos"] if o["kind"] == "vao" and o["label"] in bridged)
        # same lintels measured like the estimate does: band minus the drawn runs (GEOS), × (height − head) × thickness
        from shapely import union_all
        from shapely.geometry import box
        drawn = union_all([w.footprint() for w in runs.values()])
        estimated = 0.0
        for li in fl.lintels:
            row = next((r for r in net["linteis"] if r["lintel"] == li.ref), None)
            if row:
                x0, y0, x1, y1 = li.rect_m
                band = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                span = band.difference(drawn).area / min(band.bounds[2] - band.bounds[0], band.bounds[3] - band.bounds[1])
                t_mm = li.thickness_mm or next((w.thickness_mm for w in walls if w.id == row["peca"]), 100)
                estimated += span * (float(fl.height_m) - li.head_m) * t_mm / 1000
        network.append([_(fl.name), str(len(runs)), str(len(walls)), " · ".join(f"{k} {v}" for k, v in sorted(kinds.items())),
                        str(len(net["ligacoes"])), f"{len(net['linteis'])} / {len(fl.lintels)}", _n(lintel_volume, 3), _n(estimated, 3) if estimated else "—"])
    if not staged:
        return None
    pieces = [p for _n_, _w, a in staged for p in clt_nesting.pieces_from_walls(a)]
    nesting = clt_nesting.plan(clt_nesting.NestingInput(pieces=pieces, time_limit_s=5, blank_length_m=press[0], blank_width_m=press[1]))
    drawings = clt_drawings.build([(n, w, a["pecas"]) for n, w, a in staged], nesting, title=title, tr=_)
    checks = [(n, a["verificacao_volume"]["passed"], a["metodos"]["volume_pecas_m3"], a["metodos"]["volume_uniao_planta_m3"])
              for n, _w, a in staged]
    return {"pdf": drawings["pdf"], "folhas": drawings["folhas"], "rows": rows, "notes": notes, "checks": checks, "rede": network,
            "corte": nesting["total"]}


def _annex_pages(drawings, title):
    """A3 landscape annex pages: the drawing on the left, a title block on the right (the company stamp goes above it)."""
    import pymupdf
    from engines.calc_lots import premium

    fr, fb = premium._fontes()
    src = pymupdf.open(stream=drawings["pdf"], filetype="pdf")
    out = pymupdf.open()
    W, H = 1190.55, 841.89
    for i, sheet in enumerate(drawings["folhas"]):
        pg = out.new_page(width=W, height=H)
        pg.insert_font(fontname="cr", fontfile=fr)
        pg.insert_font(fontname="cb", fontfile=fb)
        pg.show_pdf_page(pymupdf.Rect(18, 18, W - 252, H - 18), src, i)
        pg.draw_rect(pymupdf.Rect(12, 12, W - 12, H - 12), color=(0.2, 0.2, 0.2), width=0.8)
        box = pymupdf.Rect(W - 240, H - 200, W - 30, H - 25)
        pg.draw_rect(box, color=(0.2, 0.2, 0.2), width=0.6)
        lines = [(title, 9, True), (_("Anexo A · folha {i} / {n}", i=i + 1, n=len(drawings["folhas"])), 8, False),
                 (sheet["folha"][:58], 7.5, True), (_("Cotas em mm · desenho sem escala"), 7, False),
                 (_("Origem: troços medidos no take-off (mesmas referências das tabelas)"), 6.2, False),
                 (_("Desenho de conferência de fabrico. Não substitui o projeto de execução."), 6.2, False),
                 ("ConstruPilot · " + date.today().isoformat(), 6.2, False)]
        y = box.y0 + 16
        for text, size, bold in lines:
            pg.insert_textbox(pymupdf.Rect(box.x0 + 8, y - size, box.x1 - 6, y + 2 * size), text, fontname="cb" if bold else "cr",
                              fontsize=size, color=(0.1, 0.1, 0.1))
            y += size * 2.1 if len(text) > 50 else size * 1.7
    return out


def note(entrada: dict, parametros: dict, biblioteca: dict, titulo: str | None = None, empresa: str | None = None,
         anexos: list | None = None, local: str | None = None, capa_imagem: bytes | None = None, lingua: str = "pt") -> dict:
    """entrada: EstimateInput as JSON; parametros / biblioteca: the account's merged parameters and library;
    empresa: brand slug of engines.calc_lots.premium (logo on cover and pages); anexos: [(title, png bytes, caption)];
    lingua: pt | en | uk (same numbers, translated texts)."""
    token = _LANG.set(lingua if lingua in LANGS else "pt")
    try:
        return _note(entrada, parametros, biblioteca, titulo, empresa, anexos, local, capa_imagem)
    finally:
        _LANG.reset(token)


def _note(entrada, parametros, biblioteca, titulo, empresa, anexos, local, capa_imagem):
    import pymupdf
    from engines.calc_lots import graficos as G
    from engines.calc_lots import premium, rendu
    from reportlab.lib.units import mm
    from reportlab.platypus import Image

    lang = _LANG.get()
    std_items = library_defaults()
    item_name = lambda code, name: I.item_name(code, name, lang, std_items.get(code, {}).get("name"))
    param_label = lambda key, label: I.param_label(key, label, lang, CATALOGUE.get(key, ("", ""))[1])
    origin = lambda o: _(ORIGINS.get(o, o))
    stage = lambda s: _(STAGE_NAMES.get(s, s))

    body = EstimateInput.model_validate(entrada)
    standard_h = {fl.name for fl in body.floors if fl.height_m is None}
    body, _height_notes = standard_heights(body, parametros)
    r = estimate(body, parametros, biblioteca)
    t, plan = r["total"], r["plano"]
    p = {k: Decimal(str(v["value"])) for k, v in parametros.items()}
    fit, _notes = clt_fitout.quantities(fitout_floors(body))
    titre = titulo or _("Estudo CLT completo")
    W = mm
    useful = sum((sum((rm.area_m2 for rm in fl.rooms if rm.tipo != "exterior"), Decimal(0)) for fl in body.floors), Decimal(0))
    hyp = [(lambda code, _sep, name: f"{code} · {item_name(code, name)}")(*h.partition(" · ")) if " · " in h else
           param_label(next((k for k, v in parametros.items() if v["label"] == h), ""), h) for h in r["hipoteses_por_confirmar"]]
    estado = (_("Todos os valores vêm da empresa ou do mercado.") if r["status"] == "valores_da_empresa" else
              _("ESTIMATIVA: {n} valores ainda são hipóteses (lista no capítulo 6). A empresa confirma-os em Parâmetros e Bibliotecas na página CLT e o dossier é refeito com os seus valores.", n=len(hyp)))
    B = [("kpis", [{"label": _("Custo total"), "value": _n(t["custo_total_eur"], 0), "unit": "€"},
                   {"label": _("Venda sem IVA"), "value": _n(t["receita_eur"], 0), "unit": "€"},
                   {"label": _("Margem"), "value": _n(t["margem_percent"], 1), "unit": "%", "ok": (t["margem_percent"] or 0) > 0},
                   {"label": _("CLT fabricado"), "value": _n(t["fabrico_m3"]), "unit": _u("m³")},
                   {"label": _("Prazo"), "value": str(plan["dias"]), "unit": _("dias")}])]

    # 1. synthesis ---------------------------------------------------------------------------------------------------
    B.append(("h2", _("1. Síntese")))
    B.append(("p", _("Âmbito: da compra da madeira e do fabrico dos painéis CLT até à entrega da chave: estrutura CLT, vigas de aço, revestimentos, isolamentos e estanquidade, caixilharia, eletricidade, canalização e acabamentos. Fora do âmbito: betão e lajes de betão, cálculo estrutural, projetos de especialidade e planos de execução. ") + estado))
    rows = [[stage(s), _n(t["custos_eur"].get(s, 0)), _n(t["custos_eur"].get(s, 0) * 100 / t["custo_total_eur"], 1)]
            for s in STAGE_ORDER if t["custos_eur"].get(s)]
    rows += [[_("Custo total"), _n(t["custo_total_eur"]), _n(100, 1)], [_("Venda sem IVA"), _n(t["receita_eur"]), ""],
             [_("IVA {p} %", p=_n(t["iva_percent"], 0)), _n(t["iva_eur"]), ""], [_("Venda com IVA (cliente final)"), _n(t["receita_com_iva_eur"]), ""],
             [_("Benefício (margem)"), _n(t["margem_eur"]), _("{p} % da venda", p=_n(t["margem_percent"], 1))]]
    B.append(("table", [_("Fase"), "€", _("% do custo")], rows, [100 * W, 45 * W, 35 * W]))
    B.append(("p", _("IVA aplicado: ") + _(t["iva_fonte"]) + " " + _("Depende do local da obra e do comprador: casa construída na Ucrânia → ПДВ 20 %; painéis exportados da Ucrânia → 0 % na Ucrânia e IVA do país de destino; obra em Portugal → IVA 23 %.")))
    B.append(("chart", G.barres_h([(stage(s), float(t["custos_eur"][s])) for s in STAGE_ORDER if t["custos_eur"].get(s)],
                                  titre=_("Custo por fase"), unite="€"), _("Custo direto e indireto por fase, a partir do orçamento linha a linha.")))
    per = lambda v, d: _n(v / d) if d else "—"
    ratios = [[_("Área útil (soma das divisões revistas)"), f"{_n(useful)} {_u('m²')}"],
              [_("Custo por m² útil"), f"{per(t['custo_total_eur'], float(useful))} €/{_u('m²')}"],
              [_("Venda com IVA por m² útil"), f"{per(t['receita_com_iva_eur'], float(useful))} €/{_u('m²')}"],
              [_("Custo por m³ de CLT fabricado"), f"{per(t['custo_total_eur'], t['fabrico_m3'])} €/{_u('m³')}"]]
    B.append(("table", [_("Rácio"), _("Valor")], ratios, [110 * W, 70 * W]))

    # 2. take-offs -----------------------------------------------------------------------------------------------------
    B.append(("h2", _("2. Medições (métrés)")))
    B.append(("p", _("Medidas nos planos vetoriais revistos na página CLT: cada troço de parede, cada painel, vão e divisão tem a sua referência de leitura. Altura estrutural de cada piso = pé-direito acabado + pavimento + zona do teto falso, medidos no corte.")))
    for fl, row in zip(body.floors, r["pisos"]):
        B.append(("p", _("Piso {f} · altura estrutural {h} m", f=_(fl.name), h=_n(fl.height_m, 3))
                  + (" · " + _("altura standard da empresa: a planta não marca alturas (editável)") if fl.name in standard_h else "")))
        if fl.segments:
            segs = [[s.ref, _n(s.thickness_mm, 0), _n(s.length_m, 3), _n(s.length_m * fl.height_m), _n(s.length_m * fl.height_m * s.thickness_mm / 1000, 3)]
                    for s in fl.segments]
            segs.append([_("Total"), "", _n(sum((s.length_m for s in fl.segments), Decimal(0)), 3),
                         _n(sum((s.length_m * fl.height_m for s in fl.segments), Decimal(0))),
                         _n(sum((s.length_m * fl.height_m * s.thickness_mm / 1000 for s in fl.segments), Decimal(0)), 3)])
            B.append(("table", [_("Troço CLT (ref. de leitura)"), _("Espessura mm"), _("Comprimento m"), _("Área m²"), _("Volume m³")], segs,
                      [52 * W, 30 * W, 32 * W, 33 * W, 33 * W]))
        walls = [[_("Parede CLT {t} mm", t=_n(w.thickness_mm, 0)), str(w.layers), _n(w.length_m, 3), _n(w.length_m * fl.height_m),
                  _n(w.length_m * fl.height_m * w.thickness_mm / 1000, 3)] for w in fl.walls]
        walls += [[_(e.label or e.kind), str(e.layers), "", _n(e.area_m2), _n(e.area_m2 * e.thickness_mm / 1000, 3)] for e in fl.panels]
        walls.append([_("Total CLT do piso"), "", "", _n(row["montagem_m2"]), _n(row["fabrico_m3"], 3)])
        B.append(("table", [_("Elemento CLT"), _("Camadas"), _("Comprimento m"), _("Área m²"), _("Volume m³")], walls, [70 * W, 20 * W, 28 * W, 30 * W, 32 * W]))
        if fl.windows:
            rows = []
            for n, w in enumerate(fl.windows, 1):
                height = (Decimal(str(fl.ceiling_height_m or clt_fitout.OPENING_H["vao_envidracado"])) if w.sobre == "viga" else
                          clt_fitout.OPENING_H["lintel"] if w.sobre == "lintel" else clt_fitout.OPENING_H[w.tipo])
                rows.append([_("vão {n}", n=n), _("vão envidraçado") if w.tipo == "vao_envidracado" else _("janela"), _(w.sobre) if w.sobre else "—",
                             _n(w.largura_m), _n(height), _n(w.largura_m * height)])
            B.append(("table", [_("Vão exterior"), _("Tipo"), _("Sob"), _("Largura m"), _("Altura m"), _("Área m²")], rows,
                      [24 * W, 34 * W, 20 * W, 32 * W, 34 * W, 36 * W]))
        if fl.rooms:
            rows = [[_(rm.nome), _(rm.tipo.replace("_", " ")), _n(rm.area_m2), _n(rm.perimetro_m), ", ".join(_(a) for a in rm.aparelhos) or "—"]
                    for rm in fl.rooms]
            B.append(("table", [_("Divisão"), _("Tipo"), _("Área m²"), _("Perímetro m"), _("Aparelhos desenhados")], rows,
                      [40 * W, 28 * W, 22 * W, 24 * W, 66 * W]))
    rows = [[_(row["piso"]), _n(row["placa_m2"]), _n(row["pintura_m2"]), _n(row["teto_m2"]), _n(row["fachada_m2"]), _n(row["laje_betao_m2"]),
             _n(row["cobertura_m2"]), _n(row["viga_aco_m"])] for row in r["pisos"]]
    B.append(("p", _("Revestimentos, isolamentos e estrutura complementar")))
    B.append(("table", [_("Piso"), _("Placa BA13 m²"), _("Pintura m²"), _("Teto BA15 m²"), _("Fachada m²"), _("Laje (isol.) m²"), _("Cobertura m²"), _("Aço m")],
              rows, [22 * W, 23 * W, 21 * W, 23 * W, 21 * W, 25 * W, 23 * W, 22 * W]))
    keys = [k for k in FIT_LABELS if any(q.get(k) for q in fit)]
    if keys:
        B.append(("p", _("Instalações, caixilharia e acabamentos (motor RTIEBT por divisão e aparelhos DR 23/95)")))
        rows = [[_(FIT_LABELS[k][0]), _u(FIT_LABELS[k][1])] + [_n(q.get(k, 0), 1) for q in fit] + [_n(sum((q.get(k, 0) for q in fit), Decimal(0)), 1)]
                for k in keys]
        widths = [70 * W, 16 * W] + [(94 * W) / (len(fit) + 1)] * (len(fit) + 1)
        B.append(("table", [_("Quantidade"), _("Un.")] + [_(fl.name) for fl in body.floors] + [_("Total")], rows, widths))
    rows = [[_(row["piso"]), _n(row["fabrico_m3"]), _n(row["madeira_comprada_m3"]), _n(row["adesivo_kg"], 0), _n(row["eletricidade_kwh"], 0),
             _n(row["horas_fabrico"], 1), _n(row["horas_montagem"], 1)] for row in r["pisos"]]
    B.append(("p", _("Matéria-prima e produção · {a} viagens de madeira e {b} de painéis", a=t["viagens_materia_prima"], b=t["viagens"])))
    B.append(("table", [_("Piso"), _("CLT m³"), _("Madeira m³"), _("Cola kg"), _("Eletricidade kWh"), _("h fabrico"), _("h montagem")], rows,
              [22 * W, 22 * W, 26 * W, 22 * W, 32 * W, 26 * W, 30 * W]))
    for text in r["notas_quantidades"]:
        B.append(("p", _(text)))

    # 3. detailed budget ------------------------------------------------------------------------------------------------
    B.append(("h2", _("3. Orçamento detalhado (quantidade × preço unitário)")))
    for cat in CATEGORIES:
        lines = [l for l in r["linhas"] if l["categoria"] == cat and l["quantidade"]]
        if not lines:
            continue
        B.append(("p", _(CATEGORIES[cat][0])))
        rows = [[l["codigo"], item_name(l["codigo"], l["designacao"]), _n(l["quantidade"]), _u(l["unidade"]), _n(l["custo_unitario_eur"]),
                 _n(l["custo_eur"]) if l["fase"] != "venda" else "—", _n(l["venda_eur"]) if l["venda_eur"] is not None else "—",
                 origin(l["origem"])] for l in lines]
        B.append(("table", [_("Código"), _("Designação"), _("Qtd."), _("Un."), _("€/un."), _("Custo €"), _("Venda €"), _("Origem")],
                  rows, [28 * W, 50 * W, 17 * W, 10 * W, 15 * W, 20 * W, 20 * W, 20 * W]))

    # 4. cost, profit and sensitivity -------------------------------------------------------------------------------------
    B.append(("h2", _("4. Custos, benefício e sensibilidade")))
    rows = [[_(row["piso"]), _n(row["custo_total_eur"]), _n(row["receita_eur"]), _n(row["margem_eur"]), _n(row["margem_percent"], 1)] for row in r["pisos"]]
    rows.append([_("Total"), _n(t["custo_total_eur"]), _n(t["receita_eur"]), _n(t["margem_eur"]), _n(t["margem_percent"], 1)])
    B.append(("table", [_("Piso"), _("Custo €"), _("Venda €"), _("Benefício €"), _("Margem %")], rows, [36 * W] * 5))

    def scale(field, factor, test):
        def change(item):
            if test(item) and item.get(field) is not None:
                item[field] = str(Decimal(str(item[field])) * Decimal(factor))
        return change
    cases = [("Madeira e matéria-prima +10 %", scale("cost_eur", "1.10", lambda i: i["category"] == "materia_prima")),
             ("Montagem em obra +10 %", scale("cost_eur", "1.10", lambda i: CATEGORIES.get(i["category"], ("", ""))[1] == "montagem")),
             ("Instalações e acabamentos +10 %", scale("cost_eur", "1.10", lambda i: CATEGORIES.get(i["category"], ("", ""))[1] == "acabamentos")),
             ("Todos os preços HIPÓTESE +10 %", scale("cost_eur", "1.10", lambda i: i.get("origin") == "hipotese" and i["basis"] != "pct_custo")),
             ("Todos os preços HIPÓTESE −10 %", scale("cost_eur", "0.90", lambda i: i.get("origin") == "hipotese" and i["basis"] != "pct_custo")),
             ("Preços de venda −5 %", scale("sale_eur", "0.95", lambda i: True))]
    rows = [[_("Base (este dossier)"), _n(t["custo_total_eur"], 0), _n(t["receita_eur"], 0), _n(t["margem_eur"], 0), _n(t["margem_percent"], 1)]]
    for label, change in cases:
        s = _scenario(body, parametros, biblioteca, change)
        rows.append([_(label), _n(s["custo_total_eur"], 0), _n(s["receita_eur"], 0), _n(s["margem_eur"], 0), _n(s["margem_percent"], 1)])
    B.append(("p", _("Sensibilidade: o mesmo cálculo refeito com a variação indicada (venda mantida quando só o custo muda).")))
    B.append(("table", [_("Cenário"), _("Custo €"), _("Venda €"), _("Benefício €"), _("Margem %")], rows, [64 * W, 29 * W, 29 * W, 29 * W, 29 * W]))

    # 5. tracking plan ----------------------------------------------------------------------------------------------------
    B.append(("h2", _("5. Plano de seguimento, da fabricação à montagem e à entrega")))
    B.append(("chart", _gantt(plan, 180 * W), _("Fases sequenciais em dias de calendário; o lote de seguimento da página CLT parte deste plano.")))
    crew_m2 = p["assembly_crew"] * p["work_hours_day"] / p["assembly_h_m2"] if p.get("assembly_h_m2") else None
    work = {"compra": _("{q} m³ de madeira, {n} viagens", q=_n(sum(row["madeira_comprada_m3"] for row in r["pisos"])), n=t["viagens_materia_prima"]),
            "fabrico": _("{q} m³ de CLT a {r} m³/dia", q=_n(t["fabrico_m3"]), r=_n(p["factory_m3_day"], 1)),
            "transporte": _("{n} viagens de {q} m³", n=t["viagens"], q=_n(p["truck_m3"], 0)),
            "montagem": _("{q} m² a {r} m²/dia ({c} pessoas × {h} h)", q=_n(t["montagem_m2"]), r=_n(crew_m2, 1), c=_n(p["assembly_crew"], 0),
                          h=_n(p["work_hours_day"], 0)),
            "acabamentos": _("{a} divisões, {b} vãos", a=sum(len(fl.rooms) for fl in body.floors), b=sum(len(fl.windows) for fl in body.floors))}
    rows = [[stage(f["fase"]), f["inicio"], f["fim"], str(f["dias"]), work.get(f["fase"], "")] for f in plan["fases"]]
    B.append(("table", [_("Fase"), _("Início"), _("Fim (marco)"), _("Dias"), _("Quantidade e ritmo previstos")], rows,
              [40 * W, 22 * W, 24 * W, 12 * W, 82 * W]))
    curve = _s_curve(plan, t["custos_eur"])
    B.append(("chart", G.courbes([c[0] for c in curve], [(_("Custo planeado acumulado"), [c[2] for c in curve], None)],
                                 titre=_("Curva de custo planeado"), unite="€", xlab=_("semana")),
              _("Cada fase de custo distribuída de forma uniforme pela fase do plano que a gasta; custos indiretos ao longo de toda a obra (hipótese de planeamento).")))
    rows = [[f"S{c[0]}", c[1], _n(c[2], 0), _n(c[2] * 100 / t["custo_total_eur"], 1), "", ""] for c in curve]
    B.append(("table", [_("Semana"), _("Até"), _("Custo planeado acumulado €"), _("% planeado"), _("Custo real €"), _("% real")], rows,
              [18 * W, 26 * W, 46 * W, 26 * W, 36 * W, 28 * W]))
    lot = lot_from_estimate(titre, r)
    rows = [[l["code"], item_name(l["code"], l["name"]), _(l["stage"]), _n(Decimal(l["baseline_qty"])), _u(l["unit"]), _n(Decimal(l["rate_eur"])),
             _n(Decimal(l["uncommitted_remaining_eur"])), ""] for l in lot["lines"]]
    B.append(("p", _("Folha de controlo do lote de seguimento: o orçamento de cada artigo é a base; a página CLT regista as compras e o realizado e calcula o desvio e a previsão de fecho.")))
    B.append(("table", [_("Código"), _("Artigo"), _("Fase"), _("Qtd. base"), _("Un."), _("€/un."), _("Orçamento €"), _("Real €")], rows,
              [26 * W, 48 * W, 18 * W, 18 * W, 10 * W, 16 * W, 24 * W, 20 * W]))
    B.append(("table", [_("Indicador a seguir"), _("Previsto"), _("Como medir")], [
        [_("Fabrico"), _("{r} m³/dia", r=_n(p["factory_m3_day"], 1)), _("m³ de painéis aprovados por dia na linha")],
        [_("Montagem"), _("{r} m²/dia", r=_n(crew_m2, 1)), _("m² de painéis aparafusados por dia de equipa")],
        [_("Entregas"), _("{n} viagens", n=t["viagens"]), _("guias de transporte")],
        [_("Custo comprometido"), f"{_n(t['custo_total_eur'], 0)} €", _("encomendas e faturas por artigo do lote")],
        [_("Margem prevista"), f"{_n(t['margem_percent'], 1)} %", _("venda − previsão de fecho do lote")]], [40 * W, 40 * W, 100 * W]))

    # 6. hypotheses and sources -------------------------------------------------------------------------------------------
    B.append(("h2", _("6. Parâmetros, preços, origens e fontes")))
    rows = []
    for key, v in parametros.items():
        value = _n(v["value"], 3)
        value = value.rstrip("0").rstrip(",.") if any(c in value for c in ",.") else value
        rows.append([param_label(key, v["label"]), f"{value} {_u(v['unit'])}", origin(v["origin"]), _(v.get("source") or "")[:120]])
    B.append(("table", [_("Parâmetro"), _("Valor"), _("Origem"), _("Fonte ou como confirmar")], rows, [52 * W, 26 * W, 20 * W, 82 * W]))
    used = {l["codigo"] for l in r["linhas"] if l["quantidade"]}
    rows = [[code, item_name(code, i["name"]), f"{_n(i['cost_eur'])} €/{_u(i['unit'])}", origin(i["origin"]), _(i.get("source") or "")[:100]]
            for code, i in biblioteca.items() if code in used]
    B.append(("table", [_("Código"), _("Preço"), _("Custo"), _("Origem"), _("Fonte")], rows, [26 * W, 46 * W, 26 * W, 18 * W, 64 * W]))
    checks = []
    for fl in body.floors:
        if fl.segments:
            a = sum((s.length_m for s in fl.segments), Decimal(0))
            b = sum((w.length_m for w in fl.walls), Decimal(0))
            checks.append([_("Troços medidos = paredes orçamentadas ({f})", f=_(fl.name)), f"{_n(a, 3)} / {_n(b, 3)} m",
                           "OK" if abs(a - b) <= b * Decimal("0.02") else _("VERIFICAR")])
    lines_sum = sum(l["custo_eur"] for l in r["linhas"])
    checks.append([_("Soma das linhas = custo total"), f"{_n(lines_sum)} / {_n(t['custo_total_eur'])} €", "OK" if abs(lines_sum - t["custo_total_eur"]) < 1 else _("VERIFICAR")])
    checks.append([_("IVA {p} % da venda", p=_n(t["iva_percent"], 0)), f"{_n(t['iva_eur'])} €",
                   "OK" if abs(t["receita_eur"] * t["iva_percent"] / 100 - t["iva_eur"]) < 1 else _("VERIFICAR")])
    B.append(("p", _("Controlos automáticos")))
    B.append(("table", [_("Controlo"), _("Valores"), _("Resultado")], checks, [100 * W, 55 * W, 25 * W]))

    fab = _fabrication(body, titre, (float(p.get("press_length_m", 18)), float(p.get("press_width_m", 3.5))))
    if fab:
        B.append(("h2", _("Anexo A — Desenhos de fabrico cotados (origem das cotas e medições)")))
        B.append(("p", _("Cada troço medido no take-off é desenhado com a mesma referência: a planta cota o comprimento de cada parede ao milímetro, "
                         "os alçados cotam cada peça de produção (comprimento, altura e vãos) e o plano de corte mostra os painéis de prensa. "
                         "As juntas resolvem-se sem contagem dupla: a parede mais comprida passa e a outra encosta.")))
        B.append(("table", [_("Piso"), _("Ref. take-off"), _("Espessura mm"), _("Medido m"), _("Desenhado m"), _("Peças de produção m"), _("Volume m³")],
                  fab["rows"], [16 * W, 24 * W, 18 * W, 20 * W, 22 * W, 56 * W, 24 * W]))
        checks_rows = [[_(n), f"{_n(a, 3)} / {_n(b, 3)} m³", "OK" if ok else _("VERIFICAR")] for n, ok, a, b in fab["checks"]]
        B.append(("table", [_("Controlo volume: peças / união das plantas"), _("Valores"), _("Resultado")], checks_rows, [100 * W, 55 * W, 25 * W]))
        if fab.get("rede"):
            B.append(("p", _("Rede de paredes: cada extremo de troço que encosta a outra parede é levado ao eixo dessa parede "
                             "(no máximo meia espessura), para reconhecer os cantos L, T e X. Dois troços alinhados dos dois lados "
                             "de um lintel CLT passam a uma só peça com o vão recortado; o volume do lintel fica dentro da peça "
                             "e é comparado com o painel de lintel da estimativa.")))
            B.append(("table", [_("Piso"), _("Troços"), _("Peças-mãe"), _("Juntas"), _("Extremos ligados"), _("Lintéis na peça"),
                                _("Lintéis m³ (peças)"), _("Lintéis m³ (estimativa)")], fab["rede"],
                      [14 * W, 16 * W, 20 * W, 36 * W, 22 * W, 22 * W, 26 * W, 26 * W]))
        B.append(("p", _("Plano de corte: {n} painéis de prensa, desperdício {d} % (formato de prensa {l} × {w} m, parâmetro da empresa).",
                         n=fab["corte"]["paineis"], d=_n(fab["corte"]["desperdicio_percent"], 1),
                         l=_n(p.get("press_length_m", 18), 2), w=_n(p.get("press_width_m", 3.5), 2))))
        for line in fab["notes"]:
            B.append(("p", _(line)))
    else:
        B.append(("h2", _("Anexo A — Desenhos de fabrico cotados (origem das cotas e medições)")))
        B.append(("p", _("Sem geometria dos troços nesta estimativa: volte a calcular na página CLT a partir do PDF para juntar os desenhos cotados.")))

    for title, png, caption in anexos or []:
        B.append(("h2", title))
        pix = pymupdf.Pixmap(png)
        height = min(230 * W, 180 * W * pix.height / pix.width)
        B.append(("figure", Image(io.BytesIO(png), width=height * pix.width / pix.height, height=height), caption))

    labels = None if lang == "pt" else (__import__("engines.calc_lots.lingua_ucrania", fromlist=["EN_RENDU"]).EN_RENDU if lang == "en"
                                         else __import__("engines.calc_lots.ucrania", fromlist=["UK"]).UK)
    body_pdf = rendu.build_pdf(titre, _("Medições, custos, benefício e plano de seguimento · motor ConstruPilot CLT"),
                               B + [("h2", _("Valores a confirmar pela empresa")), ("hyp", hyp or [_("nenhum")])],
                               footer=_("ConstruPilot — nota de cálculo gerada por motor determinístico; a validar pelo projetista / técnico responsável antes da execução."),
                               lang=labels)
    doc = pymupdf.open(stream=body_pdf, filetype="pdf")
    index = []
    for block in B:
        if block[0] == "h2":
            hit = next((n + 2 for n, pg in enumerate(doc) if pg.search_for(block[1][:40])), None)
            if hit:
                index.append((block[1], hit))
    png = doc[0].get_pixmap(dpi=110).tobytes("png")
    n_note = len(doc)
    if fab:
        doc.insert_pdf(_annex_pages(fab, titre))
        body_pdf = doc.tobytes()
    capa = {"titulo": titre, "subtitulo": _("Dossier completo: medições, custos, benefício e plano de seguimento, da fabricação à entrega da chave."),
            "local": local or "", "data": _("Início previsto {a} · entrega {b}", a=plan["inicio"], b=plan["fim"]),
            "kpis": [(_("Custo total"), _n(t["custo_total_eur"], 0), "€"), (_("Venda com IVA"), _n(t["receita_com_iva_eur"], 0), "€"),
                     (_("Benefício"), _n(t["margem_eur"], 0), _("€ · {p} % da venda", p=_n(t["margem_percent"], 1))),
                     (_("CLT"), _n(t["fabrico_m3"]), _("m³ fabricados")), (_("Painéis"), _n(t["montagem_m2"]), _("m² montados")),
                     (_("Prazo"), str(plan["dias"]), _("dias de calendário")), (_("Área útil"), _n(useful), _("m²")),
                     (_("Hipóteses"), str(len(hyp)), _("valores a confirmar"))],
            "indice": index, "miniatura_pagina": None, "capa_imagem": capa_imagem}
    pdf = premium.embelezar(body_pdf, capa, premium.marca(empresa) if empresa else None, n_nota=n_note, tr=_tr)
    resumo = [f"{titre}: custo {_n(t['custo_total_eur'], 0)} €, venda {_n(t['receita_eur'], 0)} € sem IVA "
              f"({_n(t['receita_com_iva_eur'], 0)} € com IVA {_n(t['iva_percent'], 0)} %), benefício {_n(t['margem_eur'], 0)} € ({_n(t['margem_percent'], 1)} %).",
              f"CLT {_n(t['fabrico_m3'])} m³, montagem {_n(t['montagem_m2'])} m², prazo {plan['dias']} dias ({plan['inicio']} → {plan['fim']}).",
              "Custos por fase: " + "; ".join(f"{STAGE_NAMES.get(s, s)} {_n(v, 0)} €" for s, v in t["custos_eur"].items() if v),
              "Dossier: medições por troço, painel, vão e divisão; orçamento linha a linha com a origem de cada preço; sensibilidade; "
              "Gantt, curva de custo e folha de controlo do lote; parâmetros e fontes.", estado]
    if hyp:
        resumo.append("Hipóteses por confirmar: " + "; ".join(hyp[:25]) + (" …" if len(hyp) > 25 else ""))
    data = {"custo_total_eur": t["custo_total_eur"], "receita_eur": t["receita_eur"], "receita_com_iva_eur": t["receita_com_iva_eur"],
            "margem_percent": t["margem_percent"], "fabrico_m3": t["fabrico_m3"], "dias": plan["dias"], "estado": r["status"], "hipoteses": len(hyp)}
    return {"titre": titre, "pdf": pdf, "png": png, "resumo": resumo, "data": data}
