"""Project-based drawing geometry. No structural design or engineering approval.

All coordinates are metres. Openings and bar paths use the element's local
x/y/z frame, z=0 at its base. Only rectangular prismatic members/openings.
Bar points are theoretical intersections; bends are circular centreline fillets.
"""
from __future__ import annotations
import hashlib
import json
import math
import textwrap
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer

VERSION = "drawing-dossier-1.1.0"
ID = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,59}$")]
Coord = Annotated[float, Field(ge=-10000, le=10000)]
Size = Annotated[float, Field(gt=0, le=10000)]
Text = Annotated[str, Field(max_length=600)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Point(Strict):
    x: Coord
    y: Coord
    z: Coord

    def xyz(self):
        return (self.x, self.y, self.z)


class Placement(Strict):
    element_id: ID
    base_z_m: Coord
    source: Text = ""
    generated_by: Literal["auto-drafting-1.0.0"] | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        if self.generated_by is None: data.pop("generated_by", None)
        return data


class Opening(Strict):
    id: ID
    element_id: ID
    x_m: Coord
    y_m: Coord
    z_m: Coord
    length_m: Size
    width_m: Size
    height_m: Size
    source: Text = ""

    def box(self):
        return ((self.x_m, self.y_m, self.z_m),
                (self.x_m+self.length_m, self.y_m+self.width_m, self.z_m+self.height_m))


class Cut(Strict):
    id: ID
    axis: Literal["x", "y"]  # horizontal section coordinate; other axis is fixed
    at_m: Coord


class BarGroup(Strict):
    mark: ID
    element_id: ID
    diameter_mm: float = Field(ge=4, le=40)
    count: int = Field(ge=1, le=500)
    points: list[Point] = Field(min_length=2, max_length=12)
    repeat: Point  # translation between identical bars; count includes first
    bend_radius_mm: float = Field(ge=0, le=1000)
    cover_mm: float = Field(ge=0, le=300)
    source: Text = ""
    role: Text = ""
    generated_by: Literal["auto-drafting-1.0.0"] | None = None

    @model_serializer(mode="wrap")
    def preserve_manual(self,handler):
        data=handler(self)
        if self.generated_by is None:data.pop("generated_by",None)
        return data


class DrawingStudy(Strict):
    basis: Literal["design_draft", "demonstration"] = "design_draft"
    placements: list[Placement] = Field(default_factory=list, max_length=200)
    openings: list[Opening] = Field(default_factory=list, max_length=100)
    cuts: list[Cut] = Field(default_factory=list, max_length=12)
    bars: list[BarGroup] = Field(default_factory=list, max_length=80)
    notes: list[Text] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def uniqueness(self):
        for rows, key in ((self.placements,"element_id"),(self.openings,"id"),(self.cuts,"id"),(self.bars,"mark")):
            values=[getattr(r,key) for r in rows]
            if len(values)!=len(set(values)):
                raise ValueError(f'Marcas do processo duplicadas: {key}')
        if sum(b.count for b in self.bars)>4000:
            raise ValueError("Máximo de 4 000 varões desenhados por processo")
        work=sum(b.count*(2+42*(len(b.points)-2))*(1+sum(o.element_id==b.element_id for o in self.openings)) for b in self.bars)
        if work>2_000_000:
            raise ValueError("Processo demasiado complexo: distribua os aços e negativos por vários estudos")
        return self


def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def unit(a): return mul(a,1/math.sqrt(dot(a,a)))


def bar_geometry(bar):
    """Exact developed length + tessellated 3D circular centreline for drawing.

    Positive turns require an explicit centreline radius. No default mandrel,
    hooks, anchorage or lap is invented. A closed polyline isn't an end closure.
    """
    pts=[p.xyz() for p in bar.points]
    lengths=[math.dist(a,b) for a,b in zip(pts,pts[1:])]
    if min(lengths)<1e-6:
        raise ValueError("Dois pontos do varão estão confundidos")
    radius=bar.bend_radius_mm/1000
    trims=[0.]*len(lengths); bends={}; adjustment=0.
    for i in range(1,len(pts)-1):
        u=unit(sub(pts[i],pts[i-1])); v=unit(sub(pts[i+1],pts[i]))
        theta=math.acos(max(-1.,min(1.,dot(u,v))))
        if theta<1e-7: continue
        if math.pi-theta<1e-6: raise ValueError("Meia volta a descrever por vários pontos")
        if radius<=bar.diameter_mm/2000:
            raise ValueError("Raio ao eixo superior ao meio diâmetro necessário para uma dobra")
        cut=radius*math.tan(theta/2)
        trims[i-1]+=cut;trims[i]+=cut;adjustment+=radius*theta-2*cut
        start=sub(pts[i],mul(u,cut)); end=add(pts[i],mul(v,cut))
        normal=unit(sub(v,mul(u,math.cos(theta))))
        center=add(start,mul(normal,radius))
        a=sub(start,center)
        steps=max(2,math.ceil(theta/(math.pi/36)))
        angles={theta*j/steps for j in range(steps+1)}
        for k in range(3):
            extremum=math.atan2(u[k]*radius,a[k])
            for j in range(-2,3):
                candidate=extremum+j*math.pi
                if 0<candidate<theta:angles.add(candidate)
        arc=[add(center,add(mul(a,math.cos(t)),mul(u,radius*math.sin(t)))) for t in sorted(angles)]
        arc[0]=start;arc[-1]=end
        bends[i]=arc
    if any(t>length+1e-8 for t,length in zip(trims,lengths)):
        raise ValueError("O raio de dobragem não cabe entre os pontos")
    path=[pts[0]]
    for i in range(1,len(pts)-1): path.extend(bends.get(i,[pts[i]]))
    path.append(pts[-1])
    return sum(lengths)+adjustment,path


def world(e, point, base=0.):
    a=math.radians(e.angle_deg);x,y,z=point
    return (e.x_m+x*math.cos(a)-y*math.sin(a),e.y_m+x*math.sin(a)+y*math.cos(a),base+z)


def outline(e, box=None):
    lo,hi=box or ((0.,0.,0.),(e.length_m,e.width_m,e.height_m))
    return [world(e,(x,y,lo[2]))[:2] for x,y in ((lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1]))]


