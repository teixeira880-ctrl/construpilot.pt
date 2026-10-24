"""Piso radiante hidráulico de baixa temperatura (NP EN 1264-2/-3/-4) — dimensionamento divisão a divisão (Portugal).

Por divisão: necessidade q = Φ / A emissora → temperatura média de superfície θF = θi + (q / 8,92)^(1/1,1) (curva característica
EN 1264-2); limites EN 1264: θF ≤ 29 °C nas zonas de permanência, 33 °C nas casas de banho (θi + 9 K); acima, apoio necessário.
Passo dos tubos, diferença média logarítmica água/ambiente Δθ_H = q / K_H (função do passo e do revestimento), temperatura de
ida comum fixada pela divisão mais exigente (σ = 5 K), σ das outras divisões recalculado, caudais, comprimento de tubo,
circuitos ≤ 120 m, perdas de carga (Darcy, tubo 16×2), controlos (revestimento R ≤ 0,15, isolante sob a betonilha EN 1264-4,
juntas de dilatação > 40 m² ou > 8 m, ida ≤ 45 °C para bomba de calor). Pré-dimensionamento indicativo.
"""
from __future__ import annotations

import math

TF_MAX = {"geral": 29.0, "casa_de_banho": 33.0}                         # NP EN 1264-2
R_ISOLANTE_MIN = {"aquecido": 0.75, "nao_aquecido": 1.25, "solo": 1.25, "exterior": 2.00}     # NP EN 1264-4, quadro 1
REVESTIMENTO_R = {"ceramico": 0.01, "pedra": 0.01, "vinilico": 0.03, "flutuante_laminado": 0.06, "madeira_colada_10": 0.07,
                  "madeira_flutuante_14": 0.10, "alcatifa": 0.12}
REVESTIMENTO_PT = {"ceramico": "cerâmico", "pedra": "pedra", "vinilico": "vinílico", "flutuante_laminado": "flutuante laminado",
                   "madeira_colada_10": "madeira colada 10 mm", "madeira_flutuante_14": "madeira flutuante 14 mm", "alcatifa": "alcatifa"}
# K_H (W/(m².K)) tubo 16 mm, betonilha ≈ 45 mm acima dos tubos — indicativo (curvas de fabricante EN 1264), interpolado em R
K_H = {10: [(0.0, 7.0), (0.05, 5.2), (0.10, 4.2), (0.15, 3.5)], 15: [(0.0, 6.0), (0.05, 4.6), (0.10, 3.8), (0.15, 3.2)],
       20: [(0.0, 5.1), (0.05, 4.0), (0.10, 3.4), (0.15, 2.9)]}
L_CIRCUITO_MAX = 120.0
DI, RHO, NU = 0.012, 994.0, 0.72e-6            # tubo 16×2, água ≈ 35 °C
HUMIDAS = ("casa_de_banho",)
T_INT = {"sala": 20, "quarto": 20, "cozinha": 20, "casa_de_banho": 22, "corredor": 18, "escritorio": 20, "lavandaria": 18, "arrumos": 15, "outro": 20}


