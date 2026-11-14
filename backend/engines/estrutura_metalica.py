"""Armazém / pavilhão em ESTRUTURA METÁLICA — pré-dimensionamento CALCULADO a partir do contorno medido no DWG.

14/11 (Valpaços, Martinho): «é um armazém em aço». A implantação dá o contorno exato (1662,25 m²) mas não traz pórticos
nem perfis. Este módulo calcula, com hipóteses DECLARADAS em cada linha:

- Geometria: retângulo mínimo do contorno → pórticos no sentido curto (vão ≤ 30 m: pilares interiores quando
  necessário), afastados ≤ 6 m no sentido longo; cobertura a 2 águas por vão (6 %).
- Ações (NP EN 1990/1991): peso próprio (painel sandwich + madres + instalações + perfis), neve NP EN 1991-1-3
  (zona e altitude), sobrecarga de cobertura H 0,4 kN/m² (não simultânea com a neve).
- Madres: IPE em S275, viga simplesmente apoiada entre pórticos, flexão + flecha L/200 (NP EN 1993-1-1 §6.2, §7).
- Vigas de pórtico: IPE S275, momento de nó rígido wL²/12, esforço transverso, flecha L/200 (banzo comprimido
  travado pelas madres e escoras — hipótese).
- Pilares: HEA S275, flexão composta com encurvadura (§6.3.3 método 2, Anexo B), Lcr,y = 2H (pórtico de bases
  rotuladas, com deslocamentos laterais), Lcr,z = H/2 (madres de fachada a meia altura).
- Fundações: sapatas isoladas para a reação ELS com σadm = 200 kPa (hipótese, sem estudo geotécnico), armadura
  mínima EN 1992 9.2.1.1, chumbadouros, betão de limpeza, vigas de fundação perimetrais.
- Envolvente: painel sandwich na cobertura e fachadas (áreas medidas no contorno), parafusos autoperfurantes, remates.

O VENTO e o SISMO não estão verificados neste pré-dimensionamento (dizem-no as linhas): os perfis e os
contraventamentos têm de ser confirmados pelo projetista de estruturas.
"""
from __future__ import annotations

import math

from engines import structuro_ec3 as EC3
from engines import structuro_profiles as P

FY = 275.0
E_MPA = 210000.0
RHO_ACO = 7850.0
VAO_PORTICO_MAX = 30.0
AFAST_PORTICOS_MAX = 6.0
ESP_MADRES = 1.5
INCLINACAO = 0.06
PE_DIREITO = 7.0            # m ao beirado — hipótese corrente de armazém (a confirmar com os alçados)
SIGMA_ADM = 200.0           # kPa
G_COB = 0.35                # kN/m² painel sandwich 0,12 + madres 0,08 + instalações 0,15
Q_COB = 0.40                # kN/m² NP EN 1991-1-1 cat. H
CZ = {"Z1": 0.30, "Z2": 0.20, "Z3": 0.10}   # NP EN 1991-1-3 Anexo Nacional


def kg_m(perfil: str) -> float:
    return P.PROFILE_DATA[perfil]["A"] * 1e-4 * RHO_ACO


def superficie_m2_m(perfil: str) -> float:
    d = P.PROFILE_DATA[perfil]
    return (2 * d["h"] + 4 * d["b"] - 2 * d["tw"]) / 1000


def neve(zona: str, altitude: float, pais: str = "PT", code_postal: str | None = None) -> tuple[float, str]:
    """Carga de neve na cobertura (kN/m²) pelo motor de coberturas (Anexo Nacional do país) + a hipótese escrita."""
    try:
        from engines.calc_lots.couverture import neige
        p = {"pays": "fr" if pais == "FR" else "pt", "altitude_m": altitude, "pente_deg": math.degrees(math.atan(INCLINACAO))}
        if pais == "FR":
            p["code_postal"] = code_postal
        else:
            p["zona_neve"] = zona
        r = neige(p)
        return float(r["s_kn_m2"]), "; ".join(r.get("hypotheses") or [])
    except Exception:  # noqa: BLE001 — motor de coberturas indisponível: fórmula NP EN 1991-1-3 direta
        return 0.8 * CZ.get(zona, 0.30) * (1 + (altitude / 500) ** 2), ""


def _t(pt: str, fr: str, lang: str) -> str:
    return fr if lang == "fr" else pt


