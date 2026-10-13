"""Deterministic drafting automation from reviewed project inputs.

Restricted positive simple-span bending, single layer; one-way solid slabs;
centred bearing-area search. No global design, site-soil inference or EXE visa.
Reference basis: JRC EUR 26566 EN (2014), chapters 3-4. See accompanying docs.
"""
from __future__ import annotations
import hashlib
import json
import math
from typing import Annotated, Literal
from pydantic import Field, model_validator
from engines.structuro_rebar import Strict, Materials, Section, section_design
from engines.structuro_drawings import ID, Point, Placement, Cut, BarGroup, DrawingStudy, bar_geometry, outline

VERSION='auto-drafting-1.0.0'
Text=Annotated[str,Field(max_length=600)]
Positive=Annotated[float,Field(gt=0,le=10000)]
Coordinate=Annotated[float,Field(ge=-10000,le=10000)]


class FoundationRule(Strict):
    element_id: ID
    mode: Literal['strip','square_pad']
    sls_case_ids: list[ID]=Field(min_length=1,max_length=12)
    uls_case_ids: list[ID]=Field(min_length=1,max_length=12)
    q_sls_kpa: Positive
    q_uls_kpa: Positive
    min_width_m: Positive
    max_width_m: Positive
    width_step_m: float=Field(ge=.01,le=.5)
    same_site_confirmed: bool=False
    centred_vertical_confirmed: bool=False
    soil_source: Text=''
    @model_validator(mode='after')
    def domain(self):
        if self.max_width_m<self.min_width_m or (self.max_width_m-self.min_width_m)/self.width_step_m>200:
            raise ValueError('Catalogue de semelles invalide ou supérieur à 201 dimensions')
        return self


class AutomationSettings(Strict):
    confirmed: bool=False
    regenerate_on_save: bool=True
    materials: Materials | None=None
    cover_mm: float | None=Field(default=None,ge=10,le=100)
    aggregate_mm: float | None=Field(default=None,gt=0,le=63)
    fctk005_mpa: float | None=Field(default=None,gt=0,le=5)
    bond_eta1: Literal[0.7,1.0] | None=None
    cot_theta: float=Field(default=1.,ge=1,le=2.5)
    uls_case_ids: list[ID]=Field(default_factory=list,max_length=12)
    rc_element_ids: list[ID]=Field(default_factory=list,max_length=60)
    diameters_mm: list[Literal[8,10,12,14,16,20,25,32]]=Field(default_factory=lambda:[10,12,14,16,20,25],min_length=1,max_length=8)
    stirrup_diameters_mm: list[Literal[6,8,10,12]]=Field(default_factory=lambda:[8,10],min_length=1,max_length=4)
    spacings_mm: list[Annotated[int,Field(ge=50,le=300)]]=Field(default_factory=lambda:[75,100,125,150,175,200,250],min_length=1,max_length=12)
    max_bars_per_layer: int=Field(default=8,ge=2,le=12)
    # The span direction and validity of the simple uniform one-way scheme are explicit.
    slab_span_axes: dict[ID,Literal['x','y']]=Field(default_factory=dict,max_length=100)
    available_anchorage_mm: dict[ID,Positive]=Field(default_factory=dict,max_length=200)
    level_base_z_m: dict[Annotated[str,Field(max_length=60)],Coordinate]=Field(default_factory=dict,max_length=40)
    level_top_z_m: dict[Annotated[str,Field(max_length=60)],Coordinate]=Field(default_factory=dict,max_length=40)
    foundations: list[FoundationRule]=Field(default_factory=list,max_length=50)
    source: Text=''
    @model_validator(mode='after')
    def unique(self):
        for values in (self.uls_case_ids,self.rc_element_ids,self.diameters_mm,self.stirrup_diameters_mm,self.spacings_mm,[f.element_id for f in self.foundations]):
            if len(values)!=len(set(values)):raise ValueError('Valeur en double dans les règles automatiques')
        return self


