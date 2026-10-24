"""Programa IA de opções — o cliente assinala, valida e depois a IA executa sozinha.

Só as opções assinaladas e validadas são executadas (nenhum acréscimo implícito).
Cada opção chama os motores determinísticos existentes (versão PT : RTIEBT,
DR 23/95) ; o prompt preparado só serve para redigir a síntese do entregável.

Fluxo : GET /missions/catalog → POST /missions/plan (resumo, nada é executado)
→ POST /agents/{run_id}/launch (fila e worker dos agentes : segundo plano,
concessão, cancelamento, notificação) → GET /missions/{run_id}.
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user, current_user
from engines import missions as M
from routes.plans_common import _now

log = logging.getLogger("missions")

router = APIRouter(tags=["missions"], prefix="/missions")


async def _option_allowed(key: str, user: dict) -> None:
    """Mesmos direitos que o ecrã de origem de cada motor."""
    from routes.agents import _authorize_agent
    if key == "controle":
        await _authorize_agent("supervise", user)
    elif key in ("devis", "dossier"):
        await _authorize_agent("devis", user)
    elif key in ("plan_electricite", "plan_plomberie"):
        from engines.access import require_level
        await _authorize_agent("metre", user)
        await require_level("pro")(user=user)
    else:  # analyse_plans, metre, planning, partage
        await _authorize_agent("metre", user)


async def _allowed_catalog(user: dict) -> dict[str, dict]:
    catalog = await M.effective_options(db)
    out = {}
    for key, spec in catalog.items():
        if not spec["enabled"]:
            continue
        try:
            await _option_allowed(key, user)
        except HTTPException:
            continue
        out[key] = spec
    return out


def _public_option(spec: dict) -> dict:
    return {k: spec[k] for k in ("key", "name", "group", "desc", "needs", "depends_on", "deliverable")}


@router.get("/catalog")
async def catalog(user=Depends(current_user)) -> dict:
    return {"options": [_public_option(s) for s in (await _allowed_catalog(user)).values()]}


class MissionIn(BaseModel):
    options: list[str] = Field(min_length=1, max_length=20)
    chantier_id: Optional[str] = Field(None, min_length=1, max_length=80)
    plan_ids: list[str] = Field(default_factory=list, max_length=50)
    note: str = Field("", max_length=1000)


@router.post("/plan")
async def propose(body: MissionIn, user=Depends(current_user)) -> dict:
    """Resumo da seleção SEM executar nada. O cliente valida-o a seguir."""
    from routes.agents import _authorize_agent, _load_owned_plans, _plan_status
    await _authorize_agent("mission", user)
    if body.chantier_id:
        from routes.chantiers import _get
        await _get(body.chantier_id, user["user_id"])
    allowed = await _allowed_catalog(user)
    try:
        ordered = M.resolve(body.options, allowed, has_plans=bool(body.plan_ids),
                            has_chantier=bool(body.chantier_id))
    except M.MissionError as exc:
        raise HTTPException(422, str(exc))
    plans = await _load_owned_plans(body.plan_ids, user) if body.plan_ids else []
    if body.chantier_id and any(p.get("chantier_id") != body.chantier_id for p in plans):
        raise HTTPException(422, "Uma planta selecionada pertence a outro processo")
    plan_status = await _plan_status(plans, user)

    warnings = [f"« {s['filename']} » não tem nenhuma medição nem divisão levantada: as opções de plantas vão assinalá-lo."
                for s in plan_status if not s["ready"]]
    if "devis" in ordered and not sum(s["priced"] for s in plan_status):
        warnings.append("Nenhuma medição está associada a um artigo: o orçamento ficará vazio enquanto não associar artigos.")
    if "partage" in ordered and not {"plan_electricite", "plan_plomberie"} & set(ordered):
        warnings.append("A partilha só contém os estudos produzidos por este programa: assinale também a planta de "
                        "eletricidade ou de canalização.")
    if "planning" in ordered and "devis" not in ordered:
        warnings.append("O planeamento parte dos orçamentos já associados ao processo; sem orçamento, ficará vazio.")

    steps = [{"key": k, "name": allowed[k]["name"], "deliverable": allowed[k]["deliverable"],
              "depends_on": allowed[k]["depends_on"], "prompt": allowed[k]["prompt"],
              "prompt_version": allowed[k]["prompt_version"], "status": "pending"} for k in ordered]
    run = {
        "run_id": "agr_" + secrets.token_hex(6), "user_id": user["user_id"], "agent": "mission",
        "prompt": body.note.strip(), "plan_ids": [s["plan_id"] for s in plan_status], "quote_ids": [],
        "chantier_id": body.chantier_id, "organization_id": user.get("organization_id"),
        "plan_status": plan_status, "warnings": warnings,
        "steps": [{"key": s["key"], "label": s["name"], "detail": s["deliverable"]} for s in steps],
        "mission": {"options": ordered, "steps": steps},
        "status": "proposed", "created_at": _now(),
    }
    await db.agent_runs.insert_one(dict(run))
    run.pop("_id", None)
    return {"run": _public_run(run)}


def _public_run(run: dict) -> dict:
    """O prompt completo fica do lado do servidor (rasto); o cliente vê o entregável."""
    out = {k: v for k, v in run.items() if k not in ("worker", "lease_until")}
    mission = dict(out.get("mission") or {})
    mission["steps"] = [{k: v for k, v in s.items() if k != "prompt"} for s in mission.get("steps") or []]
    out["mission"] = mission
    for key in ("result", "partial_result"):
        if isinstance(out.get(key), dict) and out[key].get("kind") == "mission":
            out[key] = {**out[key], "steps": [{k: v for k, v in s.items() if k != "prompt"}
                                              for s in out[key].get("steps") or []]}
    return out


@router.get("/{run_id}")
async def get_mission(run_id: str, user=Depends(current_user)) -> dict:
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"], "agent": "mission"}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Programa não encontrado")
    return {"run": _public_run(run)}


# ============================ Execução ============================

async def _exec_analyse(ctx) -> dict:
    from btp_ai.routes import get_analysis
    rows = []
    for s in ctx["run"]["plan_status"]:
        try:
            a = await get_analysis(s["plan_id"], user=ctx["user"])
        except HTTPException as exc:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": str(exc.detail)[:200]})
            continue
        analysis = a.get("analysis") or {}
        rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "state": a.get("state"),
                     "elements": len(a.get("elements") or []), "stats": a.get("stats") or {},
                     "missing": len(analysis.get("missing") or []), "conflicts": len(analysis.get("conflicts") or []),
                     "link": f"/analyse/{s['plan_id']}"})
    if rows and all(r.get("error") for r in rows):
        raise HTTPException(422, "Nenhuma planta pôde ser analisada")
    return {"kind": "analysis", "plans": rows}


async def _exec_controle(ctx) -> dict:
    from engines.platform_supervisor import run_supervisor
    return await run_supervisor(db, ctx["user"], {**ctx["run"], "quote_ids": []}, repair=False)


async def _exec_agent(agent: str, ctx) -> dict:
    from routes.agents import _do_execute
    return await _do_execute({**ctx["run"], "agent": agent}, ctx["body"], ctx["user"])


async def _mep_studies(ctx) -> list[dict]:
    """Um estudo MEP por planta, partilhado entre as opções de eletricidade e canalização."""
    if "mep" in ctx["cache"]:
        return ctx["cache"]["mep"]
    from engines.mep import generate
    from engines.mep.adapter import AdapterError, from_takeoff
    from routes.mep import DEFAULT_COUNTRY, _save
    uid = ctx["user"]["user_id"]
    rows = []
    for s in ctx["run"]["plan_status"]:
        plan = await db.plans_takeoff.find_one(
            {"plan_id": s["plan_id"], "user_id": uid},
            {"_id": 0, "plan_id": 1, "filename": 1, "rooms": 1, "calibrations": 1, "structure": 1, "mep_fixtures": 1})
        if not plan:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": "Planta não encontrada"})
            continue
        try:
            study = generate(from_takeoff(plan, None, DEFAULT_COUNTRY, {}))
        except (AdapterError, ValueError) as exc:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": str(exc)[:200]})
            continue
        saved = await _save(uid, study, f"Planos de execução — {plan.get('filename') or ''}", s["plan_id"])
        rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "study_id": saved["study_id"],
                     "summary": saved.get("summary") or {}, "pdf": f"/mep/studies/{saved['study_id']}/pdf"})
    ctx["cache"]["mep"] = rows
    return rows


async def _exec_mep(layer: str, ctx) -> dict:
    rows = await _mep_studies(ctx)
    if rows and all(r.get("error") for r in rows):
        raise HTTPException(422, rows[0]["error"])
    return {"kind": "mep", "layer": layer, "studies": [
        {**r, "svg": f"/mep/studies/{r['study_id']}/svg?layer={layer}"} if r.get("study_id") else r for r in rows]}


async def _exec_planning(ctx) -> dict:
    from routes import planning as PL
    cid, user = ctx["run"]["chantier_id"], ctx["user"]
    existing = await PL.COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 1})
    if existing:
        # Nunca se substitui um planeamento introduzido pelo profissional.
        return {"kind": "planning", "kept_existing": True, "link": f"/planning?chantier={cid}"}
    out = await PL.init_plan(cid, PL.InitIn(), user=user)
    project = (out.get("schedule") or {}).get("project") or {}
    return {"kind": "planning", "kept_existing": False, "tasks": len(out.get("tasks") or []),
            "from_lots": out.get("from_lots") or [], "start_date": project.get("start_date"),
            "end_date": project.get("end_date"), "link": f"/planning?chantier={cid}"}


async def _exec_partage(ctx) -> dict:
    """Prepara uma ligação de partilha dos estudos deste programa. A ligação fica INATIVA: só o profissional a ativa."""
    studies = [r for r in ctx["cache"].get("mep") or [] if r.get("study_id")]
    if not studies:
        raise HTTPException(422, "Nenhum entregável a partilhar: assinale também a planta de eletricidade ou de canalização.")
    items = [{"type": "mep", "id": r["study_id"], "title": f"Planos de execução — {r['filename']}"} for r in studies]
    share = {"share_id": "mshare_" + secrets.token_hex(6), "token": secrets.token_urlsafe(24), "user_id": ctx["user"]["user_id"],
             "run_id": ctx["run"]["run_id"], "items": items, "active": False, "created_at": _now()}
    await db.mission_shares.insert_one(dict(share))
    return {"kind": "share", "share_id": share["share_id"], "active": False, "files": [i["title"] for i in items],
            "activate": f"/missions/shares/{share['share_id']}/activate"}


EXECUTORS = {
    "analyse_plans": _exec_analyse,
    "controle": _exec_controle,
    "metre": lambda ctx: _exec_agent("metre", ctx),
    "plan_electricite": lambda ctx: _exec_mep("elec", ctx),
    "plan_plomberie": lambda ctx: _exec_mep("plumb", ctx),
    "devis": lambda ctx: _exec_agent("devis", ctx),
    "planning": _exec_planning,
    "dossier": lambda ctx: _exec_agent("report", ctx),
    "partage": _exec_partage,
}


async def _save_progress(run: dict, steps: list[dict]) -> None:
    await db.agent_runs.update_one(
        {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running", "worker": run.get("worker")},
        {"$set": {"partial_result": {"kind": "mission", "steps": steps}}})


async def run_mission(run: dict, body, user: dict) -> dict:
    """Executa as opções validadas, pela ordem registada no resumo.

    Uma opção falhada bloqueia as que dela dependem; as outras continuam."""
    validated = (run.get("mission") or {}).get("steps") or []
    prompts = {s["key"]: s.get("prompt") or "" for s in validated}
    # Os prompts ficam no rasto da seleção, não no resultado apresentado.
    steps = [{k: v for k, v in s.items() if k != "prompt"} for s in validated]
    if not steps:
        raise HTTPException(422, "Nenhuma opção validada")
    ctx = {"run": run, "body": body, "user": user, "cache": {}, "results": {}}
    status_of: dict[str, str] = {}
    for step in steps:
        key = step["key"]
        failed = [d for d in step.get("depends_on") or [] if status_of.get(d) != "done"]
        if failed:
            step.update(status="skipped", error="Não lançada: a opção de que depende não terminou.")
            status_of[key] = "skipped"
            await _save_progress(run, steps)
            continue
        step.update(status="running", started_at=_now())
        await _save_progress(run, steps)
        try:
            await _option_allowed(key, user)
            result = await EXECUTORS[key](ctx)
            step.update(status="done", result=result)
            ctx["results"][key] = result
            step["synthese"] = await M.synthesize(prompts[key], result)
        except HTTPException as exc:
            step.update(status="error", error=str(exc.detail)[:300])
        except Exception as exc:  # noqa: BLE001 -- no provider secrets in client errors
            log.error("Mission %s option %s failed (%s)", run["run_id"], key, type(exc).__name__)
            step.update(status="error", error="Tratamento interrompido nesta opção.")
        step["finished_at"] = _now()
        status_of[key] = step["status"]
        await _save_progress(run, steps)
    counts = {s: sum(1 for x in steps if x["status"] == s) for s in ("done", "error", "skipped")}
    if not counts["done"]:
        raise HTTPException(422, "Nenhuma opção terminou: " + (next((s["error"] for s in steps if s.get("error")), "")))
    return {"kind": "mission", "steps": steps, **counts}


# ============================ Partilha dos entregáveis ============================

SHARE_DAYS_DEFAULT = 30


class ShareActivateIn(BaseModel):
    days: int = Field(SHARE_DAYS_DEFAULT, ge=1, le=365)


def _share_url(token: str) -> str:
    import os
    base = os.environ.get("PUBLIC_BACKEND_URL") or os.environ.get("FRONTEND_URL") or ""
    return f"{base.rstrip('/')}/api/missions/public/{token}"


@router.post("/shares/{share_id}/activate")
async def activate_share(share_id: str, body: ShareActivateIn | None = None, user=Depends(current_user)) -> dict:
    """Clique do profissional: torna a ligação consultável (só leitura) pela duração escolhida. Nada é enviado."""
    from datetime import datetime, timedelta, timezone
    days = (body or ShareActivateIn()).days
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    res = await db.mission_shares.update_one({"share_id": share_id, "user_id": user["user_id"]},
                                             {"$set": {"active": True, "expires_at": expires, "activated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Partilha não encontrada")
    share = await db.mission_shares.find_one({"share_id": share_id, "user_id": user["user_id"]}, {"_id": 0, "token": 1})
    return {"ok": True, "url": _share_url(share["token"]), "expires_at": expires}


@router.post("/shares/{share_id}/revoke")
async def revoke_share(share_id: str, user=Depends(current_user)) -> dict:
    res = await db.mission_shares.update_one({"share_id": share_id, "user_id": user["user_id"]},
                                             {"$set": {"active": False, "revoked_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Partilha não encontrada")
    return {"ok": True}


async def _live_share(token: str) -> dict:
    from datetime import datetime, timezone
    share = await db.mission_shares.find_one({"token": token, "active": True}, {"_id": 0})
    if not share or not share.get("expires_at") or datetime.fromisoformat(share["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(404, "Ligação de partilha inativa ou expirada")
    return share


@router.get("/public/{token}")
async def public_share(token: str):
    """Página pública só de leitura: lista dos entregáveis partilhados."""
    from html import escape
    from fastapi.responses import HTMLResponse
    share = await _live_share(token)
    items = "".join(f'<li><a href="{escape(token)}/{escape(i["id"])}">{escape(i.get("title") or "Documento")}</a> <small>(PDF)</small></li>'
                    for i in share.get("items") or [])
    html = ("<!doctype html><html lang='pt-PT'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='robots' content='noindex'><title>Processo partilhado — ConstruPilot</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#1f2937}"
            "a{color:#0f766e}li{margin:8px 0}</style></head><body><h1>Processo partilhado</h1>"
            f"<p>Documentos transmitidos pelo seu profissional (só leitura, indicativos).</p><ul>{items}</ul></body></html>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/public/{token}/{item_id}")
async def public_share_file(token: str, item_id: str):
    from fastapi.responses import Response
    from engines.mep.pdf import build_pdf
    from engines.nom_fichier import content_disposition, nom_document
    share = await _live_share(token)
    item = next((i for i in share.get("items") or [] if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "Documento não encontrado")
    doc = await db.mep_studies.find_one({"study_id": item_id, "user_id": share["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Documento não encontrado")
    return Response(content=build_pdf(doc), media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Planos-execucao-instalacoes", doc.get("title"), doc.get("updated_at")), inline=True),
        "Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


# ============================ Admin: fichas de opções ============================

class OptionPatch(BaseModel):
    prompt: Optional[str] = Field(None, min_length=10, max_length=4000)
    enabled: Optional[bool] = None


@router.get("/admin/options")
async def admin_options(user=Depends(admin_user)) -> dict:
    catalog = await M.effective_options(db)
    return {"options": [{**_public_option(s), "prompt": s["prompt"], "enabled": s["enabled"],
                         "prompt_version": s["prompt_version"], "default_prompt": M.OPTIONS[k]["prompt"]}
                        for k, s in catalog.items()]}


@router.put("/admin/options/{key}")
async def admin_update_option(key: str, body: OptionPatch, user=Depends(admin_user)) -> dict:
    """Altera o prompt ou desativa uma opção. Os programas já validados mantêm a sua versão."""
    if key not in M.OPTIONS:
        raise HTTPException(404, "Opção desconhecida")
    patch = {"key": key, "updated_at": _now(), "updated_by": user["user_id"]}
    if body.prompt is not None:
        patch["prompt"] = body.prompt.strip()
    if body.enabled is not None:
        patch["enabled"] = body.enabled
    inc = {"version": 1} if body.prompt is not None else {}
    await db.mission_options.update_one({"key": key}, {"$set": patch, **({"$inc": inc} if inc else {})}, upsert=True)
    return {"ok": True, "options": (await admin_options(user))["options"]}


@router.delete("/admin/options/{key}/prompt")
async def admin_reset_prompt(key: str, user=Depends(admin_user)) -> dict:
    if key not in M.OPTIONS:
        raise HTTPException(404, "Opção desconhecida")
    await db.mission_options.update_one({"key": key}, {"$unset": {"prompt": ""}, "$set": {"updated_at": _now()}})
    return {"ok": True}
