"""Ferramenta do Assistente — autorização de obras para particulares (Lote N3).

Permite ao assistente responder a perguntas como «Preciso de licença para…?» invocando
diretamente o motor de regras do RJUE. Devolve procedimento aplicável + fundamento legal
+ técnicos obrigatórios + checklist de peças + referências legais clicáveis para o PGDL.
"""
from __future__ import annotations

import asyncio

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
# Lote 111 — piloto automático: de uma frase e uma morada ao processo completo, verificado.
AUTORIZACAO_TOOLS += [
    function(
        "licenciamento_automatico",
        "Faz SOZINHO, de 0 a 100 %, o processo de autorização de construção de uma moradia em Portugal a partir de uma morada: "
        "localiza o terreno, lê o PDM (CRUS da DGT), as servidões (REN/RAN…), a altimetria e o ortofotomapa, implanta a casa e a "
        "garagem da melhor forma (sol, declive, afastamentos), desenha as plantas, cortes, alçados, planta de localização e "
        "topografia indicativa, calcula o quadro de áreas, verifica PDM/RGEU/RJUE, redige a memória descritiva e confirma que "
        "todos os motores dão os mesmos números. Usar sempre que pedirem uma autorização/licença/projeto de uma casa numa "
        "morada. Passar só o que o utilizador disse; o resto é assumido de forma prudente e devolvido em «pressupostos».",
        {
            "texto": {"type": "string", "description": "O pedido do utilizador, palavra por palavra."},
            "morada": {"type": "string", "description": "Rua, número, freguesia, concelho (se já identificada)."},
            "tipologia": {"type": "string", "description": "T0..T6 (por omissão T3)."},
            "pisos": {"type": "integer", "description": "1 (térrea) ou 2."},
            "garagem": {"type": "boolean"},
            "lugares": {"type": "integer", "description": "Lugares de garagem (0-3)."},
            "fachada": {"type": "string", "description": "granito, madeira, xisto, tijolo, betão, reboco branco, misto…"},
            "area_terreno_m2": {"type": "number", "description": "Área do terreno (caderneta)."},
            "frente_m": {"type": "number", "description": "Largura da frente do terreno, se souber."},
            "requerente_nome": {"type": "string"}, "requerente_nif": {"type": "string"},
            "artigo_matricial": {"type": "string"},
        },
    ),
    function(
        "licenciamento_atualizar",
        "Atualiza um processo do piloto automático com as respostas do utilizador (área real do terreno, tipologia, pisos, "
        "garagem, requerente, artigo matricial…) e recalcula TUDO a partir dos mesmos dados.",
        {"processo_id": {"type": "string"}, "tipologia": {"type": "string"}, "pisos": {"type": "integer"},
         "garagem": {"type": "boolean"}, "lugares": {"type": "integer"}, "area_terreno_m2": {"type": "number"},
         "frente_m": {"type": "number"}, "requerente_nome": {"type": "string"}, "requerente_nif": {"type": "string"},
         "artigo_matricial": {"type": "string"}, "fachada": {"type": "string"}},
    ),
    function(
        "licenciamento_materiais",
        "Muda os materiais da casa de um processo automático (fachada: granito, madeira, xisto, tijolo, betão, reboco branco, "
        "misto granito/reboco, misto madeira/reboco; cobertura: telha_ceramica, telha_preta, zinco, plana_seixo; caixilharia: "
        "aluminio_antracite, aluminio_branco, madeira, pvc_branco). O 3D, a memória e o render seguem a escolha.",
        {"processo_id": {"type": "string"}, "fachada": {"type": "string"}, "cobertura": {"type": "string"},
         "caixilharia": {"type": "string"}},
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
    "LICENCIAMENTO AUTOMÁTICO (0-100 %): quando alguém pedir uma autorização/licença/projeto para construir uma casa numa "
    "morada (mesmo em linguagem simples, p. ex. «quero uma autorização de construção na Rua do Monte 7, Braga»), chama "
    "licenciamento_automatico IMEDIATAMENTE com o texto e o que já souberes — não faças perguntas antes. Depois explica em "
    "linguagem corrente: procedimento (licença ou comunicação prévia), a casa proposta, as decisões (sol, garagem, declive), "
    "as hipóteses assumidas e faz no máximo 2 ou 3 perguntas simples das «perguntas» devolvidas (área da caderneta, nome do "
    "requerente…). Quando responderem, usa licenciamento_atualizar. Para «quero a fachada em granito/madeira…» usa "
    "licenciamento_materiais. Nunca inventes números: usa só os devolvidos pela ferramenta. Se o estado for «inviavel» "
    "(solo rústico, REN/RAN), explica o impedimento com honestidade e sugere o pedido de informação prévia à câmara. "
    "Diz sempre que o levantamento topográfico, os projetos de especialidades e a assinatura de arquiteto/engenheiros "
    "(termos de responsabilidade) são obrigatórios, e que a página do processo permite pedir essa subscrição.\n"
)


def _pedido(args: dict) -> dict:
    a = {k: v for k, v in (args or {}).items() if v not in (None, "")}
    req = {}
    if a.get("requerente_nome"):
        req["nome"] = a.pop("requerente_nome")
    if a.get("requerente_nif"):
        req["nif"] = a.pop("requerente_nif")
    if req:
        a["requerente"] = req
    return a


async def run_autorizacao_tool(name: str, args: dict, user: dict, conv: dict) -> dict:
    if name in ("licenciamento_automatico", "licenciamento_atualizar", "licenciamento_materiais"):
        from routes import urbanismo_auto as UA
        try:
            if name == "licenciamento_automatico":
                return await asyncio.wait_for(UA.executar_e_gravar(_pedido(args), user), timeout=240)
            pid = (args or {}).get("processo_id") or ""
            if name == "licenciamento_materiais":
                return await UA.materiais(pid, UA.MateriaisIn(**{k: args.get(k) for k in ("fachada", "cobertura", "caixilharia")}), user)
            d = await UA._owned(pid, user["user_id"])
            pedido = {**(d["auto"].get("pedido") or {}), **{k: v for k, v in _pedido(args).items() if k != "processo_id"}}
            pedido["requerente"] = {**(d.get("requerente") or {}), **(pedido.get("requerente") or {})}
            return await asyncio.wait_for(UA.executar_e_gravar(pedido, user, pid=pid), timeout=240)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "Os serviços de dados oficiais estão lentos; tente de novo dentro de momentos."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(getattr(e, "detail", e))[:300]}
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
