"""Solar térmico com coletores envidraçados (AQS, sistema combinado) — pré-dimensionamento e verificação dos materiais (Portugal).

1. Pré-dimensionamento INDICATIVO: necessidades de AQS pela convenção REH (ocupantes = tipologia + 1, 40 L/dia por ocupante em
   moradia e 30 L/dia em apartamento, ΔT 35 K), produção anual dos coletores E = Ac · H · η_sist (irradiação no plano dos coletores
   por defeito 1 700 kWh/(m².ano), continente) e fração solar. O cálculo regulamentar (SCE) faz-se com o SolTerm (LNEG) ou
   equivalente: este motor não o substitui.
2. Verificação da escolha dos materiais a partir dos dados do fabricante (coletor, permutador, depósito, regulação): normas europeias
   (EN ISO 9806 / EN 12975, EN 12976, EN 12977, EN 806, EN 60529, EN 1434) e, na falta de norma portuguesa equivalente, os
   critérios numéricos da NF DTU 65.12 P1-2 usados por analogia: coeficiente mínimo do permutador (perda de rendimento Δη < 10 %)
   e coeficiente máximo de perdas do depósito ((UA) ≤ 0,16·√Vs).
Um dado em falta dá um controlo « a verificar », nunca um valor suposto.
"""
from __future__ import annotations

import math

from . import reh

ANALOGIA = "critério NF DTU 65.12 P1-2 (por analogia)"
SOURCES = {
    "coletor": "EN ISO 9806 / EN 12975 — coletor certificado (Solar Keymark), manual em português (T e P máx., caudal, inclinações, cargas, fluido)",
    "absorvedor": "Boa prática — ampliação: absorvedores da mesma natureza que os existentes; mesmo circuito: coletores idênticos",
    "parafusos": f"{ANALOGIA} §3.2 — parafusos dos coletores e suportes em aço inoxidável até Ø 8 mm inclusive",
    "materiais": "EN 14868 — compatibilidade materiais / fluido (circuito arejado ou não)",
    "tubagens": "EN 1057 / EN 12449 (cobre) ou aço inox ondulado 304L / 316L — tubagens do circuito primário",
    "resistencia": "T e P máx. de serviço das tubagens superiores à estagnação e à pressão máx. do coletor (cheio permanentemente) "
                   "ou aos máximos da instalação (autodrenante)",
    "galva": "Aço galvanizado interdito acima de 60 °C (descincagem)",
    "acessorios": "Acessórios e juntas: mesmas exigências T/P, compatíveis com o fluido, livre dilatação dos absorvedores",
    "isolamento": "Isolamento térmico: EPDM se T ≤ 150 °C, lã mineral acima; no exterior: resistência UV, intempéries e animais",
    "circulador": "EN 809 / EN 1151-1 — circulador compatível com o fluido e as T/P do circuito",
    "vaso": "EN 13831 — vaso de expansão; membrana geralmente limitada a 70 °C (vaso de proteção / tomada afastada)",
    "valvula": "EN 1489 / EN 1490 — válvula de segurança; grupo de segurança EN 1487 em circuito direto",
    "purgador": "Purgadores dos coletores: −10 °C a pelo menos 150 °C (110 °C se houver válvula de isolamento fechada após purga)",
    "ip": "EN 60529 — controlador em local seco IP 20, sondas de água IP 33, detetor de radiação IP 65",
    "sondas": "Sonda do coletor resistente à estagnação (deriva ≤ 1 K); sonda do depósito 0 a 100 °C",
    "detetor": "Detetor de radiação 0,4 a 0,8 µm, temporização ≥ 30 s",
    "cabos": "Cabos das sondas resistentes às temperaturas máximas da instalação",
    "contador": "EN 1434-1 — contador de energia classe 1",
    "manometro": "Manómetro graduado em bar até pelo menos a pressão máxima de serviço",
    "fluido": "Anticongelante ≤ 50 %; permuta simples com AQS: fluido atóxico (propilenoglicol de qualidade alimentar)",
    "permutador": f"{ANALOGIA} §7 — perdas de pressão < 2 m c.a., perda de rendimento Δη = η0·Ac·a1/(UA)hx < 10 %",
    "permutador_aqs": "Coletivo centralizado com permuta simples AQS: inox (≥ 12 % Cr, ≤ 0,08 % C), inox ao titânio ou cobre ≥ 0,8 mm",
    "deposito": f"{ANALOGIA} §8 — (UA) ≤ 0,16·√Vs (W/K, Vs em litros); AQS por aquecimento indireto: EN 12897",
    "cargas": f"{ANALOGIA} anexo A.2 — cargas admissíveis do coletor = ensaio / 1,5 em pressão, / 2 em sucção",
    "dimensionamento": "REH (Portaria 138-I/2021) — necessidades de AQS; cálculo SCE com SolTerm (LNEG)",
}

