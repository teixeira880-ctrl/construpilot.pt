"""Motor de cálculo CLT (madeira lamelada-colada cruzada) — determinístico, sem IA.

Entrada: projeto CLT (ver defaults.exemplo / adapter.from_takeoff), unidades mm, Z vertical — a MESMA geometria que o motor
LSF (perímetros por piso, paredes interiores, zonas de laje, coberturas), lida da planta real.
Saída: cada painel com geometria 3D real (origem + eixos + contorno + recortes dos vãos), volumes líquido / envolvente /
de prensa (plano de prensa MaxRects por composição), ligações contadas painel a painel e linha a linha (esquadros,
hold-downs, parafusos estruturais nos cantos, T, apoios de laje e cobertura, réguas de junta), bandas e fitas por metro,
camadas exteriores por plano de corte, pontos de elevação e corte CNC.

Cadeia: lajes (composição pela esbelteza, cota de topo) → paredes de perímetro (cantos convexos/côncavos) → paredes
interiores (corte nas faces) → painéis de parede (juntas fora dos vãos, limite de prensa) → painéis de laje → cobertura
(águas, empenas, viga de cumeeira) → ligações → camadas → resumo (plano de prensa, mapa).
"""
from __future__ import annotations

import copy
import math

from shapely.geometry import Polygon, box

from engines.lsf.geom import EPS, plano_corte, r1, subtract_rects


class Ctx:
    def __init__(self, proj: dict):
        self.proj = proj
        self.R = proj["regras"]
        self.paredes: list[dict] = []
        self.paineis: list[dict] = []
        self.lajes: list[dict] = []
        self.coberturas: list[dict] = []
        self.parafusos: dict[str, dict] = {}
        self.conectores: dict[str, dict] = {}
        self.ancoragens: dict[str, dict] = {}
        self.metros: dict[str, dict] = {}
        self.extras: list[dict] = []
        self.vigas: list[dict] = []
        self.avisos: list[str] = []
        self.grupo_topo: dict[str, float] = {}
        self.grupo_base: dict[str, float] = {}
        self.perim_topo: dict[str, float] = {}
        self.cont: dict[str, int] = {}

    def painel(self, k: str) -> dict:
        p = self.proj["paineis"].get(k)
        if not p:
            raise ValueError(f'Composição CLT "{k}" não definida em paineis')
        return p


def calcular(proj_in: dict) -> dict:
    proj = copy.deepcopy(proj_in)
    from . import defaults
    b = defaults.base(proj.get("country", "PT"), proj.get("produto") or "generico_c24")
    for k, v in b.items():
        proj.setdefault(k, v)
    for k, v in defaults.REGRAS.items():
        proj["regras"].setdefault(k, v)
    ctx = Ctx(proj)
    _prep_lajes(ctx)
    for per in proj.get("perimetros") or []:
        _expand_perimetro(ctx, per)
    niveis_z = {round(w["z0"]): w.get("nivel") for w in ctx.paredes}
    for w in proj.get("paredes") or []:
        _prep_parede_avulsa(ctx, w)
        if not ctx.paredes[-1].get("nivel"):
            ctx.paredes[-1]["nivel"] = niveis_z.get(round(ctx.paredes[-1]["z0"]))
    zmin = min((w["z0"] for w in ctx.paredes), default=0.0)
    for w in ctx.paredes:
        if not w.get("apoio"):
            w["apoio"] = "betao" if w["z0"] <= zmin + 1 else "laje"
        _paineis_parede(ctx, w)
    _ligacoes_paredes(ctx)
    for f in ctx.lajes:
        _paineis_laje(ctx, f)
    for c in proj.get("coberturas") or []:
        _cobertura(ctx, c)
    if not proj.get("soClt"):
        for w in ctx.paredes:
            _camadas_parede(ctx, w)
    for p in ctx.paineis:
        n = ctx.R["elevacaoParede"] if p["tipo"] in ("parede", "empena") else ctx.R["elevacaoLaje"]
        _add(ctx.conectores, proj["conectores"]["elevacao"], n, "Pontos de elevação")
    return _resumo(ctx)


# ------------------------------------------------------------------------------------------------------------------ util
def _add(dic, nome, qtd, origem):
    if not qtd:
        return
    e = dic.setdefault(nome, {"nome": nome, "qtd": 0, "origens": {}})
    e["qtd"] += qtd
    e["origens"][origem] = e["origens"].get(origem, 0) + qtd


def _metro(ctx, chave, L_mm, origem):
    if L_mm <= EPS:
        return
    s = ctx.proj["selantes"][chave]
    e = ctx.metros.setdefault(chave, {"nome": s["nome"], "rolo": s.get("rolo"), "mm": 0.0, "origens": {}})
    e["mm"] += L_mm
    e["origens"][origem] = e["origens"].get(origem, 0) + L_mm / 1000


def _aviso(ctx, msg):
    if msg not in ctx.avisos:
        ctx.avisos.append(msg)


def n_linha(L: float, passo: float, bordo: float) -> int:
    """Número de fixações numa linha de comprimento L (primeira e última a `bordo` dos extremos, passo máximo `passo`)."""
    if L <= EPS:
        return 0
    if L <= 2 * bordo + EPS:
        return 1
    return int(math.ceil((L - 2 * bordo) / passo - EPS)) + 1


def parafuso(ctx, esp_atravessada: float) -> str:
    L = esp_atravessada + ctx.R["penetracao"]
    std = next((x for x in __import__("engines.clt.defaults", fromlist=["PARAFUSOS_STD"]).PARAFUSOS_STD if x >= L - EPS), None)
    if std is None:
        _aviso(ctx, f"Parafuso estrutural com {L:.0f} mm — acima do comprimento corrente; prever ligação específica.")
        std = int(math.ceil(L / 20) * 20)
    return ctx.proj["conectores"]["parafusoEstrutural"].format(L=std)


