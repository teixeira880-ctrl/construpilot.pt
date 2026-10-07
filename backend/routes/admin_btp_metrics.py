"""Endpoints admin para métricas do Assistente BTP (Fase C).

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

logger = logging.getLogger("admin.btp_metrics")
router = APIRouter(prefix="/admin/btp-assistant", tags=["admin"])


# ---------------------------------------------------------------------------
# Preços Gemini (USD/1M tokens) — Oct 2026
# ---------------------------------------------------------------------------
PRECOS_USD = {
    "gemini-pro-latest":   {"in": 1.25, "out": 10.00},
    "gemini-3.1-pro-preview": {"in": 1.25, "out": 10.00},
    "gemini-flash-latest": {"in": 0.075, "out": 0.30},
}
USD_PARA_EUR = 0.92


def _custo_eur(modelo: str, in_tok: int, out_tok: int) -> float:
    tabela = PRECOS_USD.get(modelo) or PRECOS_USD["gemini-pro-latest"]
    custo_usd = (in_tok / 1_000_000.0) * tabela["in"] + (out_tok / 1_000_000.0) * tabela["out"]
    return round(custo_usd * USD_PARA_EUR, 4)


def _exige_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")


def _janela(from_iso: str | None, to_iso: str | None, dias_default: int = 30) -> dict[str, Any]:
    """Devolve query Mongo com filtro de datas."""
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
            "from": t_from.isoformat(), "to": t_to.isoformat(),
        }

    # Agregações
    pipeline_global = [
        {"$match": base_query},
        {"$group": {
            "_id": None,
            "avg_dur": {"$avg": "$duracao_ms"},
            "ok": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "grounded": {"$sum": {"$cond": ["$grounding_used", 1, 0]}},
            "with_missing": {"$sum": {"$cond": [{"$gt": ["$missing_data_count", 0]}, 1, 0]}},
        }},
    ]
    g = (await db.btp_assistant_metrics.aggregate(pipeline_global).to_list(1))
    g = g[0] if g else {}

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

    # Custo estimado — heurística de tokens (duração como proxy quando
    # tokens não estão disponíveis). Para já, estimamos:
    #   * modo conversa: ~1200 in / ~800 out por turno
    #   * modo calculo/plano: ~2000 in / ~1500 out
    pipeline_model = [
        {"$match": base_query},
        {"$group": {"_id": {"modelo": "$modelo", "modo": "$modo"},
                    "n": {"$sum": 1}}},
    ]
    total_eur = 0.0
    for r in await db.btp_assistant_metrics.aggregate(pipeline_model).to_list(20):
        modelo = r["_id"]["modelo"]
        modo_r = r["_id"]["modo"]
        n = r["n"]
        if modo_r == "conversa":
            in_tok, out_tok = 1200, 800
        else:
            in_tok, out_tok = 2000, 1500
        total_eur += n * _custo_eur(modelo, in_tok, out_tok)

    return {
        "total_calls": total,
        "avg_duration_ms": int(g.get("avg_dur") or 0),
        "avg_duration_by_mode": by_mode,
        "tools_usage": tools_usage,
        "success_rate": round((g.get("ok", 0) / total) if total else 0.0, 3),
        "grounding_rate": round((g.get("grounded", 0) / total) if total else 0.0, 3),
        "missing_data_rate": round((g.get("with_missing", 0) / total) if total else 0.0, 3),
        "cost_estimate_eur": round(total_eur, 2),
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
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="btp_assistant_metrics.csv"'},
    )
