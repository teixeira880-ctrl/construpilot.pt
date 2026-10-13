"""Espace Client & Sous-traitant — Sprint 2 : messagerie par canaux (pièces jointes via stockage objet),
signalement de problème → réserve, suivi et confirmation client, notifications (cloche + e-mail)."""
import asyncio
import io
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.db import db
from core.rate_limit import limiter
from core.security import current_user, pro_required
from engines import storage
from routes.chantiers import _get as get_chantier_owned
from routes.portal import _frontend_url, _iso, _now, _require_ref, current_participant

logger = logging.getLogger(__name__)
pro_router = APIRouter(prefix="/chantiers", tags=["portal-pro"], dependencies=[Depends(pro_required)])
router = APIRouter(prefix="/portal", tags=["portal"])

CHANNELS = ("client", "subcontractors")
MAX_FILES = 5
MAX_FILE_BYTES = 8 * 1024 * 1024
ALLOWED_CT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
ISSUE_STATUS = ("new", "in_progress", "scheduled", "resolved", "closed")
ISSUE_LABELS = {"new": "Novo", "in_progress": "Assumido", "scheduled": "Planeado", "resolved": "Resolvido", "closed": "Encerrado"}
URGENCY = ("low", "normal", "high")
EMAIL_COALESCE_MIN = 15


def channel_for(participant: dict) -> str:
    return "client" if participant["role"] == "client" else "subcontractors"


async def _store_uploads(files: list[UploadFile], folder: str) -> list[dict]:
    out = []
    for f in (files or [])[:MAX_FILES]:
        ext = ALLOWED_CT.get((f.content_type or "").split(";")[0].strip())
        if not ext:
            raise HTTPException(415, f'Formato não aceite ({f.filename}): fotografias JPG/PNG/WEBP ou PDF')
        data = await f.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f'Ficheiro demasiado volumoso ({f.filename}) : 8 MB máx')
        if not data:
            continue
        path = f"{storage.APP_NAME}/portal/{folder}/{uuid.uuid4().hex}.{ext}"
        res = await asyncio.to_thread(storage.put_object, path, data, f.content_type)
        out.append({"path": res.get("path", path), "name": (f.filename or f"fichier.{ext}")[:120], "content_type": f.content_type, "size": len(data)})
    return out


async def _serve(path: str) -> StreamingResponse:
    data, ct = await asyncio.to_thread(storage.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ct, headers={"Cache-Control": "private, no-store"})


async def _branding(owner_id: str) -> tuple[str, Optional[str]]:
    from routes.plans_common import _resolve_branding
    b = await _resolve_branding(owner_id) or {}
    pro = await db.users.find_one({"user_id": owner_id}, {"_id": 0, "name": 1, "email": 1})
    return b.get("company_name") or (pro or {}).get("name") or "A sua empresa", (pro or {}).get("email")


async def _email(to: str, subject: str, title: str, body_html: str, cta_url: str, cta_label: str, from_name: Optional[str] = None) -> str:
    from engines.emailer import send_email, wrap_html
    try:
        await send_email(to, subject, wrap_html(title, body_html, cta_url=cta_url, cta_label=cta_label), from_name=from_name)
        return "sent"
    except Exception as e:  # noqa: BLE001
        logger.warning("portal email failed (%s): %s", subject, e)
        return "failed"


async def _coalesced(key: str) -> bool:
    """Vrai si un e-mail portant cette clé a déjà été envoyé dans la fenêtre → on n'en renvoie pas."""
    since = _now() - timedelta(minutes=EMAIL_COALESCE_MIN)
    if await db.portal_email_log.find_one({"key": key, "sent_at": {"$gte": since}}, {"_id": 1}):
        return True
    await db.portal_email_log.insert_one({"key": key, "sent_at": _now()})
    return False


async def _notify_pro(owner_id: str, ntype: str, message: str, url: str, subject: str, body_html: str, coalesce_key: str) -> None:
    await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": owner_id, "type": ntype, "url": url, "read": False,
                                       "message": message, "created_at": _iso(_now())})
    pro = await db.users.find_one({"user_id": owner_id}, {"_id": 0, "email": 1})
    if pro and pro.get("email") and not await _coalesced(coalesce_key):
        await _email(pro["email"], subject, subject, body_html, f"{_frontend_url()}{url}", "Abrir o processo da obra")


