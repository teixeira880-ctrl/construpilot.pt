"""Documents pro — devis, factures, avoirs (modèle générique + éditeur).

- Devis vide OU importé depuis un plan/PC analysé par l'IA (lignes éditables).
- Modifiable même après envoi/signature.
- Base commune pour les factures et avoirs (étape suivante).
"""
from __future__ import annotations

import base64
import hashlib
import json
import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from core.db import db
from core.security import current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"], prefix="/documents")

DOC_TYPES = ("quote", "invoice", "credit_note")
PREFIX = {"quote": "DEV", "invoice": "FAC", "credit_note": "AV"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocLine(BaseModel):
    designation: str = ""
    description: str = ""
    unit: str = "u"
    qty: float = 1
    unit_price_ht: float = 0
    vat_rate: float = 10
    category: str = ""


class DocIn(BaseModel):
    doc_type: str = "quote"
    client_id: str | None = None
    title: str = ""
    lines: list[DocLine] = []
    notes: str = ""
    payment_terms: str = ""
    deposit_pct: float = Field(default=0, ge=0, le=100)
    status: str | None = None


def _compute_totals(lines: list[dict], deposit_pct: float = 0.0) -> dict:
    ht = 0.0
    tva_map: dict[float, float] = {}
    for ln in lines:
        line_ht = round((ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0), 2)
        ht += line_ht
        rate = float(ln.get("vat_rate") or 0)
        tva_map[rate] = round(tva_map.get(rate, 0) + line_ht * rate / 100, 2)
    ht = round(ht, 2)
    tva = round(sum(tva_map.values()), 2)
    ttc = round(ht + tva, 2)
    deposit = round(ttc * (deposit_pct or 0) / 100, 2)
    return {
        "ht": ht,
        "tva_breakdown": {str(k): v for k, v in sorted(tva_map.items())},
        "tva": tva, "ttc": ttc,
        "deposit_pct": deposit_pct or 0, "deposit_amount": deposit,
        "remaining": round(ttc - deposit, 2),
    }


async def _client_snapshot(client_id: str | None, user: dict) -> dict | None:
    if not client_id:
        return None
    c = await db.clients.find_one(
        {"client_id": client_id, "user_id": user["user_id"]}, {"_id": 0})
    if not c:
        return None
    keys = ("client_id", "first_name", "last_name", "company", "email",
            "phone", "address", "postal_code", "city", "siret")
    return {k: c.get(k, "") for k in keys}


async def _next_number(user_id: str, doc_type: str) -> str:
    year = datetime.now(timezone.utc).year
    res = await db.doc_counters.find_one_and_update(
        {"user_id": user_id, "doc_type": doc_type, "year": year},
        {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return f"{PREFIX.get(doc_type, 'DOC')}-{year}-{res['seq']:04d}"


async def _get_owned(doc_id: str, user: dict) -> dict:
    doc = await db.pro_documents.find_one(
        {"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document introuvable")
    return doc


class DescribeIn(BaseModel):
    designation: str
    context: str = ""


@router.post("/ai/describe")
async def ai_describe_line(body: DescribeIn, user=Depends(current_user)) -> dict:
    """Suggestions IA : génère une description de prestations pour une ligne de devis."""
    designation = (body.designation or "").strip()
    if not designation:
        raise HTTPException(400, "Indiquez d'abord une désignation de ligne")
    from engines.ai import suggest_line_description
    try:
        text = await suggest_line_description(designation, (body.context or "").strip()[:400])
    except Exception as e:
        logging.getLogger("documents").exception("ai describe failed")
        raise HTTPException(502, f"Suggestion IA indisponible : {type(e).__name__}")
    return {"description": (text or "").strip()}


@router.post("")
async def create_document(body: DocIn, user=Depends(current_user)) -> dict:
    dtype = body.doc_type if body.doc_type in DOC_TYPES else "quote"
    lines = [ln.model_dump() for ln in body.lines]
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": dtype,
        "number": None,
        "title": (body.title or "").strip()[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        "status": body.status or "draft",
        "lines": lines,
        "notes": (body.notes or "").strip()[:2000],
        "payment_terms": (body.payment_terms or "").strip()[:300],
        "deposit_pct": body.deposit_pct or 0,
        "totals": _compute_totals(lines, body.deposit_pct),
        "issue_date": None,
        "due_date": None,
        "source": "manual",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    from engines import activity
    await activity.log(user, f"{dtype}.create", "document", doc.get("title") or dtype,
                       {"doc_id": doc["doc_id"]})
    try:
        from routes.library import auto_save_from_lines
        await auto_save_from_lines(user["user_id"], doc.get("lines"))
    except Exception:
        pass
    return doc


@router.post("/from-plan/{plan_id}")
async def document_from_plan(plan_id: str, client_id: str | None = None,
                             user=Depends(current_user)) -> dict:
    """Crée un devis modifiable à partir du métré IA du plan (lignes pré-remplies)."""
    from routes.plans_common import _build_quote_and_pdf
    quote, _ = await _build_quote_and_pdf(
        plan_id, user["user_id"], "std", "carrelage", True, True, True, True)
    lines = []
    for li in quote.get("line_items", []):
        qty = li.get("quantity") or 0
        pu = round((li.get("total") or 0) / qty, 2) if qty else (li.get("total") or 0)
        lines.append({
            "designation": li.get("name") or "",
            "unit": li.get("unit") or "u",
            "qty": round(qty, 2),
            "unit_price_ht": pu,
            "vat_rate": 10,
            "category": "Depuis plan IA",
        })
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "quote",
        "number": None,
        "title": f"Devis — {quote.get('filename') or 'plan'}",
        "client_id": client_id,
        "client": await _client_snapshot(client_id, user),
        "status": "draft",
        "lines": lines,
        "notes": "",
        "payment_terms": "",
        "deposit_pct": 0,
        "totals": _compute_totals(lines, 0),
        "issue_date": None,
        "due_date": None,
        "source": "ai_plan",
        "plan_id": plan_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _transcribe_video_bytes(raw: bytes) -> str:
    """Extrait l'audio d'une vidéo (ffmpeg) et le transcrit en français (Whisper)."""
    import os
    import shutil
    import subprocess
    import tempfile
    if not raw:
        raise HTTPException(400, "Vidéo vide")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(413, "Vidéo trop volumineuse (>80 Mo). Filmez une séquence plus courte.")
    tmpdir = tempfile.mkdtemp(prefix="cp_vid_")
    src = os.path.join(tmpdir, "input")
    audio = os.path.join(tmpdir, "audio.mp3")
    try:
        with open(src, "wb") as f:
            f.write(raw)
        proc = subprocess.run(
            ["ffmpeg", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", "-y", audio],
            capture_output=True, timeout=120)
        if proc.returncode != 0 or not os.path.exists(audio):
            logging.getLogger("documents").warning("ffmpeg failed: %s", proc.stderr[-500:])
            raise HTTPException(422, "Impossible d'extraire l'audio de la vidéo.")
        if os.path.getsize(audio) > 25 * 1024 * 1024:
            raise HTTPException(413, "Audio trop long (>25 Mo). Filmez une séquence plus courte.")
        from emergentintegrations.llm.openai import OpenAISpeechToText
        stt = OpenAISpeechToText(api_key=os.environ["EMERGENT_LLM_KEY"])
        with open(audio, "rb") as af:
            resp = await stt.transcribe(file=af, model="whisper-1",
                                        response_format="text", language="fr")
        transcript = resp if isinstance(resp, str) else (getattr(resp, "text", "") or "")
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger("documents").exception("video transcription failed")
        raise HTTPException(502, f"Transcription indisponible : {type(e).__name__}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if not transcript.strip():
        raise HTTPException(422, "Aucune parole détectée dans la vidéo.")
    return transcript.strip()


async def _quote_doc_from_text(user: dict, text: str, client_id: str | None,
                               source: str = "video", images: list[str] | None = None) -> dict:
    """Génère un devis (lignes IA chiffrées via la bibliothèque) à partir d'un texte + photos."""
    from engines.ai import quote_lines_from_text
    from routes.plans_analysis import _apply_library_prices
    if not (text or "").strip():
        raise HTTPException(400, "Description vide")
    lines, title = await quote_lines_from_text(text, images=images or None)
    if not lines:
        raise HTTPException(422, "L'IA n'a pas pu générer de lignes de devis à partir de la description.")
    lines, priced = await _apply_library_prices(user["user_id"], lines)
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"], "doc_type": "quote", "number": None,
        "title": title or "Devis (vidéo)",
        "client_id": client_id, "client": await _client_snapshot(client_id, user),
        "status": "draft", "lines": lines,
        "notes": f"Description :\n{text.strip()[:1500]}",
        "payment_terms": "", "deposit_pct": 0,
        "totals": _compute_totals(lines, 0),
        "issue_date": None, "due_date": None,
        "source": source, "created_at": _now(), "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["priced_lines"] = priced
    return doc


@router.post("/video-transcribe")
async def video_transcribe(file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    """Transcrit une vidéo en texte (à relire/corriger avant génération du devis)."""
    raw = await file.read()
    transcript = await _transcribe_video_bytes(raw)
    return {"transcript": transcript}


class FromTextIn(BaseModel):
    text: str
    client_id: str | None = None
    images: list[str] = Field(default_factory=list)


@router.post("/from-text")
async def document_from_text(body: FromTextIn, user=Depends(current_user)) -> dict:
    """Crée un devis à partir d'une description (texte relu/corrigé) + photos optionnelles."""
    imgs = [(i.split(",", 1)[-1] if i.startswith("data:") else i)
            for i in (body.images or []) if i][:6]
    doc = await _quote_doc_from_text(user, body.text, body.client_id, source="video", images=imgs)
    doc["transcript"] = body.text.strip()
    return doc


@router.post("/from-video")
async def document_from_video(file: UploadFile = File(...), client_id: str | None = None,
                              user=Depends(current_user)) -> dict:
    """Crée un devis directement à partir d'une vidéo (transcription + lignes IA chiffrées)."""
    raw = await file.read()
    transcript = await _transcribe_video_bytes(raw)
    doc = await _quote_doc_from_text(user, transcript, client_id, source="video")
    doc["transcript"] = transcript
    return doc


@router.get("")
async def list_documents(doc_type: str = "", client_id: str = "", status: str = "",
                         user=Depends(current_user)) -> dict:
    query: dict = {"user_id": user["user_id"]}
    if doc_type in DOC_TYPES:
        query["doc_type"] = doc_type
    if client_id:
        query["client_id"] = client_id
    if status:
        query["status"] = status
    docs = await db.pro_documents.find(query, {"_id": 0, "lines": 0, "facturx_pdf_b64": 0}).sort(
        "created_at", -1).to_list(2000)
    return {"documents": docs, "count": len(docs)}


@router.get("/{doc_id}")
async def get_document(doc_id: str, user=Depends(current_user)) -> dict:
    return await _get_owned(doc_id, user)


@router.put("/{doc_id}")
async def update_document(doc_id: str, body: DocIn,
                          user=Depends(current_user)) -> dict:
    await _get_owned(doc_id, user)
    lines = [ln.model_dump() for ln in body.lines]
    upd = {
        "title": (body.title or "").strip()[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        "lines": lines,
        "notes": (body.notes or "").strip()[:2000],
        "payment_terms": (body.payment_terms or "").strip()[:300],
        "deposit_pct": body.deposit_pct or 0,
        "totals": _compute_totals(lines, body.deposit_pct),
        "updated_at": _now(),
        # Invalide le cache Factur-X : les lignes/totaux ont changé.
        "facturx_pdf_b64": None, "facturx_validation": None, "facturx_hash": None,
    }
    if body.status:
        upd["status"] = body.status
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]}, {"$set": upd})
    try:
        from routes.library import auto_save_from_lines
        await auto_save_from_lines(user["user_id"], upd.get("lines"))
    except Exception:
        pass
    return await _get_owned(doc_id, user)


class StatusIn(BaseModel):
    status: str


@router.patch("/{doc_id}/status")
async def set_status(doc_id: str, body: StatusIn, user=Depends(current_user)) -> dict:
    await _get_owned(doc_id, user)
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"status": body.status, "updated_at": _now()}})
    return await _get_owned(doc_id, user)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user=Depends(current_user)) -> dict:
    doc = await db.pro_documents.find_one(
        {"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0, "title": 1, "number": 1})
    res = await db.pro_documents.delete_one(
        {"doc_id": doc_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Document introuvable")
    from engines import activity
    await activity.log(user, "document.delete", "document",
                       (doc or {}).get("number") or (doc or {}).get("title") or doc_id)
    return {"ok": True}


@router.post("/issue-batch")
async def issue_batch(body: dict, user=Depends(current_user)) -> dict:
    """Émet plusieurs documents d'un coup + contrôle de conformité Factur-X (best-effort)."""
    from engines import activity
    doc_ids = (body or {}).get("doc_ids") or []
    results = []
    for did in doc_ids[:50]:
        doc = await db.pro_documents.find_one(
            {"doc_id": did, "user_id": user["user_id"]}, {"_id": 0, "doc_type": 1, "number": 1})
        if not doc:
            results.append({"doc_id": did, "ok": False, "error": "Introuvable"})
            continue
        number = doc.get("number") or await _next_number(user["user_id"], doc["doc_type"])
        await db.pro_documents.update_one(
            {"doc_id": did, "user_id": user["user_id"]},
            {"$set": {"number": number, "issue_date": _now(), "updated_at": _now()}})
        conforme = None
        if doc.get("doc_type") == "invoice":
            try:
                _d, _fx, rep, _s = await _ensure_facturx(did, user, force=True)
                conforme = bool(rep.get("valid"))
            except Exception:
                conforme = None
        await activity.log(user, "invoice.issue", "document", number, {"doc_id": did, "batch": True})
        results.append({"doc_id": did, "ok": True, "number": number, "conforme": conforme})
    issued = sum(1 for r in results if r.get("ok"))
    conformes = sum(1 for r in results if r.get("conforme"))
    return {"results": results, "issued": issued, "conformes": conformes, "count": len(results)}


@router.post("/{doc_id}/issue")
async def issue_document(doc_id: str, user=Depends(current_user)) -> dict:
    """Attribue un numéro définitif + date d'émission. Valide le Factur-X (best-effort)."""
    doc = await _get_owned(doc_id, user)
    number = doc.get("number") or await _next_number(user["user_id"], doc["doc_type"])
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"number": number, "issue_date": doc.get("issue_date") or _now(),
                  "updated_at": _now()}})
    # Contrôle de conformité Factur-X automatique (factures uniquement), non bloquant.
    if doc.get("doc_type") == "invoice":
        try:
            await _ensure_facturx(doc_id, user, force=True)
        except Exception as exc:  # quota, réseau, données incomplètes → badge "non vérifié"
            logging.getLogger("documents").info("Auto Factur-X à l'émission ignoré: %s", exc)
    from engines import activity
    await activity.log(user, "invoice.issue" if doc.get("doc_type") == "invoice" else "quote.update",
                       "document", number, {"doc_id": doc_id})
    return await _get_owned(doc_id, user)


@router.get("/{doc_id}/pdf")
async def document_pdf(doc_id: str, lang: str | None = None, user=Depends(current_user)):
    from engines.pdf_docs import build_document_pdf
    from routes.plans_common import _resolve_branding
    from routes.reviews import get_reviews_for_user
    doc = await _get_owned(doc_id, user)
    # Numérote à la volée si besoin pour que le PDF porte un numéro.
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc.get("issue_date") or _now()}})
        doc["issue_date"] = doc.get("issue_date") or _now()
    branding = await _resolve_branding(user["user_id"])
    reviews = await get_reviews_for_user(user["user_id"]) if doc["doc_type"] == "quote" else None
    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=reviews,
                                   lang=(lang or doc.get("lang") or user.get("lang")))
    fname = f"{doc.get('number') or doc['doc_id']}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class DocSendIn(BaseModel):
    client_email: str
    client_name: str = ""
    message: str = ""
    attach_3d: bool = True


