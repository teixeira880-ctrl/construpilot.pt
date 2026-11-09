"""Planos de execução das especialidades (eletricidade, águas e esgotos, aquecimento) e pormenores de gros-œuvre — PDF vetorial em
inglês ou ucraniano, desenhado sobre a mesma base (eixos, cotas, paredes) dos planos de gros-œuvre.

Folhas:
  EL-01…03 planta de eletricidade por piso (tomadas, iluminação, comandos, pontos dedicados, quadro, circuitos)
  EL-04    esquema unifilar do quadro + quadro de circuitos
  WS-01…03 planta de águas (AF / AQ) e esgotos por piso (aparelhos, ramais, tubos de queda, coletor, diâmetros)
  WS-04    esquema vertical de águas e esgotos + quadros
  HT-01…03 planta de aquecimento (piso radiante por circuito, coletores, central térmica, termóstatos)
  HT-04    esquema hidráulico da central + perdas por divisão + circuitos de piso radiante
  GO-09    pormenores construtivos tipo (fundação, ligação parede / laje, cobertura, terraço) + mapa de ligadores CLT
"""
from __future__ import annotations

import contextvars
import math

from . import gros_oeuvre as G
from .especialidades import area, centro

LANG = contextvars.ContextVar("pe_lang", default="en")
AZUL, VERM, CAST, LARANJA, ROXO = (0.10, 0.35, 0.80), (0.82, 0.12, 0.12), (0.45, 0.28, 0.10), (0.95, 0.50, 0.05), (0.45, 0.20, 0.60)
CINZA_C = (0.75, 0.75, 0.75)
CORES_CIRC = [(0.85, 0.33, 0.10), (0.10, 0.45, 0.75), (0.15, 0.55, 0.25), (0.60, 0.20, 0.60), (0.80, 0.60, 0.05), (0.10, 0.60, 0.60),
              (0.55, 0.35, 0.20), (0.90, 0.20, 0.45)]


def L(en, uk):
    return uk if LANG.get() == "uk" else en


APARELHO = {"lavatorio": ("Washbasin", "Умивальник"), "autoclismo": ("WC", "Унітаз"), "chuveiro": ("Shower", "Душ"), "banheira": ("Bathtub", "Ванна"),
            "lava_loica": ("Kitchen sink", "Кухонна мийка"), "maquina_lavar_loica": ("Dishwasher", "Посудомийна машина"),
            "maquina_lavar_roupa": ("Washing machine", "Пральна машина"), "maquina_secar": ("Dryer", "Сушильна машина"), "tanque": ("Utility sink", "Господарська мийка")}


TIPO = {"sala": ("Living", "Вітальня"), "quarto": ("Bedroom", "Спальня"), "cozinha": ("Kitchen", "Кухня"), "casa_de_banho": ("Bathroom", "Санвузол"),
        "corredor": ("Circulation", "Коридор"), "lavandaria": ("Laundry", "Пральня"), "arrumos": ("Storage", "Комора"), "escritorio": ("Office", "Кабінет")}


def _tipo(t):
    a = TIPO.get(t, (t, t))
    return a[1] if LANG.get() == "uk" else a[0]


def _nome(d):
    return d["nome_uk"] if LANG.get() == "uk" else d["nome_en"]


def _ap(t):
    a = APARELHO.get(t, (t, t))
    return a[1] if LANG.get() == "uk" else a[0]


def _n(x, d=1):
    s = f"{x:,.{d}f}".replace(",", " ")
    return s.replace(".", ",") if LANG.get() == "uk" else s


# ---------------------------------------------------------------- base comum
def _muros_nivel(m, cota):
    return [mu for mu in m.get("muros") or [] if mu.get("cota_base_m") is not None and cota - 0.3 <= mu["cota_base_m"] <= cota + 0.05]


def _base(doc, m, r, cota, num, titulo, sub, fmt, s, k, n, tot, data, lajes_sobre=True):
    fl = G._Folha(doc, fmt)
    nv = next((x for x in r["niveis"] if abs(x["cota"] - cota) < 0.05), {"en": "", "uk": ""})
    p, bb = G._base_planta(fl, m, s, f"{num} · {titulo} — {(nv['uk'] if LANG.get() == 'uk' else nv['en']).upper()}", sub)
    G._paredes(p, _muros_nivel(m, cota), "espessura_m", G.BET)
    for d in r["divisoes"]:
        if abs(d["cota"] - cota) < 0.05:
            p.rect(d["x0"], d["y0"], d["x1"], d["y1"], (0.55, 0.55, 0.55), None, 0.5)
    p.nivel(bb[0] + 0.3, bb[2] - 0.9, f"{L('FFL', 'Відм. чистої підлоги')} {G._cota_txt(cota)}")
    return fl, p, bb


def _rotulo(p, d, extra=None, dy=0.0):
    cx, cy = centro(d)
    p.txt(cx, cy + 0.45 + dy, f"{d['id']} · {_nome(d)}", 7.2, (0.15, 0.15, 0.15), True)
    p.txt(cx, cy + 0.18 + dy, f"{_n(area(d), 2)} m²", 6.5, G.CINZA)
    if extra:
        for i, e in enumerate(extra if isinstance(extra, list) else [extra]):
            p.txt(cx, cy - 0.12 - 0.27 * i + dy, e, 6.3, (0.25, 0.25, 0.25))


def _legenda(fl, x, y, itens, titulo=None):
    if titulo:
        fl.t(x, y, titulo, 10, G.VERDE, True)
        y += 18
    for desenho, txt in itens:
        desenho(fl, x + 10, y - 3)
        fl.t(x + 30, y, txt, 8)
        y += 17
    return y


def _cartucho(fl, m, titulo, num, n, tot, k, data):
    fl.cartucho(m.get("projeto") or "—", m.get("local") or "—", titulo, num, n, tot, f"1:{k}" if k else "—", data)


# ---------------------------------------------------------------- símbolos (coordenadas da folha)
def s_tomada(fl, x, y, cor=(0, 0, 0)):
    fl.circ((x, y), 3.6, cor, (1, 1, 1), 0.8)
    fl.linha([(x - 3.6, y), (x + 3.6, y)], cor, 0.8)
    fl.linha([(x, y - 3.6), (x, y - 7)], cor, 0.8)


def s_luz(fl, x, y, cor=(0, 0, 0)):
    fl.circ((x, y), 5, cor, (1, 1, 0.85), 0.9)
    fl.linha([(x - 3.5, y - 3.5), (x + 3.5, y + 3.5)], cor, 0.8)
    fl.linha([(x - 3.5, y + 3.5), (x + 3.5, y - 3.5)], cor, 0.8)


def s_inter(fl, x, y, cor=(0, 0, 0)):
    fl.circ((x, y), 2.6, cor, cor, 0.6)
    fl.linha([(x, y), (x + 6, y - 6)], cor, 0.8)


def s_dedicado(fl, x, y, cor=(0, 0, 0)):
    fl.poli([(x - 4.5, y + 4), (x + 4.5, y + 4), (x, y - 4.5)], cor, (1, 0.9, 0.7), 0.8)


def s_quadro(fl, x, y, cor=(0, 0, 0)):
    fl.ret((x - 9, y - 6, x + 9, y + 6), cor, (0.2, 0.2, 0.2), 0.8)
    fl.poli([(x - 9, y + 6), (x + 9, y - 6), (x + 9, y + 6)], cor, (1, 1, 1), 0.3)


def s_termo(fl, x, y, cor=VERM):
    fl.ret((x - 4, y - 4, x + 4, y + 4), cor, (1, 1, 1), 0.8)
    fl.t(x, y + 2.6, "T", 6, cor, True, True)


def s_aparelho(fl, x, y, t, sc):
    w = {"banheira": (1.6, 0.7), "chuveiro": (0.9, 0.9), "autoclismo": (0.38, 0.55), "lavatorio": (0.5, 0.4), "lava_loica": (0.6, 0.45), "tanque": (0.5, 0.45),
         "maquina_lavar_roupa": (0.6, 0.6), "maquina_secar": (0.6, 0.6), "maquina_lavar_loica": (0.6, 0.6)}.get(t, (0.5, 0.5))
    a, b = w[0] * sc / 2, w[1] * sc / 2
    fl.ret((x - a, y - b, x + a, y + b), (0.2, 0.2, 0.2), (0.96, 0.98, 1.0), 0.8)
    if t == "chuveiro":
        fl.linha([(x - a, y - b), (x + a, y + b)], (0.4, 0.4, 0.4), 0.4)
        fl.linha([(x - a, y + b), (x + a, y - b)], (0.4, 0.4, 0.4), 0.4)
    elif t in ("autoclismo", "lavatorio", "lava_loica", "tanque", "banheira"):
        fl.circ((x, y), min(a, b) * 0.6, (0.4, 0.4, 0.4), None, 0.5)
    elif t.startswith("maquina"):
        fl.circ((x, y), min(a, b) * 0.65, (0.4, 0.4, 0.4), None, 0.6)


def s_tq(fl, x, y, cor=CAST):
    fl.circ((x, y), 6, cor, (1, 0.95, 0.85), 1.2)
    fl.circ((x, y), 2, cor, cor, 0.5)


# ---------------------------------------------------------------- utilitários de traçado
def _orto(p, a, b, cor, w=0.9, dash=None, prim="x"):
    if prim == "x":
        pts = [a, (b[0], a[1]), b]
    else:
        pts = [a, (a[0], b[1]), b]
    p.lin(pts, cor, w, dash)


