"""Complete CLT dossier: take-offs, prices, cost and profit, tracking plan, hypotheses and sources, in one premium PDF.

The numbers come only from clt_economics.estimate (and the fit-out engine it calls) with the account's own parameters
and library, and from the floors the company reviewed on the CLT page (the last estimate it ran there) or passed
explicitly. The sensitivity cases re-run the same estimate with the stated price change. Every hypothesis is listed.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from decimal import Decimal

from bim_studio import clt_fitout
from bim_studio.clt_economics import CATEGORIES, STAGE_ORDER, EstimateInput, estimate, fitout_floors, lot_from_estimate

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
TR = {"Зміст / Contents": "Índice", "Обкладинка / Cover": "Capa"}


def _n(value, digits=2):
    if value is None:
        return "—"
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", " ").replace(".", ",")


def _tr(text):
    if text.startswith("Попередній"):
        return "Estimativa por motores determinísticos ConstruPilot — a validar pelo responsável técnico da empresa."
    return TR.get(text, text)


def _scenario(body, parametros, biblioteca, change):
    lib = copy.deepcopy(biblioteca)
    for item in lib.values():
        change(item)
    return estimate(body, parametros, lib)["total"]


def _gantt(plan, w):
    from engines.calc_lots import graficos as G
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
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
            d.add(String(wx + 1, 4, f"S{weeks + 1}", fontSize=5.5, fillColor=G.MUTED, fontName="Helvetica"))
        weeks += 1
    for i, f in enumerate(fases):
        y = h - top - row * (i + 1)
        a, b = date.fromisoformat(f["inicio"]), date.fromisoformat(f["fim"]) + timedelta(days=1)
        d.add(String(4, y + 4, STAGE_NAMES.get(f["fase"], f["fase"])[:30], fontSize=6.6, fillColor=G.INK, fontName="Helvetica"))
        d.add(Rect(fx(a), y + 1, max(2, fx(b) - fx(a)), row - 5, fillColor=G.SERIES[i % 8], strokeColor=None, rx=2, ry=2))
        d.add(String(min(fx(b) + 3, x1 - 40), y + 4, f"{f['dias']} d", fontSize=6, fillColor=G.INK2, fontName="Helvetica"))
    d.add(String(x0, h - 10, f"{plan['inicio']} → {plan['fim']} · {plan['dias']} dias de calendário", fontSize=7, fillColor=G.INK2,
                 fontName="Helvetica-Bold"))
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


def note(entrada: dict, parametros: dict, biblioteca: dict, titulo: str | None = None, empresa: str | None = None,
         anexos: list | None = None, local: str | None = None, capa_imagem: bytes | None = None) -> dict:
    """entrada: EstimateInput as JSON; parametros / biblioteca: the account's merged parameters and library;
    empresa: brand slug of engines.calc_lots.premium (logo on cover and pages); anexos: [(title, png bytes, caption)]."""
    import pymupdf
    from engines.calc_lots import graficos as G
    from engines.calc_lots import premium, rendu
    from reportlab.lib.units import mm
    from reportlab.platypus import Image

    body = EstimateInput.model_validate(entrada)
    r = estimate(body, parametros, biblioteca)
    t, plan = r["total"], r["plano"]
    p = {k: Decimal(str(v["value"])) for k, v in parametros.items()}
    fit, _ = clt_fitout.quantities(fitout_floors(body))
    titre = titulo or "Estudo CLT completo"
    W = mm
    useful = sum((sum((rm.area_m2 for rm in fl.rooms if rm.tipo != "exterior"), Decimal(0)) for fl in body.floors), Decimal(0))
    estado = ("Todos os valores vêm da empresa ou do mercado." if r["status"] == "valores_da_empresa" else
              f"ESTIMATIVA: {len(r['hipoteses_por_confirmar'])} valores ainda são hipóteses (lista no capítulo 6). "
              "A empresa confirma-os em Parâmetros e Bibliotecas na página CLT e o dossier é refeito com os seus valores.")
    B = [("kpis", [{"label": "Custo total", "value": _n(t["custo_total_eur"], 0), "unit": "€"},
                   {"label": "Venda sem IVA", "value": _n(t["receita_eur"], 0), "unit": "€"},
                   {"label": "Margem", "value": _n(t["margem_percent"], 1), "unit": "%", "ok": (t["margem_percent"] or 0) > 0},
                   {"label": "CLT fabricado", "value": _n(t["fabrico_m3"]), "unit": "m³"},
                   {"label": "Prazo", "value": str(plan["dias"]), "unit": "dias"}])]

    # 1. synthesis ---------------------------------------------------------------------------------------------------
    B.append(("h2", "1. Síntese"))
    B.append(("p", "Âmbito: da compra da madeira e do fabrico dos painéis CLT até à entrega da chave: estrutura CLT, vigas de aço, "
                   "revestimentos, isolamentos e estanquidade, caixilharia, eletricidade, canalização e acabamentos. Fora do âmbito: "
                   "betão e lajes de betão, cálculo estrutural, projetos de especialidade e planos de execução. " + estado))
    rows = [[STAGE_NAMES.get(s, s), _n(t["custos_eur"].get(s, 0)), _n(t["custos_eur"].get(s, 0) * 100 / t["custo_total_eur"], 1)]
            for s in STAGE_ORDER if t["custos_eur"].get(s)]
    rows += [["Custo total", _n(t["custo_total_eur"]), "100,0"], ["Venda sem IVA", _n(t["receita_eur"]), ""],
             [f"IVA {_n(t['iva_percent'], 0)} %", _n(t["iva_eur"]), ""], ["Venda com IVA (cliente final)", _n(t["receita_com_iva_eur"]), ""],
             ["Benefício (margem)", _n(t["margem_eur"]), _n(t["margem_percent"], 1) + " % da venda"]]
    B.append(("table", ["Fase", "€", "% do custo"], rows, [100 * W, 45 * W, 35 * W]))
    B.append(("chart", G.barres_h([(STAGE_NAMES.get(s, s), float(t["custos_eur"][s])) for s in STAGE_ORDER if t["custos_eur"].get(s)],
                                  titre="Custo por fase", unite="€"), "Custo direto e indireto por fase, a partir do orçamento linha a linha."))
    ratios = [["Área útil (soma das divisões revistas)", f"{_n(useful)} m²"],
              ["Custo por m² útil", f"{_n(t['custo_total_eur'] / float(useful)) if useful else '—'} €/m²"],
              ["Venda com IVA por m² útil", f"{_n(t['receita_com_iva_eur'] / float(useful)) if useful else '—'} €/m²"],
              ["Custo por m³ de CLT fabricado", f"{_n(t['custo_total_eur'] / t['fabrico_m3']) if t['fabrico_m3'] else '—'} €/m³"]]
    B.append(("table", ["Rácio", "Valor"], ratios, [110 * W, 70 * W]))

    # 2. take-offs -----------------------------------------------------------------------------------------------------
    B.append(("h2", "2. Medições (métrés)"))
    B.append(("p", "Medidas nos planos vetoriais revistos na página CLT: cada troço de parede, cada painel, vão e divisão tem a sua referência "
                   "de leitura. Altura estrutural de cada piso = pé-direito acabado + pavimento + zona do teto falso, medidos no corte."))
    for fl, row in zip(body.floors, r["pisos"]):
        B.append(("p", f"Piso {fl.name} · altura estrutural {_n(fl.height_m, 3)} m"))
        if fl.segments:
            segs = [[s.ref, _n(s.thickness_mm, 0), _n(s.length_m, 3), _n(s.length_m * fl.height_m), _n(s.length_m * fl.height_m * s.thickness_mm / 1000, 3)]
                    for s in fl.segments]
            segs.append(["Total", "", _n(sum((s.length_m for s in fl.segments), Decimal(0)), 3),
                         _n(sum((s.length_m * fl.height_m for s in fl.segments), Decimal(0))),
                         _n(sum((s.length_m * fl.height_m * s.thickness_mm / 1000 for s in fl.segments), Decimal(0)), 3)])
            B.append(("table", ["Troço CLT (ref. de leitura)", "Espessura mm", "Comprimento m", "Área m²", "Volume m³"], segs,
                      [52 * W, 30 * W, 32 * W, 33 * W, 33 * W]))
        walls = [[f"Parede CLT {_n(w.thickness_mm, 0)} mm", str(w.layers), _n(w.length_m, 3), _n(w.length_m * fl.height_m),
                  _n(w.length_m * fl.height_m * w.thickness_mm / 1000, 3)] for w in fl.walls]
        walls += [[e.label or e.kind, str(e.layers), "", _n(e.area_m2), _n(e.area_m2 * e.thickness_mm / 1000, 3)] for e in fl.panels]
        walls.append(["Total CLT do piso", "", "", _n(row["montagem_m2"]), _n(row["fabrico_m3"], 3)])
        B.append(("table", ["Elemento CLT", "Camadas", "Comprimento m", "Área m²", "Volume m³"], walls, [70 * W, 20 * W, 28 * W, 30 * W, 32 * W]))
        if fl.windows:
            rows = []
            for n, w in enumerate(fl.windows, 1):
                height = (Decimal(str(fl.ceiling_height_m or clt_fitout.OPENING_H["vao_envidracado"])) if w.sobre == "viga" else
                          clt_fitout.OPENING_H["lintel"] if w.sobre == "lintel" else clt_fitout.OPENING_H[w.tipo])
                rows.append([f"vão {n}", "vão envidraçado" if w.tipo == "vao_envidracado" else "janela", w.sobre or "—", _n(w.largura_m),
                             _n(height), _n(w.largura_m * height)])
            B.append(("table", ["Vão exterior", "Tipo", "Sob", "Largura m", "Altura m", "Área m²"], rows,
                      [24 * W, 34 * W, 20 * W, 32 * W, 34 * W, 36 * W]))
        if fl.rooms:
            rows = [[rm.nome, rm.tipo.replace("_", " "), _n(rm.area_m2), _n(rm.perimetro_m), ", ".join(rm.aparelhos) or "—"] for rm in fl.rooms]
            B.append(("table", ["Divisão", "Tipo", "Área m²", "Perímetro m", "Aparelhos desenhados"], rows, [40 * W, 28 * W, 22 * W, 24 * W, 66 * W]))
    rows = [[row["piso"], _n(row["placa_m2"]), _n(row["pintura_m2"]), _n(row["teto_m2"]), _n(row["fachada_m2"]), _n(row["laje_betao_m2"]),
             _n(row["cobertura_m2"]), _n(row["viga_aco_m"])] for row in r["pisos"]]
    B.append(("p", "Revestimentos, isolamentos e estrutura complementar"))
    B.append(("table", ["Piso", "Placa BA13 m²", "Pintura m²", "Teto BA15 m²", "Fachada m²", "Laje (isol.) m²", "Cobertura m²", "Aço m"], rows,
              [16 * W, 24 * W, 22 * W, 24 * W, 22 * W, 26 * W, 24 * W, 22 * W]))
    keys = [k for k in FIT_LABELS if any(q.get(k) for q in fit)]
    if keys:
        B.append(("p", "Instalações, caixilharia e acabamentos (motor RTIEBT por divisão e aparelhos DR 23/95)"))
        rows = [[FIT_LABELS[k][0], FIT_LABELS[k][1]] + [_n(q.get(k, 0), 1) for q in fit] + [_n(sum((q.get(k, 0) for q in fit), Decimal(0)), 1)]
                for k in keys]
        widths = [70 * W, 16 * W] + [(94 * W) / (len(fit) + 1)] * (len(fit) + 1)
        B.append(("table", ["Quantidade", "Un."] + [fl.name for fl in body.floors] + ["Total"], rows, widths))
    rows = [[row["piso"], _n(row["fabrico_m3"]), _n(row["madeira_comprada_m3"]), _n(row["adesivo_kg"], 0), _n(row["eletricidade_kwh"], 0),
             _n(row["horas_fabrico"], 1), _n(row["horas_montagem"], 1)] for row in r["pisos"]]
    B.append(("p", f"Matéria-prima e produção · {t['viagens_materia_prima']} viagens de madeira e {t['viagens']} de painéis"))
    B.append(("table", ["Piso", "CLT m³", "Madeira m³", "Cola kg", "Eletricidade kWh", "h fabrico", "h montagem"], rows,
              [20 * W, 24 * W, 26 * W, 24 * W, 30 * W, 26 * W, 30 * W]))
    for text in r["notas_quantidades"]:
        B.append(("p", text))

    # 3. detailed budget ------------------------------------------------------------------------------------------------
    B.append(("h2", "3. Orçamento detalhado (quantidade × preço unitário)"))
    for cat in CATEGORIES:
        lines = [l for l in r["linhas"] if l["categoria"] == cat and l["quantidade"]]
        if not lines:
            continue
        B.append(("p", CATEGORIES[cat][0]))
        rows = [[l["codigo"], l["designacao"], _n(l["quantidade"]), l["unidade"], _n(l["custo_unitario_eur"]),
                 _n(l["custo_eur"]) if l["fase"] != "venda" else "—", _n(l["venda_eur"]) if l["venda_eur"] is not None else "—",
                 ORIGINS.get(l["origem"], l["origem"])] for l in lines]
        B.append(("table", ["Código", "Designação", "Qtd.", "Un.", "€/un.", "Custo €", "Venda €", "Origem"],
                  rows, [28 * W, 50 * W, 17 * W, 10 * W, 15 * W, 20 * W, 20 * W, 20 * W]))

    # 4. cost, profit and sensitivity -------------------------------------------------------------------------------------
    B.append(("h2", "4. Custos, benefício e sensibilidade"))
    rows = [[row["piso"], _n(row["custo_total_eur"]), _n(row["receita_eur"]), _n(row["margem_eur"]), _n(row["margem_percent"], 1)] for row in r["pisos"]]
    rows.append(["Total", _n(t["custo_total_eur"]), _n(t["receita_eur"]), _n(t["margem_eur"]), _n(t["margem_percent"], 1)])
    B.append(("table", ["Piso", "Custo €", "Venda €", "Benefício €", "Margem %"], rows, [36 * W] * 5))

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
    rows = [["Base (este dossier)", _n(t["custo_total_eur"], 0), _n(t["receita_eur"], 0), _n(t["margem_eur"], 0), _n(t["margem_percent"], 1)]]
    for label, change in cases:
        s = _scenario(body, parametros, biblioteca, change)
        rows.append([label, _n(s["custo_total_eur"], 0), _n(s["receita_eur"], 0), _n(s["margem_eur"], 0), _n(s["margem_percent"], 1)])
    B.append(("p", "Sensibilidade: o mesmo cálculo refeito com a variação indicada (venda mantida quando só o custo muda)."))
    B.append(("table", ["Cenário", "Custo €", "Venda €", "Benefício €", "Margem %"], rows, [64 * W, 29 * W, 29 * W, 29 * W, 29 * W]))

    # 5. tracking plan ----------------------------------------------------------------------------------------------------
    B.append(("h2", "5. Plano de seguimento, da fabricação à montagem e à entrega"))
    B.append(("chart", _gantt(plan, 180 * W), "Fases sequenciais em dias de calendário; o lote de seguimento da página CLT parte deste plano."))
    crew_m2 = p["assembly_crew"] * p["work_hours_day"] / p["assembly_h_m2"] if p.get("assembly_h_m2") else None
    work = {"compra": f"{_n(sum(row['madeira_comprada_m3'] for row in r['pisos']))} m³ de madeira, {t['viagens_materia_prima']} viagens",
            "fabrico": f"{_n(t['fabrico_m3'])} m³ de CLT a {_n(p['factory_m3_day'], 1)} m³/dia",
            "transporte": f"{t['viagens']} viagens de {_n(p['truck_m3'], 0)} m³",
            "montagem": f"{_n(t['montagem_m2'])} m² a {_n(crew_m2, 1)} m²/dia ({_n(p['assembly_crew'], 0)} pessoas × {_n(p['work_hours_day'], 0)} h)",
            "acabamentos": f"{sum(len(fl.rooms) for fl in body.floors)} divisões, {sum(len(fl.windows) for fl in body.floors)} vãos"}
    rows = [[STAGE_NAMES.get(f["fase"], f["fase"]), f["inicio"], f["fim"], str(f["dias"]), work.get(f["fase"], "")] for f in plan["fases"]]
    B.append(("table", ["Fase", "Início", "Fim (marco)", "Dias", "Quantidade e ritmo previstos"], rows, [40 * W, 22 * W, 24 * W, 12 * W, 82 * W]))
    curve = _s_curve(plan, t["custos_eur"])
    B.append(("chart", G.courbes([c[0] for c in curve], [("Custo planeado acumulado", [c[2] for c in curve], None)],
                                 titre="Curva de custo planeado", unite="€", xlab="semana"),
              "Cada fase de custo distribuída de forma uniforme pela fase do plano que a gasta; custos indiretos ao longo de toda a obra (hipótese de planeamento)."))
    rows = [[f"S{c[0]}", c[1], _n(c[2], 0), _n(c[2] * 100 / t["custo_total_eur"], 1), "", ""] for c in curve]
    B.append(("table", ["Semana", "Até", "Custo planeado acumulado €", "% planeado", "Custo real €", "% real"], rows,
              [18 * W, 26 * W, 46 * W, 26 * W, 36 * W, 28 * W]))
    lot = lot_from_estimate(titre, r)
    rows = [[l["code"], l["name"], l["stage"], _n(Decimal(l["baseline_qty"])), l["unit"], _n(Decimal(l["rate_eur"])),
             _n(Decimal(l["uncommitted_remaining_eur"])), ""] for l in lot["lines"]]
    B.append(("p", "Folha de controlo do lote de seguimento: o orçamento de cada artigo é a base; a página CLT regista as compras e o realizado "
                   "e calcula o desvio e a previsão de fecho."))
    B.append(("table", ["Código", "Artigo", "Fase", "Qtd. base", "Un.", "€/un.", "Orçamento €", "Real €"], rows,
              [26 * W, 48 * W, 18 * W, 18 * W, 10 * W, 16 * W, 24 * W, 20 * W]))
    B.append(("table", ["Indicador a seguir", "Previsto", "Como medir"], [
        ["Fabrico", f"{_n(p['factory_m3_day'], 1)} m³/dia", "m³ de painéis aprovados por dia na linha"],
        ["Montagem", f"{_n(crew_m2, 1)} m²/dia", "m² de painéis aparafusados por dia de equipa"],
        ["Entregas", f"{t['viagens']} viagens", "guias de transporte"],
        ["Custo comprometido", f"{_n(t['custo_total_eur'], 0)} €", "encomendas e faturas por artigo do lote"],
        ["Margem prevista", f"{_n(t['margem_percent'], 1)} %", "venda − previsão de fecho do lote"]], [40 * W, 40 * W, 100 * W]))

    # 6. hypotheses and sources -------------------------------------------------------------------------------------------
    B.append(("h2", "6. Parâmetros, preços, origens e fontes"))
    rows = [[v["label"], f"{_n(v['value'], 3).rstrip('0').rstrip(',')} {v['unit']}", ORIGINS.get(v["origin"], v["origin"]), (v.get("source") or "")[:110]]
            for v in parametros.values()]
    B.append(("table", ["Parâmetro", "Valor", "Origem", "Fonte ou como confirmar"], rows, [52 * W, 26 * W, 20 * W, 82 * W]))
    used = {l["codigo"] for l in r["linhas"] if l["quantidade"]}
    rows = [[code, i["name"], f"{_n(i['cost_eur'])} €/{i['unit']}", ORIGINS.get(i["origin"], i["origin"]), (i.get("source") or "")[:90]]
            for code, i in biblioteca.items() if code in used]
    B.append(("table", ["Código", "Preço", "Custo", "Origem", "Fonte"], rows, [26 * W, 46 * W, 26 * W, 18 * W, 64 * W]))
    checks = []
    for fl in body.floors:
        if fl.segments:
            a = sum((s.length_m for s in fl.segments), Decimal(0))
            b = sum((w.length_m for w in fl.walls), Decimal(0))
            checks.append([f"Troços medidos = paredes orçamentadas ({fl.name})", f"{_n(a, 3)} / {_n(b, 3)} m", "OK" if abs(a - b) <= b * Decimal("0.02") else "VERIFICAR"])
    lines_sum = sum(l["custo_eur"] for l in r["linhas"])
    checks.append(["Soma das linhas = custo total", f"{_n(lines_sum)} / {_n(t['custo_total_eur'])} €", "OK" if abs(lines_sum - t["custo_total_eur"]) < 1 else "VERIFICAR"])
    checks.append([f"IVA {_n(t['iva_percent'], 0)} % da venda", f"{_n(t['iva_eur'])} €", "OK" if abs(t["receita_eur"] * t["iva_percent"] / 100 - t["iva_eur"]) < 1 else "VERIFICAR"])
    B.append(("p", "Controlos automáticos"))
    B.append(("table", ["Controlo", "Valores", "Resultado"], checks, [100 * W, 55 * W, 25 * W]))

    for title, png, caption in anexos or []:
        B.append(("h2", title))
        pix = pymupdf.Pixmap(png)
        width = 180 * W
        height = min(230 * W, width * pix.height / pix.width)
        B.append(("figure", Image(__import__("io").BytesIO(png), width=height * pix.width / pix.height, height=height), caption))

    hyp = r["hipoteses_por_confirmar"]
    body_pdf = rendu.build_pdf(titre, "Medições, custos, benefício e plano de seguimento · motor ConstruPilot CLT", B + [("h2", "Valores a confirmar pela empresa"), ("hyp", hyp or ["nenhum"])])
    doc = pymupdf.open(stream=body_pdf, filetype="pdf")
    index = []
    for block in B:
        if block[0] == "h2":
            hit = next((n + 2 for n, pg in enumerate(doc) if pg.search_for(block[1][:40])), None)
            if hit:
                index.append((block[1], hit))
    png = doc[0].get_pixmap(dpi=110).tobytes("png")
    capa = {"titulo": titre, "subtitulo": "Dossier completo: medições, custos, benefício e plano de seguimento, da fabricação à entrega da chave.",
            "local": local or "", "data": f"Início previsto {plan['inicio']} · entrega {plan['fim']}",
            "kpis": [("Custo total", _n(t["custo_total_eur"], 0), "€"), ("Venda com IVA", _n(t["receita_com_iva_eur"], 0), "€"),
                     ("Benefício", _n(t["margem_eur"], 0), f"€ · {_n(t['margem_percent'], 1)} % da venda"), ("CLT", _n(t["fabrico_m3"]), "m³ fabricados"),
                     ("Painéis", _n(t["montagem_m2"]), "m² montados"), ("Prazo", str(plan["dias"]), "dias de calendário"),
                     ("Área útil", _n(useful), "m²"), ("Hipóteses", str(len(hyp)), "valores a confirmar")],
            "indice": index, "miniatura_pagina": None, "capa_imagem": capa_imagem}
    pdf = premium.embelezar(body_pdf, capa, premium.marca(empresa) if empresa else None, tr=_tr)
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
