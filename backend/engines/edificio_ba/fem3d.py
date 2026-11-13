"""Modelo 3D de elementos finitos (PyNite, licença MIT) — superestrutura acima da base sísmica.

Pilares e vigas : barras elásticas (EI fendilhado = 0,5·EI, EN 1998-1 §4.3.1(7)) ; núcleos e paredes : cascas MITC4
(E fendilhado 0,5·E) ; lajes : diafragmas rígidos com massa (m, m, J) no centro de massa. Análise modal + espectro de resposta
(forças modais estáticas equivalentes, combinação CQC), excentricidade acidental ± 5 % (momentos torsores estáticos),
combinação E_x ± 0,3·E_y.

O PyNite monta a matriz de rigidez das barras e cascas ; os diafragmas, a massa e a resolução (condensação estática nos
graus de liberdade dos pisos, valores próprios generalizados) são feitos aqui com numpy/scipy. Substitui o OpenSeesPy,
cuja licença (UC Berkeley) não permite uso comercial sem acordo. Sem PyNite instalado, available() = False e o estudo usa
o método das forças laterais.
"""
from __future__ import annotations

import math

import numpy as np

from . import estrutura as ES
from . import grelha

CR = 0.5
SUB_V = 2
H_MAX = 0.80
NU = 0.2

# Eixos : (x, y, z) do edifício, z vertical → PyNite (X, Y, Z) = (x, z, −y), Y vertical como nas outras rotinas PyNite.
# Para cada g.d.l. PyNite k : (g.d.l. do edifício, sinal) com u_PyNite[k] = sinal · u_edifício[gdl].
_P2B = ((0, 1), (2, 1), (1, -1), (3, 1), (5, 1), (4, -1))


def available() -> bool:
    try:
        import Pynite  # noqa: F401
        import scipy.linalg  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


