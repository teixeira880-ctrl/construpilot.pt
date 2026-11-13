"""Cálculo estrutural de pré-dimensionamento sobre o modelo BIM (cargas verticais).

Modelo analítico 3D gerado a partir do `BuildingModel`:
- pilares encastrados na base, de 0 ao pé-direito; vigas ao nível do topo, ligadas rigidamente aos pilares;
- extremidades de viga apoiadas, por ordem: num pilar, noutra viga (nó partilhado), numa parede resistente
  (apoio simples); uma viga sem apoio é excluída e assinalada — nada é inventado;
- vigas divididas nos pilares e nos cruzamentos com outras vigas (continuidade e vigas secundárias).

Cargas (EN 1991-1-1, habitação, categoria A — valores editáveis): peso próprio da laje (25 kN/m³ × e),
revestimentos, divisórias e sobrecarga, levadas às vigas por faixas de influência (laje armada numa
direção, metade do vão até ao apoio paralelo seguinte ou até ao bordo da laje); peso próprio das vigas
(só a parte abaixo da laje) e dos pilares.

Combinações (EN 1990): ELU 1,35 G + 1,5 Q ; ELS quase-permanente G + ψ2 Q (ψ2 = 0,3), flecha a longo prazo
com E_ef = Ecm / (1 + φ), limite L/250. Dimensionamento das vigas com `engines.structuro_ec2.design_section`
(EN 1992-1-1); pilares verificados à compressão centrada com armadura mínima e esbelteza assinalada.

Âmbito: pré-dimensionamento. Sem ações horizontais (vento, sismo: ver `engines/edificio_ba`) nem verificação
dos pilares à flexão composta. `execution_ready` é sempre False: os resultados são para um engenheiro validar.
Solver: PyNite (MIT).
"""
from __future__ import annotations

import math

from .ifc_builder import stable_guid
from .model import BuildingModel

VERSION = "bim-frame-0.1.0"
SNAP_M = 0.40          # tolerância de ligação viga ↔ pilar / viga / parede (m)
SAMPLES = 11           # pontos por troço para flechas

LOAD_DEFAULTS = {
    "concrete_kn_m3": 25.0,
    "finishes_kn_m2": 1.5,       # revestimentos
    "partitions_kn_m2": 1.0,     # divisórias (EN 1991-1-1 §6.3.1.2, valor equivalente)
    "imposed_kn_m2": 2.0,        # sobrecarga habitação, categoria A (AN PT)
    "psi2": 0.3,
    "gamma_g": 1.35,
    "gamma_q": 1.5,
    "creep_phi": 2.0,
    "deflection_limit": 250.0,   # L/250
    "fck": 25.0,                 # C25/30
    "fyk": 500.0,                # A500
    "cover_m": 0.05,             # d = h − c
}

SOURCE = ("EN 1990 (combinações), EN 1991-1-1 (cargas, cat. A), EN 1992-1-1 §6.1/§6.2/§7.4 — "
          "valores usuais dos Anexos Nacionais, editáveis — pré-dimensionamento a verificar por engenheiro")


class AnalysisError(ValueError):
    pass


def _ecm(fck: float) -> float:
    """Módulo de elasticidade secante (EN 1992-1-1 Quadro 3.1), em kN/m²."""
    return 22.0 * ((fck + 8.0) / 10.0) ** 0.3 * 1e6


# ---------------------------------------------------------------- geometria auxiliar

def _proj(px, py, ax, ay, bx, by):
    """(t ao longo de AB em m, distância ao eixo, comprimento AB)."""
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    t = (px - ax) * ux + (py - ay) * uy
    d = abs(-(px - ax) * uy + (py - ay) * ux)
    return t, d, L


