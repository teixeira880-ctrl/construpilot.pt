"""Motor de cálculo LSF (Light Steel Framing) — determinístico, sem IA.

Entrada: projeto LSF (ver defaults.exemplo / adapter.from_takeoff), unidades mm, Z vertical.
Saída: cada perfil com geometria 3D real (origem + eixos + secção), placas com recortes e plano de corte, parafusos
contados ligação a ligação e linha a linha de estrutura sob cada placa, ancoragens, isolamento, ETICS, membranas, cobertura.

Cadeia: pisos (cotas) → paredes de perímetro (cantos convexos/côncavos) → paredes interiores (corte nas faces, montantes
de ligação) → estrutura das paredes (montantes à modulação, vãos com montante rei + apoio em caixão, vergas, peitoris,
montantes curtos, bloqueadores, fitas) → pisos (guias de bordadura, vigas, travamentos, OSB) → asnas Fink (diagonais
dorso-com-dorso com comprimento máximo dentro dos banzos) → revestimentos (juntas sempre sobre montante, faixa do piso,
parafusos por linha) → resumo (lista de corte, barras, plano de corte MaxRects, mapa de quantidades).
"""
from __future__ import annotations

import copy
import math

from .geom import (EPS, ffd, kg_per_m, member_bbox, plano_corte, profile_name, r1, rect_area, subtract_intervals,
                   subtract_rects)


class Ctx:
    def __init__(self, proj: dict):
        self.proj = proj
        self.membros: list[dict] = []
        self.placas: list[dict] = []
        self.avisos: list[str] = []
        self.paredes: list[dict] = []
        self.pisos: list[dict] = []
        self.coberturas: list[dict] = []
        self.parafusos: dict[str, dict] = {}
        self.ancoragens: dict[str, dict] = {}
        self.extras: list[dict] = []
        self.cont: dict[str, int] = {}
        self.grupo_topo: dict[str, float] = {}
        self.perim_topo: dict[str, float] = {}
        self.packs: dict[str, dict] = {}
        self.trace: list[dict] = []

    def P(self, k: str) -> dict:
        p = self.proj["perfis"].get(k)
        if not p:
            raise ValueError(f'Perfil "{k}" não definido em perfis')
        return p


def calcular(proj_in: dict) -> dict:
    proj = copy.deepcopy(proj_in)
    proj.setdefault("regras", {})
    proj.setdefault("placas", {})
    ctx = Ctx(proj)
    for f in proj.get("pisos") or []:
        ctx.pisos.append(_prep_piso(ctx, f))
    for per in proj.get("perimetros") or []:
        _expand_perimetro(ctx, per)
    niveis_z = {round(w["z0"]): w.get("nivel") for w in ctx.paredes}
    for w in proj.get("paredes") or []:
        _prep_parede_avulsa(ctx, w)
        if not ctx.paredes[-1].get("nivel"):
            ctx.paredes[-1]["nivel"] = niveis_z.get(round(ctx.paredes[-1]["z0"]))
    for w in ctx.paredes:
        _estrutura_parede(ctx, w)
    for f in ctx.pisos:
        _estrutura_piso(ctx, f)
    for c in proj.get("coberturas") or []:
        _estrutura_cobertura(ctx, c)
    for w in ctx.paredes:
        _revestimentos_parede(ctx, w)
    return _resumo(ctx)


# ------------------------------------------------------------------------------------------------------------------ util
def _add_par(ctx, nome, qtd, origem):
    if not qtd:
        return
    e = ctx.parafusos.setdefault(nome, {"nome": nome, "qtd": 0, "origens": {}})
    e["qtd"] += qtd
    e["origens"][origem] = e["origens"].get(origem, 0) + qtd


def _add_anc(ctx, nome, qtd, origem):
    if not qtd:
        return
    e = ctx.ancoragens.setdefault(nome, {"nome": nome, "qtd": 0, "origens": {}})
    e["qtd"] += qtd
    e["origens"][origem] = e["origens"].get(origem, 0) + qtd


def _next_id(ctx, ref, pref):
    k = ref + "|" + pref
    ctx.cont[k] = ctx.cont.get(k, 0) + 1
    return f"{ref}-{pref}{ctx.cont[k]:02d}"


def _aviso(ctx, msg):
    if msg not in ctx.avisos:
        ctx.avisos.append(msg)


def _pack(ctx, chave, nome, W, H, rodar, peca):
    e = ctx.packs.setdefault(chave, {"chave": chave, "nome": nome, "W": W, "H": H, "rodar": rodar, "pecas": []})
    e["rodar"] = e["rodar"] and rodar
    e["pecas"].append(peca)


def _membro(ctx, m: dict):
    p = ctx.P(m["perfil"])
    b = p["t"] if p["tipo"] == "F" else p["b"]
    m["prof"] = p
    m["perfilNome"] = profile_name(p)
    m["L"] = r1(m["L"])
    if m["L"] <= 0:
        _aviso(ctx, f"{m['id']}: comprimento nulo ou negativo — geometria incoerente.")
        return None
    m["kg"] = kg_per_m(p, ctx.proj.get("aco", {}).get("densidade", 7850)) * m["L"] / 1000
    m["bbox"] = member_bbox(m["o"], m["u"], m["v"], m["w"], b, p["h"], m["L"])
    ctx.membros.append(m)
    return m


def _vaos_do_lado(vaos, i):
    if not vaos:
        return []
    if isinstance(vaos, list):
        return vaos[i] if i < len(vaos) and isinstance(vaos[i], list) else []
    return vaos.get(i) or vaos.get(str(i)) or []


# --------------------------------------------------------------------------------------------------- paredes: preparação
def _tipo_parede(ctx, k):
    T = ctx.proj["tiposParede"].get(k)
    if not T:
        raise ValueError(f'Tipo de parede "{k}" não definido')
    s = ctx.P(T["montante"])
    tt = s["t"]
    guia = {"tipo": "U", "h": r1(s["h"] + 2 * tt), "b": T.get("guiaAba", 40), "t": tt}
    gk = f"U_{T['montante']}"
    ctx.proj["perfis"][gk] = guia
    return {"T": T, "s": s, "guia": guia, "gk": gk, "Dt": guia["h"], "D": s["h"], "b": s["b"], "tt": tt}


def _esp_camadas(ctx, lst):
    return sum(ctx.proj["placas"][c["placa"]]["esp"] for c in (lst or []))


def _resolve_z(ctx, z):
    if isinstance(z, (int, float)):
        return float(z)
    if isinstance(z, str) and z.startswith("auto:"):
        k = z[5:]
        if k in ctx.grupo_topo:
            return ctx.grupo_topo[k]
        if k in ctx.perim_topo:
            return ctx.perim_topo[k]
        raise ValueError(f'Referência de cota "{z}" desconhecida (piso ou perímetro ainda não calculado)')
    raise ValueError(f"Cota inválida: {z}")


def _expand_perimetro(ctx, per):
    pts = per["pontos"]
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0:
        _aviso(ctx, f"Perímetro {per['id']}: pontos em sentido horário — use sentido anti-horário (interior à esquerda).")
    z0 = _resolve_z(ctx, per.get("z0", 0))
    tp = _tipo_parede(ctx, per["tipo"])
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
        sC, eC = convexo(i), convexo((i + 1) % n)
        cross = abs(dirs[i][0] * dirs[(i + 1) % n][1] - dirs[i][1] * dirs[(i + 1) % n][0])
        if cross < 0.999:
            _aviso(ctx, f"{per['id']}-{i + 1}: canto não ortogonal — pormenor de canto a desenhar (o motor trata-o como 90°).")
        L = ln - tp["Dt"] if eC else ln + tp["Dt"]
        ctx.paredes.append({
            "id": f"{per['id']}-{i + 1}", "tipo": per["tipo"], "tp": tp, "A": list(pts[i]), "d": [dx, dy, 0], "n": [-dy, dx, 0],
            "y0": 0.0, "L": L, "z0": z0, "H": per["altura"], "vaos": [dict(v) for v in _vaos_do_lado(per.get("vaos"), i)],
            "perimetro": {"id": per["id"], "lado": ln, "sC": sC, "eC": eC}, "juncoes": [], "faces": None, "nivel": per.get("nivel", per["id"]),
        })
    ctx.perim_topo[per["id"]] = z0 + per["altura"]