def _resolve_z(ctx, z):
    if isinstance(z, (int, float)):
        return float(z)
    if isinstance(z, str) and z.startswith("auto:"):
        k = z[5:]
        if k in ctx.grupo_topo:
            return ctx.grupo_topo[k]
        if k in ctx.perim_topo:
            return ctx.perim_topo[k]
        raise ValueError(f'Referência de cota "{z}" desconhecida (laje ou perímetro ainda não calculado)')
    raise ValueError(f"Cota inválida: {z}")


def _esp_camadas(ctx, lst):
    if ctx.proj.get("soClt"):
        return 0.0
    return sum(ctx.proj["camadas"][c["camada"]].get("esp", 0) for c in (lst or []))


def _pid(ctx, ref):
    ctx.cont[ref] = ctx.cont.get(ref, 0) + 1
    k = ctx.cont[ref]
    s = ""
    while k:
        k, r = divmod(k - 1, 26)
        s = chr(65 + r) + s
    return f"{ref}{s}" if ref[-1].isdigit() else f"{ref}-{s}"


def _painel(ctx, p: dict) -> dict:
    """Completa áreas, volumes e massa de um painel a partir do contorno e dos recortes (mm, plano local u-v)."""
    poly = Polygon(p["contorno"])
    net = poly
    for r in p.get("recortes") or []:
        net = net.difference(box(r["x0"], r["z0"], r["x1"], r["z1"]))
    t = p["esp"]
    p["areaBruta"] = p["L"] * p["H"] / 1e6                 # retângulo envolvente
    p["areaContorno"] = poly.area / 1e6
    p["areaLiq"] = net.area / 1e6
    p["volBruto"] = p["areaBruta"] * t / 1000
    p["volLiq"] = p["areaLiq"] * t / 1000
    p["kg"] = p["volLiq"] * ctx.proj["densidade"]
    per = poly.length + sum(2 * ((r["x1"] - r["x0"]) + (r["z1"] - r["z0"])) for r in p.get("recortes") or [])
    p["corteCNC"] = per / 1000
    ctx.paineis.append(p)
    return p


# ---------------------------------------------------------------------------------------------------------------- lajes
def _prep_lajes(ctx):
    R = ctx.R
    grupos: dict[str, list] = {}
    for f in ctx.proj.get("pisos") or []:
        f = dict(f)
        S = (f["y1"] - f["y0"]) if f.get("vao", "y") == "y" else (f["x1"] - f["x0"])
        f["S"] = S
        grupos.setdefault(f.get("grupo", f["id"]), []).append(f)
        ctx.lajes.append(f)
    for g, fs in grupos.items():
        cob = any(f.get("cobertura") for f in fs)
        esb = R["esbeltezaCobertura"] if cob else R["esbelteza"]
        expl = [f["painel"] for f in fs if f.get("painel")]
        if expl:
            k = max(expl, key=lambda x: ctx.painel(x)["esp"])
        else:
            smax = max(f["S"] for f in fs)
            k = next((x for x in ctx.proj["lajes"] if ctx.painel(x)["esp"] >= smax / esb - EPS), None)
            if k is None:
                k = ctx.proj["lajes"][-1]
                _aviso(ctx, f"{g}: vão de {smax / 1000:.2f} m acima do pré-dimensionamento das composições disponíveis "
                            f"({ctx.painel(k)['esp']} mm) — prever apoio intermédio ou laje mista.")
        t = ctx.painel(k)["esp"]
        smax = max(f["S"] for f in fs)
        if expl and smax / t > esb + 1e-6:
            _aviso(ctx, f"{g}: vão de {smax / 1000:.2f} m com {k} (vão/espessura = {smax / t:.0f} > {esb}) — prever apoio intermédio "
                        "ou composição mais espessa.")
        for f in fs:
            f["painel"] = k
            f["esp"] = t
            f["esbelteza"] = round(f["S"] / t, 1)
        ctx.grupo_base[g] = min(f["z"] for f in fs)
        ctx.grupo_topo[g] = max(f["z"] for f in fs) + t


# ------------------------------------------------------------------------------------------------- paredes: preparação
def _tipo(ctx, k):
    T = ctx.proj["tiposParede"].get(k)
    if not T:
        raise ValueError(f'Tipo de parede "{k}" não definido')
    pn = ctx.painel(T["painel"])
    return {"T": T, "k": T["painel"], "D": pn["esp"], "camadas": pn["camadas"]}


def _expand_perimetro(ctx, per):
    pts = per["pontos"]
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0:
        _aviso(ctx, f"Perímetro {per['id']}: pontos em sentido horário — use sentido anti-horário (interior à esquerda).")
    z0 = _resolve_z(ctx, per.get("z0", 0))
    tp = _tipo(ctx, per["tipo"])
    H = float(per["altura"])
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
        L = ln - tp["D"] if eC else ln + tp["D"]
        ctx.paredes.append({
            "id": f"{per['id']}-{i + 1}", "tipo": per["tipo"], "tp": tp, "A": list(pts[i]), "d": [dx, dy, 0], "n": [-dy, dx, 0],
            "y0": 0.0, "L": L, "z0": z0, "H": H, "vaos": [dict(v) for v in _vaos_do_lado(per.get("vaos"), i)],
            "perimetro": {"id": per["id"], "lado": ln, "sC": sC, "eC": eC}, "juncoes": [], "nivel": per.get("nivel", per["id"]),
            "apoio": per.get("apoio"),
        })
    ctx.perim_topo[per["id"]] = z0 + H


def _vaos_do_lado(vaos, i):
    if not vaos:
        return []
    if isinstance(vaos, list):
        return vaos[i] if i < len(vaos) and isinstance(vaos[i], list) else []
    return vaos.get(i) or vaos.get(str(i)) or []


def _faces_esp(ctx, h, lado_interior: bool):
    T = h["tp"]["T"]
    if h.get("perimetro"):
        return _esp_camadas(ctx, T.get("interior") if lado_interior else T.get("exterior"))
    return _esp_camadas(ctx, T.get("faceA") if lado_interior else T.get("faceB"))


