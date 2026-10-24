"""Visto do engenheiro — pedir a um engenheiro parceiro que reveja e vise o anteprojeto do autopiloto BET.

Porta do módulo francês «visa BET». O engenheiro recebe uma ligação com token (sem conta), consulta a
síntese, descarrega as plantas de cofragem e armaduras (PDF determinístico já existente) e visa ou
emite reservas. O visto é uma revisão profissional registada na plataforma — não substitui o termo
de responsabilidade do autor do projeto de estabilidade (art.º 10.º do RJUE).
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user
from engines import structuro_autopilot as autopilot
from engines.access import require_level
from engines.nom_fichier import content_disposition, nom_document, sujet_lisible
from engines.structuro_coffrage import build_coffrage_pdf

bet_visto_router = APIRouter(prefix="/structuro/bet", tags=["bet-visto"], dependencies=[Depends(require_level("pro"))])
bet_visto_public = APIRouter(prefix="/publico/bet-visto", tags=["bet-visto-publico"])

RESERVA = ("Plantas produzidas automaticamente pelo autopiloto BET ConstruPilot (cálculos determinísticos segundo o "
           "Eurocódigo 2 / NP EN 1992). Constituem um ANTEPROJETO: têm de ser verificadas, completadas e VISADAS por um "
           "engenheiro civil habilitado antes de qualquer execução. O visto registado nesta plataforma não substitui o "
           "termo de responsabilidade do autor do projeto de estabilidade (art.º 10.º do RJUE).")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _owned_dossier(dossier_id: str, user_id: str) -> dict:
    d = await db.bet_dossiers.find_one({"dossier_id": dossier_id, "user_id": user_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Processo não encontrado.")
    return d


def _public_visto(v: dict) -> dict:
    return {k: v.get(k) for k in ("visto_id", "status", "project_name", "engineer_name", "engineer_title", "signatory",
                                  "title", "ordem_numero", "comment", "decided_at", "created_at", "summary",
                                  "soil_confirmed", "reserva")}


async def _render_cofragem(dossier: dict, owner_id: str) -> bytes:
    ap = dossier.get("autopilot") or {}
    sid = ap.get("calc_study_id")
    if not sid:
        raise HTTPException(422, "Nenhum anteprojeto gerado para este processo.")
    study = await db.structuro_calculations.find_one({"study_id": sid, "user_id": owner_id}, {"_id": 0})
    if not study:
        raise HTTPException(404, "Estudo de cálculo não encontrado.")
    model = study.get("model") or {}
    summary = ap.get("summary") or {}
    soil = ap.get("soil") or (study.get("autopilot_origin") or {}).get("soil") or {}
    marks = autopilot.element_marks(model)
    return await run_in_threadpool(build_coffrage_pdf, model, study.get("revision", 1),
                                   model.get("title", dossier.get("title") or "Autopiloto BET"),
                                   summary.get("superstructure"), summary.get("metre"), marks, summary, soil,
                                   ap.get("inputs") or {})


class VistoPedidoIn(BaseModel):
    engineer_name: str = Field(min_length=2, max_length=120)
    engineer_email: EmailStr
    engineer_title: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=800)


@bet_visto_router.post("/studies/{dossier_id}/visto")
async def pedir_visto(dossier_id: str, body: VistoPedidoIn, user=Depends(current_user)) -> dict:
    """Cria (ou renova) um pedido de visto e envia a ligação ao engenheiro."""
    d = await _owned_dossier(dossier_id, user["user_id"])
    ap = d.get("autopilot") or {}
    if not ap.get("calc_study_id"):
        raise HTTPException(422, "Gere primeiro o anteprojeto (autopiloto BET) antes de pedir o visto.")
    summary = ap.get("summary") or {}
    v = {"visto_id": "visto_" + secrets.token_hex(6), "token": secrets.token_urlsafe(24),
         "dossier_id": dossier_id, "user_id": user["user_id"], "calc_study_id": ap["calc_study_id"],
         "project_name": d.get("title") or "Anteprojeto BET",
         "engineer_name": body.engineer_name.strip(), "engineer_email": str(body.engineer_email).lower(),
         "engineer_title": body.engineer_title.strip(), "message": body.message.strip(),
         "status": "pendente", "signatory": None, "title": None, "ordem_numero": None, "comment": None,
         "decided_at": None, "created_at": _now(), "reserva": RESERVA,
         "summary": {k: summary.get(k) for k in ("total_elements", "n_footings", "footing_type", "max_footing_dim_m", "floor_system")},
         "soil_confirmed": bool((ap.get("soil") or {}).get("q_confirmed", False))}
    await db.bet_vistos.delete_many({"dossier_id": dossier_id, "user_id": user["user_id"], "status": "pendente"})
    await db.bet_vistos.insert_one(dict(v))
    share = f"/visto-bet/{v['token']}"
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    link = f"{base}{share}" if base.startswith("http") else share
    sent = False
    try:
        from engines.emailer import send_email, wrap_html
        pro = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "company": 1})
        empresa = (pro or {}).get("company") or "ConstruPilot"
        html = wrap_html("Pedido de visto de engenheiro",
                         f"<p>Olá {v['engineer_name']},</p><p>{empresa} pede-lhe que reveja e vise o anteprojeto de estrutura "
                         f"«{v['project_name']}» gerado pelo autopiloto BET ConstruPilot (cálculos determinísticos, Eurocódigo 2).</p>"
                         + (f"<p><i>{v['message']}</i></p>" if v["message"] else "")
                         + "<p>Pode consultar a síntese, descarregar as plantas de cofragem e armaduras (PDF) e visar ou emitir reservas.</p>",
                         cta_url=link if link.startswith("http") else None, cta_label="Consultar e visar")
        await send_email(v["engineer_email"], f"Pedido de visto — {v['project_name']}", html)
        sent = True
    except Exception:  # noqa: BLE001
        sent = False
    return {"ok": True, "visto_id": v["visto_id"], "status": "pendente", "email_sent": sent, "share_url": share, "share_link": link}


@bet_visto_router.get("/studies/{dossier_id}/visto")
async def obter_visto(dossier_id: str, user=Depends(current_user)) -> dict:
    await _owned_dossier(dossier_id, user["user_id"])
    docs = await db.bet_vistos.find({"dossier_id": dossier_id, "user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(1)
    if not docs:
        return {"visto": None}
    v = docs[0]
    return {"visto": {**_public_visto(v), "share_url": f"/visto-bet/{v['token']}", "engineer_email": v.get("engineer_email")}}


async def _visto(token: str) -> dict:
    v = await db.bet_vistos.find_one({"token": token}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Ligação de visto inválida ou expirada.")
    return v


@bet_visto_public.get("/{token}")
async def ver_visto(token: str) -> dict:
    v = await _visto(token)
    return {**_public_visto(v), "cofragem_pdf": f"/publico/bet-visto/{token}/cofragem.pdf"}


@bet_visto_public.get("/{token}/cofragem.pdf")
async def visto_pdf(token: str):
    v = await _visto(token)
    d = await db.bet_dossiers.find_one({"dossier_id": v["dossier_id"], "user_id": v["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Processo não encontrado.")
    pdf = await _render_cofragem(d, v["user_id"])
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Anteprojeto-BET", sujet_lisible(d.get("title"))), inline=True)})


class VistoAssinarIn(BaseModel):
    signatory: str = Field(min_length=2, max_length=120)
    title: str = Field(default="", max_length=120)
    ordem_numero: str = Field(default="", max_length=60)
    decision: str = Field(pattern="^(visar|recusar)$")
    comment: str = Field(default="", max_length=1500)


@bet_visto_public.post("/{token}/assinar")
async def assinar_visto(token: str, body: VistoAssinarIn) -> dict:
    v = await _visto(token)
    if v["status"] != "pendente":
        raise HTTPException(409, "Este pedido de visto já foi respondido.")
    if body.decision == "recusar" and not body.comment.strip():
        raise HTTPException(422, "Indique o motivo ou as reservas.")
    status = "visado" if body.decision == "visar" else "recusado"
    patch = {"status": status, "signatory": body.signatory.strip(), "title": body.title.strip(),
             "ordem_numero": body.ordem_numero.strip(), "comment": body.comment.strip(), "decided_at": _now()}
    await db.bet_vistos.update_one({"token": token}, {"$set": patch})
    await db.bet_dossiers.update_one({"dossier_id": v["dossier_id"], "user_id": v["user_id"]},
                                     {"$set": {"autopilot_visto": {k: patch[k] for k in patch}}})
    try:
        from engines.emailer import send_email, wrap_html
        pro = await db.users.find_one({"user_id": v["user_id"]}, {"_id": 0, "email": 1})
        if pro and pro.get("email"):
            lab = "visado" if status == "visado" else "recusado (reservas)"
            await send_email(pro["email"], f"Anteprojeto BET {lab} — {v['project_name']}",
                             wrap_html(f"Anteprojeto {lab}", f"<p>O engenheiro <b>{patch['signatory']}</b> deixou o anteprojeto "
                                       f"«{v['project_name']}» {lab}.</p>" + (f"<p>Comentário: {patch['comment']}</p>" if patch["comment"] else "")))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "status": status, "signatory": patch["signatory"], "decided_at": patch["decided_at"]}