def _faces(ctx, w):
    if w.get("faces"):
        return w["faces"]
    T = w["tp"]["T"]
    if w.get("perimetro"):
        A = {"nome": "interior", "camadas": [dict(c) for c in (T.get("interior") or [])]}
        B = {"nome": "exterior", "camadas": [dict(c) for c in (T.get("exterior") or [])]}
    else:
        A = {"nome": "face A", "camadas": [dict(c) for c in (T.get("faceA") or T.get("interior") or [])]}
        B = {"nome": "face B", "camadas": [dict(c) for c in (T.get("faceB") or T.get("exterior") or [])]}
    w["faces"] = {"A": A, "B": B}
    return w["faces"]


def _prep_parede_avulsa(ctx, w):
    tp = _tipo_parede(ctx, w["tipo"])
    z0 = _resolve_z(ctx, w.get("z0", 0))
    H = w.get("H", w.get("altura"))
    ax, bx = w["a"], w["b"]
    ln = math.hypot(bx[0] - ax[0], bx[1] - ax[1])
    if ln < 1:
        raise ValueError(f"Parede {w['id']}: comprimento nulo")
    d = [(bx[0] - ax[0]) / ln, (bx[1] - ax[1]) / ln, 0]
    n = [-d[1], d[0], 0]
    y0 = 0.0 if w.get("alinhamento") == "face" else -tp["Dt"] / 2
    ts, te = 0.0, ln
    hosts = []
    for which, Pp, Q in (("ini", ax, bx), ("fim", bx, ax)):
        for h in ctx.paredes:
            if h["z0"] + h["H"] <= z0 + EPS or h["z0"] >= z0 + H - EPS:
                continue
            rel = (Pp[0] - h["A"][0], Pp[1] - h["A"][1])
            px = rel[0] * h["d"][0] + rel[1] * h["d"][1]
            py = rel[0] * h["n"][0] + rel[1] * h["n"][1]
            if px < -1 or px > h["L"] + 1 or py < h["y0"] - 1 or py > h["y0"] + h["tp"]["Dt"] + 1:
                continue
            qy = (Q[0] - h["A"][0]) * h["n"][0] + (Q[1] - h["A"][1]) * h["n"][1]
            yc = h["y0"] + h["tp"]["Dt"] / 2
            fh = _faces(ctx, h)
            yT = h["y0"] + h["tp"]["Dt"] + _esp_camadas(ctx, fh["A"]["camadas"]) if qy > yc else h["y0"] - _esp_camadas(ctx, fh["B"]["camadas"])
            dn = d[0] * h["n"][0] + d[1] * h["n"][1]
            if abs(dn) < 1e-6:
                continue
            aY = (ax[0] - h["A"][0]) * h["n"][0] + (ax[1] - h["A"][1]) * h["n"][1]
            t = (yT - aY) / dn
            if which == "ini":
                ts = t
            else:
                te = t
            pj = (ax[0] + d[0] * t, ax[1] + d[1] * t)
            xj = (pj[0] - h["A"][0]) * h["d"][0] + (pj[1] - h["A"][1]) * h["d"][1]
            hosts.append((h, xj))
            break
    wall = {"id": w["id"], "tipo": w["tipo"], "tp": tp, "A": [ax[0] + d[0] * ts, ax[1] + d[1] * ts], "d": d, "n": n, "y0": y0,
            "L": te - ts, "z0": z0, "H": H, "vaos": [{**v, "x": v["x"] - ts} for v in (w.get("vaos") or [])],
            "perimetro": None, "juncoes": [], "faces": None, "origem": {"a": ax, "ts": ts}, "juncoesExt": 0, "nivel": w.get("nivel")}
    if wall["L"] < 200:
        _aviso(ctx, f"Parede {w['id']}: comprimento útil {r1(wall['L'])} mm após corte nas faces — verificar a geometria.")
    for h, xj in hosts:
        h["juncoes"].append({"x": xj, "largura": tp["Dt"], "parede": w["id"]})
        wall["juncoesExt"] += 1
    ctx.paredes.append(wall)


# ------------------------------------------------------------------------------------------------- paredes: estrutura
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
NX, NY, NZ = (-1, 0, 0), (0, -1, 0), (0, 0, -1)


