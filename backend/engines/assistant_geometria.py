"""Ferramentas do Assistente BTP (e, através dele, da Aurora) para a geometria v3 das plantas.

As ferramentas chamam as MESMAS funções que o ecrã (`routes/plans_geometria`): ler, aplicar e corrigir dão exatamente o
mesmo resultado, com as mesmas regras (escala por consenso, só divisões automáticas substituídas, correções guardadas).
"""
from __future__ import annotations

from engines.assistant_workspace import function

S = {"type": "string"}
PAG = {"type": "integer", "minimum": 0, "description": "Índice de página 0-based (primeira página = 0)"}

GEOMETRIA_TOOLS = [
    function("ler_geometria_planta",
             "Lê automaticamente a geometria REAL de uma página de planta importada (plan_…), sem IA: divisões fechadas pelas paredes "
             "(nome, área, perímetro), escala por consenso de várias fontes, paredes exteriores ao eixo e divisórias por espessura, "
             "portas e janelas, e a confiança de cada divisão (verde = confirmada, laranja = a verificar, vermelho = incoerente) com "
             "os motivos. Usar SEMPRE primeiro quando o utilizador pede áreas, divisões, medições ou paredes de uma planta. "
             "Funciona com DWG/DXF, PDF vetorial e imagens/digitalizações.",
             {"plan_id": S, "page_index": PAG}),
    function("aplicar_geometria_planta",
             "Passa as divisões lidas por ler_geometria_planta para as medições da planta (separador Divisões), com a fórmula da app. "
             "divisoes = lista de ids D01, D02… (lista vazia = todas). Só substitui divisões criadas antes por esta leitura; as "
             "desenhadas à mão ficam intactas. Recusado se a escala estiver em conflito ou desconhecida.",
             {"plan_id": S, "page_index": PAG, "divisoes": {"type": "array", "items": S, "maxItems": 500}}),
    function("corrigir_geometria_planta",
             "Regista uma correção do utilizador sobre a leitura automática (fica guardada para melhorar as próximas leituras). "
             "tipo: falta (divisão em falta), nao_existe, forma_errada, mal_identificado (nome), area_errada, escala_errada. "
             "Usar quando o utilizador diz que uma área, um nome ou um contorno está errado; não altera as medições sozinho.",
             {"plan_id": S, "page_index": PAG,
              "tipo": {"type": "string", "enum": ["falta", "nao_existe", "forma_errada", "mal_identificado", "area_errada", "escala_errada"]},
              "divisao_id": {"type": ["string", "null"]}, "nome_correto": {"type": ["string", "null"]},
              "area_correta_m2": {"type": ["number", "null"]}, "comentario": {"type": ["string", "null"]}}),
]
GEOMETRIA_TOOL_NAMES = {t["name"] for t in GEOMETRIA_TOOLS}

GEOMETRIA_INSTRUCTIONS = """
GEOMETRIA DAS PLANTAS (motor geometria-v3, determinístico) : para áreas de divisões, área útil, implantação, paredes ou vãos de
uma planta importada, usa PRIMEIRO ler_geometria_planta (cada página). Diz a confiança como ela vem : verde = confirmada, laranja =
a verificar (diz o motivo), vermelho = incoerente (diz o motivo e o que falta). Se a escala vier « fonte_unica » ou « conflito »,
di-lo e propõe calibrar com uma cota conhecida. Quando o utilizador quer medir/orçamentar a partir da planta, ou pede para
« aplicar », « meter nas medições », usa aplicar_geometria_planta e confirma quantas divisões entraram. Se o utilizador corrigir
um valor (« a sala tem 25 m² », « isto não é uma divisão »), regista-o com corrigir_geometria_planta e, se for preciso, volta a ler.
Nunca inventes uma área : se uma divisão não foi lida, diz que falta e propõe traçá-la ou registar « falta »."""


def _resumo(res: dict) -> dict:
    """Resposta compacta para o modelo: tudo o que é preciso para explicar, sem os polígonos em píxeis."""
    esc = res.get("escala") or {}
    return {"ok": res.get("ok", False), "motivo": res.get("motivo"), "fonte": res.get("fonte"), "page_index": res.get("page_index"),
            "escala": {"estado": esc.get("estado"), "fontes": esc.get("fontes"), "mensagem": esc.get("mensagem")},
            "area_util_m2": res.get("area_util_m2"), "area_implantacao_m2": res.get("area_implantacao_m2"),
            "paredes": res.get("paredes"), "vaos": res.get("vaos"), "verificacoes": res.get("verificacoes"),
            "confianca": res.get("confianca"),
            "divisoes": [{k: d.get(k) for k in ("id", "nome", "nome_lido", "area_m2", "perimetro_m", "area_escrita_m2", "nivel", "motivos")}
                         for d in res.get("divisoes") or []],
            "ecra": f"/plan?open={res.get('plan_id')}&tab=divisoes&page={res.get('page_index') or 0}",
            "ecra_nota": "Abre a planta no separador « Divisões »: as divisões aparecem coloridas pela confiança."}


async def execute(name: str, args: dict, user: dict) -> dict:
    from fastapi import HTTPException
    from routes import plans_geometria as PG
    try:
        if name == "ler_geometria_planta":
            return _resumo(await PG.analisar(args["plan_id"], int(args["page_index"]), user))
        if name == "aplicar_geometria_planta":
            return await PG.aplicar(args["plan_id"], PG.AplicarIn(page_index=args["page_index"], divisoes=args.get("divisoes") or []), user)
        if name == "corrigir_geometria_planta":
            body = PG.CorrecaoIn(page_index=args["page_index"], tipo=args["tipo"], divisao_id=args.get("divisao_id"),
                                 nome_correto=args.get("nome_correto"), area_correta_m2=args.get("area_correta_m2"),
                                 comentario=args.get("comentario"))
            return await PG.corrigir(args["plan_id"], body, user)
    except HTTPException as exc:
        return {"ok": False, "error": str(exc.detail)}
    except ValueError as exc:      # validação pydantic (valores fora dos limites)
        return {"ok": False, "error": f"Parâmetros inválidos: {exc}"}
    return {"ok": False, "error": "Ferramenta desconhecida"}
