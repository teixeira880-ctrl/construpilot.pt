"""A3 vector sheets and SVG previews use identical scene primitives (mm).

No hardcoded project coordinates. Geometry comes exclusively from Model and its
DrawingStudy. This renderer never turns a draft into an execution document.
"""
from __future__ import annotations
import csv
import io
import math
import threading
from pathlib import Path
from xml.sax.saxutils import escape
from engines.structuro_drawings import (compile_dossier,outline,world,section_interval,bar_geometry,add,mul)

INK="#203b37"; GREEN="#237360"; LIGHT="#edf2f0"; RED="#ae4233"; BLUE="#235ba4"; GREY="#687b76"
PALETTE={"slab":"#e3ece8","beam":"#d2dad6","wall":"#a9c4b8","column":"#7f9b8f","footing":"#d9cbb9"}
FONT_LOCK=threading.Lock()


def ensure_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonts=Path(__file__).resolve().parents[1]/"assets"/"fonts"
    with FONT_LOCK:
        if "DrawingFont" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("DrawingFont",str(fonts/"DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("DrawingFontBold",str(fonts/"DejaVuSans-Bold.ttf")))


class Scene:
    def __init__(self):
        ensure_fonts();self.items=[];self.scale=None
    def line(self,ps,color=INK,width=.25,dash=False,fill=None,closed=False):
        self.items.append(dict(kind="poly",points=ps,color=color,width=width,dash=dash,fill=fill,closed=closed))
    def rect(self,x,y,w,h,**kw):self.line([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],closed=True,**kw)
    def text(self,x,y,text,size=2.8,color=INK,bold=False,anchor="start"):
        self.items.append(dict(kind="text",x=x,y=y,text=str(text),size=size,color=color,bold=bold,anchor=anchor))
    def lines(self,x,y,text,width=90,size=2.8,leading=4.5,color=INK,bold=False):
        # Shared glyph metrics keep PDF and SVG line wrapping identical.
        from reportlab.pdfbase.pdfmetrics import stringWidth
        font="DrawingFontBold" if bold else "DrawingFont"; yy=y
        for para in str(text).splitlines() or [""]:
            line=""
            for word in para.split():
                # Split exceptionally long words (IDs/URLs) instead of overflowing.
                chunks=[];chunk=""
                for char in word:
                    if stringWidth(chunk+char,font,size)>width:chunks.append(chunk);chunk=char
                    else:chunk+=char
                chunks.append(chunk)
                for chunk in chunks:
                    if stringWidth((line+" "+chunk).strip(),font,size)>width and line:
                        self.text(x,yy,line,size,color,bold);yy+=leading;line=chunk
                    else:line=(line+" "+chunk).strip()
            self.text(x,yy,line,size,color,bold);yy+=leading
        return yy


def dimension(s,a,b,label,vertical=False):
    s.line([a,b],GREY,.18)
    for x,y in (a,b):s.line([(x-1,y+1),(x+1,y-1)],GREY,.18)
    s.text((a[0]+b[0])/2+(2 if vertical else 0),(a[1]+b[1])/2-1,label,2.5,GREY,anchor="start" if vertical else "middle")


def hatch_rectangle(s,points):
    left,right=min(p[0] for p in points),max(p[0] for p in points)
    top,bottom=min(p[1] for p in points),max(p[1] for p in points)
    height=bottom-top;start=left-height
    while start<right:
        lo=max(0.,left-start);hi=min(height,right-start)
        if hi>lo:s.line([(start+lo,top+lo),(start+hi,top+hi)],"#9aada4",.12)
        start+=3.


def fit(s,points,box=(22,55,268,174),detail_scale=False):
    xmin=min(p[0] for p in points);xmax=max(p[0] for p in points)
    ymin=min(p[1] for p in points);ymax=max(p[1] for p in points)
    x,y,w,h=box
    required=max((xmax-xmin)*1000/w,(ymax-ymin)*1000/h,.001)
    scales=([1,2,5] if detail_scale else [])+[10,20,25,50,75,100,150,200,250,500,1000,2000,5000,10000,20000,50000,100000,200000]
    denom=next((n for n in scales if n>=required),math.ceil(required/100000)*100000)
    scale=1000/denom;s.scale=denom
    ox=x+(w-(xmax-xmin)*scale)/2;oy=y+(h-(ymax-ymin)*scale)/2
    return lambda p:(ox+(p[0]-xmin)*scale,oy+(ymax-p[1])*scale)


def title(s,model,manifest,sheet):
    s.rect(8,8,404,281,color=INK,width=.35)
    s.text(14,18,"CONSTRUPILOT",5,GREEN,True)
    s.text(406,18,sheet["id"],6,GREEN,True,anchor="end")
    s.lines(14,27,sheet["title"],width=365,size=4.8,leading=6,bold=True)
    s.line([(8,39),(412,39)],INK,.3)
    s.rect(8,253,404,12,color=RED,fill="#fff4ef",width=.25)
    state="DEMONSTRAÇÃO" if manifest["status"]=="demonstration" else "PROCESSO DE TRABALHO"
    s.text(14,260.5,f'{state} - NÃO EXECUTÓRIO - NÃO UTILIZAR PARA OBRAS OU FABRICO',3.1,RED,True)
    s.lines(14,272,model.title,width=245,size=3.1,leading=4)
    s.text(14,284,f"Revisão {manifest['revision']} | {manifest['version']} | Empreinte {manifest['drawing_hash'][:16]}",2.5,GREY)
    s.text(406,274,f"A3 horizontal | 420 × 297 mm | {sheet['id']}",2.8,anchor="end")
    s.text(406,284,f"Escala {('1:' + str(s.scale) if s.scale else 'sem escala')} a 100 % | Unidades: m / mm indicadas",2.5,anchor="end")


def plan(s,model,manifest,sheet):
    d=model.drawings;es=[e for e in model.elements if e.level==sheet["level"]]
    coords=[p for e in es for p in outline(e)]
    xy=fit(s,coords)
    # Draw slab footprints first; drawn views show all members of the named level,
    # irrespective of elevation. Explicit base/top levels prevent hidden conventions.
    for e in sorted(es,key=lambda e:e.kind!="slab"):
        ps=outline(e);s.line([xy(p) for p in ps],width=.3,fill=PALETTE[e.kind],closed=True)
    for o in d.openings:
        e=next((e for e in es if e.id==o.element_id),None)
        if not e:continue
        ps=[xy(p) for p in outline(e,o.box())]
        through=o.z_m<1e-7 and o.height_m>=e.height_m-1e-7
        s.line(ps,RED,.3,fill="#ffffff" if through else "#f9ebe5",dash=not through,closed=True)
        s.line([ps[0],ps[2]],RED,.16);s.line([ps[1],ps[3]],RED,.16)
        center=tuple(sum(p[k] for p in ps)/4 for k in range(2));s.text(center[0],center[1],o.id,2.5,RED,bold=True,anchor="middle")
    xs=[p[0] for p in coords];ys=[p[1] for p in coords]
    left,right=min(xs),max(xs);bottom,top=min(ys),max(ys)
    a,b=xy((left,top)),xy((right,top));dimension(s,(a[0],a[1]-9),(b[0],b[1]-9),f'Fora a fora {right - left:.3f} m')
    a,b=xy((right,top)),xy((right,bottom));dimension(s,(a[0]+7,a[1]),(b[0]+7,b[1]),f"{top-bottom:.3f}",True)
    if sheet["kind"]=="reinforcement":
        for bar in d.bars:
            e=next((e for e in es if e.id==bar.element_id),None)
            if not e:continue
            _,path=bar_geometry(bar)
            for i in range(bar.count):
                points=[xy(world(e,add(p,mul(bar.repeat.xyz(),i)))[:2]) for p in path]
                if all(math.dist(points[0],p)<.1 for p in points):
                    x,y=points[0];s.rect(x-.4,y-.4,.8,.8,color=BLUE,fill=BLUE)
                else:s.line(points,BLUE,.25)
            x,y=xy(world(e,path[0])[:2]);s.text(x+1,y-2,bar.mark,2.5,BLUE,True)
    else:
        for cut in d.cuts:
            if cut.axis=="x" and bottom<=cut.at_m<=top:a,b=xy((left,cut.at_m)),xy((right,cut.at_m))
            elif cut.axis=="y" and left<=cut.at_m<=right:a,b=xy((cut.at_m,bottom)),xy((cut.at_m,top))
            else:continue
            s.line([a,b],BLUE,.2,True);s.text(a[0]-2,a[1]-2,cut.id,2.8,BLUE,True)
    for e in es:
        ps=outline(e);center=tuple(sum(p[k] for p in ps)/4 for k in range(2));x,y=xy(center)
        s.text(x,y+4,e.id,2.6,INK,True,anchor="middle")
    s.line([(304,43),(304,248)],GREY,.15)
    s.text(310,49,"LEGENDA E MARCAS",3.2,GREEN,True)
    yy=s.lines(310,57,"Projeção dos elementos do piso. As cotas de base e de topo constam da marcação do processo JSON. Negativos atravessantes: branco; parciais: salmão.",width=93,size=2.7)
    s.text(310,yy+5,f"{len(es)} éléments | {sum(b.count for b in d.bars if any(e.id==b.element_id for e in es))} barres",2.8,bold=True);yy+=14
    placements={p.element_id:p.base_z_m for p in d.placements}
    for e in es[:8]:
        label=e.id if len(e.id)<=28 else e.id[:25]+"…"
        yy=s.lines(310,yy,f"{label} : {e.length_m:g} × {e.width_m:g} × {e.height_m:g} m\nBase {placements[e.id]:+.3f} / dessus {placements[e.id]+e.height_m:+.3f}",93,2.6,4.1);yy+=3
    s.lines(310,yy+3,"Dimensões completas e coordenadas: folhas R / O.",93,2.6,4.1)
    s.text(18,242,"X → / Y ↑ | coordenadas do modelo | secções introduzidas, não dimensionadas",2.8,GREY)


def section(s,model,manifest,sheet):
    d=model.drawings;cut=next(c for c in d.cuts if c.id==sheet["cut"])
    elevations={p.element_id:p.base_z_m for p in d.placements};rows=[]
    for e in model.elements:
        interval=section_interval(outline(e),cut)
        if interval:rows.append((e,interval,elevations[e.id]))
    points=[p for e,(a,b),z in rows for p in ((a,z),(b,z+e.height_m))];xy=fit(s,points)
    for e,(a,b),z in rows:
        ps=[xy(p) for p in ((a,z),(b,z),(b,z+e.height_m),(a,z+e.height_m))]
        s.line(ps,INK,.35,fill=PALETTE[e.kind],closed=True)
        hatch_rectangle(s,ps)
        # Draw openings actually cut, not hidden windows outside the cutting plane.
        for o in d.openings:
            if o.element_id!=e.id:continue
            hole=section_interval(outline(e,o.box()),cut)
            if hole:
                ha,hb=hole;oz=z+o.z_m;oh=o.height_m
                s.line([xy(p) for p in ((ha,oz),(hb,oz),(hb,oz+oh),(ha,oz+oh))],RED,.25,fill="#ffffff",closed=True)
        x,y=xy(((a+b)/2,z+e.height_m/2));s.text(x,y-1,e.id,2.7,bold=True,anchor="middle")
    lo=min(p[0] for p in points);hi=max(p[0] for p in points)
    dimension(s,(xy((lo,0))[0],237),(xy((hi,0))[0],237),f'Fora a fora {hi - lo:.3f} m')
    for z in sorted(set(z for e,ab,z in rows)|set(z+e.height_m for e,ab,z in rows)):
        a,b=xy((lo,z)),xy((hi,z));s.line([(b[0]+1,b[1]),(296,b[1])],GREY,.15,True);s.text(298,b[1]+1,f"{z:+.3f}",2.5,anchor="start")
    s.lines(327,53,f"Coupe {cut.id}\nEixo horizontal {cut.axis.upper()}\n{('Y' if cut.axis == 'x' else 'X')} = {cut.at_m:g} m",75,3,5,bold=True)
    s.lines(327,81,"Interseção real do plano de corte com os volumes introduzidos, incluindo os elementos rodados e os negativos. Nenhum terreno nem elemento oculto é suposto.",75,2.8,4.5)
    s.lines(327,122,"Cotas altimétricas em m. Os aços estão documentados nas plantas F e nos pormenores D. Este corte de cofragem não constitui uma verificação das ligações.",75,2.8,4.5)


def detail(s,model,manifest,sheet):
    b=next(b for b in model.drawings.bars if b.mark==sheet["mark"])
    row=next(r for r in manifest["schedule"] if r["mark"]==b.mark)
    _,path=bar_geometry(b)
    # Show the plane carrying the bends first (e.g. Y/Z for beam links).
    # Fixed X/Y + X/Z projections would hide a transverse U-shaped stirrup.
    extents=[max(p[i] for p in path)-min(p[i] for p in path) for i in range(3)]
    planes=sorted(((0,1),(0,2),(1,2)),key=lambda ij:(extents[ij[0]]*extents[ij[1]],max(extents[i] for i in ij)),reverse=True)[:2]
    boxes=[(25,60,260,120),(25,210,260,35)]
    for view_index,(dims,box) in enumerate(zip(planes,boxes)):
        label=f"Vista local {'XYZ'[dims[0]]} / {'XYZ'[dims[1]]}"
        ps=[(p[dims[0]],p[dims[1]]) for p in path];xy=fit(s,ps,box,detail_scale=True)
        s.text(20,box[1]-10,label,3,GREEN,True)
        s.line([xy(p) for p in ps],BLUE,.65)
        original=[p.xyz() for p in b.points]
        for i,(a,c) in enumerate(zip(original,original[1:]),1):
            pa,pc=xy((a[dims[0]],a[dims[1]])),xy((c[dims[0]],c[dims[1]]))
            if view_index==0 and math.dist(pa,pc)>6:
                tx=(pa[0]+pc[0])/2;ty=(pa[1]+pc[1])/2-3;anchor="middle"
                if abs(pa[0]-pc[0])<1:
                    left=tx<box[0]+box[2]/2;tx+=-3 if left else 3;anchor="end" if left else "start";ty+=3
                s.text(tx,ty,f"L{i}={math.dist(a,c):.3f} m",2.8,anchor=anchor)
    s.scale=None # independent projection scales; dimensions govern
    yy=s.lines(310,51,f"{b.mark} | HA {b.diameter_mm:g}",94,4,5,BLUE,True)
    yy=s.lines(310,yy+5,f"Elemento: {b.element_id}\nNombre : {b.count}\nComprimento desenvolvido: {row['developed_length_m']:.3f} m\nComprimento total: {row['total_length_m']:.3f} m\nMassa teórica: {row['mass_kg']:.3f} kg\nRaio ao eixo: {b.bend_radius_mm:g} mm\nRecobrimento declarado: {b.cover_mm:g} mm",94,2.8,5)
    brief=lambda value,n:value if len(value)<=n else value[:n]+"… (continuação no JSON)"
    yy=s.lines(310,yy+5,f"Função: {brief(b.role, 90) or 'A precisar'}\nFonte: {brief(b.source, 160) or 'A preencher'}",94,2.7,4.3)
    s.lines(310,yy+5,"Cotas C: distâncias entre interseções teóricas. O comprimento desenvolvido tem em conta as dobras circulares. Nenhuma amarração nem emenda é acrescentada automaticamente. Os pontos e repetições constam do JSON.",94,2.7,4.3,color=RED)


def general(s,model,manifest,sheet):
    d=model.drawings
    s.text(17,53,"UM PROCESSO, UMA REVISÃO",4,GREEN,True)
    s.lines(17,64,"Cofragem, cortes, armaduras e lista provêm dos mesmos elementos e dos mesmos traçados de aços. Qualquer alteração das dimensões, cotas ou varões impõe uma nova gravação e uma regeneração.",width=260,size=3.2,leading=5)
    s.text(17,86,f'{len(model.elements)} éléments | {len(d.openings)} réservations | {len(d.cuts)} coupes | {len(d.bars)} marcas de aços',3.2,bold=True)
    s.text(17,95,f"{sum((r['count'] for r in manifest['schedule']))} barres | {manifest['total_mass_kg']:.3f} kg teóricos | aço 7 850 kg/m³",3.2)
    y=108
    for line in sheet["lines"]:
        s.text(17,y,line,2.8);y+=4.6
    s.text(308,53,"CONTEÚDO DO PROCESSO",3.5,GREEN,True)
    counts={kind:sum(sh["kind"]==kind for sh in manifest["sheets"]) for kind in ("general","formwork","section","reinforcement","detail","schedule","members","openings")}
    y=66
    for kind,label in (("general","G · Dados e controlos"),("formwork","C · Cofragem por piso"),("members","R · Marcação da cofragem"),("openings","O · Negativos"),("section","S · Cortes"),("reinforcement","F · Plantas de aços"),("detail","D · Pormenores de varões"),("schedule","N · Nomenclature")):
        s.text(308,y,f"{label} : {counts[kind]}",3);y+=10
    s.lines(308,154,"Imprimir em A3 a 100 %. Controlar a escala e as cotas antes de qualquer revisão. Todas as folhas têm o seu índice e a impressão digital dos dados.",95,2.8,4.5)
    s.lines(308,195,"Os controlos incidem sobre a geometria desenhável, o recobrimento declarado e os negativos. Não valem como validação da resistência, do solo ou das disposições de execução.",95,2.8,4.5,color=RED)


def schedule(s,model,manifest,sheet):
    headers=["Marca / elemento","Ø mm","Nb","C unitário m","C total m","kg"]
    xs=[17,140,185,226,294,361,403]
    s.rect(14,48,392,10,fill=GREEN,color=GREEN)
    for i,h in enumerate(headers):s.text(xs[i]+2,54.5,h,2.9,"#ffffff",True)
    y=67
    for row in manifest["schedule"][sheet["offset"]:sheet["offset"]+19]:
        values=[f"{row['mark']} / {row['element_id']}",f"{row['diameter_mm']:g}",str(row['count']),f"{row['developed_length_m']:.3f}",f"{row['total_length_m']:.3f}",f"{row['mass_kg']:.3f}"]
        for i,v in enumerate(values):s.lines(xs[i]+2,y,v,xs[i+1]-xs[i]-5,2.8,3.5)
        s.line([(14,y+3),(406,y+3)],GREY,.12);y+=8.5
    s.text(17,238,f"Massa total do processo: {manifest['total_mass_kg']:.3f} kg | comprimentos calculados sem majoração nem desperdício | não vale como nota de moldagem",2.8,RED)


def build_scene(model,manifest,sheet):
    if not manifest["can_export"]:raise ValueError("Processo incompleto: corrigir os erros geométricos antes da geração")
    s=Scene()
    {"general":general,"formwork":plan,"section":section,"reinforcement":plan,"detail":detail,"schedule":schedule,"members":geometry_table,"openings":geometry_table}[sheet["kind"]](s,model,manifest,sheet)
    title(s,model,manifest,sheet)
    return s


def scene_svg(scene):
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 297" width="1189" height="841" role="img"><rect width="420" height="297" fill="#ffffff"/>']
    for p in scene.items:
        if p["kind"]=="text":
            out.append(f'<text x="{p["x"]:.4f}" y="{p["y"]:.4f}" fill="{p["color"]}" font-family="Arial, sans-serif" font-size="{p["size"]}" font-weight="{700 if p["bold"] else 400}" text-anchor="{p["anchor"]}">{escape(p["text"])}</text>')
        else:
            points=" ".join(f"{x:.4f},{y:.4f}" for x,y in p["points"])
            tag="polygon" if p["closed"] else "polyline"
            out.append(f'<{tag} points="{points}" fill="{p["fill"] or "none"}" stroke="{p["color"]}" stroke-width="{p["width"]}"'+(' stroke-dasharray="2 1"' if p["dash"] else '')+'/>')
    return ("".join(out)+"</svg>").encode()


def build_drawing_pdf(model,revision,manifest=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    manifest=manifest or compile_dossier(model,revision)
    if not manifest["can_export"]:raise ValueError("Processo incompleto")
    ensure_fonts()
    out=io.BytesIO();c=canvas.Canvas(out,pagesize=(420*mm,297*mm),pageCompression=1,invariant=1)
    c.setTitle(model.title+" - Processo de trabalho");c.setAuthor("ConstruPilot")
    for sheet in manifest["sheets"]:
        scene=build_scene(model,manifest,sheet)
        for p in scene.items:
            c.setFillColor(HexColor(p["color"]))
            if p["kind"]=="text":
                c.setFont("DrawingFontBold" if p["bold"] else "DrawingFont",p["size"]*mm)
                fn={"start":c.drawString,"end":c.drawRightString,"middle":c.drawCentredString}[p["anchor"]]
                fn(p["x"]*mm,(297-p["y"])*mm,p["text"])
            else:
                c.setStrokeColor(HexColor(p["color"]));c.setLineWidth(p["width"]*mm)
                c.setDash([2*mm,mm] if p["dash"] else [])
                if p["fill"]:c.setFillColor(HexColor(p["fill"]))
                path=c.beginPath()
                for i,(x,y) in enumerate(p["points"]):
                    (path.moveTo if i==0 else path.lineTo)(x*mm,(297-y)*mm)
                if p["closed"]:path.close()
                c.drawPath(path,stroke=1,fill=bool(p["fill"]))
        c.showPage()
    c.save();return out.getvalue()


def build_schedule_csv(manifest):
    if not manifest["can_export"]:raise ValueError("Processo incompleto")
    s=io.StringIO(newline="");w=csv.writer(s,delimiter=";")
    w.writerow(["CONSTRUPILOT - PROCESSO NÃO EXECUTÓRIO",f"Revision {manifest['revision']}",manifest["drawing_hash"]])
    w.writerow(["Repere","Element","Diametre_mm","Número","L_unitaire_m","L_totale_m","Masse_kg","Rayon_axe_mm","Enrobage_mm"])
    for r in manifest["schedule"]:
        w.writerow([r[k] if isinstance(r[k],(int,str)) else format(r[k],".6f") for k in ("mark","element_id","diameter_mm","count","developed_length_m","total_length_m","mass_kg","bend_radius_mm","cover_mm")])
    return ("\ufeff"+s.getvalue()).encode("utf-8")


def geometry_table(s,model,manifest,sheet):
    openings=sheet['kind']=='openings'
    heads=["Marca / "+("élément" if openings else "niveau"),"X / Y (m)","L / l / h (m)","Z base / topo (m)","Rotation °"]
    xs=[17,135,211,291,374,404];s.rect(14,48,392,10,fill=GREEN,color=GREEN)
    for i,h in enumerate(heads):s.text(xs[i]+1,54.5,h,2.6,"#ffffff",True)
    places={p.element_id:p.base_z_m for p in model.drawings.placements}
    rows=model.drawings.openings if openings else model.elements
    y=67
    for r in rows[sheet['offset']:sheet['offset']+12]:
        base=r.z_m if openings else places[r.id]
        values=[f"{r.id}\n{r.element_id if openings else r.level}",f"{r.x_m:.3f}\n{r.y_m:.3f}",f"{r.length_m:.3f} / {r.width_m:.3f}\nh {r.height_m:.3f}",f"{base:+.3f}\n{base+r.height_m:+.3f}","locale" if openings else f"{r.angle_deg:g}"]
        for i,v in enumerate(values):s.lines(xs[i]+1,y,v,xs[i+1]-xs[i]-4,2.65,3.8)
        s.line([(14,y+10),(406,y+10)],GREY,.12);y+=14
    s.lines(17,241,"Negativos: X/Y/Z locais, origem na base do elemento e rotação idêntica à deste." if openings else "Elementos: X/Y globais do canto local (0,0), Z absoluto. C segue X local, l segue Y local; rotação positiva em torno de Z.",width=385,size=2.8,leading=4)