def _ao_longo(d, n, porta=None, off=0.15):
    """n pontos igualmente espaçados no perímetro interior da divisão (evitando a porta)."""
    x0, y0, x1, y1 = d["x0"] + off, d["y0"] + off, d["x1"] - off, d["y1"] - off
    per = 2 * ((x1 - x0) + (y1 - y0))

    def ponto(t):
        t %= per
        for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            Lg = abs(bx - ax) + abs(by - ay)
            if t <= Lg:
                f = t / Lg if Lg else 0
                return (ax + (bx - ax) * f, ay + (by - ay) * f)
            t -= Lg
        return (x0, y0)
    out, t, passo = [], per / (2 * n), per / n
    for i in range(n):
        q = ponto(t + i * passo)
        if porta and abs(q[0] - porta[0]) + abs(q[1] - porta[1]) < 0.7:
            q = ponto(t + i * passo + 0.8)
        out.append(q)
    return out


def _tags(el):
    tags, por_div = {}, {}
    nl = ns = nd = 0
    for c in el["circuitos"]:
        if c["familia"] == "iluminacao":
            nl += 1
            t = f"L{nl}"
        elif c["familia"] == "tomadas":
            ns += 1
            t = f"S{ns}"
        else:
            nd += 1
            t = f"D{nd}"
        tags[id(c)] = t
        c["_tag"] = t
        for dv in c.get("divisoes") or []:
            por_div.setdefault(dv, []).append(t)
    return por_div


NOME_CIRC = {"Placa / fogão trifásico": ("Hob 3-phase", "Варильна поверхня 3ф"), "Placa / fogão": ("Hob", "Варильна поверхня"), "Forno": ("Oven", "Духова шафа"),
             "Máquina de lavar roupa": ("Washing machine", "Пральна машина"), "Máquina de lavar loiça": ("Dishwasher", "Посудомийна машина"),
             "Máquina de secar": ("Dryer", "Сушильна машина"), "Bomba de calor trifásica": ("Heat pump 3-phase", "Тепловий насос 3ф"),
             "Bomba de calor": ("Heat pump", "Тепловий насос"), "Apoio elétrico da bomba de calor trifásico": ("Heat-pump backup heater 3-phase", "Резервний ТЕН ТН 3ф"),
             "Apoio elétrico da bomba de calor": ("Heat-pump backup heater", "Резервний ТЕН ТН")}


def _nome_circ(c):
    nm = c["nome"]
    if nm.startswith("Iluminação"):
        return L("Lighting ", "Освітлення ") + nm.split()[-1]
    if nm.startswith("Tomadas"):
        return L("Sockets ", "Розетки ") + nm.split()[-1]
    a = NOME_CIRC.get(nm)
    return (a[1] if LANG.get() == "uk" else a[0]) if a else nm


# ---------------------------------------------------------------- EL — plantas
def _f_el(doc, m, r, cota, num, fmt, s, k, n, tot, data):
    fl, p, bb = _base(doc, m, r, cota, num, L("ELECTRICAL LAYOUT", "ЕЛЕКТРООБЛАДНАННЯ"),
                      L(f"Sockets, lighting, switches, dedicated points and circuits · scale 1:{k} · HD 60364 / IEC 60364 (ДСТУ HD 60364), ДБН В.2.5-23",
                        f"Розетки, освітлення, вимикачі, окремі лінії та групи · масштаб 1:{k} · ДСТУ HD 60364, ДБН В.2.5-23"), fmt, s, k, n, tot, data)
    el = r["eletricidade"]
    por_div = _tags(el)
    pts = {x["divisao"]: x for x in el["pontos"]}
    q = r["mep"].get("quadro") or {}
    Q = p.P(q.get("x", 0), q.get("y", 0))
    for d in [x for x in r["divisoes"] if abs(x["cota"] - cota) < 0.05]:
        pt = pts.get(d["id"])
        if not pt:
            continue
        cx, cy = centro(d)
        lx = d["x1"] - d["x0"] > d["y1"] - d["y0"]
        luzes = [(cx, cy)] if pt["pontos_luz"] == 1 else [((d["x0"] + (d["x1"] - d["x0"]) * f, cy) if lx else (cx, d["y0"] + (d["y1"] - d["y0"]) * f))
                                                          for f in [(i + 0.5) / pt["pontos_luz"] for i in range(pt["pontos_luz"])]]
        tg = por_div.get(d["id"], [])
        lt = next((t for t in tg if t.startswith("L")), "L")
        st = next((t for t in tg if t.startswith("S")), "S")
        porta = d.get("porta")
        for (x, y) in luzes:
            a = p.P(x + (min(0.9, max(0.0, (d["x1"] - d["x0"]) / 2 - 0.35)) if pt["pontos_luz"] == 1 else 0), y - min(0.75, (d["y1"] - d["y0"]) / 2 - 0.2))
            s_luz(fl, a[0], a[1])
        if porta:
            sx = porta[0] + (0.3 if porta[0] < d["x1"] - 0.3 else -0.3)
            sy = porta[1] + (0.3 if porta[1] < d["y1"] - 0.3 else -0.3)
            a = p.P(sx, sy)
            s_inter(fl, a[0], a[1])
            b = p.P(luzes[0][0] + (min(0.9, max(0.0, (d["x1"] - d["x0"]) / 2 - 0.35)) if pt["pontos_luz"] == 1 else 0), luzes[0][1] - min(0.75, (d["y1"] - d["y0"]) / 2 - 0.2))
            fl.linha([a, (a[0], b[1]), b], (0.2, 0.2, 0.2), 0.4, "[2 2] 0")
        for (x, y) in _ao_longo(d, pt["tomadas"], porta):
            a = p.P(x, y)
            s_tomada(fl, a[0], a[1])
        _rotulo(p, d, [f"{lt} · {st}", L(f"{pt['tomadas']} sockets · {pt['pontos_luz']} lights", f"{pt['tomadas']} розет. · {pt['pontos_luz']} світ.")])
        # linha de alimentação (home run) até ao quadro ou à coluna montante
        a = p.P(cx - 0.6, cy - 0.6)
        cor = CORES_CIRC[hash(d["id"]) % len(CORES_CIRC)]
        fl.linha([a, (Q[0], a[1]), Q], cor, 0.55, "[5 2] 0")
        for ap in d.get("aparelhos") or []:
            if ap["tipo"].startswith("maquina"):
                b = p.P(ap["x"] - 0.35, ap["y"])
                s_dedicado(fl, b[0], b[1])
                c = next((c for c in el["circuitos"] if _ap(ap["tipo"]).lower()[:5] in _nome_circ(c).lower()), None)
                fl.t(b[0] + 7, b[1] + 3, c["_tag"] if c else "D", 6.5, VERM, True)
        if d["tipo"] == "cozinha":
            for nm, dy in (("Placa", 1.2), ("Forno", 1.8)):
                b = p.P(d["x1"] - 0.4, d["y0"] + 1.0 + dy)
                s_dedicado(fl, b[0], b[1])
                c = next((c for c in el["circuitos"] if c["nome"].startswith(nm)), None)
                fl.t(b[0] - 26, b[1] + 3, (c["_tag"] + " " + _nome_circ(c)) if c else nm, 6.2, VERM, True)
    if abs(q.get("cota", 0) - cota) < 0.05:
        s_quadro(fl, Q[0], Q[1])
        fl.t(Q[0] + 12, Q[1] - 8, L("MDB — main distribution board", "ЩР — щит розподільчий"), 7.5, (0, 0, 0), True)
    else:
        s_quadro(fl, Q[0], Q[1])
        fl.t(Q[0] + 12, Q[1] - 8, L("riser to MDB (ground floor)", "стояк до ЩР (1-й поверх)"), 7, G.CINZA, True)
    ue = r["mep"].get("unidade_exterior")
    if ue and abs(cota) < 0.05:
        a = p.P(ue["x"], ue["y"])
        fl.ret((a[0] - 18, a[1] - 10, a[0] + 18, a[1] + 10), (0, 0, 0), (0.85, 0.92, 1), 0.8)
        fl.circ(a, 7, (0, 0, 0), None, 0.6)
        c = next((c for c in el["circuitos"] if c["nome"].startswith("Bomba de calor")), None)
        fl.t(a[0] + 22, a[1] + 3, L("Heat-pump outdoor unit", "Зовн. блок ТН") + (f" · {c['_tag']}" if c else ""), 7, (0, 0, 0), True)
    cen = r["mep"].get("central")
    if cen and abs(cen["cota"] - cota) < 0.05:
        a = p.P(cen["x"], cen["y"])
        fl.ret((a[0] - 16, a[1] - 12, a[0] + 16, a[1] + 12), (0, 0, 0), (1, 0.93, 0.85), 0.8)
        c = next((c for c in el["circuitos"] if c["nome"].startswith("Apoio")), None)
        fl.t(a[0] + 20, a[1] + 3, L("Hydro module + backup heater", "Гідромодуль + ТЕН") + (f" · {c['_tag']}" if c else ""), 7, (0, 0, 0), True)
    xl = G._lado(fl)
    y = _legenda(fl, xl, 140, [(s_tomada, L("Socket 2P+E 16 A, h = 0.30 m (wet rooms ≥ 0.6 m from water, IP44)", "Розетка 2P+E 16 А, h = 0,30 м (санвузли IP44, ≥ 0,6 м від води)")),
                                (s_luz, L("Ceiling light point", "Світильник стельовий")),
                                (s_inter, L("Switch h = 1.10 m", "Вимикач h = 1,10 м")),
                                (s_dedicado, L("Dedicated outlet / connection (own circuit)", "Окрема лінія / підключення")),
                                (s_quadro, L("Distribution board", "Розподільчий щит")),
                                (lambda f, x, yy: f.linha([(x - 9, yy), (x + 9, yy)], CORES_CIRC[0], 0.8, "[5 2] 0"), L("Circuit run to board (in conduit)", "Траса до щита (у гофротрубі)"))],
                 L("LEGEND", "УМОВНІ ПОЗНАЧЕННЯ"))
    rows = []
    for d in [x for x in r["divisoes"] if abs(x["cota"] - cota) < 0.05]:
        pt = pts.get(d["id"])
        if pt:
            rows.append([d["id"], _nome(d)[:26], str(pt["tomadas"]), str(pt["pontos_luz"]), " ".join(por_div.get(d["id"], []))])
    y = fl.tabela(xl, y + 20, [L("Room", "Прим."), L("Name", "Назва"), L("Sockets", "Розетки"), L("Lights", "Світ."), L("Circuits", "Групи")], rows, [55, 220, 70, 60, 200])
    fl.caixa(xl, y + 18, 610, L("Notes: cables Cu 3G1.5 (lighting) / 3G2.5 (sockets, appliances) / 5G2.5 (3-phase) in flexible conduit inside the CLT linings "
                                 "(no chasing of CLT panels); all socket circuits on 30 mA RCDs; earthing TN-C-S or TT with Ra ≤ 30 Ω, main equipotential "
                                 "bonding of water / heating pipes; positions to be confirmed with the interior design.",
                                 "Примітки: кабель Cu 3×1,5 (освітлення) / 3×2,5 (розетки, техніка) / 5×2,5 (3ф) у гофротрубі в обшивці стін CLT "
                                 "(без штроблення панелей CLT); усі розеткові групи через ПЗВ 30 мА; заземлення TN-C-S або TT з Ra ≤ 30 Ом, основна система "
                                 "зрівнювання потенціалів труб водопостачання та опалення; розташування уточнити за дизайн-проєктом."), 8)
    _cartucho(fl, m, L("Electrical installation", "Електропостачання"), num, n, tot, k, data)


