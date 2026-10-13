"""Reproducible calculation trace accompanying automatically drawn reinforcement."""
import io
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from engines.structuro_automation import generation_hash


def build_automation_pdf(model,report,revision):
    if report.get('generation_hash')!=generation_hash(model):raise ValueError('Rapport automatique périmé')
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=38,rightMargin=38,topMargin=42,bottomMargin=46)
    styles=getSampleStyleSheet();styles.add(ParagraphStyle('Small',fontName='Helvetica',fontSize=8,leading=11))
    p=lambda x:Paragraph(escape(str(x)),styles['Small'])
    story=[Paragraph('ConstruPilot | Chaîne automatique',styles['Title']),p(model.title),p(f"Révision {revision} | {report['engine_version']}"),
        p('Empreinte : '+report['generation_hash']),Spacer(1,12),Paragraph('ÉTUDE PARTIELLE - NON EXÉCUTOIRE',styles['Heading2'])]
    story.extend(p(t) for t in report['limits'])
    story+=[Spacer(1,10),p('Le moteur choisit des dispositions dans le catalogue saisi. Les calculs locaux ne valident pas la structure complète, le sol ni les assemblages.'),
        p('Les longueurs d’ancrage sont des exigences calculées : les barres droites dessinées ne représentent pas à elles seules leur réalisation dans les appuis.')]
    def table(rows,widths):
        t=Table([[p(v) for v in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4efe8')),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#bbc9c2')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));return t
    story+=[Spacer(1,12),Paragraph('Couverture du projet',styles['Heading2']),table([['Élément','Nature','Calcul réalisé']]+[[r['element_id'],r['kind'],{'local_checks_only':'Contrôles locaux + barres générées','bearing_area_only':'Surface portante seule','not_designed':'Non dimensionné','blocked':'Génération bloquée'}.get(r['status'],r['status'])] for r in report['coverage']],[85,90,340])]
    if report['issues']:
        story+=[Spacer(1,12),Paragraph('Points restant à résoudre',styles['Heading2'])]
        story.extend(p(f"{r['element']} / {r['stage']} : {r['message']}") for r in report['issues'])
    s=model.automation_settings
    story+=[PageBreak(),Paragraph('Données et règles appliquées',styles['Heading1']),p(s.source)]
    data=s.materials.model_dump()
    story.append(table([['Paramètre','Valeur']]+[[k,v] for k,v in data.items()]+[['Enrobage (mm)',s.cover_mm],['Granulat (mm)',s.aggregate_mm],['fctk,0.05 (MPa)',s.fctk005_mpa],['eta1',s.bond_eta1],['cot(theta)',s.cot_theta],['Combinaisons ELU',', '.join(s.uls_case_ids)],['Diamètres (mm)',str(s.diameters_mm)],['Diamètres étriers (mm)',str(s.stirrup_diameters_mm)],['Espacements catalogue (mm)',str(s.spacings_mm)]],[190,325]))
    for r in report['designs']:
        story += [PageBreak(),Paragraph(escape(r['element_id'])+' | acier automatiquement choisi',styles['Heading1'])]
        if r['kind']=='beam':
            story.append(p(f"{r['count']} HA{r['diameter_mm']} ; As disposé {r['as_provided_mm2']:.2f} mm² ; As requis {r['as_required_mm2']:.2f} mm² ; d réel {r['d_mm']:.2f} mm."))
            story.append(p(f"Étriers 2 branches HA{r['stirrup_diameter_mm']} : {r['stirrup_count']} pièces, pas réel {r['stirrup_spacing_mm']:.2f} mm. Asw/s disposé {r['asw_provided_mm2_m']:.2f}, requis {r['asw_required_mm2_m']:.2f} mm²/m."))
        else:
            story.append(p(f"Sens {r['span_axis'].upper()}, portée conventionnelle {r['span_m']:.3f} m. Nappe principale : {r['count']} HA{r['diameter_mm']}, pas {r['spacing_mm']:.2f} mm ; As/m disposé {r['as_provided_mm2_m']:.2f}, requis {r['as_required_mm2_m']:.2f} mm²/m ; d réel {r['d_mm']:.2f} mm."))
            story.append(p(f"Répartition : HA{r['distribution_diameter_mm']}, pas {r['distribution_spacing_mm']:.2f} mm."))
        story.append(p('Faces tendues positives seulement. Les aciers supérieurs de poutre servent au montage ; ils ne couvrent pas des moments négatifs.'))
        story += [Spacer(1,12),table([['Cas','M (kN.m)','V (kN)','As requis (mm²)','MRd (kN.m)']]+[[c['case_id'],f"{c['input']['med_knm']:.3f}",f"{c['input']['ved_kn']:.3f}",f"{c['result']['as_required_mm2']:.2f}",f"{c['result']['mrd_provided_knm']:.3f}"] for c in r['cases']],[70,100,90,130,125])]
        for case in r['cases']:
            names={'area_at_least_required':'Acier fourni suffisant','area_below_four_percent':'Taux maximal','provided_section_in_domain':'Domaine de la section','shear_without_links':'Cisaillement sans étriers','strut_crushing':'Bielle comprimée'}
            story.append(p(case['case_id']+' : '+', '.join(names.get(k,k)+(' : satisfait' if v else ' : NON SATISFAIT') for k,v in case['result']['checks'].items())))
        a=r['anchorage'];story += [Spacer(1,12),Paragraph('Ancrage et recouvrement calculés',styles['Heading2']),
            p(f"fbd = {a['fbd_mpa']:.3f} MPa ; sigma_sd = {a['sigma_sd_mpa']:.3f} MPa ; lb,rqd = {a['lb_rqd_mm']:.1f} mm."),
            p(f"lbd arrondi supérieur = {a['lbd_mm']} mm ; recouvrement majoré alpha6=1,5 = {a['lap_mm']} mm."),
            p(f"Longueur disponible déclarée : {a['available_mm'] if a['available_mm'] is not None else 'inconnue'} mm ; comparaison : {dict(unknown='non renseignée',sufficient_declared_length='longueur déclarée suffisante',insufficient_declared_length='longueur déclarée insuffisante')[a['length_comparison']]}."),
            p('Formules : fbd=2,25 eta1 fctk,0.05/gamma_c ; lb,rqd=phi sigma_sd/(4 fbd) ; lbd=max(lb,rqd ; 0,3 lb,rqd ; 10 phi ; 100 mm). Aucune réduction de confinement. Recouvrement max(1,5 lb,rqd ; 0,45 lb,rqd ; 15 phi ; 200 mm).'),
            p('Le calcul de longueur ne valide ni les appuis, ni la position des arrêts, ni la congestion ou les armatures transversales de recouvrement.')]
        story += [Spacer(1,10),table([['Repère droit','Diamètre (mm)','lbd (mm)','Recouvrement (mm)']]+[[v['mark'],v['diameter_mm'],v['lbd_mm'],v['lap_mm']] for v in r['straight_bar_anchorage']],[230,90,90,105])]
    for r in report['foundations']:
        story += [PageBreak(),Paragraph(escape(r['element_id'])+' | recherche de surface portante',styles['Heading1']),p(r['soil_source']),
            p(f"Dimensions précédentes {r['old_dimensions_m']} m ; dimensions proposées {r['new_dimensions_m']} m. Centre et épaisseur conservés."),
            p('Chaque essai conserve les autres charges et remplace le poids propre par celui de la nouvelle surface, avec le coefficient G de chaque combinaison. La descente de charges est ensuite recalculée.'),Spacer(1,10),
            table([['Cas','N total (kN)','q (kPa)','Limite (kPa)']]+[[c['case_id'],f"{c['total_kn']:.3f}",f"{c['q_kpa']:.3f}",f"{c['limit_kpa']:.3f}"] for c in r['cases']],[90,140,140,145])]
        story.extend(p(t) for t in r['unresolved'])
    story += [Spacer(1,16),Paragraph('Base documentaire et limites de qualification',styles['Heading2']),p('Commission européenne / JRC, EUR 26566 EN, Eurocode 2: Background & Applications, Design of Concrete Buildings - Worked examples (2014), chapitres 3 et 4. Base de première génération utilisée pour ces sous-calculs ; ne constitue pas une vérification de conformité aux normes/annexes nationales actuellement applicables.'),p('https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/1110_WS_EC2.pdf')]
    def footer(c,doc):
        c.saveState();c.setFont('Helvetica-Bold',8);c.setFillColor(colors.HexColor('#a33d2f'))
        c.drawString(38,25,'NON EXÉCUTOIRE - CONTRÔLES LOCAUX SEULEMENT');c.drawRightString(557,25,f'Rév. {revision} | {doc.page}');c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
