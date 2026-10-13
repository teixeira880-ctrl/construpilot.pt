"""Principle drawings and calculation record from the SAME versioned model."""
import io
import math
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.graphics.shapes import Drawing, Polygon, String
from engines.structuro_calc import Model, calculate

LABELS = {"slab":"Plancher", "beam":"Poutre", "wall":"Mur", "column":"Poteau", "footing":"Semelle"}
COLORS = {"slab":"#cbd5e1", "beam":"#b46b42", "wall":"#17574b", "column":"#9d3e26", "footing":"#837466"}


def corners(e):
    if any(x is None for x in (e.x_m,e.y_m,e.length_m,e.width_m)):
        return None
    a=math.radians(e.angle_deg)
    return [(e.x_m+x*math.cos(a)-y*math.sin(a),e.y_m+x*math.sin(a)+y*math.cos(a))
            for x,y in ((0,0),(e.length_m,0),(e.length_m,e.width_m),(0,e.width_m))]


def plan_drawing(elements):
    width,height=745,340
    d=Drawing(width,height)
    rows=[(e,corners(e)) for e in elements if corners(e)]
    if not rows:
        d.add(String(15,height/2,"Implantation à compléter : coordonnées x/y et dimensions requises.",fontSize=11))
        return d
    pts=[p for _,ps in rows for p in ps]
    xmin,ymin=min(p[0] for p in pts),min(p[1] for p in pts)
    xmax,ymax=max(p[0] for p in pts),max(p[1] for p in pts)
    scale=min((width-100)/max(xmax-xmin,.001),(height-85)/max(ymax-ymin,.001))
    xy=lambda x,y: (45+(x-xmin)*scale,40+(y-ymin)*scale)
    # slabs behind the vertical/support members
    for e,ps in sorted(rows,key=lambda row:row[0].kind!="slab"):
        coords=[xy(*p) for p in ps]
        d.add(Polygon([v for p in coords for v in p],strokeColor=colors.HexColor(COLORS[e.kind]),
            fillColor=None,strokeWidth=1.5,strokeDashArray=None if e.reviewed else [4,3]))
        x,y=tuple(sum(p[i] for p in coords)/4 for i in (0,1))
        d.add(String(x+2,y+5,e.id,fontSize=8,fillColor=colors.HexColor("#152f2b")))
    d.add(String(12,12,"Projection du modèle saisi - échelle adaptée à la feuille - unités : m",fontSize=8))
    return d


