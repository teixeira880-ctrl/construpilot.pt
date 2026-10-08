"""Teste da tool `obter_preco_material` com 10 queries sintéticas (Fase c).

Após o seed de `materials_pt_prices`, todas as queries devem ser
resolvidas pela biblioteca interna (fonte='biblioteca_interna'),
nunca caindo em fallback "Google Search sugerido".
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.btp_assistant.tools.executors import exec_obter_preco_material  # noqa: E402
from engines.btp_assistant.types import ToolCall  # noqa: E402


# 10 queries sintéticas cobrindo todas as categorias semeadas
QUERIES: list[tuple[str, str | None]] = [
    ("Betão C25/30", None),
    ("Betão C30/37", "nacional"),
    ("Aço A500NR ∅12", None),
    ("tijolo cerâmico 15", None),
    ("XPS 5", None),
    ("Reboco de cimento", None),
    ("Telha lusa", None),
    ("Porta blindada entrada", None),
    ("Sanita suspensa", None),
    ("Soalho flutuante AC4", None),
]


def test_obter_preco_material_resolve_todas_pela_biblioteca_interna():
    """Executa as 10 queries num único event loop (evita o problema
    de `Event loop is closed` do motor+parametrize)."""

    async def _run_all() -> list[tuple[str, dict]]:
        resultados = []
        for material, regiao in QUERIES:
            call = ToolCall(
                id="t1", name="obter_preco_material",
                arguments={
                    "material": material,
                    **({"regiao_pt": regiao} if regiao else {}),
                },
            )
            r = await exec_obter_preco_material(call, user_id="pytest")
            resultados.append((material, {
                "status": r.status,
                "fonte": r.payload.get("fonte"),
                "preco_eur": r.payload.get("preco_eur"),
            }))
        return resultados

    resultados = asyncio.run(_run_all())
    falhas = [
        (mat, data) for mat, data in resultados
        if data["status"] != "ok"
        or data["fonte"] != "biblioteca_interna"
        or float(data["preco_eur"] or 0) <= 0
    ]
    assert not falhas, (
        f"Materiais que caíram em fallback: {falhas}\n"
        f"Resultados completos: {resultados}"
    )
    assert len(resultados) == 10


def test_materials_pt_prices_seed_tem_pelo_menos_50_docs():
    """Verifica que o seed foi executado e a colecção tem >= 50 docs."""
    async def _count() -> int:
        from core.db import db
        return await db.materials_pt_prices.count_documents({})

    n = asyncio.run(_count())
    assert n >= 50, f"Esperado >= 50 docs em `materials_pt_prices`, obtido {n}."