@router.post("/{doc_id}/send")
async def send_document(doc_id: str, body: DocSendIn, background_tasks: BackgroundTasks,
                        user=Depends(current_user)):
    """Génère le PDF puis envoie l'email au client EN TÂCHE DE FOND (réponse immédiate)."""
    import re as _re
    import secrets as _secrets
    from engines.emailer import wrap_html
    from engines.pdf_docs import build_document_pdf
    from routes.plans_common import _resolve_branding, deliver_email
    from routes.reviews import get_reviews_for_user
    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", body.client_email or ""):
        raise HTTPException(400, "Email client invalide.")
    doc = await _get_owned(doc_id, user)
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        doc["issue_date"] = doc.get("issue_date") or _now()
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc["issue_date"]}})
    branding = await _resolve_branding(user["user_id"])
    reviews = await get_reviews_for_user(user["user_id"]) if doc["doc_type"] == "quote" else None
    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=reviews,
                                   lang=(doc.get("lang") or user.get("lang")))
    company = (branding or {}).get("company_name") or user.get("name") or "ConstruPilot"
    company_email = (branding or {}).get("company_email")
    ttc = (doc.get("totals") or {}).get("ttc") or doc.get("total_ttc") or 0
    hello = f"Bonjour {body.client_name}," if body.client_name else "Bonjour,"
    inner = f"<p>{hello}</p><p>Veuillez trouver ci-joint votre devis de <b>{company}</b>.</p>"
    if body.message:
        inner += f"<p>{body.message}</p>"
    subject = f"Devis · {company}"
    html = wrap_html(subject, inner)
    sender_u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "email": 1})
    cc = (sender_u or {}).get("email")
    log_id = "qs_" + _secrets.token_hex(6)
    sign_token = _secrets.token_urlsafe(24)
    sign_url = f"{os.getenv('FRONTEND_URL', '')}/sign/{sign_token}"
    if doc["doc_type"] == "quote":
        inner += (f'<p style="margin:22px 0"><a href="{sign_url}" '
                  f'style="background:#3F7D54;color:#fff;padding:12px 22px;border-radius:8px;'
                  f'text-decoration:none;font-weight:bold;display:inline-block">'
                  f'✍️ Consulter et signer le devis en ligne</a></p>'
                  f'<p style="font-size:12px;color:#666">Ou copiez ce lien : {sign_url}</p>')
    html = wrap_html(subject, inner)
    filename = f"{doc.get('number') or doc_id}.pdf"
    # Rendu 3D du projet en pièce jointe (si disponible et demandé)
    extra_attachments = None
    has_3d = False
    if body.attach_3d and doc.get("attachment_image_b64"):
        import base64 as _b64
        raw = doc["attachment_image_b64"]
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            extra_attachments = [{"filename": "rendu-3d.png",
                                  "content": _b64.b64decode(raw),
                                  "content_type": "image/png"}]
            has_3d = True
        except Exception:  # noqa: BLE001
            extra_attachments = None
    await db.quote_sends.insert_one({
        "log_id": log_id, "doc_id": doc_id, "user_id": user["user_id"],
        "plan_id": None, "signature_token": sign_token,
        "signature_token_created_at": _now(),
        "client_email": body.client_email, "client_name": body.client_name,
        "total_ttc": ttc, "subject": subject,
        "email_status": "queued", "email_id": None, "error": None,
        "created_at": _now(), "opened": False, "open_count": 0,
        "signed": False, "reminder_sent": False,
    })
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]}, {"$set": {"status": "sent"}})

    async def _deliver():
        try:
            res = await asyncio.wait_for(
                deliver_email(user["user_id"], body.client_email, subject, html,
                              pdf_bytes=pdf_bytes, filename=filename, cc=cc,
                              extra_attachments=extra_attachments,
                              reply_to=(company_email or cc),
                              from_name=company),
                timeout=45)
            await db.quote_sends.update_one(
                {"log_id": log_id},
                {"$set": {"email_status": "sent", "email_id": res.get("id"),
                          "email_via": res.get("via")}})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"send_document email failed ({log_id}): {e}")
            await db.quote_sends.update_one(
                {"log_id": log_id}, {"$set": {"email_status": "failed", "error": str(e)[:300]}})

    background_tasks.add_task(_deliver)
    return {"ok": True, "queued": True, "log_id": log_id, "total_ttc": ttc, "attached_3d": has_3d}



