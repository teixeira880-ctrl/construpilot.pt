"""Motor de construção tradicional (estrutura porticada de betão armado + alvenarias) — determinístico, sem IA.

Entrada: a MESMA geometria que os motores LSF e CLT (perímetros por piso, paredes interiores, vãos, zonas de laje, cobertura),
lida da planta real. Saída, elemento a elemento e numerado:
  • lajes maciças dimensionadas (NP EN 1992-1-1, método dos coeficientes) → betão, cofragem, aço pelas malhas calculadas;
  • pilares nos cantos, nas ligações e a ≤ vaoMaxPilares ao longo das paredes resistentes (fora dos vãos), dimensionados com as
    cargas descidas piso a piso → betão, cofragem, varões e estribos calculados;
  • vigas sobre as paredes resistentes, vão a vão entre pilares, com as cargas reais da laje (distribuição trapezoidal / triangular)
    e da alvenaria por cima → secção, varões e estribos calculados;
  • sapatas isoladas (NP EN 1997-1, tensão admissível) e vigas de fundação → betão, aço, escavação, betão de limpeza;
  • alvenarias contadas fiada a fiada (unidades inteiras por troço, fora de pilares, vigas e vãos), argamassa, vergas;
  • pavimento térreo, ETICS por plano de corte, rebocos, cobertura (lajes inclinadas, empenas, telhas contadas fiada a fiada).
Nenhuma quantidade vem de um rácio: tudo é medido na geometria ou sai do dimensionamento de cada elemento.
"""
from __future__ import annotations

import copy
import math

from shapely.geometry import LineString, Point, Polygon

from engines.calc_lots import structure as ST
from engines.lsf.geom import EPS, plano_corte, r1, subtract_rects

KG_M = ST.KG_M
KG_M[6] = round(math.pi * 0.006 ** 2 / 4 * 7850, 3)


class Ctx:
    def __init__(self, proj):
        self.proj = proj
        self.R = proj["regras"]
        self.paredes, self.lajes, self.pilares, self.vigas, self.sapatas, self.vfund, self.vergas = [], [], [], [], [], [], []
        self.coberturas, self.itens, self.extras, self.avisos = [], [], [], []
        self.grupo_topo, self.grupo_base, self.perim_topo = {}, {}, {}
        self.niveis: list[dict] = []


def _aviso(ctx, m):
    if m not in ctx.avisos:
        ctx.avisos.append(m)


def _resolve_z(ctx, z):
    if isinstance(z, (int, float)):
        return float(z)
    if isinstance(z, str) and z.startswith("auto:"):
        k = z[5:]
        if k in ctx.grupo_topo:
            return ctx.grupo_topo[k]
        if k in ctx.perim_topo:
            return ctx.perim_topo[k]
    raise ValueError(f"Cota inválida: {z}")


def _ok(r):
    return all(c.get("ok") is not False for c in r.get("controles") or [])


def _item(ctx, **k):
    ctx.itens.append(k)


# ---------------------------------------------------------------------------------------------------------------- lajes
def _laje_kg(det, lx, ly, area):
    """Aço de uma laje pelas malhas calculadas: vãos (nas duas direções, toda a área) + armaduras de apoio (comprimento calculado)."""
    kg = 0.0
    for v in det["span"].values():
        a = v["mesh"].get("as_cm2_m") or v["as_req_cm2_m"]
        kg += a * 1e-4 * 7850 * area
    for k, v in det["supports"].items():
        if v["type"] == "libre":
            continue
        a = v["mesh"].get("as_cm2_m") or v["as_req_cm2_m"]
        lado = ly if k in ("x0", "x1") else lx
        kg += a * 1e-4 * 7850 * v["length_from_face_m"] * lado
    return kg


def _prep_lajes(ctx):
    R = ctx.R
    grupos = {}
    for f in ctx.proj.get("pisos") or []:
        f = dict(f)
        f["lx"], f["ly"] = (f["x1"] - f["x0"]) / 1000, (f["y1"] - f["y0"]) / 1000
        grupos.setdefault(f.get("grupo", f["id"]), []).append(f)
        ctx.lajes.append(f)
    for g, fs in grupos.items():
        cob = any(f.get("cobertura") for f in fs)
        g2, q = (R["g2_cob"], R["q_cob"]) if cob else (R["g2_piso"], R["q_piso"])
        h = float(max([f.get("h") or 0 for f in fs] + [0]))
        if not h:
            lmin = max(min(f["lx"], f["ly"]) for f in fs)
            h = max(R["lajeHmin"], math.ceil(lmin * 1000 / 30 / 10) * 10 + 20)
        while True:
            res = [ST.dalle_ba({"lx_m": f["lx"], "ly_m": f["ly"], "h_m": h / 1000, "g2_kn_m2": g2, "q_kn_m2": q, "fck": R["fck"]}) for f in fs]
            if all(_ok(r) for r in res) or h >= R["lajeHmax"]:
                break
            h += 10
        if not all(_ok(r) for r in res):
            _aviso(ctx, f"{g}: laje maciça com {h:.0f} mm não verifica todos os critérios — prever apoio intermédio ou laje nervurada.")
        for f, r in zip(fs, res):
            f.update(h=h, g2=g2, q=q, cobertura=cob, calc=r, kg=_laje_kg(r["details"], f["lx"], f["ly"], f["lx"] * f["ly"]),
                     m3=f["lx"] * f["ly"] * h / 1000, cofragem=f["lx"] * f["ly"], seccao=r["section"])
        ctx.grupo_base[g] = min(f["z"] for f in fs)
        ctx.grupo_topo[g] = max(f["z"] for f in fs) + h


# --------------------------------------------------------------------------------------------------------------- paredes
def _tipo(ctx, k):
    T = ctx.proj["tiposParede"][k]
    U = ctx.proj["unidades"][T["unidade"]]
    return {"T": T, "U": U, "D": U["t"], "k": k}