def _f_unifilar(doc, m, r, num, n, tot, data):
    fl = G._Folha(doc, "A1")
    el = r["eletricidade"]
    _tags(el)
    fl.t(40, 52, f"{num} · {L('SINGLE-LINE DIAGRAM OF THE MAIN BOARD', 'ОДНОЛІНІЙНА СХЕМА ЩИТА РОЗПОДІЛЬЧОГО')}", 20, G.VERDE, True)
    fl.t(40, 74, L(f"3-phase 400/230 V supply · estimated demand {_n(el['potencia_estimada_w'] / 1000, 1)} kW · requested capacity ≈ {_n(el['potencia_contratada_kva'], 1)} kVA",
                   f"Живлення 3ф 400/230 В · розрахункове навантаження {_n(el['potencia_estimada_w'] / 1000, 1)} кВт · дозволена потужність ≈ {_n(el['potencia_contratada_kva'], 1)} кВА"),
         10, G.CINZA)
    x0, y0 = 120, 230
    fl.ret((x0 - 40, y0 - 70, x0 + 40, y0 - 30), (0, 0, 0), (0.95, 0.95, 0.95), 0.8)
    fl.t(x0, y0 - 46, L("Meter", "Лічильник"), 8, (0, 0, 0), True, True)
    fl.linha([(x0, y0 - 30), (x0, y0)], (0, 0, 0), 1.6)
    fl.ret((x0 - 22, y0, x0 + 22, y0 + 30), (0, 0, 0), (1, 1, 1), 1.0)
    fl.t(x0, y0 + 19, f"{int(math.ceil(float(el.get('corrente_contrato_a') or 63)))} A 4P", 7.5, (0, 0, 0), True, True)
    fl.t(x0 + 28, y0 + 19, L("main switch + SPD type 2", "ввідний вимикач + УЗІП тип 2"), 7.5)
    bus_y = y0 + 70
    fl.linha([(x0, y0 + 30), (x0, bus_y)], (0, 0, 0), 1.6)
    difs = el.get("diferenciais_lista") or []
    circs = el["circuitos"]
    # agrupar circuitos pelos diferenciais (por ordem)
    grupos, usados = [], set()
    for dfc in difs:
        lst = dfc.get("circuitos") or []
        nomes = {(x.get("nome") if isinstance(x, dict) else x) for x in lst} if isinstance(lst, list) else set()
        cs = [c for c in circs if c["nome"] in nomes and id(c) not in usados]
        usados.update(id(c) for c in cs)
        grupos.append((dfc, cs))
    resto = [c for c in circs if id(c) not in usados]
    if resto:
        grupos.append(({"tipo": "—", "calibre": "—"}, resto))
    largura = 112
    total_c = sum(len(g[1]) for g in grupos)
    xa = x0 + 80
    fl.linha([(x0, bus_y), (xa + total_c * largura, bus_y)], (0, 0, 0), 2.2)
    xc = xa
    for dfc, cs in grupos:
        if not cs:
            continue
        xm = xc + (len(cs) * largura) / 2 - largura / 2
        fl.linha([(xm, bus_y), (xm, bus_y + 30)], (0, 0, 0), 1.2)
        fl.ret((xm - 26, bus_y + 30, xm + 26, bus_y + 70), VERM, (1, 0.95, 0.95), 1.0)
        fl.t(xm, bus_y + 47, L(f"RCD {dfc.get('calibre')} A", f"ПЗВ {dfc.get('calibre')} А"), 7.5, VERM, True, True)
        fl.t(xm, bus_y + 61, f"30 mA {L('type', 'тип')} {dfc.get('tipo')}", 7, VERM, False, True)
        sub = bus_y + 100
        fl.linha([(xm, bus_y + 70), (xm, sub)], (0, 0, 0), 1.0)
        fl.linha([(xc, sub), (xc + (len(cs) - 1) * largura, sub)], (0, 0, 0), 1.4)
        for c in cs:
            fl.linha([(xc, sub), (xc, sub + 30)], (0, 0, 0), 0.9)
            fl.ret((xc - 18, sub + 30, xc + 18, sub + 62), (0, 0, 0), (1, 1, 1), 0.9)
            fl.t(xc, sub + 44, f"C{c['disjuntor']}", 8, (0, 0, 0), True, True)
            fl.t(xc, sub + 56, "3P" if c.get("b") == 3 else "1P+N", 6.5, G.CINZA, False, True)
            fl.linha([(xc, sub + 62), (xc, sub + 250)], (0, 0, 0), 0.9)
            fl.poli([(xc - 4, sub + 244), (xc + 4, sub + 244), (xc, sub + 252)], (0, 0, 0), (0, 0, 0), 0.5)
            fl.t(xc + 4, sub + 245, f"{c['_tag']} · {_nome_circ(c)}"[:34], 7.2, (0, 0, 0), True, False, rot=90)
            sec = f"{'5G' if c.get('b') == 3 else '3G'}{G._c(c['seccao'], 1)} mm²"
            fl.t(xc - 8, sub + 245, f"{sec} · {_n(c['comprimento_m'], 0)} m · ΔU {_n(c['du'], 2)} %", 6.5, G.CINZA, False, False, rot=90)
            xc += largura
    rows = [[c["_tag"], _nome_circ(c)[:30], f"{'5G' if c.get('b') == 3 else '3G'}{G._c(c['seccao'], 1)}", f"C{c['disjuntor']}", str(c.get("pontos") or "—"),
             _n(c["comprimento_m"], 0), _n(c["du"], 2), (" ".join(c.get("divisoes") or []))[:30]] for c in circs]
    fl.tabela(80, 740, [L("Circuit", "Група"), L("Description", "Опис"), L("Cable mm²", "Кабель мм²"), L("MCB", "Автомат"), L("Points", "Точок"),
                        L("L (m)", "L (м)"), "ΔU %", L("Rooms", "Приміщення")], rows, [60, 230, 90, 70, 60, 60, 60, 300])
    fl.caixa(1300, 740, 900, L("Board: IP40 flush-mounted, ≥ 20 % spare modules; type-2 surge protection; main earthing terminal with bonding to water, heating and "
                               "CLT steel connectors where accessible; ΔU ≤ 3 % lighting / 5 % other circuits from the meter (HD 60364-5-52); circuit lengths measured "
                               "on the plans from the board to the farthest room served.",
                               "Щит: IP40 врізний, ≥ 20 % резервних модулів; УЗІП тип 2; головна заземлювальна шина зі з'єднанням труб водопостачання, опалення "
                               "та сталевих з'єднувачів CLT у доступних місцях; ΔU ≤ 3 % освітлення / 5 % інші групи від лічильника (HD 60364-5-52); довжини груп "
                               "виміряно по кресленнях від щита до найвіддаленішого приміщення."), 8.5)
    _cartucho(fl, m, L("Electrical — single-line diagram", "Електрика — однолінійна схема"), num, n, tot, None, data)


# ---------------------------------------------------------------- WS — águas e esgotos
def _dn(rede, nome):
    for t in (rede or {}).get("trocos", []):
        if t["nome"] == nome:
            return t.get("dn")
    return None