@router.get("/{doc_id}/factur-x")
async def document_facturx(doc_id: str, user=Depends(current_user)):
    """Facture électronique Factur-X PDF/A-3 conforme (via facturxapi, repli local)."""
    _doc, fx, _report, _src = await _ensure_facturx(doc_id, user)
    doc = await _get_owned(doc_id, user)
    fname = f"{doc.get('number') or doc['doc_id']}-facturx.pdf"
    return Response(content=fx, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _facturx_hash(doc: dict, branding: dict | None) -> str:
    payload = {
        "lines": doc.get("lines"),
        "totals": doc.get("totals"),
        "number": doc.get("number"),
        "client": doc.get("client"),
        "b": {k: (branding or {}).get(k) for k in
              ("company_name", "siret", "vat", "address", "city", "postal_code", "country")},
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


async def _ensure_facturx(doc_id: str, user: dict, force: bool = False):
    """Génère (ou réutilise en cache) le Factur-X PDF/A-3 conforme + son rapport.

    Retourne (doc, pdf_bytes, report, source). source ∈ cache|convert|local.
    """
    from engines.pdf_docs import build_document_pdf
    from engines.facturx_gen import to_facturx
    from engines.facturx_converter import build_invoice_data, convert_facturx, FacturxConvertError
    from routes.plans_common import _resolve_branding

    doc = await _get_owned(doc_id, user)
    if doc.get("doc_type") != "invoice":
        raise HTTPException(status_code=400, detail="Factur-X réservé aux factures")
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        doc["issue_date"] = doc.get("issue_date") or _now()
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc["issue_date"]}})

    branding = await _resolve_branding(user["user_id"])
    h = _facturx_hash(doc, branding)
    if not force and doc.get("facturx_hash") == h and doc.get("facturx_pdf_b64"):
        return doc, base64.b64decode(doc["facturx_pdf_b64"]), doc.get("facturx_validation") or {}, "cache"

    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=None, lang=user.get("lang"))
    try:
        fx, report = await convert_facturx(pdf_bytes, build_invoice_data(doc, branding))
        source = "convert"
    except FacturxConvertError as exc:
        logging.getLogger("documents").warning("Factur-X convert fallback: %s", exc)
        fx = to_facturx(pdf_bytes, doc, branding)
        report = {"valid": False, "profile": "MINIMUM", "error_count": None,
                  "warning_count": 0, "issues": [], "source": "local", "fallback_reason": str(exc)}
        source = "local"
    report["checked_at"] = _now()
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"facturx_pdf_b64": base64.b64encode(fx).decode(),
                  "facturx_validation": report, "facturx_hash": h}})
    return doc, fx, report, source


