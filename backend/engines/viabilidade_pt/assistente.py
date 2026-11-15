"""Ferramenta do Assistente BTP — «terreno_viabilidade»: avaliação preliminar da viabilidade construtiva de um terreno
a partir de um terreno guardado, de vértices ou de uma morada (o prédio é procurado na Carta Cadastral da DGT)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from engines.assistant_workspace import function

N = {"type": ["number", "null"]}
S = {"type": ["string", "null"]}

TOOL = function(
    "terreno_viabilidade",
    "Avaliação preliminar da viabilidade construtiva de um terreno em Portugal continental: relevo (altitude, declive, "
    "orientação das vertentes), radiação solar e sombreamento, acessibilidade, riscos naturais (incêndio rural, cheias, "
    "erosão, movimentos de vertente), PDM/REN/RAN/servidões, conforto térmico, potencial construtivo e implantação "
    "recomendada de um edifício. Usar quando o utilizador perguntar se pode construir num terreno, o que o terreno "
    "permite, os riscos ou a melhor implantação. Indicar terreno_id (terreno guardado), OU anel_latlon, OU morada.",
    {
        "terreno_id": S,
        "anel_latlon": {"type": ["array", "null"], "items": {"type": "array", "items": {"type": "number"}}},
        "morada": S,
        "iu_max": N, "io_max_pct": N, "n_pisos_max": N, "altura_fachada_max_m": N,
        "afastamento_frontal_min_m": N, "afastamento_lateral_min_m": N, "afastamento_tardoz_min_m": N,
        "largura_edificio_m": N, "profundidade_edificio_m": N, "n_pisos": N,
    },
)

INSTRUCOES = (
    "\nVIABILIDADE DE TERRENOS: quando o utilizador perguntar se pode construir num terreno, o que lá cabe, os riscos "
    "(incêndio, cheias, erosão, deslizamentos), a REN/RAN/PDM ou a melhor implantação/orientação de uma casa, chama "
    "terreno_viabilidade com o terreno_id (se o terreno estiver guardado em /terrenos), os vértices ou a morada, e os "
    "parâmetros do PDM que o utilizador já tiver dado. Explica a classificação e os fundamentos em linguagem corrente, "
    "cita a fonte de cada dado e diz claramente o que ficou «por confirmar». Nunca inventes índices municipais: se "
    "faltarem, pede-os ou sugere o pedido de informação prévia à câmara. Se o terreno veio da morada sem prédio "
    "cadastrado, avisa que a área analisada é aproximada e convida a desenhar o terreno em /terrenos. O relatório PDF e o "
    "IFC do terreno (para Revit/Archicad) descarregam-se no painel «Viabilidade» da página /terrenos.\n"
)


async def _anel_da_morada(morada: str) -> Dict[str, Any]:
    from engines.urbanismo_pt.auto import geo
    g = await geo.geocode(morada)
    if not g.get("ok"):
        return {"ok": False, "erro": "Morada não encontrada."}
    lat, lon = g["data"]["lat"], g["data"]["lon"]
    try:
        cad = await asyncio.wait_for(geo.cadastro(lat, lon), 30)
    except Exception:  # noqa: BLE001
        cad = {"ok": False}
    if cad.get("ok"):
        return {"ok": True, "anel": [[p[1], p[0]] for p in cad["data"]["anel_lonlat"]], "origem": "Carta Cadastral (DGT)",
                "aproximado": False}
    # sem cadastro geométrico: quadrado de ~600 m² centrado na morada
    from engines.mdt_pt import pttm06 as TM
    x, y = TM.ponto_tm(lat, lon)
    h = 12.5
    anel = [list(TM.ponto_ll(x + dx, y + dy)) for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))]
    return {"ok": True, "anel": anel, "origem": "aproximado à volta da morada (sem prédio cadastrado)", "aproximado": True}


def _resumo(res: Dict[str, Any], origem: Optional[str], aproximado: bool) -> Dict[str, Any]:
    v, rel, sol, o, im = res["viabilidade"], res["relevo"], res["solar"], res["ordenamento"], res["implantacao"]
    return {
        "ok": True, "terreno_origem": origem, "terreno_aproximado": aproximado,
        "area_m2": res["terreno"]["area_m2"], "centroide": res["terreno"]["centroide"],
        "classificacao": v["rotulo"], "indice": v["indice"], "fundamentos": v["fundamentos"],
        "relevo": {k: rel.get(k) for k in ("cota_min", "cota_max", "desnivel", "declive_medio_pct", "declive_max_pct",
                                          "exposicao", "forma_dominante")},
        "mdt": {k: res["mdt"].get(k) for k in ("fonte", "oficial", "resolucao_analise_m")},
        "solar": {"irradiacao_anual_media_kwh_m2": sol["irradiacao_anual_kwh_m2"]["media"],
                  "horas_sol_21dez": sol["horas_sol_21dez"]["media"], "horizonte_sul_graus": sol["horizonte_sul_graus"]},
        "acessibilidade": {k: res["acessibilidade"].get(k) for k in ("estado", "texto", "distancia_m", "via")},
        "riscos": [{"risco": e["risco"], "nivel": e["rotulo"]} for e in res["riscos"]["riscos"]],
        "pdm": o["solo"], "ren_fracao": o["condicionantes"]["ren"]["fracao"], "ran_fracao": o["condicionantes"]["ran"]["fracao"],
        "potencial": {k: o["potencial"].get(k) for k in ("area_livre_para_implantacao_m2", "area_implantacao_max_m2",
                                                        "area_construcao_max_m2", "n_pisos_max", "em_falta")},
        "conforto": {"orientacao": res["conforto"]["orientacao_recomendada"]["texto"],
                     "sobreaquecimento": res["conforto"]["sobreaquecimento"]["nivel"],
                     "ventilacao": res["conforto"]["ventilacao"]["exposicao_vento_dominante"]},
        "implantacao": {k: im.get(k) for k in ("ok", "nota", "largura_m", "profundidade_m", "azimute_fachada_principal",
                                              "cota_soleira_sugerida", "solucao_desnivel", "centro_latlon")},
        "recomendacoes": res["recomendacoes"][:8],
        "pagina": "/terrenos", "aviso": res["aviso_legal"],
    }


async def executar(args: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    from engines.viabilidade_pt import servico as SV
    a = {k: v for k, v in (args or {}).items() if v not in (None, "", [])}
    origem, aprox = None, False
    anel = None
    if a.get("terreno_id"):
        from core.db import db
        d = await db.terrenos.find_one({"terreno_id": a["terreno_id"], "user_id": user["user_id"]}, {"_id": 0, "anel_latlon": 1})
        if not d:
            return {"ok": False, "erro": "Terreno não encontrado na conta do utilizador."}
        anel, origem = d["anel_latlon"], "terreno guardado"
    elif a.get("anel_latlon"):
        anel, origem = a["anel_latlon"], "vértices indicados"
    elif a.get("morada"):
        m = await _anel_da_morada(a["morada"])
        if not m["ok"]:
            return m
        anel, origem, aprox = m["anel"], m["origem"], m["aproximado"]
    else:
        return {"ok": False, "erro": "Indique o terreno: terreno_id, vértices ou morada."}
    pdm = {k: a[k] for k in ("iu_max", "io_max_pct", "n_pisos_max", "altura_fachada_max_m", "afastamento_frontal_min_m",
                             "afastamento_lateral_min_m", "afastamento_tardoz_min_m") if k in a}
    ed = {"largura_m": a.get("largura_edificio_m"), "profundidade_m": a.get("profundidade_edificio_m"), "n_pisos": a.get("n_pisos")}
    try:
        res = await asyncio.wait_for(SV.avaliar(anel, pdm, ed), timeout=150)
    except SV.ViabilidadeErro as e:
        return {"ok": False, "erro": str(e)}
    except asyncio.TimeoutError:
        return {"ok": False, "erro": "Os serviços de dados oficiais estão lentos; tente de novo dentro de momentos."}
    return _resumo(res, origem, aprox)