class Model:
    def __init__(self, S, R):
        from Pynite import FEModel3D
        self.fe = FEModel3D()
        self.S, self.R = S, R
        self.M = ES.mat(S)
        self.zf = [k * S.H for k in range(S.n + 1)]
        self.nodes, self.coords, self.ntag, self.etag = {}, {}, 0, 0
        self.wall_nodes, self.floor_nodes = {}, {round(z, 3): set() for z in self.zf}
        self.col_base, self.masters, self.lines = {}, {}, []
        self.seg_rows, self.embedded = [], set()
        self.J = None

    def node(self, x, y, z):
        k = (round(x, 3), round(y, 3), round(z, 3))
        if k not in self.nodes:
            self.ntag += 1
            self.fe.add_node(f"N{self.ntag}", k[0], k[2], -k[1])
            self.nodes[k] = self.ntag
            self.coords[self.ntag] = k
            if k[2] in self.floor_nodes:
                self.floor_nodes[k[2]].add(self.ntag)
        return self.nodes[k]

    def _bar(self, n0, n1, A, Iy, Iz, J):
        """Barra elástica ; Iy / Iz = inércias para deslocamentos segundo y / x (pilares) ou vertical / horizontal (vigas)."""
        self.etag += 1
        sec = f"S{self.etag}"
        horizontal = abs(self.coords[n0][2] - self.coords[n1][2]) < 1e-6
        # PyNite : vigas → eixo local y vertical (Iz flexão vertical) ; pilares → eixo local z = −y do edifício.
        self.fe.add_section(sec, A, Iz if horizontal else Iy, Iy if horizontal else Iz, J)
        self.fe.add_member(f"E{self.etag}", f"N{n0}", f"N{n1}", "betao", sec)
        self.lines.append([self.coords[n0], self.coords[n1]])

    def wall_segments(self):
        segs = []
        for c in self.S.cores:
            x0, y0, x1, y1 = c["box"]
            t = c["t"]
            xa, xb, ya, yb = x0 + t / 2, x1 - t / 2, y0 + t / 2, y1 - t / 2
            d, side = c.get("door") or 0.0, c.get("door_side")
            faces = {"y0": ((xa, ya), (xb, ya)), "y1": ((xa, yb), (xb, yb)), "x0": ((xa, ya), (xa, yb)), "x1": ((xb, ya), (xb, yb))}
            for s, (a, b) in faces.items():
                if side == s and d > 0:
                    if s in ("x0", "x1"):
                        a, b = ((a[0], a[1] + d), b) if s == "x0" else (a, (b[0], b[1] - d))
                    else:
                        a, b = (a, (b[0] - d, b[1])) if s == "y0" else ((a[0] + d, a[1]), b)
                if math.dist(a, b) > 0.3:
                    segs.append((c["id"], a, b, t))
        for w in self.S.walls:
            segs.append((w["id"], (w["x0"], w["y0"]), (w["x1"], w["y1"]), w["t"]))
        return segs

    @staticmethod
    def _snap(x, y, segs):
        best = None
        for _, (ax, ay), (bx, by), _t in segs:
            vx, vy = bx - ax, by - ay
            tt = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy)))
            px, py = ax + tt * vx, ay + tt * vy
            d = math.hypot(px - x, py - y)
            if d < 0.6 and (best is None or d < best[0]):
                best = (d, round(px, 3), round(py, 3))
        return (best[1], best[2]) if best else (x, y)

    @staticmethod
    def _on(p, a, b, tol=0.03):
        return grelha.dist_seg(p[0], p[1], a, b) < tol

    def _embed(self, end, other, z, props):
        """Viga no prolongamento de uma parede : continua um troço dentro da parede, como nos programas comerciais.

        As cascas só têm uma mola fraca na rotação em torno da sua normal ; sem este troço a viga ficaria articulada
        no plano da parede e o acoplamento das paredes (esforço normal sísmico) seria subestimado.
        """
        ux, uy = end[0] - other[0], end[1] - other[1]
        L = math.hypot(ux, uy)
        if L < 1e-6:
            return
        ux, uy = ux / L, uy / L
        mid = ((end[0] + other[0]) / 2, (end[1] + other[1]) / 2)
        for a, b, rows in self.seg_rows:
            Lw = math.dist(a, b)
            if not self._on(end, a, b) or self._on(mid, a, b):
                continue
            if abs(ux * (b[1] - a[1]) - uy * (b[0] - a[0])) / Lw > 0.05:
                continue                                              # viga perpendicular à parede : flexão fora do plano
            n0 = self.node(end[0], end[1], z)
            best = None
            for t in rows.get(round(z, 3), []):
                x, y, _ = self.coords[t]
                d = (x - end[0]) * ux + (y - end[1]) * uy
                if d > 1e-3 and (best is None or d < best[0]):
                    best = (d, t)
            if best and (n0, best[1]) not in self.embedded:
                self.embedded.add((n0, best[1]))
                self._bar(n0, best[1], *props)

    def build(self):
        fe, S, R, Mt = self.fe, self.S, self.R, self.M
        Ec = Mt["Ec"]
        fe.add_material("betao", Ec, Ec / 2.4, NU, 0.0)
        fe.add_material("casca", CR * Ec, CR * Ec / (2 * (1 + NU)), NU, 0.0)
        segs = self.wall_segments()
        self.beam_lines = []
        pts = []
        for bm in R["beams"]:
            a, b = self._snap(*bm["a"], segs), self._snap(*bm["b"], segs)
            self.beam_lines.append((bm, a, b))
            pts += [a, b]
        cols = [c for c in R["cols"] if not c["garage"]]
        for nm, (ax, ay), (bx, by), t in segs:
            Lw = math.hypot(bx - ax, by - ay)
            ts = {0.0, 1.0}
            for (px, py) in pts + [(c["x"], c["y"]) for c in S.columns]:
                vx, vy = bx - ax, by - ay
                tt = ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)
                if 0 < tt < 1 and math.hypot(ax + tt * vx - px, ay + tt * vy - py) < 0.02:
                    ts.add(round(tt, 4))
            ts = sorted(ts)
            grid = [0.0]
            for u, v in zip(ts, ts[1:]):
                n = max(1, math.ceil((v - u) * Lw / H_MAX))
                grid += [u + (v - u) * i / n for i in range(1, n + 1)]
            zs = []
            for z0, z1 in zip(self.zf, self.zf[1:]):
                zs += [z0 + (z1 - z0) * i / SUB_V for i in range(SUB_V)]
            zs.append(self.zf[-1])
            ids = [[self.node(ax + u * (bx - ax), ay + u * (by - ay), z) for u in grid] for z in zs]
            for iz in range(len(zs) - 1):
                for iu in range(len(grid) - 1):
                    self.etag += 1
                    q = (ids[iz][iu], ids[iz][iu + 1], ids[iz + 1][iu + 1], ids[iz + 1][iu])
                    fe.add_quad(f"E{self.etag}", *(f"N{i}" for i in q), t, "casca")
                    self.lines.append([self.coords[i] for i in q])
            self.wall_nodes.setdefault(nm, []).extend(ids[0])
            self.seg_rows.append(((ax, ay), (bx, by), {round(z, 3): row for z, row in zip(zs, ids)}))
        for c in cols:
            for k, (z0, z1) in enumerate(zip(self.zf, self.zf[1:])):
                top = c.get("topo")
                sct = top if (top and top.get("from") is not None and k >= top["from"]) else c["base"]
                b, h = sct["b"], sct["h"]
                A = b * h
                self._bar(self.node(c["x"], c["y"], z0), self.node(c["x"], c["y"], z1), A,
                          b * h ** 3 / 12 * CR, h * b ** 3 / 12 * CR, 0.2 * A * min(b, h) ** 2)
            self.col_base[c["id"]] = self.node(c["x"], c["y"], self.zf[0])
        for bm, (x0, y0), (x1, y1) in self.beam_lines:
            h, b = bm["h"], bm["b_w"]
            p_ = {(x0, y0), (x1, y1)}
            for c in S.columns:
                if self._on((c["x"], c["y"]), (x0, y0), (x1, y1)):
                    p_.add((c["x"], c["y"]))
            for _, a, bb in self.beam_lines:
                for p in (a, bb):
                    if self._on(p, (x0, y0), (x1, y1)):
                        p_.add(p)
            p_ = sorted(p_, key=lambda p: math.hypot(p[0] - x0, p[1] - y0))
            for z in self.zf[1:]:
                for p, q in zip(p_, p_[1:]):
                    if math.dist(p, q) < 0.05:
                        continue
                    A = b * h
                    props = (A, b * h ** 3 / 12 * CR, h * b ** 3 / 12 * CR, 0.2 * A * b ** 2)
                    self._bar(self.node(p[0], p[1], z), self.node(q[0], q[1], z), *props)
                    self._embed(p, q, z, props)
                    self._embed(q, p, z, props)
        st = R["seis"]["storeys"]
        Lx = S.L + 2 * max([b["depth"] for b in S.balconies if b["side"] in ("x0", "x1")] or [0.0])
        Ly = S.B + sum(b["depth"] for b in S.balconies if b["side"] in ("y0", "y1"))
        self.m = np.array([s_["W"] / 9.81 for s_ in st[:S.n]])
        self.J = self.m * (Lx ** 2 + Ly ** 2) / 12 * 0.85
        for k, z in enumerate(self.zf[1:]):
            self.masters[z] = k
        self._assemble()
        return self

    def _assemble(self):
        """Rigidez PyNite → transformação dos diafragmas → condensação estática nos 3 g.d.l. (Ux, Uy, Rz) de cada piso."""
        import scipy.linalg as sla
        import scipy.sparse as sp
        from Pynite import Analysis
        from scipy.sparse.linalg import splu

        fe, S = self.fe, self.S
        Analysis._prepare_model(fe)
        K = fe.Ke(check_stability=False, sparse=True).tocsr()
        xm, ym = S.L / 2, S.B / 2
        zb = round(self.zf[0], 3)
        mr = {round(z, 3): k for z, k in self.masters.items()}
        floor_of = {t: z for z, ts in self.floor_nodes.items() if z != zb for t in ts}
        nm = 3 * S.n
        rows, cols, vals = [], [], []
        nxt = nm
        base_rows, base_ref = [], []
        for tag, (x, y, z) in self.coords.items():
            pid = fe.nodes[f"N{tag}"].ID * 6
            if z == zb:
                for k, (bi, sg) in enumerate(_P2B):
                    base_rows.append(pid + k)
                    base_ref.append((tag, bi, sg))
                continue
            fz = floor_of.get(tag)
            own = {}
            for k, (bi, sg) in enumerate(_P2B):
                if fz is not None and bi in (0, 1, 5):
                    m0 = 3 * mr[fz]
                    terms = {0: ((m0, 1.0), (m0 + 2, -(y - ym))), 1: ((m0 + 1, 1.0), (m0 + 2, x - xm)), 5: ((m0 + 2, 1.0),)}[bi]
                else:
                    if bi not in own:
                        own[bi] = nxt
                        nxt += 1
                    terms = ((own[bi], 1.0),)
                for q, c in terms:
                    rows.append(pid + k)
                    cols.append(q)
                    vals.append(sg * c)
        T = sp.csr_matrix((vals, (rows, cols)), shape=(K.shape[0], nxt))
        Kr = (T.T @ K @ T).tocsc()
        Kmm, Kms = Kr[:nm, :nm].toarray(), Kr[:nm, nm:]
        Kss = Kr[nm:, nm:].tocsc()
        self.X = splu(Kss).solve(Kms.T.toarray())                    # q_s = −X · q_m
        self.Kc = Kmm - Kms @ self.X
        self.Kc = (self.Kc + self.Kc.T) / 2
        self.Mdiag = np.ravel(np.column_stack([self.m, self.m, self.J]))
        self.Rb = (K[base_rows, :] @ T).tocsr()                      # reações = Rb · q
        self.base_ref = base_ref
        self._lu = sla.cho_factor(self.Kc)

    def modal(self, n=9):
        import scipy.linalg as sla
        n = min(n, 3 * self.S.n)
        lam, vec = sla.eigh(self.Kc, np.diag(self.Mdiag))
        m, J = self.m, self.J
        Mtot = m.sum()
        out = []
        for k in range(n):
            phi = vec[:, k].reshape(-1, 3)
            mm = (m * phi[:, 0] ** 2).sum() + (m * phi[:, 1] ** 2).sum() + (J * phi[:, 2] ** 2).sum()
            Lx, Ly, Lr = (m * phi[:, 0]).sum(), (m * phi[:, 1]).sum(), (J * phi[:, 2]).sum()
            out.append({"mode": k + 1, "T": 2 * math.pi / math.sqrt(lam[k]), "phi": phi, "Gx": Lx / mm, "Gy": Ly / mm,
                        "Mx": Lx ** 2 / mm / Mtot, "My": Ly ** 2 / mm / Mtot, "Mr": Lr ** 2 / mm / J.sum()})
        return out

    def static_case(self, loads):
        import scipy.linalg as sla
        F = np.zeros(3 * self.S.n)
        for z, (fx, fy, mz) in loads.items():
            F[3 * self.masters[z]:3 * self.masters[z] + 3] = (fx, fy, mz)
        qm = sla.cho_solve(self._lu, F)
        q = np.concatenate([qm, -self.X @ qm])
        rp = self.Rb @ q
        reac = {}
        for (tag, bi, sg), r in zip(self.base_ref, rp):
            reac.setdefault(tag, [0.0] * 6)[bi] = sg * r
        disp = {z: tuple(qm[3 * k:3 * k + 3]) for z, k in self.masters.items()}
        res = {}
        for nm, tags in self.wall_nodes.items():
            tags = sorted(set(tags))
            Fr = np.array([reac[t] for t in tags])
            xyz = np.array([self.coords[t] for t in tags])
            cx, cy = xyz[:, 0].mean(), xyz[:, 1].mean()
            Mx = -(Fr[:, 3].sum() + ((xyz[:, 1] - cy) * Fr[:, 2]).sum())
            My = -(Fr[:, 4].sum() - ((xyz[:, 0] - cx) * Fr[:, 2]).sum())
            res[nm] = {"Vx": -Fr[:, 0].sum(), "Vy": -Fr[:, 1].sum(), "N": -Fr[:, 2].sum(), "Mx": Mx, "My": My}
        for cid, t in self.col_base.items():
            Fr = reac[t]
            res[cid] = {"Vx": -Fr[0], "Vy": -Fr[1], "N": -Fr[2], "Mx": -Fr[3], "My": -Fr[4]}
        return disp, res