@router.post("/{doc_id}/factur-x/validate")
async def validate_document_facturx(doc_id: str, user=Depends(current_user)):
    """Valide/certifie le Factur-X conforme (rapport détaillé XSD + Schematron EN16931)."""
    from engines.facturx_validator import validate_facturx, FacturxValidationError
    _doc, fx, _report, _src = await _ensure_facturx(doc_id, user)
    fname = f"{_doc.get('number') or _doc['doc_id']}-facturx.pdf"
    try:
        report = await validate_facturx(fx, fname)
    except FacturxValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    report["checked_at"] = _now()
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"facturx_validation": report}})
    return report


# ============ FACTURES : conversions, paiements, avoirs ============

class ToInvoiceIn(BaseModel):
    mode: str = "total"          # total | prorata | detailed
    pct: float = Field(default=100, ge=0, le=100)


@router.post("/{doc_id}/to-invoice")
async def quote_to_invoice(doc_id: str, body: ToInvoiceIn,
                           user=Depends(current_user)) -> dict:
    """Transforme un devis en facture (total, prorata %, ou détaillé à éditer ensuite)."""
    from datetime import timedelta
    q = await _get_owned(doc_id, user)
    if q["doc_type"] != "quote":
        raise HTTPException(400, "Seul un devis peut être transformé en facture")
    scaled = body.mode in ("prorata", "acompte")
    factor = (max(0.0, min(body.pct, 100)) / 100) if scaled else 1.0
    note = q.get("notes") or ""
    if scaled and factor < 1:
        lines = [{**dict(ln), "qty": round((ln.get("qty") or 0) * factor, 4)}
                 for ln in q.get("lines", [])]
        if body.mode == "acompte":
            title = f"Facture d'acompte {int(round(body.pct))}% — {q.get('title') or 'devis'}"
            note = (f"Facture d'acompte de {int(round(body.pct))} % sur le devis "
                    f"{q.get('number') or ''}. Le solde sera facturé à l'achèvement "
                    f"des travaux.").strip()
        else:
            title = f"Facture situation {int(round(body.pct))}% — {q.get('title') or 'devis'}"
    else:
        lines = [dict(ln) for ln in q.get("lines", [])]
        title = f"Facture — {q.get('title') or 'devis'}"
    totals = _compute_totals(lines, 0)
    now = _now()
    number = await _next_number(user["user_id"], "invoice")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "invoice",
        "number": number,
        "title": title,
        "client_id": q.get("client_id"),
        "client": q.get("client"),
        "status": "sent",
        "lines": lines,
        "notes": note,
        "payment_terms": q.get("payment_terms") or "",
        "deposit_pct": 0,
        "totals": totals,
        "payments": [],
        "paid": 0.0,
        "remaining_due": totals["ttc"],
        "issue_date": now,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "source": "from_quote",
        "parent_doc_id": doc_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.post("/{doc_id}/to-credit-note")
