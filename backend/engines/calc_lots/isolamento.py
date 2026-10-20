"""Isolamento térmico de paredes (Portugal) — cálculo da parede, verificação REH e risco de condensação. Pré-dimensionamento indicativo.

  • R de cada camada e U (EN ISO 6946: Rsi 0,13 / Rse 0,04; 0,13 atrás de fachada ventilada), correção das buchas ETICS (ΔU = n·χp);
  • requisitos mínimos REH (Portaria 138-I/2021): U ≤ Umax da zona climática de inverno (continente / Açores; Madeira como continente),
    paredes em contacto com espaço não útil com btr ≤ 0,7 pelo Umax interior;
  • Glaser estacionário (EN ISO 13788) com a temperatura exterior de projeto do concelho e Sd mínimo de barreira pára-vapor;
  • quantidades por m² (rácios correntes, a ajustar pelo sistema escolhido).
Valores de λ por defeito: valores típicos de produtos com marcação CE; só o valor declarado (DoP) permite justificar o REH.
"""
from __future__ import annotations

import math

from . import reh

MATERIAIS: dict[str, dict] = {
    # suportes
    "betao": {"nome": "Betão armado", "lambda": 2.0, "mu": 80, "familia": "suporte"},
    "tijolo_furado": {"nome": "Tijolo furado", "R_fixo": {110: 0.27, 150: 0.39, 220: 0.52}, "mu": 10, "familia": "suporte"},
    "bloco_betao": {"nome": "Bloco de betão normal", "R_fixo": {150: 0.17, 200: 0.23, 250: 0.25}, "mu": 10, "familia": "suporte"},
    "bloco_termico": {"nome": "Bloco térmico (argila expandida)", "R_fixo": {250: 0.80, 300: 1.00}, "mu": 6, "familia": "suporte"},
    "alvenaria_pedra": {"nome": "Alvenaria de pedra (antiga)", "lambda": 2.3, "mu": 15, "familia": "suporte", "antigo": True},
    "taipa": {"nome": "Taipa / adobe", "lambda": 1.1, "mu": 8, "familia": "suporte", "antigo": True},
    "caixa_ar": {"nome": "Caixa de ar não ventilada", "R_qualquer": 0.18, "mu": 1, "familia": "ar"},
    # revestimentos
    "reboco_cimento": {"nome": "Reboco de cimento", "lambda": 1.3, "mu": 20, "familia": "revestimento"},
    "reboco_cal": {"nome": "Reboco de cal", "lambda": 0.8, "mu": 10, "familia": "revestimento"},
    "estuque": {"nome": "Estuque / gesso projetado", "lambda": 0.4, "mu": 10, "familia": "revestimento"},
    "reboco_etics": {"nome": "Reboco delgado armado (ETICS)", "lambda": 0.7, "mu": 25, "familia": "revestimento"},
    "gesso_cartonado": {"nome": "Placa de gesso cartonado", "lambda": 0.25, "mu": 10, "familia": "revestimento"},
    # isolantes
    "eps": {"nome": "Poliestireno expandido (EPS)", "lambda": 0.036, "mu": 40, "familia": "isolante"},
    "eps_grafite": {"nome": "EPS com grafite", "lambda": 0.031, "mu": 40, "familia": "isolante"},
    "xps": {"nome": "Poliestireno extrudido (XPS)", "lambda": 0.034, "mu": 150, "familia": "isolante"},
    "la_rocha": {"nome": "Lã de rocha", "lambda": 0.036, "mu": 1, "familia": "isolante"},
    "la_vidro": {"nome": "Lã de vidro", "lambda": 0.035, "mu": 1, "familia": "isolante"},
    "icb": {"nome": "Aglomerado de cortiça expandida (ICB)", "lambda": 0.040, "mu": 10, "familia": "isolante"},
    "pir": {"nome": "Poliisocianurato (PIR)", "lambda": 0.023, "mu": 60, "familia": "isolante"},
    "fibra_madeira": {"nome": "Fibra de madeira", "lambda": 0.040, "mu": 3, "familia": "isolante"},
    # membranas
    "barreira_vapor": {"nome": "Barreira pára-vapor (Sd ≥ 18 m)", "Sd": 18, "familia": "membrana"},
    "membrana_respiravel": {"nome": "Membrana respirável (Sd ≤ 0,2 m)", "Sd": 0.2, "familia": "membrana"},
}
SISTEMAS = {"etics": ("ETICS (isolamento exterior com reboco delgado)", "exterior", "ETAG 004 / EAD 040083 — Documento de Aplicação LNEC"),
            "fachada_ventilada": ("Fachada ventilada com isolamento", "exterior", "EAD 090062 — fixações e revestimento com aprovação técnica"),
            "caixa_ar": ("Parede dupla com isolamento na caixa de ar", "caixa", "Prática corrente — ITE 50 (LNEC)"),
            "interior": ("Isolamento pelo interior (gesso cartonado + lã mineral)", "interior", "Sistema do fabricante — ITE 50 (LNEC)")}