def _estrutura_parede(ctx, w):
    tp = w["tp"]
    T, guia, gk, Dt, D, b, tt = tp["T"], tp["guia"], tp["gk"], tp["Dt"], tp["D"], tp["b"], tp["tt"]
    R = ctx.proj["regras"]
    pa = R["parafusoAco"]
    L, H = w["L"], w["H"]
    yc = w["y0"] + Dt / 2
    ref = w["id"]
    A, d, n, z00 = w["A"], w["d"], w["n"], w["z0"]

    def loc(x, y, z):
        return [A[0] + x * d[0] + y * n[0], A[1] + x * d[1] + y * n[1], z00 + z]

    def dr(v):
        x, y, z = v
        return [x * d[0] + y * n[0], x * d[1] + y * n[1], z]

    w["membros"], w["verticais"], w["horizontais"], w["aberturas"] = [], [], [], []

    def add(pref, tipo_peca, perfil, L_, o, u, v, ww, **extra):
        m = _membro(ctx, {"id": _next_id(ctx, ref, pref), "grupo": "Paredes", "ref": ref, "tipoPeca": tipo_peca, "perfil": perfil,
                          "L": L_, "o": loc(*o), "u": dr(u), "v": dr(v), "w": dr(ww), "nivel": w.get("nivel"), **extra})
        if not m:
            return None
        p = m["prof"]
        bb = member_bbox(list(o), list(u), list(v), list(ww), p["t"] if p["tipo"] == "F" else p["b"], p["h"], m["L"])
        m["elev"] = {"x0": bb["min"][0], "x1": bb["max"][0], "z0": bb["min"][2], "z1": bb["max"][2]}
        w["membros"].append(m)
        return m

    stud_l = H - 2 * tt - (T.get("folgaMontante") or 0)
    if stud_l <= 0:
        raise ValueError(f"Parede {ref}: altura insuficiente")

    def stud(pref, tipo_peca, x_web, dir_pos, z0, ln):
        m = add(pref, tipo_peca, T["montante"], ln, (x_web, yc - D / 2, z0), X if dir_pos else NX, Y, Z)
        if m:
            xl, xr = (x_web, x_web + b) if dir_pos else (x_web - b, x_web)
            w["verticais"].append({"x": (xl + xr) / 2, "xl": xl, "xr": xr, "z0": z0, "z1": z0 + ln, "fullH": ln >= stud_l - 1, "id": m["id"]})
            _add_par(ctx, pa, R["montanteGuia"], "Montante ↔ guia")
        return m

    # vãos
    vaos = []
    for v in w["vaos"]:
        porta = v.get("tipo") == "porta"
        x0 = float(v["x"])
        x1 = x0 + float(v["largura"])
        zs = 0.0 if porta else float(v.get("peitoril") or 0)
        zh = zs + float(v["altura"])
        vaos.append({**v, "porta": porta, "x0": x0, "x1": x1, "zs": zs, "zh": zh})
    vaos.sort(key=lambda v: v["x0"])
    ph = ctx.P(T["verga"]) if vaos else None
    for v in vaos:
        if v["x0"] < 2 * b - EPS or v["x1"] > L - 2 * b + EPS:
            _aviso(ctx, f"{ref}/{v.get('id')}: vão encostado ao extremo da parede (sem espaço para o montante de apoio) — pormenor a desenhar.")
        elif v["x0"] - 2 * b < b - EPS or v["x1"] + 2 * b > L - b + EPS:
            v["usaExtremo"] = True
        v["zTop"] = v["zh"] + 2 * tt + ph["h"]
        if v["zTop"] > H - tt + EPS:
            _aviso(ctx, f"{ref}/{v.get('id')}: a verga ({profile_name(ph)}) não cabe entre o topo do vão e a guia superior.")
        w["aberturas"].append({"id": v.get("id"), "x0": v["x0"], "x1": v["x1"], "z0": v["zs"], "z1": v["zh"], "porta": v["porta"],
                               "tipo": v.get("tipo"), "origem": v.get("origem")})
    for i in range(1, len(vaos)):
        gap = vaos[i]["x0"] - vaos[i - 1]["x1"]
        if gap < 2 * b - EPS:
            _aviso(ctx, f"{ref}: vãos {vaos[i - 1].get('id')} e {vaos[i].get('id')} com {r1(gap):g} mm entre si — menos de 2 montantes de apoio; "
                        "tratar como vão único com montante intermédio.")
        elif gap < 4 * b - EPS:
            vaos[i - 1]["partilhaDir"] = vaos[i]["partilhaEsq"] = True      # ombreira partilhada: só os dois montantes de apoio

    # guias
    w["guiasInf"] = subtract_intervals(0, L, [[v["x0"], v["x1"]] for v in vaos if v["porta"]])
    for a, c in w["guiasInf"]:
        add("G", "Guia inferior", gk, c - a, (a, yc - Dt / 2, 0), Z, Y, X)
        w["horizontais"].append({"z": guia["b"] / 2, "x0": a, "x1": c, "nome": "guia inferior"})
    add("G", "Guia superior", gk, L, (0, yc - Dt / 2, H), NZ, Y, X)
    w["horizontais"].append({"z": H - guia["b"] / 2, "x0": 0, "x1": L, "nome": "guia superior"})

    stud("M", "Montante de extremo", 0, True, tt, stud_l)
    stud("M", "Montante de extremo", L, False, tt, stud_l)
    ocup = [[0, b], [L - b, L]] + [[v["x0"] - 2 * b, v["x1"] + 2 * b] for v in vaos]

    extras = []
    if w.get("perimetro") and w["perimetro"]["sC"]:
        extras.append({"x": Dt + b / 2, "tipo": "Montante de canto"})
    for j in w["juncoes"]:
        extras.append({"x": j["x"], "tipo": "Montante de ligação", "parede": j["parede"]})

    sp = T["espacamento"]
    cripples = []
    k = 1
    while k * sp < L:
        xc = k * sp
        k += 1
        l, r = xc - b / 2, xc + b / 2
        if l < b - EPS or r > L - b + EPS:
            continue
        vv = next((v for v in vaos if l >= v["x0"] - EPS and r <= v["x1"] + EPS), None)
        if vv:
            cripples.append((xc, vv))
            continue
        if any(r > a + EPS and l < c - EPS for a, c in ocup):
            continue
        stud("M", "Montante", l, True, tt, stud_l)
        ocup.append([l, r])
    for e in extras:
        l, r = e["x"] - b / 2, e["x"] + b / 2
        if any(v["x0"] - 2 * b < e["x"] < v["x1"] + 2 * b for v in vaos):
            _aviso(ctx, f"{ref}: ligação/canto em x={r1(e['x'])} cai num vão — prever reforço manual.")
            continue
        if any(q["fullH"] and q["xl"] - 1 <= e["x"] <= q["xr"] + 1 for q in w["verticais"]):
            continue
        if any(r > a + EPS and l < c - EPS for a, c in ocup):
            _aviso(ctx, f"{ref}: {e['tipo'].lower()} em x={r1(e['x'])} colide com montante existente — verificar pormenor.")
            continue
        stud("M", e["tipo"], l, True, tt, stud_l)
        ocup.append([l, r])

    for i, v in enumerate(vaos):
        jack_l = v["zh"] - tt
        # montante rei: dispensado quando o vão encosta ao montante de extremo ou partilha a ombreira com o vão vizinho
        rei_esq = v["x0"] - 2 * b >= b - EPS and not v.get("partilhaEsq")
        rei_dir = v["x1"] + 2 * b <= L - b + EPS and not v.get("partilhaDir")
        if rei_esq:
            stud("M", "Montante rei", v["x0"] - 2 * b, True, tt, stud_l)
        if v["x0"] >= b + b - EPS:
            stud("M", "Montante de apoio", v["x0"], False, tt, jack_l)
        if v["x1"] <= L - 2 * b + EPS:
            stud("M", "Montante de apoio", v["x1"], True, tt, jack_l)
        if rei_dir:
            stud("M", "Montante rei", v["x1"] + 2 * b, False, tt, stud_l)
        n_cx = int(rei_esq) + int(rei_dir)
        _add_par(ctx, pa, n_cx * 2 * (math.floor(jack_l / R["caixaoPasso"] + EPS) + 1), "Montante rei ↔ apoio (caixão)")
        xh, Lh = v["x0"] - b, v["x1"] - v["x0"] + 2 * b
        add("V", "Guia de verga (inferior)", gk, Lh, (xh, yc - Dt / 2, v["zh"]), Z, Y, X)
        add("V", "Verga", T["verga"], Lh, (xh, yc - D / 2, v["zh"] + tt), Y, Z, X)
        add("V", "Verga", T["verga"], Lh, (xh, yc + D / 2, v["zh"] + tt), NY, Z, X)
        add("V", "Guia de verga (superior)", gk, Lh, (xh, yc - Dt / 2, v["zh"] + tt + ph["h"]), Z, Y, X)
        _add_par(ctx, pa, 2 * 2 * R["vergaApoio"], "Verga ↔ montantes")
        _add_par(ctx, pa, 2 * 2 * (math.floor(Lh / R["vergaGuiaPasso"] + EPS) + 1), "Guias de verga ↔ perfis C")
        w["horizontais"].append({"z": v["zh"] + 20, "x0": xh, "x1": xh + Lh, "nome": "verga"})
        w["horizontais"].append({"z": v["zTop"] - 20, "x0": xh, "x1": xh + Lh, "nome": "verga"})
        if not v["porta"]:
            add("P", "Guia de peitoril", gk, v["x1"] - v["x0"], (v["x0"], yc - Dt / 2, v["zs"]), NZ, Y, X)
            _add_par(ctx, pa, 2 * R["peitorilExtremo"], "Peitoril ↔ montantes de apoio")
            w["horizontais"].append({"z": v["zs"] - guia["b"] / 2, "x0": v["x0"], "x1": v["x1"], "nome": "peitoril"})
        for xc, cv in cripples:
            if cv is not v:
                continue
            la = H - tt - v["zTop"]
            if la > 30:
                stud("M", "Montante curto (sobre verga)", xc - b / 2, True, v["zTop"], la)
            if not v["porta"]:
                lb = v["zs"] - 2 * tt
                if lb > 30:
                    stud("M", "Montante curto (sob peitoril)", xc - b / 2, True, tt, lb)

    if w.get("perimetro") and w["perimetro"]["eC"]:
        w["verticais"].append({"x": L + Dt / 2, "xl": L, "xr": L + Dt, "z0": 0, "z1": H, "fullH": True, "externo": True, "face": "B"})

    # bloqueadores
    alturas = []
    nb = T.get("bloqueadores") or 0
    for k in range(1, nb + 1):
        alturas.append({"z": H * k / (nb + 1), "junta": False})
    if T.get("bloqueadorAuto"):
        fc = _faces(ctx, w)
        for c in fc["B"]["camadas"] + fc["A"]["camadas"]:
            if "OSB" not in c["placa"].upper():
                continue
            ph2 = ctx.proj["placas"][c["placa"]]["h"]
            z = ph2
            while z < H - 50:
                if not any(abs(a["z"] - z) < 100 for a in alturas):
                    alturas.append({"z": z, "junta": True})
                z += ph2
    w["alturasBloq"] = alturas
    cheios = sorted([q for q in w["verticais"] if q["fullH"] and not q.get("externo")], key=lambda q: q["xl"])
    for al in alturas:
        for i in range(len(cheios) - 1):
            a, c = cheios[i]["xr"], cheios[i + 1]["xl"]
            if c - a < 150:                      # vão estreito (canto, ligação): sem bloqueador
                continue
            if any(a < v["x1"] + 2 * b and c > v["x0"] - 2 * b for v in vaos):
                continue
            add("B", "Bloqueador (junta de placa)" if al["junta"] else "Bloqueador", gk, c - a, (a, yc - Dt / 2, al["z"] + tt / 2), NZ, Y, X)
            _add_par(ctx, pa, 2 * R["bloqueadorExtremo"], "Bloqueadores")
        if al["junta"]:
            w["horizontais"].append({"z": al["z"], "x0": 0, "x1": L, "nome": "bloqueador de junta"})

    # contraventamento em fita (X) nos painéis de extremo
    if T.get("contraventamento") == "fita":
        fp = ctx.P(T["fita"])
        paineis = []
        p_ini = next((q for q in cheios if q["xr"] >= 1100), None)
        if p_ini:
            paineis.append((0, p_ini["xr"]))
        p_fim = next((q for q in reversed(cheios) if L - q["xl"] >= 1100), None)
        if p_fim:
            paineis.append((p_fim["xl"], L))
        for a, c in paineis:
            if any(v["x1"] + 2 * b > a and v["x0"] - 2 * b < c for v in vaos):
                _aviso(ctx, f"{ref}: painel de contraventamento [{r1(a)}–{r1(c)}] atravessado por vão — reposicionar.")
                continue
            cruz = len([q for q in cheios if q["xl"] > min(a, c) + 1 and q["xr"] < max(a, c) - 1])
            for face in (-1, 1):
                yf = yc - D / 2 - fp["t"] if face < 0 else yc + D / 2
                for x_a, x_b in ((a, c), (c, a)):
                    dx = x_b - x_a
                    ln = math.hypot(dx, H)
                    ww = (dx / ln, 0, H / ln)
                    vv = (-ww[2], 0, ww[0])
                    add("F", "Fita de contraventamento", T["fita"], ln, (x_a - vv[0] * fp["h"] / 2, yf, -vv[2] * fp["h"] / 2), Y, vv, ww)
                    _add_par(ctx, pa, 2 * R["fitaExtremo"] + cruz * R["fitaCruzamento"], "Fitas de contraventamento")

    # ancoragens e hold-downs
    an = T.get("ancoragem")
    if an:
        for a, c in w["guiasInf"]:
            ln = c - a
            nn = 1 if ln <= 2 * an["extremo"] else math.ceil((ln - 2 * an["extremo"]) / an["passoMax"] - EPS) + 1
            if w["z0"] < 1:
                _add_anc(ctx, an["nome"], nn, f"Guia inferior (extremos a {an['extremo']} mm, passo ≤ {an['passoMax']} mm)")
            else:
                _add_par(ctx, "Parafuso estrutural guia ↔ piso (ver cálculo)", nn, "Guia inferior sobre piso")
    hd = T.get("holdDowns")
    if hd:
        nn = (2 if hd.get("extremos") else 0) + (2 * len(vaos) if hd.get("vaos") else 0)
        if nn:
            _add_anc(ctx, "Hold-down (conector anti-levantamento)", nn, "Extremos de parede e vãos")
            if hd.get("parafusos"):
                _add_par(ctx, pa, nn * hd["parafusos"], "Hold-downs ↔ montantes")
    n_lig = (1 if w.get("perimetro") and w["perimetro"]["eC"] else 0) + (w.get("juncoesExt") or 0)
    if n_lig and R.get("ligacaoPasso"):
        _add_par(ctx, pa, n_lig * (math.floor(H / R["ligacaoPasso"] + EPS) + 1), "Ligação entre paredes (cantos e T)")