def _f_ws(doc, m, r, cota, num, fmt, s, k, n, tot, data):
    fl, p, bb = _base(doc, m, r, cota, num, L("WATER SUPPLY AND DRAINAGE", "ВОДОПОСТАЧАННЯ ТА КАНАЛІЗАЦІЯ"),
                      L(f"Cold / hot water (PE-Xa / multilayer), drainage (PP / PVC), stacks and collector · scale 1:{k} · EN 806, EN 12056, ДБН В.2.5-64",
                        f"Холодна / гаряча вода (PE-Xa / металопластик), каналізація (PP / ПВХ), стояки та колектор · масштаб 1:{k} · EN 806, EN 12056, ДБН В.2.5-64"),
                      fmt, s, k, n, tot, data)
    mep = r["mep"]
    can = r["canalizacao"]
    col = mep.get("coluna_agua")
    C = (col["x"], col["y"])
    z0 = min(x["cota"] for x in r["divisoes"])
    for d in [x for x in r["divisoes"] if abs(x["cota"] - cota) < 0.05]:
        _rotulo(p, d, dy=0.6 if d.get("aparelhos") else 0.0)
    for f in [f for f in r["aparelhos"] if abs(f["div"]["cota"] - cota) < 0.05]:
        a = f["a"]
        A = p.P(a["x"], a["y"])
        s_aparelho(fl, A[0], A[1], a["tipo"], s)
        dn = _dn(can.get("rede"), f["tag"])
        _orto(p, C, (a["x"], a["y"]), AZUL, 1.0, None, "y")
        quente = any(t["nome"] == "q" + f["tag"] for t in r["rede_aq"])
        if quente:
            _orto(p, (C[0] + 0.12, C[1] + 0.12), (a["x"] + 0.12, a["y"] + 0.12), VERM, 1.0, None, "y")
        pr = next(t for t in mep["prumadas"] if t["id"] == f["prumada"])
        dd = _dn(can.get("rede_drenagem"), "r" + f["tag"])
        _orto(p, (a["x"], a["y"]), (pr["x"], pr["y"]), CAST, 1.6, "[6 2] 0", "x")
        fl.t(A[0] + 8, A[1] - 7, f"{_ap(a['tipo'])}", 6.3, (0.2, 0.2, 0.2), True)
        fl.t(A[0] + 8, A[1] + 2, f"AF Ø{dn or 16}" + (" · AQ Ø16" if quente else "") + (f" · Ø{dd}" if dd else ""), 6, G.CINZA)
    usados = {f["prumada"] for f in r["aparelhos"]}
    for t in mep.get("prumadas") or []:
        if t["id"] not in usados:
            continue
        z_top = max(f["div"]["cota"] for f in r["aparelhos"] if f["prumada"] == t["id"])
        if cota > z_top + 0.05:
            continue
        a = p.P(t["x"], t["y"])
        s_tq(fl, a[0], a[1])
        dn = _dn(can.get("rede_drenagem"), t["id"])
        fl.t(a[0] + 9, a[1] - 4, f"{t['id']} Ø{dn or 110}", 7.5, CAST, True)
    a = p.P(*C)
    fl.circ(a, 6, AZUL, (0.85, 0.92, 1), 1.2)
    fl.t(a[0] - 70, a[1] + 16, L("Risers CW / HW", "Стояки В1 / Т3"), 7, AZUL, True)
    if abs(cota - z0) < 0.05:
        ent = mep.get("entrada_agua")
        if ent:
            b = p.P(ent["x"], ent["y"])
            fl.ret((b[0] - 10, b[1] - 7, b[0] + 10, b[1] + 7), AZUL, (1, 1, 1), 1.0)
            fl.t(b[0] - 70, b[1] - 12, L("Water inlet + meter", "Ввід водопроводу + водомір"), 7, AZUL, True)
            _orto(p, (ent["x"], ent["y"]), C, AZUL, 1.8, None, "x")
        cen = mep.get("central")
        if cen:
            b = p.P(cen["x"], cen["y"])
            fl.circ(b, 14, VERM, (1, 0.93, 0.9), 1.2)
            fl.t(b[0], b[1] + 3, L("DHW", "ГВП"), 7.5, VERM, True, True)
            fl.t(b[0] + 18, b[1] + 3, L(f"DHW cylinder {r['quantidades']['aqs_l']} L (heat pump)", f"Бойлер ГВП {r['quantidades']['aqs_l']} л (ТН)"), 7, VERM, True)
            _orto(p, (cen["x"], cen["y"]), (C[0] + 0.12, C[1] + 0.12), VERM, 1.8, None, "y")
        said = mep.get("saida_esgoto")
        if said:
            for t in mep.get("prumadas") or []:
                if t["id"] in usados:
                    _orto(p, (t["x"], t["y"]), (said["x"], said["y"]), CAST, 2.4, "[10 3] 0", "y")
            b = p.P(said["x"], said["y"])
            fl.t(b[0] + 6, b[1] - 6, L(f"Building drain Ø{can['coletor_mm']} → public sewer / septic (invert to confirm)",
                                       f"Випуск Ø{can['coletor_mm']} → зовнішня мережа (позначку лотка уточнити)"), 7, CAST, True)
        if r["quantidades"].get("estacao_elevatoria"):
            fx = [f for f in r["aparelhos"] if abs(f["div"]["cota"] - cota) < 0.05]
            if fx:
                b = p.P(fx[0]["a"]["x"] - 0.8, fx[0]["a"]["y"] - 0.8)
                fl.ret((b[0] - 9, b[1] - 9, b[0] + 9, b[1] + 9), CAST, (1, 0.9, 0.8), 1.0)
                fl.t(b[0] + 12, b[1] + 3, L("Sewage pumping unit (basement fixtures)", "КНС (прилади підвалу)"), 7, CAST, True)
    xl = G._lado(fl)
    y = _legenda(fl, xl, 140, [(lambda f, x, yy: f.linha([(x - 9, yy), (x + 9, yy)], AZUL, 1.2), L("Cold water (CW) — PE-Xa / multilayer", "Холодна вода В1 — PE-Xa / металопластик")),
                                (lambda f, x, yy: f.linha([(x - 9, yy), (x + 9, yy)], VERM, 1.2), L("Hot water (HW) — insulated 9 mm", "Гаряча вода Т3 — в ізоляції 9 мм")),
                                (lambda f, x, yy: f.linha([(x - 9, yy), (x + 9, yy)], CAST, 1.6, "[6 2] 0"), L("Drainage branch PP, slope 2 %", "Відвідна лінія PP, ухил 2 %")),
                                (s_tq, L("Soil stack (vent to roof ≥ 0.5 m)", "Каналізаційний стояк (вентиляція ≥ 0,5 м над покрівлею)"))],
                 L("LEGEND", "УМОВНІ ПОЗНАЧЕННЯ"))
    rows = []
    for f in [f for f in r["aparelhos"] if abs(f["div"]["cota"] - cota) < 0.05]:
        rows.append([f["tag"], _ap(f["a"]["tipo"])[:22], f"Ø{_dn(can.get('rede'), f['tag']) or 16}",
                     f"Ø{_dn(can.get('rede'), 'q' + f['tag'])}" if _dn(can.get("rede"), "q" + f["tag"]) else "—",
                     f"Ø{_dn(can.get('rede_drenagem'), 'r' + f['tag']) or '—'}", f["prumada"]])
    if rows:
        y = fl.tabela(xl, y + 20, [L("Point", "Точка"), L("Fixture", "Прилад"), L("CW", "В1"), L("HW", "Т3"), L("Waste", "Злив"), L("Stack", "Стояк")],
                      rows, [70, 190, 70, 70, 80, 70])
    fl.caixa(xl, y + 18, 610, L("Notes: pipes run in the screed / service voids, never through CLT floor panels except in the planned shafts (sleeves + fire collar "
                                 "EI 60); WC branches Ø110 / Ø90 max. 1 m before the stack; check valves and pressure reducer after the meter; thermostatic "
                                 "mixing valve at the DHW outlet (storage ≥ 60 °C against legionella).",
                                 "Примітки: труби прокладаються у стяжці / технічних порожнинах, через панелі CLT — лише в запроєктованих шахтах (гільзи + "
                                 "протипожежні манжети EI 60); відводи від унітазів Ø110 / Ø90 до стояка ≤ 1 м; після водоміра — зворотний клапан і редуктор тиску; "
                                 "термостатичний змішувач на виході ГВП (зберігання ≥ 60 °C проти легіонели)."), 8)
    _cartucho(fl, m, L("Water supply and drainage", "Водопостачання і каналізація"), num, n, tot, k, data)