def _seg_intersection(a, b, c, d):
    """Interseção dos segmentos AB e CD → (ta, tc) em fração, ou None (inclui pequenas extensões)."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    ta = (qx * sy - qy * sx) / den
    tc = (qx * ry - qy * rx) / den
    la, lc = math.hypot(rx, ry), math.hypot(sx, sy)
    ea, ec = SNAP_M / la, SNAP_M / lc
    if -ea <= ta <= 1 + ea and -ec <= tc <= 1 + ec:
        return ta, tc
    return None


def _ray_polygon(px, py, dx, dy, pts) -> float | None:
    """Distância do ponto P, na direção (dx, dy), até à aresta mais próxima do polígono."""
    best = None
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        qx, qy = x1 - px, y1 - py
        t = (qx * ey - qy * ex) / den
        u = (qx * dy - qy * dx) / den
        if t > 1e-6 and -1e-9 <= u <= 1 + 1e-9:
            best = t if best is None else min(best, t)
    return best


def _inside(px, py, pts) -> bool:
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            x = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if x > px:
                inside = not inside
    return inside


def _tributary(model: BuildingModel, bm, supports) -> tuple[float, str | None]:
    """Largura de influência (m) de uma viga numa laje armada numa direção."""
    mx, my = (bm.x1 + bm.x2) / 2, (bm.y1 + bm.y2) / 2
    L = bm.length
    ux, uy = (bm.x2 - bm.x1) / L, (bm.y2 - bm.y1) / L
    nx, ny = -uy, ux
    slab = next((s for s in model.slabs if _inside(mx, my, s.points)), None)
    if slab is None:
        return 0.0, "viga fora de qualquer laje lida: só peso próprio"
    width = 0.0
    for sgn in (1, -1):
        dx, dy = nx * sgn, ny * sgn
        edge = _ray_polygon(mx, my, dx, dy, slab.points) or 0.0
        nearest = None
        for (sx1, sy1, sx2, sy2, sid) in supports:
            if sid == bm.source_id:
                continue
            sl = math.hypot(sx2 - sx1, sy2 - sy1)
            if sl < 1e-6:
                continue
            sux, suy = (sx2 - sx1) / sl, (sy2 - sy1) / sl
            if abs(ux * suy - uy * sux) > 0.1:      # só apoios paralelos
                continue
            t, dist, _ = _proj(mx, my, sx1, sy1, sx2, sy2)
            if not (-SNAP_M <= t <= sl + SNAP_M):
                continue
            side = (sx1 - mx) * dx + (sy1 - my) * dy
            if side <= 0.05:
                continue
            nearest = dist if nearest is None else min(nearest, dist)
        span = min(nearest, edge) if nearest is not None else edge
        width += span / 2.0
    return width, None


# ---------------------------------------------------------------- modelo analítico

def build_frame(model: BuildingModel, loads: dict | None = None) -> dict:
    """Nós, barras, apoios e cargas do pórtico (sem chamar o solver)."""
    p = {**LOAD_DEFAULTS, **{k: float(v) for k, v in (loads or {}).items() if v is not None}}
    H = max((w.height for w in model.walls), default=model.params["wall_height"])
    if not model.beams and not model.columns:
        raise AnalysisError("O modelo não tem vigas nem pilares: nada a calcular em pórtico.")
    warnings: list[dict] = []
    nodes: dict[str, tuple[float, float, float]] = {}
    supports: dict[str, str] = {}   # nó → "fixed" | "pinned"

    def node(x, y, z):
        key = f"N{round(x, 2):.2f}_{round(y, 2):.2f}_{round(z, 2):.2f}"
        nodes.setdefault(key, (round(x, 2), round(y, 2), round(z, 2)))
        return key

    members = []   # dict(name, kind, source_id, i, j, b, h, w_g, w_q)
    col_tops = {}
    for c in model.columns:
        base = node(c.cx, c.cy, 0.0)
        top = node(c.cx, c.cy, H)
        supports[base] = "fixed"
        col_tops[c.source_id] = (c, top)
        area = c.dx * c.dy
        members.append({"name": f"C:{c.source_id}", "kind": "column", "source_id": c.source_id, "i": base, "j": top,
                        "b": min(c.dx, c.dy), "h": max(c.dx, c.dy), "w_g": p["concrete_kn_m3"] * area, "w_q": 0.0})

    lb_walls = [w for w in model.walls if w.load_bearing]
    slab_e = max((s.thickness for s in model.slabs), default=0.0)
    q_g = p["concrete_kn_m3"] * slab_e + p["finishes_kn_m2"] + p["partitions_kn_m2"] if model.slabs else 0.0
    q_q = p["imposed_kn_m2"] if model.slabs else 0.0
    support_lines = [(b.x1, b.y1, b.x2, b.y2, b.source_id) for b in model.beams] + \
                    [(w.x1, w.y1, w.x2, w.y2, w.source_id) for w in lb_walls]
    if not model.slabs:
        warnings.append({"code": "no_slab", "detail": "Sem laje lida na planta: vigas só com peso próprio."})

    beam_meta = {}
    for bm in model.beams:
        L = bm.length
        cuts = {0.0: None, L: None}
        # pilares sobre o eixo
        for c, top in col_tops.values():
            t, d, _ = _proj(c.cx, c.cy, bm.x1, bm.y1, bm.x2, bm.y2)
            if d <= SNAP_M and -SNAP_M <= t <= L + SNAP_M:
                cuts[min(max(t, 0.0), L)] = ("column", c)
        # cruzamentos com outras vigas
        for other in model.beams:
            if other is bm:
                continue
            hit = _seg_intersection((bm.x1, bm.y1), (bm.x2, bm.y2), (other.x1, other.y1), (other.x2, other.y2))
            if hit:
                # Ponto exato de interseção das duas retas: idêntico visto de cada viga → nó partilhado.
                xi, yi = bm.x1 + (bm.x2 - bm.x1) * hit[0], bm.y1 + (bm.y2 - bm.y1) * hit[0]
                t = min(max(hit[0], 0.0), 1.0) * L
                if not any(abs(t - k) < 0.05 for k in cuts if cuts[k] and cuts[k][0] == "column"):
                    t = round(t, 3)
                    if cuts.get(t) is None:            # extremidade livre (None) passa a apoiada na outra viga
                        cuts[t] = ("beam", other, (xi, yi))
        ts = sorted(cuts)
        merged = []
        for t in ts:
            if merged and t - merged[-1][0] < 0.10:
                if cuts[t] and not merged[-1][1]:
                    merged[-1] = (merged[-1][0], cuts[t])
                continue
            merged.append((t, cuts[t]))
        ux, uy = (bm.x2 - bm.x1) / L, (bm.y2 - bm.y1) / L
        pts = []
        for t, what in merged:
            if what and what[0] == "column":
                c = what[1]
                pts.append((t, col_tops[c.source_id][1], "column"))
            elif what:
                x, y = what[2]
                pts.append((t, node(x, y, H), "beam"))
            else:
                x, y = bm.x1 + ux * t, bm.y1 + uy * t
                pts.append((t, node(x, y, H), None))

        def end_support(t, key, kind):
            if kind in ("column", "beam"):
                return True
            x, y, _ = nodes[key]
            for w in lb_walls:
                tw, d, Lw = _proj(x, y, w.x1, w.y1, w.x2, w.y2)
                if d <= SNAP_M and -SNAP_M <= tw <= Lw + SNAP_M:
                    # apoio simples; a torção da viga (eixo dominante) é impedida pela parede
                    supports.setdefault(key, "pinned_x" if abs(ux) >= abs(uy) else "pinned_z")
                    return True
            return False

        ok_i = end_support(*pts[0])
        ok_j = end_support(*pts[-1])
        if not (ok_i and ok_j):
            warnings.append({"code": "beam_unsupported", "source_id": bm.source_id,
                             "detail": "Extremidade de viga sem pilar, viga ou parede resistente: viga excluída do cálculo."})
            continue
        trib, note = _tributary(model, bm, support_lines)
        if note:
            warnings.append({"code": "beam_no_slab", "source_id": bm.source_id, "detail": note})
        hang = max(bm.depth - slab_e, 0.0) if model.slabs else bm.depth
        w_g = p["concrete_kn_m3"] * bm.width * hang + q_g * trib
        w_q = q_q * trib
        beam_meta[bm.source_id] = {"trib_width_m": round(trib, 3), "w_g_kn_m": round(w_g, 3), "w_q_kn_m": round(w_q, 3)}
        for k, ((t1, n1, _), (t2, n2, _)) in enumerate(zip(pts, pts[1:])):
            if n1 == n2:
                continue
            members.append({"name": f"B:{bm.source_id}:{k}", "kind": "beam", "source_id": bm.source_id,
                            "i": n1, "j": n2, "b": bm.width, "h": bm.depth, "w_g": w_g, "w_q": w_q,
                            "span_m": round(t2 - t1, 3)})

    if not any(m["kind"] == "beam" for m in members) and not model.columns:
        raise AnalysisError("Nenhuma viga apoiada: verifique as ligações vigas/pilares/paredes na planta.")
    used = {m["i"] for m in members} | {m["j"] for m in members}
    nodes = {k: v for k, v in nodes.items() if k in used}           # nós de vigas excluídas
    supports = {k: v for k, v in supports.items() if k in used}
    return {"params": p, "height_m": H, "nodes": nodes, "supports": supports, "members": members,
            "beam_meta": beam_meta, "slab_loads": {"g_kn_m2": round(q_g, 3), "q_kn_m2": round(q_q, 3)},
            "warnings": warnings}


# ---------------------------------------------------------------- solver + verificações

def analyze(model: BuildingModel, loads: dict | None = None) -> dict:
    from Pynite import FEModel3D

    from engines.structuro_ec2 import design_section

    fr = build_frame(model, loads)
    p = fr["params"]
    E = _ecm(p["fck"])
    G = E / (2 * (1 + 0.2))
    fe = FEModel3D()
    # Eixos PyNite: Y vertical. (x, y, z)_BIM → (X, Y, Z) = (x, z, −y) — rotação própria.
    for key, (x, y, z) in fr["nodes"].items():
        fe.add_node(key, x, z, -y)
    for key, kind in fr["supports"].items():
        if kind == "fixed":
            fe.def_support(key, True, True, True, True, True, True)
        else:  # (x, y, z)_BIM → PyNite (X, Y, Z) = (x, z, −y): eixo x → RX, eixo y → RZ
            fe.def_support(key, True, True, True, kind == "pinned_x", False, kind == "pinned_z")
    fe.add_material("C", E, G, 0.2, p["concrete_kn_m3"])
    fe.add_material("C_lt", E / (1 + p["creep_phi"]), G / (1 + p["creep_phi"]), 0.2, p["concrete_kn_m3"])
    for m in fr["members"]:
        b, h = m["b"], m["h"]
        sec = f"S{b:.3f}x{h:.3f}"
        if sec not in fe.sections:
            a, c = max(b, h), min(b, h)
            J = a * c ** 3 * (1 / 3 - 0.21 * c / a * (1 - c ** 4 / (12 * a ** 4)))
            fe.add_section(sec, b * h, h * b ** 3 / 12, b * h ** 3 / 12, J)
        fe.add_member(m["name"], m["i"], m["j"], "C", sec)
        if m["kind"] == "column":
            fe.add_member_dist_load(m["name"], "FY", -m["w_g"], -m["w_g"], case="G")
        else:
            fe.add_member_dist_load(m["name"], "FY", -m["w_g"], -m["w_g"], case="G")
            if m["w_q"] > 0:
                fe.add_member_dist_load(m["name"], "FY", -m["w_q"], -m["w_q"], case="Q")
    fe.add_load_combo("ELU", {"G": p["gamma_g"], "Q": p["gamma_q"]})
    fe.add_load_combo("QP", {"G": 1.0, "Q": p["psi2"]})
    try:
        fe.analyze_linear(check_stability=True)
    except Exception as e:
        raise AnalysisError(f"Pórtico instável (verifique apoios e ligações): {e}") from e

    fcd = p["fck"] / 1.5
    lt = 1 + p["creep_phi"]
    key = (model.plan_id or "plan", model.page_index)
    beams: dict[str, dict] = {}
    columns = []
    for m in fr["members"]:
        mem = fe.members[m["name"]]
        if m["kind"] == "beam":
            L = mem.L()
            xs = [L * i / (SAMPLES - 1) for i in range(SAMPLES)]
            mz = [float(mem.moment("Mz", x, "ELU")) for x in xs]
            # Convenção PyNite (Y↑): Mz < 0 = momento positivo (fibra inferior tracionada).
            sag = max(0.0, -min(mz))
            hog = max(0.0, max(mz))
            v = float(max(abs(mem.max_shear("Fy", "ELU")), abs(mem.min_shear("Fy", "ELU"))))
            defl = float(max(abs(mem.rel_deflection("dy", x, "QP")) for x in xs)) * lt
            r = beams.setdefault(m["source_id"], {
                "guid": _guid(model, key, "IfcBeam", m["source_id"]), "source_id": m["source_id"],
                "b_m": m["b"], "h_m": m["h"], **fr["beam_meta"].get(m["source_id"], {}),
                "spans_m": [], "m_span_knm": 0.0, "m_support_knm": 0.0, "v_knm": 0.0,
                "deflection_mm": 0.0, "deflection_limit_mm": 0.0, "deflection_ratio": 0.0})
            r["spans_m"].append(round(float(L), 3))
            r["m_span_knm"] = max(r["m_span_knm"], sag)
            r["m_support_knm"] = max(r["m_support_knm"], hog)
            r["v_knm"] = max(r["v_knm"], v)
            lim = L / p["deflection_limit"]
            ratio = defl / lim if lim > 0 else 0.0
            if ratio >= r["deflection_ratio"]:
                r["deflection_mm"], r["deflection_limit_mm"], r["deflection_ratio"] = defl * 1000, lim * 1000, ratio
        else:
            n_ed = float(max(abs(mem.max_axial("ELU")), abs(mem.min_axial("ELU"))))
            col = {"guid": _guid(model, key, "IfcColumn", m["source_id"]), "source_id": m["source_id"],
                   "b_m": m["b"], "h_m": m["h"], "height_m": fr["height_m"]}
            col.update(check_column(n_ed, m["b"], m["h"], fr["height_m"], p))
            columns.append(col)

    out_beams = []
    for r in beams.values():
        d = r["h_m"] - p["cover_m"]
        med = max(r["m_span_knm"], r["m_support_knm"])
        des = design_section(med, r["v_knm"], b_m=r["b_m"], h_m=r["h_m"], d_m=d, fck=p["fck"], fyk=p["fyk"])
        span_des = design_section(r["m_span_knm"], 0.0, b_m=r["b_m"], h_m=r["h_m"], d_m=d, fck=p["fck"], fyk=p["fyk"])
        sup_des = design_section(r["m_support_knm"], 0.0, b_m=r["b_m"], h_m=r["h_m"], d_m=d, fck=p["fck"], fyk=p["fyk"])
        m_lim = des["flexure"]["mu_lim"] * r["b_m"] * d ** 2 * fcd * 1000
        parts = {"flexao": med / m_lim if m_lim else 0.0,
                 "esforco_transverso": r["v_knm"] / des["shear"]["vrdmax_kn"] if des["shear"]["vrdmax_kn"] else 0.0,
                 "flecha": r["deflection_ratio"]}
        util = max(parts.values())
        for k in ("m_span_knm", "m_support_knm", "v_knm", "deflection_mm", "deflection_limit_mm", "deflection_ratio"):
            r[k] = round(r[k], 3 if k == "deflection_ratio" else 2)
        r.update({"as_span_cm2": span_des["flexure"]["as_req_cm2"], "as_support_cm2": sup_des["flexure"]["as_req_cm2"],
                  "asw_s_cm2_m": des["shear"]["asw_s_req_cm2_m"],
                  "utilization": round(util, 3), "utilization_parts": {k: round(v, 3) for k, v in parts.items()},
                  "status": _status(util), "warnings": des["warnings"]})
        r["v_kn"] = r.pop("v_knm")
        out_beams.append(r)

    worst = max([b["utilization"] for b in out_beams] + [c["utilization"] for c in columns], default=0.0)
    return {"version": VERSION, "solver": "PyNite (MIT), análise elástica linear 3D",
            "scope": "Pré-dimensionamento para cargas verticais. Sem vento nem sismo; pilares só à compressão centrada.",
            "source": SOURCE, "params": p, "slab_loads": fr["slab_loads"],
            "combinations": {"ELU": f"{p['gamma_g']} G + {p['gamma_q']} Q", "ELS_QP": f"G + {p['psi2']} Q"},
            "counts": {"nodes": len(fr["nodes"]), "members": len(fr["members"]),
                       "beams": len(out_beams), "columns": len(columns)},
            "beams": sorted(out_beams, key=lambda b: -b["utilization"]),
            "columns": sorted(columns, key=lambda c: -c["utilization"]),
            "max_utilization": round(worst, 3), "status": _status(worst),
            "warnings": fr["warnings"], "execution_ready": False}


def check_column(n_ed: float, b: float, h: float, height: float, p: dict) -> dict:
    """Pilar à compressão centrada (EN 1992-1-1): armadura mínima §9.5.2, N_Rd, esbelteza assinalada acima de 25."""
    fcd, fyd = p["fck"] / 1.5, p["fyk"] / 1.15
    ac = b * h
    as_min = max(0.10 * n_ed / (fyd * 1000), 0.002 * ac)       # m²
    n_rd = (0.85 * ac * fcd + as_min * fyd) * 1000             # kN (fcd e fyd em MPa → kN/m² × 1000)
    lam = height / (min(b, h) / math.sqrt(12))
    util = n_ed / n_rd if n_rd > 0 else 0.0
    out = {"n_ed_kn": round(n_ed, 2), "n_rd_kn": round(n_rd, 1), "as_min_cm2": round(as_min * 1e4, 2),
           "slenderness": round(lam, 1), "utilization": round(util, 3), "status": _status(util), "warnings": []}
    if lam > 25:
        out["warnings"].append("Esbelteza > 25: verificar efeitos de 2.ª ordem (EN 1992-1-1 §5.8).")
    return out


def _guid(model: BuildingModel, key, ifc_class: str, source_id: str) -> str:
    """GlobalId do elemento: o do IFC importado, ou o GUID estável do IFC gerado pelo ConstruPilot."""
    return source_id if model.ifc_guids else stable_guid(*key, ifc_class, source_id)


def _status(u: float) -> str:
    return "ok" if u <= 0.85 else ("atencao" if u <= 1.0 else "insuficiente")