def _prep_parede_avulsa(ctx, w):
    tp = _tipo(ctx, w["tipo"])
    z0 = _resolve_z(ctx, w.get("z0", 0))
    H = float(w.get("H", w.get("altura")))
    ax, bx = w["a"], w["b"]
    ln = math.hypot(bx[0] - ax[0], bx[1] - ax[1])
    if ln < 1:
        raise ValueError(f"Parede {w['id']}: comprimento nulo")
    d = [(bx[0] - ax[0]) / ln, (bx[1] - ax[1]) / ln, 0]
    n = [-d[1], d[0], 0]
    y0 = 0.0 if w.get("alinhamento") == "face" else -tp["D"] / 2
    ts, te = 0.0, ln
    hosts = []
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
            yc = h["y0"] + Dh / 2
            yT = h["y0"] + Dh + _faces_esp(ctx, h, True) if qy > yc else h["y0"] - _faces_esp(ctx, h, False)
            dn = d[0] * h["n"][0] + d[1] * h["n"][1]
            if abs(dn) < 1e-6:
                continue
            aY = (ax[0] - h["A"][0]) * h["n"][0] + (ax[1] - h["A"][1]) * h["n"][1]
            t = (yT - aY) / dn
            if which == "ini":
                ts = t
            else:
                te = t
            hosts.append(h)
            break
    wall = {"id": w["id"], "tipo": w["tipo"], "tp": tp, "A": [ax[0] + d[0] * ts, ax[1] + d[1] * ts], "d": d, "n": n, "y0": y0,
            "L": te - ts, "z0": z0, "H": H, "vaos": [{**v, "x": v["x"] - ts} for v in (w.get("vaos") or [])],
            "perimetro": None, "juncoes": [], "nivel": w.get("nivel"), "apoio": w.get("apoio"), "hosts": [h["id"] for h in hosts]}
    if wall["L"] < 300:
        _aviso(ctx, f"Parede {w['id']}: comprimento útil {r1(wall['L'])} mm após corte nas faces — verificar a geometria.")
    for h in hosts:
        h["juncoes"].append({"parede": w["id"], "H": min(H, h["z0"] + h["H"] - z0)})
    ctx.paredes.append(wall)


# ---------------------------------------------------------------------------------------------------- painéis de parede
def _juntas(L: float, passo_max: float, proibidos: list, m_min: float = 600.0):
    """Posições das juntas ao longo de L: segmentos ≤ passo_max, juntas fora dos intervalos proibidos (vãos ± margem)."""
    n = max(1, int(math.ceil(L / passo_max - 1e-9)))
    if n == 1:
        return [], True
    ok = True
    juntas = []
    prev = 0.0
    for k in range(1, n):
        alvo = L * k / n
        lo, hi = max(prev + m_min, L - (n - k) * passo_max), min(prev + passo_max, L - m_min)
        cand = [alvo] + [v for a, b in proibidos for v in (a, b)]
        cand = [c for c in cand if lo - EPS <= c <= hi + EPS and not any(a + EPS < c < b - EPS for a, b in proibidos)]
        if not cand:
            ok = False
            c = min(max(alvo, lo), hi)
        else:
            c = min(cand, key=lambda x: abs(x - alvo))
        juntas.append(c)
        prev = c
    return juntas, ok