def _f_ws_esquema(doc, m, r, num, n, tot, data):
    fl = G._Folha(doc, "A1")
    can = r["canalizacao"]
    fl.t(40, 52, f"{num} · {L('VERTICAL SCHEMATIC — WATER SUPPLY AND DRAINAGE', 'АКСОНОМЕТРИЧНА СХЕМА — ВОДОПОСТАЧАННЯ ТА КАНАЛІЗАЦІЯ')}", 20, G.VERDE, True)
    fl.t(40, 74, L(f"Design flow CW {_n(can['qc_l_s'], 2)} L/s ({_n(can['qa_l_s'], 2)} L/s installed) · residual pressure at the worst point {_n(can['pressao_kpa'], 0)} kPa · "
                   f"stacks Ø{can['tubo_queda_mm']} · building drain Ø{can['coletor_mm']}",
                   f"Розрахункова витрата В1 {_n(can['qc_l_s'], 2)} л/с (встановлена {_n(can['qa_l_s'], 2)} л/с) · залишковий тиск у найвіддаленішій точці "
                   f"{_n(can['pressao_kpa'], 0)} кПа · стояки Ø{can['tubo_queda_mm']} · випуск Ø{can['coletor_mm']}"), 10, G.CINZA)
    cotas = sorted({d["cota"] for d in r["divisoes"]})
    z0, z1 = cotas[0], cotas[-1]
    yb, sc = 980, 150.0
    Y = lambda z: yb - (z - z0) * sc      # noqa: E731
    xr = 160
    for c in cotas:
        fl.linha([(80, Y(c)), (2250, Y(c))], CINZA_C, 0.5, "[8 4] 0")
        nv = next((x for x in r["niveis"] if abs(x["cota"] - c) < 0.05), None)
        fl.t(84, Y(c) - 5, f"{(nv['uk'] if LANG.get() == 'uk' else nv['en']) if nv else ''} {G._cota_txt(c)}", 8, G.CINZA, True)
    # colunas AF / AQ
    fl.linha([(xr, Y(z0) + 40), (xr, Y(z1) - 60)], AZUL, 2.2)
    fl.linha([(xr + 14, Y(z0) + 10), (xr + 14, Y(z1) - 60)], VERM, 2.2)
    fl.t(xr - 30, Y(z1) - 70, L("CW / HW risers", "Стояки В1 / Т3"), 8, (0, 0, 0), True)
    fl.ret((xr - 16, Y(z0) + 40, xr + 16, Y(z0) + 60), AZUL, (1, 1, 1), 1)
    fl.t(xr + 22, Y(z0) + 54, L("Meter + check valve + PRV", "Водомір + зворотний клапан + редуктор"), 7.5, AZUL)
    xx = xr + 120
    for c in cotas:
        fx = [f for f in r["aparelhos"] if abs(f["div"]["cota"] - c) < 0.05]
        divs = []
        for f in fx:
            if f["div"]["id"] not in [d["id"] for d in divs]:
                divs.append(f["div"])
        x = xx
        fl.linha([(xr, Y(c) - 30), (x + max(1, len(fx)) * 70 + 40 * len(divs), Y(c) - 30)], AZUL, 1.2)
        fl.linha([(xr + 14, Y(c) - 22), (x + max(1, len(fx)) * 70 + 40 * len(divs), Y(c) - 22)], VERM, 1.2)
        for d in divs:
            fl.t(x, Y(c) - 110, f"{d['id']} {_nome(d)}"[:26], 7.5, G.VERDE, True)
            for f in [f for f in fx if f["div"]["id"] == d["id"]]:
                fl.linha([(x, Y(c) - 30), (x, Y(c) - 62)], AZUL, 1.0)
                if any(t["nome"] == "q" + f["tag"] for t in r["rede_aq"]):
                    fl.linha([(x + 8, Y(c) - 22), (x + 8, Y(c) - 62)], VERM, 1.0)
                fl.ret((x - 12, Y(c) - 82, x + 20, Y(c) - 62), (0.2, 0.2, 0.2), (0.96, 0.98, 1), 0.8)
                fl.t(x + 4, Y(c) - 88, _ap(f["a"]["tipo"])[:14], 6.3, (0.2, 0.2, 0.2), False, True)
                fl.t(x + 4, Y(c) - 68, f"Ø{_dn(can.get('rede'), f['tag']) or 16}", 6, AZUL, True, True)
                fl.linha([(x + 4, Y(c) - 62 + 20), (x + 4, Y(c) - 8)], CAST, 1.4, "[5 2] 0")
                x += 70
            x += 40
        xx = xr + 120
    # tubos de queda
    xs = 1500
    usados = sorted({f["prumada"] for f in r["aparelhos"]})
    for i, tq in enumerate(usados):
        x = xs + i * 120
        ztop = max(f["div"]["cota"] for f in r["aparelhos"] if f["prumada"] == tq)
        fl.linha([(x, Y(z0) + 60), (x, Y(ztop) - 160)], CAST, 3.0)
        fl.t(x - 14, Y(ztop) - 168, f"{tq} Ø{_dn(can.get('rede_drenagem'), tq) or 110}", 8, CAST, True)
        fl.t(x + 5, Y(ztop) - 130, L("vent", "вент."), 6.5, CAST)
        nfx = sum(1 for f in r["aparelhos"] if f["prumada"] == tq)
        fl.t(x + 5, Y(z0) + 50, f"{nfx} {L('fixtures', 'прил.')}", 6.5, CAST)
    fl.linha([(xs, Y(z0) + 60), (xs + (len(usados) - 1) * 120 + 140, Y(z0) + 60)], CAST, 3.4)
    fl.t(xs, Y(z0) + 78, L(f"Building drain Ø{can['coletor_mm']}, slope ≥ 1.5 % → public sewer", f"Випуск Ø{can['coletor_mm']}, ухил ≥ 1,5 % → зовнішня мережа"), 8, CAST, True)
    rows = [[t["nome"], "AF" if t.get("agua") == "fria" else "AQ", _n(t["comprimento_m"], 1), _n(t["qc_l_s"], 2), f"Ø{t['dn']}", _n(t["velocidade_m_s"], 2),
             _n(t["p_fim_kpa"], 0)] for t in (can.get("rede") or {}).get("trocos", []) if not t["nome"].startswith(("q", "-", "0", "1"))][:14]
    fl.tabela(80, 1150, [L("Section", "Ділянка"), L("Water", "Вода"), "L (m)", "Qc (L/s)", "DN", "v (m/s)", L("p end (kPa)", "p кін. (кПа)")], rows,
              [90, 60, 70, 80, 60, 70, 100])
    rows2 = [[t["nome"], {"ramal": L("branch", "відвід"), "tubo_queda": L("stack", "стояк"), "coletor": L("drain", "випуск")}.get(t["tipo"], t["tipo"]),
              _n(t["qc_l_min"], 0), f"Ø{t['dn']}", _n(t.get("inclinacao_pct") or 0, 1)] for t in (can.get("rede_drenagem") or {}).get("trocos", [])
             if t["tipo"] != "ramal"]
    fl.tabela(700, 1150, [L("Drain", "Ділянка"), L("Type", "Тип"), "Qc (L/min)", "DN", L("Slope %", "Ухил %")], rows2, [90, 90, 90, 60, 70])
    fl.caixa(1150, 1150, 1050, L("Method: instantaneous flows per fixture, simultaneity curve, Darcy–Weisbach losses (supply); discharge units, Manning–Strickler at half "
                                 "depth and stack occupancy (drainage) — ConstruPilot instalacoes engine; design to be verified by the plumbing engineer against "
                                 "ДБН В.2.5-64:2012 and EN 806-3 / EN 12056-2.",
                                 "Метод: секундні витрати приладів, крива одночасності, втрати Дарсі–Вейсбаха (водопостачання); витрати стоків, Маннінг–Стриклер "
                                 "при наповненні 0,5 та завантаження стояків (каналізація) — модуль ConstruPilot instalacoes; перевірити інженером ВК за "
                                 "ДБН В.2.5-64:2012 та EN 806-3 / EN 12056-2."), 8.5)
    _cartucho(fl, m, L("Water supply and drainage — schematic", "ВК — схема"), num, n, tot, None, data)


# ---------------------------------------------------------------- HT — aquecimento
def _meandro(p, x0, y0, x1, y1, passo, cor):
    """Serpentina (traçado indicativo) no retângulo, passo em m."""
    vert = (x1 - x0) < (y1 - y0)
    pts = []
    if vert:
        n = max(2, int((x1 - x0) / passo))
        for i in range(n + 1):
            x = x0 + i * (x1 - x0) / n
            pts += [(x, y0), (x, y1)] if i % 2 == 0 else [(x, y1), (x, y0)]
    else:
        n = max(2, int((y1 - y0) / passo))
        for i in range(n + 1):
            y = y0 + i * (y1 - y0) / n
            pts += [(x0, y), (x1, y)] if i % 2 == 0 else [(x1, y), (x0, y)]
    p.lin(pts, cor, 0.45)
    return pts[0], pts[-1]


