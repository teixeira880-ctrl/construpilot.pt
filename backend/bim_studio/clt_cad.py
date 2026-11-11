"""DXF input for explicit panel and opening layers in model space."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import ezdxf
from ezdxf.units import conversion_factor

from bim_studio.clt_geometry import closed_polygon, panel_quantities


def measure_dxf(data, panel_layer, opening_layer, thickness_mm):
    if opening_layer and panel_layer.casefold() == opening_layer.casefold():
        raise ValueError("Use camadas diferentes para painéis e recortes.")
    with TemporaryDirectory() as folder:
        source = Path(folder) / "input.dxf"
        source.write_bytes(data)
        doc = ezdxf.readfile(source)
    try:
        factor = conversion_factor(doc.units, ezdxf.units.M)
    except (ValueError, TypeError, IndexError) as exc:
        raise ValueError("O DXF precisa de unidades declaradas no espaço de modelo.") from exc

    entities = {panel_layer.casefold(): []}
    if opening_layer:
        entities[opening_layer.casefold()] = []
    for entity in doc.modelspace():
        layer = entity.dxf.get("layer", "0").casefold()
        if layer not in entities:
            continue
        if (entity.dxftype() != "LWPOLYLINE" or not entity.closed or entity.has_arc
                or tuple(entity.dxf.extrusion) != (0, 0, 1)):
            raise ValueError(f"A entidade {entity.dxf.handle} precisa de um contorno linear fechado no plano XY.")
        if len(entity) > 4096 or sum(map(len, entities.values())) >= 500:
            raise ValueError("Divida o desenho em lotes com até 500 contornos.")
        ring = [(x * factor, y * factor) for x, y in entity.get_points("xy")]
        if ring and ring[-1] != ring[0]:
            ring.append(ring[0])
        entities[layer].append((entity.dxf.handle, float(entity.dxf.elevation), ring, closed_polygon(ring)))

    panels = entities[panel_layer.casefold()]
    if not panels:
        raise ValueError("A camada de painéis não contém contornos.")
    for i, (_, z, _, polygon) in enumerate(panels):
        if any(z == prior_z and polygon.intersection(prior).area > 1e-9
               for _, prior_z, _, prior in panels[:i]):
            raise ValueError("Há painéis sobrepostos no mesmo plano.")
    cuts = {handle: [] for handle, *_ in panels}
    for cut_id, z, ring, hole in entities.get((opening_layer or "").casefold(), []):
        hosts = [h for h, panel_z, _, p in panels if z == panel_z and p.covers(hole)]
        if len(hosts) != 1:
            raise ValueError(f"O recorte {cut_id} deve pertencer a exatamente um painel.")
        cuts[hosts[0]].append((cut_id, ring))
    return [
        {"handle": handle, "elevation_m": z * factor, "opening_handles": [cid for cid, _ in cuts[handle]],
         **panel_quantities(ring, [coords for _, coords in cuts[handle]], thickness_mm)}
        for handle, z, ring, _ in panels
    ]
