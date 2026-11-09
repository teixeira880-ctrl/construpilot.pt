"""Integrate UA intake with existing jobs, account scope and artifact storage."""
import asyncio
import tempfile
from pathlib import Path
from . import reader, engine, report

async def handle(docs, hypotheses, *, step, store, db, uid, cid, request_id, llm=None, job_id=None, branding=None, decide_alone=False):
    # 09/11/2026 : étude CLT complète d'abord (moteur bet_clt, livrables EN + UK) ; dossier de preuves seulement en repli.
    try:
        from engines.bet_frame import hook as _fh
        if await _fh._handle_clt(db, job_id, uid, cid, request_id, docs, hypotheses or "CLT", "UA", "uk", step=step, store=store,
                                 llm=llm, branding=branding, decide_alone=decide_alone):
            return
    except Exception:  # noqa: BLE001 — repli : dossier de preuves UA (entrées requises)
        import logging
        logging.getLogger(__name__).exception("bet_clt UA failed, fallback to evidence dossier")
    await step("CLT Ukraine: reading every source page; preserving original materials", building_kind="clt_ua")
    evidence = await reader.read(docs, hypotheses, llm=llm)
    result = engine.run(evidence["calculation_input"])
    payload = {"evidence": evidence, "calculation_status": result}
    with tempfile.TemporaryDirectory() as tmp:
        files = await asyncio.to_thread(report.save, tmp, payload, evidence["calculation_input"])
        arts = [await store(db, uid, cid, request_id, kind, Path(path),
                            "CLT Ukraine - evidence / inputs required") for kind, path in files.items()]
    await step("CLT Ukraine: evidence available; engineering inputs required", status="questions",
               model=evidence, pages=evidence["pages"], artifacts=arts,
               review_status="INPUT_REQUIRED", blocking=len(result["missing"]),
               questions=result["missing"], points=evidence["issues"],
               decisions=["Target UA / CLT; source-country and source-material facts preserved separately."],
               execution_ready=False, national_code_compliance="NOT_DEMONSTRATED")
