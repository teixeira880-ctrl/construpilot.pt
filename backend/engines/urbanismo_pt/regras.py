"""Verificação urbanística PT — quadro de áreas, parâmetros do PDM e normas nacionais (lógica pura, testada).

Princípios:
- Os parâmetros MUNICIPAIS (PDM, plano de pormenor, loteamento, regulamento municipal) são sempre
  introduzidos pelo utilizador; o motor nunca inventa um valor municipal. Sem valor → «sem dados».
- As normas NACIONAIS aplicadas citam diploma e artigo, com estado `confirmado` ou `a_confirmar`.
- O procedimento de controlo prévio (isenção / comunicação prévia / licença) é determinado pelo motor
  RJUE existente (engines.autorizacao_obras_pt.rules.diagnosticar) — não é duplicado aqui.

Geometria: ver engines.urbanismo_pt.volumes (convenção x = frente, y = profundidade, origem frente-esquerda).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from engines.autorizacao_obras_pt.rules import diagnosticar
from engines.urbanismo_pt import volumes as V

COUNTRY = "PT"

TIPOS_OBRA = {
    "moradia_nova": "Construção nova (moradia / edifício)",
    "ampliacao": "Ampliação de edifício existente",
    "anexo": "Anexo / edificação de apoio",
    "piscina": "Piscina",
    "muro": "Muro de vedação ou de suporte",
}
TIPOS_EDIFICIO = {"moradia_nova", "ampliacao", "anexo"}
USOS = {"habitacao": "Habitação", "comercio": "Comércio / serviços", "apoio": "Apoio não habitável (garagem, arrumos)"}

# ------------------------------------------------------------------ fontes nacionais ----
FONTES: Dict[str, Dict[str, Any]] = {
    "DR_5_2019": {
        "diploma": "Decreto Regulamentar n.º 5/2019, de 27 de setembro (conceitos técnicos do ordenamento do território e urbanismo)",
        "artigo": "Fichas «área de implantação», «área de construção», «índice de ocupação do solo» e «índice de utilização do solo»",
        "status": "confirmado",
        "nota": "Definições nacionais. Um PDM anterior pode usar definições próprias (p. ex. «área bruta de construção») — "
                "confirmar no regulamento do plano qual a definição a aplicar.",
    },
    "RGEU_65_1": {
        "diploma": "RGEU — Decreto-Lei n.º 38 382/51, de 7 de agosto",
        "artigo": "art.º 65.º, n.º 1 (redação do DL 650/75): altura mínima piso a piso 2,70 m e pé-direito livre mínimo 2,40 m em habitação",
        "status": "confirmado",
        "nota": "O n.º 2 admite 2,20 m em vestíbulos, corredores, instalações sanitárias, despensas e arrecadações; há regras próprias "
                "para tetos inclinados e sótãos. RGEU em vigor: a revogação prevista no art.º 25.º do DL 10/2024 (na redação do "
                "DL 108/2026) só produz efeitos com a entrada em vigor do novo diploma de normas técnicas — confirmar à data do projeto.",
    },
    "RGEU_65_COMERCIO": {
        "diploma": "RGEU — Decreto-Lei n.º 38 382/51, de 7 de agosto",
        "artigo": "art.º 65.º, n.º 3: pé-direito livre mínimo de 3,00 m em pisos destinados a estabelecimentos comerciais",
        "status": "a_confirmar",
        "nota": "Valor recordado do texto do RGEU, não verificado no texto consolidado — confirmar antes de usar.",
    },
    "RGEU_59": {
        "diploma": "RGEU — Decreto-Lei n.º 38 382/51, de 7 de agosto",
        "artigo": "art.º 59.º: nenhum elemento da edificação ultrapassa a linha a 45° traçada a partir do alinhamento da edificação fronteira",
        "status": "a_confirmar",
        "nota": "Regra simplificada (altura da fachada ≤ distância ao alinhamento fronteiro); confirmar a redação e as exceções.",
    },
    "CC_1360": {
        "diploma": "Código Civil",
        "artigo": "art.º 1360.º, n.º 1: janelas, portas, varandas e obras semelhantes que deitem diretamente sobre o prédio vizinho exigem 1,5 m de intervalo",
        "status": "confirmado",
        "nota": "Frestas, seteiras ou óculos para luz e ar são admitidos nos termos do art.º 1363.º. Servidões constituídas podem alterar a situação.",
    },
    "PORTARIA_71A_2024": {
        "diploma": "Portaria n.º 71-A/2024, de 27 de fevereiro (elementos instrutórios dos procedimentos do RJUE)",
        "artigo": "Elementos instrutórios por tipo de procedimento",
        "status": "a_confirmar",
        "nota": "Lista indicativa de peças; confirmar a lista exigida pelo município e eventuais alterações posteriores (DL 108/2026).",
    },
}

RGEU_PISO_A_PISO_MIN_M = 2.70
RGEU_PE_DIREITO_MIN_M = 2.40
RGEU_PE_DIREITO_COMERCIO_M = 3.00
CC_1360_MIN_M = 1.5

# ------------------------------------------------------------------ parâmetros municipais ----
# Introduzidos pelo utilizador (PDM / PP / loteamento / regulamento municipal). Nunca há valor por defeito.
PDM_CAMPOS: List[Dict[str, Any]] = [
    {"key": "iu_max", "label": "Índice de utilização do solo máximo (Iu)", "unit": "m²/m²", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "io_max_pct", "label": "Índice de ocupação do solo máximo (Io)", "unit": "%", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "altura_fachada_max_m", "label": "Altura máxima da fachada (cércea)", "unit": "m", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "altura_total_max_m", "label": "Altura total máxima da construção", "unit": "m", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "n_pisos_max", "label": "Número máximo de pisos acima da cota de soleira", "unit": "", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "afastamento_frontal_min_m", "label": "Afastamento frontal mínimo", "unit": "m", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "afastamento_lateral_min_m", "label": "Afastamento lateral mínimo", "unit": "m", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "afastamento_tardoz_min_m", "label": "Afastamento de tardoz mínimo", "unit": "m", "tipos": sorted(TIPOS_EDIFICIO)},
    {"key": "lugares_por_fogo", "label": "Lugares de estacionamento por fogo", "unit": "lug./fogo", "tipos": ["moradia_nova", "ampliacao"]},
    {"key": "lugares_por_100m2", "label": "Lugares de estacionamento por 100 m² de área de construção", "unit": "lug./100 m²", "tipos": ["moradia_nova", "ampliacao"]},
    {"key": "altura_muro_max_m", "label": "Altura máxima de muros (regulamento municipal)", "unit": "m", "tipos": ["muro"]},
    {"key": "afastamento_piscina_min_m", "label": "Afastamento mínimo da piscina aos limites (regulamento municipal)", "unit": "m", "tipos": ["piscina"]},
]
PDM_TEXTO = ("plano", "classe_espaco", "fonte_artigos")
_PDM_KEYS = {c["key"] for c in PDM_CAMPOS}
_PDM_LABEL = {c["key"]: c["label"] for c in PDM_CAMPOS}

ENQUADRAMENTO_CAMPOS = (
    "zona_protegida", "imovel_classificado", "confina_via_publica", "tem_edificacao_principal",
    "tem_pdm_com_parametros", "tem_loteamento_pip", "zona_urbana_consolidada",
)

AVISO = ("Ferramenta de apoio à preparação do processo. Os desenhos são esquemáticos e as verificações dependem dos "
         "parâmetros do plano municipal introduzidos pelo utilizador. A responsabilidade do projeto e do processo é do "
         "requerente e dos técnicos autores (termos de responsabilidade, art.º 10.º do RJUE).")


def _pos(v) -> Optional[float]:
    """Número positivo ou None (vazio, inválido ou ≤ 0 → sem dado)."""
    try:
        if v is None or v == "" or isinstance(v, bool):
            return None
        f = float(v)
        return f if f > 0 and math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def normalizar_pdm(pdm: Dict[str, Any] | None) -> Dict[str, Any]:
    p = pdm or {}
    out: Dict[str, Any] = {k: _pos(p.get(k)) for k in _PDM_KEYS}
    if out.get("n_pisos_max") is not None:
        out["n_pisos_max"] = int(out["n_pisos_max"])
    for k in PDM_TEXTO:
        out[k] = (str(p.get(k) or "").strip()[:300]) or None
    return out


def _item(codigo, titulo, valor, limite, unidade, resultado, fonte_key=None, fonte_user=False, nota=""):
    if fonte_user:
        fonte = {"diploma": "Parâmetro municipal introduzido pelo utilizador", "artigo": "", "status": "parametro_utilizador"}
    elif fonte_key:
        f = FONTES[fonte_key]
        fonte = {"diploma": f["diploma"], "artigo": f["artigo"], "status": f["status"]}
    else:
        fonte = {"diploma": "Coerência geométrica do desenho", "artigo": "", "status": "confirmado"}
    return {"codigo": codigo, "titulo": titulo, "valor": valor, "limite": limite, "unidade": unidade,
            "resultado": resultado, "fonte": fonte, "nota": nota}


def _cmp_max(val, lim):
    if lim is None:
        return "sem_dados"
    return "conforme" if val <= lim + 1e-9 else "nao_conforme"


def _cmp_min(val, lim):
    if lim is None:
        return "sem_dados"
    return "conforme" if val >= lim - 1e-9 else "nao_conforme"


# ------------------------------------------------------------------ quadro de áreas ----
def quadro_areas(volume: Dict[str, Any], terreno: Dict[str, Any] | None = None,
                 enquadramento: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Quadro de áreas, índices, alturas e afastamentos calculados a partir do editor de volumes."""
    v = volume or {}
    ter = terreno or {}
    enq = enquadramento or {}
    polys = V.building_polygons(v)
    main = [p for p in polys if not p["annexe"]]
    annex = [p for p in polys if p["annexe"]]
    hh = V.heights(v)
    plot_l = max(1.0, V._num(v.get("plot_l_m"), 20))
    plot_w = max(1.0, V._num(v.get("plot_w_m"), 15))
    at_user = _pos(ter.get("area_terreno_m2"))
    area_terreno = at_user or plot_l * plot_w
    ai = V.union_area(polys)
    ai_main = V.union_area(main)
    ai_annex = V.union_area(annex) if annex else 0.0
    ac_calc = ai_main * hh["levels"] + ai_annex
    ac_user = _pos(v.get("area_construcao_m2"))
    ac = ac_user or ac_calc
    mnx, mny, mxx, mxy = V.bbox(main)
    af = {"frontal": mny, "lateral_esquerdo": mnx, "lateral_direito": plot_l - mxx, "tardoz": plot_w - mxy}
    if annex:
        a_mnx, a_mny, a_mxx, a_mxy = V.bbox(annex)
        af_annex = {"frontal": a_mny, "lateral_esquerdo": a_mnx, "lateral_direito": plot_l - a_mxx, "tardoz": plot_w - a_mxy}
    else:
        af_annex = None
    slab = V._num(v.get("espessura_laje_m"), 0.30)
    slab = min(max(slab, 0.0), 1.0)
    existente = _pos(enq.get("area_construcao_existente_m2"))
    fogos = int(_pos(v.get("n_fogos")) or 0) or None
    lugares = v.get("lugares_previstos")
    try:
        lugares = int(lugares) if lugares not in (None, "") else None
    except (TypeError, ValueError):
        lugares = None
    out = {
        "area_terreno_m2": round(area_terreno, 2),
        "area_terreno_origem": "indicada (caderneta / certidão / levantamento)" if at_user else "retângulo do editor (frente × profundidade)",
        "area_implantacao_m2": round(ai, 2),
        "area_implantacao_principal_m2": round(ai_main, 2),
        "area_implantacao_anexos_m2": round(ai_annex, 2),
        "area_construcao_m2": round(ac, 2),
        "area_construcao_origem": "indicada pelo utilizador" if ac_user else "calculada (implantação principal × pisos + anexos num piso)",
        "indice_ocupacao_pct": round(ai / area_terreno * 100, 2),
        "indice_utilizacao": round(ac / area_terreno, 3),
        "n_pisos": hh["levels"],
        "piso_a_piso_m": round(hh["storey_h_m"], 2),
        "espessura_laje_m": round(slab, 2),
        "pe_direito_livre_m": round(hh["storey_h_m"] - slab, 2),
        "altura_fachada_m": hh["altura_fachada_m"],
        "altura_total_m": hh["altura_total_m"],
        "cobertura": V.ROOF_TYPES[hh["roof_type"]],
        "afastamentos_m": {k: round(x, 2) for k, x in af.items()},
        "afastamentos_anexos_m": {k: round(x, 2) for k, x in af_annex.items()} if af_annex else None,
        "terreno_frente_m": plot_l, "terreno_profundidade_m": plot_w,
        "n_fogos": fogos, "lugares_previstos": lugares,
        "area_construcao_existente_m2": existente,
        "area_construcao_criada_m2": round(max(0.0, ac - (existente or 0.0)), 2) if existente is not None else None,
    }
    return out


