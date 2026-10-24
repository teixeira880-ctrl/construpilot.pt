"""Reproducible calculation trace accompanying automatically drawn reinforcement."""
import io
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from engines.structuro_automation import generation_hash


def build_automation_pdf(model,report,revision):
    if report.get('generation_hash')!=generation_hash(model):raise ValueError("Relatório automático desatualizado")
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=38,rightMargin=38,topMargin=42,bottomMargin=46)
    styles=getSampleStyleSheet();styles.add(ParagraphStyle('Small',fontName='Helvetica',fontSize=8,leading=11))
    p=lambda x:Paragraph(escape(str(x)),styles['Small'])
    story=[Paragraph('ConstruPilot | Cadeia automática',styles['Title']),p(model.title),p(f"Revisão {revision} | {report['engine_version']}"),
        p("Impressão digital: "+report['generation_hash']),Spacer(1,12),Paragraph("ESTUDO PARCIAL - NÃO EXECUTÓRIO",styles['Heading2'])]
    story.extend(p(t) for t in report['limits'])
    story+=[Spacer(1,10),p("O motor escolhe disposições no catálogo introduzido. Os cálculos locais não validam a estrutura completa, o solo nem as ligações."),
        p("Os comprimentos de amarração são exigências calculadas: os varões retos desenhados não representam por si só a sua execução nos apoios.")]
    def table(rows,widths):
        t=Table([[p(v) for v in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4efe8')),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#bbc9c2')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));return t
    story+=[Spacer(1,12),Paragraph("Cobertura do projeto",styles['Heading2']),table([["Elemento","Natureza","Cálculo realizado"]]+[[r['element_id'],r['kind'],{'local_checks_only':"Controlos locais + varões gerados",'bearing_area_only':"Apenas área de apoio",'not_designed':"Não dimensionado",'blocked':"Geração bloqueada"}.get(r['status'],r['status'])] for r in report['coverage']],[85,90,340])]
    if report['issues']:
        story+=[Spacer(1,12),Paragraph("Pontos por resolver",styles['Heading2'])]
        story.extend(p(f"{r['element']} / {r['stage']} : {r['message']}") for r in report['issues'])
    s=model.automation_settings
    story+=[PageBreak(),Paragraph("Dados e regras aplicados",styles['Heading1']),p(s.source)]
    data=s.materials.model_dump()
    story.append(table([["Parâmetro","Valor"]]+[[k,v] for k,v in data.items()]+[["Recobrimento (mm)",s.cover_mm],['Granulat (mm)',s.aggregate_mm],['fctk,0.05 (MPa)',s.fctk005_mpa],['eta1',s.bond_eta1],['cot(theta)',s.cot_theta],["Combinações ELU",', '.join(s.uls_case_ids)],["Diâmetros (mm)",str(s.diameters_mm)],["Diâmetros dos estribos (mm)",str(s.stirrup_diameters_mm)],["Espaçamentos do catálogo (mm)",str(s.spacings_mm)]],[190,325]))
    for r in report['designs']:
        story += [PageBreak(),Paragraph(escape(r['element_id'])+" | aço escolhido automaticamente",styles['Heading1'])]
        if r['kind']=='beam':
            story.append(p(f"{r['count']} HA{r['diameter_mm']} ; As colocado {r['as_provided_mm2']:.2f} mm² ; As necessário {r['as_required_mm2']:.2f} mm² ; d real {r['d_mm']:.2f} mm."))
            story.append(p(f"Estribos de 2 ramos Ø{r['stirrup_diameter_mm']} : {r['stirrup_count']} peças, espaçamento real {r['stirrup_spacing_mm']:.2f} mm. Asw/s colocado {r['asw_provided_mm2_m']:.2f}, requis {r['asw_required_mm2_m']:.2f} mm²/m."))
        else:
            story.append(p(f"Direção {r['span_axis'].upper()}, vão convencional {r['span_m']:.3f} m. Malha principal: {r['count']} HA{r['diameter_mm']}, espaçamento {r['spacing_mm']:.2f} mm ; As/m colocado {r['as_provided_mm2_m']:.2f}, requis {r['as_required_mm2_m']:.2f} mm²/m ; d real {r['d_mm']:.2f} mm."))
            story.append(p(f"Distribuição: Ø{r['distribution_diameter_mm']}, espaçamento {r['distribution_spacing_mm']:.2f} mm."))
        story.append(p("Apenas faces tracionadas positivas. Os aços superiores das vigas servem para montagem; não cobrem momentos negativos."))
        story += [Spacer(1,12),table([["Caso",'M (kN.m)','V (kN)',"As necessário (mm²)",'MRd (kN.m)']]+[[c['case_id'],f"{c['input']['med_knm']:.3f}",f"{c['input']['ved_kn']:.3f}",f"{c['result']['as_required_mm2']:.2f}",f"{c['result']['mrd_provided_knm']:.3f}"] for c in r['cases']],[70,100,90,130,125])]
        for case in r['cases']:
            names={'area_at_least_required':"Aço fornecido suficiente",'area_below_four_percent':"Taxa máxima",'provided_section_in_domain':"Domínio da secção",'shear_without_links':"Corte sem estribos",'strut_crushing':"Escora comprimida"}
            story.append(p(case['case_id']+' : '+', '.join(names.get(k,k)+(': satisfeito' if v else ": NÃO SATISFEITO") for k,v in case['result']['checks'].items())))
        a=r['anchorage'];story += [Spacer(1,12),Paragraph("Amarração e emenda calculadas",styles['Heading2']),
            p(f"fbd = {a['fbd_mpa']:.3f} MPa ; sigma_sd = {a['sigma_sd_mpa']:.3f} MPa ; lb,rqd = {a['lb_rqd_mm']:.1f} mm."),
            p(f"lbd arredondado por excesso = {a['lbd_mm']} mm ; emenda majorada alpha6=1,5 = {a['lap_mm']} mm."),
            p(f"Comprimento disponível declarado: {(a['available_mm'] if a['available_mm'] is not None else 'inconnue')} mm ; comparação: {dict(unknown='não indicado', sufficient_declared_length='comprimento declarado suficiente', insufficient_declared_length='comprimento declarado insuficiente')[a['length_comparison']]}."),
            p("Fórmulas: fbd=2,25 eta1 fctk,0.05/gamma_c ; lb,rqd=phi sigma_sd/(4 fbd) ; lbd=max(lb,rqd ; 0,3 lb,rqd ; 10 phi ; 100 mm). Nenhuma redução por confinamento. Emenda max(1,5 lb,rqd ; 0,45 lb,rqd ; 15 phi ; 200 mm)."),
            p("O cálculo do comprimento não valida nem os apoios, nem a posição das interrupções, nem o congestionamento ou as armaduras transversais de emenda.")]
        story += [Spacer(1,10),table([["Marca reta","Diâmetro (mm)",'lbd (mm)',"Emenda (mm)"]]+[[v['mark'],v['diameter_mm'],v['lbd_mm'],v['lap_mm']] for v in r['straight_bar_anchorage']],[230,90,90,105])]
    for r in report['foundations']:
        story += [PageBreak(),Paragraph(escape(r['element_id'])+" | pesquisa de área de apoio",styles['Heading1']),p(r['soil_source']),
            p(f"Dimensões anteriores {r['old_dimensions_m']} m ; dimensões propostas {r['new_dimensions_m']} m. Centro e espessura conservados."),
            p("Cada ensaio conserva as outras cargas e substitui o peso próprio pelo da nova área, com o coeficiente G de cada combinação. A descida de cargas é depois recalculada."),Spacer(1,10),
            table([["Caso",'N total (kN)','q (kPa)','Limite (kPa)']]+[[c['case_id'],f"{c['total_kn']:.3f}",f"{c['q_kpa']:.3f}",f"{c['limit_kpa']:.3f}"] for c in r['cases']],[90,140,140,145])]
        story.extend(p(t) for t in r['unresolved'])
    story += [Spacer(1,16),Paragraph("Base documental e limites de qualificação",styles['Heading2']),p("Comissão Europeia / JRC, EUR 26566 EN, Eurocode 2: Background & Applications, Design of Concrete Buildings - Worked examples (2014), capítulos 3 e 4. Base de primeira geração utilizada para estes subcálculos; não constitui uma verificação de conformidade com as normas/anexos nacionais atualmente aplicáveis."),p('https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/1110_WS_EC2.pdf')]
    def footer(c,doc):
        c.saveState();c.setFont('Helvetica-Bold',8);c.setFillColor(colors.HexColor('#a33d2f'))
        c.drawString(38,25,"NÃO EXECUTÓRIO - APENAS CONTROLOS LOCAIS");c.drawRightString(557,25,f'Rev. {revision} | {doc.page}');c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