# ------------------------------------------------------------------------------------------------------- revestimentos
def _colunas(start, end, W, sp, first_max=None, apoios=None):
    cols = []
    cur, first = start, True
    while cur < end - EPS:
        lim = cur + (first_max if first and first_max else W)
        ap = [x for x in (apoios or []) if cur + 100 < x <= lim + EPS]
        if lim >= end - EPS:
            nxt = end
        elif ap:
            nxt = max(ap)
        elif sp:
            cand = math.floor((lim + EPS) / sp) * sp
            nxt = cand if cand > cur + EPS else lim
        else:
            nxt = lim
        cols.append([cur, nxt])
        cur, first = nxt, False
    return cols


def _contar_parafusos_placa(cell, voids, vert, horz, pl, sp_over, banzo):
    bordo = (sp_over or {}).get("bordo") or pl["bordo"]
    inter = (sp_over or {}).get("interior") or pl["interior"]
    n = 0
    usadas = []
    for q in vert:
        if q["x"] < cell["x0"] - 1 or q["x"] > cell["x1"] + 1:
            continue
        z0, z1 = max(q["z0"], cell["z0"]), min(q["z1"], cell["z1"])
        if z1 - z0 < 10:
            continue
        cuts = [[v["z0"], v["z1"]] for v in voids if v["x0"] + 1 < q["x"] < v["x1"] - 1]
        borda = abs(q["x"] - cell["x0"]) <= banzo or abs(q["x"] - cell["x1"]) <= banzo
        sp = bordo if borda else inter
        for a, c in subtract_intervals(z0, z1, cuts):
            if c - a >= 10:
                n += math.floor((c - a) / sp + EPS) + 1
        usadas.append(q)
    for hl in horz:
        if hl["z"] < cell["z0"] - 1 or hl["z"] > cell["z1"] + 1:
            continue
        x0, x1 = max(hl["x0"], cell["x0"]), min(hl["x1"], cell["x1"])
        if x1 - x0 < 10:
            continue
        cuts = [[v["x0"], v["x1"]] for v in voids if v["z0"] + 1 < hl["z"] < v["z1"] - 1]
        for a, c in subtract_intervals(x0, x1, cuts):
            cobre = [q for q in usadas if q["z0"] - 1 <= hl["z"] <= q["z1"] + 1]
            pts = sorted([a] + [q["x"] for q in cobre if a + 1 < q["x"] < c - 1] + [c])

            def on_v(x):
                return any(abs(q["x"] - x) <= 1 + banzo / 2 for q in cobre)

            if not on_v(a):
                n += 1
            if not on_v(c) and c - a > 10:
                n += 1
            for i in range(len(pts) - 1):
                g = pts[i + 1] - pts[i]
                if g > EPS:
                    n += max(0, math.ceil(g / bordo - EPS) - 1)
    return n


