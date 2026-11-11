"""Cutting plan of CLT pieces on press blanks (OR-Tools CP-SAT, Apache 2.0).

Pieces of the same build-up (thickness and layers) are placed on rectangular
blanks of the press format without overlap. Two engines run on every request:

* a deterministic shelf heuristic (first-fit decreasing), always available;
* the CP-SAT solver, which minimises the number of blanks and then the used
  length of the last blank, warm-started with the heuristic.

The result keeps the better of the two and reports the lower bound (total
piece area over blank area), so the distance to the optimum is visible.
Waste is measured from the layout, not assumed. The blank size, the saw kerf
and whether a piece may turn are company parameters.
"""
from __future__ import annotations

import math
from typing import Annotated

from pydantic import BaseModel, Field

from bim_studio.clt_walls import REZULT_FORMAT

MM = 1000  # integer millimetres inside the solver


class Piece(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    length_m: Annotated[float, Field(gt=0, le=100, allow_inf_nan=False)]
    width_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)]
    thickness_mm: Annotated[float, Field(gt=0, le=500, allow_inf_nan=False)]
    layers: Annotated[int, Field(ge=3, le=13)] = 5
    opening_area_m2: Annotated[float, Field(ge=0, le=10_000, allow_inf_nan=False)] = 0.0


class NestingInput(BaseModel):
    pieces: list[Piece] = Field(min_length=1, max_length=400)
    blank_length_m: Annotated[float, Field(gt=0, le=40)] = REZULT_FORMAT["max_length_m"]
    blank_width_m: Annotated[float, Field(gt=0, le=6)] = REZULT_FORMAT["max_width_m"]
    kerf_mm: Annotated[float, Field(ge=0, le=50)] = 10.0
    allow_rotation: bool = False
    variable_length: bool = True
    variable_width: bool = False
    time_limit_s: Annotated[float, Field(gt=0, le=60)] = 8.0


def _shelf(items, L, W):
    """First-fit decreasing on shelves. items: (key, ln, w, rotatable)."""
    blanks = []  # each: {"shelves": [[y, height, x_used]], "placed": []}
    for key, ln, w, rot in sorted(items, key=lambda i: (-max(i[1], i[2]) if i[3] else -i[2], -i[1], i[0])):
        options = [(ln, w)] + ([(w, ln)] if rot and ln != w else [])
        options = [(a, b) for a, b in options if a <= L and b <= W]
        if not options:
            raise ValueError(f"A peça {key} não cabe no formato da prensa.")
        done = False
        for blank in blanks:
            for shelf in blank["shelves"]:
                for a, b in options:
                    if b <= shelf[1] and shelf[2] + a <= L:
                        blank["placed"].append((key, shelf[2], shelf[0], a, b))
                        shelf[2] += a
                        done = True
                        break
                if done:
                    break
            if not done:
                top = sum(s[1] for s in blank["shelves"])
                for a, b in options:
                    if top + b <= W:
                        blank["shelves"].append([top, b, a])
                        blank["placed"].append((key, 0, top, a, b))
                        done = True
                        break
            if done:
                break
        if not done:
            a, b = options[0]
            blanks.append({"shelves": [[0, b, a]], "placed": [(key, 0, 0, a, b)]})
    return [b["placed"] for b in blanks]