def cqc(vals, T, xi=0.05):
    s = 0.0
    for i in range(len(vals)):
        for j in range(len(vals)):
            beta = T[j] / T[i]
            rho = 8 * xi ** 2 * (1 + beta) * beta ** 1.5 / ((1 - beta ** 2) ** 2 + 4 * xi ** 2 * beta * (1 + beta) ** 2)
            s += rho * vals[i] * vals[j]
    return math.sqrt(max(s, 0.0))


def _spectrum(Mo, modes, sp, q):
    S = Mo.S
    m = np.array([s["W"] / 9.81 for s in Mo.R["seis"]["storeys"]])
    J = Mo.J
    zs = Mo.zf[1:]
    T = [md["T"] for md in modes]
    out = {}
    corners = [(0, 0), (S.L, 0), (0, S.B), (S.L, S.B)]
    for d, gkey in (("X", "Gx"), ("Y", "Gy")):
        per = []
        for md in modes:
            a = ES._sd(md["T"], sp["ag"], sp["S"], sp["TB"], sp["TC"], sp["TD"], q)
            phi = md["phi"]
            G = md[gkey]
            F = {z: (m[k] * phi[k, 0] * G * a, m[k] * phi[k, 1] * G * a, J[k] * phi[k, 2] * G * a) for k, z in enumerate(zs)}
            per.append((F,) + Mo.static_case(F))
        comb = {kk: {c: cqc([pm[2][kk][c] for pm in per], T) for c in ("Vx", "Vy", "N", "Mx", "My")} for kk in per[0][2]}
        Vb = cqc([sum(f[0] if d == "X" else f[1] for f in pm[0].values()) for pm in per], T)
        drift = []
        for i, z in enumerate(zs):
            zb = zs[i - 1] if i else None
            worst = 0.0
            for cx, cy in corners:
                vals = []
                for pm in per:
                    ux, uy, rz = pm[1][z]
                    dx, dy = ux - (cy - S.B / 2) * rz, uy + (cx - S.L / 2) * rz
                    if zb is not None:
                        ux0, uy0, rz0 = pm[1][zb]
                        dx -= ux0 - (cy - S.B / 2) * rz0
                        dy -= uy0 + (cx - S.L / 2) * rz0
                    vals.append(dx if d == "X" else dy)
                worst = max(worst, cqc(vals, T))
            drift.append(worst)
        out[d] = {"Vb": Vb, "elems": comb, "drift_e": drift}
    return out


