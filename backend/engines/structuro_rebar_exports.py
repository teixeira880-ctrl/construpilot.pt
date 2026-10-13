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
        raise ValueError("Dossier d'armatures absent")
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
             p(f"Révision {revision} - {result['engine_version']}"),
             p("Calculs partiels et contrôle documentaire - NON EXÉCUTOIRE"),
             p("Relecture de documents sources" if inputs.basis == "source_replay" else "Projet de dimensionnement"),
             p("Empreinte des entrées : "+result["input_hash"]), Spacer(1,10), heading("Points à résoudre")]
    story.extend(p("- "+o) for o in inputs.observations)
    if model.architecture is not None:
        from engines.structuro_calc import calculate
        arch = calculate(model)["architectural_compatibility"]
        story.append(heading("Implantation et hauteurs - validation globale non acquise"))
        story.extend(p(f"{c['element_id']} / {c['label']} : {'CONFLIT' if c['status']=='conflict' else 'Contrôle local satisfait'} - {c['summary']} Source : {c['source']}") for c in arch["checks"])
        story.extend(p(x) for x in arch["issues"]+arch["unresolved"])
    story += [heading("Vérifications restantes")]
    story.extend(p("- "+o) for o in result["unresolved"])
    for source, r in zip(inputs.footings, result["footings"]):
        story += [PageBreak(), heading(f"Semelle {r['id']} - bande de 1 m"), p(r["source"]),
                  p(f"B={source.width_m:g} m ; mur={source.wall_width_m:g} m ; h={source.h_m:g} m ; d={source.d_m:g} m")]
        if "pressures" in r:
            rows = [["Combinaison", "N (kN/m)", "q (kPa)", "Limite (kPa)", "Taux"]]
            for k,v in r["pressures"].items():
                rows.append([k.replace("_", " "),f"{v['n_kn_m']:.2f}",f"{v['q_kpa']:.2f}",f"{v['limit_kpa']:.2f}",f"{v['utilisation']*100:.1f} %"])
            story += [table(rows,[157,86,86,104,86]), Spacer(1,10),
                p(f"Largeur minimale du rapport : {source.min_width_m:g} m. Comparaison : {'satisfaite' if r['checks']['width'] else 'NON SATISFAITE'}"),
                heading("Tirant transversal - effort seul"),
                p(f"Fs,max={r['tie_force_kn_m']:.3f} kN/m ; As,effort={r['as_tie_only_mm2_m']:.2f} mm²/m = {r['as_tie_only_mm2_m']/100:.3f} cm²/m"),
                p(r["pressure_basis"]),p(r["formula"]),
                p("Cette aire n'est PAS l'armature finale à poser. Elle ne comprend pas les minima et autres vérifications indiqués ci-dessous.")]
        story.extend(p("- "+o) for o in r["issues"])
    for source, r in zip(inputs.sections, result["sections"]):
        story += [PageBreak(),heading(f"Section {r['id']}"),p(f"Cas : {r['case']}"),p(r["source"]),
                  p(f"b={source.b_mm:g}, h={source.h_mm:g}, d={source.d_mm:g} mm ; MEd={source.med_knm:g} kN.m ; VEd={source.ved_kn:g} kN"),
                  p("Matériaux : "+source.materials.source)]
        if "as_required_mm2" in r:
            rows=[["Résultat", "Valeur"]]
            for key,label,unit in [("as_flexure_mm2","As flexion","mm²"),("as_min_mm2","As minimum","mm²"),("as_required_mm2","As requis en section","mm²"),
                                    ("as_provided_mm2","As disposé","mm²"),("asw_required_mm2_m","Asw/s requis","mm²/m"),("vrdc_kn","VRd,c","kN"),("vrdmax_kn","VRd,max","kN")]:
                if r.get(key) is not None: rows.append([label,f"{r[key]:.3f} {unit}"])
            story.append(table(rows,[285,234]))
            story.extend(p(f"{k} : {'satisfait' if v else 'NON SATISFAIT'}") for k,v in r["checks"].items())
        story.extend(p("- "+o) for o in r["issues"])
    if model.linked_sections:
        from engines.structuro_calc import calculate
        linked = calculate(model)["linked_reinforcement"]
        story += [PageBreak(), heading("Aciers liés aux efforts du modèle"), p(linked["engine_version"]),
                  p("Empreinte du modèle complet : "+linked["input_hash"]), p(linked["scope"])]
        if linked["status"] == "blocked":
            story += [p("CALCUL BLOQUÉ : aucun effort ni acier lié ne peut être retenu.")]
            story.extend(p(i["message"]) for i in linked["issues"])
        for i, section in enumerate(linked["sections"]):
            if i: story.append(PageBreak())
            story += [heading(section["id"]+" / "+section["element_id"]), p(section["source"]),
                      p(f"{section['force_basis']} ; portée {section['span_m']:g} m ; statut {section['status']}")]
            for row in section["cases"]:
                s, r = row["section_input"], row["result"]
                story += [p(f"Cas {row['case_id']} : b={s['b_mm']:g}, h={s['h_mm']:g}, d={s['d_mm']:g} mm ; MEd={s['med_knm']:.3f} kN.m ; VEd={s['ved_kn']:.3f} kN"),
                          p("Matériaux : "+s["materials"]["source"])]
                if "as_required_mm2" in r:
                    provided=f"{s['as_provided_mm2']:.2f} mm²" if s['as_provided_mm2'] is not None else "non renseigné"
                    story.append(p(f"As requis : {r['as_required_mm2']:.2f} mm² ; As fourni : {provided}"))
                if "vrdc_kn" in r: story.append(p(f"VRd,c : {r['vrdc_kn']:.3f} kN"))
                if "asw_required_mm2_m" in r: story.append(p(f"Asw/s requis : {r['asw_required_mm2_m']:.2f} mm²/m"))
                labels={"area_at_least_required":"Aire d'aciers suffisante", "area_below_four_percent":"Limite supérieure d'armatures",
                        "provided_section_in_domain":"Domaine de la section armée", "shear_without_links":"Cisaillement sans cadres",
                        "strut_crushing":"Compression des bielles"}
                story.extend(p(f"{labels.get(k,k)} : {'satisfait pour ce contrôle' if v else 'NON SATISFAIT'}") for k,v in r["checks"].items())
                story.extend(p("- "+o) for o in r["issues"])
    for r in result["schedules"]:
        story += [PageBreak(),heading(f"Nomenclature {r['id']}"),p(r["basis"]),p(r["source"]),p(r["note"])]
        rows=[["Repère", "Ø (mm)", "Nombre", "Lg unitaire (m)", "Lg totale (m)", "Poids (kg)"]]
        for b in r["bars"]:
            rows.append([b["mark"],f"{b['diameter_mm']:g}",b["count"],f"{b['developed_length_m']:.3f}",f"{b['total_length_m']:.3f}",f"{b['mass_kg']:.3f}"])
        story += [table(rows,[68,63,63,105,110,110]),Spacer(1,12),p(f"Total recalculé hors chutes : {r['total_kg']:.3f} kg")]
        if r["source_total_kg"] is not None:
            story.append(p(f"Total imprimé sur la source : {r['source_total_kg']:.3f} kg ; écart : {r['delta_kg']:+.3f} kg"))
        story.extend(p(f"Repère {b['mark']} : {b['description']}") for b in r["bars"])
    story += [PageBreak(),heading("Documents et version des données")]
    for i, s in enumerate(inputs.sources):
        if i and i % 9 == 0:
            story += [PageBreak(),heading("Documents et version des données (suite)")]
        story += [p(f"{s.filename} | {s.pages} page(s) | {s.revision}"),p("SHA-256 : "+s.sha256)]
    story += [heading("Référence des sous-calculs"),p("JRC EUR 26566 EN (2014), chapitres 3 et 4. Formules de la première génération de l'EC2 ; ce module ne constitue pas un paquet normatif complet qualifié."),
              p("https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/1110_WS_EC2.pdf")]
    def footer(c,d):
        c.saveState(); c.setFont("Helvetica-Bold",8); c.setFillColor(colors.HexColor("#943e29"))
        c.drawString(38,24,"CALCULS PARTIELS - NON EXÉCUTOIRE"); c.drawRightString(A4[0]-38,24,f"Rév. {revision} | {d.page}"); c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
