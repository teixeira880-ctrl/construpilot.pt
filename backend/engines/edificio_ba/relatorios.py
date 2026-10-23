"""Notas PDF (PT / FR) : memória de cálculo da estrutura, mapa de medições, orçamento estimativo e quadro de quantidades.
Renderização comum ConstruPilot (engines.calc_lots.rendu)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.units import mm
from reportlab.platypus import Image

from engines.calc_lots import graficos as G
from engines.calc_lots import rendu

from . import estrutura as ES
from . import fem3d
from .medicoes import CAPS, KG
from .textos import fmt as f

W = mm


def _sub(S):
    cave = S.t("cave + ", "sous-sol + ") if S.basement else ""
    return f"{S.address or S.municipality} · {cave}{S.n} {S.t('pisos', 'niveaux')} · {len(S.units)} {S.t('frações', 'logements')} · {S.t('betão armado', 'béton armé')}"


def norm_ctl(ctl):
    """ok numpy → bool Python (o renderizador compara com « is True »)."""
    for c in ctl:
        if c.get("ok") is not None:
            c["ok"] = bool(c["ok"])
    return ctl


def _write(path, pdf):
    Path(path).write_bytes(pdf)
    return path


# ------------------------------------------------------------------ memória de cálculo
def memoria(S, R, path, out_dir) -> Path:
    T = S.t
    s = R["seis"]
    b = []
    b.append(("kpis", [
        {"label": T("Pisos", "Niveaux"), "value": f"{'−1 + ' if S.basement else ''}{S.n}"},
        {"label": T("Período T1", "Période T1"), "value": f(R["fem"]["modes"][0]["T"] if R.get("fem") else s.get("T1", 0), 3), "unit": "s"},
        {"label": T("Corte basal", "Effort tranchant à la base"), "value": f((R["fem"]["Vb"]["X"] if R.get("fem") else (s.get("gov") or {}).get("Fb", 0)), 0), "unit": "kN"},
        {"label": T("Fundações", "Fondations"), "value": str(len(R["fnd"]) + len(R["foots"]))},
    ]))
    b.append(("p", T("Estudo prévio / pré-dimensionamento da estrutura, elaborado a partir das plantas de arquitetura fornecidas. Fixa o sistema estrutural, as "
                     f"secções e as quantidades ; não substitui o projeto de execução de estabilidade, a desenvolver e assinar por {S.prof['engineer']}.",
                     "Étude préalable / prédimensionnement de la structure à partir des plans d'architecte fournis. Elle fixe le système porteur, les sections "
                     f"et les quantités ; elle ne remplace pas les études d'exécution, à établir et signer par un {S.prof['engineer']}.")))
    b.append(("h2", T("1. Objeto e descrição do edifício", "1. Objet et description du bâtiment")))
    lv = S.levels()
    b.append(("p", T(f"Edifício de habitação multifamiliar ({S.name}) : {'uma cave e ' if S.basement else ''}{S.n} pisos de habitação ({lv[0][1]} à cota {f(lv[0][2])} "
                     f"até à {lv[-1][1]} à cota {f(lv[-1][2])}), pé-direito estrutural {f(S.H)} m, {len(S.units)} frações. Planta retangular de {f(S.L)} × {f(S.B)} m "
                     "entre eixos dos pilares de fachada" + (", com varandas em consola" if S.balconies else "") + ".",
                     f"Bâtiment de logements collectifs ({S.name}) : {'un sous-sol et ' if S.basement else ''}{S.n} niveaux ({lv[0][1]} à {f(lv[0][2])} "
                     f"jusqu'à {lv[-1][1]} à {f(lv[-1][2])}), hauteur d'étage {f(S.H)} m, {len(S.units)} logements. Emprise rectangulaire {f(S.L)} × {f(S.B)} m "
                     "entre axes des poteaux de façade" + (", avec balcons en console" if S.balconies else "") + ".")))
    rows = [[T("Área de um piso (entre eixos)", "Surface d'un niveau (entre axes)"), f"{f(S.area_floor, 1)} m²"],
            [T("Varandas por piso", "Balcons par niveau"), f"{f(S.balcony_area(), 1)} m²"],
            [T("Área da cave", "Surface du sous-sol"), f"{f(S.basement_area(), 1)} m²"],
            [T("Pilares / núcleos / paredes", "Poteaux / noyaux / voiles"), f"{len(S.columns)} / {len(S.cores)} / {len(S.walls)}"]]
    b.append(("table", [T("Grandeza", "Grandeur"), T("Valor", "Valeur")], rows, [110 * W, 70 * W]))
    b.append(("h2", T("2. Regulamentação e materiais", "2. Réglementation et matériaux")))
    b.append(("p", S.prof["norms"] + "."))
    M = ES.mat(S)
    b.append(("table", [T("Material / parâmetro", "Matériau / paramètre"), T("Valor", "Valeur")], [
        [T("Betão estrutural", "Béton de structure"), f"{S.concrete} — f_cd = {f(M['fcd'], 1)} MPa · E_cm = {f(M['Ec'] / 1e6, 1)} GPa"],
        [T("Aço", "Acier"), f"{S.prof['steel']} — f_yd = {f(M['fyd'], 0)} MPa"],
        [T("Recobrimentos nominais", "Enrobages nominaux"), T("lajes 25 mm · vigas e pilares 30 mm · varandas 35 mm · fundações e muros 50 mm",
                                                               "dalles 25 mm · poutres et poteaux 30 mm · balcons 35 mm · fondations et voiles enterrés 50 mm")],
        [T("Coeficientes parciais", "Coefficients partiels"), "γ_G = 1,35 · γ_Q = 1,50 · γ_c = 1,50 · γ_s = 1,15"]], [55 * W, 125 * W]))
    b.append(("h2", T("3. Ações", "3. Actions")))
    lab = {"residential": T("Habitação (cat. A)", "Logement (cat. A)"), "balcony": T("Varandas", "Balcons"), "roof": T("Cobertura em terraço", "Toiture-terrasse"),
           "garden": T("Laje sobre a cave (exterior)", "Dalle sur sous-sol (extérieur)"), "stair": T("Escadas comuns", "Escaliers communs")}
    rows = [[lab[k], f(v["g2"], 1), f(v["q"], 1), f(v["psi2"], 1)] for k, v in S.loads.items()]
    rows.append([T("Paredes exteriores (fachada)", "Murs de façade"), f"{f(S.facade_kn_m, 1)} kN/m", "—", "—"])
    b.append(("table", [T("Zona", "Zone"), "G2 (kN/m²)", "Q (kN/m²)", "ψ2"], rows, [95 * W, 30 * W, 30 * W, 25 * W]))
    b.append(("p", T("Combinação fundamental ELU : 1,35 G + 1,50 Q ; combinação sísmica : G + A_Ed + ψ2·Q. Vento e neve sem relevância no pré-dimensionamento "
                     "face à ação sísmica para um edifício de betão com núcleos (a verificar no projeto de execução).",
                     "Combinaison fondamentale ELU : 1,35 G + 1,50 Q ; combinaison sismique : G + A_Ed + ψ2·Q. Vent et neige non dimensionnants au stade du "
                     "prédimensionnement pour un bâtiment en béton à noyaux (à vérifier en exécution).")))
    b.append(("h2", T("4. Sistema estrutural", "4. Système porteur")))
    prop = [w for w in S.walls if w["proposed"]]
    reg0 = R.get("reg0") or {}
    txt = T(f"Lajes maciças h = {f(S.slab_h)} m apoiadas em {len({b_['line'] for b_ in R['beams']})} alinhamentos de vigas (bordadura e interiores, geradas a "
            "partir dos pilares e núcleos), pilares e paredes. Contraventamento sísmico pelos núcleos de escada e elevador",
            f"Dalles pleines h = {f(S.slab_h)} m sur {len({b_['line'] for b_ in R['beams']})} files de poutres (de rive et intérieures, générées à partir des "
            "poteaux et des noyaux), poteaux et voiles. Contreventement par les noyaux d'escalier et d'ascenseur")
    if S.walls:
        txt += T(f" e por {len(S.walls)} paredes resistentes", f" et par {len(S.walls)} voiles")
    txt += "."
    if prop:
        txt += T(f" As paredes {', '.join(w['id'] for w in prop)} são PROPOSTAS por este estudo : sem elas o centro de rigidez ficaria a "
                 f"{f(max(reg0.get('e0x', 0), reg0.get('e0y', 0)), 1) if reg0.get('KX') else '—'} m do centro de massa e o edifício seria sensível à torção.",
                 f" Les voiles {', '.join(w['id'] for w in prop)} sont PROPOSÉS par cette étude : sans eux le centre de torsion serait à "
                 f"{f(max(reg0.get('e0x', 0), reg0.get('e0y', 0)), 1) if reg0.get('KX') else '—'} m du centre de masse (bâtiment sensible à la torsion).")
    b.append(("p", txt))
    # 5 lajes
    b.append(("h2", T("5. Lajes maciças", "5. Dalles pleines")))
    rows = []
    for sl in R["slabs"]:
        r = sl["r"]
        try:
            bx = ES.mesh(r["span"]["x"]["as_req_cm2_m"])[0]
            by = ES.mesh(r["span"]["y"]["as_req_cm2_m"])[0]
            bs = ES.mesh(max(v["as_req_cm2_m"] for v in r["supports"].values()))[0]
            rows.append([sl["name"], f"{f(sl['lx'])} × {f(sl['ly'])}", f(sl["h"]), f(r["loads"]["pu"], 1), f(r["span"]["x"]["m_knm"], 1), f"{bx} / {by}", bs,
                         f(r["deflection_ld"]["l_over_d"], 1)])
        except (KeyError, TypeError, ValueError):
            rows.append([sl["name"], f"{f(sl['lx'])} × {f(sl['ly'])}", f(sl["h"]), "—", "—", "—", "—", "—"])
    b.append(("table", [T("Painel", "Panneau"), "lx × ly (m)", "h (m)", "p_Ed (kN/m²)", "M_Ed,x (kN.m/m)", T("Inferior x / y", "Inférieur x / y"),
                        T("Superior (apoios)", "Supérieur (appuis)"), "L/d"], rows, [16 * W, 26 * W, 13 * W, 22 * W, 25 * W, 36 * W, 26 * W, 16 * W]))
    b.append(("p", T("Painéis delimitados automaticamente por vigas, paredes, núcleos e contorno ; regiões não retangulares decompostas em retângulos com bordo livre "
                     "na linha de corte (a favor da segurança). Lajes em duas direções (coeficientes de Pigeaud, continuidade), EN 1992-1-1 §6.1, §9.3.1.1, §7.4.2.",
                     "Panneaux délimités automatiquement par les poutres, voiles, noyaux et le contour ; régions non rectangulaires découpées en rectangles avec bord "
                     "libre sur la ligne de coupe (sécuritaire). Dalles portant dans deux directions (Pigeaud, continuité), EN 1992-1-1 §6.1, §9.3.1.1, §7.4.2.")))
    if R["cant"]:
        b.append(("h2", T("6. Varandas em consola", "6. Balcons en console")))
        rows = [[f(c["depth"]), f(c["pu"], 2), f(c["M_Ed"], 1), f(c["V_Ed"], 1), f"{f(c['as_cm2_m'], 2)} → {ES.mesh(c['as_cm2_m'])[0]}", f"{f(c['w_mm'], 1)} ≤ {f(c['w_lim_mm'], 1)}"]
                for c in R["cant"].values()]
        b.append(("table", [T("Consola (m)", "Console (m)"), "p_Ed (kN/m²)", "M_Ed (kN.m/m)", "V_Ed (kN/m)", T("A_s superior", "A_s supérieur"), T("Flecha (mm)", "Flèche (mm)")],
                  rows, [24 * W, 26 * W, 28 * W, 26 * W, 46 * W, 30 * W]))
    # 7 vigas
    b.append(("h2", T("7. Vigas", "7. Poutres")))
    rows = [[x["name"], f(x["L"]), f"{int(x['b_w'] * 100)}×{int(x['h'] * 100)}", f(x["trib"]), f(x["w_kNm"], 1), f(x["M_sup"], 0), f(x["V"], 0),
             f"{f(x['As'], 1)} → {ES.beam_bars(x['As'])[0]}", f(x["w_mm"], 0)] for x in R["beams"] + (R.get("gbeam_design") or [])]
    b.append(("table", [T("Viga", "Poutre"), T("Vão (m)", "Portée (m)"), "b×h", T("Larg. infl. (m)", "Larg. infl. (m)"), "p_Ed (kN/m)", "M_Ed (kN.m)", "V_Ed (kN)",
                        T("A_s → varões", "A_s → barres"), T("Flecha (mm)", "Flèche (mm)")], rows,
              [16 * W, 15 * W, 15 * W, 18 * W, 20 * W, 20 * W, 18 * W, 38 * W, 18 * W]))
    b.append(("p", T("Vigas carregadas pelos painéis adjacentes (cargas trapezoidais / triangulares equivalentes), pela fachada e pelas varandas. Momentos p·L²/10 "
                     "(apoio) e p·L²/11 (vão) em vigas contínuas ; flecha a longo prazo ≈ 3 × flecha elástica com EI fendilhado, ≤ L/250.",
                     "Poutres chargées par les panneaux adjacents (charges trapézoïdales / triangulaires équivalentes), la façade et les balcons. Moments p·L²/10 "
                     "(appui) et p·L²/11 (travée) en continuité ; flèche différée ≈ 3 × flèche élastique (EI fissuré), ≤ L/250.")))
    # 8 pilares
    b.append(("h2", T("8. Pilares — descida de cargas", "8. Poteaux — descente de charges")))
    rows = []
    by = {r["id"]: r for r in R["rows"]}
    for col in R["cols"]:
        bb = col["base"]
        a = by.get(col["id"], {})
        tp = col.get("topo") if col.get("topo") is not col["base"] else None
        rows.append([col["id"], f"{f(col['x'])} ; {f(col['y'])}", f(a.get("A_hab", 0), 1), f(a.get("A_balc", 0), 1), f(a.get("A_gar", 0), 1),
                     f"{int(round(bb['b'] * 100))}×{int(round(bb['h'] * 100))}", f(bb["N_Ed"], 0), f(bb["nu"]), ES.bars(bb["As_cm2"])[0],
                     f"{int(round(tp['b'] * 100))}×{int(round(tp['h'] * 100))}" if tp else "—"])
    b.append(("table", [T("Pilar", "Poteau"), "X ; Y (m)", T("A laje", "A dalle"), T("A varanda", "A balcon"), T("A cave ext.", "A s.-sol ext."), T("Base", "Pied"),
                        "N_Ed (kN)", "ν", T("Armadura", "Armatures"), T("Topo", "Tête")], rows,
              [14 * W, 26 * W, 16 * W, 18 * W, 18 * W, 18 * W, 20 * W, 12 * W, 22 * W, 16 * W]))
    b.append(("chart", G.barres_h([(c_["id"], c_["base"]["N_Ed"]) for c_ in R["cols"]], T("Esforço normal de cálculo na base dos pilares", "Effort normal de calcul en pied"), "kN"),
              T("Áreas de influência : cada ponto da laje atribuído ao elemento vertical mais próximo (pilar, parede ou núcleo). ν ≤ 0,65.",
                "Surfaces d'influence : chaque point de dalle affecté à l'élément vertical le plus proche (poteau, voile ou noyau). ν ≤ 0,65.")))
    # 9 sismo
    b.append(("h2", T("9. Ação sísmica — método das forças laterais", "9. Action sismique — méthode des forces latérales") + f" ({S.prof['seismic_ref']})"))
    if s.get("ok"):
        acts = s["acts"]
        head = [T("Parâmetro", "Paramètre")] + [a["label"] for a in acts]
        rows = [["a_gR (m/s²)"] + [f(a["agR"]) for a in acts], ["a_g = γ_I·a_gR (m/s²)"] + [f(a["ag"]) for a in acts],
                [T(f"Terreno tipo {S.soil['ground']} : S", f"Sol de classe {S.soil['ground']} : S")] + [f(a["S"]) for a in acts],
                ["T_B / T_C / T_D (s)"] + [f"{f(a['TB'])} / {f(a['TC'])} / {f(a['TD'], 1)}" for a in acts],
                [f"S_d(T_1 = {f(s['T1'], 3)} s), q = {f(s['q'], 1)}"] + [f(a["Sd"], 3) for a in acts], ["F_b (kN)"] + [f(a["Fb"], 0) for a in acts]]
        b.append(("table", head, rows, [80 * W] + [100 / len(acts) * W] * len(acts)))
        if not s["required"]:
            w = s["wind"]
            b.append(("p", T(f"Sem exigência sísmica regulamentar para esta zona e classe de importância : espectro dado a título indicativo ; o contraventamento "
                             f"(núcleos, paredes, fundações) é verificado ao VENTO (forfait c_f = {f(w['cf'], 1)}, q_p = {f(w['qp'], 2)} kPa) : "
                             f"F_X = {f(w['Fx'], 0)} kN, F_Y = {f(w['Fy'], 0)} kN.",
                             f"Zone de sismicité et catégorie d'importance sans exigence parasismique (arrêté du 22/10/2010) : spectre donné à titre indicatif ; "
                             f"le contreventement (noyaux, voiles, fondations) est vérifié au VENT (forfait c_f = {f(w['cf'], 1)}, q_p = {f(w['qp'], 2)} kPa, "
                             f"EN 1991-1-4) : F_X = {f(w['Fx'], 0)} kN, F_Y = {f(w['Fy'], 0)} kN — à confirmer par l'étude au vent.")))
        rg = s["reg"]
        b.append(("p", T(f"Base sísmica ao nível do {S.lname(0)}{' (a cave é uma caixa rígida de muros de betão)' if S.basement else ''}. T_1 = 0,05·H^0,75, H = {f(s['H'], 1)} m. "
                         f"Peso sísmico W = {f(s['W'], 0)} kN. Centro de massa ({f(rg['xm'], 2)} ; {f(rg['ym'], 2)}), centro de rigidez ({f(rg['xr'], 2)} ; {f(rg['yr'], 2)}), "
                         f"raios de torção {f(rg['r_x'], 2)} / {f(rg['r_y'], 2)} m (l_s = {f(rg['ls'], 2)} m). Ação condicionante : {s['gov']['label']}, F_b = {f(s['gov']['Fb'], 0)} kN.",
                         f"Base sismique au niveau {S.lname(0)}{' (sous-sol en caisson rigide de voiles)' if S.basement else ''}. T_1 = 0,05·H^0,75, H = {f(s['H'], 1)} m. "
                         f"Poids sismique W = {f(s['W'], 0)} kN. Centre de masse ({f(rg['xm'], 2)} ; {f(rg['ym'], 2)}), centre de torsion ({f(rg['xr'], 2)} ; {f(rg['yr'], 2)}), "
                         f"rayons de torsion {f(rg['r_x'], 2)} / {f(rg['r_y'], 2)} m (l_s = {f(rg['ls'], 2)} m). Action dimensionnante : {s['gov']['label']}, F_b = {f(s['gov']['Fb'], 0)} kN.")))
        b.append(("chart", G.barres_h([(x["level"], x["F"]) for x in s["storeys"]], T("Forças sísmicas por piso", "Forces sismiques par niveau"), "kN"),
                  T(f"Momento derrubador na base M_0 = {f(s['M0'], 0)} kN.m.", f"Moment de renversement M_0 = {f(s['M0'], 0)} kN.m.")))
        rows = []
        for e in s["elems"]:
            sx = next(z for z in s["dist"]["X"]["elems"] if z["id"] == e["id"])
            sy = next(z for z in s["dist"]["Y"]["elems"] if z["id"] == e["id"])
            rows.append([e["id"], f"{f(e['x'])} ; {f(e['y'])}", f(e["Iy"], 2), f(e["Ix"], 2), f"{f(sx['share'] * 100, 0)} %", f"{f(sy['share'] * 100, 0)} %",
                         f"{f(sx['V'], 0)} / {f(sy['V'], 0)}"])
        b.append(("table", [T("Elemento", "Élément"), T("Centro (m)", "Centre (m)"), "I_y (m⁴)", "I_x (m⁴)", T("Parte X", "Part X"), T("Parte Y", "Part Y"),
                            "V_Ed X / Y (kN)"], rows, [32 * W, 26 * W, 20 * W, 20 * W, 20 * W, 20 * W, 42 * W]))
        dr = s["drift"]
        b.append(("table", [T("Direção", "Direction"), "d_e (mm)", "d_s (mm)", "d_r (mm)", "ν·d_r (mm)", T("Limite 0,005·h", "Limite 0,005·h")],
                  [[d, f(v["d_e_mm"], 1), f(v["d_s_mm"], 1), f(v["dr_mm"], 1), f(v["nu_dr_mm"], 1), f(v["lim_mm"], 1)] for d, v in dr.items()],
                  [22 * W, 30 * W, 30 * W, 34 * W, 30 * W, 34 * W]))
    # 10 núcleos e paredes
    b.append(("h2", T("10. Núcleos e paredes resistentes", "10. Noyaux et voiles de contreventement")
              + (T(" (esforços do modelo 3D)", " (efforts du modèle 3D)") if R.get("fem") else "")))
    rows = []
    for cd in (s.get("cores") or []) + (s.get("walls") or []):
        for d in ("X", "Y"):
            v = cd[d]
            if cd["kind"] == "wall" and v["Lw"] < 0.5:
                continue
            rows.append([f"{cd['id']} ({d})", f(cd["N_sis"], 0), f(v["M"], 0), f(v.get("M_simpl", v["M"]), 0), f(v["V"], 0), f(v["Lw"], 2),
                         f"{f(v['As_ext_cm2'], 1)} → {ES.bars(v['As_ext_cm2'])[0]}", f"{f(v['rho_h'] * 100, 2)} %"])
    b.append(("table", [T("Elemento", "Élément"), "N (kN)", "M_Ed (kN.m)", T("M simplif.", "M simplifié"), "V_Ed (kN)", "l_w (m)", T("A_s extremidade", "A_s about"), "ρ_h"],
              rows, [32 * W, 20 * W, 22 * W, 20 * W, 20 * W, 14 * W, 34 * W, 18 * W]))
    b.append(("p", T("Flexão composta (z = 0,8·l_w), elementos de extremidade (ρ ≥ 0,5 %, §5.4.3.4.2), corte amplificado ε = 1,5 (DCM), V_Rd,c ≈ 0,35 MPa, "
                     "armadura horizontal mínima 0,2 %. Elementos de extremidade confinados na altura crítica h_cr = máx(l_w ; H/6).",
                     "Flexion composée (z = 0,8·l_w), éléments de rive (ρ ≥ 0,5 %, §5.4.3.4.2), effort tranchant majoré ε = 1,5 (DCM), V_Rd,c ≈ 0,35 MPa, "
                     "aciers horizontaux minimaux 0,2 %. Éléments de rive confinés sur la hauteur critique h_cr = max(l_w ; H/6).")))
    # 11 muros
    if R["bwalls"]:
        b.append(("h2", T("11. Muros de cave", "11. Voiles enterrés")))
        rows = [[w["name"], f(w["L"]), f(w["ht"], 1) if w["ht"] else "—", f(w["t"]), f(w["M"], 1) if w["ht"] else "—",
                 f"{f(w['As'], 1)} → {ES.mesh(w['As'])[0]}" if w["ht"] else T("Ø10//0,20 (mín.)", "HA10 e=20 (min.)")] for w in R["bwalls"]]
        b.append(("table", [T("Muro", "Voile"), T("Compr. (m)", "Long. (m)"), T("Terras (m)", "Terres (m)"), "e (m)", "M_Ed (kN.m/m)", T("Armadura vertical (terras)", "Aciers verticaux (côté terres)")],
                  rows, [40 * W, 24 * W, 24 * W, 14 * W, 24 * W, 54 * W]))
        b.append(("p", T("Muros apoiados na laje do Piso 0 e na fundação, impulso em repouso K_0 = 0,50, γ = 20 kN/m³, sobrecarga 10 kN/m², drenados.",
                         "Voiles appuyés sur la dalle haute et la fondation, poussée au repos K_0 = 0,50, γ = 20 kN/m³, surcharge 10 kN/m², drainés.")))
    # 12 fundações
    b.append(("h2", T("12. Fundações", "12. Fondations")))
    rows = [[f"S{x['id'].lstrip('P')}", f"{f(x['x1'] - x['x0'])} × {f(x['y1'] - x['y0'])} × {f(x['h'])}", f(x["N_Ed"], 0), f(x["sigma_Ed"], 0),
             ES.mesh(x["As_cm2"] / max(x["x1"] - x["x0"], x["y1"] - x["y0"]))[0]] for x in R["foots"]]
    rows += [[x["id"] + " (" + ", ".join(x["members"]) + ")", f"{f(x['L'])} × {f(x['B'])} × {f(x['h'])}", "—", f(x.get("sigma_grav") or 0, 0),
              T("Ø16//0,15 inf. + sup.", "HA16 e=15 inf. + sup.")] for x in R["fnd"]]
    b.append(("table", ["Ref.", "B × L × h (m)", "N_Ed (kN)", "σ_Ed (kPa)", T("Armadura (2 dir.)", "Armatures (2 dir.)")], rows, [44 * W, 44 * W, 24 * W, 24 * W, 44 * W]))
    so = S.soil
    b.append(("p", T(f"σ_Rd = {f(so['sigma_rd'], 0)} kPa (ELU) / {f(so['sigma_sls'], 0)} kPa (serviço) — {'estudo geotécnico' if so['report'] else 'valores ADMITIDOS, a confirmar por estudo geotécnico'}. "
                     "Ensoleiramentos sob núcleos e paredes à combinação sísmica com largura efetiva B' = B − 2e (EN 1997-1, Anexo D) ; sapatas isoladas que tocam um "
                     "ensoleiramento são nele integradas ; lintéis de travamento entre sapatas (EN 1998-5).",
                     f"σ_Rd = {f(so['sigma_rd'], 0)} kPa (ELU) / {f(so['sigma_sls'], 0)} kPa (ELS) — {'étude de sol' if so['report'] else 'valeurs ADMISES, à confirmer par une G2'}. "
                     "Radiers sous noyaux et voiles en combinaison sismique avec largeur effective B' = B − 2e (EN 1997-1, annexe D) ; semelles isolées touchant un radier "
                     "intégrées à celui-ci ; longrines de liaison entre semelles (EN 1998-5).")))
    # 13 3D
    if R.get("fem") and R.get("_F"):
        fm = R["fem"]
        b.append(("h2", T("13. Análise 3D por elementos finitos (espectro de resposta)", "13. Analyse 3D aux éléments finis (spectre de réponse)")))
        pm, pmo = Path(out_dir) / "fem_model.png", Path(out_dir) / "fem_modes.png"
        try:
            fem3d.figures(S, R["_F"], pm, pmo)
            figs = True
        except Exception:  # noqa: BLE001
            figs = False
        b.append(("p", T(f"Modelo da superestrutura (OpenSees) com {fm['n_nodes']} nós e {fm['n_el']} elementos : núcleos e paredes em cascas ShellMITC4, pilares e vigas em "
                         "barras, lajes como diafragmas rígidos. Rigidez fendilhada 0,5·EI. Análise modal, CQC (ξ = 5 %), excentricidade acidental ± 5 %, E_X ± 0,3·E_Y.",
                         f"Modèle de la superstructure (OpenSees) : {fm['n_nodes']} nœuds, {fm['n_el']} éléments — noyaux et voiles en coques ShellMITC4, poteaux et poutres "
                         "en barres, dalles en diaphragmes rigides. Raideur fissurée 0,5·EI. Analyse modale, CQC (ξ = 5 %), excentricité accidentelle ± 5 %, E_X ± 0,3·E_Y.")))
        if figs:
            b.append(("figure", Image(str(pm), width=150 * mm, height=95 * mm), T("Modelo 3D.", "Modèle 3D.")))
        rows = []
        cx = cy = 0.0
        for m in fm["modes"]:
            cx += m["Mx"]
            cy += m["My"]
            kind = T("torção", "torsion") if m["Mr"] > max(m["Mx"], m["My"]) else ("X" if m["Mx"] > m["My"] else "Y")
            rows.append([str(m["mode"]), f(m["T"], 3), f(m["Mx"] * 100, 1), f(m["My"] * 100, 1), f(m["Mr"] * 100, 1), f(cx * 100, 1), f(cy * 100, 1), kind])
        b.append(("table", [T("Modo", "Mode"), "T (s)", "M_X (%)", "M_Y (%)", "M_θ (%)", "Σ M_X", "Σ M_Y", T("Tipo", "Type")], rows,
                  [14 * W, 18 * W, 20 * W, 20 * W, 20 * W, 22 * W, 22 * W, 44 * W]))
        if figs:
            b.append(("figure", Image(str(pmo), width=170 * mm, height=57 * mm), T("Três primeiros modos (planta da cobertura).", "Trois premiers modes (plan de toiture).")))
        dfm = s.get("drift_fem", {})
        b.append(("table", [T("Grandeza", "Grandeur"), T("Método simplificado", "Méthode simplifiée"), T("Modelo 3D", "Modèle 3D")], [
            [T("Período fundamental (s)", "Période fondamentale (s)"), f(s["T1"], 3), f(fm["modes"][0]["T"], 3)],
            [T("Corte basal X / Y (kN)", "Tranchant à la base X / Y (kN)"), f(s["gov"]["Fb"], 0), f"{f(fm['Vb']['X'], 0)} / {f(fm['Vb']['Y'], 0)}"],
            ["ν·d_r X / Y (mm)", f"{f(s['drift']['X']['nu_dr_mm'], 1)} / {f(s['drift']['Y']['nu_dr_mm'], 1)}",
             f"{f(dfm.get('X', {}).get('nu_dr_mm', 0), 1)} / {f(dfm.get('Y', {}).get('nu_dr_mm', 0), 1)}"]], [80 * W, 50 * W, 50 * W]))
    # 14 verificações
    ctl = []
    for sl in R["slabs"]:
        ld = (sl["r"] or {}).get("deflection_ld") or {}
        if ld:
            ctl.append({"ref": T(f"Laje {sl['name']} — deformação (L/d)", f"Dalle {sl['name']} — flèche (L/d)"), "exigence": "L/d ≤ §7.4.2",
                        "valeur": f(ld.get("l_over_d", 0), 1), "ok": ld.get("ok")})
    for x in R["beams"] + (R.get("gbeam_design") or []):
        ctl.append({"ref": T(f"Viga {x['name']} — flecha", f"Poutre {x['name']} — flèche"), "exigence": f"≤ L/250 = {f(x['L'] / 250 * 1000, 0)} mm",
                    "valeur": f"{f(x['w_mm'], 0)} mm", "ok": x["w_mm"] <= x["L"] / 250 * 1000})
    for col in R["cols"]:
        ctl.append({"ref": T(f"Pilar {col['id']} — esforço normal reduzido", f"Poteau {col['id']} — effort normal réduit"), "exigence": "ν ≤ 0,65",
                    "valeur": f(col["base"]["nu"]), "ok": col["base"]["nu"] <= 0.65 + 1e-9})
    if s.get("ok"):
        dsrc = s.get("drift_fem") or {d: {"nu_dr_mm": v["nu_dr_mm"], "lim_mm": v["lim_mm"]} for d, v in s["drift"].items()}
        for d, v in dsrc.items():
            ctl.append({"ref": T(f"Deriva entre pisos — {d}", f"Déplacement entre niveaux — {d}"), "exigence": f"ν·d_r ≤ {f(v['lim_mm'], 0)} mm",
                        "valeur": f"{f(v['nu_dr_mm'], 1)} mm", "ok": v["nu_dr_mm"] <= v["lim_mm"]})
        rg = s["reg"]
        ctl.append({"ref": T("Regularidade em planta (torção)", "Régularité en plan (torsion)"), "exigence": "e_0 ≤ 0,30·r ; r ≥ l_s",
                    "valeur": f"e_0 {f(rg['e0x'], 2)} / {f(rg['e0y'], 2)} m ; r {f(rg['r_x'], 2)} / {f(rg['r_y'], 2)} m", "ok": rg["ok"]})
        if R.get("fem"):
            mds = R["fem"]["modes"]
            ctl.append({"ref": T("Massa modal mobilizada", "Masse modale mobilisée"), "exigence": "≥ 90 % X et Y" if S.lang == "fr" else "≥ 90 % em X e Y",
                        "valeur": f"{f(sum(m['Mx'] for m in mds) * 100, 0)} % / {f(sum(m['My'] for m in mds) * 100, 0)} %",
                        "ok": sum(m["Mx"] for m in mds) >= 0.9 and sum(m["My"] for m in mds) >= 0.9})
    for c in R["cant"].values():
        ctl.append({"ref": T(f"Consola {f(c['depth'])} m — flecha", f"Console {f(c['depth'])} m — flèche"), "exigence": f"≤ {f(c['w_lim_mm'], 1)} mm",
                    "valeur": f"{f(c['w_mm'], 1)} mm", "ok": c["w_mm"] <= c["w_lim_mm"]})
    ctl.append({"ref": T("Fundações — terreno", "Fondations — sol"), "exigence": "σ_Ed ≤ σ_Rd", "valeur": f"σ_Rd {f(so['sigma_rd'], 0)} kPa",
                "ok": True if so["report"] else None, "note": None if so["report"] else T("estudo geotécnico obrigatório", "étude G2 obligatoire")})
    b.append(("h2", T("14. Verificações", "14. Vérifications")))
    b.append(("controls", norm_ctl(ctl)))
    hyp = list(R["decisions"]) + [T("Geometria relevada das plantas de arquitetura (precisão ± 5 cm) ; a confirmar com os ficheiros CAD.",
                                    "Géométrie relevée sur les plans d'architecte (± 5 cm) ; à confirmer sur les fichiers DAO."),
                                  T("Vigas, painéis e áreas de influência gerados automaticamente a partir dos pilares, paredes e núcleos.",
                                    "Poutres, panneaux et surfaces d'influence générés automatiquement à partir des poteaux, voiles et noyaux."),
                                  T("Pré-dimensionamento : esforços em vigas e pilares por métodos simplificados.", "Prédimensionnement : efforts des poutres et poteaux par méthodes simplifiées.")]
    for a in R["anomalies"]:
        hyp.append(f"{a['level'].upper()} — {a['message']}")
    pdf = rendu.build_pdf(T("Estudo prévio de estrutura — ", "Étude préalable de structure — ") + S.name, _sub(S), b + [("h2", T("Hipóteses / a validar", "Hypothèses / à valider")), ("hyp", hyp)],
                          footer=T("ConstruPilot — pré-dimensionamento determinístico ; a validar pelo projetista de estruturas.",
                                   "ConstruPilot — prédimensionnement déterministe ; à valider par le BET structure."))
    return _write(path, pdf)


# ------------------------------------------------------------------ medições
def medicoes_pdf(S, R, Q, path) -> Path:
    T = S.t
    L = Q["lines"]
    tot = Q["totais"]
    ex = next((x["q"] for x in L if x["art"] == "1.1"), 0.0)
    b = [("kpis", [{"label": T("Betão estrutural", "Béton de structure"), "value": f(tot["betao"], 0), "unit": "m³"},
                   {"label": T("Aço", "Acier") + f" {S.prof['steel']}", "value": f(tot["aco"] / 1000, 1), "unit": "t"},
                   {"label": T("Cofragem", "Coffrage"), "value": f(tot["cofragem"], 0), "unit": "m²"},
                   {"label": T("Escavação", "Terrassement"), "value": f(ex, 0), "unit": "m³"}])]
    b.append(("p", T("Mapa de medições da estrutura, elemento a elemento. Betão em volume teórico ; cofragem pela área de contacto ; aço por taxas médias de "
                     "pré-dimensionamento por tipo de elemento (kg/m³) — a substituir pelas listas de armaduras do projeto de execução.",
                     "Métré de la structure, élément par élément. Béton au volume théorique ; coffrage à la surface de contact ; acier par ratios moyens de "
                     "prédimensionnement par type d'élément (kg/m³) — à remplacer par les nomenclatures d'armatures d'exécution.")))
    A = Q["areas"]
    b.append(("table", [T("Quadro de áreas", "Tableau des surfaces"), T("Valor", "Valeur")], [
        [T("Área de implantação / piso", "Emprise / niveau"), f"{f(A['piso'], 1)} m²"], [T("Pisos acima do solo — área bruta", "Niveaux hors sol — surface brute"), f"{f(A['acima_solo'], 1)} m²"],
        [T("Cave", "Sous-sol"), f"{f(A['cave'], 1)} m²"], [T("Varandas (por piso)", "Balcons (par niveau)"), f"{f(A['varandas_piso'], 1)} m²"],
        [T("Total bruto", "Total brut"), f"{f(A['bruta'], 1)} m²"], [T("Área útil das frações", "Surface habitable des logements"), f"{f(A['util'], 1)} m²"]], [110 * W, 70 * W]))
    for cap, (pt, fr) in CAPS.items():
        rows = [[x["art"], x["el"], x["dims"], f(x["q"], 2), x["un"], f(x["vol"], 2) if x["vol"] else "—", f(x["cof"], 1) if x["cof"] else "—",
                 f(x["aco"], 0) if x["aco"] else "—"] for x in L if x["cap"] == cap]
        if not rows:
            continue
        tl = [x for x in L if x["cap"] == cap]
        rows.append(["", T("Subtotal", "Sous-total"), "", "", "", f(sum(x["vol"] for x in tl), 2), f(sum(x["cof"] for x in tl), 1), f(sum(x["aco"] for x in tl), 0)])
        b.append(("h2", f"{cap}. {S.t(pt, fr)}"))
        b.append(("table", ["Art.", T("Elemento", "Élément"), T("Dimensões (m)", "Dimensions (m)"), T("Quant.", "Quant."), T("Un.", "U."), T("Betão (m³)", "Béton (m³)"),
                            T("Cofragem (m²)", "Coffrage (m²)"), T("Aço (kg)", "Acier (kg)")], rows, [11 * W, 50 * W, 44 * W, 16 * W, 9 * W, 17 * W, 18 * W, 15 * W]))
    b.append(("h2", T("Taxas de armadura adotadas (kg/m³)", "Ratios d'armatures adoptés (kg/m³)")))
    b.append(("table", [T("Elemento", "Élément"), "kg/m³"], [[k.replace("_", " "), str(v)] for k, v in KG.items()], [120 * W, 60 * W]))
    pdf = rendu.build_pdf(T("Mapa de medições — Estrutura", "Métré — Structure"), _sub(S), b,
                          footer=T("ConstruPilot — medições do estudo prévio ; a confirmar com o projeto de execução.", "ConstruPilot — métré de l'étude préalable ; à confirmer en exécution."))
    return _write(path, pdf)


# ------------------------------------------------------------------ orçamento
def orcamento_pdf(S, R, Q, O, path) -> Path:
    T = S.t
    vat_lbl = T("IVA", "TVA")
    b = [("kpis", [{"label": T("Estrutura (cap. 1-6)", "Structure (lots 1-6)"), "value": f(O["tot_s"] / 1000, 0), "unit": "k€"},
                   {"label": T("Restantes trabalhos", "Autres lots"), "value": f(O["tot_p"] / 1000, 0), "unit": "k€"},
                   {"label": T(f"Total s/ {vat_lbl}", "Total HT"), "value": f(O["sub"] / 1000, 0), "unit": "k€"},
                   {"label": T("Custo por m² bruto", "Coût au m² brut"), "value": f(O["m2"], 0), "unit": "€/m²"}])]
    P = S.prices
    b.append(("p", T(f"Orçamento estimativo. Capítulos 1 a 6 (estrutura) : quantidades do mapa de medições × preços compostos (betão {f(P['concrete'], 0)} €/m³, "
                     f"aço {f(P['steel'])} €/kg, cofragem {f(P['formwork'], 0)} €/m²…). Capítulos 7 a 17 : estimativa PARAMÉTRICA por m² (± 20 %, sem projetos de "
                     f"especialidades nem mapa de acabamentos). {S.prof['price_ref']}.",
                     f"Estimation. Lots 1 à 6 (structure) : quantités du métré × prix composés (béton {f(P['concrete'], 0)} €/m³, acier {f(P['steel'])} €/kg, "
                     f"coffrage {f(P['formwork'], 0)} €/m²…). Lots 7 à 17 : estimation PARAMÉTRIQUE au m² (± 20 %, sans études techniques ni descriptif de finitions). "
                     f"{S.prof['price_ref']}.")))
    b.append(("h2", T("Parte A — Estrutura e fundações", "Partie A — Structure et fondations")))
    for cap, (pt, fr) in CAPS.items():
        rows = [[a["art"], a["desc"], a["un"], f(a["q"], 2), f(a["pu"], 2), f(a["total"], 0)] for a in O["arts"] if a["cap"] == cap]
        if not rows:
            continue
        rows.append(["", T(f"Total do capítulo {cap}", f"Total du lot {cap}"), "", "", "", f(sum(a["total"] for a in O["arts"] if a["cap"] == cap), 0)])
        b.append(("h2", f"{cap}. {S.t(pt, fr)}"))
        b.append(("table", ["Art.", T("Designação", "Désignation"), T("Un.", "U."), T("Quant.", "Quant."), "P.U. (€)", "Total (€)"], rows,
                  [12 * W, 98 * W, 10 * W, 20 * W, 18 * W, 22 * W]))
    b.append(("h2", T("Parte B — Restantes trabalhos (estimativa paramétrica)", "Partie B — Autres lots (estimation paramétrique)")))
    rows = [[p["cap"], p["desc"], p["un"], f(p["q"], 1), f(p["pu"], 2), f(p["total"], 0)] for p in O["par"]]
    rows.append(["", T("Estaleiro, segurança e saúde, ensaios (3 %)", "Installation de chantier, sécurité, essais (3 %)"), "vg", "1", f(O["estaleiro"], 0), f(O["estaleiro"], 0)])
    b.append(("table", [T("Cap.", "Lot"), T("Designação", "Désignation"), T("Un.", "U."), T("Quant.", "Quant."), "P.U. (€)", "Total (€)"], rows,
              [12 * W, 98 * W, 10 * W, 20 * W, 18 * W, 22 * W]))
    b.append(("h2", T("Resumo", "Récapitulatif")))
    res = [[f"{c}. {S.t(pt, fr)}", f(sum(a["total"] for a in O["arts"] if a["cap"] == c), 0)] for c, (pt, fr) in CAPS.items() if any(a["cap"] == c for a in O["arts"])]
    res += [[f"{p['cap']}. {p['desc']}", f(p["total"], 0)] for p in O["par"]]
    res += [[T("Estaleiro (3 %)", "Installation de chantier (3 %)"), f(O["estaleiro"], 0)], [T(f"TOTAL SEM {vat_lbl}", "TOTAL HT"), f(O["sub"], 0)],
            [S.prof["vat_note"], f(O["vat"], 0)], [T(f"TOTAL COM {vat_lbl}", "TOTAL TTC"), f(O["sub"] + O["vat"], 0)]]
    b.append(("table", [T("Capítulo", "Lot"), "Total (€)"], res, [140 * W, 40 * W]))
    b.append(("chart", G.barres_h([(T("Estrutura (1-6)", "Structure (1-6)"), O["tot_s"])] + [(p["desc"].split(",")[0].split(" (")[0][:38], p["total"]) for p in O["par"]]
                                  + [(T("Estaleiro (3 %)", "Chantier (3 %)"), O["estaleiro"])], T("Repartição do orçamento", "Répartition de l'estimation"), "€"),
              T(f"Custo por fração ≈ {f(O['per_unit'] / 1000, 0)} k€ sem IVA ; {f(O['m2'], 0)} €/m² de área bruta.",
                f"Coût par logement ≈ {f(O['per_unit'] / 1000, 0)} k€ HT ; {f(O['m2'], 0)} €/m² de surface brute.")))
    hyp = [T("Quantidades da estrutura do estudo prévio ; taxas de armadura médias por tipo de elemento.", "Quantités de structure de l'étude préalable ; ratios d'armatures moyens."),
           T("Restantes especialidades por rácios €/m² (acabamento médio-alto).", "Autres lots par ratios €/m² (finitions moyen-haut de gamme)."),
           T("Exclui : projeto, licenças e taxas, fiscalização, contenções especiais, rebaixamento freático, fundações indiretas, mobiliário, margem de promoção.",
             "Exclus : honoraires, taxes, contrôle, soutènements spéciaux, rabattement de nappe, fondations profondes, mobilier, marge de promotion."),
           S.prof["vat_note"]]
    pdf = rendu.build_pdf(T("Orçamento estimativo — ", "Estimation — ") + S.name, _sub(S), b + [("h2", T("Hipóteses / exclusões", "Hypothèses / exclusions")), ("hyp", hyp)],
                          footer=T("ConstruPilot — orçamento estimativo ; a confirmar por consulta ao mercado.", "ConstruPilot — estimation ; à confirmer par consultation des entreprises."))
    return _write(path, pdf)


# ------------------------------------------------------------------ quantidades (paredes, sapatas, lajes, vãos)
def quantidades_pdf(S, R, Q, path) -> Path:
    T = S.t
    qd = Q["quant"]
    ch = qd["clear_h"]
    par = qd["paredes"]
    fach = sum(p["L_fach"] * p["h"] - p["a_vaos"] - p["L_bet"] * p["h"] for p in par)
    div = sum(p["div"] * ch for p in par)
    sep = sum(p["sep"] * ch for p in par)
    enu = sum(p["enu"] * ch for p in par)
    mur = sum(w["L"] * S.H for w in R["bwalls"])
    imp = sum(w["L"] * w["ht"] for w in R["bwalls"])
    ns = len(ES.storeys(S))
    bet = sum(w["Lw"] * S.H * ns for w in S.walls) + sum(ES.core_section(c)["A"] / c["t"] * S.H * ns for c in S.cores)
    ml_sc = sum(w["L"] for w in R["bwalls"])
    lajes = [x for x in Q["lines"] if x["art"] in ("5.1", "5.2", "5.3", "5.6")]
    lj = sum(x["q"] for x in lajes)
    vaos = qd["vaos"]
    ot = S.opening_types
    n_tot = sum(v["n"] for v in vaos.values())
    a_v = sum(v["n"] * float(ot.get(k, {}).get("width") or 0) * float(ot.get(k, {}).get("height") or 0) for k, v in vaos.items())
    b = [("kpis", [{"label": T("Paredes de alvenaria", "Murs de maçonnerie"), "value": f(fach + div + sep + enu, 0), "unit": "m²"},
                   {"label": T("Muros de cave", "Voiles enterrés"), "value": f(mur, 0), "unit": "m²"},
                   {"label": T("Sapatas contínuas", "Semelles filantes"), "value": f(ml_sc, 1), "unit": "ml"},
                   {"label": T("Lajes", "Dalles"), "value": f(lj, 0), "unit": "m²"},
                   {"label": T("Janelas / vãos", "Fenêtres / baies"), "value": str(n_tot), "unit": "un"}])]
    b.append(("h2", T("1. Resumo", "1. Récapitulatif")))
    b.append(("table", [T("Grandeza", "Grandeur"), T("Quantidade", "Quantité"), T("Un.", "U.")], [
        [T("Fachadas — alvenaria exterior + isolamento (líquido de vãos e betão)", "Façades — maçonnerie + isolation (déduction baies et béton)"), f(fach, 1), "m²"],
        [T("Paredes divisórias interiores", "Cloisons intérieures"), f(div, 1), "m²"], [T("Paredes de separação entre frações", "Murs séparatifs entre logements"), f(sep, 1), "m²"],
        [T("Paredes da caixa de escada / hall comum", "Murs de cage d'escalier / hall"), f(enu, 1), "m²"], [T("Muros de cave (1 face)", "Voiles enterrés (1 face)"), f(mur, 1), "m²"],
        [T("Muros de cave — impermeabilização", "Voiles enterrés — étanchéité"), f(imp, 1), "m²"],
        [T("Paredes de betão — núcleos e paredes (1 face)", "Voiles béton — noyaux et voiles (1 face)"), f(bet, 1), "m²"],
        [T("Sapatas contínuas sob muros", "Semelles filantes sous voiles"), f(ml_sc, 2), "ml"],
        [T("Sapatas isoladas + ensoleiramentos", "Semelles isolées + radiers"), str(len(R["foots"]) + len(R["fnd"])), "un"],
        [T("Lajes, varandas e pavimento térreo", "Dalles, balcons et dallage"), f(lj, 1), "m²"],
        [T("Janelas e portas exteriores", "Fenêtres et portes extérieures"), str(n_tot), "un"], [T("Área total de vãos", "Surface totale des baies"), f(a_v, 1), "m²"]],
        [120 * W, 35 * W, 20 * W]))
    b.append(("h2", T("2. Paredes por piso", "2. Murs par niveau")))
    rows = [[p["piso"], f(p["L_fach"] * p["h"], 1), f(p["a_vaos"], 1), f(p["L_fach"] * p["h"] - p["a_vaos"] - p["L_bet"] * p["h"], 1), f(p["div"] * ch, 1),
             f(p["sep"] * ch, 1), f(p["enu"] * ch, 1)] for p in par]
    b.append(("table", [T("Piso", "Niveau"), T("Fachada bruta m²", "Façade brute m²"), T("Vãos m²", "Baies m²"), T("Alvenaria ext. m²", "Maçonnerie ext. m²"),
                        T("Divisórias m²", "Cloisons m²"), T("Separação m²", "Séparatifs m²"), T("Escada/hall m²", "Cage/hall m²")], rows,
              [20 * W, 27 * W, 20 * W, 27 * W, 26 * W, 26 * W, 28 * W]))
    if qd["estimado"]:
        b.append(("p", T("Paredes interiores ESTIMADAS por rácios (divisórias 0,34 ml/m² útil) : indicar os comprimentos medidos para um quadro exato.",
                         "Cloisons ESTIMÉES par ratios (0,34 ml/m² habitable) : renseigner les longueurs mesurées pour un quantitatif exact.")))
    b.append(("h2", T("3. Sapatas e muros", "3. Semelles et voiles enterrés")))
    rows = [[w["name"], f(w["L"]), f(S.H), f(w["L"] * S.H), f(w["L"] * w["ht"])] for w in R["bwalls"]]
    rows += [[f"S{x['id'].lstrip('P')}", f(x["y1"] - x["y0"]), f(x["x1"] - x["x0"]), f(x["h"]), f((x["x1"] - x["x0"]) * (x["y1"] - x["y0"]) * x["h"])] for x in R["foots"]]
    b.append(("table", [T("Elemento", "Élément"), T("Compr. ml", "Long. ml"), T("Alt./larg. m", "Haut./larg. m"), T("Área m² / alt.", "Surface m² / haut."),
                        T("Impermeab. m² / vol.", "Étanch. m² / vol.")], rows, [60 * W, 25 * W, 28 * W, 30 * W, 30 * W]))
    b.append(("h2", T("4. Lajes", "4. Dalles")))
    b.append(("table", [T("Laje", "Dalle"), T("Área m²", "Surface m²"), T("Volume m³", "Volume m³")], [[x["el"], f(x["q"], 1), f(x["vol"], 1)] for x in lajes],
              [110 * W, 35 * W, 35 * W]))
    b.append(("h2", T("5. Janelas e vãos", "5. Fenêtres et baies")))
    rows = []
    for k, v in vaos.items():
        d = ot.get(k, {})
        rows.append([k, d.get("label", ""), f"{f(d.get('width') or 0)} × {f(d.get('height') or 0)}", " · ".join(f"{S.lname(l_)}: {n}" for l_, n in sorted(v["by_level"].items())),
                     str(v["n"]), f(v["n"] * float(d.get("width") or 0) * float(d.get("height") or 0), 1)])
    b.append(("table", [T("Tipo", "Type"), T("Descrição", "Description"), "L × H (m)", T("Por piso", "Par niveau"), "Total", T("Área m²", "Surface m²")], rows,
              [12 * W, 52 * W, 22 * W, 60 * W, 12 * W, 18 * W]))
    fa = {}
    for v in vaos.values():
        for o, n in v["by_facade"].items():
            fa[o] = fa.get(o, 0) + n
    b.append(("table", [T("Fachada", "Façade"), "Total"], [[o, str(n)] for o, n in sorted(fa.items())], [60 * W, 30 * W]))
    pdf = rendu.build_pdf(T("Quadro de quantidades — paredes, sapatas, lajes, janelas", "Quantitatifs — murs, semelles, dalles, fenêtres"), _sub(S), b,
                          footer=T("ConstruPilot — quantidades do estudo prévio.", "ConstruPilot — quantitatifs de l'étude préalable."))
    return _write(path, pdf)
