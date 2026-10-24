"""Agents métier ConstruPilot — orchestration par prompt.

Principe strict : l'agent ORIENTE (propose un plan d'actions, enchaîne les
outils) mais ne CALCULE jamais lui-même. Tous les chiffres proviennent des
moteurs déterministes existants (métré, corps d'état, PDF).

Mode : proposer → l'utilisateur valide → exécuter. Apprentissage pratique :
chaque exécution validée est mémorisée (`agent_runs`) et les choix (marge,
nom de projet, client) sont re-proposés par défaut la fois suivante.
"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from core.db import db
from core.security import current_user, pro_required
from core.permissions import require_feature
from engines.platform_supervisor import authorize, can_check_quotes, run_supervisor, undo_correction
from engines.expenses.context import bind
from routes.plans_common import _now

log = logging.getLogger("agents")
AGENT_LEASE_SECONDS = 600
AGENT_MAX_SECONDS = 1800

router = APIRouter(tags=["agents"], prefix="/agents")


AGENTS = {
    "supervise": {
        "name": "Pilote ConstruPilot", "icon": "ShieldCheck", "needs_plans": False,
        "desc": "Controla as suas plantas, medições e orçamentos, corrige os valores recalculáveis e detalha os pontos a verificar. Histórico e restauro incluídos.",
        "output": "supervision",
    },
    "report": {
        "name": "Processo automático",
        "desc": "Agrupa as suas plantas, levanta a medição (paredes, aberturas, áreas), orçamenta e produz o processo PDF completo com capa.",
        "icon": "FileText",
        "needs_plans": True,
        "output": "pdf",
    },
    "devis": {
        "name": "Orçamento automático",
        "desc": "Orçamenta todas as medições atribuídas das suas plantas e cria um orçamento consolidado editável.",
        "icon": "ReceiptText",
        "needs_plans": True,
        "output": "quote",
    },
    "metre": {
        "name": "Medição expresso",
        "desc": "Faz o ponto da medição das suas plantas: áreas, lineares, número de medições e de aberturas, e assinala as plantas a completar.",
        "icon": "Ruler",
        "needs_plans": True,
        "output": "summary",
    },
    "detect": {
        "name": "Deteção automática de paredes",
        "desc": "Lança a deteção IA das paredes e aberturas numa planta ainda não medida. Uma calibração (cota conhecida) continua obrigatória antes de qualquer medição.",
        "icon": "ScanLine",
        "needs_plans": True,
        "output": "detect",
    },
    "compare": {
        "name": "Comparação de plantas",
        "desc": "Compara duas versões de uma planta (antes / depois) e lista as divisões e paredes acrescentadas, retiradas ou modificadas.",
        "icon": "GitCompare",
        "needs_plans": True,
        "output": "compare",
    },
    # Programa de opções: lançado a partir de /missions (routes/missions.py), nunca a partir do catálogo.
    "mission": {
        "name": "Programa IA de opções", "icon": "ListChecks", "needs_plans": False, "hidden": True,
        "desc": "Executa apenas as opções assinaladas e validadas no processo.",
        "output": "mission",
    },
}


def _auto_level(filename: str, idx: int) -> str:
    """Déduit un libellé de niveau depuis le nom de fichier (sinon ordre)."""
    f = (filename or "").lower()
    rules = [
        (r"sous[\s_-]?sol|ss\b|s/sol", "Cave"),
        (r"fondation|semelle", "Fondations"),
        (r"\brdc\b|rez|r\.?d\.?c", "RDC"),
        (r"r\+?\s?4|4e|4ème|etage\s*4", "R+4"),
        (r"r\+?\s?3|3e|3ème|etage\s*3", "R+3"),
        (r"r\+?\s?2|2e|2ème|etage\s*2", "R+2"),
        (r"r\+?\s?1|1er|1ère|etage\s*1|combles?", "R+1"),
        (r"toiture|charpente", "Toiture"),
    ]
    for pat, label in rules:
        if re.search(pat, f):
            return label
    return ["RDC", "R+1", "R+2", "R+3", "R+4"][idx] if idx < 5 else f'Piso {idx + 1}'


async def _last_defaults(agent: str, user: dict) -> dict:
    """Réutilise les choix de la dernière exécution validée (apprentissage)."""
    prev = await db.agent_runs.find_one(
        {"user_id": user["user_id"], "agent": agent, "status": "done"},
        {"_id": 0, "params": 1}, sort=[("created_at", -1)])
    p = (prev or {}).get("params") or {}
    return {"margin_pct": p.get("margin_pct", 0), "project_name": "",
            "client": {}}


class PlanIn(BaseModel):
    agent: str
    chantier_id: Optional[str] = Field(None, min_length=1, max_length=80)
    plan_ids: list[str] = Field(default_factory=list, max_length=50)
    quote_ids: list[str] = Field(default_factory=list, max_length=50)
    prompt: str = Field("", max_length=1000)


class ExecIn(BaseModel):
    margin_pct: float = Field(0.0, ge=0, le=1000, allow_inf_nan=False)
    mode: Literal["audit", "repair"] = "audit"
    project_name: str = Field("", max_length=120)
    client_name: str = Field("", max_length=200)
    client_company: str = Field("", max_length=200)
    client_address: str = Field("", max_length=500)
    client_city: str = Field("", max_length=200)
    client_email: str = Field("", max_length=254)
    client_phone: str = Field("", max_length=80)


async def _authorize_agent(agent, user):
    authorize(user)
    if agent not in AGENTS:
        raise HTTPException(422, "Agente desconhecido")
    if agent != "supervise":
        await pro_required(user)
        require_feature(user, "devis" if agent in ("devis", "report") else "chantier")


async def _load_owned_plans(ids, user):
    if len(set(ids)) != len(ids) or any(not isinstance(pid, str) or not pid.strip() for pid in ids):
        raise HTTPException(422, "Seleção de plantas inválida ou duplicada")
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1, "measurements": 1, "chantier_id": 1}).to_list(51)
    if {p["plan_id"] for p in plans} != set(ids):
        raise HTTPException(404, "Uma ou várias plantas não foram encontradas para esta conta")
    order = {pid: i for i, pid in enumerate(ids)}
    return sorted(plans, key=lambda p: order[p["plan_id"]])


async def _plan_status(plans: list[dict], user: dict) -> list[dict]:
    """Statut de métré par plan (déterministe, aucun calcul inventé)."""
    # Libellés de niveau appris (corrections passées) par nom de fichier
    learned = {m["key"]: m["value"] async for m in db.agent_memory.find(
        {"user_id": user["user_id"], "kind": "level_label"}, {"_id": 0, "key": 1, "value": 1})}
    plan_status = []
    for i, p in enumerate(plans):
        ms = p.get("measurements") or []
        priced = [m for m in ms if m.get("poste")]
        openings = sum(len(m.get("openings") or []) for m in ms)
        rooms = p.get("rooms") or []
        fname = p.get("filename") or p["plan_id"]
        level = learned.get((p.get("filename") or "").lower()[:120]) or _auto_level(p.get("filename"), i)
        plan_status.append({
            "plan_id": p["plan_id"], "filename": fname,
            "level": level,
            "measures": len(ms), "priced": len(priced), "openings": openings,
            "rooms": len(rooms), "rooms_surface_m2": round(sum(float(r.get("surface_m2") or 0) for r in rooms), 2),
            "ready": len(ms) > 0 or len(rooms) > 0,
        })
    return plan_status


@router.get("/catalog")
async def catalog(user=Depends(current_user)) -> dict:
    available = []
    for key, spec in AGENTS.items():
        if spec.get("hidden"):
            continue
        try:
            await _authorize_agent(key, user)
        except HTTPException:
            continue
        available.append({"key": key, **spec})
    return {"agents": available, "can_check_quotes": can_check_quotes(user)}


@router.post("/plan")
async def propose_plan(body: PlanIn, user=Depends(current_user)) -> dict:
    """Propose un plan d'actions SANS rien exécuter. L'utilisateur le valide ensuite."""
    await _authorize_agent(body.agent, user)
    if AGENTS[body.agent].get("hidden"):
        raise HTTPException(422, "Este agente lança-se a partir do seu próprio ecrã")
    if body.chantier_id:
        from routes.chantiers import _get
        await _get(body.chantier_id, user["user_id"])
    if body.quote_ids and body.agent != "supervise":
        raise HTTPException(422, "Seleção de orçamentos reservada ao Piloto")
    if len(set(body.quote_ids)) != len(body.quote_ids):
        raise HTTPException(422, "Seleção de orçamentos duplicada")
    spec = AGENTS[body.agent]
    plans = []
    if spec["needs_plans"] or body.plan_ids:
        if spec["needs_plans"] and not body.plan_ids:
            raise HTTPException(422, "Selecione pelo menos uma planta")
        if body.agent == "compare" and len(body.plan_ids) != 2:
            raise HTTPException(422, "Selecione exatamente 2 plantas (antes / depois)")
        plans = await _load_owned_plans(body.plan_ids, user)
        if body.chantier_id and any(p.get("chantier_id") != body.chantier_id for p in plans):
            raise HTTPException(422, "Uma planta selecionada pertence a outro processo")
    order = {pid: i for i, pid in enumerate(body.plan_ids)}
    plans.sort(key=lambda p: order.get(p["plan_id"], 99))

    plan_status = await _plan_status(plans, user)
    plan_status = [{**x, "ready": x["measures"] > 0} for x in plan_status]   # agents clássicos: só medições
    priced_total = sum(x["priced"] for x in plan_status)

    steps = []
    if body.agent == "supervise":
        steps = [
            {"key": "inspect", "label": "Rever os dados registados", "detail": "Recursos selecionados, ou documentos associados ao processo (máximo 200 por tipo)." if body.chantier_id else "Recursos selecionados, ou recursos da conta (máximo 200 plantas e 200 orçamentos)."},
            {"key": "check", "label": "Controlar a coerência", "detail": "Escalas por página, geometria, aberturas, áreas, quantidades, preços e totais dos orçamentos."},
            {"key": "repair", "label": "Corrigir e voltar a verificar", "detail": "Em modo correção: apenas os valores derivados recalculáveis. Histórico e restauro; nenhuma alteração de um orçamento já comprometido."},
        ]
    if body.agent in ("report", "devis"):
        steps.append({"key": "group", "label": f'Agrupar {len(plans)} planta(s) em níveis',
                      "detail": " · ".join(f"{s['filename']} → {s['level']}" for s in plan_status)})
        steps.append({"key": "metre", "label": "Levantar a medição (paredes, aberturas, áreas)",
                      "detail": f"{sum((s['measures'] for s in plan_status))} medições · {sum((s['openings'] for s in plan_status))} aberturas detetadas"})
        steps.append({"key": "chiffrage", "label": "Orçamentar com os seus preços (motor determinístico)",
                      "detail": f'{priced_total} medição(ões) já atribuída(s) a um artigo'})
    if body.agent == "report":
        steps.append({"key": "pdf", "label": "Gerar o processo PDF completo",
                      "detail": "Capa + medição por nível + orçamentação + total c/ IVA"})
    elif body.agent == "devis":
        steps.append({"key": "quote", "label": "Criar o orçamento consolidado editável",
                      "detail": "Um artigo por trabalho, agrupado por nível"})
    elif body.agent == "metre":
        steps.append({"key": "summary", "label": "Produzir a síntese de medição",
                      "detail": f'{len(plans)} planta(s) analisada(s)'})
    elif body.agent == "detect":
        steps.append({"key": "detect", "label": "Detetar paredes e aberturas (IA)",
                      "detail": f'{len(plans)} planta(s) · renderização semântica paredes + portas/janelas'})
        steps.append({"key": "calibrate", "label": "Calibração OBRIGATÓRIA antes da medição",
                      "detail": "Abra a planta e introduza uma cota conhecida: sem escala fiável, nenhum comprimento é calculado."})
    elif body.agent == "compare":
        a, b = plan_status[0], plan_status[1]
        steps.append({"key": "compare", "label": "Associar divisões e paredes das 2 versões",
                      "detail": f"Avant : {a['filename']} · Depois: {b['filename']}"})
        steps.append({"key": "diff", "label": "Listar as diferenças (acrescentadas / retiradas / modificadas)",
                      "detail": "Divisões e paredes"})

    warnings = [f"« {s['filename']}» não tem nenhuma medição traçada — a completar no editor de plantas antes da orçamentação."
                for s in plan_status if not s["ready"]]
    if body.agent in ("report", "devis") and priced_total == 0:
        warnings.append("Nenhuma medição está atribuída a um artigo: a orçamentação ficará vazia enquanto não associar artigos às medições.")

    defaults = await _last_defaults(body.agent, user)
    run = {
        "run_id": "agr_" + secrets.token_hex(6), "user_id": user["user_id"],
        "agent": body.agent, "prompt": body.prompt.strip(), "plan_ids": [s["plan_id"] for s in plan_status],
        "quote_ids": body.quote_ids, "chantier_id": body.chantier_id, "organization_id": user.get("organization_id"),
        "plan_status": plan_status, "steps": steps, "warnings": warnings,
        "status": "proposed", "created_at": _now(),
    }
    await db.agent_runs.insert_one(dict(run))
    run.pop("_id", None)
    return {"run": run, "defaults": defaults, "agent_name": spec["name"]}


async def _make_group(run: dict, project_name: str, user: dict) -> str:
    name = (project_name or run.get("prompt") or "Dossier agent").strip()[:120] or "Dossier agent"
    g = {
        "group_id": "grp_" + secrets.token_hex(6), "user_id": user["user_id"],
        "name": name, "chantier_id": run.get("chantier_id"),
        "levels": [{"plan_id": s["plan_id"], "level_label": s["level"]} for s in run["plan_status"]],
        "created_at": _now(), "updated_at": _now(),
    }
    await db.plan_groups.insert_one(dict(g))
    return g["group_id"]


def _exec_params(body: ExecIn) -> dict:
    return {"mode": body.mode, "margin_pct": float(body.margin_pct or 0), "project_name": body.project_name,
            "client": {k.replace("client_", ""): getattr(body, k)
                       for k in ("client_name", "client_company", "client_address",
                                 "client_city", "client_email", "client_phone") if getattr(body, k)}}


async def _do_execute(run: dict, body: ExecIn, user: dict) -> dict:
    """Exécute réellement l'agent via les moteurs déterministes. Ne modifie pas le statut."""
    agent = run["agent"]
    margin = float(body.margin_pct or 0)
    result: dict = {}

    await _authorize_agent(agent, user)
    if agent == "supervise":
        async def progress(report):
            await db.agent_runs.update_one(
                {"run_id": run["run_id"], "user_id": user["user_id"], "status": "running", "worker": run["worker"]},
                {"$set": {"partial_result": report}})
        return await run_supervisor(db, user, run, repair=body.mode == "repair", progress=progress)
    if agent == "mission":
        from routes.missions import run_mission
        return await run_mission(run, body, user)
    from routes import plans_analysis as PA
    # Refresh source counts; a proposal may predate edits or resource deletion.
    fresh = await _load_owned_plans(run["plan_ids"], user)
    previous = {s["plan_id"]: s for s in run.get("plan_status") or []}
    run["plan_status"] = [{**previous[p["plan_id"]], "filename": p.get("filename"),
                           "measures": len(p.get("measurements") or []),
                           "priced": sum(bool(m.get("poste")) for m in p.get("measurements") or []),
                           "openings": sum(len(m.get("openings") or []) for m in p.get("measurements") or [])} for p in fresh]

    if agent in ("report", "devis"):
        gid = await _make_group(run, body.project_name, user)
        if agent == "report":
            from urllib.parse import urlencode
            q = {"margin_pct": margin}
            for k in ("client_name", "client_company", "client_address", "client_city", "client_email", "client_phone"):
                v = getattr(body, k)
                if v:
                    q[k] = v
            payload = await PA._group_payload(
                await db.plan_groups.find_one({"group_id": gid, "user_id": user["user_id"]}, {"_id": 0}),
                user, with_consolidation=True, margin=margin)
            result = {
                "kind": "pdf", "group_id": gid,
                "download": f"/takeoffs/multilevel/groups/{gid}/pdf?" + urlencode(q),
                "totals": payload.get("totals") or {}, "levels": len(payload.get("levels") or []),
            }
        else:  # devis
            created = await PA.plan_group_to_quote(gid, {"margin_pct": margin}, user)
            doc_id = created.get("doc_id") if isinstance(created, dict) else None
            result = {"kind": "quote", "group_id": gid, "doc_id": doc_id,
                      "edit": f"/devis-editeur/{doc_id}", "download": f"/documents/{doc_id}/pdf"}
    elif agent == "metre":
        rows = [s for s in run["plan_status"]]
        result = {"kind": "summary", "plans": rows,
                  "total_measures": sum(s["measures"] for s in rows),
                  "total_openings": sum(s["openings"] for s in rows)}
    elif agent == "detect":
        rows = []
        for s in run["plan_status"]:
            try:
                det = await PA.detect_structure_route(s["plan_id"], page_index=0, plan_kind="auto", user=user)
            except Exception:  # noqa: BLE001
                rows.append({**s, "error": "Deteção indisponível nesta planta", "walls": 0, "openings": 0})
                continue
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"],
                         "walls": len(det.get("walls") or []),
                         "openings": len(det.get("openings") or []),
                         "columns": len(det.get("columns") or []),
                         "beams": len(det.get("beams") or [])})
        result = {"kind": "detect", "plans": rows,
                  "partial": any(r.get("error") for r in rows),
                  "total_walls": sum(r.get("walls", 0) for r in rows),
                  "total_openings": sum(r.get("openings", 0) for r in rows),
                  "needs_calibration": True,
                  "edit_plan_id": rows[0]["plan_id"] if rows else None}
        if rows and all(r.get("error") for r in rows):
            raise HTTPException(502, "Nenhuma planta pôde ser analisada")
    elif agent == "compare":
        pid = run["plan_ids"]
        diff = await PA.compare_plans(PA.CompareIn(before_plan_id=pid[0], after_plan_id=pid[1]), user)
        result = {"kind": "compare", "diff": diff,
                  "before_plan_id": pid[0], "after_plan_id": pid[1]}
    return result


