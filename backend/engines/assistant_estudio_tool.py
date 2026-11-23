"""Ferramentas do Assistente — Estúdio de Projeto (modelo único do edifício de um processo de licenciamento).

estudio_ver     → estado do modelo (pisos, divisões, paredes exteriores com identificadores, mapa de vãos, acabamentos, totais)
estudio_editar  → aplica operações (sala, parede, vão, materiais, divisão, cobertura, pisos, escada, objeto…) e guarda

Os números devolvidos saem todos da geometria do modelo; a ferramenta nunca estima.
"""
from __future__ import annotations

import json

from engines.assistant_workspace import function

ESTUDIO_TOOLS = [
    function(
        "estudio_ver",
        "Lê o Estúdio de Projeto de um processo de licenciamento automático: pisos, divisões com áreas e acabamentos, paredes "
        "exteriores (com identificador e coordenadas em metros), mapa de vãos, escadas, cobertura, totais, erros e avisos. "
        "Usar antes de editar, para conhecer os identificadores e as coordenadas.",
        {"processo_id": {"type": "string"}},
    ),
    function(
        "estudio_editar",
        "Altera o Estúdio de Projeto de um processo e guarda. «operacoes_json» é uma lista JSON de operações aplicadas por ordem. "
        "Coordenadas em metros (x ao longo da frente, y para o tardoz; ver «limites_xy» em estudio_ver). Operações: "
        '{"op":"sala","x0":,"y0":,"x1":,"y1":,"nome":"Quarto","piso":0} · '
        '{"op":"parede","a":[x,y],"b":[x,y],"tipo":"int_12"} · {"op":"remover_parede","id":"w7"} · '
        '{"op":"tipo_parede","de":"exteriores"|"interiores"|"w3","tipo":"nome ou id do tipo"} · '
        '{"op":"vao","tipo":"janela|porta|portada|portao","lado":"frente|tardoz|esquerda|direita" ou "parede":"w1","pos_m":,"largura_m":,"altura_m":,"peitoril_m":} · '
        '{"op":"mudar_vao","id":"v3","largura_m":1.6} · {"op":"remover_vao","id":"v3"} · '
        '{"op":"cobertura","tipo":"plana|uma_agua|duas_aguas|quatro_aguas","inclinacao_graus":25} · '
        '{"op":"materiais","fachada":"granito","cobertura":"zinco","caixilharia":"madeira","pavimento":"carvalho","parede_interior":"…","teto":"…"} · '
        '{"op":"divisao","nome":"Cozinha","pavimento":"cerâmico","parede_interior":"azulejo","novo_nome":"Copa"} · '
        '{"op":"piso_adicionar"} · {"op":"piso_remover"} · {"op":"pe_direito","piso":0,"valor":2.7} · '
        '{"op":"escada","piso":0,"tipo":"u|l|reta","x":,"y":} ou "divisao":"Escada" · {"op":"remover_escada","id":"e1"} · '
        '{"op":"objeto","tipo":"sofá","divisao":"Sala"} ou "x":,"y":,"rot": · {"op":"remover_objeto","id":"o2"} · '
        '{"op":"nota","x":,"y":,"texto":"…"}. Devolve o que foi feito, o que falhou (com o motivo) e o novo resumo.',
        {"processo_id": {"type": "string"}, "operacoes_json": {"type": "string", "description": "Lista JSON de operações."}},
    ),
]
ESTUDIO_TOOL_NAMES = {t["name"] for t in ESTUDIO_TOOLS}

ESTUDIO_INSTRUCTIONS = (
    "ESTÚDIO DE PROJETO: quando o utilizador pedir para mudar a casa de um processo de licenciamento (acrescentar ou tirar "
    "uma parede, uma divisão, uma janela, uma porta, mudar materiais de uma divisão ou da casa, a cobertura, um piso, uma "
    "escada, mobilar), chama estudio_ver para conheceres o modelo e depois estudio_editar com as operações. Diz ao utilizador "
    "exatamente o que a ferramenta devolveu em «feitos» e «falhas», com as áreas do novo resumo, e que pode ver e continuar a "
    "editar no cartão «Estúdio de Projeto» da página do processo. Nunca inventes medidas: usa só as devolvidas. O Estúdio não "
    "altera as peças do licenciamento; se houver diferenças, o utilizador vê-as em «Diferenças para o processo».\n"
)


async def run_estudio_tool(name: str, args: dict, user: dict, conv: dict) -> dict:
    from routes import estudio_projeto as RE
    pid = (args or {}).get("processo_id") or ""
    try:
        if name == "estudio_ver":
            return {"ok": True, **(await RE.ver_resumo(pid, user["user_id"])), "pagina": f"/licenciamento-automatico/{pid}"}
        try:
            ops = json.loads((args or {}).get("operacoes_json") or "[]")
        except ValueError:
            return {"ok": False, "error": "operacoes_json não é JSON válido."}
        if isinstance(ops, dict):
            ops = [ops]
        if not isinstance(ops, list) or not ops or len(ops) > 60:
            return {"ok": False, "error": "Indique entre 1 e 60 operações."}
        r = await RE.aplicar_operacoes(pid, user["user_id"], ops)
        return {"ok": r["ok"], "feitos": r["feitos"], "falhas": r["falhas"], "guardado": bool(r["updated_at"]), "resumo": r["resumo"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(getattr(e, "detail", e))[:300]}
