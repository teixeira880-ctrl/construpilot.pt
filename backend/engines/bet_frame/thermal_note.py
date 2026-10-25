"""Note d'étude thermique du bâtiment (A4, même présentation que les notes de calcul des lots ConstruPilot).

PT : estudo de comportamento térmico — pré-certificado REH por fração (clima, soluções construtivas com U calculado e Umáx,
síntese, cálculo detalhado de cada fração : envolvente, pontes térmicas, balanço de inverno e verão, energia primária, requisitos,
potência de aquecimento).
FR : pré-étude RE2020 du bâtiment (Bbio, Cep, Cep,nr, DH, Ic, modulations, enveloppe, besoins mensuels, consommations, étiquettes)
+ parois, déperditions et puissances de chauffage logement par logement (NF EN 12831 simplifiée).
"""
from __future__ import annotations

from pathlib import Path

from .calc import num
from .model import Frame

LANG_PT = {"note": "Nota de cálculo", "page": "página", "ref": "Ref.", "synthese": "Síntese das verificações", "conformes": "conformes",
           "non_conformes": "não conformes", "a_verifier": "a verificar", "verdict_ok": "CONFORME", "verdict_ko": "NÃO CONFORME",
           "verdict_na": "A VERIFICAR", "verdict_glob_ok": "Todas as verificações calculadas estão conformes",
           "verdict_glob_ko": "Pelo menos uma verificação não está conforme", "verdict_glob_na": "Nenhuma não conformidade — pontos a verificar",
           "head": ["Referência", "Exigência", "Valor", "Resultado"], "hyp": "Hipóteses / a validar", "brand_sub": "Gabinete de projeto digital"}
LANG_FR = {"note": "Note de calcul", "page": "page", "ref": "Réf.", "synthese": "Synthèse des vérifications", "conformes": "conformes",
           "non_conformes": "non conformes", "a_verifier": "à vérifier", "verdict_ok": "CONFORME", "verdict_ko": "NON CONFORME",
           "verdict_na": "À VÉRIFIER", "verdict_glob_ok": "Toutes les vérifications calculées sont conformes",
           "verdict_glob_ko": "Au moins une vérification est non conforme", "verdict_glob_na": "Aucune non-conformité — points à vérifier",
           "head": ["Référence", "Exigence", "Valeur", "Résultat"], "hyp": "Hypothèses / à valider", "brand_sub": "Bureau d'études numérique"}
FOOT = {"pt": "ConstruPilot — nota de cálculo gerada por motor determinístico; a validar pelo projetista / técnico responsável antes da execução.",
        "fr": "ConstruPilot — note de calcul générée par moteur déterministe ; à valider par le BET / la MOE avant exécution."}
TIPO_PT = {"parede": "Parede", "cobertura": "Cobertura", "pavimento": "Pavimento", "porta": "Porta", "envidracado": "Envidraçado"}
FRONT = {"exterior": "exterior", "enu": "ENU", "solo": "solo", "adjacente": "adjacente"}


def f(x, d=1):
    return num(float(x), d) if x is not None else "—"


def _sol_blocks(sols: dict, pt: bool, W) -> list:
    out, ctl = [], []
    for k, s in sols.items():
        out.append(("p", f"{s['name']} — U = {f(s['U'], 2)} W/(m².K)" + (f" · g = {f(s['g'], 2)}" if s.get("g") else "")))
        if s["layers"]:
            rows = [[nm, f(e * 100, 1), f(lam, 3) if lam else "—", f(R, 3)] for nm, e, lam, R in s["layers"]]
            rows.append(["Rsi + Rse", "", "", f(s["Rsi"] + s["Rse"], 2)])
            rows.append([("Resistência térmica total Rt" if pt else "Résistance thermique totale Rt"), "", "", f(s["Rt"], 3)])
            out.append(("table", ["Camada (int. → ext.)" if pt else "Couche", "e (cm)", "λ W/(m.K)", "R m².K/W"], rows,
                        [92 * W, 22 * W, 28 * W, 28 * W]))
        if s.get("Umax") is not None:
            ctl.append({"ref": (f"Umáx — {s['name'].split(' — ')[0]}" if pt else s["name"].split(" — ")[0]),
                        "exigence": f"U ≤ {f(s['Umax'], 2)} W/(m².K) (Portaria 138-I/2021) · Uref {f(s['Uref'], 2)}",
                        "valeur": f(s["U"], 2), "ok": s["U"] <= s["Umax"] + 1e-9})
    if ctl:
        out.append(("controls", ctl))
    return out