TUBAGENS_OK = {"cobre", "inox_304l", "inox_316l"}
NOMES = {"cobre": "cobre", "inox_304l": "inox ondulado 304L", "inox_316l": "inox ondulado 316L", "aco_galvanizado": "aço galvanizado",
         "aco_preto": "aço preto", "pex": "PE-X", "pb": "PB", "multicamada": "multicamada"}
GALVA_T_MAX = 60
EPDM_T_MAX = 150
MEMBRANA_T_MAX = 70
PURGADOR_T_MIN, PURGADOR_T_ISOLADO = 150, 110
IP_MIN = {"controlador": 20, "sondas": 33, "detetor": 65}
DETETOR_TEMPO_S = 30
SONDA_DEPOSITO_T_MAX = 100
ANTICONGELANTE_MAX_PCT = 50
PERMUTADOR_DP_MAX = 2.0
PERMUTADOR_DETA_MAX = 0.10
UA_DEPOSITO_K = 0.16
CU_EP_MIN_MM = 0.8
PARAFUSOS_D_MAX_MM = 8
COEF_PRESSAO, COEF_SUCCAO = 1.5, 2.0
H_DEFAULT = {"continente": 1700.0, "acores": 1350.0, "madeira": 1550.0}     # kWh/(m².ano) no plano dos coletores (ordem de grandeza)
ETA_SIST = {"termossifao": 0.40, "forcado": 0.42, "combinado": 0.35}
L_POR_M2 = (50, 80)                                                          # volume de acumulação por m² de coletor (boa prática)


def ua_permutador_min(eta0: float, ac_m2: float, a1: float) -> float:
    return eta0 * ac_m2 * a1 / PERMUTADOR_DETA_MAX


def perda_rendimento(eta0: float, ac_m2: float, a1: float, ua_hx: float) -> float:
    return eta0 * ac_m2 * a1 / ua_hx


def ua_deposito_max(volume_l: float) -> float:
    return UA_DEPOSITO_K * math.sqrt(volume_l)


def _c(ref, exigencia, valor, ok, note=None):
    return {"ref": SOURCES[ref], "exigencia": exigencia, "valor": valor, "ok": ok, "note": note}


def _falta(ref, exigencia, o_que):
    return _c(ref, exigencia, f"{o_que} a fornecer (ficha do fabricante)", None)


def dimensionamento(p: dict, ac: float | None, vol: float | None, hyp: list) -> dict:
    tip = p.get("tipologia")
    n_oc = int(p.get("ocupantes") or reh.OCUPANTES.get(int(tip), int(tip) + 1)) if (p.get("ocupantes") or tip is not None) else None
    if n_oc is None:
        return {}
    tipo = p.get("tipo_habitacao") or "moradia"
    litros = float(p.get("consumo_l_dia_ocupante") or (40 if tipo == "moradia" else 30))
    Qa = litros * n_oc * 4187 * 35 * 365 / 3.6e6
    reg = p.get("regiao") or "continente"
    H = float(p.get("irradiacao_kwh_m2") or H_DEFAULT.get(reg, 1700.0))
    sist = p.get("sistema") or ("combinado" if p.get("utilizacao") == "combinado" else "termossifao")
    eta = ETA_SIST.get(sist, 0.40)
    if not p.get("irradiacao_kwh_m2"):
        hyp.append(f"irradiação no plano dos coletores {H:.0f} kWh/(m².ano) ({reg}, orientação a sul, inclinação ≈ latitude): substituir pelo valor do SolTerm")
    hyp.append(f"rendimento médio anual do sistema {eta:.2f} ({sist}), perdas do depósito e da tubagem incluídas (indicativo)")
    ac_sug = Qa * 0.70 / (H * eta)                                            # área para ≈ 70 % de fração solar
    out = {"ocupantes": n_oc, "consumo_l_dia": litros * n_oc, "Qa_kwh": Qa, "irradiacao": H, "eta_sist": eta, "sistema": sist,
           "area_sugerida_m2": ac_sug, "volume_sugerido_l": (L_POR_M2[0] * ac_sug, L_POR_M2[1] * ac_sug)}
    if ac:
        E = ac * H * eta
        out.update(producao_kwh=E, fracao_solar=min(E / Qa, 1.0) if Qa else 0.0, excedente=E > Qa)
    if ac and vol:
        out["litros_por_m2"] = vol / ac
    return out