def run(S, R) -> dict:
    """→ {modes, sp, env, Vb, n_nodes, n_el, gov} ; R deve conter cols, beams, seis."""
    Mo = Model(S, R).build()
    modes = Mo.modal()
    q = S.seismic["q"]
    sps = [(sp, _spectrum(Mo, modes, sp, q)) for sp in ES.spectra(S)]
    gov_sp, gov = max(sps, key=lambda x: x[1]["X"]["Vb"] + x[1]["Y"]["Vb"])
    st = R["seis"]["storeys"]
    zs = Mo.zf[1:]
    sz = sum(s["W"] * z for s, z in zip(st, zs))
    acc = {}
    for d in ("X", "Y"):
        e = 0.05 * (S.B if d == "X" else S.L)
        loads = {z: (0.0, 0.0, gov[d]["Vb"] * s["W"] * z / sz * e) for s, z in zip(st, zs)}
        acc[d] = Mo.static_case(loads)[1]
    env = {}
    for kk in gov["X"]["elems"]:
        ex, ey, ax_, ay_ = gov["X"]["elems"][kk], gov["Y"]["elems"][kk], acc["X"][kk], acc["Y"][kk]
        env[kk] = {c: max(ex[c] + abs(ax_[c]) + 0.3 * (ey[c] + abs(ay_[c])), 0.3 * (ex[c] + abs(ax_[c])) + ey[c] + abs(ay_[c]))
                   for c in ("Vx", "Vy", "N", "Mx", "My")}
    geo = {"zf": Mo.zf, "lines": Mo.lines}
    res = {"modes": modes, "sp": gov, "sp_label": gov_sp["label"], "env": env, "n_nodes": len(Mo.nodes), "n_el": Mo.etag,
           "Vb_all": {sp["label"]: {d: round(r[d]["Vb"], 0) for d in "XY"} for sp, r in sps}, "geo": geo}
    return res


