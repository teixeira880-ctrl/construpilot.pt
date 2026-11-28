"""Pré-estudo térmico do projeto do Ateliê, feito sobre as camadas REAIS das paredes do modelo.

Portugal (REH — DL 101-D/2020, Portaria 138-I/2021, Anexo I): U de cada parede exterior (EN ISO 6946) contra o Umáx da zona
climática, Uw,máx dos vãos e gtot,máx; quando não cumpre, diz o isolamento a acrescentar.
França (RE2020 — arrêté du 4 août 2021): Bbio, Cep, Cep,nr, Ic e DH só podem ser calculados pelo motor oficial (Th-BCE) num
software aprovado; aqui verificam-se as exigências de meios que a geometria já permite (superfície envidraçada ≥ 1/6 da
superfície habitável) e calculam-se os U das paredes para o BET térmico.

Regras para não inventar nada:
- λ por defeito só de tabela publicada (SEAI DEAP — TGD L 2022 / CIBSE A / EN ISO 10456), sempre com a fonte e a indicação
  «confirmar o λ declarado (DoP) do produto»; o utilizador pode substituir qualquer λ ou R pelo valor declarado.
- Alvenarias de blocos furados (tijolo furado, bloco térmico, bloco de betão vazado…) não têm λ de material: sem o R do
  fabricante ou do ITE 50 do LNEC, a camada conta como 0 — o U sai então como LIMITE SUPERIOR (o real é melhor), e diz-se
  que R falta para concluir.
- Resistências superficiais EN ISO 6946: Rsi 0,13 / Rse 0,04 (paredes, fluxo horizontal).
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from engines.fio_projeto.lingua import LANG

RSI, RSE = 0.13, 0.04            # EN ISO 6946, fluxo horizontal
LAMBDA_ISOLANTE_REF = 0.038      # EPS SD (SEAI DEAP / EN ISO 10456) — referência conservadora para indicar espessuras
ESP_COMERCIAIS_CM = (2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 24)
FONTE_SEAI = "SEAI DEAP (TGD L 2022, CIBSE A, EN ISO 10456)"
FONTE_ISO6946 = "EN ISO 6946"

# Portaria 138-I/2021, Anexo I — habitação (Tabelas 1, 2, 3, 6 e 8)
UMAX = {
    "continente": {"parede": {"I1": 0.50, "I2": 0.40, "I3": 0.35}, "cobertura": {"I1": 0.40, "I2": 0.35, "I3": 0.30},
                   "ptp": {"I1": 0.90, "I2": 0.90, "I3": 0.90}, "uw": {"I1": 2.80, "I2": 2.40, "I3": 2.20}},
    "madeira": {"parede": {"I1": 0.50, "I2": 0.40, "I3": 0.35}, "cobertura": {"I1": 0.40, "I2": 0.35, "I3": 0.30},
                "ptp": {"I1": 0.90, "I2": 0.90, "I3": 0.90}, "uw": {"I1": 2.80, "I2": 2.40, "I3": 2.20}},
    "acores": {"parede": {"I1": 1.75, "I2": 1.60, "I3": 1.45}, "cobertura": {"I1": 1.25, "I2": 1.00, "I3": 0.90},
               "ptp": {"I1": 1.75, "I2": 1.60, "I3": 1.45}, "uw": {"I1": 2.90, "I2": 2.60, "I3": 2.40}},
}
GTOT_MAX = {"fraca": {"V1": 0.15, "V2": 0.10, "V3": 0.10}, "media": {"V1": 0.56, "V2": 0.56, "V3": 0.50}}
FONTE_PT = "Portaria n.º 138-I/2021, Anexo I (Tabelas 1 a 8)"

# RE2020 — exigências de meios retomadas da RT2012 (arrêté du 4 août 2021)
FR_MOYENS = {"ratio_psi_max": 0.33, "psi9_max": 0.6, "q4_maison_max": 0.6, "q4_collectif_max": 1.0, "baies_min_shab": 1 / 6}


def _n(v: Any) -> str:
    """Número com vírgula decimal (pt / fr)."""
    return str(v).replace(".", ",")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


# (palavras-chave, λ W/(m.K), fonte, é isolante) — por ordem: a primeira que casa vence
_TABELA: List[Tuple[Tuple[str, ...], Optional[float], str, bool]] = [
    (("caixa de ar ventilada",), None, "ventilada", False),          # camadas exteriores a uma caixa ventilada não contam
    (("caixa de ar",), None, "ar", False),
    (("tijolo ceramico furado", "bloco ceramico", "alvenaria de tijolo ceramico", "bloco de betao normal", "bloco de betao de argila",
      "bloco termico", "bloco de cofragem", "bloco silico", "abobadilha", "laje aligeirada", "laje alveolar", "tijolo de vidro"),
     None, "bloco", False),
    (("placa de gesso com isolamento colado",), None, "doublage", True),
    (("poliestireno expandido grafitado", "eps cinza"), 0.038, FONTE_SEAI, True),
    (("poliestireno expandido", "(eps)", "isolamento termico pelo exterior (eps)"), 0.038, FONTE_SEAI, True),
    (("poliestireno extrudido", "xps"), 0.029, FONTE_SEAI, True),
    (("la de rocha", "la de vidro", "la mineral"), 0.037, FONTE_SEAI, True),
    (("poliisocianurato", "pir"), 0.025, FONTE_SEAI, True),
    (("poliuretano",), 0.028, FONTE_SEAI, True),
    (("espuma fenolica",), 0.025, FONTE_SEAI, True),
    (("celulose",), 0.042, FONTE_SEAI, True),
    (("betao armado", "laje macica", "massame de betao armado", "pre-laje", "painel pre-fabricado de betao"), 2.30, FONTE_SEAI, False),
    (("betao celular", "bloco de betao celular"), 0.20, FONTE_SEAI, False),
    (("betao",), 2.00, FONTE_SEAI, False),
    (("gesso cartonado", "placa de gesso"), 0.25, FONTE_SEAI, False),
    (("bloco de gesso",), None, "bloco", False),
    (("reboco projetado de gesso", "estuque", "reboco de gesso"), 0.43, FONTE_SEAI, False),
    (("reboco termico",), None, "dop", False),
    (("reboco", "argamassa", "betonilha", "camada de base armada", "acabamento acrilico", "acabamento de silicato",
      "acabamento de silicone", "acabamento exterior", "monomassa", "barramento", "cimento-cola", "salpico"), 1.00, FONTE_SEAI, False),
    (("osb", "contraplacado", "aglomerado de madeira", "mdf", "painel de madeira", "madeira lamelada", "madeira microlaminada",
      "estrutura de madeira", "madeira macica de pinho", "madeira macica de criptomeria", "ripado de madeira"), 0.13, FONTE_SEAI, False),
    (("madeira macica de carvalho", "madeira macica de castanho"), 0.18, FONTE_SEAI, False),
    (("azulejo", "gres", "ceramica", "mosaico"), 1.30, FONTE_SEAI, False),
    (("granito", "basalto", "marmore"), 3.50, FONTE_SEAI, False),
    (("calcario",), 1.70, FONTE_SEAI, False),
    (("arenito",), 2.30, FONTE_SEAI, False),
    (("ardosia",), 2.20, FONTE_SEAI, False),
    (("tijolo ceramico macico", "tijolo de burro", "tijolo ceramico face a vista"), 0.77, FONTE_SEAI, False),
    (("membrana", "barreira para-vapor", "barreira pára-vapor", "geotextil", "emulsao"), 0.0, "desprezável", False),
]


def material(nome: str) -> Dict[str, Any]:
    n = _norm(nome)
    for chaves, lam, fonte, isol in _TABELA:
        if any(_norm(k) in n for k in chaves):
            return {"lambda": lam, "fonte": fonte, "isolante": isol}
    return {"lambda": None, "fonte": "desconhecido", "isolante": False}


def _r_ar(esp_m: float) -> float:
    """Caixa de ar não ventilada, fluxo horizontal (EN ISO 6946, Tabela 8): 0,11 (5 mm) … 0,18 (≥ 25 mm)."""
    mm = esp_m * 1000
    pontos = [(0, 0.0), (5, 0.11), (7, 0.13), (10, 0.15), (15, 0.17), (25, 0.18)]
    if mm >= 25:
        return 0.18
    for (a, ra), (b, rb) in zip(pontos, pontos[1:]):
        if a <= mm <= b:
            return round(ra + (rb - ra) * (mm - a) / (b - a), 3)
    return 0.0


def u_parede(camadas: List[Dict[str, Any]], declarados: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """U de uma parede (camadas do interior para o exterior). `declarados`: {material: {"lambda": x} ou {"r": y}}."""
    declarados = {_norm(k): v for k, v in (declarados or {}).items()}
    linhas, faltam, confirmar = [], [], []
    soma_r = RSI + RSE
    ventilada = False
    for c in camadas:
        nome, e = c.get("material") or "", float(c.get("esp_m") or 0)
        if ventilada:
            linhas.append({"material": nome, "esp_m": e, "r": 0.0, "fonte": "exterior a caixa ventilada (EN ISO 6946)"})
            continue
        dec = declarados.get(_norm(nome))
        info = material(nome)
        r, fonte = None, info["fonte"]
        if dec and dec.get("r") is not None:
            r, fonte = float(dec["r"]), "declarado"
        elif dec and dec.get("lambda"):
            r, fonte = e / float(dec["lambda"]), "declarado"
        elif info["fonte"] == "ventilada":
            ventilada, r, fonte = True, 0.0, FONTE_ISO6946
            soma_r = soma_r - RSE + RSI          # depois de uma caixa ventilada: Rse = Rsi (EN ISO 6946 §6.9.4)
        elif info["fonte"] == "ar":
            r, fonte = _r_ar(e), FONTE_ISO6946
        elif info["fonte"] == "doublage":     # placa de gesso 13 mm + EPS colado
            r = 0.013 / 0.25 + max(e - 0.013, 0) / LAMBDA_ISOLANTE_REF
            fonte = FONTE_SEAI
            confirmar.append(nome)
        elif info["lambda"] is not None:
            r = e / info["lambda"] if info["lambda"] > 0 else 0.0
            if info["isolante"]:
                confirmar.append(nome)
        else:
            faltam.append(nome)
        lam = (dec or {}).get("lambda") or (info["lambda"] if fonte == FONTE_SEAI and info["fonte"] != "doublage" else None)
        linhas.append({"material": nome, "esp_m": e, "r": None if r is None else round(r, 3), "fonte": fonte, "lambda": lam})
        if r is not None:
            soma_r += r
    u = 1 / soma_r
    return {"u": round(u, 3), "r_total": round(soma_r, 3), "camadas": linhas, "limite_superior": bool(faltam),
            "faltam": sorted(set(faltam)), "confirmar_dop": sorted(set(confirmar))}


def _isolamento_a_acrescentar(r_total: float, u_alvo: float) -> Optional[Dict[str, Any]]:
    falta_r = 1 / u_alvo - r_total
    if falta_r <= 0:
        return None
    cm = falta_r * LAMBDA_ISOLANTE_REF * 100
    comercial = next((c for c in ESP_COMERCIAIS_CM if c >= cm), math.ceil(cm))
    return {"r_em_falta": round(falta_r, 2), "espessura_cm": comercial, "lambda_ref": LAMBDA_ISOLANTE_REF}


def _vaos_area(vaos: List[Dict[str, Any]], tipos=("janela", "portada", "porta-janela", "porta_janela")) -> float:
    a = 0.0
    for v in vaos:
        if str(v.get("tipo") or "").lower() in tipos and v.get("largura_m") and v.get("altura_m"):
            a += float(v["largura_m"]) * float(v["altura_m"]) * int(v.get("quantidade") or 1)
    return round(a, 2)


def estudo(m: Dict[str, Any], der: Dict[str, Any], *, zona_inverno: str = "", zona_verao: str = "", regiao: str = "continente",
           inercia: str = "media", declarados: Optional[Dict[str, Dict[str, float]]] = None,
           uw_declarados: Optional[Dict[str, float]] = None, pais: Optional[str] = None) -> Dict[str, Any]:
    pais = (pais or ("pt" if LANG == "pt" else "fr")).lower()
    med = der.get("medicoes") or {}
    tipos = m.get("tipos_parede") or {}
    usados = {pt.get("tipo"): pt for pt in med.get("por_tipo") or []}
    paredes = []
    for tid, pt in usados.items():
        t = tipos.get(tid) or {}
        if not t.get("exterior"):
            continue
        r = u_parede(t.get("camadas") or [], declarados)
        paredes.append({"tipo": tid, "nome": t.get("nome"), "area_m2": pt.get("area_liquida_m2"), **r})
    vaos = []
    for linha in med.get("mapa_vaos") or []:
        vaos.append({k: linha.get(k) for k in ("codigo", "tipo", "largura_m", "altura_m", "caixilharia")} | {"quantidade": len(linha.get("ids") or [])})
    area_vidro = _vaos_area(vaos)
    area_util = float((med.get("totais") or {}).get("area_util_m2") or 0)
    out: Dict[str, Any] = {"pais": pais, "paredes": paredes, "vaos": vaos, "area_envidracada_m2": area_vidro,
                           "area_util_m2": area_util, "cobertura": med.get("cobertura") or {}, "verificacoes": [], "indicacoes": [],
                           "dados_em_falta": [], "rsi": RSI, "rse": RSE}
    ver, ind, falta = out["verificacoes"], out["indicacoes"], out["dados_em_falta"]

    for p in paredes:
        if p["faltam"]:
            falta.append({"o_que": "R da alvenaria" if pais == "pt" else "R de la maçonnerie", "materiais": p["faltam"], "parede": p["nome"],
                          "onde": "ficha técnica do fabricante (DoP) ou LNEC ITE 50" if pais == "pt" else "fiche du fabricant (DoP) ou Th-U"})
        if p["confirmar_dop"]:
            falta.append({"o_que": "λ declarado do isolamento" if pais == "pt" else "λ déclaré de l'isolant", "materiais": p["confirmar_dop"], "parede": p["nome"],
                          "onde": "Declaração de Desempenho (DoP) do produto escolhido" if pais == "pt" else "Déclaration de performance (DoP)"})

    if pais == "pt":
        zi = (zona_inverno or "").upper()
        zv = (zona_verao or "").upper()
        reg = (regiao or "continente").lower()
        tab = UMAX.get(reg, UMAX["continente"])
        out["regulamento"] = FONTE_PT
        if zi not in ("I1", "I2", "I3"):
            falta.append({"o_que": "zona climática de inverno (I1, I2 ou I3)", "onde": "concelho e altitude do terreno (Despacho 15793-F/2013)"})
        else:
            umax = tab["parede"][zi]
            for p in paredes:
                ok = p["u"] <= umax
                ver.append({"elemento": p["nome"], "grandeza": "U parede", "valor": p["u"], "limite": umax,
                            "estado": "cumpre" if ok else ("a confirmar" if p["limite_superior"] else "não cumpre"),
                            "nota": "U calculado sem a alvenaria (limite superior): o valor real é melhor" if p["limite_superior"] else ""})
                if not ok:
                    a = _isolamento_a_acrescentar(p["r_total"], umax)
                    if a:
                        ind.append(f"{p['nome']}: acrescentar ≥ {_n(a['espessura_cm'])} cm de isolamento com λ ≤ {_n(a['lambda_ref'])} W/(m·K) "
                                   f"(R em falta {_n(a['r_em_falta'])} m²·°C/W) para U ≤ {_n(umax)}"
                                   + (" — ou demonstrar o R da alvenaria com a ficha do fabricante." if p["limite_superior"] else "."))
            ucob = tab["cobertura"][zi]
            r_min = round(1 / ucob - 0.10 - 0.04, 2)          # Rsi fluxo ascendente 0,10 (EN ISO 6946)
            ind.append(f"Cobertura e pavimento sobre exterior: U ≤ {_n(ucob)} — resistência das camadas ≥ {_n(r_min)} m²·°C/W "
                       f"(≈ {_n(math.ceil(r_min * LAMBDA_ISOLANTE_REF * 100))} cm de isolamento λ {_n(LAMBDA_ISOLANTE_REF)}, sem contar a laje).")
            ver.append({"elemento": "Pontes térmicas planas (pilares, vigas, caixas de estore)", "grandeza": "U PTP",
                        "valor": None, "limite": tab["ptp"][zi], "estado": "a verificar",
                        "nota": "isolar pelo exterior de forma contínua (ETICS) resolve as PTP"})
            uwmax = tab["uw"][zi]
            for v in vaos:
                if str(v.get("tipo")) not in ("janela", "portada"):
                    continue
                uw = (uw_declarados or {}).get(v.get("codigo")) or (uw_declarados or {}).get(v.get("caixilharia") or "")
                ver.append({"elemento": f"Vão {v.get('codigo')} ({v.get('caixilharia') or '—'})", "grandeza": "Uw", "valor": uw,
                            "limite": uwmax, "estado": ("cumpre" if uw <= uwmax else "não cumpre") if uw else "a confirmar",
                            "nota": "" if uw else "pedir o Uw da janela (marcação CE) ao fornecedor"})
            if any(v.get("tipo") in ("janela", "portada") for v in vaos):
                ind.append(f"Caixilharia: Uw ≤ {_n(uwmax)} W/(m²·°C) com vidro duplo baixo emissivo e corte térmico.")
        if zv in ("V1", "V2", "V3"):
            gmax = GTOT_MAX["fraca" if inercia == "fraca" else "media"][zv]
            ind.append(f"Proteção solar dos vãos não orientados a norte: gtot ≤ {_n(gmax)} (estores ou portadas exteriores).")
        else:
            falta.append({"o_que": "zona climática de verão (V1, V2 ou V3)", "onde": "concelho e altitude do terreno"})
        out["aprovacao"] = ("Pré-estudo REH. O pré-certificado SCE é emitido por um Perito Qualificado (ADENE) com o "
                            "cálculo completo das necessidades (Nic, Nvc, Ntc) — este estudo dá-lhe a envolvente pronta e conforme.")
    else:
        out["regulamento"] = "RE2020 — arrêté du 4 août 2021"
        if area_util > 0:
            alvo = round(area_util * FR_MOYENS["baies_min_shab"], 2)
            ok = area_vidro >= alvo
            ver.append({"elemento": "Surface des baies (côté tableau)", "grandeza": "≥ 1/6 SHAB", "valor": area_vidro, "limite": alvo,
                        "estado": "conforme" if ok else "non conforme",
                        "nota": "surface habitable estimée par la surface utile de la maquette"})
            if not ok:
                ind.append(f"Augmenter la surface vitrée d'au moins {_n(round(alvo - area_vidro, 2))} m² (exigence de moyens 1/6 SHAB).")
        for p in paredes:
            ver.append({"elemento": p["nome"], "grandeza": "U paroi (information BET)", "valor": p["u"], "limite": None,
                        "estado": "à confirmer" if p["limite_superior"] else "calculé",
                        "nota": "U sans la maçonnerie (borne haute)" if p["limite_superior"] else ""})
        ind += [f"Ponts thermiques : ratio ψ moyen ≤ {_n(FR_MOYENS['ratio_psi_max'])} W/(m²SRT·K) et ψ9 ≤ {_n(FR_MOYENS['psi9_max'])} W/(m·K) "
                "— rupteurs de ponts thermiques ou isolation par l'extérieur continue.",
                f"Perméabilité à l'air : Q4Pa-surf ≤ {_n(FR_MOYENS['q4_maison_max'])} m³/(h·m²) en maison individuelle "
                f"({_n(FR_MOYENS['q4_collectif_max'])} en collectif), mesure obligatoire en fin de chantier.",
                "Bbio, Cep, Cep,nr, Ic énergie, Ic construction et DH : calcul réglementaire par un BET thermique avec un logiciel "
                "RE2020 évalué (moteur Th-BCE) ; ce pré-dimensionnement lui fournit l'enveloppe, les surfaces et les U."]
        out["aprovacao"] = ("Pré-étude RE2020. L'attestation de prise en compte (dépôt du permis) et l'attestation d'achèvement "
                            "sont établies à partir du calcul réglementaire du BET thermique.")
    estados = [v["estado"] for v in ver]
    if "não cumpre" in estados or "non conforme" in estados:
        res = "nao_cumpre"
    elif falta or any(e in ("a confirmar", "à confirmer", "a verificar") for e in estados):
        res = "a_confirmar"
    else:
        res = "cumpre"
    out["estado"] = res
    out["resultado"] = {"pt": {"nao_cumpre": "não cumpre", "a_confirmar": "a confirmar", "cumpre": "cumpre"},
                        "fr": {"nao_cumpre": "non conforme", "a_confirmar": "à confirmer", "cumpre": "conforme"}}[pais if pais in ("pt", "fr") else "pt"][res]
    return out