def _n(x, d=1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def q_de_tf(tf, ti):
    return 8.92 * max(tf - ti, 0) ** 1.1


def tf_de_q(q, ti):
    return ti + (max(q, 0) / 8.92) ** (1 / 1.1)


def k_h(passo_cm, r):
    pts = K_H[passo_cm]
    r = min(max(r, 0.0), 0.15)
    for (r0, k0), (r1, k1) in zip(pts, pts[1:]):
        if r0 <= r <= r1:
            return k0 + (k1 - k0) * (r - r0) / (r1 - r0)
    return pts[-1][1]


def theta_ida(ti, dth, sigma):
    """Ida θV tal que (θV − θR) / ln((θV − θi) / (θR − θi)) = Δθ_H com θR = θV − σ."""
    return ti + sigma / (1 - math.exp(-sigma / dth))


def sigma_para(ti, tv, dth):
    """σ (K) que dá Δθ_H para uma ida θV imposta (bisseção)."""
    lo, hi = 0.05, max(tv - ti - 0.05, 0.1)
    for _ in range(80):
        mid = (lo + hi) / 2
        th = mid / math.log((tv - ti) / (tv - mid - ti)) if tv - mid - ti > 0 else 0
        if th > dth:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def perda_carga(caudal_lh, comprimento_m):
    """Pa — Darcy-Weisbach, Blasius (turbulento) ou 64/Re (laminar), +30 % singularidades."""
    q = caudal_lh / 3600 / 1000
    v = q / (math.pi * DI ** 2 / 4)
    re = v * DI / NU
    lam = 64 / re if re < 2300 else 0.3164 / re ** 0.25
    return 1.3 * lam * comprimento_m / DI * RHO * v ** 2 / 2, v


def calcular(params: dict) -> dict:
    """params : {divisoes: [{nome, tipo, area_m2, phi_w, theta_int, revestimento | r_revestimento, exclusao_m2, comprimento_max_m,
                             local_inferior, r_isolante, distancia_coletor_m}], sigma_k (5), ida_max (45)}"""
    p = dict(params or {})
    sigma = float(p.get("sigma_k") or 5.0)
    tv_max = float(p.get("ida_max") or 45.0)
    hyp: list[str] = []
    rows = []
    for r in p.get("divisoes") or []:
        typ = r.get("tipo") or "sala"
        ti = float(r.get("theta_int") or T_INT.get(typ, 20))
        A = float(r["area_m2"])
        exc = float(r["exclusao_m2"]) if r.get("exclusao_m2") is not None else round(A * 0.08, 1)
        Aem = max(A - exc, 0.5)
        phi = float(r["phi_w"])
        rev = r.get("revestimento") or ("ceramico" if typ in ("casa_de_banho", "cozinha", "lavandaria", "corredor") else "madeira_colada_10")
        R = float(r["r_revestimento"]) if r.get("r_revestimento") is not None else REVESTIMENTO_R.get(rev, 0.10)
        q = phi / Aem
        tf_lim = TF_MAX["casa_de_banho"] if typ in HUMIDAS else TF_MAX["geral"]
        qmax = q_de_tf(tf_lim, ti)
        apoio = max(0.0, (q - qmax) * Aem)
        q_ef = min(q, qmax)
        passo = 10 if (typ in HUMIDAS or q_ef > 70) else (20 if q_ef < 35 else 15)
        dth = q_ef / k_h(passo, R)
        rows.append({"nome": r.get("nome") or typ, "tipo": typ, "theta_int": ti, "area_m2": A, "A_em": Aem, "phi_w": phi, "q": q, "q_ef": q_ef,
                     "qmax": qmax, "tf": tf_de_q(q_ef, ti), "tf_lim": tf_lim, "apoio_w": apoio, "revestimento": rev, "R_rev": R, "passo": passo,
                     "dth": dth, "comprimento_max_m": r.get("comprimento_max_m"), "local_inferior": r.get("local_inferior") or "solo",
                     "r_isolante": r.get("r_isolante"), "dist_col": float(r.get("distancia_coletor_m") or 6.0),
                     "comprimento_m": float(r["comprimento_m"]) if r.get("comprimento_m") else None,
                     "largura_m": float(r["largura_m"]) if r.get("largura_m") else None})
    if not rows:
        raise ValueError("indicar as divisões (tipo, área, perdas de calor)")
    for row in rows:
        if theta_ida(row["theta_int"], row["dth"], sigma) > tv_max - 5 and row["passo"] > 10:
            row["passo"] = 10
            row["dth"] = row["q_ef"] / k_h(10, row["R_rev"])
    crit = max(rows, key=lambda x: theta_ida(x["theta_int"], x["dth"], sigma))
    tv = theta_ida(crit["theta_int"], crit["dth"], sigma)
    tot = {"caudal": 0.0, "tubo": 0.0, "circuitos": 0, "phi": 0.0, "volume_l": 0.0}
    ctl = []
    for row in rows:
        s = sigma if row is crit else sigma_para(row["theta_int"], tv, row["dth"])
        lim = 0.5 * (tv - row["theta_int"])                        # validade da média logarítmica EN 1264 : σ/(θV − θi) ≤ 0,5
        if s > lim and row["passo"] < 20 and row is not crit:
            row["passo"] = 20
            row["dth"] = row["q_ef"] / k_h(20, row["R_rev"])
            s = sigma_para(row["theta_int"], tv, row["dth"])
        if s > lim:
            s = lim
            row["sobrepotencia"] = True
        row["sigma"] = s
        row["caudal_lh"] = row["q_ef"] * row["A_em"] / (1.163 * s)
        L = row["A_em"] / (row["passo"] / 100) * 1.1
        n = max(1, math.ceil((L + 2 * row["dist_col"]) / L_CIRCUITO_MAX))
        while (L / n + 2 * row["dist_col"]) > L_CIRCUITO_MAX:
            n += 1
        row["circuitos"] = n
        row["comprimento_circuito_m"] = L / n + 2 * row["dist_col"]
        row["tubo_m"] = row["comprimento_circuito_m"] * n
        dp, v = perda_carga(row["caudal_lh"] / n, row["comprimento_circuito_m"])
        row["dp_kpa"], row["velocidade"] = dp / 1000, v
        tot["caudal"] += row["caudal_lh"]; tot["tubo"] += row["tubo_m"]; tot["circuitos"] += n; tot["phi"] += row["q_ef"] * row["A_em"]
        tot["volume_l"] += math.pi * DI ** 2 / 4 * row["tubo_m"] * 1000
        ctl.append({"ref": f"{row['nome']} — temperatura de superfície (NP EN 1264-2)", "exigencia": f"θF ≤ {row['tf_lim']:g} °C",
                    "valor": f"{_n(row['tf'])} °C ({row['q']:.0f} W/m² pedidos, {row['qmax']:.0f} máx.)",
                    "ok": row["apoio_w"] <= 50, "note": (f"apoio {row['apoio_w']:.0f} W (p. ex. toalheiro ou radiador)" if row["apoio_w"] > 1 else None)})
        if row["R_rev"] > 0.15:
            ctl.append({"ref": f"{row['nome']} — revestimento", "exigencia": "R revestimento ≤ 0,15 m².°C/W", "valor": _n(row['R_rev'], 2), "ok": False})
        rmin = R_ISOLANTE_MIN.get(row["local_inferior"], 1.25)
        if row["r_isolante"] is not None:
            ctl.append({"ref": f"{row['nome']} — isolante sob o piso (NP EN 1264-4)", "exigencia": f"R ≥ {rmin:g} m².°C/W (local inferior: {row['local_inferior']})",
                        "valor": _n(float(row['r_isolante']), 2), "ok": float(row["r_isolante"]) >= rmin})
        if row["area_m2"] > 40 or (row["comprimento_max_m"] and float(row["comprimento_max_m"]) > 8):
            ctl.append({"ref": f"{row['nome']} — juntas de dilatação", "exigencia": "obrigatórias acima de 40 m² ou de 8 m de comprimento (NP EN 1264-4)",
                        "valor": f"{row['area_m2']:.0f} m²", "ok": None, "note": "prever as juntas em planta; tubos atravessam só em manga"})
    ctl.insert(0, {"ref": "Temperatura de ida", "exigencia": f"θ ida ≤ {tv_max:g} °C (bomba de calor; NP EN 1264 admite até 55 °C)",
                   "valor": f"{_n(tv)} °C (divisão dimensionante: {crit['nome']})", "ok": tv <= tv_max})
    ctl.append({"ref": "Tubo PE-X / PE-RT com barreira de oxigénio (ISO 10508)", "exigencia": "classe de aplicação 4 (piso radiante, ≤ 60 °C de serviço)",
                "valor": f"ida {_n(tv)} °C", "ok": tv <= 60})
    dpmax = max(r["dp_kpa"] for r in rows)
    ctl.append({"ref": "Perdas de carga por circuito", "exigencia": "≤ 25 kPa no circuito mais desfavorável", "valor": f"{_n(dpmax)} kPa", "ok": dpmax <= 25})
    n_col = max(1, math.ceil(tot["circuitos"] / 12))
    if any(r["r_isolante"] is None for r in rows):
        hyp.append("isolante sob o piso não indicado: respeitar o R mínimo da NP EN 1264-4 (0,75 sobre local aquecido, 1,25 sobre o solo / local não aquecido, "
                   "2,00 sobre o exterior)")
    if any(r.get("sobrepotencia") for r in rows):
        hyp.append("divisões de pequena necessidade (" + ", ".join(r["nome"] for r in rows if r.get("sobrepotencia")) + "): σ limitado a 0,5·(θV − θi), "
                   "potência regulada por termostato ambiente / válvula de zona")
    hyp.append("perdas para baixo do piso radiante não contadas nas perdas de calor (isolante sob a betonilha suposto conforme)")
    hyp.append("coeficientes K_H indicativos (tubo 16 mm, betonilha ≈ 45 mm): substituir pelo ábaco do fabricante escolhido")
    hyp.append(f"áreas não aquecidas (móveis fixos, roupeiros): 8 % da divisão se não indicadas; circuitos ≤ {L_CIRCUITO_MAX:g} m")
    if any(not (r["comprimento_m"] and r["largura_m"]) for r in rows):
        hyp.append("dimensões das divisões não indicadas: plantas desenhadas sobre um retângulo equivalente à área (traçado indicativo)")
    return {"divisoes": rows, "theta_ida": tv, "theta_retorno_crit": tv - sigma, "sigma": sigma, "caudal_total_lh": tot["caudal"], "tubo_total_m": tot["tubo"],
            "circuitos": tot["circuitos"], "coletores": n_col, "potencia_w": tot["phi"], "volume_agua_l": tot["volume_l"],
            "apoio_total_w": sum(r["apoio_w"] for r in rows), "controles": ctl, "hipoteses": hyp}


def _conv(lst):
    return [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in lst]


def _dims(row):
    """Dimensões interiores (m): as indicadas, ou um quadrado equivalente à área (assinalado como hipótese)."""
    L, B = row.get("comprimento_m"), row.get("largura_m")
    A = row["area_m2"]
    if L and B:
        return max(L, B), min(L, B), True
    if L or B:
        k = L or B
        return max(k, A / k), min(k, A / k), True
    c = math.sqrt(A)
    return c, c, False


def planta(row) -> tuple:
    """Planta desenhada do piso radiante de uma divisão: contorno, zona periférica sem tubos, circuitos em espiral dupla
    (contracorrente) ao passo calculado, coletor, cotas e legenda. → (Drawing, legenda)."""
    from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from . import rendu
    rendu.fonts()
    C = colors.HexColor
    L, B, given = _dims(row)
    Wd, Hd = 172 * mm, 112 * mm
    m0 = 14 * mm
    sc = min((Wd - 2 * m0 - 40 * mm) / L, (Hd - 2 * m0) / B)
    x0, y0 = m0 + 6 * mm, m0
    X = lambda x: x0 + x * sc
    Y = lambda y: y0 + y * sc
    d = Drawing(Wd, Hd)
    t = lambda x, y, s_, sz=6.6, col=C("#1d2422"), anc="start", bold=False: String(x, y, rendu.txt(s_), fontName="CP-Bold" if bold else "CP",
                                                                                fontSize=sz, fillColor=col, textAnchor=anc)
    ida, ret = C("#d8452f"), C("#2a78d6")
    d.add(Rect(X(0), Y(0), L * sc, B * sc, fillColor=C("#f7f7f2"), strokeColor=C("#1d2422"), strokeWidth=2.2))
    borda = 0.15                                                      # zona periférica / junta perimetral
    n = max(1, int(row.get("circuitos") or 1))
    passo = row["passo"] / 100.0
    # divide a divisão em n faixas ao longo do comprimento, uma espiral dupla por circuito
    faixa = (L - 2 * borda) / n
    for k in range(n):
        ax, ay = borda + k * faixa, borda
        bw, bh = faixa, B - 2 * borda
        # espiral contracorrente: anéis concêntricos com passo 2×p, ida e retorno intercalados
        ring = 0
        while True:
            off = ring * passo
            w_, h_ = bw - 2 * off, bh - 2 * off
            if w_ <= passo or h_ <= passo:
                break
            col = ida if ring % 2 == 0 else ret
            d.add(Rect(X(ax + off), Y(ay + off), w_ * sc, h_ * sc, fillColor=None, strokeColor=col, strokeWidth=0.9))
            ring += 1
        # alimentação até ao coletor (lado esquerdo, a meio)
        yc = B / 2
        d.add(PolyLine([X(ax + 0.02), Y(ay + 0.05), X(ax + 0.02), Y(yc - 0.06 * (k + 1)), X(-0.18), Y(yc - 0.06 * (k + 1))],
                       strokeColor=ida, strokeWidth=0.8))
        d.add(PolyLine([X(ax + 0.06), Y(ay + 0.05), X(ax + 0.06), Y(yc + 0.06 * (k + 1)), X(-0.18), Y(yc + 0.06 * (k + 1))],
                       strokeColor=ret, strokeWidth=0.8))
        d.add(Rect(X(ax + bw / 2) - 5 * mm, Y(B) + 2, 10 * mm, 4.2 * mm, fillColor=C("#ffffff"), strokeColor=None))
        d.add(t(X(ax + bw / 2), Y(B) + 4, f"C{k + 1}", 7, bold=True, anc="middle"))
        if k:
            d.add(Line(X(ax), Y(borda), X(ax), Y(B - borda), strokeColor=C("#9aa3a0"), strokeWidth=0.4, strokeDashArray=[2, 2]))
    # coletor
    d.add(Rect(X(-0.18) - 8 * mm, Y(B / 2) - 7 * mm, 8 * mm, 14 * mm, fillColor=C("#1d2422"), strokeColor=None))
    d.add(t(X(-0.18) - 4 * mm, Y(B / 2) - 10 * mm, "Coletor", 6.2, anc="middle", bold=True))
    # cotas
    d.add(Line(X(0), Y(0) - 6, X(L), Y(0) - 6, strokeColor=C("#1d2422"), strokeWidth=0.5))
    d.add(t(X(L / 2), Y(0) - 14, f"{_n(L, 2)} m", 7, anc="middle", bold=True))
    d.add(Line(X(L) + 6, Y(0), X(L) + 6, Y(B), strokeColor=C("#1d2422"), strokeWidth=0.5))
    d.add(t(X(L) + 9, Y(B / 2), f"{_n(B, 2)} m", 7, bold=True))
    lab = f"{row['nome']} — {_n(row['area_m2'], 1)} m²"
    d.add(Rect(X(L / 2) - (len(lab) * 2.4 + 6), Y(B / 2) - 6, len(lab) * 4.8 + 12, 14, fillColor=C("#ffffff"), strokeColor=C("#1d2422"), strokeWidth=0.5))
    d.add(t(X(L / 2), Y(B / 2) - 2, lab, 8, anc="middle", bold=True))
    # legenda
    lx = X(L) + 26 * mm
    for i, (col, lab) in enumerate(((ida, "Ida"), (ret, "Retorno"))):
        d.add(Line(lx, Hd - 20 * mm - i * 6 * mm, lx + 8 * mm, Hd - 20 * mm - i * 6 * mm, strokeColor=col, strokeWidth=1.6))
        d.add(t(lx + 10 * mm, Hd - 21 * mm - i * 6 * mm, lab, 6.6))
    info = [f"Passo {row['passo']} cm", f"{n} circuito(s) ≤ {L_CIRCUITO_MAX:g} m", f"{row['tubo_m']:.0f} m de tubo 16×2",
            f"{row['caudal_lh']:.0f} L/h, σ {_n(row['sigma'])} K", f"θF {_n(row['tf'])} °C (≤ {row['tf_lim']:g})", f"Faixa periférica {borda * 100:.0f} cm"]
    for i, s_ in enumerate(info):
        d.add(t(lx, Hd - 36 * mm - i * 5 * mm, s_, 6.4))
    leg = (f"Planta esquemática do piso radiante — {row['nome']}: espiral dupla em contracorrente ao passo de {row['passo']} cm, "
           f"{n} circuito(s) até ao coletor. " + ("Dimensões indicadas." if given else
           f"Dimensões não indicadas: quadrado equivalente de {_n(L, 2)} × {_n(B, 2)} m (a substituir pelas dimensões reais)."))
    return d, leg


def blocos(r: dict, pref: str = "") -> list:
    from . import notes
    W = notes.W
    return [("h2", f"{pref}Piso radiante (NP EN 1264)"),
            ("p", f"Ida {_n(r['theta_ida'])} °C / retorno {_n(r['theta_retorno_crit'])} °C (σ {_n(r['sigma'], 0)} K na divisão dimensionante), "
                  f"{r['circuitos']} circuitos, {r['coletores']} coletor(es), {r['tubo_total_m']:.0f} m de tubo 16×2, caudal {r['caudal_total_lh']:.0f} L/h, "
                  f"volume de água {r['volume_agua_l']:.0f} L."),
            ("table", ["Divisão", "Φ W", "W/m²", "θF °C", "Passo cm", "σ K", "L/h", "Circ.", "Δp kPa"],
             [[x["nome"], f"{x['phi_w']:.0f}", f"{x['q']:.0f}", _n(x['tf']), f"{x['passo']}", _n(x['sigma']), f"{x['caudal_lh']:.0f}",
               f"{x['circuitos']}", _n(x['dp_kpa'])] for x in r["divisoes"]],
             [38 * W, 16 * W, 16 * W, 16 * W, 18 * W, 14 * W, 18 * W, 14 * W, 18 * W]),
            ("controls", _conv(r["controles"]))] + [("chart", *planta(x)) for x in r["divisoes"]]


def note(params: dict) -> dict:
    from . import notes
    r = calcular(params)
    kp = [{"label": "Temperatura de ida", "value": f"{r['theta_ida']:.1f}".replace(".", ","), "unit": "°C", "ok": r["controles"][0]["ok"]},
          {"label": "Circuitos", "value": str(r["circuitos"]), "unit": f"{r['coletores']} coletor(es)"},
          {"label": "Tubo", "value": f"{r['tubo_total_m']:.0f}", "unit": "m"},
          {"label": "Apoio necessário", "value": f"{r['apoio_total_w']:.0f}", "unit": "W"}]
    blocs = [("kpis", kp), ("p", "Pré-dimensionamento indicativo — não substitui o projeto de AVAC.")] + blocos(r, "1. ")
    titre = "Pré-dimensionamento — piso radiante"
    pdf, png = notes.pdf(titre, "NP EN 1264-2/-3/-4", blocs, r["hipoteses"])
    return {**r, "titre": titre, "pdf": pdf, "png": png}