def _cp_sat(items, L, W, upper, hint, time_limit):
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    nb = len(upper)
    used = [m.NewBoolVar(f"u{b}") for b in range(nb)]
    for b in range(nb - 1):
        m.Add(used[b] >= used[b + 1])
    x_iv = {b: [] for b in range(nb)}
    y_iv = {b: [] for b in range(nb)}
    vars_ = {}
    ends = {b: [] for b in range(nb)}
    for key, ln, w, rot in items:
        orient = [(ln, w)] + ([(w, ln)] if rot and ln != w else [])
        orient = [(a, c) for a, c in orient if a <= L and c <= W]
        lits = []
        for b in range(nb):
            for o, (a, c) in enumerate(orient):
                p = m.NewBoolVar(f"p_{key}_{b}_{o}")
                x = m.NewIntVar(0, L - a, "")
                y = m.NewIntVar(0, W - c, "")
                x_iv[b].append(m.NewOptionalFixedSizeIntervalVar(x, a, p, ""))
                y_iv[b].append(m.NewOptionalFixedSizeIntervalVar(y, c, p, ""))
                m.AddImplication(p, used[b])
                end = m.NewIntVar(0, L, "")
                m.Add(end == x + a).OnlyEnforceIf(p)
                m.Add(end == 0).OnlyEnforceIf(p.Not())
                ends[b].append(end)
                lits.append(p)
                vars_[(key, b, o)] = (p, x, y, a, c)
        m.AddExactlyOne(lits)
    span = []
    for b in range(nb):
        m.AddNoOverlap2D(x_iv[b], y_iv[b])
        s = m.NewIntVar(0, L, f"s{b}")
        m.AddMaxEquality(s, ends[b] or [0])
        span.append(s)
    # Blanks first; then the total used length (trimmed blanks).
    m.Minimize(sum(used) * (L * nb + 1) + sum(span))
    for (key, b, o), (p, x, y, a, c) in vars_.items():
        h = hint.get(key)
        if h:
            on = h[0] == b and h[3] == a and h[4] == c
            m.AddHint(p, on)
            if on:
                m.AddHint(x, h[1])
                m.AddHint(y, h[2])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 4
    solver.parameters.random_seed = 7
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, solver.StatusName(status)
    out = [[] for _ in range(nb)]
    for (key, b, o), (p, x, y, a, c) in vars_.items():
        if solver.Value(p):
            out[b].append((key, solver.Value(x), solver.Value(y), a, c))
    return [b for b in out if b], solver.StatusName(status)


def _group_plan(group, body):
    kerf = round(body.kerf_mm)
    L, W = round(body.blank_length_m * MM), round(body.blank_width_m * MM)
    # The kerf is added to each piece; a cut on the blank edge is trimmed anyway.
    items = [(p.id, round(p.length_m * MM) + kerf, round(p.width_m * MM) + kerf, body.allow_rotation) for p in group]
    for key, ln, w, rot in items:
        if not ((ln <= L + kerf and w <= W + kerf) or (rot and w <= L + kerf and ln <= W + kerf)):
            raise ValueError(f"A peça {key} excede o formato {body.blank_length_m} × {body.blank_width_m} m; divida-a primeiro.")
    L, W = L + kerf, W + kerf
    heuristic = _shelf(items, L, W)
    hint = {key: (b, x, y, a, c) for b, blank in enumerate(heuristic) for key, x, y, a, c in blank}
    area = sum(ln * w for _, ln, w, _ in items)
    lower = math.ceil(area / (L * W) - 1e-9)
    best, engine, status = heuristic, "heurística de prateleiras", "heurística"
    if len(items) <= 120:
        solved, status = _cp_sat(items, L, W, heuristic, hint, body.time_limit_s)
        if solved is not None and _score(solved, L) <= _score(heuristic, L):
            best, engine = solved, "OR-Tools CP-SAT"
    return best, {"motor": engine, "estado_solver": status, "limite_inferior_paineis": lower,
                  "heuristica_paineis": len(heuristic), "otimo_provado": status == "OPTIMAL"}, (L, W)


def _score(blanks, L):
    return (len(blanks), sum(max(x + a for _, x, _, a, _ in b) for b in blanks))