def _familia(f):
    return [k for k, v in P.PROFILE_DATA.items() if v["family"] == f]


def _viga(L, w_uls, w_sls, familia="IPE"):
    """Menor perfil que verifica flexão, esforço transverso e flecha (viga entre apoios rígidos/rotulados)."""
    for nome in _familia(familia):
        d = P.PROFILE_DATA[nome]
        w_u = w_uls + 1.35 * kg_m(nome) * 9.81 / 1000
        M, V = w_u * L ** 2 / 8, w_u * L / 2
        r = EC3.verify(M, V, wpl_y_cm3=d["Wpl"], wel_y_cm3=d["Wel"], av_cm2=d["Av"], fy_mpa=FY,
                       tw_mm=d["tw"], h_mm=d["h"], tf_mm=d["tf"])
        flecha = 5 * (w_sls + kg_m(nome) * 9.81 / 1000) * (L * 1000) ** 4 / (384 * E_MPA * d["Iy"] * 1e4)
        util = max(r["bending"]["utilisation"]["ratio"], r["shear"]["utilisation"]["ratio"], flecha / (L * 1000 / 200))
        if util <= 1.0:
            return {"perfil": nome, "M_Ed": round(M, 1), "V_Ed": round(V, 1), "flecha_mm": round(flecha, 1), "util": round(util, 2)}
    raise ValueError(f"nenhum {familia} verifica um vão de {L:.1f} m")


def _viga_portico(L, w_uls, w_sls):
    for nome in _familia("IPE"):
        d = P.PROFILE_DATA[nome]
        w_u = w_uls + 1.35 * kg_m(nome) * 9.81 / 1000
        M, V = w_u * L ** 2 / 12, w_u * L / 2
        Mc = d["Wpl"] * FY / 1000
        flecha = (w_sls + kg_m(nome) * 9.81 / 1000) * (L * 1000) ** 4 / (384 * E_MPA * d["Iy"] * 1e4)
        Vc = d["Av"] * 100 * FY / math.sqrt(3) / 1000
        util = max(M / Mc, V / Vc, flecha / (L * 1000 / 200))
        if util <= 1.0:
            return {"perfil": nome, "M_Ed": round(M, 1), "V_Ed": round(V, 1), "flecha_mm": round(flecha, 1), "util": round(util, 2)}
    raise ValueError(f"nenhum IPE verifica a viga de pórtico de {L:.1f} m — prever viga treliçada ou mais pilares / aucun IPE ne vérifie la traverse : prévoir une poutre treillis ou des poteaux intermédiaires")


def _pilar(N, M, H):
    for nome in _familia("HEA"):
        d = P.PROFILE_DATA[nome]
        r = EC3.verify_column(N, M, A_cm2=d["A"], iy_cm4=d["Iy"], iz_cm4=d["Iz"], it_cm4=d["It"], iw_cm6=d["Iw"],
                              wpl_y_cm3=d["Wpl"], wel_y_cm3=d["Wel"], b_fl_mm=d["b"], h_mm=d["h"], tf_mm=d["tf"],
                              fy_mpa=FY, lcr_y_m=2.0 * H, lcr_z_m=H / 2, lateral_restraint=False)
        u = max(r[k]["utilisation"]["ratio"] for k in ("buckling", "cross_section", "interaction") if r.get(k) and r[k]["utilisation"]["ratio"] is not None)
        if u <= 1.0:
            return {"perfil": nome, "N_Ed": round(N, 1), "M_Ed": round(M, 1), "util": round(u, 2)}
    raise ValueError("nenhum HEA verifica o pilar")


def _sapata(N_sls):
    B = max(1.0, math.ceil(math.sqrt(N_sls / SIGMA_ADM) * 10) / 10)
    h = max(0.50, math.ceil(B / 3 * 20) / 20)
    As = 0.0013 * 1000 * (h - 0.05) * 1000 / 1e6                     # m²/m  (EN 1992 9.2.1.1, b·d)
    kg = 2 * As * B * (B + 0.3) * RHO_ACO * 1.0                          # 2 direções, com dobras
    return {"B": B, "h": h, "kg": kg}