async def invoice_to_credit_note(doc_id: str, user=Depends(current_user)) -> dict:
    """Crée un avoir à partir d'une facture (montants à ajuster ensuite si partiel)."""
    inv = await _get_owned(doc_id, user)
    if inv["doc_type"] != "invoice":
        raise HTTPException(400, "Seule une facture peut donner lieu à un avoir")
    lines = [dict(ln) for ln in inv.get("lines", [])]
    totals = _compute_totals(lines, 0)
    now = _now()
    number = await _next_number(user["user_id"], "credit_note")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "credit_note",
        "number": number,
        "title": f"Avoir — facture {inv.get('number') or ''}".strip(),
        "client_id": inv.get("client_id"),
        "client": inv.get("client"),
        "status": "issued",
        "lines": lines,
        "notes": f"Avoir émis en référence à la facture {inv.get('number') or inv['doc_id']}.",
        "payment_terms": "",
        "deposit_pct": 0,
        "totals": totals,
        "issue_date": now,
        "due_date": None,
        "source": "from_invoice",
        "parent_doc_id": doc_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str = "virement"
    date: str | None = None
    note: str = ""


def _apply_payment_status(payments: list, ttc: float) -> tuple[float, float, str]:
    paid = round(sum(p.get("amount", 0) for p in payments), 2)
    remaining = round(ttc - paid, 2)
    if ttc > 0 and paid + 0.01 >= ttc:
        status = "paid"
    elif paid > 0:
        status = "partial"
    else:
        status = "sent"
    return paid, remaining, status