def _f_ht(doc, m, r, cota, num, fmt, s, k, n, tot, data):
    fl, p, bb = _base(doc, m, r, cota, num, L("HEATING — UNDERFLOOR HEATING", "ОПАЛЕННЯ — ВОДЯНА ТЕПЛА ПІДЛОГА"),
                      L(f"Heat losses per room (EN 12831), UFH loops (EN 1264), manifolds, room thermostats · scale 1:{k} · ДБН В.2.5-67:2013",
                        f"Тепловтрати приміщень (EN 12831), контури теплої підлоги (EN 1264), колектори, кімнатні термостати · масштаб 1:{k} · ДБН В.2.5-67:2013"),
                      fmt, s, k, n, tot, data)
    u = r["piso_radiante"].get(round(cota, 2))
    mep = r["mep"]
    if u:
        col = u["coletor"]
        Cp = (col["x"], col["y"])
        rows_d = {x["nome"]: x for x in u["divisoes"]}
        for d in [x for x in r["divisoes"] if abs(x["cota"] - cota) < 0.05]:
            rw = rows_d.get(d["id"])
            if not rw:
                _rotulo(p, d)
                continue
            nc = rw["circuitos"]
            ins = 0.2
            x0, y0, x1, y1 = d["x0"] + ins, d["y0"] + ins, d["x1"] - ins, d["y1"] - ins
            longo_x = (x1 - x0) >= (y1 - y0)
            for i in range(nc):
                if longo_x:
                    a0, a1 = x0 + (x1 - x0) * i / nc, x0 + (x1 - x0) * (i + 1) / nc
                    ini, fim = _meandro(p, a0 + 0.04, y0, a1 - 0.04, y1, rw["passo"] / 100 * 2, CORES_CIRC[i % len(CORES_CIRC)])
                else:
                    a0, a1 = y0 + (y1 - y0) * i / nc, y0 + (y1 - y0) * (i + 1) / nc
                    ini, fim = _meandro(p, x0, a0 + 0.04, x1, a1 - 0.04, rw["passo"] / 100 * 2, CORES_CIRC[i % len(CORES_CIRC)])
                _orto(p, ini, (Cp[0] - 0.05 * i, Cp[1]), VERM, 0.5, None, "y")
                _orto(p, fim, (Cp[0] + 0.05 * i, Cp[1] - 0.05), AZUL, 0.5, "[3 1] 0", "y")
            porta = d.get("porta")
            if porta:
                a = p.P(porta[0] + (0.35 if porta[0] < d["x1"] - 0.4 else -0.35), porta[1] + (0.45 if porta[1] < d["y1"] - 0.5 else -0.45))
                s_termo(fl, a[0], a[1])
            cx, cy = centro(d)
            q = p.P(cx, cy)
            fl.ret((q[0] - 62, q[1] - 22, q[0] + 62, q[1] + 22), (0.3, 0.3, 0.3), (1, 1, 1), 0.5)
            fl.t(q[0], q[1] - 11, f"{d['id']} · {_nome(d)}"[:30], 6.8, (0.1, 0.1, 0.1), True, True)
            fl.t(q[0], q[1] + 0, f"Φ {_n(r['phi'][d['id']], 0)} W · {G._c(rw['theta_int'], 0)} °C", 6.4, VERM, True, True)
            fl.t(q[0], q[1] + 11, L(f"{nc} loop{'s' if nc > 1 else ''} × {_n(rw['comprimento_circuito_m'], 0)} m · {rw['passo']} cm · {_n(rw['caudal_lh'], 0)} L/h",
                                    f"{nc} конт. × {_n(rw['comprimento_circuito_m'], 0)} м · крок {rw['passo']} см · {_n(rw['caudal_lh'], 0)} л/год"),
                 6.2, (0.2, 0.2, 0.2), False, True)
        a = p.P(*Cp)
        fl.ret((a[0] - 26, a[1] - 8, a[0] + 26, a[1] + 8), (0, 0, 0), (0.9, 0.9, 0.9), 1.0)
        fl.t(a[0], a[1] + 3, L(f"UFH manifold {u['circuitos']} outlets", f"Колектор ТП {u['circuitos']} вих."), 6.8, (0, 0, 0), True, True)
        fl.t(a[0] + 30, a[1] + 16, L(f"supply {_n(u['theta_ida'], 1)} °C / σ {_n(u['sigma'], 0)} K · {_n(u['caudal_total_lh'], 0)} L/h",
                                     f"подача {_n(u['theta_ida'], 1)} °C / σ {_n(u['sigma'], 0)} K · {_n(u['caudal_total_lh'], 0)} л/год"), 7, VERM, True)
    else:
        for d in [x for x in r["divisoes"] if abs(x["cota"] - cota) < 0.05]:
            _rotulo(p, d, L("unheated", "неопалюване"))
    cen = mep.get("central")
    if cen and abs(cen["cota"] - cota) < 0.05:
        a = p.P(cen["x"], cen["y"])
        bc = r["bomba_calor"]
        for i, (lab, w_) in enumerate(((L("Hydro module", "Гідромодуль"), 36), (L(f"DHW {r['quantidades']['aqs_l']} L", f"ГВП {r['quantidades']['aqs_l']} л"), 30),
                                       (L(f"Buffer {max(50, r['quantidades']['deposito_inercia_l'])} L", f"Буфер {max(50, r['quantidades']['deposito_inercia_l'])} л"), 26),
                                       (L(f"Exp. vessel {r['quantidades']['vaso_l']} L", f"Розшир. бак {r['quantidades']['vaso_l']} л"), 20))):
            x = a[0] - 80 + i * 52
            fl.ret((x, a[1] - 18, x + w_ + 10, a[1] + 18), VERM, (1, 0.95, 0.92), 0.9)
            fl.t(x + 2, a[1] + 30, lab, 6.4, VERM, True)
        fl.t(a[0] - 80, a[1] - 26, L(f"Plant room — air/water heat pump {bc['p_nominal_kw']} kW (A7/W35) + backup {G._c(bc.get('apoio_kw') or 0, 0)} kW",
                                     f"Котельня — ТН повітря/вода {bc['p_nominal_kw']} кВт (A7/W35) + ТЕН {G._c(bc.get('apoio_kw') or 0, 0)} кВт"), 7.5, VERM, True)
        col = mep.get("coluna_agua")
        for c in mep.get("coletores") or []:
            _orto(p, (cen["x"], cen["y"]), (col["x"] - 0.25, col["y"] - 0.25), VERM, 1.6, None, "y")
            _orto(p, (cen["x"] + 0.15, cen["y"]), (col["x"] - 0.1, col["y"] - 0.25), AZUL, 1.6, "[4 2] 0", "y")
        b = p.P(col["x"] - 0.25, col["y"] - 0.25)
        fl.t(b[0] - 120, b[1] + 14, L("heating risers to manifolds", "стояки опалення до колекторів"), 7, VERM, True)
    ue = mep.get("unidade_exterior")
    if ue and abs(cota) < 0.05:
        a = p.P(ue["x"], ue["y"])
        fl.ret((a[0] - 22, a[1] - 12, a[0] + 22, a[1] + 12), (0, 0, 0), (0.85, 0.92, 1), 0.9)
        fl.circ(a, 8, (0, 0, 0), None, 0.6)
        fl.t(a[0] + 26, a[1] + 3, L("Outdoor unit on anti-vibration feet, condensate to gravel", "Зовнішній блок на віброопорах, конденсат у гравій"), 7, (0, 0, 0), True)
    xl = G._lado(fl)
    y = _legenda(fl, xl, 140, [(lambda f, x, yy: f.linha([(x - 9, yy), (x + 9, yy)], VERM, 1.0), L("Flow", "Подача")),
                                (lambda f, x, yy: f.linha([(x - 9, yy), (x + 9, yy)], AZUL, 1.0, "[3 1] 0"), L("Return", "Зворотна")),
                                (lambda f, x, yy: f.linha([(x - 9, yy - 3), (x + 9, yy - 3), (x + 9, yy + 3), (x - 9, yy + 3)], CORES_CIRC[0], 0.6),
                                 L("UFH loop PE-Xa 16×2 with O₂ barrier (path indicative)", "Контур ТП PE-Xa 16×2 з кисневим бар'єром (траса умовна)")),
                                (s_termo, L("Room thermostat → manifold actuator", "Кімнатний термостат → сервопривод колектора"))],
                 L("LEGEND", "УМОВНІ ПОЗНАЧЕННЯ"))
    if u:
        rows = [[x["nome"], f"{_n(x['area_m2'], 1)}", _n(x["phi_w"], 0), _n(x["q"], 0), str(x["passo"]), str(x["circuitos"]), _n(x["comprimento_circuito_m"], 0),
                 _n(x["caudal_lh"], 0), _n(x["tf"], 1)] for x in u["divisoes"]]
        y = fl.tabela(xl, y + 20, [L("Room", "Прим."), "A m²", "Φ W", "q W/m²", L("e cm", "крок"), L("loops", "конт."), "L m", L("L/h", "л/год"), "θF °C"],
                      rows, [52, 58, 62, 62, 52, 52, 56, 62, 60])
    fl.caixa(xl, y + 18, 610, L("Build-up: CLT 240 + acoustic underlay + EPS/XPS ≥ R 0.75 (above heated) / ≥ R 1.25 (above basement) + PE film + UFH pipe + "
                                 "screed 45–65 mm + finish; edge strip on all walls; movement joints > 40 m² or > 8 m; pressure test 1.5 × working pressure "
                                 "before screeding; first heating per EN 1264-4.",
                                 "Пиріг: CLT 240 + звукоізоляція + ППС/XPS R ≥ 0,75 (над опалюваним) / R ≥ 1,25 (над підвалом) + плівка + труба ТП + стяжка "
                                 "45–65 мм + покриття; демпферна стрічка по периметру; деформаційні шви > 40 м² або > 8 м; опресування 1,5 × робочого тиску "
                                 "до заливки стяжки; перший запуск за EN 1264-4."), 8)
    _cartucho(fl, m, L("Heating — underfloor heating", "Опалення — тепла підлога"), num, n, tot, k, data)


