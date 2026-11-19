"""Estudo completo sobre geometria real: leitura → cotas (cortes) → cálculo → peças → quantidades.

Usado pelo estudo BET do Assistente quando a planta não é retangular (antes: só "peças de origem").
"""
from __future__ import annotations

import asyncio
import logging
import zipfile
from pathlib import Path

from . import levels_ai, outputs, pdf_vector, structure

log = logging.getLogger(__name__)


def _plan_page(docs):
    plans = pdf_vector.find_plans(docs)
    return plans[0].page if plans else None


async def study(docs, hypotheses: str, country: str, out_dir: Path, *, llm=None, meta: dict | None = None,
                on_step=None) -> dict:
    async def step(label):
        if on_step:
            await on_step(label)

    await step("A ler a geometria real nas plantas vetoriais (contorno, pátios, paredes)")
    b = await asyncio.to_thread(pdf_vector.read, docs, hypotheses, country)
    if b is None or b.footprint.area < 20:
        return {"ok": False, "reason": "geometria não legível nas plantas (sem planta vetorial à escala)"}
    await step("A ler cotas e terras suportadas nos cortes")
    warns = await levels_ai.read_levels(b, docs, llm, _plan_page(docs))
    await step("A calcular laje, vigas, pilares, fundações e muros sobre o contorno real")
    R = await asyncio.to_thread(structure.design, b)
    R.warnings = warns + R.warnings
    meta = {"obra": (meta or {}).get("obra") or "Moradia", **(meta or {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    await step("A desenhar plantas de estrutura e fundações, nota de cálculo e quantidades")
    report = outputs.write_report_pdf(b, R, out_dir / "Nota_de_calculo_estrutura.pdf", meta)
    plans = outputs.write_plans_pdf(b, R, out_dir / "Plantas_estrutura_fundacoes.pdf", meta)
    xlsx = outputs.write_quantities_xlsx(R, out_dir / "Mapa_de_quantidades_estrutura.xlsx", meta)
    dxf = outputs.write_dxf(b, R, out_dir / "Estrutura_fundacoes.dxf")
    zpath = out_dir / "Estrutura_DXF.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(dxf, dxf.name)
    ok_checks = all(c.get("ok") is not False for c in [*R.checks, *b.checks])
    return {
        "ok": True, "building": b, "result": R, "checks_ok": ok_checks,
        "files": [("pdf", report, "Nota de cálculo — estrutura (geometria real)"),
                  ("plans_pdf", plans, "Plantas de estrutura e fundações"),
                  ("xlsx", xlsx, "Mapa de quantidades — estrutura (Excel)"),
                  ("zip", zpath, "Desenhos DXF da estrutura")],
        "summary": {
            "area": round(b.footprint.area, 2), "slab_h": R.slab["h"], "pilares": len(R.columns),
            "vigas": len(R.beams), "sapatas": len(R.footings), "muros": len(R.retaining),
            "aco_kg": round(sum(q["aco_kg"] for q in R.quantities)),
            "betao_m3": round(sum(q["qtd"] for q in R.quantities if q["un"] == "m³" and "C" in q["item"]), 1),
        },
    }


async def handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, *, step, store, llm=None) -> bool:
    """Gancho do estudo BET (assistant_tool). True = estudo entregue; False = deixar o fluxo anterior."""
    import tempfile

    if str(country).upper() not in ("PT", "FR"):
        return False

    async def on_step(label):
        await step(label)

    with tempfile.TemporaryDirectory(prefix="cp_geo_") as tmp:
        try:
            res = await study(docs, hypotheses, country, Path(tmp), llm=llm, on_step=on_step)
        except Exception:  # noqa: BLE001
            log.exception("bet_geo study failed for %s", job_id)
            return False
        if not res.get("ok"):
            log.info("bet_geo: %s", res.get("reason"))
            return False
        arts = [await store(db, uid, cid, request_id, kind, path, label) for kind, path, label in res["files"]]
    R, s = res["result"], res["summary"]
    points = [
        f"Geometria real: {s['area']:.1f} m² lidos nas plantas (forma qualquer, pátios descontados).".replace(".", ","),
        f"Estrutura proposta: laje maciça e = {s['slab_h']:.2f} m, {s['vigas']} vigas, {s['pilares']} pilares, "
        f"{s['sapatas']} sapatas" + (f", {s['muros']} muro(s) de suporte" if s["muros"] else "") + ".",
        f"Betão estrutural ≈ {s['betao_m3']:.1f} m³ · aço A500 ≈ {s['aco_kg']} kg.".replace(".", ",", 1),
    ] + R.warnings
    review = ("Pré-dimensionamento sobre geometria real — confrontações OK. Projeto de estabilidade a assinar por engenheiro."
              if res["checks_ok"] else
              "Pré-dimensionamento sobre geometria real — há confrontações a rever (ver avisos).")
    await step("Estudo de estrutura concluído (geometria real)", status="done", review_status=review, artifacts=arts,
               points=points, questions=[], geometry_verified=True, execution_verified=False,
               geo_engine={"summary": s, "checks": R.checks, "geometry_checks": res["building"].checks})
    return True


async def geo_first(db, job_id, uid, cid, request_id, docs, hypotheses, country, step, store, llm=None, *,
                    when_irregular_only=False) -> bool:
    """Ponto de entrada no estudo BET. False = seguir o fluxo anterior; nunca levanta exceção.

    when_irregular_only: só atua se a planta não for retangular (o motor bet_core trata os retângulos).
    Desligar em produção sem deploy: BET_GEO_ENGINE=0.
    """
    import os

    if str(os.environ.get("BET_GEO_ENGINE", "1")).lower() in ("0", "false", "no"):
        return False
    try:
        if when_irregular_only:
            from engines.bet_core import geometry_review as _gr
            if await asyncio.to_thread(_gr.inspect, docs, hypotheses) is None:
                return False
        if llm is None:
            from engines.bet_core.reader import _default_llm as llm
        return await handle(db, job_id, uid, cid, request_id, docs, hypotheses, country,
                            step=step, store=store, llm=llm)
    except Exception:  # noqa: BLE001 — nunca estraga o estudo: volta ao fluxo anterior
        log.warning("bet_geo failed for %s", job_id, exc_info=True)
        return False