@router.post("/{doc_id}/payments")
async def add_payment(doc_id: str, body: PaymentIn, user=Depends(current_user)) -> dict:
    doc = await _get_owned(doc_id, user)
    if doc["doc_type"] != "invoice":
        raise HTTPException(400, "Les paiements ne concernent que les factures")
    pay = {
        "payment_id": "pay_" + secrets.token_hex(4),
        "amount": round(body.amount, 2),
        "method": (body.method or "virement").strip()[:40],
        "date": body.date or _now(),
        "note": (body.note or "").strip()[:200],
    }
    payments = doc.get("payments", []) + [pay]
    ttc = doc.get("totals", {}).get("ttc", 0)
    paid, remaining, status = _apply_payment_status(payments, ttc)
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"payments": payments, "paid": paid, "remaining_due": remaining,
                  "status": status, "updated_at": _now()}})
    return await _get_owned(doc_id, user)


@router.delete("/{doc_id}/payments/{payment_id}")
async def delete_payment(doc_id: str, payment_id: str,
                         user=Depends(current_user)) -> dict:
    doc = await _get_owned(doc_id, user)
    payments = [p for p in doc.get("payments", []) if p.get("payment_id") != payment_id]
    ttc = doc.get("totals", {}).get("ttc", 0)
    paid, remaining, status = _apply_payment_status(payments, ttc)
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"payments": payments, "paid": paid, "remaining_due": remaining,
                  "status": status, "updated_at": _now()}})
    return await _get_owned(doc_id, user)