def _f_ht_esquema(doc, m, r, num, n, tot, data):
    fl = G._Folha(doc, "A1")
    bc = r["bomba_calor"]
    per = r["perdas"]
    fl.t(40, 52, f"{num} · {L('HEATING PLANT — HYDRAULIC SCHEMATIC AND SCHEDULES', 'ТЕПЛОВИЙ ПУНКТ — ГІДРАВЛІЧНА СХЕМА ТА ТАБЛИЦІ')}", 20, G.VERDE, True)
    fl.t(40, 74, L(f"Design outdoor temperature {G._c(per['theta_e'], 0)} °C · heat loss {_n(r['phi_total_w'] / 1000, 1)} kW · heat pump {bc['p_nominal_kw']} kW nominal "
                   f"({_n(bc['p_theta_e_kw'], 1)} kW at θe) + backup {G._c(bc.get('apoio_kw') or 0, 0)} kW · bivalent point {_n(bc['bivalencia_c'], 1)} °C",
                   f"Розрахункова зовнішня температура {G._c(per['theta_e'], 0)} °C · тепловтрати {_n(r['phi_total_w'] / 1000, 1)} кВт · ТН {bc['p_nominal_kw']} кВт "
                   f"номін. ({_n(bc['p_theta_e_kw'], 1)} кВт при θe) + ТЕН {G._c(bc.get('apoio_kw') or 0, 0)} кВт · точка бівалентності {_n(bc['bivalencia_c'], 1)} °C"),
         10, G.CINZA)
    y0 = 300

    def bloco(x, y, w, h, t1, t2=None, cor=VERM, fill=(1, 0.95, 0.92)):
        fl.ret((x, y, x + w, y + h), cor, fill, 1.1)
        fl.t(x + w / 2, y + h / 2 - (3 if t2 else -3), t1, 8, (0, 0, 0), True, True)
        if t2:
            fl.t(x + w / 2, y + h / 2 + 11, t2, 7, G.CINZA, False, True)
    bloco(80, y0, 150, 80, L("Outdoor unit", "Зовнішній блок"), f"{bc['p_nominal_kw']} kW · R290/R32", (0, 0, 0), (0.88, 0.94, 1))
    bloco(320, y0, 160, 80, L("Hydro module", "Гідромодуль"), L(f"pump + backup {G._c(bc.get('apoio_kw') or 0, 0)} kW", f"насос + ТЕН {G._c(bc.get('apoio_kw') or 0, 0)} кВт"))
    bloco(560, y0 - 120, 150, 110, L(f"DHW cylinder {r['quantidades']['aqs_l']} L", f"Бойлер ГВП {r['quantidades']['aqs_l']} л"), L("coil + legionella cycle", "змійовик + цикл проти легіонели"))
    bloco(560, y0 + 60, 150, 90, L(f"Buffer {max(50, r['quantidades']['deposito_inercia_l'])} L", f"Буфер {max(50, r['quantidades']['deposito_inercia_l'])} л"),
          L("hydraulic separation", "гідророзділення"))
    bloco(820, y0 + 60, 140, 90, L("Mixing group", "Змішувальний вузол"), L(f"3-way + pump · {_n(max(u['theta_ida'] for u in r['piso_radiante'].values()), 1)} °C",
                                                                           f"3-ход. + насос · {_n(max(u['theta_ida'] for u in r['piso_radiante'].values()), 1)} °C"))
    x = 1060
    for c, u in sorted(r["piso_radiante"].items()):
        nv = next((z for z in r["niveis"] if abs(z["cota"] - c) < 0.05), {"en": "", "uk": ""})
        bloco(x, y0 + 60, 180, 90, L(f"Manifold {nv['en']}", f"Колектор — {nv['uk']}"),
              L(f"{u['circuitos']} loops · {_n(u['caudal_total_lh'], 0)} L/h", f"{u['circuitos']} конт. · {_n(u['caudal_total_lh'], 0)} л/год"), (0.2, 0.2, 0.2), (0.95, 0.95, 0.95))
        fl.linha([(960, y0 + 95), (x, y0 + 95)], VERM, 1.4)
        fl.linha([(960, y0 + 125), (x, y0 + 125)], AZUL, 1.4, "[4 2] 0")
        for i in range(min(u["circuitos"], 14)):
            xx = x + 10 + i * 12
            fl.linha([(xx, y0 + 150), (xx, y0 + 200)], CORES_CIRC[i % len(CORES_CIRC)], 0.8)
        x += 230
    fl.linha([(230, y0 + 30), (320, y0 + 30)], VERM, 1.6)
    fl.linha([(230, y0 + 55), (320, y0 + 55)], AZUL, 1.6, "[4 2] 0")
    fl.linha([(480, y0 + 30), (530, y0 + 30), (530, y0 - 65), (560, y0 - 65)], VERM, 1.4)
    fl.t(500, y0 - 72, L("3-way diverter", "3-ход. перемикач"), 6.5, VERM)
    fl.linha([(530, y0 + 30), (530, y0 + 105), (560, y0 + 105)], VERM, 1.4)
    fl.linha([(710, y0 + 105), (820, y0 + 105)], VERM, 1.4)
    fl.linha([(480, y0 + 55), (510, y0 + 55), (510, y0 + 135), (560, y0 + 135)], AZUL, 1.4, "[4 2] 0")
    fl.circ((420, y0 + 130), 14, VERM, (1, 1, 1), 1)
    fl.t(420, y0 + 160, L(f"Exp. vessel {r['quantidades']['vaso_l']} L", f"Розшир. бак {r['quantidades']['vaso_l']} л"), 7, VERM, False, True)
    fl.linha([(420, y0 + 116), (420, y0 + 80)], VERM, 0.8)
    for xx, lab in ((300, L("magnetic dirt separator", "магн. шламовідділювач")), (470, L("safety valve 3 bar", "запобіжний клапан 3 бар"))):
        fl.t(xx, y0 + 200, lab, 6.5, G.CINZA)
    rows = [[x["nome"], _tipo(x["tipo"])[:14], _n(x["area_m2"], 1), G._c(x["theta_int"], 0), _n(x["phi_T"], 0), _n(x["phi_V"], 0), _n(x["phi"], 0), _n(x["w_m2"], 0)]
            for x in per["divisoes"]]
    rows.append([L("Total", "Разом"), "", _n(sum(x["area_m2"] for x in per["divisoes"]), 1), "", _n(sum(x["phi_T"] for x in per["divisoes"]), 0),
                 _n(sum(x["phi_V"] for x in per["divisoes"]), 0), _n(r["phi_total_w"], 0), ""])
    fl.tabela(80, 640, [L("Room", "Прим."), L("Use", "Тип"), "A m²", "θi °C", "ΦT W", "ΦV W", "Φ W", "W/m²"], rows, [70, 100, 70, 60, 80, 80, 80, 60])
    rows2 = [[L("Nominal capacity A7/W35", "Номінальна потужність A7/W35"), f"{bc['p_nominal_kw']} kW"],
             [L("Capacity at θe (indicative)", "Потужність при θe (орієнтовно)"), f"{_n(bc['p_theta_e_kw'], 1)} kW"],
             [L("Coverage at θe", "Покриття при θe"), f"{_n(bc['cobertura'] * 100, 0)} %"],
             [L("Backup heater", "Резервний ТЕН"), f"{G._c(bc.get('apoio_kw') or 0, 0)} kW"],
             [L("Bivalent point", "Точка бівалентності"), f"{_n(bc['bivalencia_c'], 1)} °C"],
             [L("Flow temperature (UFH)", "Температура подачі (ТП)"), f"{_n(bc['temperatura_ida'], 1)} °C"],
             ["SCOP / ηs", f"{_n(bc['scop'], 2)} / {_n(bc['eta_s_pct'], 0)} %"],
             [L("Expansion vessel", "Розширювальний бак"), f"{r['quantidades']['vaso_l']} L"],
             [L("Electrical input (max)", "Електроспоживання (макс.)"), f"{_n(bc['p_absorvida_kw'], 1)} kW · {_n(bc['corrente_a'], 1)} A 3~"]]
    fl.tabela(820, 640, [L("Heat pump", "Тепловий насос"), L("Value", "Значення")], rows2, [300, 200])
    fl.caixa(1400, 640, 820, L("Kyiv −22 °C: a standard air/water heat pump covers ≈ "
                               f"{_n(bc['cobertura'] * 100, 0)} % at design temperature with the indicative curve — select a cold-climate model (rated ≥ 100 % at −20 °C, "
                               "EVI / R290) or a ground-source unit; capacity and COP to be taken from the manufacturer's table at 45 °C flow. Antifreeze protection "
                               "of the outdoor hydraulic line (glycol or monobloc with heater), condensate drain frost-free.",
                               "Київ −22 °C: стандартний ТН повітря/вода за орієнтовною кривою покриває ≈ "
                               f"{_n(bc['cobertura'] * 100, 0)} % при розрахунковій температурі — обрати модель для холодного клімату (≥ 100 % при −20 °C, "
                               "EVI / R290) або геотермальний ТН; потужність і COP — за таблицею виробника при подачі 45 °C. Захист від замерзання зовнішньої "
                               "гідролінії (гліколь або моноблок з підігрівом), відвід конденсату без замерзання."), 8.5)
    _cartucho(fl, m, L("Heating — plant and schedules", "Опалення — тепловий пункт"), num, n, tot, None, data)


