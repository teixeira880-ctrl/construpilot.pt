"""Plans already read by ConstruPilot → the common project of estudo.py.

- from_plan_page: a page of the traditional take-off (plans_takeoff: walls_analysis of engines.plan_walls, two-face
  walls read on a vector PDF or a DXF, plus the rooms drawn by the user). Wall axes are in page pixels; metres =
  pixels ÷ (pt_per_m × px_per_pt). The y axis is flipped so the plan reads with y up, like the CLT engine.
- from_clt_walls: walls already in metres (CLT PDF reader, CLT page, IFC) → the same project format.

Nothing is invented: a wall without an axis or thickness is skipped and listed; ambiguous walls are kept and listed
for confirmation. Openings are not positioned by the traditional reader, so they are inferred from the gaps between
runs (inferir_vaos) and stay "estimativa" until confirmed.
"""
from __future__ import annotations


def from_plan_page(page: dict, *, name: str, nivel: int = 0, rooms: list | None = None, room_ppm: float | None = None,
                   system: str | None = None, ref: str = "") -> tuple[dict, list[str]]:
    analysis = page.get("walls_analysis") or {}
    ppm, px = analysis.get("pt_per_m"), analysis.get("px_per_pt")
    notes = []
    if not ppm or not px:
        raise ValueError("A página não tem escala: calibre a planta antes de a medir.")
    k = 1 / (ppm * px)
    walls = []
    for w in analysis.get("walls") or []:
        axis, t = w.get("axis") or {}, w.get("thickness_m")
        if w.get("is_post"):
            continue
        if not axis or not t:
            notes.append(f"{w.get('wall_id')}: sem eixo ou espessura, não medida")
            continue
        if w.get("ambiguous"):
            notes.append(f"{w.get('wall_id')}: leitura ambígua, a confirmar")
        walls.append({"id": f"{name[:12]}-{w['wall_id']}", "x1": axis["x1"] * k, "y1": -axis["y1"] * k, "x2": axis["x2"] * k,
                      "y2": -axis["y2"] * k, "thickness_mm": round(float(t) * 1000, 1), "sistema": system,
                      "source": (f"{ref} {w['wall_id']} ({w.get('source')}, confiança {w.get('confidence')})").strip()[:200]})
    walls = [w for w in walls if ((w["x2"] - w["x1"]) ** 2 + (w["y2"] - w["y1"]) ** 2) ** .5 >= 0.05]
    if not walls:
        raise ValueError("Nenhuma parede lida nesta página.")
    divisoes = []
    rk = 1 / room_ppm if room_ppm else k
    for r in rooms or []:
        pts = r.get("points") or []
        if len(pts) >= 3:
            divisoes.append({"nome": str(r.get("name") or r.get("label") or r.get("room_id") or "divisão")[:60],
                             "poligono": [(float(p[0] if isinstance(p, (list, tuple)) else p["x"]) * rk,
                                           -float(p[1] if isinstance(p, (list, tuple)) else p["y"]) * rk) for p in pts]})
    cad = (page.get("cad_import") or {}) or page.get("geometry_coordinate_space") == "dxf"
    floor = {"nome": name, "nivel": nivel, "paredes": walls, "divisoes": divisoes, "inferir_vaos": True, "ligar": True,
             "leitura": "dxf" if cad else "vetorial"}
    return floor, notes


def from_clt_walls(name, walls, *, nivel=0, lintels=(), height_m=None, leitura="vetorial"):
    """Walls of the CLT engines (bim_studio.clt_walls.WallAxis or dicts) → a floor of the common project, system CLT."""
    out = []
    for w in walls:
        d = w.model_dump() if hasattr(w, "model_dump") else dict(w)
        out.append({k: d[k] for k in ("id", "x1", "y1", "x2", "y2", "thickness_mm", "openings", "source") if k in d}
                   | {"layers": d.get("layers"), "height_m": d.get("height_m") if height_m is None else height_m,
                      "base_z_m": d.get("base_z_m", 0.0), "sistema": "clt"})
    return {"nome": name, "nivel": nivel, "paredes": out, "linteis": list(lintels), "ligar": True, "leitura": leitura}