def calcular(params: dict) -> dict:
    """params : {tipologia | ocupantes, tipo_habitacao, consumo_l_dia_ocupante, regiao, irradiacao_kwh_m2, sistema, utilizacao ('aqs' | 'combinado'),
    tipo_instalacao ('cheio' | 'autodrenante'), circuito ('indireto' | 'direto'), coletivo,
    coletor: {numero, area_m2 (Ac unitária), eta0, a1, t_estagnacao_c, p_max_bar, absorvedor, identicos, certificado},
    absorvedor_existente, t_max_regulacao_c, p_max_instalacao_bar, tubagem: {material, t_max_c, p_max_bar},
    isolamento: {tipo ('epdm' | 'la_mineral' | outro), exterior, uv}, fluido: {anticongelante_pct, atoxico},
    permutador: {ua_w_k, dp_mca, material, ep_cobre_mm, dupla_permuta}, deposito: {volume_l, ua_w_k, en12897},
    regulacao: {ip_controlador, ip_sondas, ip_detetor, tempo_detetor_s, t_max_sonda_coletor_c, t_max_sonda_deposito_c},
    tarado_valvula_bar, manometro_max_bar, contador_classe, vaso_t_max_c, purgador_t_max_c, purgador_isolado,
    parafusos: {diametro_mm, inox}, cargas: {ensaio_pressao_pa, ensaio_succao_pa, pressao_pa, succao_pa}}"""
    p = dict(params or {})
    cheio = (p.get("tipo_instalacao") or "cheio") != "autodrenante"
    direto = p.get("circuito") == "direto"
    uso = p.get("utilizacao") or "aqs"
    col = dict(p.get("coletor") or {})
    n = int(col.get("numero") or 1)
    ac_u = col.get("area_m2")
    ac = float(ac_u) * n if ac_u else None
    t_est, p_col = col.get("t_estagnacao_c"), col.get("p_max_bar")
    t_max = t_est if cheio else p.get("t_max_regulacao_c")
    p_max = p_col if cheio else p.get("p_max_instalacao_bar")
    tarado = p.get("tarado_valvula_bar")
    ctl: list[dict] = []
    hyp: list[str] = []
    if p.get("tipo_instalacao") is None:
        hyp.append("instalação com coletores permanentemente cheios (caso mais exigente) na falta de indicação")
    dep = dict(p.get("deposito") or {})
    dim = dimensionamento(p, ac, float(dep["volume_l"]) if dep.get("volume_l") else None, hyp)
    if dim.get("litros_por_m2") is not None:
        lm = dim["litros_por_m2"]
        ctl.append(_c("dimensionamento", f"acumulação {L_POR_M2[0]} a {L_POR_M2[1]} L por m² de coletor (boa prática)", f"{lm:.0f} L/m²",
                      L_POR_M2[0] <= lm <= L_POR_M2[1] + 20, "risco de sobreaquecimento / estagnação frequente" if lm < L_POR_M2[0] else None))
    if dim.get("fracao_solar") is not None:
        fs = dim["fracao_solar"]
        ctl.append(_c("dimensionamento", "fração solar indicativa 50 a 85 % (sem excedente de verão)", f"{fs * 100:.0f} %",
                      0.5 <= fs <= 0.85 if not dim["excedente"] else False,
                      "produção superior às necessidades: estagnação no verão, reduzir a área" if dim["excedente"] else
                      ("área reduzida face às necessidades" if fs < 0.5 else None)))

    ctl.append(_c("coletor", "EN ISO 9806 / EN 12975, Solar Keymark", "declarado conforme" if col.get("certificado") else "a justificar",
                  True if col.get("certificado") else None))
    if col.get("identicos") is False:
        ctl.append(_c("absorvedor", "coletores idênticos no mesmo circuito", "coletores diferentes", False))
    if p.get("absorvedor_existente"):
        ok = col.get("absorvedor") == p["absorvedor_existente"] if col.get("absorvedor") else None
        ctl.append(_c("absorvedor", f"absorvedor da mesma natureza que o existente ({p['absorvedor_existente']})",
                      col.get("absorvedor") or "absorvedor dos novos coletores a indicar", ok))
    pf = dict(p.get("parafusos") or {})
    if pf.get("diametro_mm") is not None:
        need = float(pf["diametro_mm"]) <= PARAFUSOS_D_MAX_MM
        ctl.append(_c("parafusos", f"inox até Ø {PARAFUSOS_D_MAX_MM} mm inclusive", f"Ø {float(pf['diametro_mm']):g} mm, " + ("inox" if pf.get("inox") else "não inox"),
                      bool(pf.get("inox")) if need else True))
    else:
        ctl.append(_falta("parafusos", f"inox até Ø {PARAFUSOS_D_MAX_MM} mm inclusive", "diâmetro e material dos parafusos"))

    tb = dict(p.get("tubagem") or {})
    mat = tb.get("material")
    if mat:
        note = SOURCES["galva"] if mat == "aco_galvanizado" and (t_max is None or float(t_max) > GALVA_T_MAX) else None
        ctl.append(_c("tubagens", "cobre EN 1057 / EN 12449 ou inox ondulado 304L / 316L", NOMES.get(mat, mat), mat in TUBAGENS_OK, note))
    else:
        ctl.append(_falta("tubagens", "cobre EN 1057 / EN 12449 ou inox ondulado 304L / 316L", "material das tubagens"))
    lab = "estagnação do coletor" if cheio else "máx. da instalação"
    if t_max is not None and tb.get("t_max_c") is not None:
        ctl.append(_c("resistencia", f"T máx. de serviço > {float(t_max):g} °C ({lab})", f"{float(tb['t_max_c']):g} °C", float(tb["t_max_c"]) > float(t_max)))
    else:
        ctl.append(_falta("resistencia", f"T máx. de serviço das tubagens, acessórios e juntas > T {lab}",
                          "resistência térmica das tubagens" if t_max is not None else
                          ("temperatura de estagnação do coletor e resistência das tubagens" if cheio else "regulação máx. do controlador e resistência das tubagens")))
    if p_max is not None and tb.get("p_max_bar") is not None:
        ctl.append(_c("resistencia", f"P máx. de serviço > {float(p_max):g} bar", f"{float(tb['p_max_bar']):g} bar", float(tb["p_max_bar"]) > float(p_max)))
    ctl.append(_c("acessorios", "acessórios e juntas às mesmas T/P, ligações entre coletores que deixam dilatar os absorvedores", "a verificar", None))

    iso = dict(p.get("isolamento") or {})
    if iso.get("tipo"):
        if not cheio:
            ok, val = None, f"{iso['tipo']} (autodrenante: resistência à T máx. do troço)"
        elif t_max is None:
            ok, val = None, f"{iso['tipo']} — temperatura de estagnação a fornecer"
        else:
            need = "epdm" if float(t_max) <= EPDM_T_MAX else "la_mineral"
            ok, val = iso["tipo"] == need, f"{iso['tipo']} para {float(t_max):g} °C"
        ctl.append(_c("isolamento", f"EPDM se T ≤ {EPDM_T_MAX} °C, lã mineral acima", val, ok))
    else:
        ctl.append(_falta("isolamento", f"EPDM se T ≤ {EPDM_T_MAX} °C, lã mineral acima", "natureza do isolamento"))
    if iso.get("exterior"):
        ctl.append(_c("isolamento", "isolamento exterior resistente aos UV, às intempéries e aos animais",
                      "proteção UV declarada" if iso.get("uv") else "proteção a justificar", True if iso.get("uv") else None))

    ctl.append(_c("circulador", "EN 809 / EN 1151-1, gama do circuito primário (−10 a +120 °C em geral)", "a verificar", None))
    vt = p.get("vaso_t_max_c")
    vt_val = float(vt) if vt is not None else MEMBRANA_T_MAX
    if vt is None:
        hyp.append(f"membrana do vaso de expansão limitada a {MEMBRANA_T_MAX} °C (valor corrente): indicar o dado do fabricante")
    ctl.append(_c("vaso", f"membrana ≤ {vt_val:g} °C protegida da estagnação", "prever vaso de proteção / tomada afastada dos coletores", None))
    ctl.append(_c("valvula", "válvula de segurança" + (" e grupo de segurança EN 1487" if direto else ""),
                  f"tarada a {float(tarado):g} bar" if tarado is not None else "tarado a fornecer", None))
    if p.get("purgador_t_max_c") is not None:
        lim = PURGADOR_T_ISOLADO if p.get("purgador_isolado") else PURGADOR_T_MIN
        ctl.append(_c("purgador", f"purgador dos coletores ≥ {lim} °C", f"{float(p['purgador_t_max_c']):g} °C", float(p["purgador_t_max_c"]) >= lim))

    rg = dict(p.get("regulacao") or {})
    for k, lab_ in (("controlador", "controlador (local seco)"), ("sondas", "sondas de temperatura de água"), ("detetor", "detetor de radiação")):
        val = rg.get(f"ip_{k}")
        if val is not None:
            ctl.append(_c("ip", f"{lab_} ≥ IP {IP_MIN[k]}", f"IP {int(val):02d}", int(val) >= IP_MIN[k]))
    if not any(rg.get(f"ip_{k}") is not None for k in IP_MIN):
        ctl.append(_falta("ip", "IP 20 controlador, IP 33 sondas, IP 65 detetor", "índices IP"))
    if rg.get("tempo_detetor_s") is not None:
        ctl.append(_c("detetor", f"temporização ≥ {DETETOR_TEMPO_S} s", f"{float(rg['tempo_detetor_s']):g} s", float(rg["tempo_detetor_s"]) >= DETETOR_TEMPO_S))
    if rg.get("t_max_sonda_coletor_c") is not None:
        ok = float(rg["t_max_sonda_coletor_c"]) >= float(t_est) if t_est is not None else None
        ctl.append(_c("sondas", "sonda do coletor resistente à estagnação" + (f" ({float(t_est):g} °C)" if t_est is not None else ""),
                      f"{float(rg['t_max_sonda_coletor_c']):g} °C", ok))
    if rg.get("t_max_sonda_deposito_c") is not None:
        ctl.append(_c("sondas", f"sonda do depósito de 0 a {SONDA_DEPOSITO_T_MAX} °C", f"{float(rg['t_max_sonda_deposito_c']):g} °C",
                      float(rg["t_max_sonda_deposito_c"]) >= SONDA_DEPOSITO_T_MAX))
    ctl.append(_c("cabos", "cabos das sondas resistentes às T máx." + (f" ({float(t_max):g} °C)" if t_max is not None else ""),
                  "a verificar (silicone 180 °C correntemente)", None))
    pm = p_max if p_max is not None else tarado
    if p.get("manometro_max_bar") is not None:
        ctl.append(_c("manometro", "graduação ≥ pressão máx. de serviço" + (f" ({float(pm):g} bar)" if pm is not None else ""),
                      f"{float(p['manometro_max_bar']):g} bar", float(p["manometro_max_bar"]) >= float(pm) if pm is not None else None))
    if p.get("contador_classe") is not None:
        ctl.append(_c("contador", "classe 1", f"classe {int(p['contador_classe'])}", int(p["contador_classe"]) <= 1))

    fl = dict(p.get("fluido") or {})
    if fl.get("anticongelante_pct") is not None:
        ctl.append(_c("fluido", f"anticongelante ≤ {ANTICONGELANTE_MAX_PCT} %", f"{float(fl['anticongelante_pct']):g} %",
                      float(fl["anticongelante_pct"]) <= ANTICONGELANTE_MAX_PCT))
    pm_ = dict(p.get("permutador") or {})
    if not direto and uso in ("aqs", "combinado") and not pm_.get("dupla_permuta"):
        ctl.append(_c("fluido", "permuta simples com AQS: fluido atóxico", "declarado atóxico" if fl.get("atoxico") else "a justificar",
                      True if fl.get("atoxico") else None))

    eta0, a1 = col.get("eta0"), col.get("a1")
    ua_min = ua_permutador_min(float(eta0), ac, float(a1)) if (eta0 and a1 and ac) else None
    deta = None
    if pm_.get("ua_w_k") and ua_min is not None:
        deta = perda_rendimento(float(eta0), ac, float(a1), float(pm_["ua_w_k"]))
        ctl.append(_c("permutador", f"Δη < 10 % ou seja (UA)hx ≥ {ua_min:.0f} W/K", f"(UA)hx {float(pm_['ua_w_k']):g} W/K → Δη = {deta * 100:.1f} %",
                      deta < PERMUTADOR_DETA_MAX))
    elif ua_min is not None:
        ctl.append(_c("permutador", f"(UA)hx ≥ {ua_min:.0f} W/K (Δη < 10 %)", "(UA)hx a fornecer (ensaio EN 12977-3/-4 ou ficha)", None))
    else:
        ctl.append(_falta("permutador", "Δη = η0·Ac·a1/(UA)hx < 10 %", "η0, a1 e área dos coletores"))
    if pm_.get("dp_mca") is not None:
        ctl.append(_c("permutador", f"perdas de pressão < {PERMUTADOR_DP_MAX:g} m c.a.", f"{float(pm_['dp_mca']):g} m c.a.", float(pm_["dp_mca"]) < PERMUTADOR_DP_MAX))
    if p.get("coletivo") and not direto and pm_.get("material"):
        m = pm_["material"]
        ok = m in ("inox", "inox_titanio") or (m == "cobre" and pm_.get("ep_cobre_mm") is not None and float(pm_["ep_cobre_mm"]) >= CU_EP_MIN_MM)
        ctl.append(_c("permutador_aqs", f"inox, inox ao titânio ou cobre ≥ {CU_EP_MIN_MM:g} mm", m + (f" {float(pm_['ep_cobre_mm']):g} mm" if pm_.get("ep_cobre_mm") else ""),
                      ok if m != "cobre" or pm_.get("ep_cobre_mm") is not None else None))

    ua_b = ua_deposito_max(float(dep["volume_l"])) if dep.get("volume_l") else None
    if ua_b is not None and dep.get("ua_w_k") is not None:
        ctl.append(_c("deposito", f"(UA) ≤ 0,16·√{float(dep['volume_l']):g} = {ua_b:.2f} W/K", f"{float(dep['ua_w_k']):g} W/K", float(dep["ua_w_k"]) <= ua_b + 1e-9))
    elif ua_b is not None:
        ctl.append(_c("deposito", f"(UA) ≤ {ua_b:.2f} W/K", "(UA) a fornecer (ficha do fabricante / etiqueta ErP)", None))
    else:
        ctl.append(_falta("deposito", "(UA) ≤ 0,16·√Vs", "volume do depósito"))
    if not direto and uso in ("aqs", "combinado"):
        ctl.append(_c("deposito", "depósito de AQS de aquecimento indireto conforme EN 12897", "declarado" if dep.get("en12897") else "a justificar",
                      True if dep.get("en12897") else None))

    ch = dict(p.get("cargas") or {})
    adm = {}
    for k, coef, lab_ in (("pressao", COEF_PRESSAO, "pressão"), ("succao", COEF_SUCCAO, "sucção")):
        if ch.get(f"ensaio_{k}_pa"):
            adm[k] = float(ch[f"ensaio_{k}_pa"]) / coef
            sol = ch.get(f"{k}_pa")
            ctl.append(_c("cargas", f"carga admissível em {lab_} = ensaio / {coef:g} = {adm[k]:.0f} Pa",
                          f"solicitação {float(sol):.0f} Pa" if sol is not None else "solicitação de vento / neve a fornecer",
                          (float(sol) <= adm[k]) if sol is not None else None))
    hyp.append("pré-dimensionamento indicativo: o contributo solar para o SCE calcula-se com o SolTerm (LNEG) e a instalação é feita por instalador certificado")
    return {"cheio": cheio, "circuito": "direto" if direto else "indireto", "numero_coletores": n, "area_coletores_m2": ac, "t_max_c": t_max, "p_max_bar": p_max,
            "ua_permutador_min_w_k": ua_min, "perda_rendimento": deta, "ua_deposito_max_w_k": ua_b, "cargas_admissiveis_pa": adm,
            "dimensionamento": dim, "controles": ctl, "hipoteses": hyp}