def apply(S, R, F) -> None:
    """Substitui M e V dos núcleos/paredes pelos esforços do modelo 3D (envolvente) e recalcula armaduras, derivas e fundações."""
    Mt = ES.mat(S)
    s = R["seis"]
    env = F["env"]
    for dsg in s["cores"] + s["walls"]:
        e = env.get(dsg["id"])
        if not e:
            continue
        webs = 2 if dsg["kind"] == "core" else 1
        for d, Mk, Vk in (("X", "My", "Vx"), ("Y", "Mx", "Vy")):
            v = dsg[d]
            v["M_simpl"], v["V_simpl"] = v["M"], v["V"]
            v["M"], v["V"] = round(float(e[Mk]), 0), round(float(e[Vk]), 0)
            Lw, t = v["Lw"], dsg["t"]
            as_min = 0.005 * t * max(0.15 * Lw, 1.5 * t) * 1e4
            v["As_ext_cm2"] = round(max((v["M"] / (0.8 * Lw) - dsg["N_sis"] / 2) / (Mt["fyd"] * 1000) * 1e4, as_min), 1)
            rho = max((v["V"] * 1.5 - v["VRdc"]) / (webs * t * 0.9 * Lw * Mt["fyd"] * 1000), 0.0)
            v["rho_h"] = round(max(rho, 0.002), 4)
    q = s["q"]
    s["drift_fem"] = {d: {"de_mm": [round(x * 1000, 2) for x in F["sp"][d]["drift_e"]], "nu_dr_mm": round(0.5 * q * max(F["sp"][d]["drift_e"]) * 1000, 2),
                          "lim_mm": round(0.005 * S.H * 1000, 1)} for d in ("X", "Y")}
    R["fem"] = {"modes": [{k: v for k, v in m.items() if k != "phi"} for m in F["modes"]], "Vb": {d: round(F["sp"][d]["Vb"], 0) for d in "XY"},
                "Vb_all": F["Vb_all"], "sp_label": F["sp_label"], "n_nodes": F["n_nodes"], "n_el": F["n_el"],
                "cols": {k: v for k, v in env.items() if any(c["id"] == k for c in R["cols"])}}