def _vaos_do_lado(vaos, i):
    if not vaos:
        return []
    if isinstance(vaos, list):
        return vaos[i] if i < len(vaos) and isinstance(vaos[i], list) else []
    return vaos.get(i) or vaos.get(str(i)) or []


def _perimetro(ctx, per):
    pts = per["pontos"]
    n = len(pts)
    z0 = _resolve_z(ctx, per.get("z0", 0))
    tp = _tipo(ctx, per["tipo"])
    dirs = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        dirs.append(((b[0] - a[0]) / L, (b[1] - a[1]) / L, L))

    def convexo(i):
        d0, d1 = dirs[(i - 1) % n], dirs[i]
        return d0[0] * d1[1] - d0[1] * d1[0] > 0

    for i in range(n):
        dx, dy, ln = dirs[i]
        eC = convexo((i + 1) % n)
        ctx.paredes.append({"id": f"{per['id']}-{i + 1}", "tipo": per["tipo"], "tp": tp, "A": list(pts[i]), "d": [dx, dy, 0], "n": [-dy, dx, 0],
                            "y0": 0.0, "L": ln - tp["D"] if eC else ln + tp["D"], "z0": z0, "H": float(per["altura"]),
                            "vaos": [dict(v) for v in _vaos_do_lado(per.get("vaos"), i)], "perimetro": {"id": per["id"], "lado": ln},
                            "nivel": per.get("nivel", per["id"]), "resistente": True})
    ctx.perim_topo[per["id"]] = z0 + float(per["altura"])


def _avulsa(ctx, w):
    tp = _tipo(ctx, w["tipo"])
    z0 = _resolve_z(ctx, w.get("z0", 0))
    H = float(w.get("H", w.get("altura")))
    ax, bx = w["a"], w["b"]
    ln = math.hypot(bx[0] - ax[0], bx[1] - ax[1])
    d = [(bx[0] - ax[0]) / ln, (bx[1] - ax[1]) / ln, 0]
    n = [-d[1], d[0], 0]
    y0 = 0.0 if w.get("alinhamento") == "face" else -tp["D"] / 2
    ts, te = 0.0, ln
    for which, Pp, Q in (("ini", ax, bx), ("fim", bx, ax)):
        for h in ctx.paredes:
            if h["z0"] + h["H"] <= z0 + EPS or h["z0"] >= z0 + H - EPS:
                continue
            rel = (Pp[0] - h["A"][0], Pp[1] - h["A"][1])
            px = rel[0] * h["d"][0] + rel[1] * h["d"][1]
            py = rel[0] * h["n"][0] + rel[1] * h["n"][1]
            Dh = h["tp"]["D"]
            if px < -1 or px > h["L"] + 1 or py < h["y0"] - 1 or py > h["y0"] + Dh + 1:
                continue
            qy = (Q[0] - h["A"][0]) * h["n"][0] + (Q[1] - h["A"][1]) * h["n"][1]
            yT = h["y0"] + Dh if qy > h["y0"] + Dh / 2 else h["y0"]
            dn = d[0] * h["n"][0] + d[1] * h["n"][1]
            if abs(dn) < 1e-6:
                continue
            aY = (ax[0] - h["A"][0]) * h["n"][0] + (ax[1] - h["A"][1]) * h["n"][1]
            t = (yT - aY) / dn
            if which == "ini":
                ts = t
            else:
                te = t
            break
    ctx.paredes.append({"id": w["id"], "tipo": w["tipo"], "tp": tp, "A": [ax[0] + d[0] * ts, ax[1] + d[1] * ts], "d": d, "n": n, "y0": y0,
                        "L": te - ts, "z0": z0, "H": H, "vaos": [{**v, "x": v["x"] - ts} for v in (w.get("vaos") or [])], "perimetro": None,
                        "nivel": w.get("nivel"), "resistente": bool(w.get("resistente")), "eixo_ini": [ax, bx]})


def _eixo(w):
    yc = w["y0"] + w["tp"]["D"] / 2
    a = (w["A"][0] + w["n"][0] * yc, w["A"][1] + w["n"][1] * yc)
    return a, (a[0] + w["d"][0] * w["L"], a[1] + w["d"][1] * w["L"])


def _aberturas(ctx, w):
    ab = []
    for v in w["vaos"]:
        z0 = 0.0 if v.get("tipo") == "porta" else float(v.get("peitoril", 0))
        x0 = max(float(v["x"]), 0.0)
        x1 = min(float(v["x"]) + float(v["largura"]), w["L"])
        if x1 - x0 < 100:
            _aviso(ctx, f"{w['id']}: vão {v.get('id')} fora da parede — ignorado.")
            continue
        ab.append({"id": v.get("id"), "tipo": v.get("tipo", "janela"), "x0": x0, "x1": x1, "z0": z0, "z1": z0 + float(v["altura"])})
    w["aberturas"] = ab


# ----------------------------------------------------------------------------------------------------- paredes resistentes
def _resistentes(ctx):
    """Paredes interiores que suportam lajes: o eixo coincide com o bordo de uma zona de laje logo acima."""
    for w in ctx.paredes:
        if w["resistente"]:
            continue
        top = w["z0"] + w["H"]
        a, b = _eixo(w)
        ln = LineString([a, b])
        for f in ctx.lajes:
            if abs(f["z"] - top) > 5:
                continue
            for e in (((f["x0"], f["y0"]), (f["x1"], f["y0"])), ((f["x1"], f["y0"]), (f["x1"], f["y1"])), ((f["x1"], f["y1"]), (f["x0"], f["y1"])),
                      ((f["x0"], f["y1"]), (f["x0"], f["y0"]))):
                el = LineString(e)
                if ln.buffer(w["tp"]["D"] / 2 + 5).intersection(el).length > 0.5 * min(ln.length, el.length):
                    w["resistente"] = True
                    break
            if w["resistente"]:
                break