def _revestimentos_parede(ctx, w):
    tp = w["tp"]
    T, Dt, b = tp["T"], tp["Dt"], tp["b"]
    fc = _faces(ctx, w)
    sp = T["espacamento"]
    H0 = w["H"]
    per = w.get("perimetro")
    faixa = 0.0
    if per:
        mid = (w["A"][0] + w["d"][0] * w["L"] / 2, w["A"][1] + w["d"][1] * w["L"] / 2)
        f = next((f for f in ctx.pisos if abs(f["z"] - (w["z0"] + H0)) < 1 and f["x0"] - 1 <= mid[0] <= f["x1"] + 1
                  and f["y0"] - 1 <= mid[1] <= f["y1"] + 1), None)
        if f:
            faixa = f["topo"] - f["z"]
            w["horizontais"].append({"z": H0 + 30, "x0": 0, "x1": w["L"], "nome": "bordadura do piso", "soB": True})
            w["horizontais"].append({"z": H0 + f["rimH"] - 30, "x0": 0, "x1": w["L"], "nome": "bordadura do piso", "soB": True})
    w["faixaPiso"] = faixa
    w["faceInfo"] = []
    for lado, face in (("B", fc["B"]), ("A", fc["A"])):
        acc = 0.0
        H = H0 + faixa if lado == "B" and per else H0
        ncam = len(face["camadas"])
        for k, cam in enumerate(face["camadas"]):
            pl = ctx.proj["placas"].get(cam["placa"])
            if not pl:
                raise ValueError(f'Placa "{cam["placa"]}" não definida')
            o = acc + pl["esp"] / 2
            xs, xe = 0.0, w["L"]
            if per:
                if lado == "B":
                    xs = -o if per["sC"] else o
                    xe = per["lado"] + (o if per["eC"] else -o)
                else:
                    oi = Dt + o
                    xs = oi if per["sC"] else -oi
                    xe = per["lado"] + (-oi if per["eC"] else oi)
            y_plane = w["y0"] - acc - pl["esp"] if lado == "B" else w["y0"] + Dt + acc
            apoios = sorted({q["x"] for q in w["verticais"] if q["fullH"] and (not q.get("externo") or q.get("face") == lado)})
            cols = _colunas(xs, xe, pl["w"], sp, max(pl["w"] - sp, sp) if k % 2 == 1 else None, apoios)
            rows = []
            z = 0.0
            while z < H - EPS:
                rows.append([z, min(z + pl["h"], H)])
                z += pl["h"]
            voids = [{"x0": a["x0"], "x1": a["x1"], "z0": a["z0"], "z1": a["z1"]} for a in w["aberturas"]]
            ultima = k == ncam - 1
            gesso = cam["placa"].upper().startswith("GC")
            if ncam > 1 and not ultima and gesso:
                espac = {"bordo": cam.get("passo") or 750, "interior": cam.get("passo") or 750}
            else:
                espac = {"bordo": cam["passo"], "interior": cam["passo"]} if cam.get("passo") else None
            parafuso = cam.get("parafuso") or (pl["parafuso"].replace("×25", "×35") if k > 0 and gesso else pl["parafuso"])
            vert = [q for q in w["verticais"] if not q.get("externo") or q.get("face") == lado]
            horz = [h for h in w["horizontais"] if not h.get("soB") or lado == "B"]
            for x0, x1 in cols:
                for z0, z1 in rows:
                    cell = {"x0": x0, "x1": x1, "z0": z0, "z1": z1}
                    pecas = subtract_rects(cell, voids)
                    area = sum(rect_area(r) for r in pecas)
                    if area < 1000:
                        continue
                    npar = _contar_parafusos_placa(cell, voids, vert, horz, pl, espac, b)
                    _add_par(ctx, parafuso, npar, f"Placas {pl['nome']}")
                    bx = (min(r["x0"] for r in pecas), max(r["x1"] for r in pecas), min(r["z0"] for r in pecas), max(r["z1"] for r in pecas))
                    _pack(ctx, cam["placa"], pl["nome"], pl["w"], pl["h"], pl.get("rodar", True),
                          {"w": bx[1] - bx[0], "h": bx[3] - bx[2], "ref": f"{w['id']} {face['nome']}"})
                    ctx.placas.append({"ref": w["id"], "grupo": "Paredes", "face": face["nome"], "camada": k + 1, "placa": cam["placa"],
                                       "nome": pl["nome"], "cell": cell, "pecas": pecas, "area": area, "bruta": pl["w"] * pl["h"], "parafusos": npar,
                                       "plano": {"tipo": "parede", "A": w["A"], "d": w["d"], "n": w["n"], "z0": w["z0"], "y": y_plane, "esp": pl["esp"]}})
                    for xe2 in (x0, x1):
                        if abs(xe2 - xs) < EPS or abs(xe2 - xe) < EPS:
                            continue
                        segs = subtract_intervals(z0, z1, [[v["z0"], v["z1"]] for v in voids if v["x0"] < xe2 < v["x1"]])
                        if not segs:
                            continue
                        cob = [[q["z0"] - 60, q["z1"] + 60] for q in w["verticais"] if q["xl"] - 1 <= xe2 <= q["xr"] + 1]
                        cob += [[a["z1"] - 60, a["z1"] + 400] for a in w["aberturas"] if a["x0"] - 2 * b <= xe2 <= a["x1"] + 2 * b]
                        if lado == "B" and faixa:
                            cob.append([H0 - 60, H0 + faixa + 60])
                        falta = [s for p_, q_ in segs for s in subtract_intervals(max(p_, tp["tt"] + 40), min(q_, H - tp["tt"] - 40), cob)]
                        if any(q_ - p_ > 1 for p_, q_ in falta):
                            _aviso(ctx, f"{w['id']} ({face['nome']}, {pl['nome']}): junta vertical em x={r1(xe2)} sem montante de apoio.")
            if ultima and gesso:
                lj = 0.0
                for i in range(len(cols) - 1):
                    x = cols[i][1]
                    lj += sum(q - p_ for p_, q in subtract_intervals(0, H, [[v["z0"], v["z1"]] for v in voids if v["x0"] < x < v["x1"]]))
                for j in range(1, len(rows)):
                    z = rows[j][0]
                    lj += sum(q - p_ for p_, q in subtract_intervals(xs, xe, [[v["x0"], v["x1"]] for v in voids if v["z0"] < z < v["z1"]]))
                ctx.extras.append({"cat": "Acabamento gesso", "item": "Fita + massa de juntas (juntas planas entre placas)", "un": "m", "qtd": lj / 1000,
                                   "ref": w["id"]})
            w["faceInfo"].append({"lado": lado, "nome": face["nome"], "placa": cam["placa"], "xs": xs, "xe": xe, "yPlane": y_plane,
                                  "cols": len(cols), "rows": len(rows)})
            acc += pl["esp"]
        if lado == "B" and per and T.get("etics"):
            _etics(ctx, w, acc, H)
        if lado == "B" and per and T.get("membrana"):
            m = T["membrana"]
            o = acc
            xs, xe = (-o if per["sC"] else o), per["lado"] + (o if per["eC"] else -o)
            faixas = math.ceil(H / (m["larguraRolo"] - m["sobreposicao"]) - EPS)
            area = (xe - xs) * H - sum((a["x1"] - a["x0"]) * (a["z1"] - a["z0"]) for a in w["aberturas"])
            ctx.extras.append({"cat": "Membranas", "item": f"{m['nome']} — área líquida", "un": "m²", "qtd": area / 1e6, "ref": w["id"]})
            ctx.extras.append({"cat": "Membranas", "item": f"{m['nome']} — comprimento de rolo", "un": "m", "qtd": faixas * (xe - xs) / 1000,
                               "ref": w["id"], "rolo": m["comprimentoRolo"]})
    if T.get("isolamento"):
        area = w["L"] * (H0 - 2 * tp["tt"]) - sum((a["x1"] - a["x0"]) * (a["z1"] - a["z0"]) for a in w["aberturas"])
        iso = T["isolamento"]
        ctx.extras.append({"cat": "Isolamento", "item": f"{iso['nome']} {iso['esp']:g} mm (caixa-de-ar)", "un": "m²", "qtd": area / 1e6,
                           "ref": w["id"], "m2emb": iso.get("m2PorEmbalagem"), "esp": iso["esp"]})
    for a in w["aberturas"]:
        per_ = 2 * (a["z1"] - a["z0"]) + (a["x1"] - a["x0"]) * (1 if a["porta"] else 2)
        ctx.extras.append({"cat": "Vãos", "item": f"Perímetro de vão ({'porta' if a['porta'] else 'janela'}) — remates/selagem", "un": "m",
                           "qtd": per_ / 1000, "ref": f"{w['id']}/{a.get('id')}"})