def figures(S, F, path_model, path_modes):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7.2, 4.6), dpi=170)
    ax = fig.add_subplot(111, projection="3d")
    for xyz in F["geo"]["lines"]:
        xyz = np.array(xyz)
        if len(xyz) == 4:
            ax.plot(*np.vstack([xyz, xyz[:1]]).T, color="#8e8e8a", lw=0.25)
        else:
            vert = abs(xyz[0, 2] - xyz[1, 2]) > 0.1
            ax.plot(*xyz.T, color="#1d2422" if vert else "#eb6834", lw=0.8 if vert else 0.5)
    ax.set_box_aspect((S.L, S.B, S.n * S.H))
    ax.view_init(elev=24, azim=-58)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path_model, bbox_inches="tight")
    fig = Figure(figsize=(7.4, 2.5), dpi=170)
    axs = [fig.add_subplot(1, 3, k + 1) for k in range(3)]
    outline = np.array([[0, 0], [S.L, 0], [S.L, S.B], [0, S.B], [0, 0]])
    for k, ax in enumerate(axs):
        if k >= len(F["modes"]):
            ax.axis("off")
            continue
        md = F["modes"][k]
        ux, uy, rz = md["phi"][-1]
        sc = 2.5 / max(abs(ux), abs(uy), abs(rz) * 10, 1e-9)
        xm, ym = S.L / 2, S.B / 2
        dp = np.array([(x + sc * (ux - (y - ym) * rz), y + sc * (uy + (x - xm) * rz)) for x, y in outline])
        ax.plot(outline[:, 0], outline[:, 1], color="#b9b9b5", lw=0.8)
        ax.plot(dp[:, 0], dp[:, 1], color="#2a78d6", lw=1.2)
        kind = ("torção" if S.lang == "pt" else "torsion") if md["Mr"] > max(md["Mx"], md["My"]) else \
            ("translação X" if S.lang == "pt" else "translation X") if md["Mx"] > md["My"] else ("translação Y" if S.lang == "pt" else "translation Y")
        ax.set_title(f"{'Modo' if S.lang == 'pt' else 'Mode'} {k + 1} — T = {md['T']:.3f} s\n{kind}".replace(".", ","), fontsize=7)
        ax.set_aspect("equal")
        ax.set_xlim(-4, S.L + 4)
        ax.set_ylim(-4, S.B + 4)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path_modes, bbox_inches="tight")