@router.get("/client-summary/{client_id}")
async def client_summary(client_id: str, user=Depends(current_user)) -> dict:
    """Synthèse par client : devis signés/refusés, factures, encaissements, reste à facturer."""
    docs = await db.pro_documents.find(
        {"user_id": user["user_id"], "client_id": client_id}, {"_id": 0, "lines": 0}
    ).sort("created_at", -1).to_list(3000)
    quotes = [d for d in docs if d["doc_type"] == "quote"]
    invoices = [d for d in docs if d["doc_type"] == "invoice"]
    credits = [d for d in docs if d["doc_type"] == "credit_note"]

    def _ttc(x):
        return x.get("totals", {}).get("ttc", 0)

    signed = [q for q in quotes if q.get("status") == "signed"]
    ca_signed = round(sum(_ttc(q) for q in signed), 2)
    invoiced = round(sum(_ttc(i) for i in invoices), 2)
    paid = round(sum(i.get("paid", 0) for i in invoices), 2)
    credited = round(sum(_ttc(c) for c in credits), 2)
    return {
        "kpis": {
            "ca_signed": ca_signed,
            "invoiced": invoiced,
            "paid": paid,
            "credited": credited,
            "to_invoice": round(ca_signed - invoiced, 2),
            "to_collect": round(invoiced - paid - credited, 2),
        },
        "quotes": quotes,
        "invoices": invoices,
        "credit_notes": credits,
    }