def _paineis_parede(ctx, w):
    R = ctx.R
    tp = w["tp"]
    Wmax, Lmax = ctx.proj["prensa"]["W"], ctx.proj["prensa"]["L"]
    L, H = w["L"], w["H"]
    ab = []
    for v in w["vaos"]:
        z0 = 0.0 if v.get("tipo") == "porta" else float(v.get("peitoril", 0))
        r = {"id": v.get("id"), "tipo": v.get("tipo", "janela"), "x0": float(v["x"]), "x1": float(v["x"]) + float(v["largura"]),
             "z0": z0, "z1": z0 + float(v["altura"])}
        if r["x0"] < -1 or r["x1"] > L + 1:
            _aviso(ctx, f"{w['id']}: vão {r['id']} fora da parede (x {r1(r['x0'])}–{r1(r['x1'])} mm, parede {r1(L)} mm) — ajustado.")
            r["x0"], r["x1"] = max(r["x0"], 0.0), min(r["x1"], L)
            if r["x1"] - r["x0"] < 100:
                continue
        if H - r["z1"] < R["vergaMin"] - EPS:
            _aviso(ctx, f"{w['id']}: vão {r['id']} com {r1(H - r['z1'])} mm de painel acima (< {R['vergaMin']} mm) — verga a verificar.")
        ab.append(r)
    w["aberturas"] = ab
    m = R["juntaVaoMin"]
    proib = [(a["x0"] - m, a["x1"] + m) for a in ab]
    vertical = H > Wmax + EPS
    passo = Wmax if vertical else Lmax
    if vertical and H > Lmax + EPS:
        _aviso(ctx, f"{w['id']}: altura {r1(H)} mm acima do comprimento de prensa ({Lmax:.0f} mm) — junta horizontal a prever.")
    juntas, ok = _juntas(L, passo, proib)
    if not ok:
        _aviso(ctx, f"{w['id']}: não foi possível pôr todas as juntas a ≥ {m:.0f} mm dos vãos — junta junto a vão (reforço a prever).")
    xs = [0.0] + juntas + [L]
    w["juntasPaineis"] = juntas
    w["paineis"] = []
    o2 = (w["A"][0] + w["n"][0] * w["y0"], w["A"][1] + w["n"][1] * w["y0"])
    for i in range(len(xs) - 1):
        xa, xb = xs[i], xs[i + 1]
        rec = []
        for a in ab:
            if a["x1"] > xa + EPS and a["x0"] < xb - EPS:
                rec.append({"id": a["id"], "tipo": a["tipo"], "x0": max(a["x0"], xa) - xa, "x1": min(a["x1"], xb) - xa, "z0": a["z0"], "z1": min(a["z1"], H)})
        Lp = xb - xa
        p = {"id": _pid(ctx, w["id"]), "tipo": "parede", "ref": w["id"], "nivel": w.get("nivel"), "painel": tp["k"], "esp": tp["D"],
             "camadas": tp["camadas"], "o": [o2[0] + w["d"][0] * xa, o2[1] + w["d"][1] * xa, w["z0"]], "u": list(w["d"]), "v": [0, 0, 1],
             "w": list(w["n"]), "L": r1(Lp), "H": r1(H), "contorno": [[0, 0], [Lp, 0], [Lp, H], [0, H]], "recortes": rec,
             "xParede": r1(xa), "orientacao": "vertical" if vertical else "horizontal"}
        _painel(ctx, p)
        w["paineis"].append(p)
        if i > 0:                                  # junta vertical entre painéis: régua LVL + parafusos dos dois lados + fita
            lb = ctx.proj["conectores"]["lambrim"]
            _add(ctx.parafusos, lb["parafuso"], 2 * n_linha(H, R["lambrimPasso"], R["bordoPasso"] / 2), f"Juntas de painéis de parede ({w['id']})")
            ctx.extras.append({"cat": "Réguas de junta", "item": lb["nome"], "un": "m", "qtd": H / 1000, "ref": w["id"]})
            _metro(ctx, "fitaAr", H, "Juntas de painéis de parede")
    # base: esquadros de corte e hold-downs
    con = ctx.proj["conectores"]
    betao = w["apoio"] == "betao"
    esq = con["esquadroBetao" if betao else "esquadroMadeira"]
    hd = con["holdDownBetao" if betao else "holdDownMadeira"]
    portas = [(a["x0"], a["x1"]) for a in ab if a["z0"] <= EPS]
    base_total = 0.0
    for p in w["paineis"]:
        xa, xb = p["xParede"], p["xParede"] + p["L"]
        segs = [(xa, xb)]
        for a, b in portas:
            nseg = []
            for s0, s1 in segs:
                if b <= s0 or a >= s1:
                    nseg.append((s0, s1))
                    continue
                if a > s0:
                    nseg.append((s0, a))
                if b < s1:
                    nseg.append((b, s1))
            segs = nseg
        ne = 0
        for s0, s1 in segs:
            ls = s1 - s0
            base_total += ls
            if ls < 300:
                continue
            ne += max(1, n_linha(ls, R["esquadroPasso"], R["esquadroExtremo"]))
        ne = max(ne, R["esquadroMin"])
        p["esquadros"] = ne
        orig = f"Base das paredes — {'betão' if betao else 'laje CLT'}"
        _add(ctx.conectores, esq["nome"], ne, orig)
        _add(ctx.parafusos, con["prego"], ne * esq["pregos"] * (1 if betao else 2), "Esquadros de corte")
        if betao:
            _add(ctx.ancoragens, esq["ancora"], ne, "Esquadros de corte")
        nh = 2 if tp["T"].get("holdDowns", True) else 0
        nh += 2 * sum(1 for r in p["recortes"] if (r["x1"] - r["x0"]) >= R["holdDownVaoMin"] - EPS and 0 < r["x0"] and r["x1"] < p["L"])
        p["holdDowns"] = nh
        if nh:
            _add(ctx.conectores, hd["nome"], nh, "Extremos de painel e vãos ≥ " + f"{R['holdDownVaoMin'] / 1000:.2f} m".replace(".", ","))
            _add(ctx.parafusos, con["prego"], nh * hd["pregos"], "Hold-downs")
            _add(ctx.ancoragens, hd["ancora"], nh, "Hold-downs")
    _metro(ctx, "bandaBase" if betao else "bandaPiso", base_total, f"Base das paredes ({w.get('nivel') or w['id']})")
    w["baseMm"] = base_total


def _ligacoes_paredes(ctx):
    """Cantos do perímetro e ligações em T: parafusos estruturais ao longo da altura + fita de estanquidade."""
    R = ctx.R
    por_id = {w["id"]: w for w in ctx.paredes}
    for w in ctx.paredes:
        per = w.get("perimetro")
        if per:
            # canto no fim desta parede: a parede seguinte (canto convexo) ou esta (côncavo) atravessa — parafusos pela atravessante
            n = n_linha(w["H"], R["cantoPasso"], R["bordoPasso"])
            _add(ctx.parafusos, parafuso(ctx, w["tp"]["D"]), n, "Cantos entre paredes exteriores")
            _metro(ctx, "fitaAr", w["H"], "Cantos entre paredes")
        for h_id in w.get("hosts") or []:
            h = por_id[h_id]
            Hc = min(w["z0"] + w["H"], h["z0"] + h["H"]) - max(w["z0"], h["z0"])
            n = n_linha(Hc, R["cantoPasso"], R["bordoPasso"])
            _add(ctx.parafusos, parafuso(ctx, h["tp"]["D"]), n, "Ligações em T (parede interior → parede)")
            _metro(ctx, "fitaAr", 2 * Hc, "Ligações em T")