def note(p: dict) -> dict:
    from . import notes
    r = calcular(p)
    f, W = notes._f, notes.W
    nok = sum(1 for c in r["controles"] if c["ok"] is False)
    nav = sum(1 for c in r["controles"] if c["ok"] is None)
    d = r["dimensionamento"]
    rows = [["Tipo de instalação", ("coletores permanentemente cheios" if r["cheio"] else "autodrenante") + f", circuito {r['circuito']}"],
            ["Coletores", f"{r['numero_coletores']} × " + (f"{r['area_coletores_m2'] / r['numero_coletores']:g} m² = {r['area_coletores_m2']:g} m²"
                                                         if r["area_coletores_m2"] else "área a fornecer")],
            ["T / P máx. consideradas", (f"{r['t_max_c']:g} °C" if r["t_max_c"] is not None else "—") + " / " + (f"{r['p_max_bar']:g} bar" if r["p_max_bar"] is not None else "—")],
            ["(UA) mínimo do permutador (Δη < 10 %)", f"{r['ua_permutador_min_w_k']:.0f} W/K" if r["ua_permutador_min_w_k"] is not None else "—"],
            ["(UA) máximo do depósito", f"{r['ua_deposito_max_w_k']:.2f} W/K" if r["ua_deposito_max_w_k"] is not None else "—"]]
    for k, v in r["cargas_admissiveis_pa"].items():
        rows.append([f"Carga admissível do coletor ({'pressão' if k == 'pressao' else 'sucção'})", f"{f(v)} Pa"])
    kp = [{"label": "Não conformes", "value": str(nok), "unit": ""}, {"label": "A verificar", "value": str(nav), "unit": ""},
          {"label": "Área de coletores", "value": f"{r['area_coletores_m2']:g}".replace(".", ",") if r["area_coletores_m2"] else "—", "unit": "m²"}]
    blocs = [("p", "Pré-dimensionamento indicativo e verificação dos materiais. O cálculo regulamentar do contributo solar (SCE) faz-se com o "
                   "SolTerm (LNEG); as regras de montagem são da responsabilidade do instalador certificado.")]
    n = 1
    if d:
        kp.append({"label": "Fração solar", "value": f"{d['fracao_solar'] * 100:.0f}" if d.get("fracao_solar") is not None else "—", "unit": "%"})
        drow = [["Ocupantes (convenção REH)", f"{d['ocupantes']}"], ["Consumo de AQS", f"{d['consumo_l_dia']:.0f} L/dia a 60 °C (ΔT 35 K)"],
                ["Necessidades de AQS (Qa)", f"{f(d['Qa_kwh'])} kWh/ano"], ["Irradiação no plano dos coletores", f"{f(d['irradiacao'])} kWh/(m².ano)"],
                ["Rendimento do sistema", f"{d['eta_sist']:.2f}".replace(".", ",") + f" ({d['sistema']})"],
                ["Área sugerida (≈ 70 % de fração solar)", f"{d['area_sugerida_m2']:.1f} m²".replace(".", ",")],
                ["Acumulação sugerida", f"{d['volume_sugerido_l'][0]:.0f} a {d['volume_sugerido_l'][1]:.0f} L"]]
        if d.get("producao_kwh") is not None:
            drow += [["Produção anual estimada", f"{f(d['producao_kwh'])} kWh/ano"], ["Fração solar", f"{d['fracao_solar'] * 100:.0f} %"]]
        blocs += [("h2", f"{n}. Pré-dimensionamento"), ("table", ["Grandeza", "Valor"], drow, [80 * W, 95 * W])]
        n += 1
    blocs += [("h2", f"{n}. Síntese dos materiais"), ("table", ["Grandeza", "Valor"], rows, [80 * W, 95 * W]),
              ("h2", f"{n + 1}. Controlos"),
              ("controls", [{"ref": c["ref"], "exigence": c["exigencia"], "valeur": c["valor"], "ok": c["ok"], "note": c.get("note")} for c in r["controles"]])]
    titre = "Solar térmico — pré-dimensionamento e verificação dos materiais"
    sous = f"{r['numero_coletores']} coletor(es) · {nok} não conformidade(s) · {nav} ponto(s) a verificar"
    pdf, png = notes.pdf(titre, sous, [("kpis", kp)] + blocs, r["hipoteses"])
    return {**r, "titre": titre, "sous_titre": sous, "pdf": pdf, "png": png}