# ------------------------------------------------------------------------------------------------------------ pilares
def _pilares(ctx):
    R = ctx.R
    pontos = []                                    # (x, y, dir) — centros de pilar

    def add(p, d):
        for q in pontos:
            if math.hypot(q[0] - p[0], q[1] - p[1]) < 150:
                return
        pontos.append((p[0], p[1], d))

    res = [w for w in ctx.paredes if w["resistente"]]
    for w in res:
        a, b = _eixo(w)
        if w.get("perimetro"):
            add(a, w["d"])
        for h in res:
            if h is w or abs(h["z0"] - w["z0"]) > 5:
                continue
            ia = LineString(_eixo(h)).intersection(LineString([(a[0] - w["d"][0] * 400, a[1] - w["d"][1] * 400), (b[0] + w["d"][0] * 400, b[1] + w["d"][1] * 400)]))
            if ia.geom_type == "Point" and LineString(_eixo(h)).distance(ia) < 1 and LineString([a, b]).buffer(h["tp"]["D"]).contains(ia):
                add((ia.x, ia.y), w["d"])
        if not w.get("perimetro"):
            add(a, w["d"])
            add(b, w["d"])
    # intermédios ao longo de cada parede resistente (fora dos vãos)
    for w in res:
        a, b = _eixo(w)
        ln = LineString([a, b])
        ts = sorted({0.0, w["L"], *[ln.project(Point(p[0], p[1])) for p in pontos if ln.distance(Point(p[0], p[1])) < w["tp"]["D"]]})
        proib = [(ab["x0"] - R["pilarH"] / 2 - 50, ab["x1"] + R["pilarH"] / 2 + 50) for ab in w["aberturas"]]
        for t0, t1 in zip(ts[:-1], ts[1:]):
            gap = t1 - t0
            if gap <= R["vaoMaxPilares"] + EPS:
                continue
            nn = math.ceil(gap / R["vaoMaxPilares"] - 1e-9)
            for k in range(1, nn):
                x = t0 + gap * k / nn
                for lo, hi in proib:
                    if lo < x < hi:
                        x = lo if (x - lo) < (hi - x) and lo - t0 > 600 else hi
                if not (t0 + 300 < x < t1 - 300) or any(lo < x < hi for lo, hi in proib):
                    _aviso(ctx, f"{w['id']}: pilar intermédio impossível fora dos vãos — viga com vão {gap / 1000:.2f} m.")
                    continue
                add((a[0] + w["d"][0] * x, a[1] + w["d"][1] * x), w["d"])
    zs = sorted({round(w["z0"]) for w in ctx.paredes})
    for i, (x, y, d) in enumerate(pontos, 1):
        pid = f"P{i}"
        for z in zs:
            ws = [w for w in res if round(w["z0"]) == z and LineString(_eixo(w)).distance(Point(x, y)) < w["tp"]["D"]]
            if not ws:
                continue
            w = ws[0]
            ctx.pilares.append({"id": f"{pid}-{w.get('nivel') or z}", "pilar": pid, "x": x, "y": y, "d": list(w["d"][:2]), "z0": w["z0"], "H": w["H"],
                                "nivel": w.get("nivel"), "b": R["pilarB"], "h": R["pilarH"], "paredes": [x_["id"] for x_ in ws], "G": 0.0, "Q": 0.0})


# --------------------------------------------------------------------------------------------------------------- vigas
def _carga_laje(ctx, a, b, z_top, D):
    """Carga característica (g, q em kN/m) das lajes que apoiam na linha a-b à cota z_top (distribuição trapezoidal / triangular)."""
    g = q = 0.0
    ln = LineString([a, b])
    for f in ctx.lajes:
        if abs(f["z"] - z_top) > 5:
            continue
        lx, ly = min(f["lx"], f["ly"]), max(f["lx"], f["ly"])
        bordos = [(((f["x0"], f["y0"]), (f["x1"], f["y0"])), (f["x1"] - f["x0"]) / 1000), (((f["x0"], f["y1"]), (f["x1"], f["y1"])), (f["x1"] - f["x0"]) / 1000),
                  (((f["x0"], f["y0"]), (f["x0"], f["y1"])), (f["y1"] - f["y0"]) / 1000), (((f["x1"], f["y0"]), (f["x1"], f["y1"])), (f["y1"] - f["y0"]) / 1000)]
        for e, comp in bordos:
            if ln.buffer(D / 2 + 5).intersection(LineString(e)).length < 0.3 * min(ln.length, comp * 1000):
                continue
            larg = lx / 4 * (2 - lx / ly) if abs(comp - ly) < 1e-6 and ly > lx + 1e-6 else lx / 4    # bordo maior: trapézio; menor: triângulo
            g += (25 * f["h"] / 1000 + f["g2"]) * larg
            q += f["q"] * larg
    return g, q