def _etics(ctx, w, acc_osb, H):
    E = w["tp"]["T"]["etics"]
    per = w["perimetro"]
    o = acc_osb + E["esp"] / 2
    xs, xe = (-o if per["sC"] else o), per["lado"] + (o if per["eC"] else -o)
    voids = [{"x0": a["x0"], "x1": a["x1"], "z0": a["z0"], "z1": a["z1"]} for a in w["aberturas"]]
    n, net, pecas = 0, 0.0, []
    z, row = 0.0, 0
    while z < H - EPS:
        off = E["placaW"] / 2 if row % 2 else 0
        x = xs - off
        while x < xe - EPS:
            cell = {"x0": max(x, xs), "x1": min(x + E["placaW"], xe), "z0": z, "z1": min(z + E["placaH"], H)}
            x += E["placaW"]
            if cell["x1"] - cell["x0"] < 1:
                continue
            pcs = subtract_rects(cell, voids)
            a = sum(rect_area(r) for r in pcs)
            if a < 1000:
                continue
            n += 1
            net += a
            pecas += pcs
            bx = (min(r["x0"] for r in pcs), max(r["x1"] for r in pcs), min(r["z0"] for r in pcs), max(r["z1"] for r in pcs))
            _pack(ctx, "ETICS|" + E["nome"] + str(E["esp"]), f"{E['nome']} {E['esp']:g} mm", E["placaW"], E["placaH"], True,
                  {"w": bx[1] - bx[0], "h": bx[3] - bx[2], "ref": w["id"]})
        z += E["placaH"]
        row += 1
    ctx.placas.append({"ref": w["id"], "grupo": "ETICS", "face": "exterior", "camada": 0, "placa": "ETICS", "nome": f"{E['nome']} {E['esp']:g} mm",
                       "cell": {"x0": xs, "x1": xe, "z0": 0, "z1": H}, "pecas": pecas, "area": net, "bruta": 0, "parafusos": 0,
                       "plano": {"tipo": "parede", "A": w["A"], "d": w["d"], "n": w["n"], "z0": w["z0"], "y": w["y0"] - acc_osb - E["esp"], "esp": E["esp"]}})
    ctx.extras.append({"cat": "ETICS", "item": "Área líquida ETICS", "un": "m²", "qtd": net / 1e6, "ref": w["id"]})
    if E.get("bucha"):
        ctx.extras.append({"cat": "ETICS", "item": "Buchas de fixação ETICS", "un": "un", "qtd": n * E["bucha"], "ref": w["id"]})
    if E.get("cola"):
        ctx.extras.append({"cat": "ETICS", "item": "Argamassa de colagem + barramento", "un": "kg", "qtd": net / 1e6 * E["cola"], "ref": w["id"]})
    if E.get("rede"):
        faixas = math.ceil(H / (E["rede"]["largura"] - E["rede"]["sobreposicao"]) - EPS)
        ctx.extras.append({"cat": "ETICS", "item": "Rede de fibra de vidro", "un": "m", "qtd": faixas * (xe - xs) / 1000, "ref": w["id"],
                           "rolo": E["rede"]["rolo"]})
    jan = sum(1 for a in w["aberturas"] if not a["porta"])
    por = sum(1 for a in w["aberturas"] if a["porta"])
    if jan + por:
        ctx.extras.append({"cat": "ETICS", "item": "Reforços diagonais de rede nos cantos de vãos", "un": "un", "qtd": 4 * jan + 2 * por, "ref": w["id"]})
    cant = (H if per["eC"] else 0) + sum(2 * (a["z1"] - a["z0"]) + (a["x1"] - a["x0"]) * (1 if a["porta"] else 2) for a in w["aberturas"])
    ctx.extras.append({"cat": "ETICS", "item": "Cantoneira com rede (esquinas e contornos de vãos)", "un": "m", "qtd": cant / 1000, "ref": w["id"]})
    if w["z0"] < 1:
        ctx.extras.append({"cat": "ETICS", "item": "Perfil de arranque ETICS", "un": "m",
                           "qtd": (xe - xs - sum(a["x1"] - a["x0"] for a in w["aberturas"] if a["porta"])) / 1000, "ref": w["id"]})


# ------------------------------------------------------------------------------------------------------------------ pisos
def _prep_piso(ctx, f):
    vg = ctx.P(f["viga"])
    z = _resolve_z(ctx, f["z"])
    rim_h = vg["h"] + 2 * vg["t"]
    pl = ctx.proj["placas"].get(f.get("placa"))
    topo = z + rim_h + (pl["esp"] if pl else 0)
    if f.get("grupo"):
        ctx.grupo_topo[f["grupo"]] = max(ctx.grupo_topo.get(f["grupo"], -math.inf), topo)
    ctx.grupo_topo[f["id"]] = topo
    return {**f, "z": z, "vg": vg, "rimH": rim_h, "topo": topo}


def _estrutura_piso(ctx, f):
    R = ctx.proj["regras"]
    pa = R["parafusoAco"]
    vg = f["vg"]
    t, jb = vg["t"], vg["b"]
    span_y = f.get("vao", "y") == "y"
    S = (f["y1"] - f["y0"]) if span_y else (f["x1"] - f["x0"])
    Pl = (f["x1"] - f["x0"]) if span_y else (f["y1"] - f["y0"])
    Pd = (1, 0, 0) if span_y else (0, 1, 0)
    Sd = (0, 1, 0) if span_y else (1, 0, 0)

    def loc(p, s, z):
        return [f["x0"] + p * Pd[0] + s * Sd[0], f["y0"] + p * Pd[1] + s * Sd[1], f["z"] + z]

    def dr(v):
        p, s, z = v
        return [p * Pd[0] + s * Sd[0], p * Pd[1] + s * Sd[1], z]

    rim_k = f"U_{f['viga']}"
    ctx.proj["perfis"][rim_k] = {"tipo": "U", "h": r1(f["rimH"]), "b": f.get("rimAba", 50), "t": t}
    ref = f["id"]
    vmax = f.get("vaoMax")
    if vmax and S > vmax + EPS:
        _aviso(ctx, f"{ref}: vão das vigas {r1(S)} mm > {r1(vmax)} mm admitido para {profile_name(vg)} — prever apoio intermédio ou perfil maior.")

    def add(pref, tipo_peca, perfil, L, o, u, v, w):
        return _membro(ctx, {"id": _next_id(ctx, ref, pref), "grupo": "Pisos", "ref": ref, "tipoPeca": tipo_peca, "perfil": perfil, "L": L,
                             "o": loc(*o), "u": dr(u), "v": dr(v), "w": dr(w), "nivel": f.get("grupo")})

    add("R", "Guia de bordadura (rim)", rim_k, Pl, (0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))
    add("R", "Guia de bordadura (rim)", rim_k, Pl, (0, S, 0), (0, -1, 0), (0, 0, 1), (1, 0, 0))
    jl = S - 2 * t
    pos = [(0.0, True)]
    k = 1
    while k * f["espacamento"] < Pl:
        c = k * f["espacamento"]
        k += 1
        if c - jb / 2 < jb or c + jb / 2 > Pl - jb:
            continue
        pos.append((c - jb / 2, True))
    pos.append((Pl, False))
    linhas = []
    for web, dpos in pos:
        add("V", "Viga de piso", f["viga"], jl, (web, t, t), (1, 0, 0) if dpos else (-1, 0, 0), (0, 0, 1), (0, 1, 0))
        xl = web if dpos else web - jb
        linhas.append({"x": xl + jb / 2, "xl": xl, "xr": xl + jb, "z0": 0, "z1": S})
    _add_par(ctx, pa, len(pos) * 2 * R["vigaRim"], "Vigas de piso ↔ guia de bordadura")
    _add_par(ctx, pa, len(pos) * 2 * (R.get("pisoParede") or 0), "Piso ↔ guia superior das paredes")
    nr = max(0, math.ceil(S / f["travamentoMax"] - EPS) - 1) if f.get("travamentoMax") else 0
    srt = sorted(linhas, key=lambda q: q["xl"])
    for r in range(1, nr + 1):
        s = S * r / (nr + 1)
        for i in range(len(srt) - 1):
            a, c = srt[i]["xr"], srt[i + 1]["xl"]
            if c - a < 20:
                continue
            add("B", "Bloqueador de piso", f["viga"], c - a, (a, s - jb / 2, t), (0, 1, 0), (0, 0, 1), (1, 0, 0))
            _add_par(ctx, pa, 2 * R["bloqueadorExtremo"], "Bloqueadores de piso")
    pl = ctx.proj["placas"].get(f.get("placa"))
    if pl:
        horz = [{"z": t + 10, "x0": 0, "x1": Pl}, {"z": S - t - 10, "x0": 0, "x1": Pl}]
        s0, row = 0.0, 0
        while s0 < S - EPS:
            half = math.floor((pl["w"] / 2 + EPS) / f["espacamento"]) * f["espacamento"] if row % 2 else None
            for x0, x1 in _colunas(0, Pl, pl["w"], f["espacamento"], half):
                cell = {"x0": x0, "x1": x1, "z0": s0, "z1": min(s0 + pl["h"], S)}
                npar = _contar_parafusos_placa(cell, [], linhas, horz, pl, None, jb)
                _add_par(ctx, pl["parafuso"], npar, f"Placas {pl['nome']}")
                _pack(ctx, f["placa"], pl["nome"], pl["w"], pl["h"], pl.get("rodar", False), {"w": x1 - x0, "h": cell["z1"] - cell["z0"], "ref": ref})
                ctx.placas.append({"ref": ref, "grupo": "Pisos", "face": "pavimento", "camada": 1, "placa": f["placa"], "nome": pl["nome"], "cell": cell,
                                   "pecas": [cell], "area": rect_area(cell), "bruta": pl["w"] * pl["h"], "parafusos": npar,
                                   "plano": {"tipo": "piso", "O": [f["x0"], f["y0"]], "Pd": list(Pd), "Sd": list(Sd), "z": f["z"] + f["rimH"], "esp": pl["esp"]}})
            s0 += pl["h"]
            row += 1