# ---------------------------------------------------------------- GO-09 pormenores
def _f_go_det(doc, m, ver, num, n, tot, data):
    fl = G._Folha(doc, "A1")
    fl.t(40, 52, f"{num} · {L('TYPICAL CONSTRUCTION DETAILS AND CLT CONNECTOR SCHEDULE', 'ТИПОВІ ВУЗЛИ ТА СПЕЦИФІКАЦІЯ З’ЄДНУВАЧІВ CLT')}", 20, G.VERDE, True)
    fl.t(40, 74, L("Details from the architect's sheet (Home A) redrawn at 1:10 · connectors per ETA of the supplier (e.g. Rothoblaas) · to be confirmed by the structural engineer",
                   "Вузли за аркушем архітектора (Home A), М 1:10 · з’єднувачі за ETA постачальника (напр. Rothoblaas) · підтверджує інженер-конструктор"), 10, G.CINZA)
    S = 2.2 * 2.835           # 1:10 → 1 mm real = 0,1 mm → s pt/mm

    def camadas(x, y, lst, larg=360, titulo=""):
        fl.t(x, y - 14, titulo, 11, G.VERDE, True)
        yy = y
        for nome, esp, cor in lst:
            h = max(6.0, esp * S / 10)
            fl.ret((x, yy, x + larg, yy + h), (0.2, 0.2, 0.2), cor, 0.6)
            fl.linha([(x + larg, yy + h / 2), (x + larg + 30, yy + h / 2)], (0.3, 0.3, 0.3), 0.4)
            fl.t(x + larg + 34, yy + h / 2 + 3, nome, 7.5)
            yy += h
        return yy
    ISO_, MW, PL, BETX, GRV = (0.80, 0.90, 1.0), (1.0, 0.95, 0.70), (0.92, 0.92, 0.92), (0.82, 0.82, 0.82), (0.75, 0.72, 0.65)
    camadas(80, 160, [(L("PVC waterproof membrane + geotextile", "ПВХ-мембрана + геотекстиль"), 15, (0.3, 0.3, 0.35)),
                      (L("Gravel ballast 50 mm", "Гравійний баласт 50 мм"), 50, GRV),
                      (L("Lightweight concrete to falls ±100 mm", "Легкий бетон для ухилу ±100 мм"), 100, BETX),
                      (L("XPS 100 mm thermal-acoustic board (design: 200 mm for ДБН R ≥ 7.0)", "XPS 100 мм (проєктно 200 мм для R ≥ 7,0 ДБН)"), 100, ISO_),
                      (L("Vapour control layer (Al)", "Пароізоляція (Al)"), 6, (0.6, 0.6, 0.6)),
                      (L("CLT 140-5s → 160 / 180 per check (Rezult ETA-21/0914)", "CLT 140-5s → 160 / 180 за розрахунком (Rezult ETA-21/0914)"), 140, G.MAD),
                      (L("Service void + BA15 plasterboard ceiling", "Інсталяційний простір + стеля ГКП 15"), 40, PL)],
             titulo=L("D1 · Roof (CLT 140)", "D1 · Покрівля (CLT 140)"))
    camadas(80, 560, [(L("Floor finish (engineered wood / tiles)", "Чистове покриття (інж. дошка / плитка)"), 15, (0.85, 0.75, 0.6)),
                      (L("Screed 50–65 mm with UFH pipes 16×2", "Стяжка 50–65 мм з трубами ТП 16×2"), 60, BETX),
                      (L("EPS / XPS UFH board R ≥ 0.75", "Плита ТП ППС / XPS R ≥ 0,75"), 30, ISO_),
                      (L("Impact-sound underlay", "Звукоізоляція від ударного шуму"), 10, (0.6, 0.8, 0.6)),
                      (L("CLT 240-7s (Rezult)", "CLT 240-7s (Rezult)"), 240, G.MAD),
                      (L("Resilient hangers + BA15 ceiling", "Віброкріплення + стеля ГКП 15"), 40, PL)],
             titulo=L("D2 · Intermediate floor (CLT 240) with underfloor heating", "D2 · Міжповерхове перекриття (CLT 240) з теплою підлогою"))
    yy = camadas(1250, 160, [(L("Plasterboard BA13 ×2", "ГКП 12,5 ×2"), 25, PL), (L("CLT 100-5s wall", "Стіна CLT 100-5s"), 100, G.MAD),
                             (L("Vapour control membrane (Vapor IN 150)", "Пароізоляційна мембрана (Vapor IN 150)"), 6, (0.6, 0.6, 0.6)),
                             (L("Mineral wool 120 mm (design check: ≥ 120 mm, U ≤ 0.25)", "Мінвата 120 мм (за розрахунком ≥ 120 мм, U ≤ 0,25)"), 120, MW),
                             (L("Breather membrane + ventilated cavity 25 mm", "Вітрозахисна мембрана + вентзазор 25 мм"), 25, (0.95, 0.95, 0.95)),
                             (L("Timber cladding / render board", "Дерев'яне облицювання / фасадна плита"), 20, (0.8, 0.6, 0.35))],
                 larg=300, titulo=L("D3 · External wall (horizontal section)", "D3 · Зовнішня стіна (горизонтальний переріз)"))
    camadas(1250, 560, [(L("CLT 100 wall on sole plate + EPDM / bitumen DPC", "Стіна CLT 100 на лежні + гідроізоляція EPDM / бітум"), 100, G.MAD),
                        (L("Shear angle bracket + hold-down M16 (chemical anchor 8.8)", "Кутник на зсув + анкер на відрив M16 (хім. анкер 8.8)"), 20, (0.5, 0.5, 0.55)),
                        (L("RC upstand h 300 mm + TERMI FLOOR membrane", "З/б цоколь h 300 мм + мембрана TERMI FLOOR"), 300, BETX),
                        (L("RC slab 250 over basement (C25/30, A500C)", "З/б плита 250 над підвалом (C25/30, A500C)"), 250, BETX),
                        (L("XPS 100 + waterproofing on basement walls", "XPS 100 + гідроізоляція стін підвалу"), 100, ISO_)],
             larg=300, titulo=L("D4 · CLT wall to RC base", "D4 · Примикання стіни CLT до з/б основи"))
    # mapa de ligadores
    Lw = 0.0
    for mu in m.get("muros") or []:
        if mu.get("material") == "clt":
            Lw += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(mu["pontos"][:-1], mu["pontos"][1:]))
    q = conectores(m)
    rows = [[L(a, b), u, _n(v, 0)] for (a, b, u, v) in q["linhas"]]
    fl.tabela(80, 1080, [L("Connector", "З’єднувач"), L("Unit", "Од."), L("Qty", "К-сть")], rows, [560, 60, 90])
    fl.caixa(900, 1080, 1300, L(f"Quantities from the model: {_n(Lw, 1)} m of CLT walls (both floors), panel joints from the floor / roof panel layout. Spacing: shear "
                                "brackets every 0.8 m along wall bases, hold-downs at wall ends and beside openings, self-tapping screws Ø8 at 300 mm for "
                                "wall–floor, splines LVL 27×100 with Ø6 screws at 150 mm on panel joints — indicative, to be verified by calculation of the "
                                "connections (EN 1995-1-1 §8, supplier ETA).",
                                f"Кількості з моделі: {_n(Lw, 1)} м стін CLT (обидва поверхи), шви панелей — за розкладкою плит перекриття / покриття. Крок: кутники "
                                "на зсув через 0,8 м по низу стін, анкери на відрив на кінцях стін і біля прорізів, шурупи Ø8 через 300 мм стіна–перекриття, "
                                "шпонки LVL 27×100 з шурупами Ø6 через 150 мм у швах панелей — орієнтовно, перевіряється розрахунком з’єднань (EN 1995-1-1 §8, "
                                "ETA постачальника)."), 8.5)
    _cartucho(fl, m, L("Structure — typical details", "Конструкції — типові вузли"), num, n, tot, "10", data)


def conectores(m) -> dict:
    """Quantidades indicativas de ligadores CLT a partir do modelo (paredes e painéis)."""
    Lw, ends = 0.0, 0
    for mu in m.get("muros") or []:
        if mu.get("material") == "clt":
            segs = list(zip(mu["pontos"][:-1], mu["pontos"][1:]))
            Lw += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
            ends += 2 * len(segs)
    juntas = 0.0
    for lj in m.get("lajes") or []:
        if lj.get("tipo") == "clt":
            w = (lj["x1_m"] - lj["x0_m"]) if lj.get("direcao_vao") == "y" else (lj["y1_m"] - lj["y0_m"])
            span = (lj["y1_m"] - lj["y0_m"]) if lj.get("direcao_vao") == "y" else (lj["x1_m"] - lj["x0_m"])
            juntas += max(0, math.ceil(w / 2.95) - 1) * span
    linhas = [("Shear angle brackets (wall base and wall–floor)", "Кутники на зсув (низ стін і стіна–перекриття)", "un", math.ceil(Lw / 0.8)),
              ("Hold-downs with M16 threaded rods / chemical anchors", "Анкери на відрив з шпильками M16 / хім. анкерами", "un", ends + 16),
              ("Self-tapping screws Ø8 wall–floor (300 mm)", "Шурупи Ø8 стіна–перекриття (крок 300 мм)", "un", math.ceil(Lw / 0.3)),
              ("LVL splines 27×100 on panel joints", "Шпонки LVL 27×100 у швах панелей", "m", round(juntas, 1)),
              ("Screws Ø6 for splines (150 mm, 2 rows)", "Шурупи Ø6 для шпонок (150 мм, 2 ряди)", "un", math.ceil(juntas / 0.15 * 2)),
              ("Sole plate + DPC under CLT walls", "Лежень + гідроізоляція під стінами CLT", "m", round(Lw * 0.55, 1)),
              ("Acoustic decoupling strips (wall–floor)", "Віброізоляційні стрічки (стіна–перекриття)", "m", round(Lw * 0.45, 1))]
    return {"L_paredes_clt": Lw, "juntas_m": juntas, "linhas": linhas}


# ---------------------------------------------------------------- caderno
def planos(m: dict, r: dict, ver: dict | None = None, data: str | None = None, lingua: str = "en") -> bytes:
    """Caderno das especialidades + GO-09, na língua indicada ('en' | 'uk')."""
    import pymupdf
    from datetime import date
    data = data or date.today().strftime("%d/%m/%Y")
    tok = LANG.set(lingua)
    tok2 = G._TR_CV.set(G._dic(lingua))
    try:
        fmt, s, k = G._escala(m)
        cotas = sorted({d["cota"] for d in r["divisoes"]})
        aq = sorted({c for c in r["piso_radiante"]} | {r["mep"]["central"]["cota"]} if r["mep"].get("central") else set(r["piso_radiante"]))
        tot = len(cotas) * 2 + 2 + len(aq) + 1 + 1
        doc = pymupdf.open()
        i = 0
        for j, c in enumerate(cotas):
            i += 1
            _f_el(doc, m, r, c, f"EL-{j + 1:02d}", fmt, s, k, i, tot, data)
        i += 1
        _f_unifilar(doc, m, r, f"EL-{len(cotas) + 1:02d}", i, tot, data)
        for j, c in enumerate(cotas):
            i += 1
            _f_ws(doc, m, r, c, f"WS-{j + 1:02d}", fmt, s, k, i, tot, data)
        i += 1
        _f_ws_esquema(doc, m, r, f"WS-{len(cotas) + 1:02d}", i, tot, data)
        for j, c in enumerate(aq):
            i += 1
            _f_ht(doc, m, r, c, f"HT-{j + 1:02d}", fmt, s, k, i, tot, data)
        i += 1
        _f_ht_esquema(doc, m, r, f"HT-{len(aq) + 1:02d}", i, tot, data)
        i += 1
        _f_go_det(doc, m, ver, "GO-09", i, tot, data)
        return doc.tobytes(garbage=3, deflate=True)
    finally:
        G._TR_CV.reset(tok2)
        LANG.reset(tok)