def _groups(us: list, key) -> list:
    """Frações idênticas em pisos consecutivos (mesmo nome, tipologia e resultados) → uma só linha « Pisos 1 a 3 »."""
    out = []
    for x in us:
        k = key(x)
        g = next((g for g in out if g[0] == k), None)
        if g:
            g[2].append(x["level_name"])
        else:
            out.append([k, x, [x["level_name"]]])
    res = []
    for _k, x, lv in out:
        lab = lv[0] if len(lv) == 1 else f"{lv[0]} – {lv[-1]}"
        res.append({**x, "level_name": lab, "n": len(lv), "label": f"{x['name']} · {lv[0] if len(lv) == 1 else f'{len(lv)} pisos'}"})
    return res


GLOBAL_CTL = ("Nic", "Nvc", "Classe", "Renov", "Ventila")


def _pt_blocks(m: Frame, t: dict, W, G) -> tuple[str, str, list, list]:
    us_all = t["units"]
    us = _groups(us_all, lambda x: (x["name"], x["typology"], round(x["Nic"], 1), round(x["Ntc"], 1), round(x["phi_w"])))
    c = t["climate"]
    cls = {}
    for x in us_all:
        cls[x["classe"]] = cls.get(x["classe"], 0) + 1
    order = ["A+", "A", "B", "B-", "C", "D", "E", "F"]
    worst = max(us, key=lambda x: x["RNt"])
    phi = sum(x["phi_w"] for x in us_all) / 1000
    ok_all = all(x["ok"] for x in us_all)
    kp = [{"label": "Classes energéticas", "value": " · ".join(f"{k}×{cls[k]}" for k in order if k in cls), "ok": worst["RNt"] <= 0.50 + 1e-9},
          {"label": "RNt máximo (fração)", "value": f(worst["RNt"], 2), "unit": worst["name"][:22], "ok": worst["RNt"] <= 0.50 + 1e-9},
          {"label": "Potência de aquecimento", "value": f(phi, 1), "unit": "kW (edifício)"},
          {"label": "Fotovoltaico coletivo", "value": f(t["pv_kwp"], 1), "unit": "kWp"}]
    b = [("kpis", kp),
         ("p", "Estudo INDICATIVO do comportamento térmico segundo a metodologia do REH (DL 101-D/2020, Portaria 138-I/2021, Despachos 6476-E e "
               "6476-H/2021), fração a fração, a partir da geometria do levantamento. Não substitui o projeto de comportamento térmico assinado nem o "
               "certificado energético SCE emitido por Perito Qualificado (ADENE)."),
         ("h2", "1. Enquadramento e clima"),
         ("p", f"Concelho : {(t.get('concelho') or 'não identificado').title()} · NUTS III {c['nuts']} · altitude {c['altitude_m']:.0f} m · "
               f"GD {c['GD']:.0f} °C.dia · estação de aquecimento M = {num(c['M'], 1)} meses · Gsul {c['Gsul']:.0f} kWh/m².mês · "
               f"θext,v {num(c['theta_v'], 1)} °C · zonas climáticas {c['zona_i']} (inverno) / {c['zona_v']} (verão) · "
               f"θ de projeto (aquecimento) {num(us[0]['te'], 1)} °C · {len(us_all)} frações, área útil total {f(sum(x['Ap'] for x in us_all), 0)} m²."),
         ("h2", "2. Soluções construtivas da envolvente (U calculado — NP EN ISO 6946)")]
    b += _sol_blocks(t["solutions"], True, W)
    b += [("h2", "3. Síntese por fração"),
          ("table", ["Fração", "Piso", "Tip.", "Ap m²", "Nic / Ni", "Nvc / Nv", "Ntc / Nt", "RNt", "Classe", "Φ kW"],
           [[x["name"][:26], x["level_name"][:24], x["typology"], f(x["Ap"], 1), f"{f(x['Nic'])} / {f(x['Ni'])}", f"{f(x['Nvc'])} / {f(x['Nv'])}",
             f"{f(x['Ntc'])} / {f(x['Nt'])}", f(x["RNt"], 2), x["classe"], f(x["phi_w"] / 1000, 2)] for x in us],
           [30 * W, 24 * W, 10 * W, 14 * W, 20 * W, 18 * W, 20 * W, 11 * W, 12 * W, 11 * W]),
          ("chart", G.jauges([(x["label"][:26], x["RNt"] / 0.50, f"RNt {f(x['RNt'], 2)} · {x['classe']}") for x in us][:24],
                             "RNt de cada fração relativo ao requisito NZEB (classe ≥ A : RNt ≤ 0,50)"),
           "Verde ≤ 90 % do requisito, âmbar entre 90 e 100 %, vermelho acima."),
          ("chart", G.barres_h([(x["label"][:26], x["phi_w"] / 1000) for x in us][:24], "Potência de aquecimento de projeto por fração (kW por fração)", "kW",
                               couleur=G.SERIES[1]))]
    b.append(("h2", "4. Cálculo detalhado por fração"))
    for k, x in enumerate(us, 1):
        r = x["calc"]
        b.append(("p", f"4.{k} {x['name']} — {x['level_name']} ({x['typology']}) · Ap = {f(x['Ap'], 1)} m² · pé-direito {f(x['ch'], 2)} m · "
                       f"{r['ocupantes']} ocupantes convencionais"))
        rows = [[TIPO_PT.get(e["tipo"], e["tipo"]) + (f" {e['orientacao']}" if e.get("orientacao") and e["orientacao"] != "H" else ""),
                 FRONT.get(e.get("fronteira") or "exterior", e.get("fronteira") or "exterior"), f(e["area_m2"], 2), f(e["U"], 2), f(e["btr"], 2),
                 f(e["H"], 2)] for e in x["env"]]
        rows.append(["Pontes térmicas lineares Σψ·B", "", "", "", "", f(x["hp"], 2)])
        rows.append(["Htr (transmissão)", "", "", "", "", f(r["Htr"], 1)])
        rows.append([f"Hve (ventilação, Rph {num(r['rph'], 2)} h⁻¹)", "", "", "", "", f(r["Hve"], 1)])
        b.append(("table", ["Elemento", "Fronteira", "A m²", "U", "btr", "H W/°C"], rows, [60 * W, 24 * W, 22 * W, 18 * W, 16 * W, 22 * W]))
        u = r["ntc_usos"]
        bal = [["Perdas por transmissão Qtr = 0,024·GD·Htr", f"{f(r['Qtr'], 0)} kWh"], ["Perdas por ventilação Qve = 0,024·GD·Hve", f"{f(r['Qve'], 0)} kWh"],
               ["Ganhos internos Qint (4 W/m²)", f"{f(r['Qint'], 0)} kWh"], ["Ganhos solares Qsol (vãos)", f"{f(r['Qsol'], 0)} kWh"],
               ["Fator de utilização dos ganhos ηi", f(r["eta_i"], 2)],
               ["Nic / Ni (aquecimento)", f"{f(x['Nic'])} / {f(x['Ni'])} kWh/(m².ano)"], ["Nvc / Nv (arrefecimento)", f"{f(x['Nvc'])} / {f(x['Nv'])} kWh/(m².ano)"],
               ["Qa (AQS)", f"{f(r['Qa'], 0)} kWh/ano"],
               ["Energia primária : aquec. / arref. / AQS / ventilação", f"{f(u['aquecimento'])} / {f(u['arrefecimento'])} / {f(u['aqs'])} / {f(u['ventilacao'])} kWhEP/(m².ano)"],
               ["Dedução renováveis (fotovoltaico)", f"− {f(u['renovavel'])} kWhEP/(m².ano) ({f(x['ren_kwh'], 0)} kWh/ano)"],
               ["Ntc / Nt → RNt → classe", f"{f(x['Ntc'])} / {f(x['Nt'])} → {f(x['RNt'], 2)} → {x['classe']}"],
               [f"Potência de aquecimento Φ = (Htr + Hve)·(20 − θe) com θe = {num(x['te'], 1)} °C", f"{f(x['phi_w'], 0)} W"]]
        b.append(("table", ["Balanço energético (REH)", "Valor"], bal, [110 * W, 70 * W]))
        b.append(("controls", [{"ref": f"{x['label'][:22]} — {c_['ref']}", "exigence": c_["exigencia"].replace(".", ","),
                                "valeur": c_["valor"].replace(".", ","), "ok": c_["ok"]}
                               for c_ in r["controles"] if c_["ref"].startswith(GLOBAL_CTL)]))
    plages, lo = [], None
    for lim, cl in ((0.25, "A+"), (0.50, "A"), (0.75, "B"), (1.00, "B-"), (1.50, "C"), (2.00, "D"), (2.50, "E"), (None, "F")):
        plages.append((cl, f"≤ {num(lim)}" if lo is None else (f"> {num(lo)}" if lim is None else f"{num(lo + 0.01)} a {num(lim)}")))
        lo = lim
    b += [("h2", "5. Classes energéticas do edifício"),
          ("chart", G.etiquette(plages, {k: f"{v} fração(ões)" for k, v in cls.items()}, "Classe energética — RNt = Ntc/Nt", couleurs=G.REH_COULEURS),
           "Classe = posição de RNt na escala do SCE (Despacho 6476-H/2021).")]
    from .thermal import emitters
    em = _groups(emitters(t)["rows"], lambda x: (x["name"], x["typology"], round(x["phi_w"])))
    b += [("h2", "6. Potências de projeto e emissores"),
          ("table", ["Fração", "Φ kW", "Sistema proposto", "Unidades"], [[x["label"][:30], f(x["kw"], 2), x["system"], x["units_txt"]] for x in em],
           [44 * W, 18 * W, 70 * W, 48 * W]),
          ("p", "Potências majoradas de 15 % para a escolha dos equipamentos ; ventilação mecânica com extração na cozinha e instalações sanitárias "
                "e admissão nos compartimentos principais (NP 1037-1).")]
    sous = (f"{m.project.get('name') or 'Edifício'} · {len(us_all)} frações · {c['nuts']} ({c['zona_i']}/{c['zona_v']}) · "
            + ("todas as frações com requisitos cumpridos" if ok_all else "pelo menos uma fração com requisito não cumprido"))
    return "Estudo de comportamento térmico — pré-certificado REH por fração", sous, b, t["hyp"]