# ----------------------------------------------------------------------------------------------- coberturas (asnas Fink)
def _estrutura_cobertura(ctx, c):
    R = ctx.proj["regras"]
    pa = R["parafusoAco"]
    zr = _resolve_z(ctx, c["z"])
    bc, dg = ctx.P(c["banzo"]), ctx.P(c["diagonal"])
    hc, hw, b = bc["h"], dg["h"], bc["b"]
    along_x = c.get("cumeeira", "x") == "x"
    Lr = (c["x1"] - c["x0"]) if along_x else (c["y1"] - c["y0"])
    S = (c["y1"] - c["y0"]) if along_x else (c["x1"] - c["x0"])
    a = math.radians(c["inclinacao"])
    ta, ca, sa = math.tan(a), math.cos(a), math.sin(a)
    ov = c.get("beiral") or 0
    zb = hc / 2
    Rp = (S / 2, zb + S / 2 * ta)
    EL, ER = (-ov, zb - ov * ta), (S + ov, zb - ov * ta)
    dL, dR = (ca, sa), (ca, -sa)

    def z_tc(s):
        return zb + s * ta if s <= S / 2 else zb + (S - s) * ta

    ref = c["id"]
    Rd = (1, 0, 0) if along_x else (0, 1, 0)
    Sd = (0, 1, 0) if along_x else (1, 0, 0)

    def g(r, s, z):
        return [c["x0"] + r * Rd[0] + s * Sd[0], c["y0"] + r * Rd[1] + s * Sd[1], zr + z]

    def gd(r, s, z):
        return [r * Rd[0] + s * Sd[0], r * Rd[1] + s * Sd[1], z]

    def plano(A, B, h):
        L = math.hypot(B[0] - A[0], B[1] - A[1])
        w = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
        v = (-w[1], w[0])
        return L, w, v, (A[0] - v[0] * h / 2, A[1] - v[1] * h / 2)

    folga = c.get("folga", 5)

    def extensao(Aw, dd, Q, m):
        p = (-dd[1], dd[0])
        pm = p[0] * m[0] + p[1] * m[1]
        dm = dd[0] * m[0] + dd[1] * m[1]
        base = (Q[0] - Aw[0]) * m[0] + (Q[1] - Aw[1]) * m[1] - folga
        return min((base - pm * hw / 2) / dm, (base + pm * hw / 2) / dm)

    B1, B2 = (S / 3, zb), (2 * S / 3, zb)
    T1, T2 = (S / 4, z_tc(S / 4)), (3 * S / 4, z_tc(3 * S / 4))
    webs = []
    for A_, B_, lado in ((B1, T1, "L"), (B1, Rp, "L"), (B2, Rp, "R"), (B2, T2, "R")):
        L0 = math.hypot(B_[0] - A_[0], B_[1] - A_[1])
        dd = ((B_[0] - A_[0]) / L0, (B_[1] - A_[1]) / L0)
        n_up = (-sa, ca) if lado == "L" else (sa, ca)
        E_ = EL if lado == "L" else ER
        t_top = extensao(A_, dd, (E_[0] + n_up[0] * hc / 2, E_[1] + n_up[1] * hc / 2), n_up)
        if B_ is Rp:
            n_o = (sa, ca) if lado == "L" else (-sa, ca)
            E_o = ER if lado == "L" else EL
            t_top = min(t_top, extensao(A_, dd, (E_o[0] + n_o[0] * hc / 2, E_o[1] + n_o[1] * hc / 2), n_o))
        t_bot = extensao(A_, (-dd[0], -dd[1]), (0, zb - hc / 2), (0, -1))
        webs.append({"start": (A_[0] - dd[0] * t_bot, A_[1] - dd[1] * t_bot), "d": dd, "L": t_top + t_bot})

    banzo_sup = (S / 2 + ov) / ca
    corte = hc * ta
    pos = [b]
    k = 1
    while k * c["espacamento"] < Lr - b:
        x = k * c["espacamento"]
        k += 1
        if 2 * b < x < Lr - 2 * b:
            pos.append(x)
    pos.append(Lr - b)
    ctx.coberturas.append({"id": ref, "n": len(pos), "S": S, "Lr": Lr, "inclinacao": c["inclinacao"], "beiral": ov})

    linhas = []
    for rc in pos:
        tag = _next_id(ctx, ref, "A")

        def add_in(tipo_peca, perfil, L, o2, w2, v2, u_sign, nota=None):
            kk = tag + tipo_peca
            ctx.cont[kk] = ctx.cont.get(kk, 0) + 1
            return _membro(ctx, {"id": f"{tag}.{tipo_peca[0]}{ctx.cont[kk]}", "grupo": "Cobertura", "ref": ref, "asna": tag, "tipoPeca": tipo_peca,
                                 "perfil": perfil, "L": L, "nota": nota, "o": g(rc, o2[0], o2[1]), "u": gd(u_sign, 0, 0),
                                 "v": gd(0, v2[0], v2[1]), "w": gd(0, w2[0], w2[1]), "nivel": "COB"})

        L_, w_, v_, o_ = plano((0, zb), (S, zb), hc)
        add_in("Banzo inferior", c["banzo"], L_, o_, w_, v_, 1)
        for A_, B_ in ((EL, Rp), (ER, Rp)):
            L_, w_, v_, o_ = plano(A_, B_, hc)
            add_in("Banzo superior", c["banzo"], L_, o_, w_, v_, 1, f"Cortes a prumo nos extremos; barra mínima {r1(L_ + corte):g} mm")
        for wb in webs:
            B_ = (wb["start"][0] + wb["d"][0] * wb["L"], wb["start"][1] + wb["d"][1] * wb["L"])
            L_, w_, v_, o_ = plano(wb["start"], B_, hw)
            add_in("Diagonal", c["diagonal"], L_, o_, w_, v_, -1, "Corte reto; dorso-com-dorso no banzo")
        _add_par(ctx, pa, len(webs) * 2 * R["asnaNoBanzo"] + 2 * R["asnaApoio"] + R["asnaCumeeira"], "Nós das asnas")
        _add_par(ctx, pa, 2 * R["asnaParede"], "Asnas ↔ guia superior")
        linhas.append({"x": rc, "xl": rc - b, "xr": rc + b, "z0": -1e9, "z1": 1e9})

    pl = ctx.proj["placas"].get(c.get("placa"))
    vert_l = banzo_sup + hc / 2 * ta
    area_v = Lr * vert_l
    for lado in ("L", "R"):
        if not pl:
            continue
        v0 = 0.0
        while v0 < vert_l - EPS:
            for x0, x1 in _colunas(0, Lr, pl["w"], c["espacamento"]):
                cell = {"x0": x0, "x1": x1, "z0": v0, "z1": min(v0 + pl["h"], vert_l)}
                lin = [{**q, "z0": 0, "z1": vert_l} for q in linhas]
                npar = _contar_parafusos_placa(cell, [], lin, [], pl, None, b)
                _add_par(ctx, pl["parafuso"], npar, f"Placas {pl['nome']}")
                _pack(ctx, c["placa"], pl["nome"], pl["w"], pl["h"], pl.get("rodar", True), {"w": x1 - x0, "h": cell["z1"] - cell["z0"], "ref": ref})
                E_ = EL if lado == "L" else ER
                n_up = (-sa, ca) if lado == "L" else (sa, ca)
                along = dL if lado == "L" else (-dR[0], -dR[1])
                ctx.placas.append({"ref": ref, "grupo": "Cobertura", "face": f"vertente {1 if lado == 'L' else 2}", "camada": 1, "placa": c["placa"],
                                   "nome": pl["nome"], "cell": cell, "pecas": [cell], "area": rect_area(cell), "bruta": pl["w"] * pl["h"], "parafusos": npar,
                                   "plano": {"tipo": "vertente", "O": g(0, E_[0] + n_up[0] * hc / 2, E_[1] + n_up[1] * hc / 2), "U": gd(1, 0, 0),
                                             "Vv": gd(0, along[0], along[1]), "N": gd(0, n_up[0], n_up[1]), "esp": pl["esp"]}})
            v0 += pl["h"]
    ctx.extras.append({"cat": "Cobertura", "item": "Área das vertentes (inclinada)", "un": "m²", "qtd": 2 * area_v / 1e6, "ref": ref})
    st = c.get("subtelha")
    if st:
        faixas = math.ceil(vert_l / (st["larguraRolo"] - st["sobreposicao"]) - EPS)
        ctx.extras.append({"cat": "Cobertura", "item": st["nome"], "un": "m", "qtd": 2 * faixas * Lr / 1000, "ref": ref, "rolo": st["comprimentoRolo"]})
    ctx.extras.append({"cat": "Cobertura", "item": "Cumeeira", "un": "m", "qtd": Lr / 1000, "ref": ref})
    ctx.extras.append({"cat": "Cobertura", "item": "Beirados (2 lados)", "un": "m", "qtd": 2 * Lr / 1000, "ref": ref})
    ctx.extras.append({"cat": "Cobertura", "item": "Remates de empena (4 arestas)", "un": "m", "qtd": 4 * vert_l / 1000, "ref": ref})
    ctx.extras.append({"cat": "Cobertura", "item": "Empenas: área triangular a revestir (2 empenas)", "un": "m²", "qtd": 2 * (S * (S / 2) * ta / 2) / 1e6, "ref": ref})
    if (c.get("ripas") or {}).get("passo"):
        lin = math.ceil(vert_l / c["ripas"]["passo"] - EPS) + 1
        ctx.extras.append({"cat": "Cobertura", "item": f"{c['ripas'].get('nome') or 'Ripa'} (passo {c['ripas']['passo']} mm)", "un": "m",
                           "qtd": 2 * lin * Lr / 1000, "ref": ref})