# ============ RELANCE AUTOMATIQUE DES FACTURES IMPAYÉES (J+7 / J+15) ============

async def run_invoice_reminders() -> int:
    """Relance quotidienne des factures impayées à J+7 puis J+15, PDF en pièce jointe."""
    from datetime import timedelta  # noqa: F401
    from engines.pdf_docs import build_document_pdf
    from engines.emailer import wrap_html
    from routes.plans_common import _resolve_branding, deliver_email
    log = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    sent = 0
    cur = db.pro_documents.find(
        {"doc_type": "invoice", "status": {"$in": ["sent", "partial"]}})
    async for inv in cur:
        client = inv.get("client") or {}
        email = (client.get("email") or "").strip()
        if "@" not in email:
            continue
        try:
            issued = datetime.fromisoformat(inv["issue_date"]) if inv.get("issue_date") else None
        except Exception:  # noqa: BLE001
            issued = None
        if not issued:
            continue
        days = (now - issued).days
        reminders = inv.get("reminders", {})
        if days >= 15 and not reminders.get("j15"):
            stage = "j15"
        elif days >= 7 and not reminders.get("j7"):
            stage = "j7"
        else:
            continue
        try:
            branding = await _resolve_branding(inv["user_id"])
            pro = await db.users.find_one({"user_id": inv["user_id"]}, {"_id": 0, "lang": 1})
            lang = (pro or {}).get("lang")
            pdf = build_document_pdf(inv, branding=branding, lang=lang)
            remaining = inv.get("remaining_due", inv.get("totals", {}).get("ttc", 0)) or 0
            name = client.get("first_name") or client.get("company") or ""
            company_name = (branding or {}).get("company_name")
            company_email = (branding or {}).get("company_email")
            from engines.email_i18n import T
            number = inv.get("number")
            inner = (
                f"<p>{T(lang, 'invrem.greeting', name=name)}</p>"
                f"<p>{T(lang, 'invrem.body1', number=number, amount=f'{remaining:.2f} €')}</p>"
                f"<p>{T(lang, 'invrem.body2')}</p>")
            html = wrap_html(T(lang, "invrem.title", number=number), inner)
            await deliver_email(
                inv["user_id"], email, T(lang, "invrem.subject", number=number),
                html, pdf_bytes=pdf, filename=f"{number}.pdf",
                reply_to=company_email, from_name=company_name)
            await db.pro_documents.update_one(
                {"doc_id": inv["doc_id"]},
                {"$set": {f"reminders.{stage}": now.isoformat()}})
            sent += 1
        except Exception as e:  # noqa: BLE001
            log.warning("Invoice reminder failed for %s: %s", inv.get("doc_id"), e)
    return sent