async def _notify_participants(chantier: dict, channel: str, exclude_pid: Optional[str], subject: str, body_html: str) -> None:
    company, _ = await _branding(chantier["user_id"])
    q = {"chantier_id": chantier["chantier_id"], "status": "active", "permissions.chat": True,
         "role": "client" if channel == "client" else "subcontractor"}
    async for p in db.chantier_participants.find(q, {"_id": 0, "participant_id": 1, "email": 1, "chantier_ref": 1}):
        if p["participant_id"] == exclude_pid or await _coalesced(f"part:{p['participant_id']}:{channel}"):
            continue
        await _email(p["email"], subject, subject, body_html, f"{_frontend_url()}/espace/{p['chantier_ref']}?tab=messages", "Abrir a minha área de obra", from_name=company)


def _msg_doc(chantier: dict, channel: str, author_type: str, author_id: str, author_name: str, body: str, attachments: list[dict]) -> dict:
    return {"message_id": "msg_" + secrets.token_hex(6), "chantier_id": chantier["chantier_id"], "owner_user_id": chantier["user_id"], "channel": channel,
            "author_type": author_type, "author_id": author_id, "author_name": author_name, "body": body.strip(), "attachments": attachments,
            "read_by": [author_id], "created_at": _iso(_now())}


async def _list_messages(chantier_id: str, channel: str, reader_id: str, since: Optional[str]) -> list[dict]:
    q = {"chantier_id": chantier_id, "channel": channel}
    if since:
        q["created_at"] = {"$gt": since}
    rows = await db.chantier_messages.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    unread = [r["message_id"] for r in rows if reader_id not in (r.get("read_by") or [])]
    if unread:
        await db.chantier_messages.update_many({"message_id": {"$in": unread}}, {"$addToSet": {"read_by": reader_id}})
    return rows