def build_pdf(model: Model, revision: int) -> bytes:
    result=calculate(model)
    out=io.BytesIO()
    doc=SimpleDocTemplate(out,pagesize=landscape(A4),leftMargin=35,rightMargin=35,topMargin=42,bottomMargin=36)
    ss=getSampleStyleSheet()
    ss.add(ParagraphStyle("Tiny",parent=ss["BodyText"],fontSize=8,leading=11))
    p=lambda text: Paragraph(escape(str(text)),ss["Tiny"])
    story=[Paragraph("ConstruPilot | Étude gravitaire",ss["Title"]),p(model.title),
        p(f"Révision {revision} | moteur {result['engine_version']} | empreinte {result['input_hash']}"),
        Spacer(1,10),Paragraph("PLAN DE PRINCIPE - NON EXÉCUTOIRE",ss["Heading2"]),
        p("Sections saisies, non dimensionnées. Les résultats mécaniques ne constituent pas une vérification de résistance."),
        Spacer(1,6)]
    for text in result["limits"]:
        story.append(p(text))
    if model.assumptions:
        story.append(Paragraph("Hypothèses du modèle",ss["Heading2"]))
        story.extend(p(x) for x in model.assumptions)
    if result["issues"]:
        story.append(Paragraph("Données à compléter avant calcul",ss["Heading2"]))
        story.extend(p(f"{x['element'] or 'Modèle'} : {x['message']}") for x in result["issues"])
    def table(rows,widths):
        t=Table([[p(c) for c in r] for r in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e7eee9")),
            ("GRID",(0,0),(-1,-1),.3,colors.HexColor("#c5cfca")),("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        return t
    for level in dict.fromkeys(e.level for e in model.elements):
        es=[e for e in model.elements if e.level==level]
        story += [PageBreak(),Paragraph(escape(level),ss["Heading1"]),plan_drawing(es),Spacer(1,8)]
        rows=[["Repère / nature","L × l × h (m)","Appuis","Source / état"]]
        for e in es:
            dims=" × ".join("?" if n is None else f"{n:g}" for n in (e.length_m,e.width_m,e.height_m))
            state="Saisie confirmée" if e.reviewed else "À confirmer"
            if corners(e) is None: state+=" ; non dessiné (implantation incomplète)"
            rows.append([f"{e.id} / {LABELS[e.kind]}",dims,", ".join(s.target for s in e.supports) or "Sol / à préciser",
                f"{e.source.document} p.{e.source.page or '?'} {e.source.note} - {state}"])
        story.append(table(rows,[130,105,120,415]))
    for case in result["cases"]:
        story += [PageBreak(),Paragraph(escape(case["label"]),ss["Heading1"]),
            p("Facteurs explicitement saisis : "+str(case["factors"])),
            p(f"Charges externes : {case['external_kn']:.3f} kN | Réactions au sol : {case['ground_kn']:.3f} kN | Écart : {case['balance_error_kn']:.3g} kN"),Spacer(1,10)]
        rows=[["Repère","N total (kN)","Efforts / pressions","Relation / limites"]]
        for r in case["elements"]:
            value="Répartition tributaire saisie"
            if r["kind"]=="beam":
                value=f"RA={r['reaction_left_kn']:.3f} ; RB={r['reaction_right_kn']:.3f} kN ; Mmax={r['moment_max_knm']:.3f} kN.m"
                if r["deflection_sampled_mm"] is not None: value+=f" ; flèche élastique échantillonnée={r['deflection_sampled_mm']:.3f} mm"
            if "axial_stress_mpa" in r: value=f"Contrainte moyenne : {r['axial_stress_mpa']:.4f} MPa"
            if "mean_pressure_kpa" in r: value=f"Pression moyenne : {r['mean_pressure_kpa']:.3f} kPa ; sol non vérifié"
            rows.append([r["id"],f"{r['total_kn']:.3f}",value,r.get("formula","Somme des forces ; répartition déclarée")])
        story.append(table(rows,[75,80,305,310]))
    story += [PageBreak(),Paragraph("Traçabilité des entrées",ss["Heading1"])]
    for e in model.elements:
        story.extend([p(f"{e.id} : poids volumique={e.density_kn_m3} kN/m³ ; EI={e.ei_kn_m2} kN.m² ; {e.mechanics_source.document} {e.mechanics_source.note}")])
        for load in e.loads:
            story.append(p(f"Charge {load.action}, {load.mode}, valeur={load.value}, position={load.position_m} m. {load.source.document} p.{load.source.page or '?'} {load.source.note}"))
    for c in model.combinations:
        story.append(p(f"{c.id} : {c.source.document} {c.source.note}"))
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont("Helvetica-Bold",8)
        canvas.setFillColor(colors.HexColor("#9d3e26"))
        canvas.drawString(35,20,"PLAN DE PRINCIPE - NON EXÉCUTOIRE - RÉSISTANCE NON VÉRIFIÉE")
        canvas.drawRightString(806,20,f"Rév. {revision} | {doc.page}");canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


def build_dxf(model: Model, revision: int) -> bytes:
    import ezdxf
    doc=ezdxf.new("R2010");doc.units=6
    ms=doc.modelspace()
    for kind in LABELS:
        doc.layers.new("PRINCIPE_"+kind.upper())
    ms.add_text(f"CONSTRUPILOT - PLAN DE PRINCIPE NON EXECUTOIRE - REV {revision}",dxfattribs={"height":.18,"insert":(0,-1)})
    # Separate layouts in modelspace to avoid overlaying storeys.
    offset=0.
    for level in dict.fromkeys(e.level for e in model.elements):
        es=[e for e in model.elements if e.level==level]
        pairs=[(e,corners(e)) for e in es if corners(e)]
        allpoints=[pt for _,ps in pairs for pt in ps]
        xmin=min((p[0] for p in allpoints),default=0)
        ymin=min((p[1] for p in allpoints),default=0)
        xmax=max((p[0] for p in allpoints),default=0)
        ymax=max((p[1] for p in allpoints),default=0)
        ms.add_text(level,dxfattribs={"height":.18,"insert":(offset,ymax-ymin+.5)})
        for e,ps in pairs:
            pts=[(x-xmin+offset,y-ymin) for x,y in ps]
            ms.add_lwpolyline(pts,close=True,dxfattribs={"layer":"PRINCIPE_"+e.kind.upper()})
            ms.add_text(f"{e.id} {e.length_m:g}x{e.width_m:g}x{e.height_m if e.height_m is not None else '?'} m - NON DIMENSIONNE",
                dxfattribs={"height":.10,"insert":pts[0]})
        missing=", ".join(e.id for e in es if corners(e) is None)
        if missing: ms.add_text("NON DESSINES: "+missing,dxfattribs={"height":.12,"insert":(offset,-.4)})
        offset+=max(xmax-xmin,3)+4
    stream=io.StringIO();doc.write(stream)
    return stream.getvalue().encode("utf-8")