def generation_hash(model):
    from engines.structuro_calc import VERSION as gravity_version
    from engines.structuro_drawings import VERSION as drawing_version
    from engines.structuro_rebar import VERSION as rebar_version
    normalized=type(model).model_validate_json(model.model_dump_json()).model_dump(exclude={'automation_generated_hash'})
    return hashlib.sha256(json.dumps(dict(engine=VERSION,gravity=gravity_version,drawings=drawing_version,rebar=rebar_version,model=normalized),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def area(phi):return math.pi*phi*phi/4

def anchorage(phi,settings):
    """Straight tension at fyd, alpha1..5=1; worst lap fraction alpha6=1.5.
    This is a required length, not a verification of the available support space.
    """
    fyd=settings.materials.fyk_mpa/settings.materials.gamma_s
    fbd=2.25*settings.bond_eta1*settings.fctk005_mpa/settings.materials.gamma_c
    basic=phi*fyd/(4*fbd)
    return dict(fbd_mpa=fbd,sigma_sd_mpa=fyd,lb_rqd_mm=basic,
        lbd_mm=math.ceil(max(basic,.3*basic,10*phi,100)/10)*10,
        lap_mm=math.ceil(max(1.5*basic,.3*1.5*basic,15*phi,200)/10)*10,
        basis='Traction droite à fyd ; alpha1..5=1 ; alpha6=1,5 ; conditions à vérifier',execution_ready=False)


def mark(eid,suffix):return 'AUTO_'+eid[:35]+'_'+hashlib.sha256(eid.encode()).hexdigest()[:6]+'_'+suffix

def group(e,tag,phi,count,pts,repeat,cover,role,radius=0.):
    return BarGroup(mark=mark(e.id,tag),element_id=e.id,diameter_mm=float(phi),count=count,
        points=[Point(x=float(x),y=float(y),z=float(z)) for x,y,z in pts],
        repeat=Point(x=float(repeat[0]),y=float(repeat[1]),z=float(repeat[2])),bend_radius_mm=float(radius),cover_mm=cover,
        source=f'{VERSION} : efforts de la révision courante ; contrôles locaux seulement.',role=role,generated_by=VERSION)


def section_cases(e,forces,settings,d,provided,kind='beam',b=None):
    rows=[]
    for case,med,ved in forces:
        sec=Section(id=e.id,kind=kind,b_mm=b if b is not None else e.width_m*1000,h_mm=e.height_m*1000,d_mm=d,
            med_knm=med,ved_kn=ved,materials=settings.materials,as_provided_mm2=provided,cot_theta=settings.cot_theta,
            source=settings.source or VERSION,case=case)
        r=section_design(sec)
        if r['status']!='partial':return None
        rows.append(dict(case_id=case,input=sec.model_dump(),result=r))
    return rows


def choose_beam(e,forces,rules):
    """Search catalogue; all cases checked with the actual chosen centroid."""
    c=rules.cover_mm;h=e.height_m*1000;b=e.width_m*1000;L=e.length_m
    best=None
    for phi in sorted(rules.diameters_mm):
        for stirrup in sorted(rules.stirrup_diameters_mm):
            radius=2.5*stirrup # internal mandrel=4phi for phi<=12; concrete bearing not verified
            # Move bottom corner bars inside the rounded link, including their radius.
            offset=max(c+stirrup+phi/2,c+stirrup/2+radius-(radius-stirrup/2-phi/2)/math.sqrt(2))
            d=h-offset
            if d<=0 or b<=2*offset:continue
            for n in range(2,rules.max_bars_per_layer+1):
                clear=(b-2*offset)/(n-1)-phi
                if clear<max(phi,20.,rules.aggregate_mm+5)-1e-8:continue
                checks=section_cases(e,forces,rules,d,n*area(phi))
                if not checks:continue
                asw=max(x['result']['asw_required_mm2_m'] for x in checks)
                smax=min(x['result']['stirrup_spacing_max_mm'] for x in checks)
                if b-2*c-stirrup>min(.75*d,600):continue
                spacing=next((s for s in sorted(rules.spacings_mm,reverse=True) if s<=smax and 2*area(stirrup)*1000/s>=asw),None)
                if spacing is None:continue
                # Open two-leg stirrup, inward 135-degree hooks, actual straight tail
                # max(5phi,50) beyond the bend; no torsion/closed-hoop claim.
                tail=max(5*stirrup,50)+radius*math.tan(3*math.pi/8)
                projection=tail/math.sqrt(2)
                low=c+stirrup/2;high=b-low;top=h-low
                if high-low-2*projection<stirrup+5 or top-low<2*radius+projection:continue
                xedge=(c+stirrup/2)/1000
                if L<=2*xedge:continue
                links=math.ceil((L-2*xedge)/(spacing/1000))+1
                if links>500:continue
                pitch=(L-2*xedge)/(links-1)
                link=group(e,'E',stirrup,links,[(xedge,(low+projection)/1000,(top-projection)/1000),(xedge,low/1000,top/1000),
                    (xedge,low/1000,low/1000),(xedge,high/1000,low/1000),(xedge,high/1000,top/1000),(xedge,(high-projection)/1000,(top-projection)/1000)],
                    (pitch,0,0),c,'Étriers 2 branches, retours 135° ; assemblage et ancrage local à vérifier',radius)
                try:link_length,_=bar_geometry(link)
                except ValueError:continue
                end=(c+phi/2)/1000
                if L<=2*end:continue
                bottom=group(e,'B',phi,n,[(end,offset/1000,offset/1000),(L-end,offset/1000,offset/1000)],
                    (0,(b-2*offset)/(n-1)/1000,0),c,'Travée : armatures calculées de flexion positive ; liaison aux appuis à vérifier')
                hanger_phi=min(rules.diameters_mm)
                ho=max(c+stirrup+hanger_phi/2,c+stirrup/2+radius-(radius-stirrup/2-hanger_phi/2)/math.sqrt(2))
                hanger=group(e,'H',hanger_phi,2,[((c+hanger_phi/2)/1000,ho/1000,(h-ho)/1000),(L-(c+hanger_phi/2)/1000,ho/1000,(h-ho)/1000)],
                    (0,(b-2*ho)/1000,0),c,'Montage des étriers seulement ; aucun moment négatif couvert')
                cost=n*area(phi)*(L-2*end)+links*area(stirrup)*link_length+2*area(hanger_phi)*(L-2*(c+hanger_phi/2)/1000)
                if best is None or cost<best[0]:
                    best=(cost,[bottom,hanger,link],dict(element_id=e.id,kind='beam',status='local_checks_only',
                        diameter_mm=phi,count=n,as_provided_mm2=n*area(phi),as_required_mm2=max(x['result']['as_required_mm2'] for x in checks),
                        d_mm=d,clear_spacing_mm=clear,stirrup_diameter_mm=stirrup,stirrup_count=links,stirrup_spacing_mm=pitch*1000,
                        asw_provided_mm2_m=2*area(stirrup)/pitch,asw_required_mm2_m=asw,cases=checks,anchorage=anchorage(phi,rules)))
    return None if best is None else best[1:]


def choose_slab(e,forces,rules,axis):
    """Main and distribution bottom layers; no opening, point load or continuity."""
    span=e.length_m if axis=='x' else e.width_m
    width=e.width_m if axis=='x' else e.length_m
    c=rules.cover_mm;best=None
    for phi in sorted(rules.diameters_mm):
        edge=(c+phi/2)/1000;d=e.height_m*1000-c-phi/2
        if d<=0 or min(span,width)<=2*edge:continue
        for nominal in sorted(rules.spacings_mm,reverse=True):
            if nominal>min(2*e.height_m*1000,250):continue
            n=math.ceil((width-2*edge)/(nominal/1000))+1
            if n>500:continue
            pitch=(width-2*edge)/(n-1);provided=area(phi)/pitch
            if pitch*1000-phi<max(phi,20,rules.aggregate_mm+5):continue
            checks=section_cases(e,forces,rules,d,provided,'slab_strip',1000.)
            if not checks:continue
            # Distribution steel >= 20% main AND the same local slab As,min.
            dist_min=max(.2*provided,max(x['result']['as_min_mm2'] for x in checks))
            for transverse in sorted(rules.diameters_mm):
                z=c+phi+transverse/2;side=(c+transverse/2)/1000
                if z+transverse/2+c>=e.height_m*1000:continue
                max_pitch=min(3*e.height_m*1000,400,max(rules.spacings_mm),area(transverse)*1000/dist_min)
                count=math.ceil((span-2*side)/(max_pitch/1000))+1
                if not 2<=count<=500:continue
                ts=(span-2*side)/(count-1)
                if ts*1000-transverse<max(transverse,20,rules.aggregate_mm+5):continue
                if axis=='x':
                    main=group(e,'B',phi,n,[(edge,edge,edge),(span-edge,edge,edge)],(0,pitch,0),c,'Nappe principale, travée simplement appuyée')
                    cross=group(e,'X',transverse,count,[(side,side,z/1000),(side,width-side,z/1000)],(ts,0,0),c,'Répartition transversale, minima locaux')
                else:
                    main=group(e,'B',phi,n,[(edge,edge,edge),(edge,span-edge,edge)],(pitch,0,0),c,'Nappe principale Y, travée simplement appuyée')
                    cross=group(e,'X',transverse,count,[(side,side,z/1000),(width-side,side,z/1000)],(0,ts,0),c,'Répartition transversale X, minima locaux')
                cost=n*area(phi)*(span-2*edge)+count*area(transverse)*(width-2*side)
                if best is None or cost<best[0]:best=(cost,[main,cross],dict(element_id=e.id,kind='slab',status='local_checks_only',
                    span_axis=axis,span_m=span,diameter_mm=phi,count=n,spacing_mm=pitch*1000,d_mm=d,
                    as_provided_mm2_m=provided,as_required_mm2_m=max(x['result']['as_required_mm2'] for x in checks),
                    distribution_diameter_mm=transverse,distribution_spacing_mm=ts*1000,cases=checks,anchorage=anchorage(phi,rules)))
    return None if best is None else best[1:]


def resize_foundations(model,gravity,report):
    """Only bearing area, preserving thickness and centre. Recompute own weight.
    Soil limits and catalogue bounds are explicitly supplied for THIS site.
    """
    settings=model.automation_settings;elements={e.id:e for e in model.elements}
    cases={c['id']:c for c in gravity['cases']};combos={c.id for c in model.combinations}
    for rule in settings.foundations:
        def fail(message):report['issues'].append(dict(element=rule.element_id,stage='foundations',message=message))
        e=elements.get(rule.element_id)
        if not e or e.kind!='footing':fail('Semelle introuvable.');continue
        if not rule.same_site_confirmed or not rule.centred_vertical_confirmed or not rule.soil_source.strip():
            fail('G2 du même terrain et chargement vertical centré à confirmer ; aucune portance transférée entre sites.');continue
        if any(c not in combos for c in rule.sls_case_ids+rule.uls_case_ids):fail('Combinaisons ELS/ELU explicites requises.');continue
        if any(v is None for v in (e.x_m,e.y_m)):fail('Implantation nécessaire pour conserver le centre de la semelle.');continue
        incoming=[m for m in model.elements if any(s.target==e.id for s in m.supports)]
        expected='wall' if rule.mode=='strip' else 'column'
        if len(incoming)!=1 or incoming[0].kind!=expected:fail('Une semelle doit recevoir un seul mur (filante) ou poteau (isolée) dans ce domaine.');continue
        support=incoming[0]
        # Explicit centred hypothesis must also agree with current geometry.
        if any(v is None for v in (support.x_m,support.y_m)) or abs(math.sin(math.radians(e.angle_deg-support.angle_deg)))>1e-8:
            fail('Appui et semelle alignés, implantations connues requises.');continue
        from engines.structuro_drawings import world
        a=world(e,(e.length_m/2,e.width_m/2,0));b=world(support,(support.length_m/2,support.width_m/2,0))
        if math.dist(a[:2],b[:2])>.005:fail('Excentricité géométrique détectée ; aucune semelle centrée générée.');continue
        if rule.mode=='strip' and e.length_m+1e-8<support.length_m:fail('La semelle doit couvrir la longueur du mur.');continue
        selected=None
        for k in range(math.floor((rule.max_width_m-rule.min_width_m)/rule.width_step_m+1e-8)+1):
            width=round(rule.min_width_m+k*rule.width_step_m,9)
            length=e.length_m if rule.mode=='strip' else width
            if width<=support.width_m or length<support.length_m:continue
            rows=[]
            for ids,limit,label in ((rule.sls_case_ids,rule.q_sls_kpa,'ELS'),(rule.uls_case_ids,rule.q_uls_kpa,'ELU')):
                for case_id in ids:
                    case=cases[case_id];old=next(x for x in case['elements'] if x['id']==e.id)
                    factor=case['factors'].get(model.self_weight_action,0.)
                    oldweight=e.length_m*e.width_m*e.height_m*e.density_kn_m3*factor
                    newweight=length*width*e.height_m*e.density_kn_m3*factor
                    force=old['total_kn']-oldweight+newweight;q=force/(length*width)
                    rows.append(dict(case_id=case_id,limit_state=label,total_kn=force,q_kpa=q,limit_kpa=limit,passes=q<=limit))
            if all(r['passes'] for r in rows):selected=(length,width,rows);break
        if selected is None:fail('Aucune dimension du catalogue ne satisfait les pressions du rapport fourni.');continue
        length,width,rows=selected;old_dims=[e.length_m,e.width_m,e.height_m]
        angle=math.radians(e.angle_deg);dx=(e.length_m-length)/2;dy=(e.width_m-width)/2
        e.x_m+=dx*math.cos(angle)-dy*math.sin(angle);e.y_m+=dx*math.sin(angle)+dy*math.cos(angle)
        e.length_m=length;e.width_m=width
        report['foundations'].append(dict(element_id=e.id,mode=rule.mode,old_dimensions_m=old_dims,new_dimensions_m=[length,width,e.height_m],
            cases=rows,status='bearing_area_only',soil_source=rule.soil_source,
            unresolved=['Épaisseur conservée, non dimensionnée','Ferraillage, cisaillement, poinçonnement et ancrage non dimensionnés','Assise, tassements, voisinage et stabilité non vérifiés']))


def run_automation(original):
    """Pure function: returns a candidate model and full coverage report; no I/O."""
    from engines.structuro_calc import calculate
    model=original.model_copy(deep=True)
    report=dict(engine_version=VERSION,execution_ready=False,status='blocked',issues=[],designs=[],foundations=[],coverage=[],generated_marks=[],
        source_input_hash=calculate(original)['input_hash'],limits=[
            'Projet non validé pour exécution ; stabilité globale, ELS, feu et dispositions locales à vérifier.',
            'Poteaux, voiles, continuités, torsion, poinçonnement et ouvertures : dimensionnement automatique non disponible.',
            'Ancrage droit calculé à pleine contrainte ; implantation dans les appuis et recouvrements à détailler.',
            'Fondations : recherche de surface portante seulement, sans dimensionnement de l’épaisseur ni des aciers.'])
    report['coverage']=[dict(element_id=e.id,kind=e.kind,status='blocked') for e in model.elements]
    rules=model.automation_settings
    def issue(e,stage,message):report['issues'].append(dict(element=e,stage=stage,message=message))
    if rules is None:issue('Projet','inputs','Règles d’automatisation absentes.');return model,report
    needed=[k for k in ('materials','cover_mm','aggregate_mm','fctk005_mpa','bond_eta1') if getattr(rules,k) is None]
    if not rules.confirmed or not rules.source.strip():needed.append('confirmation et source des règles')
    if not rules.uls_case_ids:needed.append('combinaisons ELU')
    if needed:issue('Projet','inputs','À renseigner : '+', '.join(needed));return model,report
    if rules.fctk005_mpa>rules.materials.fctm_mpa:
        issue('Projet','inputs','fctk,0.05 ne peut pas dépasser fctm.');return model,report
    if any(c not in {x.id for x in model.combinations} for c in rules.uls_case_ids):
        issue('Projet','inputs','Sélectionnez des combinaisons du modèle, pas des actions isolées.');return model,report
    gravity=calculate(model)
    if gravity['status']=='blocked':
        report['issues'] += [dict(element=x['element'] or 'Projet',stage='gravity',message=x['message']) for x in gravity['issues']]
        return model,report
    if gravity.get('architectural_compatibility',{}).get('status') in ('conflicts','incomplete'):
        issue('Projet','architecture','Résoudre les conflits et données manquantes des contrôles architecturaux.');return model,report
    if model.drawings is None:model.drawings=DrawingStudy()
    d=model.drawings
    # Regenerate only generated marks; preserve explicitly drafted reinforcement.
    manual=[b for b in d.bars if b.generated_by is None]
    d.bars=manual[:];model.automation_generated_hash=None
    resize_foundations(model,gravity,report)
    gravity=calculate(model) # fresh self-weight after resizing, no old N carried forward
    report['coverage']=[]
    by_case={case['id']:{e['id']:e for e in case['elements']} for case in gravity['cases']}
    d.placements=[p for p in d.placements if p.generated_by is None]
    placed={p.element_id for p in d.placements}
    for e in model.elements:
        if e.id not in placed:
            levelmap=rules.level_top_z_m if e.kind in ('beam','slab') else rules.level_base_z_m
            if e.level in levelmap and e.height_m is not None:
                base=levelmap[e.level]-(e.height_m if e.kind in ('beam','slab') else 0.)
                d.placements.append(Placement(element_id=e.id,base_z_m=base,source=rules.source,generated_by=VERSION))
            else:issue(e.id,'placement','Altitude du niveau absente ; aucune hauteur inventée.')
        if e.kind not in ('beam','slab'):
            report['coverage'].append(dict(element_id=e.id,kind=e.kind,status='bearing_area_only' if any(x['element_id']==e.id for x in report['foundations']) else 'not_designed'))
            continue
        if e.id not in rules.rc_element_ids:
            issue(e.id,'reinforcement','Élément non affecté explicitement au calcul béton armé automatique.');continue
        if any(b.element_id==e.id for b in manual):
            issue(e.id,'reinforcement','Aciers manuels conservés : retirer ces repères pour autoriser la génération de cet élément.');continue
        if any(o.element_id==e.id for o in d.openings):
            issue(e.id,'reinforcement','Réservation présente : renforts de trémie/ouverture hors domaine, aucun acier automatique.');continue
        if any(v is None for v in (e.x_m,e.y_m)):issue(e.id,'placement','Implantation X/Y absente.');continue
        if e.kind=='beam':
            linked=[s for s in model.linked_sections if s.element_id==e.id]
            if linked:
                issue(e.id,'reinforcement','Section liée préexistante conservée ; retirez ce lien avant de choisir les aciers avec les règles globales.');continue
            forces=[(case,by_case[case][e.id]['moment_max_knm'],by_case[case][e.id]['shear_max_kn']) for case in rules.uls_case_ids]
            chosen=choose_beam(e,forces,rules)
        else:
            axis=rules.slab_span_axes.get(e.id)
            if not axis or len(e.supports)!=2 or any(abs(s.fraction-.5)>1e-8 for s in e.supports) or any(l.mode!='surface' for l in e.loads):
                issue(e.id,'reinforcement','Dalle : sens de portée explicite, charges uniformes et deux transferts égaux requis.');continue
            span=e.length_m if axis=='x' else e.width_m
            forces=[]
            for case in rules.uls_case_ids:
                q=by_case[case][e.id]['total_kn']/(e.length_m*e.width_m)
                forces.append((case,q*span**2/8,q*span/2))
            chosen=choose_slab(e,forces,rules,axis)
        if chosen is None:issue(e.id,'reinforcement','Aucune disposition du catalogue ne satisfait flexion, cisaillement, géométrie et espacement.');continue
        bars,design=chosen
        available=rules.available_anchorage_mm.get(e.id)
        design['anchorage']['available_mm']=available
        design['anchorage']['length_comparison']='unknown' if available is None else 'sufficient_declared_length' if available>=design['anchorage']['lbd_mm'] else 'insufficient_declared_length'
        design['anchorage']['support_detail_verified']=False
        if available is None:issue(e.id,'anchorage','Longueur d’ancrage calculée ; espace disponible dans les appuis à renseigner.')
        elif available<design['anchorage']['lbd_mm']:issue(e.id,'anchorage','Longueur déclarée dans l’appui inférieure à l’ancrage droit calculé.')
        design['straight_bar_anchorage']=[dict(mark=b.mark,diameter_mm=b.diameter_mm,**anchorage(b.diameter_mm,rules)) for b in bars if b.bend_radius_mm==0.]
        d.bars.extend(bars);report['designs'].append(design);report['generated_marks'].extend(b.mark for b in bars)
        report['coverage'].append(dict(element_id=e.id,kind=e.kind,status='local_checks_only'))
    # Every element must appear, including those rejected before selection.
    covered={x['element_id'] for x in report['coverage']}
    report['coverage'].extend(dict(element_id=e.id,kind=e.kind,status='blocked') for e in model.elements if e.id not in covered)
    if not d.cuts:
        drawable=[e for e in model.elements if all(v is not None for v in (e.x_m,e.y_m,e.length_m,e.width_m,e.height_m))]
        if drawable:
            largest=max(drawable,key=lambda e:e.length_m*e.width_m);pts=outline(largest)
            cx=sum(p[0] for p in pts)/4;cy=sum(p[1] for p in pts)/4
            d.cuts=[Cut(id='AUTO_X',axis='x',at_m=cy),Cut(id='AUTO_Y',axis='y',at_m=cx)]
    note='Aciers issus du moteur automatique restreint. Recalcul obligatoire après modification. Ancrages et assemblages dessinés partiellement ; aucun visa d’exécution.'
    if note not in d.notes:d.notes=(d.notes+[note])[-20:]
    # Enforce schema limits after generation; no oversized partial payload is saved.
    try:model.drawings=DrawingStudy.model_validate(d.model_dump())
    except ValueError:
        issue('Projet','generation','Limites de complexité dépassées ; répartir le projet. Aucune génération conservée.')
        return original.model_copy(deep=True),report
    model.automation_generated_hash=generation_hash(model)
    from engines.structuro_drawings import compile_dossier
    manifest=compile_dossier(model)
    report['issues'] += [dict(element=x['ref'],stage='geometry',message=x['message']) for x in manifest['errors']]
    report['status']='partial' if report['designs'] or report['foundations'] else 'blocked'
    report['drawings_ready']=manifest['can_export']
    report['output_input_hash']=calculate(model)['input_hash']
    report['generation_hash']=model.automation_generated_hash
    report['total_mass_kg']=manifest['total_mass_kg']
    return model,report