def _vigas(ctx):
    R = ctx.R
    for w in ctx.paredes:
        if not w["resistente"]:
            continue
        a, b = _eixo(w)
        ln = LineString([a, b])
        top = w["z0"] + w["H"]
        tol = max(w["tp"]["D"], R["pilarH"]) + 50
        ps = sorted((p for p in ctx.pilares if abs(p["z0"] - w["z0"]) < 5 and ln.distance(Point(p["x"], p["y"])) < tol),
                    key=lambda p: ln.project(Point(p["x"], p["y"])))
        g_l, q_l = _carga_laje(ctx, a, b, top, w["tp"]["D"])
        # alvenaria do piso de cima sobre esta linha
        g_alv = 0.0
        for u in ctx.paredes:
            if abs(u["z0"] - top) < 400 and u is not w and LineString(_eixo(u)).buffer(w["tp"]["D"]).intersection(ln).length > 0.5 * u["L"]:
                g_alv = max(g_alv, R["gamaAlvenaria"] * u["tp"]["D"] / 1000 * u["H"] / 1000)
        if g_l == 0 and q_l == 0 and g_alv == 0:
            g_l = 0.0                                            # coroamento (cobertura inclinada): carga da cobertura somada em _cobertura
        w["vigas"] = []
        xs = [ln.project(Point(p["x"], p["y"])) for p in ps]
        if len(xs) < 2:
            xs = [0.0, w["L"]]
            ps = [None, None]
        n_sp = len(xs) - 1
        for i in range(n_sp):
            Lm = (xs[i + 1] - xs[i]) / 1000
            if Lm < 0.3:
                continue
            ap = "isostatique" if n_sp == 1 else ("continue_rive" if i in (0, n_sp - 1) else "continue_interieure")
            b_ = max(R["vigaB"], w["tp"]["D"]) / 1000
            h = max(R["vigaHmin"], math.ceil(Lm * 1000 / 12 / 50) * 50) / 1000
            while True:
                r = ST.poutre_ba({"portee_m": Lm, "b_m": b_, "h_m": h, "g_kn_m": g_l + g_alv, "q_kn_m": q_l, "appuis": ap, "fck": R["fck"]})
                if _ok(r) or h >= 0.8:
                    break
                h = round(h + 0.05, 2)
            if not _ok(r):
                _aviso(ctx, f"{w['id']}: viga de {Lm:.2f} m não verifica com {b_ * 100:.0f}×{h * 100:.0f} cm — secção a rever.")
            vid = f"V{len(ctx.vigas) + 1}"
            v = {"id": vid, "parede": w["id"], "nivel": w.get("nivel"), "L": Lm * 1000, "b": b_ * 1000, "h": h * 1000, "x0": xs[i], "x1": xs[i + 1],
                 "z1": top, "g": g_l + g_alv, "q": q_l, "apoios": ap, "calc": r, "seccao": r["section"], "armadura": r["barres"]["label"],
                 "estribos": r["etriers"], "kg": r["quantites"]["acier_kg"], "m3": r["quantites"]["beton_m3"], "cofragem": (b_ + 2 * h) * Lm,
                 "o": [a[0] + w["d"][0] * xs[i] - w["n"][0] * b_ * 500, a[1] + w["d"][1] * xs[i] - w["n"][1] * b_ * 500, top - h * 1000],
                 "eixo": list(w["d"][:2]) + [0], "lado": list(w["n"][:2]) + [0]}
            v["pilares"] = [p["id"] for p in (ps[i], ps[i + 1]) if p is not None]
            ctx.vigas.append(v)
            w["vigas"].append(v)


def _dim_pilares(ctx):
    R = ctx.R
    pid_ = {p["id"]: p for p in ctx.pilares}
    for v in ctx.vigas:                                       # reações das vigas (cargas finais, cobertura incluída)
        for k in v.get("pilares") or []:
            p = pid_[k]
            p["G"] += (v["g"] + 25 * v["b"] * v["h"] / 1e6) * v["L"] / 1000 / 2
            p["Q"] += v["q"] * v["L"] / 1000 / 2
    por = {}
    for p in ctx.pilares:
        por.setdefault(p["pilar"], []).append(p)
    for pid, lst in por.items():
        lst.sort(key=lambda p: -p["z0"])
        G = Q = 0.0
        for p in lst:
            G += p["G"] + 25 * p["b"] * p["h"] / 1e6 * p["H"] / 1000
            Q += p["Q"]
            b, h = p["b"] / 1000, p["h"] / 1000
            while True:
                r = ST.poteau_ba({"b_m": b, "h_m": h, "hauteur_m": p["H"] / 1000, "g_kn": G, "q_kn": Q, "fck": R["fck"]})
                if _ok(r) or h >= 0.6:
                    break
                h = round(h + 0.05, 2)
            if not _ok(r):
                _aviso(ctx, f"{p['id']}: pilar não verifica com {b * 100:.0f}×{h * 100:.0f} cm — secção a rever.")
            p.update(Ntot_G=G, Ntot_Q=Q, h=h * 1000, calc=r, seccao=r["section"], armadura=(r.get("barres") or {}).get("label", "—"),
                     estribos=r.get("etriers", "—"), kg=r["quantites"].get("acier_kg", 0.0), m3=b * h * p["H"] / 1000, cofragem=2 * (b + h) * p["H"] / 1000)
        base = lst[-1]
        ctx.sapatas.append({"pilar": pid, "x": base["x"], "y": base["y"], "z": base["z0"], "G": G, "Q": Q, "b_pilar": base["b"], "h_pilar": base["h"],
                            "d": base["d"]})