# ---------------------------------------------------------------------------------------------- resumo / quantidades
def _resumo(ctx):
    proj = ctx.proj
    dens = proj.get("aco", {}).get("densidade", 7850)
    perfis = {}
    for m in ctx.membros:
        e = perfis.setdefault(m["perfilNome"], {"perfil": m["perfilNome"], "chave": m["perfil"], "n": 0, "metros": 0.0, "kg": 0.0,
                                                "kgm": kg_per_m(m["prof"], dens), "cortes": {}, "lista": []})
        e["n"] += 1
        e["metros"] += m["L"] / 1000
        e["kg"] += m["kg"]
        e["lista"].append(m["L"])
        c = e["cortes"].setdefault((m["tipoPeca"], m["L"]), {"tipoPeca": m["tipoPeca"], "L": m["L"], "n": 0, "ids": []})
        c["n"] += 1
        c["ids"].append(m["id"])
    barra = proj.get("barraComercial") or 6000
    lista_perfis = []
    for e in perfis.values():
        br = ffd(e["lista"], barra, 3)
        lista_perfis.append({"perfil": e["perfil"], "chave": e["chave"], "pecas": e["n"], "metros": e["metros"], "kg": e["kg"], "kgm": e["kgm"],
                             "barras": len(br["bars"]), "sobraBarras": sum(b["free"] for b in br["bars"]) / 1000,
                             "pecasMaioresQueBarra": len(br["too_long"]),
                             "cortes": sorted(e["cortes"].values(), key=lambda c: -c["L"])})
    lista_perfis.sort(key=lambda p: -p["kg"])

    kerf = (proj.get("corte") or {}).get("kerf", 3)
    cortes = []
    for pk in ctx.packs.values():
        r = plano_corte(pk["pecas"], pk["W"], pk["H"], kerf, pk["rodar"])
        cortes.append({"chave": pk["chave"], "nome": pk["nome"], "W": pk["W"], "H": pk["H"], "rodar": pk["rodar"], "folhas": r["folhas"],
                       "fora": len(r["fora"]), "pecas": len(pk["pecas"])})
        if r["fora"]:
            ctx.avisos.append(f"{pk['nome']}: {len(r['fora'])} peça(s) maiores que a placa comercial.")
    placas = {}
    for p in ctx.placas:
        if p["placa"] == "ETICS":
            continue
        e = placas.setdefault(p["nome"], {"nome": p["nome"], "placa": p["placa"], "un": 0, "area": 0.0, "bruta": 0.0})
        e["un"] += 1
        e["area"] += p["area"] / 1e6
        e["bruta"] += p["bruta"] / 1e6
    lista_placas = []
    for e in placas.values():
        c = next((x for x in cortes if x["chave"] == e["placa"]), None)
        un = len(c["folhas"]) if c else e["un"]
        bruta = un * (c["W"] * c["H"] / 1e6 if c else e["bruta"] / max(e["un"], 1))
        lista_placas.append({**e, "unSemSobras": e["un"], "un": un, "bruta": bruta, "desperdicio": 1 - e["area"] / bruta if bruta else 0})
    for c in cortes:
        if c["chave"].startswith("ETICS|"):
            ctx.extras.append({"cat": "ETICS", "item": f"Placas {c['nome']} ({c['W']}×{c['H']}) — plano de corte com reaproveitamento", "un": "un",
                               "qtd": len(c["folhas"])})

    agg = {}
    for x in ctx.extras:
        k = (x["cat"], x["item"], x["un"])
        e = agg.setdefault(k, {"cat": x["cat"], "item": x["item"], "un": x["un"], "qtd": 0.0, "rolo": x.get("rolo"), "m2emb": x.get("m2emb"),
                               "esp": x.get("esp"), "refs": []})
        e["qtd"] += x["qtd"]
        if x.get("ref") and x["ref"] not in e["refs"]:
            e["refs"].append(x["ref"])
    extras = []
    for e in agg.values():
        o = dict(e)
        if e.get("rolo") and e["un"] == "m":
            o["rolos"] = math.ceil(e["qtd"] * 1000 / e["rolo"] - EPS)
        if e.get("m2emb") and e["un"] == "m²":
            o["embalagens"] = math.ceil(e["qtd"] / e["m2emb"] - EPS)
        if e.get("esp") and e["un"] == "m²":
            o["m3"] = e["qtd"] * e["esp"] / 1000
        extras.append(o)

    kg = sum(m["kg"] for m in ctx.membros)
    area_pisos = 0.0
    for p in proj.get("perimetros") or []:
        pts = p["pontos"]
        area_pisos += abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2 / 1e6
    parafusos = sorted(ctx.parafusos.values(), key=lambda p: -p["qtd"])
    por_grupo = {}
    for m in ctx.membros:
        por_grupo[m["grupo"]] = por_grupo.get(m["grupo"], 0) + m["kg"]

    membros_out = []
    for m in ctx.membros:
        mo = {k: v for k, v in m.items() if k != "prof"}
        mo["sec"] = m["prof"]
        membros_out.append(mo)
    return {
        "nome": proj.get("nome"),
        "country": proj.get("country", "PT"),
        "membros": membros_out,
        "placas": ctx.placas,
        "paredes": [{"id": w["id"], "tipo": w["tipo"], "L": w["L"], "H": w["H"], "z0": w["z0"], "A": w["A"], "d": w["d"], "n": w["n"],
                     "y0": w["y0"], "Dt": w["tp"]["Dt"], "aberturas": w["aberturas"], "membros": [m["id"] for m in w.get("membros", [])],
                     "faceInfo": w.get("faceInfo"), "perimetro": w.get("perimetro"), "nivel": w.get("nivel"), "faixaPiso": w.get("faixaPiso", 0)}
                    for w in ctx.paredes],
        "pisos": [{k: v for k, v in f.items() if k != "vg"} for f in ctx.pisos],
        "coberturas": ctx.coberturas,
        "perfis": lista_perfis,
        "placasResumo": lista_placas,
        "planosCorte": cortes,
        "parafusos": parafusos,
        "ancoragens": list(ctx.ancoragens.values()),
        "extras": extras,
        "avisos": ctx.avisos,
        "hipoteses": list(proj.get("hipoteses") or []),
        "regras": proj.get("regras"),
        "estudo": {"kgAco": kg, "nMembros": len(ctx.membros), "areaPisos": area_pisos, "kgPorM2": kg / area_pisos if area_pisos else None,
                   "nParafusos": sum(p["qtd"] for p in parafusos), "kgPorGrupo": por_grupo, "coberturas": ctx.coberturas},
    }