def _fr_blocks(m: Frame, t: dict, W, G) -> tuple[str, str, list, list]:
    us_all = t["units"]
    us = _groups(us_all, lambda x: (x["name"], x["typology"], round(x["phi_w"])))
    re = t.get("re2020") or {}
    b, hyp = [], list(t["hyp"])
    phi = sum(x["phi_w"] for x in us_all) / 1000
    if re.get("blocs"):
        bl = list(re["blocs"])
        # renumérote les sections de la pré-étude RE2020 (1 à 6) et insère les solutions constructives
        b += bl
        hyp += re.get("hypotheses") or []
    else:
        b.append(("p", "Pré-étude RE2020 non calculée : " + str(re.get("error") or "données insuffisantes") + "."))
    b += [("h2", "7. Solutions constructives (U calculé — NF EN ISO 6946)")]
    b += _sol_blocks(t["solutions"], False, W)
    b += [("h2", "8. Déperditions et puissance de chauffage par logement (NF EN 12831 simplifiée)"),
          ("table", ["Logement", "Niveau", "Typo.", "S m²", "H parois W/K", "H ponts W/K", "H air W/K", "Φ kW"],
           [[x["name"][:26], x["level_name"][:24], x["typology"], f(x["Ap"], 1), f(x["H"] - x["hp"], 1), f(x["hp"], 1), f(x["Hv"], 1),
             f(x["phi_w"] / 1000, 2)] for x in us], [32 * W, 26 * W, 12 * W, 14 * W, 24 * W, 24 * W, 22 * W, 18 * W]),
          ("chart", G.barres_h([(x["label"][:26], x["phi_w"] / 1000) for x in us][:24], "Puissance de chauffage par logement", "kW", couleur=G.SERIES[1]))]
    for k, x in enumerate(us, 1):
        b.append(("p", f"8.{k} {x['name']} — {x['level_name']} ({x['typology']}) · S = {f(x['Ap'], 1)} m² · θe = {f(x['te'], 0)} °C"))
        rows = [[r["label"], f(r["A"], 2), f(r["U"], 2), f(r["b"], 2), f(r["H"], 2)] for r in x["rows"]]
        rows += [[f"Pont thermique — {n}", f"{f(L, 1)} m", f"ψ {f(v, 2)}", "", f(v * L, 2)] for n, v, L in x["psi"]]
        rows += [["Renouvellement d'air (VMC hygro B)", "", "", "", f(x["Hv"], 1)],
                 [f"Puissance Φ = ΣH × (19 − θe)", "", "", "", f"{f(x['phi_w'], 0)} W"]]
        b.append(("table", ["Paroi", "A m²", "U", "b", "H W/K"], rows, [80 * W, 24 * W, 22 * W, 16 * W, 24 * W]))
    from .thermal import emitters
    em = _groups(emitters(t)["rows"], lambda x: (x["name"], x["typology"], round(x["phi_w"])))
    b += [("h2", "9. Émetteurs proposés"),
          ("table", ["Logement", "Φ kW", "Système", "Dimensionnement"], [[x["label"][:30], f(x["kw"], 2), x["system"], x["units_txt"]] for x in em],
           [44 * W, 18 * W, 70 * W, 48 * W])]
    titre = "Étude thermique — pré-étude RE2020 et déperditions par logement"
    sous = (f"{m.project.get('name') or 'Bâtiment'} · {len(us_all)} logements · " +
            (f"zone {re['zone']} · Bbio {re['Bbio']:.0f} / {re['seuils']['Bbio_max']:.0f}" if re.get("blocs") else "RE2020 à compléter") +
            f" · Φ total {f(phi, 1)} kW")
    return titre, sous, b, hyp


def write(m: Frame, t: dict, path: str | Path, lang: str) -> Path:
    from engines.calc_lots import graficos as G
    from engines.calc_lots import rendu
    from reportlab.lib.units import mm as W
    titre, sous, blocs, hyp = (_pt_blocks if t["country"] == "PT" else _fr_blocks)(m, t, W, G)
    pt = lang == "pt"
    blocs = blocs + [("h2", "Hipóteses / a validar" if pt else "Hypothèses / à valider"), ("hyp", hyp or ["—"])]
    old = dict(rendu.LANG)
    rendu.LANG.update(LANG_PT if pt else LANG_FR)
    try:
        data = rendu.build_pdf(titre, sous, blocs, footer=FOOT["pt" if pt else "fr"])
    finally:
        rendu.LANG.clear()
        rendu.LANG.update(old)
    p = Path(path)
    p.write_bytes(data)
    return p