# ---------------------------------------------------------------------------------------------------------- fundações
def _fundacoes(ctx):
    R = ctx.R
    qa = R["q_adm_kpa"]
    D = R["profundidadeFundacao"] / 1000
    for i, s in enumerate(ctx.sapatas, 1):
        B = max(R["sapataBmin"] / 1000, math.ceil(math.sqrt((s["G"] + s["Q"]) / qa) / 0.05) * 0.05)
        while True:
            h = max(R["sapataHmin"] / 1000, math.ceil(((B - s["h_pilar"] / 1000) / 4 + 0.05) / 0.05) * 0.05)
            r = ST.semelle({"b_m": B, "l_m": B, "h_m": h, "profondeur_m": D, "g_kn": s["G"], "q_kn": s["Q"], "q_adm_els_kpa": qa,
                            "largeur_mur_m": s["b_pilar"] / 1000})
            if _ok(r) or B >= 4:
                break
            B = round(B + 0.05, 2)
        ned = r["sollicitations"]["ned"]
        d = h - 0.05
        As = ned * (B - s["b_pilar"] / 1000) / (8 * d * 500 / 1.15) * 10                  # cm² por direção (bielas)
        n = max(math.ceil(As / 1.131 - 1e-9), math.ceil((B - 0.1) / 0.20) + 1)        # Ø12 (1,131 cm²), espaçamento ≤ 20 cm
        comp = B - 0.10 + 2 * (h - 0.10)                                              # varão com dobras verticais
        kg = 2 * n * comp * KG_M[12]
        s.update(id=f"S{i}", B=B * 1000, hs=h * 1000, calc=r, seccao=r["section"], armadura=f"{n} Ø12 por direção (As ≥ {As:.2f} cm²)", kg=kg,
                 m3=B * B * h, cofragem=4 * B * h, limpeza=B * B * R["limpeza"] / 1000,
                 escavacao=(B + 2 * R["folgaEscavacao"] / 1000) ** 2 * (D + R["limpeza"] / 1000))
        _item(ctx, id=s["id"], tipo="sapata", grupo="fundacoes", o=[s["x"] - B * 500, s["y"] - B * 500, s["z"] - D * 1000], u=[1, 0, 0], v=[0, 1, 0], w=[0, 0, 1],
              contorno=[[0, 0], [B * 1000, 0], [B * 1000, B * 1000], [0, B * 1000]], esp=h * 1000, info=s["seccao"])
    # vigas de fundação sob as paredes resistentes do piso mais baixo, entre sapatas
    zmin = min((w["z0"] for w in ctx.paredes), default=0)
    for w in ctx.paredes:
        if not w["resistente"] or w["z0"] > zmin + 5:
            continue
        a, b = _eixo(w)
        ln = LineString([a, b])
        ss = sorted((s for s in ctx.sapatas if ln.distance(Point(s["x"], s["y"])) < w["tp"]["D"]), key=lambda s: ln.project(Point(s["x"], s["y"])))
        for s0, s1 in zip(ss[:-1], ss[1:]):
            x0 = ln.project(Point(s0["x"], s0["y"])) + s0["B"] / 2
            x1 = ln.project(Point(s1["x"], s1["y"])) - s1["B"] / 2
            Lm = (x1 - x0) / 1000
            if Lm < 0.2:
                continue
            bf, hf = R["vigaFundB"] / 1000, R["vigaFundH"] / 1000
            g = R["gamaAlvenaria"] * w["tp"]["D"] / 1000 * w["H"] / 1000
            r = ST.poutre_ba({"portee_m": Lm, "b_m": bf, "h_m": hf, "g_kn_m": g, "q_kn_m": 0, "appuis": "continue_rive", "fck": R["fck"]})
            vid = f"VF{len(ctx.vfund) + 1}"
            ctx.vfund.append({"id": vid, "parede": w["id"], "L": Lm * 1000, "b": bf * 1000, "h": hf * 1000, "calc": r, "seccao": r["section"],
                              "armadura": r["barres"]["label"], "estribos": r["etriers"], "kg": r["quantites"]["acier_kg"], "m3": bf * hf * Lm,
                              "cofragem": 2 * hf * Lm, "escavacao": (bf + 0.4) * (hf + R["limpeza"] / 1000) * Lm, "limpeza": bf * Lm * R["limpeza"] / 1000})
            _item(ctx, id=vid, tipo="viga_fundacao", grupo="fundacoes", o=[a[0] + w["d"][0] * x0 - w["n"][0] * bf * 500, a[1] + w["d"][1] * x0 - w["n"][1] * bf * 500,
                                                                          zmin - hf * 1000], u=list(w["d"]), v=list(w["n"]), w=[0, 0, 1],
                  contorno=[[0, 0], [Lm * 1000, 0], [Lm * 1000, bf * 1000], [0, bf * 1000]], esp=hf * 1000, info=r["section"])


# ---------------------------------------------------------------------------------------------------------- alvenarias
def _contar(segs_por_fiada, U):
    """Unidades inteiras por fiada e troço (cada troço começa por uma unidade inteira; a última é cortada)."""
    mod = U["l"] + U["junta"]
    return sum(math.ceil((s1 - s0 + U["junta"]) / mod - 1e-9) for segs in segs_por_fiada for s0, s1 in segs if s1 - s0 > 20)


