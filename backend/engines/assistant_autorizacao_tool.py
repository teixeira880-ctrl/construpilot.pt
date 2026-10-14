"""Ferramenta do Assistente — autorização de obras para particulares (Lote N3).

Permite ao assistente responder a perguntas como «Preciso de licença para…?» invocando
diretamente o motor de regras do RJUE. Devolve procedimento aplicável + fundamento legal
+ técnicos obrigatórios + checklist de peças + referências legais clicáveis para o PGDL.
"""
from __future__ import annotations

from engines.assistant_workspace import function
from engines.autorizacao_obras_pt.rules import diagnosticar
from engines.autorizacao_obras_pt.dossier import checklist_pecas, estimativa_e_calendario

AUTORIZACAO_TOOLS = [
    function(
        "preparar_autorizacao_obras",
        "Diagnóstico rápido do procedimento de autorização de obras aplicável em Portugal "
        "(RJUE / DL 555/99). Usar sempre que o utilizador perguntar se precisa de licença, "
        "comunicação prévia ou se a obra está isenta. Devolve o procedimento, o fundamento "
        "legal com artigo e URL, os técnicos obrigatórios indicativos e a checklist de peças. "
        "Para uma geração completa do processo, orientar o utilizador para a página "
        "/particulares/autorizacao-obras.",
        {
            "tipo_obra": {
                "type": "string",
                "description": "anexo | muro | interiores | piscina | ampliacao | moradia_nova | outro",
            },
            "altura_m": {"type": "number"},
            "area_implantacao_m2": {"type": "number"},
            "area_construcao_total_m2": {"type": "number"},
            "area_construcao_criada_m2": {"type": "number"},
            "zona_protegida": {"type": "boolean"},
            "imovel_classificado": {"type": "boolean"},
            "confina_via_publica": {"type": "boolean"},
            "altera_fachada": {"type": "boolean"},
            "altera_uso": {"type": "boolean"},
            "altera_cobertura": {"type": "boolean"},
            "tem_edificacao_principal": {"type": "boolean"},
            "tem_pdm_com_parametros": {"type": "boolean"},
            "zona_urbana_consolidada": {"type": "boolean"},
            "subtipo_muro": {"type": "string"},
        },
    ),
]
AUTORIZACAO_TOOL_NAMES = {t["name"] for t in AUTORIZACAO_TOOLS}

AUTORIZACAO_INSTRUCTIONS = (
    "\nAUTORIZAÇÃO DE OBRAS (RJUE / DL 555/99): sempre que o utilizador perguntar se precisa "
    "de licença, comunicação prévia, se a obra é isenta, se o anexo precisa de autorização, "
    "ou pedir ajuda com a câmara municipal, chama preparar_autorizacao_obras com os parâmetros "
    "que já tenhas da conversa (podes passar só o tipo_obra se mais não houver). Apresenta o "
    "procedimento aplicável, o fundamento legal citando o artigo exato e os técnicos obrigatórios. "
    "Convida o utilizador a abrir /particulares/autorizacao-obras para gerar o processo completo. "
    "Para zonas de proteção ou imóveis classificados avisa claramente que as isenções do art.º 6.º-A "
    "não se aplicam (n.º 2 do mesmo artigo) exceto para a substituição de caixilhos para eficiência "
    "energética.\n"
)


async def run_autorizacao_tool(name: str, args: dict, user: dict, conv: dict) -> dict:
    if name != "preparar_autorizacao_obras":
        return {"ok": False, "error": "tool_desconhecida"}
    diag = diagnosticar(args or {})
    cl = checklist_pecas(diag, [])
    est = estimativa_e_calendario(args or {}, diag)
    return {
        "ok": True,
        "procedimento": diag["procedimento"],
        "regra_aplicada": diag["regra_aplicada"],
        "titulo_regra": diag["titulo_regra"],
        "fundamento_legal": diag["fundamento_legal"],
        "tecnicos_obrigatorios": diag["tecnicos_obrigatorios"],
        "referencias_legais": diag["referencias_legais"],
        "checklist": {
            "em_falta": cl["em_falta"],
            "total": cl["total"],
        },
        "estimativa": {
            "custo_min_eur": est["custo_min_eur"],
            "custo_max_eur": est["custo_max_eur"],
            "obra_semanas_min": est["calendario"]["obra_semanas_min"],
            "obra_semanas_max": est["calendario"]["obra_semanas_max"],
        },
        "cta_pagina": "/particulares/autorizacao-obras",
    }
