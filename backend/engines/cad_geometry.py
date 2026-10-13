"""Géométrie CAO partagée : unités explicites, blocs transformés et courbes.

Les noms de calques sont une indication métier, pas une preuve de matériau.
"""
from __future__ import annotations
import math
from collections import Counter

import ezdxf
from ezdxf.math import Vec3, is_point_in_polygon_2d

UNIT_FACTORS = {'mm':.001, 'cm':.01, 'm':1., 'inches':.0254, 'feet':.3048}
INSUNITS = {1:('inches',.0254),2:('feet',.3048),3:('miles',1609.344),4:('mm',.001),5:('cm',.01),6:('m',1.),
            7:('km',1000.),8:('microinches',.0000000254),9:('mils',.0000254),10:('yards',.9144),
            11:('angstroms',1e-10),12:('nanometers',1e-9),13:('microns',1e-6),14:('decimeters',.1),
            15:('dekameters',10.),16:('hectometers',100.),17:('gigameters',1e9),21:('US survey feet',1200/3937)}


class CadUnitsRequired(ValueError):
    pass


def resolve_units(doc, override=None):
    code=int(doc.header.get('$INSUNITS',0))
    if override:
        if override not in UNIT_FACTORS: raise ValueError('Unité CAO non supportée')
        return {'name':override,'unit_to_m':UNIT_FACTORS[override],'source':'user','declared_code':code}
    if code not in INSUNITS:
        raise CadUnitsRequired('CAD_UNIT_REQUIRED : unité du dessin non définie ; choisissez mm, cm, m, pouces ou pieds.')
    name,factor=INSUNITS[code]
    return {'name':name,'unit_to_m':factor,'source':'INSUNITS','declared_code':code}


def visible(entity, doc, inherited_layer='0'):
    layer=entity.dxf.get('layer','0')
    layer=inherited_layer if layer=='0' else layer
    try:
        definition=doc.layers.get(layer)
        if definition.is_off() or definition.is_frozen(): return False
    except ezdxf.DXFTableEntryError:
        pass
    return not bool(entity.dxf.get('invisible',0))


def walk_entities(doc, entities=None, *, explode_dimensions=True, keep_inserts=False, preserve_blocks=None, diagnostics=None, max_depth=16, max_entities=400000):
    """Décompose les INSERT (dont MINSERT), avec transformations et calque hérité.

    Les références externes absentes et les objets non transformables sont
    signalés ; aucun fichier externe n'est chargé automatiquement.
    """
    issues=diagnostics if diagnostics is not None else []
    emitted=0
    def walk(items, depth=0, layer='0', ancestors=(), source_kind=None, parent_linetype='CONTINUOUS'):
        nonlocal emitted
        for entity in items:
            if not visible(entity,doc,layer): continue
            kind=entity.dxftype()
            effective=entity.dxf.get('layer','0')
            if effective=='0': effective=layer
            linetype=entity.dxf.get('linetype','BYLAYER').upper()
            if linetype=='BYBLOCK': linetype=parent_linetype
            if linetype=='BYLAYER':
                try: linetype=doc.layers.get(effective).dxf.linetype.upper()
                except ezdxf.DXFTableEntryError: linetype='CONTINUOUS'
            if kind=='INSERT':
                name=entity.dxf.name
                if depth>=max_depth or name in ancestors:
                    issues.append({'code':'BLOCK_RECURSION','block':name});continue
                block=doc.blocks.get(name)
                if block is None or block.block.is_xref:
                    issues.append({'code':'XREF_UNRESOLVED','block':name});continue
                inserts=entity.multi_insert() if entity.mcount>1 else [entity]
                for insert in inserts:
                    preserve = preserve_blocks and preserve_blocks(insert, effective)
                    if keep_inserts or preserve:
                        copy=insert.copy();copy.dxf.layer=effective;yield copy
                    if preserve: continue
                    def skipped(e, reason):
                        issues.append({'code':'TRANSFORM_UNSUPPORTED','entity':e.dxftype(),'reason':str(reason)[:160]})
                    try:
                        children=list(insert.virtual_entities(skipped_entity_callback=skipped)) + list(insert.attribs)
                        yield from walk(children,depth+1,effective,ancestors+(name,),source_kind,linetype)
                    except (ezdxf.DXFError,ValueError,TypeError) as exc:
                        issues.append({'code':'BLOCK_UNREADABLE','block':name,'reason':type(exc).__name__})
                continue
            if kind=='DIMENSION' and explode_dimensions:
                try: yield from walk(entity.virtual_entities(),depth+1,effective,ancestors,'dimension',linetype)
                except Exception as exc: issues.append({'code':'DIMENSION_RENDER_MISSING','reason':type(exc).__name__})
                continue
            emitted+=1
            if emitted>max_entities: raise ValueError('CAO trop complexe : limite d’entités atteinte, sélectionner une zone ou une présentation.')
            if entity.is_virtual or (depth==0 and effective==entity.dxf.get('layer','0')):
                clone=entity  # entité virtuelle (déjà une copie) ou entité du document lue seule : pas de deepcopy
            else:
                clone=entity.copy()
            clone.dxf.layer=effective
            clone._cp_role=source_kind
            clone._cp_linetype=linetype
            if tuple(entity.dxf.get('extrusion',(0,0,1))) != (0,0,1) or (kind=='POLYLINE' and entity.is_3d_polyline):
                issues.append({'code':'NON_PLANAR_GEOMETRY','entity':kind})
            yield clone
    yield from walk(doc.modelspace() if entities is None else entities)


