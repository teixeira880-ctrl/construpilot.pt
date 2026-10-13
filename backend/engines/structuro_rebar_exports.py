"""Traceable numerical report; no fabricated execution drawing."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from engines.structuro_rebar import calculate_reinforcement, ReinforcementStudy


def build_rebar_pdf(model, revision=1):
    if model.reinforcement is None and not model.linked_sections:
        raise ValueError("Processo de armaduras ausente")
    inputs = model.reinforcement or ReinforcementStudy(basis="design_draft")
    result = calculate_reinforcement(inputs)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=38, rightMargin=38, topMargin=42, bottomMargin=44)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("SmallRC", parent=styles["BodyText"], fontSize=8.5, leading=12, spaceAfter=5))
    p = lambda text: Paragraph(escape(str(text)), styles["SmallRC"])
    heading = lambda text: Paragraph(escape(str(text)), styles["Heading2"])
    def table(rows, widths):
        t = Table([[p(c) for c in row] for row in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e5eee9")),
            ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#bac9c2")),
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
        return t
    story = [Paragraph("ConstruPilot | Aciers et fondations", styles["Title"]), heading(model.title),
             p(f"Revisão {revision} - {result['engine_version']}"),
             p("Cálculos parciais e controlo documental - NÃO EXECUTÓRIO"),
             p("Revisão dos documentos de origem" if inputs.basis == "source_replay" else "Projeto de dimensionamento"),
             p("Impressão digital das entradas: "+result["input_hash"]), Spacer(1,10), heading("Pontos a resolver")]
    story.extend(p("- "+o) for o in inputs.observations)
    if model.architecture is not None:
        from engines.structuro_calc import calculate
        arch = calculate(model)["architectural_compatibility"]
        story.append(heading("Implantação e alturas - validação global não obtida"))
        story.extend(p(f"{c['element_id']} / {c['label']} : {('CONFLITO' if c['status'] == 'conflict' else 'Controlo local satisfeito')} - {c['summary']} Fonte: {c['source']}") for c in arch["checks"])
        story.extend(p(x) for x in arch["issues"]+arch["unresolved"])
    story += [heading("Verificações restantes")]
    story.extend(p("- "+o) for o in result["unresolved"])
    for source, r in zip(inputs.footings, result["footings"]):
        story += [PageBreak(), heading(f"Sapata {r['id']} - faixa de 1 m"), p(r["source"]),
                  p(f'B={source.width_m:g} m ; parede={source.wall_width_m:g} m ; h={source.h_m:g} m ; d={source.d_m:g} m')]
        if "pressures" in r:
            rows = [["Combinação", "N (kN/m)", "q (kPa)", "Limite (kPa)", "Taxa"]]
            for k,v in r["pressures"].items():
                rows.append([k.replace("_", " "),f"{v['n_kn_m']:.2f}",f"{v['q_kpa']:.2f}",f"{v['limit_kpa']:.2f}",f"{v['utilisation']*100:.1f} %"])
            story += [table(rows,[157,86,86,104,86]), Spacer(1,10),
                p(f"Largura mínima do relatório: {source.min_width_m:g} m. Comparação: {('satisfaite' if r['checks']['width'] else 'NÃO SATISFEITA')}"),
                heading("Tirante transversal - apenas esforço"),
                p(f"Fs,max={r['tie_force_kn_m']:.3f} kN/m ; As,effort={r['as_tie_only_mm2_m']:.2f} mm²/m = {r['as_tie_only_mm2_m']/100:.3f} cm²/m"),
                p(r["pressure_basis"]),p(r["formula"]),
                p("Esta área NÃO é a armadura final a colocar. Não inclui os mínimos e outras verificações indicadas abaixo.")]
        story.extend(p("- "+o) for o in r["issues"])
    for source, r in zip(inputs.sections, result["sections"]):
        story += [PageBreak(),heading(f"Secção {r['id']}"),p(f"Caso: {r['case']}"),p(r["source"]),
                  p(f"b={source.b_mm:g}, h={source.h_mm:g}, d={source.d_mm:g} mm ; MEd={source.med_knm:g} kN.m ; VEd={source.ved_kn:g} kN"),
                  p("Materiais: "+source.materials.source)]
        if "as_required_mm2" in r:
            rows=[["Resultado", "Valor"]]
            for key,label,unit in [("as_flexure_mm2","As flexion","mm²"),("as_min_mm2","As minimum","mm²"),("as_required_mm2","As necessária na secção","mm²"),
                                    ("as_provided_mm2","As disposta","mm²"),("asw_required_mm2_m","Asw/s necessária","mm²/m"),("vrdc_kn","VRd,c","kN"),("vrdmax_kn","VRd,max","kN")]:
                if r.get(key) is not None: rows.append([label,f"{r[key]:.3f} {unit}"])
            story.append(table(rows,[285,234]))
            story.extend(p(f"{k} : {('satisfait' if v else 'NÃO SATISFEITO')}") for k,v in r["checks"].items())
        story.extend(p("- "+o) for o in r["issues"])
    if model.linked_sections:
        from engines.structuro_calc import calculate
        linked = calculate(model)["linked_reinforcement"]
        story += [PageBreak(), heading("Armaduras ligadas aos esforços do modelo"), p(linked["engine_version"]),
                  p("Impressão digital do modelo completo: "+linked["input_hash"]), p(linked["scope"])]
        if linked["status"] == "blocked":
            story += [p("CÁLCULO BLOQUEADO: nenhum esforço nem armadura ligada pode ser considerado.")]
            story.extend(p(i["message"]) for i in linked["issues"])
        for i, section in enumerate(linked["sections"]):
            if i: story.append(PageBreak())
            story += [heading(section["id"]+" / "+section["element_id"]), p(section["source"]),
                      p(f"{section['force_basis']} ; vão {section['span_m']:g} m ; estado {section['status']}")]
            for row in section["cases"]:
                s, r = row["section_input"], row["result"]
                story += [p(f"Caso {row['case_id']} : b={s['b_mm']:g}, h={s['h_mm']:g}, d={s['d_mm']:g} mm ; MEd={s['med_knm']:.3f} kN.m ; VEd={s['ved_kn']:.3f} kN"),
                          p("Materiais: "+s["materials"]["source"])]
                if "as_required_mm2" in r:
                    provided=f"{s['as_provided_mm2']:.2f} mm²" if s['as_provided_mm2'] is not None else "não preenchido"
                    story.append(p(f"As necessária: {r['as_required_mm2']:.2f} mm² ; As fornecida: {provided}"))
                if "vrdc_kn" in r: story.append(p(f"VRd,c : {r['vrdc_kn']:.3f} kN"))
                if "asw_required_mm2_m" in r: story.append(p(f"Asw/s necessária: {r['asw_required_mm2_m']:.2f} mm²/m"))
                labels={"area_at_least_required":"Área de armaduras suficiente", "area_below_four_percent":"Limite superior de armaduras",
                        "provided_section_in_domain":"Domínio da secção armada", "shear_without_links":"Esforço transverso sem estribos",
                        "strut_crushing":"Compressão das bielas"}
                story.extend(p(f"{labels.get(k, k)} : {('satisfeito para este controlo' if v else 'NÃO SATISFEITO')}") for k,v in r["checks"].items())
                story.extend(p("- "+o) for o in r["issues"])
    for r in result["schedules"]:
        story += [PageBreak(),heading(f"Nomenclature {r['id']}"),p(r["basis"]),p(r["source"]),p(r["note"])]
        rows=[["Referência", "Ø (mm)", "Número", "Comp. unitário (m)", "Comp. total (m)", "Peso (kg)"]]
        for b in r["bars"]:
            rows.append([b["mark"],f"{b['diameter_mm']:g}",b["count"],f"{b['developed_length_m']:.3f}",f"{b['total_length_m']:.3f}",f"{b['mass_kg']:.3f}"])
        story += [table(rows,[68,63,63,105,110,110]),Spacer(1,12),p(f"Total recalculado sem desperdícios: {r['total_kg']:.3f} kg")]
        if r["source_total_kg"] is not None:
            story.append(p(f"Total impresso na origem: {r['source_total_kg']:.3f} kg ; desvio: {r['delta_kg']:+.3f} kg"))
        story.extend(p(f"Referência {b['mark']} : {b['description']}") for b in r["bars"])
    story += [PageBreak(),heading("Documentos e versão dos dados")]
    for i, s in enumerate(inputs.sources):
        if i and i % 9 == 0:
            story += [PageBreak(),heading("Documentos e versão dos dados (continuação)")]
        story += [p(f"{s.filename} | {s.pages} page(s) | {s.revision}"),p("SHA-256 : "+s.sha256)]
    story += [heading("Referência dos subcálculos"),p("JRC EUR 26566 EN (2014), capítulos 3 e 4. Fórmulas da primeira geração do EC2; este módulo não constitui um pacote normativo completo qualificado."),
              p("https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/1110_WS_EC2.pdf")]
    def footer(c,d):
        c.saveState(); c.setFont("Helvetica-Bold",8); c.setFillColor(colors.HexColor("#943e29"))
        c.drawString(38,24,"CÁLCULOS PARCIAIS - NÃO EXECUTÓRIO"); c.drawRightString(A4[0]-38,24,f'Rev. {revision} | {d.page}'); c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