def plan(body: NestingInput):
    groups = {}
    for p in body.pieces:
        groups.setdefault((p.thickness_mm, p.layers), []).append(p)
    if len({p.id for p in body.pieces}) != len(body.pieces):
        raise ValueError("Cada peça precisa de um identificador único.")
    by_id = {p.id: p for p in body.pieces}
    kerf = body.kerf_mm / MM
    result_groups, totals = [], {"paineis": 0, "volume_pecas_m3": 0.0, "volume_vaos_m3": 0.0,
                                 "volume_paineis_m3": 0.0, "volume_desperdicio_m3": 0.0}
    for (t, n), group in sorted(groups.items()):
        blanks, info, (L, W) = _group_plan(group, body)
        layout = []
        for i, blank in enumerate(blanks, 1):
            used_len = max(x + a for _, x, _, a, _ in blank) / MM - kerf if body.variable_length else body.blank_length_m
            used_len = min(max(used_len, 0), body.blank_length_m)
            placed = []
            for key, x, y, a, c in sorted(blank, key=lambda r: (r[2], r[1])):
                p = by_id[key]
                turned = round(p.length_m * MM) + round(body.kerf_mm) != a
                placed.append({"id": key, "x_m": x / MM, "y_m": y / MM, "comprimento_m": p.width_m if turned else p.length_m,
                               "largura_m": p.length_m if turned else p.width_m, "rodada": turned})
            used_w = (max(y + c for _, _, y, _, c in blank) / MM - kerf) if body.variable_width else body.blank_width_m
            used_w = min(max(used_w, 0), body.blank_width_m)
            blank_area = used_len * used_w
            piece_area = sum(by_id[k].length_m * by_id[k].width_m for k, *_ in blank)
            layout.append({"painel": i, "comprimento_usado_m": round(used_len, 4), "largura_m": round(used_w, 4),
                           "pecas": placed, "aproveitamento_percent": round(piece_area / blank_area * 100, 2) if blank_area else 0})
        pieces_v = sum(p.length_m * p.width_m for p in group) * t / MM
        openings_v = sum(p.opening_area_m2 for p in group) * t / MM
        blanks_v = sum(b["comprimento_usado_m"] * b["largura_m"] for b in layout) * t / MM
        result_groups.append({
            "espessura_mm": t, "camadas": n, **info, "paineis": len(layout), "layout": layout,
            "volume_pecas_m3": round(pieces_v, 4), "volume_vaos_m3": round(openings_v, 4),
            "volume_paineis_m3": round(blanks_v, 4),
            "desperdicio_m3": round(blanks_v - pieces_v + openings_v, 4),
            "desperdicio_percent": round((blanks_v - pieces_v + openings_v) / blanks_v * 100, 2) if blanks_v else 0,
        })
        totals["paineis"] += len(layout)
        totals["volume_pecas_m3"] += pieces_v
        totals["volume_vaos_m3"] += openings_v
        totals["volume_paineis_m3"] += blanks_v
        totals["volume_desperdicio_m3"] += blanks_v - pieces_v + openings_v
    net = totals["volume_pecas_m3"] - totals["volume_vaos_m3"]
    totals = {k: round(v, 4) if isinstance(v, float) else v for k, v in totals.items()}
    totals["volume_liquido_m3"] = round(net, 4)
    totals["fator_paineis_sobre_liquido"] = round(totals["volume_paineis_m3"] / net, 4) if net > 0 else None
    totals["desperdicio_percent"] = (round(totals["volume_desperdicio_m3"] / totals["volume_paineis_m3"] * 100, 2)
                                     if totals["volume_paineis_m3"] else 0)
    return {"grupos": result_groups, "total": totals,
            "parametros": {"painel_m": [body.blank_length_m, body.blank_width_m], "corte_mm": body.kerf_mm,
                           "rotacao": body.allow_rotation, "comprimento_variavel": body.variable_length,
                           "largura_variavel": body.variable_width,
                           "origem_formato": REZULT_FORMAT["source"] if (body.blank_length_m, body.blank_width_m) == (
                               REZULT_FORMAT["max_length_m"], REZULT_FORMAT["max_width_m"]) else "empresa",
                           "origem_corte": "hipótese editável (largura de serra/fresa)"}}


def pieces_from_walls(analysis):
    """Nesting pieces from clt_walls.analyse(): wall length along the blank, height across."""
    return [Piece(id=p["id"], length_m=p["comprimento_m"], width_m=p["altura_m"], thickness_mm=p["espessura_mm"],
                  layers=p["camadas"], opening_area_m2=p["area_vaos_m2"]) for p in analysis["pecas"]]
