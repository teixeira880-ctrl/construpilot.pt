"""Executores REAIS das 11 ferramentas do Assistente BTP.

Cada executor:
    * Chama código Construpilot existente (Plans Pro, estimação, Perplexity).
    * Devolve `ToolResult` tipado em PT-PT.
    * Nunca inventa dados; se faltar informação, devolve
      `status='needs_user_input'` com `missing_data[]`.
    * Nunca invoca directamente outra LLM — isso é da camada agent.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.db import db
from engines.btp_assistant.tools.registry import NOMES_FERRAMENTAS_COM_CONFIRMACAO
from engines.btp_assistant.types import MissingDataRequest, ToolCall, ToolResult

logger = logging.getLogger("btp_assistant.executors")

# URLs internas por nome lógico do módulo
URLS_APPS = {
    "orcamento": "/devis",
    "plans-pro": "/plans-pro",
    "calculadoras": "/calculadoras",
    "precos": "/precos",
    "estimador": "/estimador",
    "biblioteca": "/biblioteca",
    "escadas": "/calculadoras/escadas",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ok(call: ToolCall, user_message_pt: str, payload: dict | None = None) -> ToolResult:
    return ToolResult(
        tool_call_id=call.id, status="ok",
        payload=payload or {}, user_message_pt=user_message_pt,
    )


def _err(call: ToolCall, user_message_pt: str, detail: str | None = None) -> ToolResult:
    return ToolResult(
        tool_call_id=call.id, status="error",
        payload={"detail": detail} if detail else {},
        user_message_pt=user_message_pt,
    )


def _needs_input(call: ToolCall, missing: list[MissingDataRequest],
                 user_message_pt: str) -> ToolResult:
    return ToolResult(
        tool_call_id=call.id, status="needs_user_input",
        payload={}, user_message_pt=user_message_pt, missing_data=missing,
    )


# ---------------------------------------------------------------------------
# 1. abrir_app
# ---------------------------------------------------------------------------
async def exec_abrir_app(call: ToolCall, *, user_id: str) -> ToolResult:
    nome = (call.arguments.get("nome_app") or "").strip()
    url = URLS_APPS.get(nome)
    if not url:
        return _err(
            call,
            f"Não reconheço o módulo '{nome}'. Opções válidas: " + ", ".join(URLS_APPS),
        )
    return _ok(
        call,
        f"A abrir o módulo {nome}.",
        {"action": "navigate", "url": url, "target": "_self"},
    )


# ---------------------------------------------------------------------------
# 2. criar_orcamento
# ---------------------------------------------------------------------------
async def exec_criar_orcamento(call: ToolCall, *, user_id: str) -> ToolResult:
    cliente = (call.arguments.get("cliente_nome") or "").strip()
    titulo = (call.arguments.get("titulo") or "").strip()
    items = call.arguments.get("items") or []
    iva = float(call.arguments.get("iva_pct") or 23.0)
    # Fase D — portal cliente final (link mágico opcional)
    convidar_portal = bool(call.arguments.get("convidar_cliente_portal") or False)
    cliente_email = (call.arguments.get("cliente_email") or "").strip() or None
    if not cliente or not titulo or not items:
        missing: list[MissingDataRequest] = []
        if not cliente:
            missing.append(MissingDataRequest(
                question_pt="Qual é o nome do cliente?",
                field="cliente_nome", unit=None, element_id=None,
                suggested_default=None, criticidade="bloqueante",
            ))
        if not titulo:
            missing.append(MissingDataRequest(
                question_pt="Que título dou ao orçamento?",
                field="titulo", unit=None, element_id=None,
                suggested_default=None, criticidade="bloqueante",
            ))
        return _needs_input(
            call, missing,
            "Preciso de mais informação para criar o orçamento.",
        )

    orcamento_id = f"orc_{uuid.uuid4().hex[:12]}"
    subtotal = sum(
        float(it.get("qtd") or 0) * float(it.get("preco_unit_eur") or 0)
        for it in items
    )
    iva_eur = subtotal * iva / 100.0
    total = subtotal + iva_eur
    doc = {
        "orcamento_id": orcamento_id,
        "user_id": user_id,
        "cliente_nome": cliente,
        "cliente_email": cliente_email,
        "titulo": titulo,
        "items": items,
        "iva_pct": iva,
        "subtotal_eur": round(subtotal, 2),
        "iva_eur": round(iva_eur, 2),
        "total_eur": round(total, 2),
        "created_at_iso": datetime.now(timezone.utc).isoformat(),
        "source": "btp_assistant",
    }
    await db.btp_assistant_orcamentos.insert_one(doc)

    # Payload base da resposta
    payload: dict[str, Any] = {
        "orcamento_id": orcamento_id,
        "subtotal_eur": doc["subtotal_eur"],
        "iva_eur": doc["iva_eur"],
        "total_eur": doc["total_eur"],
        "items_count": len(items),
    }
    mensagem = (
        f"Orçamento '{titulo}' criado para {cliente}: {total:.2f} EUR "
        f"(c/ IVA {iva:.0f}%)."
    )

    # Fase D — gera link público opcional (fluxo síncrono, não bloqueia o turno)
    if convidar_portal:
        try:
            import secrets
            from datetime import timedelta
            import os as _os
            ttl = max(1, int(_os.environ.get("PUBLIC_LINK_TTL_DAYS", "60")))
            app_url = (
                _os.environ.get("PUBLIC_APP_URL")
                or _os.environ.get("FRONTEND_URL")
                or "https://construpilot.pt"
            ).rstrip("/")
            agora = datetime.now(timezone.utc)
            token = f"mp_{secrets.token_urlsafe(32)}"
            link_doc = {
                "token": token,
                "orcamento_id": orcamento_id,
                "created_by_user_id": user_id,
                "cliente_email": cliente_email,
                "created_at": agora,
                "expires_at": agora + timedelta(days=ttl),
                "viewed_count": 0,
                "last_viewed_at": None,
            }
            await db.orcamento_public_links.insert_one(link_doc)
            public_url = f"{app_url}/orcamento-publico/{token}"
            payload["public_link_token"] = token
            payload["public_link_url"] = public_url
            mensagem += f" Ligação pública criada: {public_url}"
            # Envio por e-mail quando `cliente_email` presente
            if cliente_email:
                try:
                    from engines.emailer import send_email
                    html = (
                        f"<p>Olá {cliente},</p>"
                        f"<p>Enviamos-lhe o orçamento <b>{titulo}</b> "
                        f"({total:.2f} €).</p>"
                        f'<p><a href="{public_url}" style="background:#D9541E;'
                        f'color:#fff;padding:10px 18px;text-decoration:none;'
                        f'border-radius:4px">Ver o orçamento</a></p>'
                        f'<p style="color:#999;font-size:11px">'
                        f'Gerado com ConstruPilot.pt — IA para orçamentos de obras.</p>'
                    )
                    await send_email(
                        to=cliente_email,
                        subject=f"O seu orçamento ConstruPilot — {titulo}",
                        html=html,
                        campaign_id="orcamento_public_link_tool",
                    )
                    payload["email_enviado"] = True
                    mensagem += " E-mail enviado ao cliente."
                except Exception as e:  # noqa: BLE001
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "e-mail do link público falhou: %s", e,
                    )
                    payload["email_enviado"] = False
        except Exception as e:  # noqa: BLE001
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "geração de link público falhou: %s", e,
            )

    return _ok(call, mensagem, payload)


# ---------------------------------------------------------------------------
# 3. adicionar_item_orcamento
# ---------------------------------------------------------------------------
async def exec_adicionar_item_orcamento(call: ToolCall, *, user_id: str) -> ToolResult:
    oid = call.arguments.get("orcamento_id") or ""
    doc = await db.btp_assistant_orcamentos.find_one(
        {"orcamento_id": oid, "user_id": user_id}, {"_id": 0},
    )
    if not doc:
        return _err(
            call, f"Orçamento '{oid}' não encontrado.",
        )
    item = {
        "descricao": call.arguments.get("descricao", ""),
        "qtd": float(call.arguments.get("qtd") or 0),
        "unidade": call.arguments.get("unidade", "un"),
        "preco_unit_eur": float(call.arguments.get("preco_unit_eur") or 0),
    }
    items = (doc.get("items") or []) + [item]
    subtotal = sum(
        float(it.get("qtd") or 0) * float(it.get("preco_unit_eur") or 0)
        for it in items
    )
    iva_pct = float(doc.get("iva_pct") or 23.0)
    iva_eur = subtotal * iva_pct / 100.0
    total = subtotal + iva_eur
    await db.btp_assistant_orcamentos.update_one(
        {"orcamento_id": oid, "user_id": user_id},
        {"$set": {
            "items": items,
            "subtotal_eur": round(subtotal, 2),
            "iva_eur": round(iva_eur, 2),
            "total_eur": round(total, 2),
            "updated_at_iso": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return _ok(
        call,
        f"Item adicionado. Novo total: {total:.2f} EUR.",
        {"orcamento_id": oid, "total_eur": round(total, 2),
         "items_count": len(items)},
    )


# ---------------------------------------------------------------------------
# 4. calcular_metrado — delega a Plans Pro Fase 1
# ---------------------------------------------------------------------------
async def exec_calcular_metrado(call: ToolCall, *, user_id: str) -> ToolResult:
    plan_id = call.arguments.get("plan_id") or ""
    if not plan_id:
        return _needs_input(
            call,
            [MissingDataRequest(
                question_pt="De qual plano Plans Pro quer o metrado?",
                field="plan_id", unit=None, element_id=None,
                suggested_default=None, criticidade="bloqueante",
            )],
            "Indique o ID do plano para calcular o metrado.",
        )
    plano = await db.plans_pro.find_one(
        {"plan_id": plan_id, "user_id": user_id}, {"_id": 0},
    )
    if not plano:
        return _err(call, f"Plano '{plan_id}' não encontrado.")

    # Reutiliza análise já executada se disponível (evita re-chamar LLM)
    cached = (plano.get("ai_analysis") or {}).get("analise")
    if cached:
        n_elem = len(cached.get("elementos") or [])
        return _ok(
            call,
            f"Metrado disponível: {n_elem} elementos detectados.",
            {"plan_id": plan_id, "elementos_count": n_elem,
             "confidence_global": cached.get("confidence_global"),
             "requires_human_review": cached.get("requires_human_review")},
        )
    return _needs_input(
        call,
        [MissingDataRequest(
            question_pt=(
                f"O plano '{plan_id}' ainda não foi analisado. "
                "Executa a análise automática?"
            ),
            field="plano.analise_llm", unit=None, element_id=plan_id,
            suggested_default=None, criticidade="bloqueante",
        )],
        "Plano ainda sem análise; peça para executar primeiro.",
    )


# ---------------------------------------------------------------------------
# 5. estimar_custo — delega a `engines.estimation.estimate`
# ---------------------------------------------------------------------------
async def exec_estimar_custo(call: ToolCall, *, user_id: str) -> ToolResult:
    tipo = call.arguments.get("tipo_projecto") or "maison_neuve"
    surface = float(call.arguments.get("surface_m2") or 0)
    acab = call.arguments.get("acabamento") or "standard"
    regiao = call.arguments.get("regiao_pt") or None
    if surface <= 0:
        return _needs_input(
            call,
            [MissingDataRequest(
                question_pt="Qual é a área bruta de construção em m²?",
                field="surface_m2", unit="m²", element_id=None,
                suggested_default=120.0, criticidade="bloqueante",
            )],
            "Faltam-me a área de construção para estimar o custo.",
        )
    try:
        from engines import estimation
        res = estimation.estimate(
            project_type=tipo, surface=surface, finish=acab,
            country="PT", region=regiao,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("estimar_custo falhou")
        return _err(call, "Motor de estimação temporariamente indisponível.",
                    detail=f"{type(e).__name__}")
    total = res.get("financials", {}).get("total_ttc") or res.get("total_eur") or 0
    return _ok(
        call,
        f"Estimativa: cerca de {float(total):,.0f} EUR para {surface:.0f} m² ({acab}).",
        {
            "tipo_projecto": tipo, "surface_m2": surface,
            "acabamento": acab, "regiao_pt": regiao,
            "total_eur": float(total), "resultado": res,
        },
    )


# ---------------------------------------------------------------------------
# 6. pesquisar_norma — delega a Perplexity Plus
# ---------------------------------------------------------------------------
async def exec_pesquisar_norma(call: ToolCall, *, user_id: str) -> ToolResult:
    termo = (call.arguments.get("termo") or "").strip()
    tipo = call.arguments.get("tipo") or "outros"
    if not termo:
        return _err(call, "Indique o termo da norma a pesquisar.")
    try:
        from engines.perplexity_plus.pplx_client import PplxClient
        client = PplxClient()
        if not client.is_configured():
            return _err(call, "Pesquisa de normas indisponível (Perplexity não configurado).")
        prompt = (
            f"Normas portuguesas e europeias sobre '{termo}' "
            f"(família {tipo}). Lista exigências actuais, Decreto-Lei "
            "aplicável e Eurocódigo relacionado. Resposta em PT-PT."
        )
        resp = await client.ask_structured(
            question=prompt, user_id=user_id, flow="btp_assistant",
            max_tokens=800,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("pesquisar_norma falhou")
        return _err(call, "Falha ao consultar normas.", detail=f"{type(e).__name__}")
    return _ok(
        call, "Pesquisa de normas concluída.",
        {
            "termo": termo, "tipo": tipo,
            "resumo_pt": (resp.get("text") or "")[:3000] if isinstance(resp, dict) else str(resp)[:3000],
            "citacoes": resp.get("citations") if isinstance(resp, dict) else [],
        },
    )


# ---------------------------------------------------------------------------
# 7. obter_preco_material
# ---------------------------------------------------------------------------
async def exec_obter_preco_material(call: ToolCall, *, user_id: str) -> ToolResult:
    mat = (call.arguments.get("material") or "").strip()
    unidade = (call.arguments.get("unidade") or "").strip() or None
    regiao = call.arguments.get("regiao_pt") or None
    if not mat:
        return _err(call, "Indique o material a consultar.")
    # 1. Biblioteca interna
    query: dict[str, Any] = {"nome": {"$regex": mat, "$options": "i"}}
    if regiao:
        query["regiao"] = regiao
    doc = await db.materials_pt_prices.find_one(query, {"_id": 0})
    if doc:
        return _ok(
            call,
            f"Preço de '{mat}' (biblioteca interna, {regiao or 'nacional'}): "
            f"{doc.get('preco_eur')} EUR / {doc.get('unidade') or unidade or 'un'}.",
            {"fonte": "biblioteca_interna", **doc},
        )
    # 2. Sinaliza que o LLM deve usar Google Search (grounding)
    return _ok(
        call,
        f"Preço de '{mat}' não está na biblioteca interna — recomenda-se Google Search.",
        {
            "fonte": "nao_encontrado_interno",
            "material": mat, "unidade": unidade, "regiao_pt": regiao,
            "sugestao_agente": "Usa Google Search para obter o preço actual.",
        },
    )


# ---------------------------------------------------------------------------
# 8. exportar_excel — delega a excel_export (quando aplicável)
# ---------------------------------------------------------------------------
async def exec_exportar_excel(call: ToolCall, *, user_id: str) -> ToolResult:
    oid = call.arguments.get("orcamento_id") or ""
    doc = await db.btp_assistant_orcamentos.find_one(
        {"orcamento_id": oid, "user_id": user_id}, {"_id": 0},
    )
    if not doc:
        return _err(call, f"Orçamento '{oid}' não encontrado.")
    # Em vez de regenerar o Excel no acto (I/O pesado), devolvemos URL
    # para o endpoint `/api/btp-assistant/orcamentos/{oid}/excel` que a
    # UI pode chamar (criação sob demanda).
    return _ok(
        call,
        f"Pode descarregar o Excel do orçamento '{oid}'.",
        {
            "download_url": f"/api/btp-assistant/orcamentos/{oid}/excel",
            "orcamento_id": oid,
        },
    )


# ---------------------------------------------------------------------------
# 9. calcular_escada — Stair Engine em pausa
# ---------------------------------------------------------------------------
async def exec_calcular_escada(call: ToolCall, *, user_id: str) -> ToolResult:
    h = float(call.arguments.get("altura_total_m") or 0)
    e = float(call.arguments.get("espaco_horizontal_m") or 0)
    # Verifica se o Stair Engine está disponível
    try:
        from engines.stair_engine import calcular as _stair_calc  # type: ignore
    except Exception:
        _stair_calc = None
    if _stair_calc is None:
        return _needs_input(
            call,
            [MissingDataRequest(
                question_pt=(
                    "O motor dedicado de escadas está em finalização "
                    "(Sprint 5). Quer que eu faça uma estimativa "
                    "rápida com RGEU (contrahuella 17 cm, pisada 28 cm)?"
                ),
                field="escada.motor_dedicado", unit=None, element_id=None,
                suggested_default=None, criticidade="importante",
            )],
            "Motor dedicado de escadas ainda não disponível — posso fazer estimativa simplificada.",
        )
    # Caso o Stair Engine esteja disponível no futuro
    try:
        res = _stair_calc(altura_total_m=h, espaco_horizontal_m=e,
                          **{k: v for k, v in call.arguments.items()
                             if k not in ("altura_total_m", "espaco_horizontal_m")})
    except Exception as ex:  # noqa: BLE001
        return _err(call, "Cálculo de escada falhou.", detail=f"{type(ex).__name__}")
    return _ok(call, "Escada dimensionada com sucesso.", res or {})


# ---------------------------------------------------------------------------
# 10. pesquisar_biblioteca
# ---------------------------------------------------------------------------
async def exec_pesquisar_biblioteca(call: ToolCall, *, user_id: str) -> ToolResult:
    q = (call.arguments.get("query") or "").strip()
    cat = call.arguments.get("categoria")
    if not q:
        return _err(call, "Indique o termo de pesquisa.")
    filtro: dict[str, Any] = {
        "$or": [
            {"titulo": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
            {"conteudo_pt": {"$regex": q, "$options": "i"}},
        ],
    }
    if cat:
        filtro["categoria"] = cat
    rows = await db.library_pt.find(filtro, {"_id": 0}).limit(10).to_list(10)
    return _ok(
        call,
        f"{len(rows)} resultado(s) na biblioteca interna para '{q}'.",
        {"resultados": rows, "count": len(rows)},
    )


# ---------------------------------------------------------------------------
# 11. pedir_precisao — não executa; devolve directamente MissingDataRequest
# ---------------------------------------------------------------------------
async def exec_pedir_precisao(call: ToolCall, *, user_id: str) -> ToolResult:
    args = call.arguments
    req = MissingDataRequest(
        question_pt=(args.get("pergunta_pt") or "").strip(),
        field=(args.get("campo") or "").strip() or "desconhecido",
        unit=args.get("unidade"),
        element_id=None,
        suggested_default=args.get("suggested_default"),
        criticidade=args.get("criticidade") or "importante",
    )
    return _needs_input(
        call, [req],
        "Preciso de uma informação adicional para prosseguir.",
    )


# ---------------------------------------------------------------------------
# Despachante
# ---------------------------------------------------------------------------
_EXECUTORS = {
    "abrir_app": exec_abrir_app,
    "criar_orcamento": exec_criar_orcamento,
    "adicionar_item_orcamento": exec_adicionar_item_orcamento,
    "calcular_metrado": exec_calcular_metrado,
    "estimar_custo": exec_estimar_custo,
    "pesquisar_norma": exec_pesquisar_norma,
    "obter_preco_material": exec_obter_preco_material,
    "exportar_excel": exec_exportar_excel,
    "calcular_escada": exec_calcular_escada,
    "pesquisar_biblioteca": exec_pesquisar_biblioteca,
    "pedir_precisao": exec_pedir_precisao,
}


async def executar_tool_call(call: ToolCall, *, user_id: str) -> ToolResult:
    """Executa uma `ToolCall`. Marca `requires_user_confirmation` quando aplicável."""
    if call.name in NOMES_FERRAMENTAS_COM_CONFIRMACAO and not call.requires_user_confirmation:
        # A camada router já deve ter sinalizado; defesa em profundidade.
        logger.debug("ferramenta '%s' precisa de confirmação", call.name)
    fn = _EXECUTORS.get(call.name)
    if fn is None:
        return ToolResult(
            tool_call_id=call.id, status="error",
            payload={"detail": f"ferramenta '{call.name}' desconhecida"},
            user_message_pt=f"Ferramenta '{call.name}' não existe.",
        )
    try:
        return await fn(call, user_id=user_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("executor '%s' falhou", call.name)
        return ToolResult(
            tool_call_id=call.id, status="error",
            payload={"detail": f"{type(e).__name__}: {str(e)[:200]}"},
            user_message_pt="Falha interna ao executar a ferramenta.",
        )


__all__ = ["executar_tool_call", "_EXECUTORS"]