# ---------------------------------------------------------------- pro : messagerie
@pro_router.get("/{chantier_id}/messages")
async def pro_messages(chantier_id: str, channel: Literal["client", "subcontractors"] = "client", since: Optional[str] = None, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    return {"channel": channel, "messages": await _list_messages(chantier_id, channel, user["user_id"], since)}


@pro_router.get("/{chantier_id}/inbox")
async def pro_inbox(chantier_id: str, user=Depends(current_user)) -> dict:
    """Compteurs pour la fiche chantier : messages non lus par canal, problèmes ouverts."""
    await get_chantier_owned(chantier_id, user["user_id"])
    unread = {}
    for ch in CHANNELS:
        unread[ch] = await db.chantier_messages.count_documents({"chantier_id": chantier_id, "channel": ch, "read_by": {"$ne": user["user_id"]}})
    open_issues = await db.chantier_issues.count_documents({"chantier_id": chantier_id, "status": {"$in": ["new", "in_progress", "scheduled"]}})
    new_issues = await db.chantier_issues.count_documents({"chantier_id": chantier_id, "status": "new"})
    return {"unread": unread, "open_issues": open_issues, "new_issues": new_issues}


@pro_router.post("/{chantier_id}/messages", status_code=201)
async def pro_send_message(chantier_id: str, channel: Literal["client", "subcontractors"] = Form(...), body: str = Form("", max_length=4000),
                           files: list[UploadFile] = File([]), user=Depends(current_user)) -> dict:
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    if not body.strip() and not files:
        raise HTTPException(422, "Message vide")
    company, _ = await _branding(user["user_id"])
    attachments = await _store_uploads(files, f"{chantier_id}/messages")
    doc = _msg_doc(chantier, channel, "pro", user["user_id"], company, body, attachments)
    await db.chantier_messages.insert_one(dict(doc))
    doc.pop("_id", None)
    excerpt = (doc["body"] or f'{len(attachments)} anexo(s)')[:300]
    asyncio.create_task(_notify_participants(chantier, channel, None, f"Nova mensagem de {company} — obra {chantier['name']}",
                                             f"<p><strong>{company}</strong> escreveu-lhe a propósito da obra <strong>{chantier['name']}</strong> :</p><blockquote>{excerpt}</blockquote>"))
    return doc


@pro_router.get("/{chantier_id}/messages/file")
async def pro_message_file(chantier_id: str, path: str, user=Depends(current_user)):
    await get_chantier_owned(chantier_id, user["user_id"])
    ok = await db.chantier_messages.find_one({"chantier_id": chantier_id, "attachments.path": path}, {"_id": 1}) \
        or await db.chantier_issues.find_one({"chantier_id": chantier_id, "photos.path": path}, {"_id": 1})
    if not ok:
        raise HTTPException(404, "Ficheiro não encontrado")
    return await _serve(path)


# ---------------------------------------------------------------- pro : problèmes signalés
class IssueUpdateIn(BaseModel):
    status: Optional[Literal["new", "in_progress", "scheduled", "resolved", "closed"]] = None
    assignee: Optional[str] = Field(None, max_length=120)
    target_date: Optional[str] = Field(None, max_length=10)
    pro_response: Optional[str] = Field(None, max_length=3000)


@pro_router.get("/{chantier_id}/issues")
async def pro_issues(chantier_id: str, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    rows = await db.chantier_issues.find({"chantier_id": chantier_id}, {"_id": 0}).sort("created_at", -1).to_list(300)
    return {"issues": rows, "labels": ISSUE_LABELS}


@pro_router.put("/{chantier_id}/issues/{issue_id}")
async def pro_update_issue(chantier_id: str, issue_id: str, body: IssueUpdateIn, user=Depends(current_user)) -> dict:
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    issue = await db.chantier_issues.find_one({"issue_id": issue_id, "chantier_id": chantier_id}, {"_id": 0})
    if not issue:
        raise HTTPException(404, "Sinalização não encontrada")
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(422, "Nenhuma alteração")
    now = _iso(_now())
    history = list(issue.get("history") or [])
    for k, v in changes.items():
        if issue.get(k) != v:
            history.append({"at": now, "by": "pro", "field": k, "value": v})
    if "status" in changes and changes["status"] != issue.get("status"):
        changes["client_confirmed"] = None if changes["status"] == "resolved" else issue.get("client_confirmed")
        if issue.get("reserve_id"):
            lifted = changes["status"] in ("resolved", "closed")
            await db.site_reserves.update_one({"reserve_id": issue["reserve_id"]}, {"$set": {"status": "lifted" if lifted else "open", "lifted_at": now if lifted else None}})
    await db.chantier_issues.update_one({"issue_id": issue_id}, {"$set": {**changes, "history": history, "updated_at": now}})
    updated = await db.chantier_issues.find_one({"issue_id": issue_id}, {"_id": 0})
    if "status" in changes or "pro_response" in changes:
        asyncio.create_task(_notify_reporter(chantier, updated))
    return updated


async def _notify_reporter(chantier: dict, issue: dict) -> None:
    p = await db.chantier_participants.find_one({"participant_id": issue["participant_id"], "status": "active"}, {"_id": 0, "email": 1, "chantier_ref": 1})
    if not p:
        return
    company, _ = await _branding(chantier["user_id"])
    label = ISSUE_LABELS.get(issue.get("status"), issue.get("status"))
    resp = f"<p>Resposta da empresa:</p><blockquote>{issue['pro_response'][:800]}</blockquote>" if issue.get("pro_response") else ""
    confirm = "<p>Diga-nos na sua área se o problema ficou resolvido.</p>" if issue.get("status") == "resolved" else ""
    await _email(p["email"], f"A sua sinalização «{issue['title'][:60]} » — {label}", f'Sinalização: {label}',
                 f"<p>Obra <strong>{chantier['name']}</strong> — a sua sinalização <strong>{issue['title']}</strong> passou ao estado <strong>{label}</strong>.</p>{resp}{confirm}",
                 f"{_frontend_url()}/espace/{p['chantier_ref']}?tab=issues", "Ver o acompanhamento", from_name=company)


# ---------------------------------------------------------------- participant : messagerie
async def _chat_ctx(ref: str, p: dict, perm: str) -> dict:
    _require_ref(p, ref)
    if not (p.get("permissions") or {}).get(perm):
        raise HTTPException(403, "Esta função não está ativada para o seu acesso")
    c = await db.chantiers.find_one({"chantier_id": p["chantier_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Obra não encontrada")
    return c


@router.get("/{ref}/messages")
async def portal_messages(ref: str, since: Optional[str] = None, p=Depends(current_participant)) -> dict:
    await _chat_ctx(ref, p, "chat")
    company, _ = await _branding(p["owner_user_id"])
    return {"channel": channel_for(p), "company": company, "messages": await _list_messages(p["chantier_id"], channel_for(p), p["participant_id"], since)}


@router.post("/{ref}/messages", status_code=201)
@limiter.limit("60/hour")
async def portal_send_message(ref: str, request: Request, response: Response, body: str = Form("", max_length=4000), files: list[UploadFile] = File([]),
                              p=Depends(current_participant)) -> dict:
    chantier = await _chat_ctx(ref, p, "chat")
    if not body.strip() and not files:
        raise HTTPException(422, "Message vide")
    attachments = await _store_uploads(files, f"{p['chantier_id']}/messages")
    doc = _msg_doc(chantier, channel_for(p), "participant", p["participant_id"], p.get("name") or p["email"], body, attachments)
    await db.chantier_messages.insert_one(dict(doc))
    doc.pop("_id", None)
    who = doc["author_name"]
    excerpt = (doc["body"] or f'{len(attachments)} anexo(s)')[:300]
    url = f"/chantiers/{chantier['chantier_id']}?tab=messages&channel={doc['channel']}"
    asyncio.create_task(_notify_pro(chantier["user_id"], "portal_message", f"Mensagem de {who} na obra {chantier['name']}", url,
                                    f"Nova mensagem — obra {chantier['name']}", f"<p><strong>{who}</strong> ({('client' if p['role'] == 'client' else 'sous-traitant')}) escreveu-lhe:</p><blockquote>{excerpt}</blockquote>",
                                    f"pro:{chantier['chantier_id']}:{doc['channel']}"))
    return doc


@router.get("/{ref}/messages/file")
async def portal_message_file(ref: str, path: str, p=Depends(current_participant)):
    _require_ref(p, ref)
    ok = await db.chantier_messages.find_one({"chantier_id": p["chantier_id"], "channel": channel_for(p), "attachments.path": path}, {"_id": 1}) \
        or await db.chantier_issues.find_one({"chantier_id": p["chantier_id"], "participant_id": p["participant_id"], "photos.path": path}, {"_id": 1})
    if not ok:
        raise HTTPException(404, "Ficheiro não encontrado")
    return await _serve(path)


# ---------------------------------------------------------------- participant : signalement de problème
@router.get("/{ref}/issues")
async def portal_issues(ref: str, p=Depends(current_participant)) -> dict:
    await _chat_ctx(ref, p, "report_issue")
    rows = await db.chantier_issues.find({"chantier_id": p["chantier_id"], "participant_id": p["participant_id"]}, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(200)
    return {"issues": rows, "labels": ISSUE_LABELS}


@router.post("/{ref}/issues", status_code=201)
@limiter.limit("20/hour")
async def portal_report_issue(ref: str, request: Request, response: Response, title: str = Form(..., min_length=3, max_length=160), description: str = Form("", max_length=3000),
                              location: str = Form("", max_length=120), urgency: Literal["low", "normal", "high"] = Form("normal"), files: list[UploadFile] = File([]),
                              p=Depends(current_participant)) -> dict:
    chantier = await _chat_ctx(ref, p, "report_issue")
    photos = await _store_uploads(files, f"{p['chantier_id']}/issues")
    now = _iso(_now())
    reporter = p.get("name") or p["email"]
    reserve = {"reserve_id": "rs_" + secrets.token_hex(6), "user_id": chantier["user_id"], "project": chantier["name"], "doc_id": None, "chantier_id": chantier["chantier_id"],
               "lot": (location or p.get("lot") or "").strip()[:80], "description": f'[Assinalado por {reporter}] {title.strip()}', "company": "", "company_email": "",
               "photos": [ph["path"] for ph in photos], "status": "open", "created_at": now, "lifted_at": None, "source": "portal_issue"}
    issue = {"issue_id": "iss_" + secrets.token_hex(6), "chantier_id": chantier["chantier_id"], "owner_user_id": chantier["user_id"], "participant_id": p["participant_id"],
             "reporter_name": reporter, "reporter_role": p["role"], "title": title.strip(), "description": description.strip(), "location": location.strip(),
             "urgency": urgency, "photos": photos, "status": "new", "assignee": "", "target_date": None, "pro_response": "", "client_confirmed": None,
             "reserve_id": reserve["reserve_id"], "history": [{"at": now, "by": "participant", "field": "status", "value": "new"}], "created_at": now, "updated_at": now}
    reserve["issue_id"] = issue["issue_id"]
    await db.site_reserves.insert_one(dict(reserve))
    await db.chantier_issues.insert_one(dict(issue))
    issue.pop("_id", None)
    url = f"/chantiers/{chantier['chantier_id']}?tab=issues"
    urg = {"low": "faible", "normal": "normale", "high": "URGENT"}[urgency]
    asyncio.create_task(_notify_pro(chantier["user_id"], "portal_issue", f"Problema assinalado por {reporter} sur {chantier['name']} : {title[:60]}", url,
                                    f"Problema assinalado — obra {chantier['name']}",
                                    f"<p><strong>{reporter}</strong> assinala: <strong>{title}</strong> (urgência {urg}{(', ' + location if location else '')}).</p><p>{description[:600]}</p><p>Foi criada automaticamente uma reserva no acompanhamento da obra.</p>",
                                    f"pro:{chantier['chantier_id']}:issue:{issue['issue_id']}"))
    return issue


class ConfirmIn(BaseModel):
    resolved: bool
    comment: str = Field("", max_length=1000)


@router.post("/{ref}/issues/{issue_id}/confirm")
async def portal_confirm_issue(ref: str, issue_id: str, body: ConfirmIn, p=Depends(current_participant)) -> dict:
    chantier = await _chat_ctx(ref, p, "report_issue")
    issue = await db.chantier_issues.find_one({"issue_id": issue_id, "chantier_id": p["chantier_id"], "participant_id": p["participant_id"]}, {"_id": 0})
    if not issue:
        raise HTTPException(404, "Sinalização não encontrada")
    if issue.get("status") not in ("resolved", "closed"):
        raise HTTPException(409, "A empresa ainda não marcou este problema como resolvido")
    now = _iso(_now())
    status = "closed" if body.resolved else "in_progress"
    hist = list(issue.get("history") or []) + [{"at": now, "by": "participant", "field": "client_confirmed", "value": body.resolved, "comment": body.comment}]
    await db.chantier_issues.update_one({"issue_id": issue_id}, {"$set": {"client_confirmed": body.resolved, "client_comment": body.comment, "status": status, "history": hist, "updated_at": now}})
    if issue.get("reserve_id"):
        await db.site_reserves.update_one({"reserve_id": issue["reserve_id"]}, {"$set": {"status": "lifted" if body.resolved else "open", "lifted_at": now if body.resolved else None}})
    reporter = p.get("name") or p["email"]
    verdict = "confirma que está resolvido" if body.resolved else "indica que o problema NÃO está resolvido"
    asyncio.create_task(_notify_pro(chantier["user_id"], "portal_issue", f"{reporter} {verdict} : {issue['title'][:60]}", f"/chantiers/{chantier['chantier_id']}?tab=issues",
                                    f"Resposta do cliente — {issue['title'][:60]}", f"<p><strong>{reporter}</strong> {verdict} para a sinalização <strong>{issue['title']}</strong>.</p>{('<p>' + body.comment + '</p>' if body.comment else '')}",
                                    f"pro:{chantier['chantier_id']}:confirm:{issue_id}:{now}"))
    return {"ok": True, "status": status, "client_confirmed": body.resolved}