RSI, RSE, RSE_VENT = 0.13, 0.04, 0.13
CHI_BUCHA = 0.002
HUMIDADE = {"fraca": 0.45, "media": 0.55, "forte": 0.65}


def _R(code, ep, lam=None):
    m = MATERIAIS.get(code)
    if not m:
        raise ValueError(f"material desconhecido {code!r} ({', '.join(MATERIAIS)})")
    if lam:
        return ep / 1000 / float(lam), "λ declarado (DoP)"
    if "R_qualquer" in m:
        return m["R_qualquer"], "valor forfetário"
    if "R_fixo" in m:
        k = min(m["R_fixo"], key=lambda e: abs(e - ep))
        return m["R_fixo"][k] * ep / k, f"valor indicativo ITE 50 ({k} mm)"
    if "lambda" not in m:
        return 0.0, "membrana"
    return ep / 1000 / m["lambda"], "λ por defeito"


def _Sd(code, ep):
    m = MATERIAIS[code]
    return float(m["Sd"]) if "Sd" in m else m.get("mu", 1) * ep / 1000


def _psat(t):
    return 610.5 * math.exp(17.269 * t / (237.3 + t)) if t >= 0 else 610.5 * math.exp(21.875 * t / (265.5 + t))


def glaser(camadas, ti, te, phi_i, phi_e=0.80, rse=RSE):
    Rt = RSI + sum(c["R"] for c in camadas) + rse
    Sdt = sum(c["Sd"] for c in camadas) or 1e-6
    pi, pe = phi_i * _psat(ti), phi_e * _psat(te)
    pts, r, sd = [{"pos": "face interior", "T": ti - (ti - te) * RSI / Rt, "sd": 0.0}], RSI, 0.0
    for c in camadas:
        r += c["R"]; sd += c["Sd"]
        pts.append({"pos": f"após {c['nom']}", "T": ti - (ti - te) * r / Rt, "sd": sd})
    for p in pts:
        p["psat"] = _psat(p["T"]); p["p"] = pi - (pi - pe) * p["sd"] / Sdt; p["condensation"] = p["p"] > p["psat"] + 1e-6
    risco = [p for p in pts[1:-1] if p["condensation"]]
    best = None
    for p in pts[1:-1]:
        if 0 < p["sd"] < Sdt:
            fl = 2.0e-10 * ((pi - p["psat"]) / p["sd"] - (p["psat"] - pe) / (Sdt - p["sd"]))
            if fl > 0 and (best is None or fl > best[0]):
                best = (fl, p)
    return {"points": pts, "pi": pi, "pe": pe, "Sd_total": Sdt, "condensation": bool(risco), "plan": best[1]["pos"] if (risco and best) else None,
            "g_jour": best[0] * 8.64e7 if (risco and best) else 0.0, "conditions": {"ti": ti, "te": te, "phi_i": phi_i, "phi_e": phi_e}}