def _alvenaria(ctx, w):
    R = ctx.R
    U = w["tp"]["U"]
    Halv = w["H"]                                 # a alvenaria sobe até à face inferior da viga de cada troço (ou da laje)
    vigas_b = [(v["x0"], v["x1"], w["H"] - v["h"], w["H"]) for v in w.get("vigas") or []]
    a, b = _eixo(w)
    ln = LineString([a, b])
    pil = []
    for p in ctx.pilares:
        if abs(p["z0"] - w["z0"]) < 5 and ln.distance(Point(p["x"], p["y"])) < w["tp"]["D"]:
            x = ln.project(Point(p["x"], p["y"]))
            par = abs(p["d"][0] * w["d"][0] + p["d"][1] * w["d"][1]) > 0.7
            meio = (p["h"] if par else p["b"]) / 2
            pil.append((max(0.0, x - meio), min(w["L"], x + meio)))
    w["pilaresX"] = pil
    # vergas
    def topo(x):
        return min([zb for x0, x1, zb, _ in vigas_b if x0 - 1 <= x <= x1 + 1] + [Halv])

    for ab in w["aberturas"]:
        if min(topo(ab["x0"]), topo(ab["x1"])) - ab["z1"] >= R["vergaH"] + 50:
            Lv = (ab["x1"] - ab["x0"] + 2 * R["vergaApoio"]) / 1000
            bt, hv_ = w["tp"]["D"] / 1000, R["vergaH"] / 1000
            nst = math.ceil(Lv / 0.15) + 1
            kg = 2 * (Lv + 0.2) * KG_M[10] + 2 * (Lv + 0.2) * KG_M[8] + nst * (2 * (bt + hv_) - 0.16 + 0.1) * KG_M[6]
            vg = {"id": f"VG-{w['id']}-{ab['id']}", "parede": w["id"], "vao": ab["id"], "L": Lv * 1000, "b": bt * 1000, "h": R["vergaH"],
                  "armadura": f"2 Ø10 + 2 Ø8, estribos Ø6 // 0,15 ({nst})", "kg": kg, "m3": bt * hv_ * Lv, "cofragem": (bt + 2 * hv_) * Lv,
                  "x0": ab["x0"] - R["vergaApoio"], "z0": ab["z1"]}
            ctx.vergas.append(vg)
            ab["verga"] = vg["id"]
    blocos = [(x0, x1, 0, Halv) for x0, x1 in pil] + vigas_b + [(ab["x0"], ab["x1"], ab["z0"], ab["z1"]) for ab in w["aberturas"]] + \
             [(vg["x0"], vg["x0"] + vg["L"], vg["z0"], vg["z0"] + vg["h"]) for vg in ctx.vergas if vg["parede"] == w["id"]]
    mod_h = U["h"] + U["junta"]
    fiadas = math.ceil(Halv / mod_h - 1e-9)
    segs_f = []
    for k in range(fiadas):
        z0, z1 = k * mod_h, min((k + 1) * mod_h, Halv)
        # um troço da fiada é interrompido onde um vão / pilar / viga ocupa ≥ metade da altura da fiada (senão: unidades cortadas)
        cortes = sorted((max(0.0, x0), min(w["L"], x1)) for x0, x1, bz0, bz1 in blocos if min(bz1, z1) - max(bz0, z0) >= (z1 - z0) / 2)
        segs, cur = [], 0.0
        for x0, x1 in cortes:
            if x0 > cur:
                segs.append((cur, x0))
            cur = max(cur, x1)
        if cur < w["L"]:
            segs.append((cur, w["L"]))
        segs_f.append(segs)
    n_un = _contar(segs_f, U)
    area_bruta = w["L"] * Halv / 1e6
    area_furos = sum(max(0, min(x1, w["L"]) - max(x0, 0)) * max(0, min(bz1, Halv) - max(bz0, 0)) for x0, x1, bz0, bz1 in blocos) / 1e6
    area = max(area_bruta - area_furos, 0.0)
    f_arg = 1 - U["l"] * U["h"] / ((U["l"] + U["junta"]) * (U["h"] + U["junta"]))
    w.update(Halv=Halv, fiadas=fiadas, unidades=n_un, areaAlv=area, argamassa=area * U["t"] / 1000 * f_arg)
    _item(ctx, id=w["id"], tipo="alvenaria", grupo="paredes", o=[a[0] - w["n"][0] * w["tp"]["D"] / 2, a[1] - w["n"][1] * w["tp"]["D"] / 2, w["z0"]],
          u=list(w["d"]), v=[0, 0, 1], w=list(w["n"]), contorno=[[0, 0], [w["L"], 0], [w["L"], Halv], [0, Halv]],
          recortes=[{"x0": max(0.0, x0), "x1": min(w["L"], x1), "z0": max(0.0, bz0), "z1": min(Halv, bz1)} for x0, x1, bz0, bz1 in blocos],
          esp=w["tp"]["D"], info=f"{U['nome']} · {n_un} un · {area:.2f} m²")


# ---------------------------------------------------------------------------------------------------------- camadas
def _camadas(ctx, w):
    T = w["tp"]["T"]
    holes = [{"x0": ab["x0"], "x1": ab["x1"], "z0": ab["z0"], "z1": ab["z1"]} for ab in w["aberturas"]]
    if w.get("perimetro"):
        faixa = 0.0
        for g, zb in ctx.grupo_base.items():
            if abs(zb - (w["z0"] + w["H"])) < 5:
                faixa = max(faixa, ctx.grupo_topo[g] - zb)
        ext = [(T.get("exterior"), (w["perimetro"]["lado"], w["H"] + faixa), "Fachada")]
        intr = [(T.get("interior"), (w["L"], w["H"]), "Rebocos interiores")]
    else:
        ext = []
        intr = [(T.get("faceA"), (w["L"], w["H"]), "Rebocos interiores"), (T.get("faceB"), (w["L"], w["H"]), "Rebocos interiores")]
    for lst, (L, H), cat in ext + intr:
        for c in lst or []:
            C = ctx.proj["camadas"][c["camada"]]
            cells = subtract_rects({"x0": 0, "x1": L, "z0": 0, "z1": H}, holes)
            area = sum((cl["x1"] - cl["x0"]) * (cl["z1"] - cl["z0"]) for cl in cells) / 1e6
            ctx.extras.append({"cat": cat, "nivel": w.get("nivel"), "item": C["nome"], "un": "m²", "qtd": area, "ref": w["id"]})
            if C["tipo"] == "placa":
                pecas = []
                for cl in cells:
                    nx = math.ceil((cl["x1"] - cl["x0"]) / C["w"] - 1e-9)
                    nz = math.ceil((cl["z1"] - cl["z0"]) / C["h"] - 1e-9)
                    for ix in range(nx):
                        for iz in range(nz):
                            pecas.append({"w": min(C["w"], cl["x1"] - cl["x0"] - ix * C["w"]), "h": min(C["h"], cl["z1"] - cl["z0"] - iz * C["h"]), "ref": w["id"]})
                ctx.extras.append({"cat": cat, "nivel": w.get("nivel"), "item": f"{C['nome']} — placas {C['w']}×{C['h']} (plano de corte)", "un": "un",
                                   "qtd": len(plano_corte(pecas, C["w"], C["h"], 3, True)["folhas"]), "ref": w["id"]})