# ------------------------------------------------------------------ verificações ----
def _verif_edificio(q: Dict[str, Any], pdm: Dict[str, Any], v: Dict[str, Any], tipo: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    af = q["afastamentos_m"]
    allaf = list(af.values()) + (list((q["afastamentos_anexos_m"] or {}).values()))
    fora = min(allaf) < -1e-6
    items.append(_item("GEOM_DENTRO_TERRENO", "Construção contida no terreno", round(min(allaf), 2), 0.0, "m",
                       "nao_conforme" if fora else "conforme",
                       nota="Algum volume ultrapassa o limite do terreno — corrija as dimensões ou os afastamentos." if fora else ""))
    items.append(_item("PDM_IU", "Índice de utilização do solo (Iu)", q["indice_utilizacao"], pdm["iu_max"], "m²/m²",
                       _cmp_max(q["indice_utilizacao"], pdm["iu_max"]), fonte_user=True,
                       nota="Iu = área de construção / área do terreno (DR 5/2019)."))
    items.append(_item("PDM_IO", "Índice de ocupação do solo (Io)", q["indice_ocupacao_pct"], pdm["io_max_pct"], "%",
                       _cmp_max(q["indice_ocupacao_pct"], pdm["io_max_pct"]), fonte_user=True,
                       nota="Io = área de implantação / área do terreno × 100 (DR 5/2019)."))
    items.append(_item("PDM_ALTURA_FACHADA", "Altura da fachada (cércea)", q["altura_fachada_m"], pdm["altura_fachada_max_m"], "m",
                       _cmp_max(q["altura_fachada_m"], pdm["altura_fachada_max_m"]), fonte_user=True,
                       nota="Medida da cota de soleira ao beirado / platibanda; terreno considerado plano."))
    items.append(_item("PDM_ALTURA_TOTAL", "Altura total da construção", q["altura_total_m"], pdm["altura_total_max_m"], "m",
                       _cmp_max(q["altura_total_m"], pdm["altura_total_max_m"]), fonte_user=True))
    items.append(_item("PDM_N_PISOS", "Número de pisos acima da cota de soleira", q["n_pisos"], pdm["n_pisos_max"], "",
                       _cmp_max(q["n_pisos"], pdm["n_pisos_max"]), fonte_user=True))
    items.append(_item("PDM_AFAST_FRONTAL", "Afastamento frontal", af["frontal"], pdm["afastamento_frontal_min_m"], "m",
                       _cmp_min(af["frontal"], pdm["afastamento_frontal_min_m"]), fonte_user=True))
    lat = min(af["lateral_esquerdo"], af["lateral_direito"])
    items.append(_item("PDM_AFAST_LATERAL", "Afastamento lateral (o menor dos dois)", round(lat, 2), pdm["afastamento_lateral_min_m"], "m",
                       _cmp_min(lat, pdm["afastamento_lateral_min_m"]), fonte_user=True,
                       nota="Moradias geminadas / em banda encostadas ao limite exigem leitura própria do regulamento."))
    items.append(_item("PDM_AFAST_TARDOZ", "Afastamento de tardoz", af["tardoz"], pdm["afastamento_tardoz_min_m"], "m",
                       _cmp_min(af["tardoz"], pdm["afastamento_tardoz_min_m"]), fonte_user=True))

    if tipo in ("moradia_nova", "ampliacao"):
        exig = []
        if pdm["lugares_por_fogo"] is not None and q["n_fogos"]:
            exig.append(math.ceil(pdm["lugares_por_fogo"] * q["n_fogos"] - 1e-9))
        if pdm["lugares_por_100m2"] is not None:
            exig.append(math.ceil(pdm["lugares_por_100m2"] * q["area_construcao_m2"] / 100 - 1e-9))
        if not exig:
            res, lim, nota = "sem_dados", None, "Indique o rácio do plano municipal (por fogo ou por 100 m²) e, se for o caso, o n.º de fogos."
        elif q["lugares_previstos"] is None:
            res, lim, nota = "sem_dados", max(exig), "Indique o número de lugares de estacionamento previstos no lote."
        else:
            lim = max(exig)
            res = "conforme" if q["lugares_previstos"] >= lim else "nao_conforme"
            nota = "Exigência = maior dos rácios indicados, arredondada à unidade superior."
        items.append(_item("PDM_ESTACIONAMENTO", "Lugares de estacionamento no lote", q["lugares_previstos"], lim, "lugares",
                           res, fonte_user=True, nota=nota))

    uso = v.get("uso") or ("apoio" if tipo == "anexo" else "habitacao")
    if uso == "habitacao":
        items.append(_item("RGEU_65_PISO_A_PISO", "Altura piso a piso (habitação)", q["piso_a_piso_m"], RGEU_PISO_A_PISO_MIN_M, "m",
                           _cmp_min(q["piso_a_piso_m"], RGEU_PISO_A_PISO_MIN_M), fonte_key="RGEU_65_1"))
        items.append(_item("RGEU_65_PE_DIREITO", "Pé-direito livre (compartimentos habitáveis)", q["pe_direito_livre_m"], RGEU_PE_DIREITO_MIN_M, "m",
                           _cmp_min(q["pe_direito_livre_m"], RGEU_PE_DIREITO_MIN_M), fonte_key="RGEU_65_1",
                           nota=f"Pé-direito livre estimado = piso a piso − laje e revestimentos ({V.fmt(q['espessura_laje_m'])} m, valor editável)."))
    elif uso == "comercio":
        items.append(_item("RGEU_65_COMERCIO", "Pé-direito livre (comércio)", q["pe_direito_livre_m"], RGEU_PE_DIREITO_COMERCIO_M, "m",
                           _cmp_min(q["pe_direito_livre_m"], RGEU_PE_DIREITO_COMERCIO_M), fonte_key="RGEU_65_COMERCIO",
                           nota="Valor a confirmar no texto consolidado do RGEU."))
    else:
        items.append(_item("RGEU_65_NA", "Pé-direito (RGEU art.º 65.º)", q["pe_direito_livre_m"], None, "m", "informativo",
                           fonte_key="RGEU_65_1", nota="Uso de apoio não habitável: o mínimo de 2,40 m para habitação não é aplicado."))

    for lado, nome in (("lateral_esquerdo", "limite lateral esquerdo"), ("lateral_direito", "limite lateral direito"), ("tardoz", "limite de tardoz")):
        d = af[lado]
        if d < CC_1360_MIN_M - 1e-9:
            items.append(_item(f"CC_1360_{lado.upper()}", f"Vãos virados para o {nome}", round(d, 2), CC_1360_MIN_M, "m", "atencao",
                               fonte_key="CC_1360",
                               nota=f"A {V.fmt(d)} m do {nome}: não abrir janelas, portas ou varandas que deitem diretamente sobre o "
                                    "prédio vizinho (apenas frestas, art.º 1363.º), salvo servidão constituída."))

    dfront = _pos(v.get("distancia_alinhamento_fronteiro_m"))
    if dfront is not None:
        items.append(_item("RGEU_59_45GRAUS", "Regra dos 45° face ao alinhamento fronteiro", q["altura_fachada_m"], dfront, "m",
                           _cmp_max(q["altura_fachada_m"], dfront), fonte_key="RGEU_59",
                           nota="Altura da fachada comparada com a distância indicada ao alinhamento da edificação fronteira."))
    return items


def _verif_muro(p: Dict[str, Any], pdm: Dict[str, Any]) -> List[Dict[str, Any]]:
    h = _pos(p.get("altura_m"))
    items = []
    if h is None:
        items.append(_item("MURO_ALTURA", "Altura do muro", None, pdm["altura_muro_max_m"], "m", "sem_dados",
                           nota="Indique a altura do muro."))
    else:
        items.append(_item("PDM_ALTURA_MURO", "Altura do muro (regulamento municipal)", h, pdm["altura_muro_max_m"], "m",
                           _cmp_max(h, pdm["altura_muro_max_m"]), fonte_user=True))
    return items


def _verif_piscina(p: Dict[str, Any], pdm: Dict[str, Any]) -> List[Dict[str, Any]]:
    d = _pos(p.get("distancia_limites_m"))
    return [_item("PDM_AFAST_PISCINA", "Afastamento da piscina aos limites", d, pdm["afastamento_piscina_min_m"], "m",
                  "sem_dados" if d is None else _cmp_min(d, pdm["afastamento_piscina_min_m"]), fonte_user=True)]


def respostas_rjue(tipo: str, q: Dict[str, Any] | None, parametros: Dict[str, Any], enq: Dict[str, Any],
                   terreno: Dict[str, Any]) -> Dict[str, Any]:
    """Traduz o processo para as respostas do motor RJUE existente (autorizacao_obras_pt)."""
    r: Dict[str, Any] = {"tipo_obra": tipo if tipo in TIPOS_OBRA else "outro",
                         "concelho": (terreno or {}).get("concelho"), "freguesia": (terreno or {}).get("freguesia")}
    for k in ENQUADRAMENTO_CAMPOS:
        if k in enq and enq[k] is not None:
            r[k] = bool(enq[k])
    r.setdefault("confina_via_publica", False)
    r.setdefault("tem_edificacao_principal", tipo != "moradia_nova")
    if tipo in TIPOS_EDIFICIO and q:
        r["altura_m"] = q["altura_total_m"]
        r["area_implantacao_m2"] = q["area_implantacao_m2"]
        r["area_construcao_total_m2"] = q["area_construcao_m2"]
        if q.get("area_construcao_criada_m2") is not None:
            r["area_construcao_criada_m2"] = q["area_construcao_criada_m2"]
    elif tipo == "piscina":
        L, W = _pos(parametros.get("comprimento_m")), _pos(parametros.get("largura_m"))
        r["area_implantacao_m2"] = round(L * W, 2) if (L and W) else 0.0
        r["area_construcao_total_m2"] = _pos(enq.get("area_construcao_existente_m2")) or 0.0
    elif tipo == "muro":
        r["altura_m"] = _pos(parametros.get("altura_m")) or 0.0
        r["subtipo_muro"] = "suporte" if parametros.get("subtipo") == "suporte" else "vedacao"
        if "confina_via_publica" not in enq:
            r["confina_via_publica"] = (parametros.get("implantacao") or "frente") in ("frente", "frente_e_laterais")
    return r


def verificar(processo: Dict[str, Any]) -> Dict[str, Any]:
    """Verificação completa de um processo: quadro de áreas, PDM, normas nacionais e procedimento RJUE."""
    d = processo or {}
    tipo = d.get("tipo_obra") if d.get("tipo_obra") in TIPOS_OBRA else "moradia_nova"
    pdm = normalizar_pdm(d.get("pdm"))
    enq = d.get("enquadramento") or {}
    ter = d.get("terreno") or {}
    params = d.get("parametros") or {}
    q = None
    if tipo in TIPOS_EDIFICIO and not d.get("volume"):
        items = [_item("VOLUME_POR_DEFINIR", "Volumes da construção", None, None, "", "sem_dados",
                       nota="Defina os volumes no editor para calcular o quadro de áreas e verificar os parâmetros.")]
    elif tipo in TIPOS_EDIFICIO:
        vol = d.get("volume") or {}
        q = quadro_areas(vol, ter, enq)
        items = _verif_edificio(q, pdm, vol, tipo)
    elif tipo == "muro":
        items = _verif_muro(params, pdm)
    else:
        items = _verif_piscina(params, pdm)

    resp = respostas_rjue(tipo, q, params, enq, ter)
    rjue = diagnosticar(resp)
    resumo = {k: sum(1 for i in items if i["resultado"] == k)
              for k in ("conforme", "nao_conforme", "sem_dados", "atencao", "informativo")}
    relevantes = [c for c in PDM_CAMPOS if tipo in c["tipos"]]
    ratio_ok = pdm.get("lugares_por_fogo") is not None or pdm.get("lugares_por_100m2") is not None
    em_falta = [c["label"] for c in relevantes if pdm.get(c["key"]) is None
                and not (ratio_ok and c["key"] in ("lugares_por_fogo", "lugares_por_100m2"))]
    a_confirmar = sorted({i["fonte"]["diploma"] + " — " + i["fonte"]["artigo"]
                          for i in items if i["fonte"]["status"] == "a_confirmar"})
    return {
        "country": COUNTRY,
        "tipo_obra": tipo,
        "tipo_obra_label": TIPOS_OBRA[tipo],
        "quadro": q,
        "pdm": pdm,
        "verificacoes": items,
        "resumo": resumo,
        "parametros_em_falta": em_falta,
        "valores_a_confirmar": a_confirmar,
        "rjue": {"respostas": resp, **{k: rjue[k] for k in ("procedimento", "regra_aplicada", "titulo_regra", "fundamento_legal",
                                                         "tecnicos_obrigatorios", "pecas_necessarias", "avisos",
                                                         "referencias_legais")}},
        "aviso": AVISO,
    }


# ------------------------------------------------------------------ peças do processo ----
PROCEDIMENTO_LABEL = {
    "isento": "Isento de controlo prévio",
    "comunicacao_previa": "Comunicação prévia",
    "licenciamento": "Licença (licenciamento)",
}

# code → (rótulo, origem): auto = gerada pelo ConstruPilot ; upload = a carregar pelo utilizador.
PECAS = {
    "PLANTA_LOCALIZACAO": ("Planta de localização (cartografia municipal / SNIG)", "upload"),
    "LEVANTAMENTO_TOPOGRAFICO": ("Levantamento topográfico", "upload"),
    "PLANTA_IMPLANTACAO": ("Planta de implantação", "auto"),
    "PLANTAS_PISOS": ("Plantas dos pisos e da cobertura", "upload"),
    "CORTES": ("Cortes", "auto"),
    "ALCADOS": ("Alçados", "auto"),
    "AXONOMETRIA": ("Vista axonométrica do volume (complementar)", "auto"),
    "QUADRO_AREAS": ("Quadro de áreas e verificação de parâmetros", "auto"),
    "MEMORIA": ("Memória descritiva e justificativa", "auto"),
    "ESTIMATIVA": ("Estimativa orçamental e calendarização", "auto"),
    "FICHA_ESTATISTICA": ("Ficha de elementos estatísticos (INE)", "auto"),
    "TERMOS_RESPONSABILIDADE": ("Termos de responsabilidade dos técnicos (art.º 10.º do RJUE)", "upload"),
    "FOTOGRAFIAS": ("Fotografias do local", "upload"),
    "INICIO_TRABALHOS": ("Informação sobre o início dos trabalhos (art.º 80.º-A do RJUE)", "upload"),
}


def pecas_exigidas(procedimento: str, tipo: str) -> List[Dict[str, Any]]:
    """Lista indicativa de peças (Portaria n.º 71-A/2024 — confirmar no município)."""
    if procedimento == "isento":
        codes = ["INICIO_TRABALHOS", "FOTOGRAFIAS"]
        if tipo in TIPOS_EDIFICIO:
            codes += ["PLANTA_IMPLANTACAO", "QUADRO_AREAS"]
    else:
        codes = ["PLANTA_LOCALIZACAO", "LEVANTAMENTO_TOPOGRAFICO", "PLANTA_IMPLANTACAO", "CORTES", "ALCADOS",
                 "QUADRO_AREAS", "MEMORIA", "ESTIMATIVA", "TERMOS_RESPONSABILIDADE", "FOTOGRAFIAS"]
        if tipo in TIPOS_EDIFICIO:
            codes.insert(3, "PLANTAS_PISOS")
        if tipo == "piscina":
            codes.remove("ALCADOS")
        if procedimento == "licenciamento":
            codes.append("FICHA_ESTATISTICA")
    out = []
    for c in codes:
        label, origem = PECAS[c]
        if c == "ALCADOS" and tipo == "muro":
            label = "Alçado do muro"
        out.append({"code": c, "label": label, "origem": origem, "required": True})
    if tipo in TIPOS_EDIFICIO:
        label, origem = PECAS["AXONOMETRIA"]
        out.append({"code": "AXONOMETRIA", "label": label, "origem": origem, "required": False})
    return out