def calcular(p: dict) -> dict:
    hyp: list[str] = []
    sk = p.get("sistema") or "etics"
    if sk not in SISTEMAS:
        raise ValueError(f"sistema desconhecido {sk!r} ({', '.join(SISTEMAS)})")
    nome_s, pos, ref = SISTEMAS[sk]
    if p.get("theta_e") is not None:
        te, c = float(p["theta_e"]), None
        ri, regiao = int(p.get("zona_inverno", "I1")[-1]) - 1, p.get("regiao") or "continente"
    else:
        c = reh.clima(p.get("concelho"), p.get("nuts"), p.get("altitude_m"))
        te, ri, regiao = round(c["theta_i"] - 8.0, 1), c["ri"], c["regiao"]
        hyp.append(f"{c['nuts']}: zona {c['zona_i']}; Glaser com θe = θext,i − 8 K = {te:g} °C")
        if c.get("aviso"):
            hyp.append(c["aviso"])
    lado = p.get("lado") or "exterior"
    btr = float(p.get("btr") or (1.0 if lado == "exterior" else 0.8))
    tabela = reh.UMAX_ACORES if regiao == "acores" else (reh.UMAX_INT if (lado == "enu" and btr <= 0.7) else reh.UMAX)
    umax = tabela["parede"][ri]
    suporte = p.get("suporte") or ([{"material": "tijolo_furado", "ep_mm": 150}] + ([{"material": "caixa_ar", "ep_mm": 40}, {"material": "tijolo_furado", "ep_mm": 110}] if sk == "caixa_ar" else []))
    if not p.get("suporte"):
        hyp.append("suporte por defeito: " + " + ".join(f"{MATERIAIS[s['material']]['nome'].lower()} {s['ep_mm']} mm" for s in suporte))
    iso = p.get("isolante") or {"etics": "eps_grafite", "fachada_ventilada": "la_rocha", "caixa_ar": "xps", "interior": "la_mineral"}.get(sk)
    iso = "la_rocha" if iso == "la_mineral" else iso
    if MATERIAIS.get(iso, {}).get("familia") != "isolante":
        raise ValueError(f"isolante desconhecido {iso!r}")
    lam = p.get("lambda_declarado")
    lam_v = float(lam) if lam else MATERIAIS[iso]["lambda"]
    if not lam:
        hyp.append(f"λ do isolante por defeito ({lam_v:g} W/(m.°C)): usar o λ declarado (DoP / marcação CE) do produto")
    alvo = min(umax, float(p.get("u_alvo") or umax))
    antigo = any(MATERIAIS.get(s["material"], {}).get("antigo") for s in suporte)

    def montar(ep, bv=False):
        cs = []

        def add(code, e, l=None, papel=None):
            R, o = _R(code, e, l)
            cs.append({"code": code, "nom": MATERIAIS[code]["nome"] + (f" {e:g} mm" if MATERIAIS[code]["familia"] == "isolante" else ""), "ep_mm": e, "R": R, "R_brut": R,
                       "Sd": _Sd(code, e), "origine": o, "role": papel or MATERIAIS[code]["familia"]})
        sup = list(suporte)
        if sk == "interior":
            add("gesso_cartonado", 12.5)
            if bv:
                add("barreira_vapor", 0)
            add(iso, ep, lam, "isolante")
            for s in sup:
                add(s["material"], float(s["ep_mm"]))
            add("reboco_cal" if antigo else "reboco_cimento", 20)
            return cs, RSE
        add("estuque", 10)
        if sk == "caixa_ar":
            add(sup[0]["material"], float(sup[0]["ep_mm"]))
            if bv:
                add("barreira_vapor", 0)
            add(iso, ep, lam, "isolante")
            for s in sup[1:]:
                if s["material"] == "caixa_ar":
                    continue
                add(s["material"], float(s["ep_mm"]))
            add("reboco_cimento", 20)
            return cs, RSE
        for s in sup:
            add(s["material"], float(s["ep_mm"]))
        add(iso, ep, lam, "isolante")
        if sk == "etics":
            add("reboco_etics", 8)
            return cs, RSE
        add("membrana_respiravel", 0)
        return cs, RSE_VENT

    n_b = int(p.get("buchas_m2") or 6) if sk == "etics" else 0
    dU = n_b * CHI_BUCHA
    ep = float(p.get("isolante_ep_mm") or 0)
    if ep <= 0:
        for e in (30, 40, 50, 60, 70, 80, 100, 120, 140, 160, 180, 200):
            cs, rse = montar(e)
            if 1 / (RSI + sum(x["R"] for x in cs) + rse) + dU <= alvo:
                ep = float(e); break
        else:
            ep = 200.0
        hyp.append(f"espessura de isolante não indicada: {ep:g} mm (menor espessura comercial com U ≤ {alvo:g})")
    phi_i = HUMIDADE.get(p.get("humidade") or "media", 0.55)
    cs, rse = montar(ep)
    g = glaser(cs, 20.0, te, phi_i, rse=rse)
    bv = False
    if g["condensation"] and sk in ("interior", "caixa_ar"):
        bv = True
        cs, rse = montar(ep, True)
        g2 = glaser(cs, 20.0, te, phi_i, rse=rse)
        hyp.append("barreira pára-vapor acrescentada do lado quente: sem ela o Glaser indica condensação" + ("" if not g2["condensation"] else " (ainda insuficiente)"))
        g = g2
    R_par = sum(x["R"] for x in cs)
    U = 1 / (RSI + R_par + rse) + dU
    iso_c = next(x for x in cs if x["role"] == "isolante")
    ctl = [{"ref": "REH — requisito mínimo (Portaria 138-I/2021)", "exigencia": f"U ≤ Umax = {umax:g} W/(m².°C) (zona I{ri + 1}, {regiao}, {lado})",
            "valor": f"{U:.3f}", "ok": (U <= umax + 1e-9) if lam else (None if U <= umax + 1e-9 else False),
            "note": None if lam else "conforme apenas com o λ declarado do produto (DoP)"},
           {"ref": "Condensações internas — Glaser EN ISO 13788", "exigencia": f"sem condensação (20 °C / {phi_i * 100:.0f} %, {te:g} °C / 80 %)",
            "valor": "nula" if not g["condensation"] else f"no plano « {g['plan']} » ({g['g_jour']:.1f} g/m²/dia)",
            "ok": (not g["condensation"]) if not antigo else (True if not g["condensation"] else None),
            "note": "parede antiga: confirmar com simulação higrotérmica dinâmica (EN 15026)" if (g["condensation"] and antigo) else None}]
    if sk == "interior":
        ctl.append({"ref": "Pontes térmicas planas (isolamento interior)", "exigencia": "tratar topos de laje e pilares (correção ψ no REH)",
                    "valor": "a quantificar (ψ das ligações laje/fachada e pilares)", "ok": None})
    regras = {"etics": ["Sistema com DA LNEC/ETA: colagem + buchas após presa; ensaio de arrancamento das buchas no suporte existente",
                        "perfil de arranque ≥ 15 cm acima do solo ou XPS no embasamento; reforço com rede dupla até 2 m de altura (choques)",
                        "retorno do isolante nos vãos, peitoris com pingadeira, juntas com mastique nas caixilharias"],
              "fachada_ventilada": ["caixa de ar ventilada ≥ 20 mm com entradas e saídas protegidas", "isolante fixado mecanicamente, membrana respirável sobre lã mineral",
                                    "verificar a reação ao fogo do revestimento (SCIE, Portaria 1532/2008) conforme a altura do edifício"],
              "caixa_ar": ["isolante encostado ao pano interior, caixa de ar residual drenada (tubos de drenagem e caleira na base)",
                           "corrigir as pontes térmicas de pilares, vigas e topos de laje (forra exterior de isolante)", "grampos de ligação inox entre os panos"],
              "interior": ["perfis metálicos a 0,60 m, isolante contínuo, barreira pára-vapor contínua com juntas fitadas",
                           "verificar previamente humidade ascensional e infiltrações da parede", "deixar espaço técnico para cablagem sem perfurar a barreira"]}[sk]
    S = float(p.get("area_m2") or 0)
    met = []
    if S > 0:
        q = lambda d, v, u: {"designation": d, "quantite": round(v, 1 if v < 100 else 0), "unite": u}
        met = [q(f"Isolante {MATERIAIS[iso]['nome']} {ep:g} mm", S * 1.05, "m²")]
        if sk == "etics":
            met += [q("Argamassa de colagem", S * 4.5, "kg"), q("Buchas", S * n_b * 1.05, "un"), q("Reboco de base (2 demãos)", S * 5.0, "kg"),
                    q("Rede de fibra de vidro", S * 1.12, "m²"), q("Primário + acabamento", S * 2.65, "kg")]
        elif sk == "interior":
            met += [q("Perfis (montantes a 0,60 m + guias)", S * 2.55, "m"), q("Gesso cartonado", S * 1.05, "m²"), q("Parafusos", S * 18, "un"),
                    q("Barreira pára-vapor", S * 1.1, "m²") if bv else q("Fita de juntas", S * 1.5, "m")]
        elif sk == "fachada_ventilada":
            met += [q("Subestrutura (montantes)", S * 1.75, "m"), q("Ancoragens", S * 1.4, "un"), q("Membrana respirável", S * 1.1, "m²"), q("Revestimento", S * 1.08, "m²")]
        else:
            met += [q("Grampos inox", S * 4, "un"), q("Tubos de drenagem da caixa de ar", S / 1.5, "un")]
    return {"sistema": sk, "sistema_nome": nome_s, "referencia": ref, "couches": cs, "R_parede": R_par, "U": U, "dU_buchas": dU, "umax": umax, "theta_e": te,
            "isolante": {"code": iso, "ep_mm": ep, "lambda": lam_v, "declarado": bool(lam)}, "glaser": g, "barreira_vapor": bv, "controles": ctl,
            "regras": regras, "metre": met, "hipoteses": hyp, "conforme": all(x["ok"] is not False for x in ctl)}


