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
        "desc": "Contrôle vos plans, métrés et devis, corrige les valeurs recalculables et détaille les points à vérifier. Historique et restauration inclus.",
        "output": "supervision",
    },
    "report": {
        "name": "Dossier automatique",
        "desc": "Regroupe vos plans, relève le métré (murs, ouvertures, surfaces), chiffre et produit le dossier PDF complet avec page de garde.",
        "icon": "FileText",
        "needs_plans": True,
        "output": "pdf",
    },
    "devis": {
        "name": "Devis automatique",
        "desc": "Chiffre toutes les mesures affectées de vos plans et crée un devis consolidé modifiable.",
        "icon": "ReceiptText",
        "needs_plans": True,
        "output": "quote",
    },
    "metre": {
        "name": "Métré express",
        "desc": "Fait le point sur le métré de vos plans : surfaces, linéaires, nombre de mesures et d'ouvertures, et signale les plans à compléter.",
        "icon": "Ruler",
        "needs_plans": True,
        "output": "summary",
    },
    "detect": {
        "name": "Détection murs auto",
        "desc": "Lance la détection IA des murs et ouvertures sur un plan non encore mesuré. Un étalonnage (cote connue) reste obligatoire avant tout métré.",
        "icon": "ScanLine",
        "needs_plans": True,
        "output": "detect",
    },
    "compare": {
        "name": "Comparaison de plans",
        "desc": "Compare deux versions d'un plan (avant / après) et liste les pièces et murs ajoutés, retirés ou modifiés.",
        "icon": "GitCompare",
        "needs_plans": True,
        "output": "compare",
    },
}


def _auto_level(filename: str, idx: int) -> str:
    """Déduit un libellé de niveau depuis le nom de fichier (sinon ordre)."""
    f = (filename or "").lower()
    rules = [
        (r"sous[\s_-]?sol|ss\b|s/sol", "Sous-sol"),
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
    return ["RDC", "R+1", "R+2", "R+3", "R+4"][idx] if idx < 5 else f"Niveau {idx + 1}"


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
        raise HTTPException(422, "Agent inconnu")
    if agent != "supervise":
        await pro_required(user)
        require_feature(user, "devis" if agent in ("devis", "report") else "chantier")


async def _load_owned_plans(ids, user):
    if len(set(ids)) != len(ids) or any(not isinstance(pid, str) or not pid.strip() for pid in ids):
        raise HTTPException(422, "Sélection de plans invalide ou dupliquée")
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1, "measurements": 1, "chantier_id": 1}).to_list(51)
    if {p["plan_id"] for p in plans} != set(ids):
        raise HTTPException(404, "Un ou plusieurs plans sont introuvables pour ce compte")
    order = {pid: i for i, pid in enumerate(ids)}
    return sorted(plans, key=lambda p: order[p["plan_id"]])


