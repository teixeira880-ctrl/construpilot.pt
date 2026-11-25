"""Relatório PDF da avaliação preliminar de viabilidade construtiva (ReportLab + figuras matplotlib)."""
from __future__ import annotations

import io
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from engines.mdt_pt import analise as AN
from engines.mdt_pt import pttm06 as TM

VERDE = "#0f6e4f"
CORES_NIVEL = {"baixo": "#1a9850", "moderado": "#e0a800", "elevado": "#e8590c", "muito_elevado": "#c92a2a",
               "por_confirmar": "#868e96"}
CORES_CLASSE = {"viavel": "#1a9850", "viavel_com_condicionantes": "#e0a800", "condicionada": "#e8590c",
                "inviavel_provavel": "#c92a2a"}


def _n(v, d=0, u="") -> str:
    if v is None:
        return "—"
    try:
        t = f"{float(v):,.{d}f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return str(v)
    return f"{t}{(' ' + u) if u else ''}"


def _fig_png(fig) -> bytes:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return b.getvalue()


def figura_planta(res: Dict[str, Any]) -> Optional[bytes]:
    """Planta: sombreado do MDT, curvas, limite, zona livre, linhas de água e implantação recomendada."""
    it = res.get("_interno") or {}
    r = it.get("r")
    if r is None:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    anel = np.asarray(it["anel_tm"])
    pad = 25.0
    x0, x1 = anel[:, 0].min() - pad, anel[:, 0].max() + pad
    y0, y1 = anel[:, 1].min() - pad, anel[:, 1].max() + pad
    hs = AN.sombreado(r)
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    ax.imshow(hs, cmap="gray", extent=(r.x0, r.x1, r.y1, r.y0), alpha=0.9, vmin=0, vmax=1)
    z = AN._preencher_nan(r.z.astype(np.float64))
    xc, yc = AN.centros(r)
    desn = float(np.nanmax(z) - np.nanmin(z))
    eq = AN.equidistancia_auto(desn / 2 if desn > 0 else 1)
    cs = ax.contour(xc, yc, z, levels=np.arange(math.floor(z.min()), math.ceil(z.max()) + eq, eq), colors="#8c6d46",
                    linewidths=0.4)
    ax.clabel(cs, fontsize=5, fmt="%.0f")
    for k, a in enumerate(it.get("zona_livre_tm") or []):
        a = np.asarray(a)
        ax.fill(a[:, 0], a[:, 1], color="#40c057", alpha=0.25, label="Zona livre para edificar" if k == 0 else None)
    for k, l in enumerate((res.get("relevo") or {}).get("linhas_agua") or []):
        ll = np.asarray(l["latlon"])
        x, y = TM.para_tm(ll[:, 0], ll[:, 1])
        ax.plot(x, y, color="#1c7ed6", lw=1.2, label="Linha de água potencial (MDT)" if k == 0 else None)
    p = np.vstack([anel, anel[:1]])
    ax.plot(p[:, 0], p[:, 1], color="#c92a2a", lw=1.8, label="Limite do terreno")
    impl = it.get("impl") or {}
    if impl.get("ok"):
        q = np.asarray(impl["poligono_tm"])
        q = np.vstack([q, q[:1]])
        ax.fill(q[:, 0], q[:, 1], color=VERDE, alpha=0.8, label="Implantação recomendada")
        c = impl["centro_tm"]
        az = math.radians(impl["azimute_fachada_principal"])
        L = max(impl["largura_m"], impl["profundidade_m"]) * 0.9
        ax.annotate("", xy=(c[0] + L * math.sin(az), c[1] + L * math.cos(az)), xytext=(c[0], c[1]),
                    arrowprops=dict(arrowstyle="->", color="#f59f00", lw=1.6))
    ac = res.get("acessibilidade") or {}
    if ac.get("ponto_via_latlon"):
        vx, vy = TM.ponto_tm(*ac["ponto_via_latlon"])
        ax.plot(vx, vy, "s", color="#495057", ms=6, label=f"Via: {ac.get('via') or ac.get('tipo_via') or 'acesso'}")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xlabel("M (m) PT-TM06", fontsize=7)
    ax.set_ylabel("P (m) PT-TM06", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.annotate("N", xy=(0.95, 0.95), xytext=(0.95, 0.86), xycoords="axes fraction", ha="center", fontsize=9,
                arrowprops=dict(arrowstyle="-|>", color="black"))
    ax.legend(loc="lower left", fontsize=6, framealpha=0.85)
    return _fig_png(fig)


def figura_solar(res: Dict[str, Any]) -> Optional[bytes]:
    sol = res.get("solar") or {}
    if not sol.get("horizonte_centro"):
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    hz = sol["horizonte_centro"]
    az = [h["azimute"] for h in hz] + [360]
    an = [h["angulo"] for h in hz] + [hz[0]["angulo"]]
    ax.fill_between(az, 0, an, color="#868e96", alpha=0.6, label="Horizonte (relevo + edifícios)")
    for t, cor in zip(sol.get("trajetorias") or [], ("#e8590c", "#f59f00", "#1c7ed6")):
        ax.plot([p["azimute"] for p in t["pontos"]], [p["altura"] for p in t["pontos"]], color=cor, lw=1.4, label=t["dia"])
    ax.set_xlim(45, 315)
    ax.set_ylim(0, 80)
    ax.set_xticks([45, 90, 135, 180, 225, 270, 315])
    ax.set_xticklabels(["NE", "E", "SE", "S", "SO", "O", "NO"], fontsize=7)
    ax.set_ylabel("altura do sol (°)", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=6, loc="upper right")
    return _fig_png(fig)


def pdf(res: Dict[str, Any], nome: str = "", empresa: Optional[Dict[str, str]] = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from xml.sax.saxutils import escape as esc

    # DejaVu incorporada: m², m³, °, ≥ e acentos iguais em qualquer leitor de PDF
    try:
        from engines import pdf_fonts as PF
        PF._register()
        FN, FB = PF.CYR, PF.CYR_BOLD
    except Exception:  # noqa: BLE001
        FN, FB = "Helvetica", "Helvetica-Bold"
    emp = empresa or {}
    cor = emp.get("cor") if (emp.get("cor") or "").startswith("#") and len(emp.get("cor")) == 7 else VERDE
    nome_emp = emp.get("nome") or "ConstruPilot"
    st = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=st["Heading1"], fontName=FB, textColor=colors.HexColor(cor), fontSize=17, spaceAfter=6)
    H2 = ParagraphStyle("h2", parent=st["Heading2"], fontName=FB, textColor=colors.HexColor(cor), fontSize=12.5, spaceBefore=10, spaceAfter=4)
    P = ParagraphStyle("p", parent=st["BodyText"], fontName=FN, fontSize=8.8, leading=11.5, alignment=TA_LEFT)
    PS = ParagraphStyle("ps", parent=P, fontSize=7.2, leading=9, textColor=colors.HexColor("#555555"))

    def p(t, s=P):
        return Paragraph(esc(str(t)), s)

    def tabela(linhas, larg=(6.2 * cm, 11 * cm), cab=False):
        dados = [[p(a), p(b)] if not isinstance(b, Paragraph) else [p(a), b] for a, b in linhas]
        t = Table(dados, colWidths=larg)
        estilo = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ced4da")),
                  ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f3f5"))]
        if cab:
            estilo.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dee2e6")))
        t.setStyle(TableStyle(estilo))
        return t

    data = datetime.now().strftime("%d/%m/%Y")
    buf = io.BytesIO()

    def rodape(c, d):
        c.saveState()
        c.setFillColor(colors.HexColor(cor))
        c.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FB, 10.5)
        c.drawString(1.5 * cm, A4[1] - 0.72 * cm, f"{nome_emp} · Viabilidade construtiva do terreno")
        c.setFont(FN, 8)
        c.drawRightString(A4[0] - 1.5 * cm, A4[1] - 0.72 * cm, f"{data} · página {d.page}")
        c.setFillColor(colors.HexColor("#666666"))
        c.setFont(FN, 6.5)
        c.drawString(1.5 * cm, 0.8 * cm, "Avaliação preliminar automática — não substitui a informação prévia da câmara, "
                                          "o levantamento topográfico nem o estudo geotécnico.")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.7 * cm,
                            bottomMargin=1.4 * cm, title="Viabilidade construtiva", author=nome_emp)
    E: List[Any] = []
    ter = res["terreno"]
    via = res["viabilidade"]
    E.append(Paragraph("Avaliação preliminar da viabilidade construtiva", H1))
    E.append(p(f"{nome or 'Terreno'} · {_n(ter['area_m2'], 0, 'm²')} · centroide {ter['centroide'][0]:.6f}, {ter['centroide'][1]:.6f} "
               f"(PT-TM06 M {_n(ter['centroide_tm06'][0], 2)} / P {_n(ter['centroide_tm06'][1], 2)})"))
    E.append(Spacer(1, 6))
    caixa = Table([[Paragraph(f"<b>{esc(via['rotulo'])}</b> — índice {int(via['indice'])}/100", ParagraphStyle(
        "cx", parent=P, fontSize=12, textColor=colors.white))]], colWidths=[18 * cm])
    caixa.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(CORES_CLASSE.get(via["classificacao"], cor))),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    E.append(caixa)
    E.append(Spacer(1, 4))
    for f in via["fundamentos"]:
        cor_f = {"critico": "#c92a2a", "aviso": "#e8590c", "ok": "#1a9850", "info": "#495057"}.get(f["nivel"], "#495057")
        rot_f = {"critico": "Impeditivo", "aviso": "Atenção", "ok": "Favorável", "info": "Informação"}.get(f["nivel"], "")
        E.append(Paragraph(f"<b><font color='{cor_f}'>{rot_f}:</font></b> {esc(f['texto'])}", P))
    planta = figura_planta(res)
    if planta:
        E.append(Spacer(1, 6))
        E.append(Image(io.BytesIO(planta), width=15.5 * cm, height=12.9 * cm))

    # 1 — características físicas
    rel = res["relevo"]
    E.append(PageBreak())
    E.append(Paragraph("1. Características físicas", H2))
    mdt = res["mdt"]
    E.append(tabela([
        ("Modelo digital do terreno", f"{mdt.get('fonte')} — resolução de análise {_n(mdt.get('resolucao_analise_m'), 1, 'm')}"
                                      f"{'' if mdt.get('oficial') else ' (indicativo)'}"),
        ("Altitude mín. / média / máx.", f"{_n(rel['cota_min'], 2)} / {_n(rel['cota_media'], 2)} / {_n(rel['cota_max'], 2)} m"),
        ("Desnível no terreno", _n(rel["desnivel"], 2, "m")),
        ("Declive médio / máximo (p99)", f"{_n(rel['declive_medio_pct'], 1)} % / {_n(rel['declive_max_pct'], 1)} %"),
        ("Orientação das vertentes", f"dominante {rel.get('exposicao')} — " + ", ".join(
            f"{e['setor']} {_n(e['pct'], 0)} %" for e in rel["exposicao_setores"] if e["pct"] >= 5)),
        ("Forma do relevo", "; ".join(f"{e['descricao'].split(' — ')[0]} {_n(e['pct'], 0)} %" for e in rel["formas"][:3])),
        ("Rugosidade média", _n(rel.get("rugosidade_m"), 2, "m")),
        ("Linhas de água potenciais", f"{len(rel.get('linhas_agua') or [])} troço(s) com bacia ≥ {_n(rel.get('limiar_linha_agua_m2'), 0, 'm²')}"),
    ]))
    E.append(Spacer(1, 4))
    E.append(tabela([(c["classe"], f"{_n(c['pct'], 1)} % · {_n(c['area_m2'], 0, 'm²')}") for c in rel["classes_declive"]],
                    larg=(6.2 * cm, 11 * cm)))
    sol = res["solar"]
    E.append(Paragraph("Radiação solar e sombreamento", H2))
    E.append(tabela([
        ("Irradiação anual no terreno", f"{_n(sol['irradiacao_anual_kwh_m2']['media'], 0)} kWh/m² (mín. {_n(sol['irradiacao_anual_kwh_m2']['min'], 0)}, "
                                        f"máx. {_n(sol['irradiacao_anual_kwh_m2']['max'], 0)}) — referência horizontal desafogada "
                                        f"{_n(sol['referencia_horizontal_livre_kwh_m2'], 0)} kWh/m²"),
        ("Índice solar do terreno", f"{_n(sol['indice_solar_pct'], 0)} %"),
        ("Horas de sol a 21 de dezembro", f"{_n(sol['horas_sol_21dez']['media'], 1)} h de {_n(sol['horas_sol_21dez']['duracao_dia'], 1)} h de dia"),
        ("Horas de sol a 21 de junho", _n(sol["horas_sol_21jun"]["media"], 1, "h")),
        ("Horizonte a sul / céu visível", f"{_n(sol['horizonte_sul_graus'], 1)}° / {_n(sol['ceu_visivel'] * 100, 0)} %"),
    ] + ([("Relevo longínquo (até 1,4 km)", f"incluído — horizonte a sul {_n(sol['horizonte_distante']['sul_graus'], 1)}°, "
                                              f"máximo {_n(sol['horizonte_distante']['max_graus'], 1)}°")]
         if sol.get("horizonte_distante") else [])
       + ([("Irradiação real média (PVGIS)", f"{_n(sol['pvgis']['anual_kwh_m2'], 0)} kWh/m²·ano no plano horizontal "
                                              f"({sol['pvgis']['periodo']}, com nebulosidade e horizonte)")]
          if sol.get("pvgis") else [])))
    fs = figura_solar(res)
    if fs:
        E.append(Image(io.BytesIO(fs), width=15.5 * cm, height=6.6 * cm))
    E.append(p(sol["fonte"], PS))
    ac = res["acessibilidade"]
    E.append(Paragraph("Acessibilidade", H2))
    if ac.get("ok"):
        pc = ac.get("percurso_implantacao") or {}
        E.append(tabela([("Via de acesso", f"{ac.get('via') or '(sem nome)'} — {ac.get('tipo_via') or ''}"),
                         ("Situação", ac["texto"]),
                         ("Percurso via → implantação", f"{_n(pc.get('comprimento_m'), 0, 'm')}, desnível {_n(pc.get('desnivel_m'), 1, 'm')}, "
                                                        f"declive médio {_n(pc.get('declive_medio_pct'), 1)} % (máx. {_n(pc.get('declive_max_pct'), 0)} %)"),
                         ("Fonte", ac.get("fonte") or "")]))
    else:
        E.append(p("Por confirmar — " + (ac.get("nota") or "")))

    # 2 — ordenamento
    o = res["ordenamento"]
    E.append(Paragraph("2. Condicionantes territoriais e legais", H2))
    so, cd, pt = o["solo"], o["condicionantes"], o["potencial"]
    E.append(tabela([
        ("PDM — classificação do solo", f"{so['solo']} · {so.get('categoria') or so.get('classe') or '—'}"
                                        f"{' (' + _n((so.get('fracao') or 0) * 100, 0) + ' % do terreno)' if so.get('fracao') else ''}"),
        ("REN", f"{_n(cd['ren']['fracao'] * 100, 1)} % do terreno" + (f" — {', '.join(cd['ren']['temas'][:3])}" if cd["ren"]["temas"] else "")),
        ("RAN", f"{_n(cd['ran']['fracao'] * 100, 1)} % do terreno" + (f" — {', '.join(cd['ran']['temas'][:3])}" if cd["ran"]["temas"] else "")),
        ("Domínio hídrico", "; ".join(f"{e['titulo']} a {_n(e['distancia_m'], 0, 'm')}" for e in cd["dominio_hidrico"]) or "nenhum cartografado"),
        ("Servidões e restrições", "; ".join(e["titulo"] for e in cd["servidoes"]) or "nenhuma cartografada no terreno"),
        ("Temas por confirmar", ", ".join(cd["por_confirmar"][:8]) or "—"),
    ]))
    E.append(Paragraph("Potencial construtivo", H2))
    af = o["afastamentos"]
    E.append(tabela([
        ("Área do terreno", _n(pt["area_terreno_m2"], 0, "m²")),
        ("Área livre para implantação", _n(pt["area_livre_para_implantacao_m2"], 0, "m²")),
        ("Afastamentos aplicados", f"frontal {_n(af['valores_m']['frontal'], 1)} m · lateral {_n(af['valores_m']['lateral'], 1)} m · "
                                   f"tardoz {_n(af['valores_m']['tardoz'], 1)} m"),
        ("Área de implantação máxima", _n(pt["area_implantacao_max_m2"], 0, "m²")),
        ("Área de construção máxima", _n(pt["area_construcao_max_m2"], 0, "m²")),
        ("N.º máximo de pisos / cércea", f"{pt.get('n_pisos_max') or '—'} / {_n(pt.get('altura_fachada_max_m'), 1, 'm')}"),
        ("Parâmetros em falta", ", ".join(pt["em_falta"]) or "—"),
    ]))
    E.append(p(pt["nota"] + " " + af["nota"], PS))
    if res.get("verificacao_edificio"):
        E.append(tabela([("Verificação", "Proposto / limite")] +
                        [(v["item"], f"{_n(v['valor'], 1)} / {_n(v['limite'], 1)} — {v['resultado'].replace('_', ' ')}")
                         for v in res["verificacao_edificio"]], cab=True))

    # 3 — riscos
    E.append(Paragraph("3. Riscos naturais", H2))
    nomes = {"incendio_rural": "Incêndio rural", "cheias_inundacoes": "Cheias e inundações", "erosao_hidrica": "Erosão hídrica",
             "movimentos_vertente": "Movimentos de vertente"}
    linhas = []
    for e in res["riscos"]["riscos"]:
        of = e.get("cartografia_oficial")
        if of and of.get("temas"):
            of_txt = ", ".join(of["temas"][:3])
        else:
            of_txt = "sem afetação publicada" if of else "por confirmar"
        txt = (f"<b><font color='{CORES_NIVEL[e['nivel']]}'>{esc(e['rotulo'])}</font></b> — cartografia: {esc(of_txt)}; "
               f"MDT: {esc(e['suscetibilidade_mdt']['nivel'].replace('_', ' '))}")
        if e["recomendacoes"]:
            txt += "<br/>" + "<br/>".join("• " + esc(x) for x in e["recomendacoes"][:3])
        linhas.append((nomes.get(e["risco"], e["risco"]), Paragraph(txt, P)))
    E.append(tabela(linhas))
    E.append(p(res["riscos"]["nota"], PS))

    # 4 — conforto
    cf = res["conforto"]
    E.append(Paragraph("4. Conforto térmico e sustentabilidade", H2))
    fa = cf["irradiacao_fachadas"]
    t = Table([["Fachada"] + list(fa.keys()),
               ["Verão (kWh/m²)"] + [_n(v["verao_kwh_m2"], 0) for v in fa.values()],
               ["Inverno (kWh/m²)"] + [_n(v["inverno_kwh_m2"], 0) for v in fa.values()]],
              colWidths=[3.4 * cm] + [1.7 * cm] * 8)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ced4da")),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dee2e6")), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("FONTNAME", (0, 0), (-1, -1), FN)]))
    E.append(t)
    E.append(Spacer(1, 4))
    E.append(tabela([
        ("Orientação recomendada", cf["orientacao_recomendada"]["texto"]),
        ("Sombreamento de inverno", f"{cf['sombreamento']['nivel_inverno']} (horizonte a sul {_n(cf['sombreamento']['horizonte_sul_graus'], 1)}°)"),
        ("Zona climática (REH)", (f"{cf['clima_reh']['zona_inverno']} / {cf['clima_reh']['zona_verao']} — NUTS III {cf['clima_reh']['nuts3']}, "
                                  f"{_n(cf['clima_reh']['graus_dia'], 0)} graus-dia, θext,v {_n(cf['clima_reh']['theta_ext_verao'], 1)} °C")
                                 if (cf.get("clima_reh") or {}).get("ok") else "por confirmar no projeto térmico"),
        ("Ventilação natural", cf["ventilacao"]["recomendacao"]
         + (f" (vento medido: {cf['ventilacao']['fonte']}, {cf['ventilacao']['periodo']})" if cf["ventilacao"].get("medido") else "")),
        ("Potencial de sobreaquecimento", f"{cf['sobreaquecimento']['nivel']} (índice {_n(cf['sobreaquecimento']['indice'], 2)})"),
    ]))
    E.append(p(cf["nota"], PS))

    # 5 — implantação e recomendações
    E.append(Paragraph("5. Implantação recomendada", H2))
    im = res["implantacao"]
    if im.get("ok"):
        mv = im["movimento_terras"]
        E.append(tabela([
            ("Edifício", f"{_n(im['largura_m'], 1)} × {_n(im['profundidade_m'], 1)} m · {im.get('n_pisos')} piso(s) · {im.get('origem_dimensoes')}"),
            ("Posição (centro)", f"{im['centro_latlon'][0]:.6f}, {im['centro_latlon'][1]:.6f} · PT-TM06 M {_n(im['centro_tm'][0], 2)} / P {_n(im['centro_tm'][1], 2)}"),
            ("Fachada principal", f"virada a {_rumo(im['azimute_fachada_principal'])} ({_n(im['azimute_fachada_principal'], 0)}°)"),
            ("Cota de soleira sugerida", _n(im["cota_soleira_sugerida"], 2, "m")),
            ("Terreno sob o edifício", f"cotas {_n(im['terreno_sob_edificio']['cota_min'], 2)}–{_n(im['terreno_sob_edificio']['cota_max'], 2)} m, "
                                       f"declive médio {_n(im['terreno_sob_edificio']['declive_medio_pct'], 1)} % → {im['solucao_desnivel']}"),
            ("Movimento de terras", f"escavação {_n(mv.get('escavacao_m3'), 0, 'm³')} · aterro {_n(mv.get('aterro_m3'), 0, 'm³')}"),
        ]))
    else:
        E.append(p(im.get("nota") or "Sem implantação possível."))
    E.append(Paragraph("Recomendações", H2))
    for r_ in res["recomendacoes"]:
        E.append(p("• " + r_))
    E.append(Spacer(1, 8))
    E.append(p(res["aviso_legal"], PS))
    doc.build(E, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()


def _rumo(az):
    from .solar import rumo
    return rumo(az)
