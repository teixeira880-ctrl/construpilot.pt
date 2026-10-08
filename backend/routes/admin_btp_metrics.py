"""Endpoints admin para métricas do Assistente BTP (Fase C + Fase B tokens reais).

GET  /api/admin/btp-assistant/metrics             — agregados
GET  /api/admin/btp-assistant/metrics/recent      — últimas N chamadas
GET  /api/admin/btp-assistant/metrics/export.csv  — export CSV

Acesso restrito a `user.role == 'admin'`.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from core.db import db
from core.security import current_user
from engines.btp_assistant.pricing import (
    PRECOS_USD_POR_1M,
    custo_eur,
    taxa_eur_usd,
)

logger = logging.getLogger("admin.btp_metrics")
router = APIRouter(prefix="/admin/btp-assistant", tags=["admin"])


def _exige_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")


def _janela(from_iso: str | None, to_iso: str | None, dias_default: int = 30) -> tuple[dict[str, Any], datetime, datetime]:
    """Devolve query Mongo com filtro de datas + limites."""
    now = datetime.now(timezone.utc)
    try:
        t_to = datetime.fromisoformat(to_iso.replace("Z", "+00:00")) if to_iso else now
    except Exception:  # noqa: BLE001
        t_to = now
    try:
        t_from = (
            datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
            if from_iso else now - timedelta(days=dias_default)
        )
    except Exception:  # noqa: BLE001
        t_from = now - timedelta(days=dias_default)
    return {"created_at": {"$gte": t_from, "$lte": t_to}}, t_from, t_to


@router.get("/metrics")
async def metrics(
    user=Depends(current_user),
    from_iso: str | None = Query(default=None, alias="from"),
    to_iso: str | None = Query(default=None, alias="to"),
    user_plan: str | None = Query(default=None),
    modo: str | None = Query(default=None),
):
    """Agregados principais do Assistente BTP."""
    _exige_admin(user)
    base_query, t_from, t_to = _janela(from_iso, to_iso)
    if user_plan:
        base_query["user_plan"] = user_plan
    if modo:
        base_query["modo"] = modo

    total = await db.btp_assistant_metrics.count_documents(base_query)
    if total == 0:
        return {
            "total_calls": 0, "avg_duration_ms": 0,
            "avg_duration_by_mode": {}, "tools_usage": [],
            "success_rate": 0.0, "grounding_rate": 0.0,
            "missing_data_rate": 0.0, "cost_estimate_eur": 0.0,
            "avg_tokens_input": 0, "avg_tokens_output": 0,
            "avg_thinking_tokens": 0, "avg_cached_tokens": 0,
            "total_tokens_input": 0, "total_tokens_output": 0,
            "total_thinking_tokens": 0,
            "eur_usd_rate": taxa_eur_usd(),
            "from": t_from.isoformat(), "to": t_to.isoformat(),
        }

    # Agregação global (sucesso, grounding, duração, tokens reais)
    # NOTA: usa `tokens_input_real` quando existe; fallback para `tokens_input`
    pipeline_global = [
        {"$match": base_query},
        {"$addFields": {
            "_tok_in": {"$ifNull": ["$tokens_input_real", {"$ifNull": ["$tokens_input", 0]}]},
            "_tok_out": {"$ifNull": ["$tokens_output_real", {"$ifNull": ["$tokens_output", 0]}]},
            "_tok_think": {"$ifNull": ["$thinking_tokens_real", 0]},
            "_tok_cached": {"$ifNull": ["$cached_tokens_real", 0]},
            "_cost_eur": {"$ifNull": ["$cost_estimate_eur", 0]},
        }},
        {"$group": {
            "_id": None,
            "avg_dur": {"$avg": "$duracao_ms"},
            "ok": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "grounded": {"$sum": {"$cond": ["$grounding_used", 1, 0]}},
            "with_missing": {"$sum": {"$cond": [{"$gt": ["$missing_data_count", 0]}, 1, 0]}},
            "sum_in": {"$sum": "$_tok_in"},
            "sum_out": {"$sum": "$_tok_out"},
            "sum_think": {"$sum": "$_tok_think"},
            "sum_cached": {"$sum": "$_tok_cached"},
            "avg_in": {"$avg": "$_tok_in"},
            "avg_out": {"$avg": "$_tok_out"},
            "avg_think": {"$avg": "$_tok_think"},
            "avg_cached": {"$avg": "$_tok_cached"},
            "sum_cost": {"$sum": "$_cost_eur"},
            "has_real": {"$sum": {"$cond": [{"$gt": ["$_tok_in", 0]}, 1, 0]}},
        }},
    ]
    g_rows = await db.btp_assistant_metrics.aggregate(pipeline_global).to_list(1)
    g = g_rows[0] if g_rows else {}

    pipeline_mode = [
        {"$match": base_query},
        {"$group": {"_id": "$modo", "avg": {"$avg": "$duracao_ms"},
                    "n": {"$sum": 1}}},
    ]
    by_mode = {
        row["_id"]: {"avg_duration_ms": int(row["avg"] or 0),
                     "count": row["n"]}
        for row in await db.btp_assistant_metrics.aggregate(pipeline_mode).to_list(10)
    }

    pipeline_tools = [
        {"$match": base_query},
        {"$unwind": "$tools_called"},
        {"$group": {"_id": "$tools_called", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 15},
    ]
    tools_usage = [
        {"name": r["_id"], "count": r["n"]}
        for r in await db.btp_assistant_metrics.aggregate(pipeline_tools).to_list(15)
    ]

    # Custo total EUR: usa `cost_estimate_eur` real quando existe. Caso contrário,
    # recalcula com a heurística antiga (retrocompat para registos antigos).
    total_cost_real = float(g.get("sum_cost") or 0.0)
    docs_sem_real = total - int(g.get("has_real") or 0)
    total_cost_heur = 0.0
    if docs_sem_real > 0:
        # Heurística para linhas antigas sem tokens reais
        pipeline_model = [
            {"$match": {**base_query, "$or": [
                {"tokens_input_real": {"$exists": False}},
                {"tokens_input_real": {"$lte": 0}},
            ]}},
            {"$group": {"_id": {"modelo": "$modelo", "modo": "$modo"},
                        "n": {"$sum": 1}}},
        ]
        for r in await db.btp_assistant_metrics.aggregate(pipeline_model).to_list(20):
            modelo_r = r["_id"]["modelo"]
            modo_r = r["_id"]["modo"]
            n = r["n"]
            if modo_r == "conversa":
                in_tok, out_tok = 1200, 800
            else:
                in_tok, out_tok = 2000, 1500
            total_cost_heur += n * custo_eur(
                modelo_r, tokens_input=in_tok, tokens_output=out_tok,
            )
    custo_total_eur = round(total_cost_real + total_cost_heur, 6)

    return {
        "total_calls": total,
        "avg_duration_ms": int(g.get("avg_dur") or 0),
        "avg_duration_by_mode": by_mode,
        "tools_usage": tools_usage,
        "success_rate": round((g.get("ok", 0) / total) if total else 0.0, 3),
        "grounding_rate": round((g.get("grounded", 0) / total) if total else 0.0, 3),
        "missing_data_rate": round((g.get("with_missing", 0) / total) if total else 0.0, 3),
        "cost_estimate_eur": custo_total_eur,
        # Tokens reais agregados (Fase B)
        "avg_tokens_input": int(g.get("avg_in") or 0),
        "avg_tokens_output": int(g.get("avg_out") or 0),
        "avg_thinking_tokens": int(g.get("avg_think") or 0),
        "avg_cached_tokens": int(g.get("avg_cached") or 0),
        "total_tokens_input": int(g.get("sum_in") or 0),
        "total_tokens_output": int(g.get("sum_out") or 0),
        "total_thinking_tokens": int(g.get("sum_think") or 0),
        "total_cached_tokens": int(g.get("sum_cached") or 0),
        "calls_with_real_tokens": int(g.get("has_real") or 0),
        "eur_usd_rate": taxa_eur_usd(),
        "from": t_from.isoformat(),
        "to": t_to.isoformat(),
    }


@router.get("/metrics/recent")
async def metrics_recent(
    user=Depends(current_user),
    limit: int = 50,
):
    """Últimas N chamadas (anonimizadas: user_id truncado)."""
    _exige_admin(user)
    limit = max(1, min(limit, 200))
    rows = await db.btp_assistant_metrics.find(
        {}, {"_id": 0},
    ).sort("created_at", -1).to_list(limit)
    for r in rows:
        uid = r.get("user_id") or ""
        r["user_id_short"] = (uid[:6] + "…") if len(uid) > 6 else uid
        r.pop("user_id", None)
        if isinstance(r.get("created_at"), datetime):
            r["created_at_iso"] = r["created_at"].isoformat()
            r.pop("created_at", None)
    return {"items": rows, "count": len(rows)}


@router.get("/metrics/export.csv")
async def metrics_export(user=Depends(current_user)):
    """Export CSV de todas as métricas (admin)."""
    _exige_admin(user)
    rows = await db.btp_assistant_metrics.find(
        {}, {"_id": 0},
    ).sort("created_at", -1).to_list(10_000)
    buf = io.StringIO()
    campos = [
        "created_at", "conversation_id", "user_plan", "modo", "modelo",
        "duracao_ms", "status", "tools_called", "tool_errors",
        "grounding_used", "missing_data_count", "attachments_count",
        "tokens_input_real", "tokens_output_real", "thinking_tokens_real",
        "cached_tokens_real", "cost_estimate_eur",
    ]
    w = csv.writer(buf)
    w.writerow(campos)
    for r in rows:
        w.writerow([
            r.get("created_at").isoformat() if r.get("created_at") else "",
            r.get("conversation_id", ""),
            r.get("user_plan", ""),
            r.get("modo", ""),
            r.get("modelo", ""),
            r.get("duracao_ms", 0),
            r.get("status", ""),
            "|".join(r.get("tools_called") or []),
            r.get("tool_errors", 0),
            r.get("grounding_used", False),
            r.get("missing_data_count", 0),
            r.get("attachments_count", 0),
            r.get("tokens_input_real", r.get("tokens_input", 0)),
            r.get("tokens_output_real", r.get("tokens_output", 0)),
            r.get("thinking_tokens_real", 0),
            r.get("cached_tokens_real", 0),
            r.get("cost_estimate_eur", 0.0),
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="btp_assistant_metrics.csv"'},
    )


@router.get("/metrics/pricing")
async def metrics_pricing(user=Depends(current_user)):
    """Devolve a tabela de preços actual (admin — útil para debug)."""
    _exige_admin(user)
    return {
        "precos_usd_por_1m": PRECOS_USD_POR_1M,
        "eur_usd_rate": taxa_eur_usd(),
    }