@router.get("/catalog")
async def catalog(user=Depends(current_user)) -> dict:
    available = []
    for key, spec in AGENTS.items():
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
    if body.chantier_id:
        from routes.chantiers import _get
        await _get(body.chantier_id, user["user_id"])
    if body.quote_ids and body.agent != "supervise":
        raise HTTPException(422, "Sélection de devis réservée au Pilote")
    if len(set(body.quote_ids)) != len(body.quote_ids):
        raise HTTPException(422, "Sélection de devis dupliquée")
    spec = AGENTS[body.agent]
    plans = []
    if spec["needs_plans"] or body.plan_ids:
        if spec["needs_plans"] and not body.plan_ids:
            raise HTTPException(422, "Sélectionnez au moins un plan")
        if body.agent == "compare" and len(body.plan_ids) != 2:
            raise HTTPException(422, "Sélectionnez exactement 2 plans (avant / après)")
        plans = await _load_owned_plans(body.plan_ids, user)
        if body.chantier_id and any(p.get("chantier_id") != body.chantier_id for p in plans):
            raise HTTPException(422, "Un plan sélectionné appartient à un autre dossier")
    order = {pid: i for i, pid in enumerate(body.plan_ids)}
    plans.sort(key=lambda p: order.get(p["plan_id"], 99))

    # Libellés de niveau appris (corrections passées) par nom de fichier
    learned = {m["key"]: m["value"] async for m in db.agent_memory.find(
        {"user_id": user["user_id"], "kind": "level_label"}, {"_id": 0, "key": 1, "value": 1})}

    # Statut de métré par plan (déterministe, aucun calcul inventé)
    plan_status = []
    priced_total = 0
    for i, p in enumerate(plans):
        ms = p.get("measurements") or []
        priced = [m for m in ms if m.get("poste")]
        openings = sum(len(m.get("openings") or []) for m in ms)
        priced_total += len(priced)
        fname = p.get("filename") or p["plan_id"]
        level = learned.get((p.get("filename") or "").lower()[:120]) or _auto_level(p.get("filename"), i)
        plan_status.append({
            "plan_id": p["plan_id"], "filename": fname,
            "level": level,
            "measures": len(ms), "priced": len(priced), "openings": openings,
            "ready": len(ms) > 0,
        })

    steps = []
    if body.agent == "supervise":
        steps = [
            {"key": "inspect", "label": "Relire les données enregistrées", "detail": "Ressources sélectionnées, ou documents rattachés au dossier (200 par type maximum)." if body.chantier_id else "Ressources sélectionnées, ou ressources du compte (200 plans et 200 devis maximum)."},
            {"key": "check", "label": "Contrôler la cohérence", "detail": "Échelles par page, géométrie, ouvertures, surfaces, quantités, prix et totaux des devis."},
            {"key": "repair", "label": "Corriger puis vérifier à nouveau", "detail": "En mode correction : uniquement les valeurs dérivées recalculables. Historique et restauration ; aucune modification d'un devis engagé."},
        ]
    if body.agent in ("report", "devis"):
        steps.append({"key": "group", "label": f"Regrouper {len(plans)} plan(s) en niveaux",
                      "detail": " · ".join(f"{s['filename']} → {s['level']}" for s in plan_status)})
        steps.append({"key": "metre", "label": "Relever le métré (murs, ouvertures, surfaces)",
                      "detail": f"{sum(s['measures'] for s in plan_status)} mesures · "
                                f"{sum(s['openings'] for s in plan_status)} ouvertures détectées"})
        steps.append({"key": "chiffrage", "label": "Chiffrer avec vos prix (moteur déterministe)",
                      "detail": f"{priced_total} mesure(s) déjà affectée(s) à un poste"})
    if body.agent == "report":
        steps.append({"key": "pdf", "label": "Générer le dossier PDF complet",
                      "detail": "Page de garde + métré par niveau + chiffrage + total TTC"})
    elif body.agent == "devis":
        steps.append({"key": "quote", "label": "Créer le devis consolidé modifiable",
                      "detail": "Un poste par ouvrage, regroupé par niveau"})
    elif body.agent == "metre":
        steps.append({"key": "summary", "label": "Produire la synthèse de métré",
                      "detail": f"{len(plans)} plan(s) analysé(s)"})
    elif body.agent == "detect":
        steps.append({"key": "detect", "label": "Détecter les murs et ouvertures (IA)",
                      "detail": f"{len(plans)} plan(s) · rendu sémantique murs + portes/fenêtres"})
        steps.append({"key": "calibrate", "label": "Étalonnage OBLIGATOIRE avant métré",
                      "detail": "Ouvrez le plan et saisissez une cote connue : sans échelle fiable, aucune longueur n'est calculée."})
    elif body.agent == "compare":
        a, b = plan_status[0], plan_status[1]
        steps.append({"key": "compare", "label": "Rapprocher pièces et murs des 2 versions",
                      "detail": f"Avant : {a['filename']} · Après : {b['filename']}"})
        steps.append({"key": "diff", "label": "Lister les écarts (ajoutés / retirés / modifiés)",
                      "detail": "Pièces et murs"})

    warnings = [f"« {s['filename']} » n'a aucune mesure tracée — à compléter dans l'éditeur de plan avant chiffrage."
                for s in plan_status if not s["ready"]]
    if body.agent in ("report", "devis") and priced_total == 0:
        warnings.append("Aucune mesure n'est affectée à un poste : le chiffrage sera vide tant que vous n'aurez pas associé des postes aux mesures.")

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
                rows.append({**s, "error": "Détection indisponible sur ce plan", "walls": 0, "openings": 0})
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
            raise HTTPException(502, "Aucun plan n'a pu être analysé")
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
        raise HTTPException(404, "Exécution introuvable")
    await _authorize_agent(run["agent"], user)
    claimed = await db.agent_runs.find_one_and_update(
        {"run_id": run_id, "user_id": user["user_id"], "status": "proposed"},
        {"$set": {"status": "running", "worker": secrets.token_hex(16), "exec_params": body.model_dump(),
                  "lease_until": (datetime.now(timezone.utc) + timedelta(seconds=AGENT_LEASE_SECONDS)).isoformat(), "started_at": _now()}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if not claimed:
        raise HTTPException(409, "Cette tâche est déjà lancée ou terminée ; consultez son résultat")
    await _run_agent_job(claimed)
    completed = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if completed.get("status") != "done":
        raise HTTPException(409, completed.get("error") or "Exécution interrompue")
    return {"ok": True, "result": completed["result"]}


@router.post("/{run_id}/launch")
async def launch_run(run_id: str, body: ExecIn, user=Depends(current_user)) -> dict:
    """Met l'exécution en file d'attente : elle tourne en arrière-plan côté serveur
    (survit au changement de page). L'avancement se suit via /agents/runs et /agents/active."""
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Exécution introuvable")
    await _authorize_agent(run["agent"], user)
    if run.get("status") == "queued":
        return {"queued": True, "run_id": run_id}
    changed = await db.agent_runs.update_one(
        {"run_id": run_id, "user_id": user["user_id"], "status": "proposed"},
        {"$set": {"status": "queued", "exec_params": body.model_dump(), "queued_at": _now(),
                  "result": None, "error": None}})
    if not changed.matched_count:
        raise HTTPException(409, "Cette tâche est déjà lancée ou terminée ; consultez son résultat")
    return {"queued": True, "run_id": run_id}


@router.get("/{run_id}/checks")
async def run_checks(run_id: str, offset: int = 0, user=Depends(current_user)):
    if not 0 <= offset <= 400:
        raise HTTPException(422, "Page invalide")
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
        raise HTTPException(409, "Tâche absente, inaccessible ou déjà terminée")
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
        query, {"_id": 0, "plan_status": 0, "steps": 0}
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
        raise HTTPException(404, "Exécution introuvable")
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
        raise HTTPException(404, "Exécution introuvable")
    await _authorize_agent(run["agent"], user)
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
        steps.append({"key": "group", "label": f"Regrouper {len(new_status)} plan(s) en niveaux",
                      "detail": " · ".join(f"{s['filename']} → {s['level']}" for s in new_status)})
        steps.append({"key": "metre", "label": "Relever le métré (murs, ouvertures, surfaces)",
                      "detail": f"{sum(s['measures'] for s in new_status)} mesures · "
                                f"{sum(s['openings'] for s in new_status)} ouvertures"})
        steps.append({"key": "chiffrage", "label": "Chiffrer avec vos prix (moteur déterministe)",
                      "detail": f"{sum(s['priced'] for s in new_status)} mesure(s) affectée(s)"})
    if agent == "report":
        steps.append({"key": "pdf", "label": "Régénérer le dossier PDF corrigé", "detail": "Avec vos corrections"})
    elif agent == "devis":
        steps.append({"key": "quote", "label": "Recréer le devis corrigé", "detail": "Avec vos corrections"})
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

async def _agent_notify(run_id: str, uid: str, status: str, agent_name: str) -> None:
    if status not in ("done", "error"):
        return
    await db.notifications.update_one(
        {"user_id": uid, "notif_id": "n_agent_" + run_id},
        {"$set": {"notif_id": "n_agent_" + run_id, "user_id": uid, "type": "agent",
                  "title": "Agent terminé" if status == "done" else "Agent en échec",
                  "message": (f"{agent_name} : résultat prêt" if status == "done"
                              else f"{agent_name} : l'exécution a échoué"),
                  "link": f"/agents?run={run_id}", "read": False, "created_at": _now()}},
        upsert=True)


async def _finish_agent(run, status, result=None, error=None):
    changed = await db.agent_runs.update_one(
        {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running", "worker": run["worker"]},
        {"$set": {"status": status, "result": result, "error": error, "executed_at": _now()},
         "$unset": {"lease_until": "", "worker": ""}})
    if changed.matched_count:
        await _agent_notify(run["run_id"], run["user_id"], status, AGENTS[run["agent"]]["name"])


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
                raise HTTPException(403, "Le rattachement du compte a changé")
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
            raise HTTPException(403, "Le rattachement du compte a changé")
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
        await _finish_agent(run, "error", error="Traitement interrompu ou autorisation retirée. Vérifiez les corrections déjà effectuées avant de relancer.")
        raise
    except HTTPException as exc:
        await _finish_agent(run, "error", error=str(exc.detail)[:300])
    except Exception as exc:  # noqa: BLE001 -- no provider secrets in client errors
        log.error("Agent run %s failed (%s)", run["run_id"], type(exc).__name__)
        await _finish_agent(run, "error", error="Traitement interrompu. Consultez les résultats partiels avant de créer une nouvelle tâche.")
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
            {"$set": {"status": "error", "error": "Traitement interrompu (redémarrage). Vérifiez les résultats partiels.", "executed_at": now},
             "$unset": {"lease_until": "", "worker": ""}})
        if changed.matched_count:
            await _agent_notify(run["run_id"], run["user_id"], "error", AGENTS.get(run["agent"], {}).get("name", "Agent"))
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