# ------------------------------------------------------------------------------------------------------ painéis de laje
def _clip(a, b, x0, y0, x1, y1):
    """Comprimento do segmento ab dentro do retângulo (Liang-Barsky)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return 0.0
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return 0.0
    return (t1 - t0) * math.hypot(dx, dy)


def _paineis_laje(ctx, f):
    R = ctx.R
    Wmax, Lmax = ctx.proj["prensa"]["W"], ctx.proj["prensa"]["L"]
    vy = f.get("vao", "y") == "y"
    S0, S1 = (f["y0"], f["y1"]) if vy else (f["x0"], f["x1"])
    P0, P1 = (f["x0"], f["x1"]) if vy else (f["y0"], f["y1"])
    S, B = S1 - S0, P1 - P0
    t = f["esp"]
    tipo = "cobertura" if f.get("cobertura") else "laje"
    if S > Lmax + EPS:
        _aviso(ctx, f"{f['id']}: vão {S / 1000:.2f} m acima do comprimento de prensa — junta de topo sobre apoio a prever.")
    nb = max(1, int(math.ceil(B / Wmax - 1e-9)))
    larg = [Wmax] * (nb - 1) + [B - Wmax * (nb - 1)]
    if nb > 1 and larg[-1] < 600:
        m = (larg[-1] + larg[-2]) / 2
        larg[-2:] = [m, m]
    f["paineis"] = []
    p0 = P0
    lb = ctx.proj["conectores"]["lambrim"]
    for i, bw in enumerate(larg):
        if vy:
            o, u, v = [p0 + bw, S0, f["z"]], [0, 1, 0], [-1, 0, 0]
        else:
            o, u, v = [S0, p0, f["z"]], [1, 0, 0], [0, 1, 0]
        p = {"id": _pid(ctx, f["id"]), "tipo": tipo, "ref": f["id"], "nivel": f.get("nivel") or f.get("grupo"), "painel": f["painel"], "esp": t,
             "camadas": ctx.painel(f["painel"])["camadas"], "o": o, "u": u, "v": v, "w": [0, 0, 1], "L": r1(S), "H": r1(bw),
             "contorno": [[0, 0], [S, 0], [S, bw], [0, bw]], "recortes": [], "vao": r1(S), "esbelteza": f["esbelteza"]}
        _painel(ctx, p)
        f["paineis"].append(p)
        if i > 0:
            _add(ctx.parafusos, lb["parafuso"], 2 * n_linha(S, R["lambrimPasso"], R["bordoPasso"] / 2), f"Juntas de painéis de laje ({f['id']})")
            ctx.extras.append({"cat": "Réguas de junta", "item": lb["nome"], "un": "m", "qtd": S / 1000, "ref": f["id"]})
            _metro(ctx, "fitaAr", S, "Juntas de painéis de laje")
        p0 += bw
    # apoios: paredes cujo topo coincide com a face inferior da laje
    apoio = 0.0
    for w in ctx.paredes:
        if abs(w["z0"] + w["H"] - f["z"]) > 5:
            continue
        yc = w["y0"] + w["tp"]["D"] / 2
        a = (w["A"][0] + w["n"][0] * yc, w["A"][1] + w["n"][1] * yc)
        b = (a[0] + w["d"][0] * w["L"], a[1] + w["d"][1] * w["L"])
        apoio += _clip(a, b, f["x0"] - 1, f["y0"] - 1, f["x1"] + 1, f["y1"] + 1)
    f["apoioMm"] = apoio
    if apoio < 1:
        _aviso(ctx, f"{f['id']}: nenhuma parede de apoio encontrada sob a laje — apoios a definir.")
    n = n_linha(apoio, R["coberturaApoioPasso"] if tipo == "cobertura" else R["lajeApoioPasso"], R["bordoPasso"]) if apoio else 0
    _add(ctx.parafusos, parafuso(ctx, t), n, "Laje → paredes de apoio" if tipo == "laje" else "Cobertura plana → paredes")
    if tipo == "cobertura" and not ctx.proj.get("soClt"):
        _camadas_area(ctx, ctx.proj["cobertura"]["plana"], [(S, B)] * 1, f["id"], "Cobertura")


# ----------------------------------------------------------------------------------------------------------- cobertura
def _cobertura(ctx, c):
    R = ctx.R
    Wmax, Lmax = ctx.proj["prensa"]["W"], ctx.proj["prensa"]["L"]
    z = _resolve_z(ctx, c["z"])
    ax = c.get("cumeeira", "x") == "x"
    x0, y0, x1, y1 = c["x0"], c["y0"], c["x1"], c["y1"]
    A_len, C_len = (x1 - x0, y1 - y0) if ax else (y1 - y0, x1 - x0)
    alpha = math.radians(float(c.get("inclinacao", 30)))
    bei = float(c.get("beiral", 500))
    half = C_len / 2
    hh = half * math.tan(alpha)
    zr = z + hh

    def P(s, r, zz):                       # coordenadas locais (s ao longo da cumeeira, r transversal) → globais
        return [x0 + s, y0 + r, zz] if ax else [x0 + r, y0 + s, zz]

    def V(s, r, zz):
        return [s, r, zz] if ax else [r, s, zz]

    Ls_apoio = half / math.cos(alpha)                       # vão inclinado parede de beirado → cumeeira
    esb = R["esbeltezaCobertura"]
    k = c.get("painel") or next((x for x in ctx.proj["lajes"] if ctx.painel(x)["esp"] >= Ls_apoio / esb - EPS), ctx.proj["lajes"][-1])
    t = ctx.painel(k)["esp"]
    Ls = (half + bei) / math.cos(alpha) + t * math.tan(alpha)
    if Ls > Lmax + EPS:
        _aviso(ctx, f"{c['id']}: água com {Ls / 1000:.2f} m acima do comprimento de prensa — junta a prever.")
    B_tot = A_len + 2 * bei
    nb = max(1, int(math.ceil(B_tot / Wmax - 1e-9)))
    larg = [Wmax] * (nb - 1) + [B_tot - Wmax * (nb - 1)]
    if nb > 1 and larg[-1] < 600:
        m = (larg[-1] + larg[-2]) / 2
        larg[-2:] = [m, m]
    ca, sa = math.cos(alpha), math.sin(alpha)
    info = {"id": c["id"], "tipo": "duas_aguas", "z": z, "zCumeeira": zr, "inclinacao": c.get("inclinacao", 30), "beiral": bei, "painel": k,
            "esp": t, "vaoInclinado": r1(Ls_apoio), "esbelteza": round(Ls_apoio / t, 1), "paineis": [], "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "cumeeira": "x" if ax else "y"}
    lb = ctx.proj["conectores"]["lambrim"]
    for lado, sg in (("A", 1), ("B", -1)):
        # água A: desce para r = 0 ; água B: desce para r = C_len.  Origem no beirado (face inferior), u sobe para a cumeeira.
        r_e = -bei if sg == 1 else C_len + bei
        z_e = z - bei * math.tan(alpha)
        s0 = -bei
        for i, bw in enumerate(larg):
            o = P(s0, r_e, z_e)
            u = V(0, sg * ca, sa)
            v = V(1, 0, 0)
            wv = V(0, -sg * sa, ca)
            if sg == -1:                         # manter (u, v, w) direto: v ao contrário na água B
                o = P(s0 + bw, r_e, z_e)
                v = V(-1, 0, 0)
            p = {"id": _pid(ctx, f"{c['id']}{lado}"), "tipo": "cobertura", "ref": c["id"], "nivel": "Cobertura", "painel": k, "esp": t,
                 "camadas": ctx.painel(k)["camadas"], "o": o, "u": u, "v": v, "w": wv, "L": r1(Ls), "H": r1(bw),
                 "contorno": [[0, 0], [Ls, 0], [Ls, bw], [0, bw]], "recortes": [], "vao": r1(Ls_apoio), "esbelteza": info["esbelteza"],
                 "nota": "corte em bisel na cumeeira"}
            _painel(ctx, p)
            info["paineis"].append(p["id"])
            if i > 0:
                _add(ctx.parafusos, lb["parafuso"], 2 * n_linha(Ls, R["lambrimPasso"], R["bordoPasso"] / 2), f"Juntas de painéis de cobertura ({c['id']})")
                ctx.extras.append({"cat": "Réguas de junta", "item": lb["nome"], "un": "m", "qtd": Ls / 1000, "ref": c["id"]})
                _metro(ctx, "fitaAr", Ls, "Juntas de painéis de cobertura")
            s0 += bw
    # empenas (triângulos CLT sobre as paredes de topo) com bolsa da viga de cumeeira
    Tx = ctx.proj["tiposParede"].get("EXT") or next(iter(ctx.proj["tiposParede"].values()))
    te = ctx.painel(Tx["painel"])["esp"]
    vao_viga = A_len - 2 * te
    h_v = max(240.0, math.ceil(vao_viga / 17 / 40) * 40)
    b_v = 160.0 if vao_viga <= 8000 else 200.0
    gl = ctx.proj["cobertura"].get("vigaCumeeira", "GL24h")
    ctx.vigas.append({"id": f"{c['id']}-VC", "nome": f"Viga de cumeeira em lamelado-colado {gl} {b_v:.0f}×{h_v:.0f} mm",
                      "b": b_v, "h": h_v, "L": A_len, "vao": vao_viga, "m3": b_v * h_v * A_len / 1e9,
                      "o": P(0, half - b_v / 2, zr - h_v), "eixo": V(1, 0, 0), "lado": V(0, 1, 0)})
    _aviso(ctx, f"{c['id']}: viga de cumeeira {gl} {b_v:.0f}×{h_v:.0f} mm por pré-dimensionamento (h ≈ vão/17, vão {vao_viga / 1000:.2f} m) — "
                "dimensionar (EN 1995-1-1).")
    if vao_viga > 7000:
        _aviso(ctx, f"{c['id']}: viga de cumeeira com {vao_viga / 1000:.2f} m de vão — apoio intermédio (parede ou pilar) recomendado.")
    for lado, s_w in (("E1", 0.0), ("E2", A_len)):
        sgn = 1 if s_w == 0 else -1
        o = P(s_w, 0, z)
        u = V(0, 1, 0)
        wv = V(sgn, 0, 0)
        v = [0, 0, 1]
        if sgn == -1:
            o = P(s_w, C_len, z)
            u = V(0, -1, 0)
        rec = [{"id": "VC", "tipo": "bolsa", "x0": half - b_v / 2 - 10, "x1": half + b_v / 2 + 10, "z0": hh - h_v, "z1": hh}]
        p = {"id": _pid(ctx, f"{c['id']}-{lado}"), "tipo": "empena", "ref": c["id"], "nivel": "Cobertura", "painel": Tx["painel"], "esp": te,
             "camadas": ctx.painel(Tx["painel"])["camadas"], "o": o, "u": u, "v": v, "w": wv, "L": r1(C_len), "H": r1(hh),
             "contorno": [[0, 0], [C_len, 0], [half, hh]], "recortes": rec, "nota": "empena triangular com bolsa da viga de cumeeira"}
        _painel(ctx, p)
        info["paineis"].append(p["id"])
        con = ctx.proj["conectores"]
        ne = max(R["esquadroMin"], n_linha(C_len, R["esquadroPasso"], R["esquadroExtremo"]))
        _add(ctx.conectores, con["esquadroMadeira"]["nome"], ne, "Empenas → paredes de topo")
        _add(ctx.parafusos, con["prego"], ne * con["esquadroMadeira"]["pregos"] * 2, "Esquadros de corte")
        _metro(ctx, "fitaAr", C_len, "Empenas → paredes")
        rake = half / math.cos(alpha)
        _add(ctx.parafusos, parafuso(ctx, t), 2 * n_linha(rake, R["coberturaApoioPasso"], R["bordoPasso"]), "Cobertura → empenas")
    # apoios da cobertura: paredes de beirado e viga de cumeeira
    _add(ctx.parafusos, parafuso(ctx, t), 2 * n_linha(A_len, R["coberturaApoioPasso"], R["bordoPasso"]), "Cobertura → paredes de beirado")
    _add(ctx.parafusos, parafuso(ctx, t), 2 * n_linha(A_len, R["coberturaApoioPasso"], R["bordoPasso"]), "Cobertura → viga de cumeeira")
    _metro(ctx, "fitaAr", A_len, "Junta de cumeeira")
    info["areaInclinada"] = 2 * Ls * B_tot / 1e6
    ctx.coberturas.append(info)
    if not ctx.proj.get("soClt"):
        _camadas_area(ctx, ctx.proj["cobertura"]["exterior"], [(Ls, B_tot), (Ls, B_tot)], c["id"], "Cobertura")


# ------------------------------------------------------------------------------------------------------------- camadas
def _camadas_area(ctx, camadas, rects, ref, cat_base, holes_por_rect=None):
    """Camadas sobre um conjunto de retângulos (mm). Placas → plano de corte; rolos → m² e rolos (com sobreposição)."""
    for c in camadas or []:
        C = ctx.proj["camadas"][c["camada"]]
        if C["tipo"] == "placa":
            pecas = []
            area = 0.0
            for i, (L, H) in enumerate(rects):
                cells = subtract_rects({"x0": 0, "x1": L, "z0": 0, "z1": H}, (holes_por_rect or {}).get(i, []))
                for cl in cells:
                    area += (cl["x1"] - cl["x0"]) * (cl["z1"] - cl["z0"]) / 1e6
                    # corte em faixas da dimensão da placa (cada célula é coberta por placas inteiras e recortes)
                    nx = int(math.ceil((cl["x1"] - cl["x0"]) / C["w"] - 1e-9))
                    nz = int(math.ceil((cl["z1"] - cl["z0"]) / C["h"] - 1e-9))
                    for ix in range(nx):
                        for iz in range(nz):
                            pw = min(C["w"], cl["x1"] - cl["x0"] - ix * C["w"])
                            ph = min(C["h"], cl["z1"] - cl["z0"] - iz * C["h"])
                            pecas.append({"w": pw, "h": ph, "ref": ref})
            r = plano_corte(pecas, C["w"], C["h"], 3, True)
            ctx.extras.append({"cat": cat_base, "item": C["nome"], "un": "m²", "qtd": area, "esp": C.get("esp"), "ref": ref})
            ctx.extras.append({"cat": cat_base, "item": f"{C['nome']} — placas {C['w']}×{C['h']} (plano de corte)", "un": "un",
                               "qtd": len(r["folhas"]), "ref": ref})
        elif C["tipo"] == "rolo":
            area = 0.0
            for i, (L, H) in enumerate(rects):
                cells = subtract_rects({"x0": 0, "x1": L, "z0": 0, "z1": H}, (holes_por_rect or {}).get(i, []))
                area += sum((cl["x1"] - cl["x0"]) * (cl["z1"] - cl["z0"]) for cl in cells) / 1e6
            util = (C["largura"] - C.get("sobreposicao", 0)) / 1000
            ctx.extras.append({"cat": "Membranas", "item": C["nome"], "un": "m²", "qtd": area, "ref": ref,
                               "rolo_m2": util * C["comprimento"] / 1000})


def _camadas_parede(ctx, w):
    T = w["tp"]["T"]
    if not w.get("perimetro"):
        rects = []
        for lst in (T.get("faceA"), T.get("faceB")):
            if lst:
                _camadas_area(ctx, lst, [(w["L"], w["H"])], w["id"], "Camadas interiores",
                              {0: [{"x0": a["x0"], "x1": a["x1"], "z0": a["z0"], "z1": a["z1"]} for a in w["aberturas"]]})
        return
    ln = w["perimetro"]["lado"]
    faixa = 0.0
    for g, zb in ctx.grupo_base.items():
        if abs(zb - (w["z0"] + w["H"])) < 5:
            faixa = max(faixa, ctx.grupo_topo[g] - zb)
    Hf = w["H"] + faixa
    holes = {0: [{"x0": a["x0"], "x1": a["x1"], "z0": a["z0"], "z1": a["z1"]} for a in w["aberturas"]]}
    w["faixaPiso"] = faixa
    _camadas_area(ctx, T.get("exterior"), [(ln, Hf)], w["id"], "Isolamento exterior", holes)
    if T.get("interior"):
        _camadas_area(ctx, T.get("interior"), [(w["L"], w["H"])], w["id"], "Camadas interiores", holes)


# --------------------------------------------------------------------------------------------------------------- resumo
def _resumo(ctx):
    proj = ctx.proj
    Wmax, Lmax = proj["prensa"]["W"], proj["prensa"]["L"]
    kerf = (proj.get("corte") or {}).get("kerf", 10)
    por_k: dict[str, list] = {}
    for p in ctx.paineis:
        por_k.setdefault(p["painel"], []).append(p)
    resumo, planos = [], []
    for k, ps in sorted(por_k.items(), key=lambda kv: ctx.painel(kv[0])["esp"]):
        t = ctx.painel(k)["esp"]
        larguras = sorted(proj["prensa"].get("larguras") or [Wmax])
        grupos: dict[float, list] = {}
        for p in ps:
            menor = min(p["L"], p["H"])
            wb = next((x for x in larguras if x >= menor - EPS), larguras[-1])
            grupos.setdefault(wb, []).append({"w": p["L"], "h": p["H"], "ref": p["id"]})
        folhas, fora = [], []
        vol_prensa = 0.0
        for wb, pecas in sorted(grupos.items()):
            r = plano_corte(pecas, Lmax, wb, kerf, True)
            for fl in r["folhas"]:
                usado = min(max(x["x"] + x["w"] for x in fl) + kerf, Lmax)
                vol_prensa += usado * wb * t / 1e9
                folhas.append({"comprimento": r1(usado), "largura": wb, "pecas": fl})
            fora += r["fora"]
        for x in fora:
            _aviso(ctx, f"Painel {x['ref']} ({x['w']:.0f}×{x['h']:.0f} mm) maior que a prensa {Lmax:.0f}×{Wmax:.0f} mm — fabrico especial.")
            vol_prensa += x["w"] * x["h"] * t / 1e9
        r = {"fora": fora}
        vl = sum(p["volLiq"] for p in ps)
        vb = sum(p["volBruto"] for p in ps)
        resumo.append({"painel": k, "esp": t, "camadas": ctx.painel(k)["camadas"], "n": len(ps), "areaLiq": sum(p["areaLiq"] for p in ps),
                       "volLiq": vl, "volBruto": vb, "volPrensa": vol_prensa, "brutos": len(folhas) + len(r["fora"]),
                       "desperdicio": 1 - vl / vol_prensa if vol_prensa else 0, "kg": sum(p["kg"] for p in ps),
                       "corteCNC": sum(p["corteCNC"] for p in ps),
                       "usos": sorted({p["tipo"] for p in ps})})
        planos.append({"painel": k, "esp": t, "W": Wmax, "L": Lmax, "folhas": folhas, "fora": len(r["fora"])})

    agg = {}
    for x in ctx.extras:
        kk = (x["cat"], x["item"], x["un"])
        e = agg.setdefault(kk, {"cat": x["cat"], "item": x["item"], "un": x["un"], "qtd": 0.0, "esp": x.get("esp"), "rolo_m2": x.get("rolo_m2"), "refs": []})
        e["qtd"] += x["qtd"]
        if x.get("ref") and x["ref"] not in e["refs"]:
            e["refs"].append(x["ref"])
    extras = []
    for e in agg.values():
        o = dict(e)
        if e.get("rolo_m2") and e["un"] == "m²":
            o["rolos"] = math.ceil(e["qtd"] / e["rolo_m2"] - EPS)
        if e.get("esp") and e["un"] == "m²":
            o["m3"] = e["qtd"] * e["esp"] / 1000
        extras.append(o)
    for v in ctx.vigas:
        extras.append({"cat": "Lamelado-colado", "item": v["nome"], "un": "m³", "qtd": v["m3"], "refs": [v["id"]],
                       "detalhe": f"{v['L'] / 1000:.2f} m".replace(".", ",")})
    metros = []
    for k, e in ctx.metros.items():
        metros.append({"chave": k, "nome": e["nome"], "m": e["mm"] / 1000, "rolos": math.ceil(e["mm"] / e["rolo"] - EPS) if e.get("rolo") else None,
                       "origens": e["origens"]})
    vaos = []
    for w in ctx.paredes:
        for a in w.get("aberturas") or []:
            vaos.append({"parede": w["id"], "nivel": w.get("nivel"), "id": a["id"], "tipo": a["tipo"], "largura": r1(a["x1"] - a["x0"]),
                         "altura": r1(a["z1"] - a["z0"]), "m2": (a["x1"] - a["x0"]) * (a["z1"] - a["z0"]) / 1e6,
                         "m3Recorte": (a["x1"] - a["x0"]) * (a["z1"] - a["z0"]) * w["tp"]["D"] / 1e9})

    area_pisos = 0.0
    for p in proj.get("perimetros") or []:
        pts = p["pontos"]
        area_pisos += abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2 / 1e6
    parafusos = sorted(ctx.parafusos.values(), key=lambda p: -p["qtd"])
    conectores = sorted(ctx.conectores.values(), key=lambda p: -p["qtd"])
    vl = sum(r["volLiq"] for r in resumo)
    vp = sum(r["volPrensa"] for r in resumo)
    por_uso = {}
    for p in ctx.paineis:
        e = por_uso.setdefault(p["tipo"], {"n": 0, "m3": 0.0, "m2": 0.0})
        e["n"] += 1
        e["m3"] += p["volLiq"]
        e["m2"] += p["areaLiq"]
    return {
        "nome": proj.get("nome"),
        "country": proj.get("country", "PT"),
        "produto": {"chave": proj.get("produto"), "nome": proj.get("produtoNome"), "eta": proj.get("eta"), "classe": proj.get("classe"),
                    "prensa": proj["prensa"], "densidade": proj["densidade"]},
        "soClt": bool(proj.get("soClt")),
        "paineis": ctx.paineis,
        "paredes": [{"id": w["id"], "tipo": w["tipo"], "L": w["L"], "H": w["H"], "z0": w["z0"], "A": w["A"], "d": w["d"], "n": w["n"],
                     "y0": w["y0"], "Dt": w["tp"]["D"], "painel": w["tp"]["k"], "aberturas": w.get("aberturas", []),
                     "paineis": [p["id"] for p in w.get("paineis", [])], "juntas": w.get("juntasPaineis", []), "perimetro": w.get("perimetro"),
                     "nivel": w.get("nivel"), "apoio": w.get("apoio"), "faixaPiso": w.get("faixaPiso", 0)} for w in ctx.paredes],
        "lajes": [{k: v for k, v in f.items() if k != "paineis"} | {"paineis": [p["id"] for p in f.get("paineis", [])]} for f in ctx.lajes],
        "coberturas": ctx.coberturas,
        "vigas": ctx.vigas,
        "paineisResumo": resumo,
        "planosPrensa": planos,
        "parafusos": parafusos,
        "conectores": conectores,
        "ancoragens": sorted(ctx.ancoragens.values(), key=lambda p: -p["qtd"]),
        "metros": metros,
        "extras": extras,
        "vaos": vaos,
        "avisos": ctx.avisos,
        "hipoteses": list(proj.get("hipoteses") or []),
        "regras": proj.get("regras"),
        "estudo": {"m3Liq": vl, "m3Prensa": vp, "m3Bruto": sum(r["volBruto"] for r in resumo), "desperdicio": 1 - vl / vp if vp else 0,
                   "kg": sum(r["kg"] for r in resumo), "nPaineis": len(ctx.paineis), "areaPisos": area_pisos,
                   "m3PorM2": vl / area_pisos if area_pisos else None, "nParafusos": sum(p["qtd"] for p in parafusos),
                   "nConectores": sum(c["qtd"] for c in conectores), "porUso": por_uso,
                   "corteCNC": sum(r["corteCNC"] for r in resumo), "m3Vaos": sum(v["m3Recorte"] for v in vaos),
                   "m2Vaos": sum(v["m2"] for v in vaos)},
    }