def calcular(pontos, *, nome: str, pe_direito: float = PE_DIREITO, zona_neve: str = "Z1", altitude: float = 400.0,
             lang: str = "pt", pais: str = "PT", code_postal: str | None = None) -> dict:
    from shapely.geometry import Polygon
    poly = Polygon(pontos).buffer(0)
    rect = poly.minimum_rotated_rectangle
    xs = list(rect.exterior.coords)[:4]
    l1 = math.dist(xs[0], xs[1])
    l2 = math.dist(xs[1], xs[2])
    comprimento, largura = max(l1, l2), min(l1, l2)
    n_vaos = max(1, math.ceil(largura / VAO_PORTICO_MAX - 1e-9))
    vao = largura / n_vaos
    n_tramos = max(1, math.ceil(comprimento / AFAST_PORTICOS_MAX - 1e-9))
    s = comprimento / n_tramos
    n_porticos = n_tramos + 1
    H = pe_direito
    sn, hip_neve = neve(zona_neve, altitude, pais, code_postal)
    var = max(sn, Q_COB)
    w_uls_m2 = 1.35 * G_COB + 1.5 * var
    w_sls_m2 = G_COB + var

    madre = _viga(s, w_uls_m2 * ESP_MADRES, w_sls_m2 * ESP_MADRES)
    w_madres = kg_m(madre["perfil"]) * 9.81 / 1000 / ESP_MADRES       # kN/m² do peso das madres reais
    viga = _viga_portico(vao, (w_uls_m2 + 1.35 * w_madres) * s, (w_sls_m2 + w_madres) * s)
    wv = kg_m(viga["perfil"]) * 9.81 / 1000
    w_u = (w_uls_m2 + 1.35 * w_madres) * s + 1.35 * wv
    w_s = (w_sls_m2 + w_madres) * s + wv
    pil_ext = _pilar(w_u * vao / 2, w_u * vao ** 2 / 12, H)
    pil_int = _pilar(w_u * vao * 1.25, w_u * vao ** 2 / 12 * 0.25, H) if n_vaos > 1 else None

    L_viga = vao / math.cos(math.atan(INCLINACAO)) * n_vaos
    n_pil_ext = 2 * n_porticos
    n_pil_int = (n_vaos - 1) * n_porticos
    linhas_madres = n_vaos * 2 * (math.ceil(vao / 2 / ESP_MADRES) + 1)
    perimetro = poly.exterior.length
    n_madres_fach = math.ceil(H / 1.8)
    area_cob = poly.area / math.cos(math.atan(INCLINACAO))
    area_fach = perimetro * (H + vao / 2 * INCLINACAO / 2)

    perf = []
    def add_perfil(des, p, comp, n_lig=None):
        perf.append((des, p, comp))
    add_perfil("vigas de pórtico", viga["perfil"], L_viga * n_porticos)
    add_perfil("pilares de fachada lateral (pórticos)", pil_ext["perfil"], n_pil_ext * H)
    if pil_int:
        add_perfil("pilares interiores", pil_int["perfil"], n_pil_int * H)
    add_perfil("madres de cobertura", madre["perfil"], linhas_madres * comprimento)
    add_perfil("madres de fachada", madre["perfil"], n_madres_fach * perimetro)

    norma_neve = f"NF EN 1991-1-3/NA ({hip_neve})" if pais == "FR" else f"NP EN 1991-1-3 zona {zona_neve}"
    hip = _t(f"Pré-dimensionamento CALCULADO (NP EN 1990/1991/1993-1-1) sobre o contorno medido no DWG. HIPÓTESES a confirmar: "
             f"armazém de 1 piso em estrutura metálica S275 (dado do dono de obra), pé-direito {H:g} m ao beirado, {n_porticos} pórticos "
             f"a {s:.2f} m, {n_vaos} vão(s) de {vao:.2f} m, cobertura a 2 águas {INCLINACAO*100:g} %, madres a {ESP_MADRES} m; ações: G "
             f"{G_COB} kN/m² + peso dos perfis, neve {sn:.2f} kN/m² ({norma_neve}, altitude {altitude:g} m), "
             f"sobrecarga H {Q_COB} kN/m²; σadm do terreno {SIGMA_ADM:g} kPa (sem estudo geotécnico). VENTO e SISMO não verificados "
             f"neste pré-dimensionamento — a validar pelo projetista de estruturas.",
             f"Prédimensionnement CALCULÉ (NF EN 1990/1991/1993-1-1) sur le contour mesuré sur le DWG. HYPOTHÈSES à confirmer : "
             f"bâtiment de stockage de plain-pied en charpente métallique S275 (donnée du maître d'ouvrage), hauteur {H:g} m sous sablière, "
             f"{n_porticos} portiques à {s:.2f} m, {n_vaos} travée(s) de {vao:.2f} m, toiture 2 pans {INCLINACAO*100:g} %, pannes à "
             f"{ESP_MADRES} m ; actions : G {G_COB} kN/m² + poids des profilés, neige {sn:.2f} kN/m² ({norma_neve}, altitude {altitude:g} m), "
             f"charge d'entretien H {Q_COB} kN/m² ; contrainte admissible du sol {SIGMA_ADM:g} kPa (sans étude géotechnique G2). VENT et "
             f"SÉISME non vérifiés dans ce prédimensionnement — à valider par le bureau d'études structure.", lang)
    L = []
    cap_e, cap_f, cap_v = (_t("Estrutura metálica", "Charpente métallique", lang), _t("Fundações", "Fondations", lang),
                           _t("Envolvente (cobertura e fachadas)", "Enveloppe (couverture et bardage)", lang))
    ac = "B500B" if pais == "FR" else "A500 NR"

    def item(cap, des, un, q, extra=""):
        if q and q > 0:
            L.append({"kind": "item", "category": cap, "designation": des, "unit": un, "qty": round(q, 2),
                      "description": (extra + " " if extra else "") + hip, "classe": "estrutura_metalica"})
    total_kg = 0.0
    sup = 0.0
    for des, p, comp in perf:
        kg = comp * kg_m(p)
        total_kg += kg
        sup += comp * superficie_m2_m(p)
        ver = {"vigas de pórtico": viga, "pilares de fachada lateral (pórticos)": pil_ext, "pilares interiores": pil_int}.get(des) or madre
        des_l = _t(des, {"vigas de pórtico": "traverses de portique", "pilares de fachada lateral (pórticos)": "poteaux de long-pan (portiques)",
                         "pilares interiores": "poteaux intermédiaires", "madres de cobertura": "pannes de toiture",
                         "madres de fachada": "lisses de bardage"}[des], lang)
        item(cap_e, _t(f"Aço S275 em perfis {p} — {des_l}", f"Acier S275 en profilés {p} — {des_l}", lang), "kg", kg,
             _t(f"{comp:.1f} m de {p} × {kg_m(p):.1f} kg/m. Verificação EC3: taxa de utilização {ver['util']:.2f}.",
                f"{comp:.1f} m de {p} × {kg_m(p):.1f} kg/m. Vérification EC3 : taux de travail {ver['util']:.2f}.", lang))
    item(cap_e, _t("Aço S275 em chapas de ligação, placas de base e reforços (8 % do peso dos perfis)", "Acier S275 en platines, goussets et raidisseurs (8 % du poids des profilés)", lang), "kg", total_kg * 0.08)
    diag = 2 * n_vaos * 2 * math.hypot(s, vao / 2)          # 2 tramos de extremidade, cruz por água
    item(cap_e, _t("Aço S275 em varão Ø20 — contraventamentos de cobertura (2 tramos de extremidade)", "Acier S275 rond Ø20 — contreventements de toiture (2 travées d'extrémité)", lang), "kg", diag * 2.47)
    item(cap_e, _t("Aço S275 em varão Ø20 — contraventamentos de fachada (2 tramos por fachada lateral)", "Acier S275 rond Ø20 — palées de stabilité (2 travées par long-pan)", lang), "kg", 2 * 2 * 2 * math.hypot(s, H) * 2.47)
    n_nos = n_porticos * (2 + 2 * n_vaos + (n_vaos - 1))
    item(cap_e, _t("Parafusos M20 classe 8.8 com porca e anilha — ligações dos pórticos (8 por nó)", "Boulons M20 classe 8.8 avec écrou et rondelle — assemblages des portiques (8 par nœud)", lang), "un", n_nos * 8)
    n_pil = n_pil_ext + n_pil_int
    item(cap_e, _t("Chumbadouros M24 com porca, anilha e contraporca (4 por pilar)", "Tiges d'ancrage M24 avec écrou, rondelle et contre-écrou (4 par poteau)", lang), "un", n_pil * 4)
    n_lig_madres = (linhas_madres + n_madres_fach * 2) * n_porticos
    item(cap_e, _t("Parafusos M12 classe 8.8 com porca e anilha — ligação madres/pórticos (2 por apoio)", "Boulons M12 classe 8.8 avec écrou et rondelle — fixation pannes/portiques (2 par appui)", lang), "un", n_lig_madres * 2)
    item(cap_e, _t("Proteção anticorrosiva dos perfis — primário epóxi + acabamento, 2 demãos", "Protection anticorrosion des profilés — primaire époxy + finition, 2 couches", lang), "m2", sup * 1.08)
    # fundações
    N_ext = w_s * vao / 2
    N_int = w_s * vao * 1.25
    se, si = _sapata(N_ext), _sapata(N_int)
    v_sap = n_pil_ext * se["B"] ** 2 * se["h"] + n_pil_int * si["B"] ** 2 * si["h"]
    item(cap_f, _t("Escavação para sapatas", "Fouilles des semelles", lang), "m3", n_pil_ext * (se["B"] + 0.4) ** 2 * (se["h"] + 0.1) + n_pil_int * (si["B"] + 0.4) ** 2 * (si["h"] + 0.1))
    item(cap_f, _t("Betão de limpeza e=10 cm", "Béton de propreté e=10 cm", lang), "m3", n_pil_ext * (se["B"] + 0.1) ** 2 * 0.1 + n_pil_int * (si["B"] + 0.1) ** 2 * 0.1)
    dims = f"{se['B']:.2f}×{se['B']:.2f}×{se['h']:.2f} m; int. {si['B']:.2f}×{si['B']:.2f}×{si['h']:.2f} m"
    item(cap_f, _t(f"Betão C25/30 em sapatas (ext. {dims})", f"Béton C25/30 des semelles isolées (rive {dims})", lang), "m3", v_sap,
         _t(f"Reações ELS: pilar exterior {N_ext:.0f} kN, interior {N_int:.0f} kN.", f"Réactions ELS : poteau de rive {N_ext:.0f} kN, intermédiaire {N_int:.0f} kN.", lang))
    item(cap_f, _t(f"Aço {ac} em varão — sapatas (armadura mínima EN 1992 9.2.1.1)", f"Acier HA {ac} — semelles (ferraillage minimal EN 1992 9.2.1.1)", lang), "kg", n_pil_ext * se["kg"] + n_pil_int * si["kg"])
    item(cap_f, _t("Betão C25/30 em vigas de fundação perimetrais 0,30 × 0,50 m", "Béton C25/30 des longrines périphériques 0,30 × 0,50 m", lang), "m3", perimetro * 0.30 * 0.50)
    item(cap_f, _t(f"Aço {ac} em varão — vigas de fundação (4Ø16 + estribos Ø8//0,20)", f"Acier HA {ac} — longrines (4HA16 + cadres HA8 e=0,20)", lang), "kg",
         perimetro * (4 * 1.58 + 2 * (0.30 + 0.50) * 0.395 / 0.20) * 1.1)
    item(cap_f, _t("Laje térrea R/C e=0,15 (malha eletrossoldada)", "Dallage sur terre-plein e=0,15 (treillis soudé)", lang), "m2", poly.area)
    # envolvente
    item(cap_v, _t("Painel sandwich de cobertura (área medida no contorno, inclinação incluída)",
                   "Panneau sandwich de couverture (surface mesurée sur le contour, pente incluse)", lang), "m2", area_cob)
    item(cap_v, _t("Painel sandwich de fachada (perímetro medido × altura; vãos a descontar)",
                   "Panneau sandwich de bardage (périmètre mesuré × hauteur ; baies à déduire)", lang), "m2", area_fach)
    item(cap_v, _t("Remate de cumeeira em chapa lacada", "Faîtière en tôle laquée", lang), "m", comprimento * n_vaos)
    item(cap_v, _t("Caleira e remates de beirado/platibanda em chapa lacada", "Chéneau et bavettes d'égout/acrotère en tôle laquée", lang), "m", perimetro)
    return {"linhas": L, "hipoteses": hip, "geometria": {"comprimento": round(comprimento, 2), "largura": round(largura, 2),
            "porticos": n_porticos, "afastamento": round(s, 2), "vaos": n_vaos, "vao": round(vao, 2), "pe_direito": H},
            "perfis": {"madre": madre, "viga": viga, "pilar_ext": pil_ext, "pilar_int": pil_int},
            "aco_perfis_kg": round(total_kg), "aco_kg_m2": round(total_kg * 1.08 / poly.area, 1)}