def note(params: dict) -> dict:
    from . import rendu
    r = calcular(params)
    W = 2.83
    titre = f"Isolamento de paredes — {r['sistema_nome']}"
    sous = f"{r['referencia']} · isolante {r['isolante']['ep_mm']:g} mm (λ {r['isolante']['lambda']:g}{' declarado' if r['isolante']['declarado'] else ' por defeito'})"
    rows = [[c["nom"], f"{c['ep_mm']:g}" if c["ep_mm"] else "—", f"{c['R']:.2f}", f"{c['Sd']:.2f}", c["origine"]] for c in r["couches"]]
    blocks = [("h2", "1. Composição (do interior para o exterior)"),
              ("table", ["Camada", "esp. (mm)", "R (m².°C/W)", "Sd (m)", "Origem"], rows, [70 * W, 18 * W, 22 * W, 18 * W, 52 * W]),
              ("p", f"R = {r['R_parede']:.2f} m².°C/W; U = {r['U']:.3f} W/(m².°C)" + (f" (inclui buchas ΔU = {r['dU_buchas']:.3f})" if r["dU_buchas"] else "")),
              ("h2", "2. Perfil de temperaturas e diagrama de Glaser"), ("figure", rendu.ParoiGlaser(r["couches"], r["glaser"])),
              ("h2", "3. Verificações"), ("controls", [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in r["controles"]]), ("h2", "4. Regras de execução"), ("hyp", r["regras"])]
    if r["metre"]:
        blocks += [("h2", "5. Quantidades (rácios correntes)"),
                   ("table", ["Designação", "Quantidade", "Unidade"], [[m["designation"], f"{m['quantite']:g}", m["unite"]] for m in r["metre"]], [120 * W, 30 * W, 20 * W])]
    blocks += [("h2", "Hipóteses / a validar"), ("hyp", r["hipoteses"] or ["nenhuma"])]
    pdf = rendu.build_pdf(titre, sous, blocks)
    return {**r, "titre": titre, "sous_titre": sous, "pdf": pdf, "png": rendu.first_page_png(pdf)}