@router.post("/{run_id}/execute")
async def execute_run(run_id: str, body: ExecIn, user=Depends(current_user)) -> dict:
    """Exécution SYNCHRONE (page Plans & métré). Pour l'arrière-plan, voir /launch."""
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Execução não encontrada")
    await _authorize_agent(run["agent"], user)
    claimed = await db.agent_runs.find_one_and_update(
        {"run_id": run_id, "user_id": user["user_id"], "status": "proposed"},
        {"$set": {"status": "running", "worker": secrets.token_hex(16), "exec_params": body.model_dump(),
                  "lease_until": (datetime.now(timezone.utc) + timedelta(seconds=AGENT_LEASE_SECONDS)).isoformat(), "started_at": _now()}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if not claimed:
        raise HTTPException(409, "Esta tarefa já foi lançada ou concluída; consulte o seu resultado")
    await _run_agent_job(claimed)
    completed = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if completed.get("status") != "done":
        raise HTTPException(409, completed.get("error") or "Execução interrompida")
    return {"ok": True, "result": completed["result"]}


@router.post("/{run_id}/launch")
async def launch_run(run_id: str, body: ExecIn, user=Depends(current_user)) -> dict:
    """Met l'exécution en file d'attente : elle tourne en arrière-plan côté serveur
    (survit au changement de page). L'avancement se suit via /agents/runs et /agents/active."""
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Execução não encontrada")
    await _authorize_agent(run["agent"], user)
    if run.get("status") == "queued":
        return {"queued": True, "run_id": run_id}
    changed = await db.agent_runs.update_one(
        {"run_id": run_id, "user_id": user["user_id"], "status": "proposed"},
        {"$set": {"status": "queued", "exec_params": body.model_dump(), "queued_at": _now(),
                  "result": None, "error": None}})
    if not changed.matched_count:
        raise HTTPException(409, "Esta tarefa já foi lançada ou concluída; consulte o seu resultado")
    return {"queued": True, "run_id": run_id}


@router.get("/{run_id}/checks")
async def run_checks(run_id: str, offset: int = 0, user=Depends(current_user)):
    if not 0 <= offset <= 400:
        raise HTTPException(422, "Página inválida")
    rows = await db.agent_checks.find({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0}).sort("resource_id", 1).skip(offset).to_list(51)
    return {"checks": rows[:50], "next_offset": offset + 50 if len(rows) > 50 else None}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, user=Depends(current_user)):
    query = {"run_id": run_id, "user_id": user["user_id"]}
    queued = await db.agent_runs.update_one({**query, "status": "queued"},
        {"$set": {"status": "error", "cancel_requested": True, "error": "Tâche annulée avant exécution.", "executed_at": _now()}})
    if queued.matched_count:
        return {"ok": True, "cancel_requested": True}
    running = await db.agent_runs.update_one({**query, "status": "running"}, {"$set": {"cancel_requested": True}})
    if not running.matched_count:
        raise HTTPException(409, "Tarefa ausente, inacessível ou já concluída")
    return {"ok": True, "cancel_requested": True}


class UndoIn(BaseModel):
    kind: Literal["plan", "quote"]
    resource_id: str = Field(min_length=1, max_length=100)


@router.post("/{run_id}/undo")
async def undo_run(run_id: str, body: UndoIn, user=Depends(current_user)):
    result = await undo_correction(db, user, body.kind, body.resource_id, run_id)
    await db.agent_checks.update_one(
        {"run_id": run_id, "user_id": user["user_id"], "kind": body.kind, "resource_id": body.resource_id},
        {"$set": {"restored": True}})
    return result


@router.get("/active")
async def active_runs(user=Depends(current_user)) -> dict:
    """Runs en file ou en cours pour l'indicateur global (léger)."""
    rows = await db.agent_runs.find(
        {"user_id": user["user_id"], "status": {"$in": ["queued", "running"]}},
        {"_id": 0, "run_id": 1, "agent": 1, "status": 1, "created_at": 1, "queued_at": 1}
    ).sort("queued_at", 1).to_list(50)
    for r in rows:
        r["agent_name"] = AGENTS.get(r.get("agent"), {}).get("name", r.get("agent"))
    return {"runs": rows}


@router.get("/runs")
async def list_runs(user=Depends(current_user), chantier_id: Optional[str] = None) -> dict:
    query = {"user_id": user["user_id"]}
    if chantier_id:
        from routes.chantiers import _get
        await _get(chantier_id, user["user_id"])
        query["chantier_id"] = chantier_id
    rows = await db.agent_runs.find(
        query, {"_id": 0, "plan_status": 0, "steps": 0, "mission.steps.prompt": 0}
    ).sort("created_at", -1).limit(30).to_list(30)
    for r in rows:
        r["agent_name"] = AGENTS.get(r.get("agent"), {}).get("name", r.get("agent"))
    return {"runs": rows}


class FeedbackIn(BaseModel):
    rating: Literal["", "ok", "error"] = ""
    note: str = Field("", max_length=1000)
    level_labels: dict = Field(default_factory=dict)  # {plan_id: "RDC"} corrections
    margin_pct: float | None = Field(None, ge=0, le=1000, allow_inf_nan=False)


@router.post("/{run_id}/feedback")
async def give_feedback(run_id: str, body: FeedbackIn, user=Depends(current_user)) -> dict:
    """Revue de l'utilisateur sur un résultat. Les corrections (libellés de
    niveau, marge) sont mémorisées et re-proposées ensuite (apprentissage)."""
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Execução não encontrada")
    fb = {"rating": body.rating, "note": body.note.strip(),
          "level_labels": body.level_labels or {}, "margin_pct": body.margin_pct,
          "at": _now()}
    await db.agent_runs.update_one(
        {"run_id": run_id, "user_id": user["user_id"]}, {"$set": {"feedback": fb}})
    # Apprentissage : mémorise les corrections de libellés de niveau par nom de fichier
    for s in run.get("plan_status") or []:
        corrected = (body.level_labels or {}).get(s["plan_id"])
        if corrected and corrected != s["level"]:
            await db.agent_memory.update_one(
                {"user_id": user["user_id"], "kind": "level_label",
                 "key": (s.get("filename") or "").lower()[:120]},
                {"$set": {"value": corrected, "updated_at": _now()}}, upsert=True)
    return {"ok": True}


@router.post("/{run_id}/revise")
async def revise_run(run_id: str, body: FeedbackIn, user=Depends(current_user)) -> dict:
    """Crée une nouvelle proposition corrigée à partir d'un run (libellés de
    niveau et/ou marge revus), prête à être ré-exécutée."""
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Execução não encontrada")
    await _authorize_agent(run["agent"], user)
    if AGENTS[run["agent"]].get("hidden"):
        raise HTTPException(422, "Esta execução não se revê; crie uma nova seleção")
    new_status = []
    for s in run.get("plan_status") or []:
        s2 = dict(s)
        corr = (body.level_labels or {}).get(s["plan_id"])
        if corr:
            s2["level"] = corr.strip()[:40]
        new_status.append(s2)
    # Reconstruit les étapes avec les niveaux corrigés
    steps = []
    agent = run["agent"]
    if agent in ("report", "devis"):
        steps.append({"key": "group", "label": f'Agrupar {len(new_status)} planta(s) em níveis',
                      "detail": " · ".join(f"{s['filename']} → {s['level']}" for s in new_status)})
        steps.append({"key": "metre", "label": "Levantar a medição (paredes, aberturas, áreas)",
                      "detail": f"{sum((s['measures'] for s in new_status))} medições · {sum((s['openings'] for s in new_status))} ouvertures"})
        steps.append({"key": "chiffrage", "label": "Orçamentar com os seus preços (motor determinístico)",
                      "detail": f"{sum((s['priced'] for s in new_status))} medição(ões) atribuída(s)"})
    if agent == "report":
        steps.append({"key": "pdf", "label": "Regenerar o processo PDF corrigido", "detail": "Com as suas correções"})
    elif agent == "devis":
        steps.append({"key": "quote", "label": "Recriar o orçamento corrigido", "detail": "Com as suas correções"})
    new = {
        "run_id": "agr_" + secrets.token_hex(6), "user_id": user["user_id"],
        "agent": agent, "prompt": run.get("prompt", ""), "plan_ids": run.get("plan_ids", []),
        "quote_ids": run.get("quote_ids", []), "organization_id": user.get("organization_id"),
        "plan_status": new_status, "steps": steps, "warnings": run.get("warnings", []),
        "status": "proposed", "revised_from": run_id, "created_at": _now(),
    }
    await db.agent_runs.insert_one(dict(new))
    new.pop("_id", None)
    defaults = {"margin_pct": body.margin_pct if body.margin_pct is not None else 0,
                "project_name": "", "client": {}}
    return {"run": new, "defaults": defaults, "agent_name": AGENTS[agent]["name"]}


# ===================== Exécution en arrière-plan (worker) =====================

async def _agent_notify(run_id: str, uid: str, status: str, agent_name: str, agent: str = "") -> None:
    if status not in ("done", "error"):
        return
    await db.notifications.update_one(
        {"user_id": uid, "notif_id": "n_agent_" + run_id},
        {"$set": {"notif_id": "n_agent_" + run_id, "user_id": uid, "type": "agent",
                  "title": "Agent terminé" if status == "done" else "Agent en échec",
                  "message": (f"{agent_name} : résultat prêt" if status == "done"
                              else f"{agent_name} : l'exécution a échoué"),
                  "link": f"/missions?run={run_id}" if agent == "mission" else f"/agents?run={run_id}",
                  "read": False, "created_at": _now()}},
        upsert=True)


async def _finish_agent(run, status, result=None, error=None):
    changed = await db.agent_runs.update_one(
        {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running", "worker": run["worker"]},
        {"$set": {"status": status, "result": result, "error": error, "executed_at": _now()},
         "$unset": {"lease_until": "", "worker": ""}})
    if changed.matched_count:
        await _agent_notify(run["run_id"], run["user_id"], status, AGENTS[run["agent"]]["name"], run["agent"])


async def _heartbeat(run, operation):
    while True:
        await asyncio.sleep(30)
        try:
            user = await db.users.find_one({"user_id": run["user_id"]}, {"_id": 0})
        except Exception:
            operation.cancel()
            return
        try:
            await _authorize_agent(run["agent"], user)
            if "organization_id" in run and user.get("organization_id") != run.get("organization_id"):
                raise HTTPException(403, "A associação da conta mudou")
        except HTTPException:
            operation.cancel()
            return
        until = (datetime.now(timezone.utc) + timedelta(seconds=AGENT_LEASE_SECONDS)).isoformat()
        try:
            renewed = await db.agent_runs.update_one(
                {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running", "worker": run["worker"], "cancel_requested": {"$ne": True}},
                {"$set": {"lease_until": until}})
        except Exception:
            operation.cancel()
            return
        if not renewed.matched_count:
            operation.cancel()
            return


async def _run_agent_job(run: dict) -> None:
    operation = heartbeat = None
    try:
        user = await db.users.find_one({"user_id": run["user_id"]}, {"_id": 0, "password_hash": 0, "password": 0})
        await _authorize_agent(run["agent"], user)
        if "organization_id" in run and user.get("organization_id") != run.get("organization_id"):
            raise HTTPException(403, "A associação da conta mudou")
        bind(user)
        body = ExecIn(**(run.get("exec_params") or {}))
        operation = asyncio.create_task(_do_execute(run, body, user))
        heartbeat = asyncio.create_task(_heartbeat(run, operation))
        result = await asyncio.wait_for(operation, timeout=AGENT_MAX_SECONDS)
        await db.agent_runs.update_one(
            {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running", "worker": run["worker"]},
            {"$set": {"params": _exec_params(body)}})
        await _finish_agent(run, "done", result=result)
    except asyncio.CancelledError:
        await _finish_agent(run, "error", error="Processamento interrompido ou autorização retirada. Verifique as correções já efetuadas antes de relançar.")
        raise
    except HTTPException as exc:
        await _finish_agent(run, "error", error=str(exc.detail)[:300])
    except Exception as exc:  # noqa: BLE001 -- no provider secrets in client errors
        log.error("Agent run %s failed (%s)", run["run_id"], type(exc).__name__)
        await _finish_agent(run, "error", error="Processamento interrompido. Consulte os resultados parciais antes de criar uma nova tarefa.")
    finally:
        for task in (operation, heartbeat):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (operation, heartbeat) if t), return_exceptions=True)


async def _claim_agent_run(worker: str) -> dict | None:
    now = _now()
    stale = await db.agent_runs.find(
        {"status": "running", "lease_until": {"$lt": now}},
        {"_id": 0, "run_id": 1, "user_id": 1, "agent": 1, "worker": 1, "lease_until": 1}).to_list(20)
    for run in stale:
        changed = await db.agent_runs.update_one(
            {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running",
             "worker": run.get("worker"), "lease_until": {"$lt": now}},
            {"$set": {"status": "error", "error": "Processamento interrompido (reinício). Verifique os resultados parciais.", "executed_at": now},
             "$unset": {"lease_until": "", "worker": ""}})
        if changed.matched_count:
            await _agent_notify(run["run_id"], run["user_id"], "error", AGENTS.get(run["agent"], {}).get("name", "Agent"), run["agent"])
    until = (datetime.now(timezone.utc) + timedelta(seconds=AGENT_LEASE_SECONDS)).isoformat()
    return await db.agent_runs.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "running", "worker": worker + ":" + secrets.token_hex(8), "lease_until": until, "started_at": now}},
        sort=[("queued_at", 1)], return_document=ReturnDocument.AFTER, projection={"_id": 0})


async def _agent_worker_loop() -> None:
    worker = secrets.token_hex(8)
    while True:
        try:
            run = await _claim_agent_run(worker)
            if run:
                try:
                    await _run_agent_job(run)
                except asyncio.CancelledError:
                    # A revoked job must not kill the shared worker; application shutdown must.
                    if asyncio.current_task().cancelling():
                        raise
            else:
                await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Agent worker crashed")
            await asyncio.sleep(3)


async def start_agent_workers() -> list:
    await db.agent_runs.create_index("run_id")
    await db.agent_runs.create_index([("status", 1), ("queued_at", 1)])
    await db.agent_runs.create_index([("user_id", 1), ("created_at", -1)])
    await db.agent_checks.create_index([("user_id", 1), ("run_id", 1), ("resource_id", 1)])
    return [asyncio.create_task(_agent_worker_loop())]