def polyline_length_area(entity):
    """Longueur et aire signée des arcs de bulge incluses, sans corde de substitution."""
    if entity.dxftype()=='LWPOLYLINE':
        vertices=[(float(p[0]),float(p[1]),float(p[4])) for p in entity.get_points('xyseb')]
        closed=bool(entity.closed)
    else:
        vertices=[(float(v.dxf.location.x),float(v.dxf.location.y),float(v.dxf.get('bulge',0))) for v in entity.vertices]
        closed=bool(entity.is_closed)
    if len(vertices)<2:return 0.,0.
    pairs=list(zip(vertices,vertices[1:]))
    if closed:pairs.append((vertices[-1],vertices[0]))
    length,area=0.,0.
    for (x1,y1,bulge),(x2,y2,_) in pairs:
        chord=math.hypot(x2-x1,y2-y1)
        area+=(x1*y2-x2*y1)/2
        if abs(bulge)<1e-12 or chord==0:length+=chord;continue
        theta=4*math.atan(bulge)
        radius=chord*(1+bulge*bulge)/(4*abs(bulge))
        length+=abs(radius*theta)
        area+=radius*radius*(theta-math.sin(theta))/2
    return length,abs(area) if closed else 0.


def hatch_area(entity):
    """Aire nette des boucles, en retirant les îlots ; arcs aplatis avec tolérance."""
    from ezdxf.path import from_hatch
    from ezdxf.math import Vec2
    loops=[]
    for path in from_hatch(entity):
        pts=[Vec2(v) for v in path.flattening(distance=.001,segments=16)]
        if len(pts)<3:continue
        area=abs(sum(a.x*b.y-b.x*a.y for a,b in zip(pts,pts[1:]+pts[:1])))/2
        if area>0:loops.append((pts,area))
    total=0.
    for points,area in loops:
        depth=sum(1 for other,bigger in loops if bigger>area and is_point_in_polygon_2d(points[0],other)==1)
        total+=(-1 if depth%2 else 1)*area
    return max(0.,total)


def entity_vectors(entity, to_px, tolerance):
    """Primitives dans le repère de l'aperçu, avec rôle/calque et courbure tracés."""
    from ezdxf.path import make_path
    kind=entity.dxftype()
    style={'layer':entity.dxf.get('layer','0'),'cad_role':getattr(entity,'_cp_role',None),'source_entity_type':kind,
           'dashes':'[1 1] 0' if getattr(entity,'_cp_linetype',entity.dxf.get('linetype','BYLAYER')).upper() not in ('BYLAYER','BYBLOCK','CONTINUOUS') else '[] 0'}
    if kind=='HATCH':
        from ezdxf.path import from_hatch
        result=[]
        for path in from_hatch(entity):
            points=[to_px(p.x,p.y) for p in path.flattening(distance=tolerance,segments=12)]
            if points and points[0]!=points[-1]:points.append(points[0])
            curved=bool(path.has_curves)
            if not curved and len(points)==5:
                result.append({**style,'type':'quad','points':[list(p) for p in points[:4]]})
            else:
                result.extend({**style,'type':'line','p1':list(a),'p2':list(b),'curve_approximation':curved} for a,b in zip(points,points[1:]))
        return result
    if kind=='LINE':
        a,b=entity.dxf.start,entity.dxf.end
        return [{**style,'type':'line','p1':list(to_px(a.x,a.y)),'p2':list(to_px(b.x,b.y))}]
    if kind not in ('LWPOLYLINE','POLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE','SOLID','TRACE','3DFACE'):return []
    try:
        path=make_path(entity)
        points=[to_px(p.x,p.y) for p in path.flattening(distance=tolerance,segments=12)]
        coarse=tolerance
        while len(points)>20000 and coarse<tolerance*64:  # courbe très dense : on relâche la tolérance plutôt que d'échouer
            coarse*=4
            points=[to_px(p.x,p.y) for p in path.flattening(distance=coarse,segments=4)]
        if len(points)>20000:
            step=len(points)//20000+1
            points=points[::step]+[points[-1]]
        if coarse!=tolerance or len(points)>20000: style={**style,'curve_simplified':True}
        closed=bool(path.is_closed)
        if closed and points and points[0]!=points[-1]: points.append(points[0])
        straight=kind in ('SOLID','TRACE','3DFACE') or (kind in ('LWPOLYLINE','POLYLINE') and not bool(entity.has_arc))
        if closed and straight and len(points)==5:
            return [{**style,'type':'quad','points':[list(p) for p in points[:4]]}]
        return [{**style,'type':'line','p1':list(a),'p2':list(b),'curve_approximation':not straight}
                for a,b in zip(points,points[1:])]
    except (TypeError,AttributeError,ezdxf.DXFError):return []


def inventory(doc, entities, diagnostics):
    counts=Counter(e.dxftype() for e in entities)
    layers=Counter(e.dxf.get('layer','0') for e in entities)
    unsupported=sorted(set(counts)-{'LINE','LWPOLYLINE','POLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE','HATCH','SOLID','TRACE','3DFACE','TEXT','MTEXT','ATTRIB','ATTDEF','POINT','DIMENSION'})
    if unsupported:diagnostics.append({'code':'UNSUPPORTED_ENTITIES','types':unsupported})
    layouts=[l.name for l in doc.layouts if l.name!='Model' and any(e.dxftype()!='VIEWPORT' for e in l)]
    if layouts:diagnostics.append({'code':'PAPERSPACE_NOT_ANALYZED','layouts':layouts})
    return {'entity_counts':dict(counts),'layers':[{'name':k,'entities':v} for k,v in sorted(layers.items())],
            'layout':'Model','paper_layouts':layouts,'diagnostics':diagnostics,'complete':not diagnostics}