# ---------------------------------------------------------------------------------------------------------- cobertura
def _cobertura(ctx, c):
    R = ctx.R
    z = _resolve_z(ctx, c["z"])
    ax = c.get("cumeeira", "x") == "x"
    x0, y0, x1, y1 = c["x0"], c["y0"], c["x1"], c["y1"]
    A_len, C_len = (x1 - x0, y1 - y0) if ax else (y1 - y0, x1 - x0)
    al = math.radians(float(c.get("inclinacao", R["inclinacao"])))
    bei = float(c.get("beiral", R["beiral"]))
    half = C_len / 2
    lx = (half / math.cos(al)) / 1000
    ly = A_len / 1000
    h = max(R["lajeHmin"], math.ceil(min(lx, ly) * 1000 / 30 / 10) * 10 + 20)
    while True:
        r = ST.dalle_ba({"lx_m": lx, "ly_m": ly, "h_m": h / 1000, "g2_kn_m2": R["g2_cob"], "q_kn_m2": R["q_cob"], "fck": R["fck"], "y1": "continu"})
        if _ok(r) or h >= R["lajeHmax"]:
            break
        h += 10
    Ls = (half + bei) / math.cos(al) / 1000
    B = (A_len + 2 * bei) / 1000
    hh = half * math.tan(al)
    area = 2 * Ls * B
    kg = 2 * _laje_kg(r["details"], lx, ly, Ls * B)
    info = {"id": c["id"], "tipo": "duas_aguas", "h": h, "seccao": r["section"], "calc": r, "m3": area * h / 1000, "kg": kg, "cofragem": area,
            "area": area, "inclinacao": c.get("inclinacao", 30), "zCumeeira": z + hh}
    T = ctx.proj["telha"]
    n_t = 2 * math.ceil(Ls * 1000 / T["passo"] - 1e-9) * math.ceil(B * 1000 / T["largura"] - 1e-9)
    info["telhas"] = n_t
    ctx.coberturas.append(info)
    # carga da cobertura nas vigas de beirado (coroamento)
    for w in ctx.paredes:
        if w.get("vigas") and abs(w["z0"] + w["H"] - z) < 5 and w.get("perimetro"):
            par = abs(w["d"][0]) > 0.7 if ax else abs(w["d"][1]) > 0.7
            for v in w["vigas"]:
                if par:                                           # beirado: reação da água
                    v["g"] += (25 * h / 1000 + R["g2_cob"]) * lx / 2
                    v["q"] += R["q_cob"] * lx / 2
                else:                                             # topo: empena em alvenaria por cima (altura média)
                    U_ = ctx.proj["unidades"][ctx.proj["tiposParede"]["EXT"]["unidade"]]
                    v["g"] += R["gamaAlvenaria"] * U_["t"] / 1000 * hh / 2000
    # empenas em alvenaria (contadas fiada a fiada)
    Tx = ctx.proj["tiposParede"]["EXT"]
    U = ctx.proj["unidades"][Tx["unidade"]]
    mod_h = U["h"] + U["junta"]
    n_un, area_e = 0, 0.0
    for _ in range(2):
        k = 0
        while k * mod_h < hh:
            zc = (k + 0.5) * mod_h
            comp = C_len * max(0.0, 1 - zc / hh)
            n_un += math.ceil((comp + U["junta"]) / (U["l"] + U["junta"]) - 1e-9) if comp > 20 else 0
            k += 1
        area_e += C_len * hh / 2 / 1e6
    info["empenas"] = {"unidades": n_un, "area": area_e, "unidade": U["nome"]}

    def P(s, rr, zz):
        return [x0 + s, y0 + rr, zz] if ax else [x0 + rr, y0 + s, zz]

    def V(s, rr, zz):
        return [s, rr, zz] if ax else [rr, s, zz]
    ca, sa = math.cos(al), math.sin(al)
    for lado, sg in (("A", 1), ("B", -1)):
        r_e = -bei if sg == 1 else C_len + bei
        o = P(-bei if sg == 1 else A_len + bei, r_e, z - bei * math.tan(al))
        v = V(1, 0, 0) if sg == 1 else V(-1, 0, 0)
        _item(ctx, id=f"{c['id']}{lado}", tipo="cobertura", grupo="cobertura", o=o, u=V(0, sg * ca, sa), v=v, w=V(0, -sg * sa, ca),
              contorno=[[0, 0], [Ls * 1000, 0], [Ls * 1000, B * 1000], [0, B * 1000]], esp=h, info=r["section"])
    for lado, s_w in (("E1", 0.0), ("E2", A_len)):
        sgn = 1 if s_w == 0 else -1
        _item(ctx, id=f"{c['id']}-{lado}", tipo="empena", grupo="paredes", o=P(s_w, 0 if sgn == 1 else C_len, z), u=V(0, sgn, 0), v=[0, 0, 1], w=V(sgn, 0, 0),
              contorno=[[0, 0], [C_len, 0], [half, hh]], esp=U["t"], info=f"empena em alvenaria · {U['nome']}")


# --------------------------------------------------------------------------------------------------------------- cálculo
def calcular(proj_in: dict) -> dict:
    proj = copy.deepcopy(proj_in)
    from . import defaults
    b = defaults.base(proj.get("country", "PT"))
    for k, v in b.items():
        proj.setdefault(k, v)
    for k, v in defaults.REGRAS.items():
        proj["regras"].setdefault(k, v)
    ctx = Ctx(proj)
    _prep_lajes(ctx)
    for per in proj.get("perimetros") or []:
        _perimetro(ctx, per)
    for w in proj.get("paredes") or []:
        _avulsa(ctx, w)
    for w in ctx.paredes:
        _aberturas(ctx, w)
    _resistentes(ctx)
    _pilares(ctx)
    _vigas(ctx)
    for c in proj.get("coberturas") or []:
        _cobertura(ctx, c)
    if proj.get("coberturas"):                            # vigas de coroamento redimensionadas com a carga da cobertura
        for v in ctx.vigas:
            if True:
                Lm, b_, h = v["L"] / 1000, v["b"] / 1000, v["h"] / 1000
                while True:
                    r = ST.poutre_ba({"portee_m": Lm, "b_m": b_, "h_m": h, "g_kn_m": v["g"], "q_kn_m": v["q"], "appuis": v["apoios"], "fck": ctx.R["fck"]})
                    if _ok(r) or h >= 0.8:
                        break
                    h = round(h + 0.05, 2)
                v.update(h=h * 1000, calc=r, seccao=r["section"], armadura=r["barres"]["label"], estribos=r["etriers"], kg=r["quantites"]["acier_kg"],
                         m3=r["quantites"]["beton_m3"], cofragem=(b_ + 2 * h) * Lm)
                v["o"][2] = v["z1"] - h * 1000
    _dim_pilares(ctx)
    _fundacoes(ctx)
    for w in ctx.paredes:
        _alvenaria(ctx, w)
        _camadas(ctx, w)
    return _resumo(ctx)