def section_interval(poly, cut):
    """Intersection of a convex footprint with x/y section line, including rotation."""
    horizontal=0 if cut.axis=="x" else 1; other=1-horizontal
    coords=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da=a[other]-cut.at_m;db=b[other]-cut.at_m
        if abs(da)<1e-8:coords.append(a[horizontal])
        if da*db<0:
            t=da/(da-db);coords.append(a[horizontal]+t*(b[horizontal]-a[horizontal]))
    return (min(coords),max(coords)) if coords and max(coords)-min(coords)>1e-8 else None


def segment_hits_box(a,b,box,margin=0.):
    """Slab intersection, including endpoints; expanded opening catches bar radius."""
    lo,hi=box;t0,t1=0.,1.
    for k in range(3):
        low,high=lo[k]-margin,hi[k]+margin;d=b[k]-a[k]
        if abs(d)<1e-12:
            if a[k]<low or a[k]>high:return False
        else:
            q1,q2=sorted(((low-a[k])/d,(high-a[k])/d));t0=max(t0,q1);t1=min(t1,q2)
            if t0>t1:return False
    return True


def compile_dossier(model, revision=1):
    """Manifest, checks and nomenclature recomputed from this saved model only."""
    from engines.structuro_calc import calculate
    result=calculate(model);d=model.drawings
    errors=[];warnings=[];rows=[];sheets=[]
    def issue(code,ref,message): errors.append(dict(code=code,ref=ref,message=message))
    if model.automation_generated_hash or (d and any(b.generated_by for b in d.bars)):
        from engines.structuro_automation import generation_hash
        if model.automation_generated_hash!=generation_hash(model):
            issue("automation_stale","Automatização","Dados alterados: relançar a geração automática antes da exportação.")
    if not d:issue("missing_dossier","Dossier","Ative o processo de plantas e indique as cotas.")
    if not model.elements:issue("missing_elements","Modelo","Nenhum elemento a desenhar.")
    es={e.id:e for e in model.elements}
    places={p.element_id:p for p in d.placements} if d else {}
    valid=set()
    for e in es.values():
        if any(v is None for v in (e.x_m,e.y_m,e.length_m,e.width_m,e.height_m)):
            issue("geometry",e.id,"Coordenadas x/y e três dimensões obrigatórias.")
        elif e.id not in places:issue("elevation",e.id,"Cota de base em falta.")
        else:valid.add(e.id)
        if not e.reviewed:warnings.append(f'{e.id} : introdução do elemento a controlar.')
    if d:
        for p in d.placements:
            if p.element_id not in es:issue("unknown_element",p.element_id,"Implantação sem elemento correspondente.")
            if not p.source.strip():warnings.append(f'{p.element_id} : fonte da cota a indicar.')
        for o in d.openings:
            e=es.get(o.element_id)
            if o.element_id not in valid:issue("opening_element",o.id,"Negativo: elemento ausente ou geometria incompleta.");continue
            lo,hi=o.box();dims=(e.length_m,e.width_m,e.height_m)
            if any(a<-1e-8 or b>size+1e-8 for a,b,size in zip(lo,hi,dims)):
                issue("opening_outside",o.id,"O negativo sai do volume do seu elemento.")
            if not o.source.strip():warnings.append(f'{o.id} : fonte do negativo a indicar.')
        for b in d.bars:
            if b.element_id not in valid:issue("bar_element",b.mark,"Varão: elemento ausente ou geometria incompleta.");continue
            try:length,path=bar_geometry(b)
            except ValueError as ex:issue("bar_shape",b.mark,str(ex));continue
            e=es[b.element_id];dims=(e.length_m,e.width_m,e.height_m)
            cover=(b.cover_mm+b.diameter_mm/2)/1000
            vec=b.repeat.xyz()
            if b.count>1 and math.sqrt(dot(vec,vec))<b.diameter_mm/1000-1e-9:
                issue("bar_repeat",b.mark,"Repetição demasiado baixa: varões sobrepostos.")
            outside=False;hit=False
            for i in range(b.count):
                ps=[add(p,mul(vec,i)) for p in path]
                # Arcs are sampled at <=5 degrees. Extra 1 mm tolerance envelope
                # conservatively catches their deviation from the straight chords.
                if any(p[k]<cover-1e-8 or p[k]>dims[k]-cover+1e-8 for p in ps for k in range(3)):
                    outside=True
                for o in d.openings:
                    if o.element_id==b.element_id and any(segment_hits_box(a,c,o.box(),cover+.001) for a,c in zip(ps,ps[1:])):hit=True
            if outside:issue("bar_cover",b.mark,"Um varão sai do elemento ou do recobrimento declarado.")
            if hit:issue("bar_opening",b.mark,"Um varão atravessa um negativo ou o seu recobrimento declarado.")
            if not b.source.strip():warnings.append(f'{b.mark} : justificação das armaduras a indicar.')
            mass=math.pi*(b.diameter_mm/1000)**2/4*7850*length*b.count
            rows.append(dict(mark=b.mark,element_id=b.element_id,diameter_mm=b.diameter_mm,count=b.count,
                developed_length_m=length,total_length_m=length*b.count,mass_kg=mass,
                bend_radius_mm=b.bend_radius_mm,cover_mm=b.cover_mm,source=b.source,role=b.role))
        for cut in d.cuts:
            if not any(section_interval(outline(es[eid]),cut) for eid in valid):
                issue("empty_cut",cut.id,"O corte não atravessa nenhum elemento.")
        if not d.cuts:warnings.append("Nenhum corte definido.")
        if not d.bars:warnings.append("Nenhum aço desenhado: nem armaduras nem lista gerados.")
        if d.openings:warnings.append("Os negativos estão desenhados; o motor gravítico conserva os volumes brutos e não modela o seu efeito na resistência. Adapte o esquema estrutural.")
    if result["status"]=="blocked":warnings.append("Cálculo gravítico incompleto: as plantas não são justificadas por uma descida de cargas completa.")
    if d and any(b.generated_by for b in d.bars):
        warnings.append("Secções de betão introduzidas; escolha automática dos aços limitada a vigas simples e lajes maciças. Paredes, pilares, espessura e aços das sapatas não dimensionados por esta cadeia.")
        warnings.append("Comprimentos de amarração e emenda calculados na nota automática; implantação nos apoios, ligações e interações entre grupos a verificar.")
    else:
        warnings.append("Secções e aços introduzidos: nenhum dimensionamento global automático. Amarrações, emendas, interações entre grupos e regras construtivas continuam por verificar.")
    levels=list(dict.fromkeys(e.level for e in model.elements))
    # Ordered, stable sheet families. Catalogue pagination never hides warnings.
    lines=[]
    for msg in warnings+(d.notes if d else []):
        lines.extend(textwrap.wrap("• "+msg,width=90,subsequent_indent="  ") or [""])
        lines.append("")
    for i in range(0,max(1,len(lines)),28):
        sheets.append(dict(id=f"G{i//28+1:02}",kind="general",title="Processo e controlos",lines=lines[i:i+28]))
    for n,lev in enumerate(levels,1):sheets.append(dict(id=f"C{n:02}",kind="formwork",title=f'Cofragem - {lev}',level=lev))
    for i in range(0,len(model.elements),12):sheets.append(dict(id=f"R{i//12+1:02}",kind="members",title="Marcação e dimensões da cofragem",offset=i))
    if d:
        for i in range(0,len(d.openings),12):sheets.append(dict(id=f"O{i//12+1:02}",kind="openings",title="Marcação e dimensões dos negativos",offset=i))
        for n,c in enumerate(d.cuts,1):sheets.append(dict(id=f"S{n:02}",kind="section",title=f"Coupe {c.id}",cut=c.id))
        for n,lev in enumerate(levels,1):
            if any(es.get(b.element_id) and es[b.element_id].level==lev for b in d.bars):sheets.append(dict(id=f"F{n:02}",kind="reinforcement",title=f'Armaduras - {lev}',level=lev))
        for n,b in enumerate(d.bars,1):sheets.append(dict(id=f"D{n:02}",kind="detail",title=f'Detalhe {b.mark} - {b.element_id}',mark=b.mark))
        for i in range(0,len(rows),19):sheets.append(dict(id=f"N{i//19+1:02}",kind="schedule",title="Lista de aços",offset=i))
    normalized=type(model).model_validate_json(model.model_dump_json()).model_dump(mode="json")
    digest=hashlib.sha256(json.dumps(dict(version=VERSION,model=normalized),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return dict(version=VERSION,revision=revision,input_hash=result["input_hash"],drawing_hash=digest,
        execution_ready=False,status="blocked" if errors else "demonstration" if d and d.basis=="demonstration" else "design_draft",
        can_export=not errors,errors=errors,warnings=warnings,sheets=sheets,schedule=rows,
        total_mass_kg=sum(r["mass_kg"] for r in rows),mechanical_status=result["status"])