# --------------------------------------------------------------------------------------------------------------- resumo
def _resumo(ctx):
    proj, R = ctx.proj, ctx.R
    for p in ctx.pilares:
        _item(ctx, id=p["id"], tipo="pilar", grupo="estrutura", o=[p["x"] - p["d"][0] * p["h"] / 2 + p["d"][1] * p["b"] / 2,
                                                                   p["y"] - p["d"][1] * p["h"] / 2 - p["d"][0] * p["b"] / 2, p["z0"]],
              u=[p["d"][0], p["d"][1], 0], v=[-p["d"][1], p["d"][0], 0], w=[0, 0, 1], contorno=[[0, 0], [p["h"], 0], [p["h"], p["b"]], [0, p["b"]]],
              esp=p["H"], info=f"{p['seccao']} · {p['armadura']}")
    for v in ctx.vigas:
        _item(ctx, id=v["id"], tipo="viga", grupo="estrutura", o=v["o"], u=v["eixo"], v=v["lado"], w=[0, 0, 1],
              contorno=[[0, 0], [v["L"], 0], [v["L"], v["b"]], [0, v["b"]]], esp=v["h"], info=f"{v['seccao']} · {v['armadura']}")
    for f in ctx.lajes:
        _item(ctx, id=f["id"], tipo="laje", grupo="lajes", o=[f["x0"], f["y0"], f["z"]], u=[1, 0, 0], v=[0, 1, 0], w=[0, 0, 1],
              contorno=[[0, 0], [f["x1"] - f["x0"], 0], [f["x1"] - f["x0"], f["y1"] - f["y0"]], [0, f["y1"] - f["y0"]]], esp=f["h"], info=f["seccao"])
    # pavimento térreo
    terreo = None
    if proj.get("perimetros"):
        p0 = min(proj["perimetros"], key=lambda p: _resolve_z(ctx, p.get("z0", 0)))
        t_ext = ctx.proj["unidades"][ctx.proj["tiposParede"]["EXT"]["unidade"]]["t"]
        poly = Polygon(p0["pontos"]).buffer(-t_ext, join_style=2)
        area = poly.area / 1e6
        malha = 2 * (math.pi * 0.006 ** 2 / 4 / 0.15) * 7850           # #Ø6 // 0,15 nas duas direções (kg/m²) — armadura construtiva
        terreo = {"area": area, "m3": area * R["massameH"] / 1000, "enrocamento": area * R["enrocamento"] / 1000, "kg": area * malha,
                  "malha": "malha eletrossoldada Ø6 // 0,15 (A500 ER)"}
    niveis = []
    for w in ctx.paredes:
        if w.get("nivel") not in niveis:
            niveis.append(w.get("nivel"))
    return {"nome": proj.get("nome"), "country": proj.get("country", "PT"), "regras": R, "hipoteses": list(proj.get("hipoteses") or []),
            "avisos": ctx.avisos, "niveis": niveis,
            "paredes": [{k: w.get(k) for k in ("id", "tipo", "L", "H", "z0", "A", "d", "n", "y0", "nivel", "aberturas", "resistente", "Halv", "fiadas",
                                                "unidades", "areaAlv", "argamassa", "pilaresX", "perimetro")} | {"Dt": w["tp"]["D"], "unidade": w["tp"]["U"]["nome"],
                                                                                                                "vigas": [v["id"] for v in w.get("vigas") or []]}
                        for w in ctx.paredes],
            "pilares": [{k: v for k, v in p.items() if k != "calc"} for p in ctx.pilares],
            "vigas": [{k: v for k, v in x.items() if k != "calc"} for x in ctx.vigas],
            "sapatas": [{k: v for k, v in s.items() if k != "calc"} for s in ctx.sapatas],
            "vigasFundacao": [{k: v for k, v in x.items() if k != "calc"} for x in ctx.vfund],
            "vergas": ctx.vergas,
            "lajes": [{k: v for k, v in f.items() if k != "calc"} for f in ctx.lajes],
            "coberturas": [{k: v for k, v in c.items() if k != "calc"} for c in ctx.coberturas],
            "terreo": terreo, "extras": ctx.extras, "itens": ctx.itens,
            "estudo": _totais(ctx, terreo)}


def _totais(ctx, terreo):
    m3 = sum(x["m3"] for x in ctx.pilares + ctx.vigas + ctx.sapatas + ctx.vfund + ctx.vergas + ctx.lajes + ctx.coberturas) + (terreo or {}).get("m3", 0)
    kg = sum(x["kg"] for x in ctx.pilares + ctx.vigas + ctx.sapatas + ctx.vfund + ctx.vergas + ctx.lajes + ctx.coberturas) + (terreo or {}).get("kg", 0)
    area = 0.0
    for p in ctx.proj.get("perimetros") or []:
        pts = p["pontos"]
        area += Polygon(pts).area / 1e6
    un = sum(w.get("unidades", 0) for w in ctx.paredes) + sum(c.get("empenas", {}).get("unidades", 0) for c in ctx.coberturas)
    return {"m3Betao": m3, "kgAco": kg, "unidadesAlvenaria": un, "m2Alvenaria": sum(w.get("areaAlv", 0) for w in ctx.paredes),
            "nPilares": len({p["pilar"] for p in ctx.pilares}), "nVigas": len(ctx.vigas), "nSapatas": len(ctx.sapatas), "areaPisos": area,
            "kgPorM3": kg / m3 if m3 else None, "escavacao": sum(s["escavacao"] for s in ctx.sapatas) + sum(v["escavacao"] for v in ctx.vfund)}
