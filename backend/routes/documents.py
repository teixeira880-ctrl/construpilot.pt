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

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from core.db import db
from core.security import current_user, pro_required

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"], prefix="/documents", dependencies=[Depends(pro_required)])

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


def _reduced_vat_rate(doc: dict) -> float | None:
    """Retourne le taux réduit (10 ou 5.5) présent dans le devis, sinon None."""
    rates = [float(ln.get("vat_rate") or 0) for ln in doc.get("lines", [])]
    reduced = sorted({r for r in rates if 0 < r < 20}, reverse=True)
    return reduced[0] if reduced else None


def _resolved_email_message(doc: dict, company: str, name: str, branding: dict | None) -> str:
    """Message d'accompagnement : texte perso du pro (avec variables) sinon modèle type."""
    custom = (branding or {}).get("default_email_message")
    if custom:
        return (custom.replace("{client}", name or "").replace("{nom}", name or "")
                .replace("{entreprise}", company or "").replace("{numero}", doc.get("number") or ""))
    return _email_template(doc, company, name)



def _email_template(doc: dict, company: str, client_name: str | None) -> str:
    """Modèle d'e-mail type selon type de document + taux de TVA."""
    number = doc.get("number") or ""
    name = (client_name or "").strip() or "Madame, Monsieur"
    if doc.get("doc_type") == "invoice":
        return (f"Bonjour {name},\n\n"
                f"Vous trouverez ci-joint votre facture n° {number}.\n\n"
                f"Dans l'attente de votre aimable règlement.\n\n"
                f"Cordialement,\n{company}")
    if _reduced_vat_rate(doc) is not None:
        return (f"Bonjour {name},\n\n"
                f"Vous trouverez ci-joint votre devis n° {number} ainsi que l'attestation de TVA "
                f"correspondante, pré-remplie et vous permettant de bénéficier de la TVA à taux "
                f"réduit sur vos travaux.\n\n"
                f"Nous vous remercions pour votre confiance.\n\n"
                f"Cordialement,\n{company}")
    return (f"Bonjour {name},\n\n"
            f"Veuillez trouver ci-joint le devis correspondant à votre demande devis n° {number}.\n\n"
            f"Nous restons à votre entière disposition pour toute information complémentaire ou pour "
            f"échanger sur certains points si nécessaire.\n\n"
            f"Dans l'attente de votre retour, nous vous remercions pour votre confiance.\n\n"
            f"Cordialement,\n{company}")


def _text_to_html(text: str) -> str:
    import html as _html
    out = []
    for para in text.split("\n\n"):
        if not para.strip():
            continue
        out.append(f'<p style="margin:0 0 14px 0">'
                   f'{_html.escape(para).strip().replace(chr(10), "<br/>")}</p>')
    return "".join(out)


def _render_button_html(url: str) -> str:
    """Bouton e-mail vers la projection avant/après du chantier (rendu IA)."""
    if not url:
        return ""
    return (f'<p style="margin:18px 0"><a href="{url}" '
            f'style="background:#0A0D14;color:#fff;padding:12px 22px;border-radius:8px;'
            f'text-decoration:none;font-weight:bold;display:inline-block">'
            f'🏠 Voir la projection avant / après du chantier</a></p>')



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


class DepositIn(BaseModel):
    pct: float = Field(default=30, ge=1, le=100)


@router.post("/{doc_id}/deposit-invoice")
async def create_deposit_invoice(doc_id: str, body: DepositIn, user=Depends(current_user)) -> dict:
    """Crée une facture d'acompte (ex. 30%) à partir d'un devis SIGNÉ.
    Une ligne par taux de TVA, sans le détail du devis, référencée « Acompte …% sur devis N°… »."""
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Devis introuvable")
    if not (q.get("signed") or q.get("status") == "signed"):
        raise HTTPException(status_code=400, detail="Le devis doit être signé pour facturer un acompte")
    pct = max(1.0, min(100.0, float(body.pct or 30)))

    ht_by_rate: dict[float, float] = {}
    for ln in q.get("lines", []):
        rate = float(ln.get("vat_rate") or 0)
        ht_by_rate[rate] = ht_by_rate.get(rate, 0) + (ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0)
    if not ht_by_rate:
        raise HTTPException(status_code=400, detail="Le devis ne contient aucune ligne chiffrée")

    num = q.get("number") or q["doc_id"]
    pct_txt = f"{pct:g}"
    multi = len(ht_by_rate) > 1
    lines = []
    for rate, ht in sorted(ht_by_rate.items()):
        desig = f"Acompte {pct_txt}% sur devis N°{num}" + (f" — TVA {rate:g}%" if multi else "")
        lines.append({"designation": desig, "description": (q.get("title") or "").strip()[:200],
                      "unit": "forfait", "qty": 1, "unit_price_ht": round(ht * pct / 100, 2),
                      "vat_rate": rate, "category": "Acompte"})

    from datetime import timedelta
    number = await _next_number(user["user_id"], "invoice")
    now = _now()
    totals = _compute_totals(lines, 0)
    inv = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": user["user_id"],
        "doc_type": "invoice", "number": number,
        "title": f"Facture d'acompte {pct_txt}% — devis N°{num}",
        "client_id": q.get("client_id"), "client": q.get("client"),
        "status": "draft", "lines": lines,
        "notes": f"Facture d'acompte de {pct_txt}% correspondant au devis N°{num}.",
        "payment_terms": q.get("payment_terms") or "",
        "deposit_pct": 0, "totals": totals,
        "payments": [], "paid": 0.0, "remaining_due": totals["ttc"],
        "issue_date": now,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "source": "deposit", "parent_doc_id": q["doc_id"],
        "source_quote_id": q["doc_id"], "source_quote_number": num,
        "deposit_pct_of_quote": pct,
        "created_at": now, "updated_at": now,
    }
    await db.pro_documents.insert_one(dict(inv))
    inv.pop("_id", None)
    await db.pro_documents.update_one({"doc_id": q["doc_id"]},
                                      {"$set": {"deposit_invoice_id": inv["doc_id"], "updated_at": now}})
    from engines import activity
    await activity.log(user, "invoice.deposit", "document", inv["title"], {"doc_id": inv["doc_id"], "quote_id": q["doc_id"]})
    return inv


def _ht_by_rate(lines: list) -> dict:
    res: dict[float, float] = {}
    for ln in lines or []:
        rate = float(ln.get("vat_rate") or 0)
        res[rate] = res.get(rate, 0) + (ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0)
    return res


async def _quote_children(user_id: str, quote_id: str) -> list:
    return await db.pro_documents.find(
        {"user_id": user_id, "source_quote_id": quote_id, "doc_type": "invoice"},
        {"_id": 0, "doc_id": 1, "number": 1, "source": 1, "title": 1, "status": 1,
         "lines": 1, "totals": 1, "created_at": 1}).sort("created_at", 1).to_list(200)


@router.get("/{doc_id}/billing-recap")
async def billing_recap(doc_id: str, user=Depends(current_user)) -> dict:
    """Décompte général : devis + toutes ses factures liées (acomptes, situations, solde)."""
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Devis introuvable")
    children = await _quote_children(user["user_id"], doc_id)
    q_ht = q.get("totals", {}).get("ht", 0)
    q_ttc = q.get("totals", {}).get("ttc", 0)
    billed_ht = sum(c.get("totals", {}).get("ht", 0) for c in children)
    billed_ttc = sum(c.get("totals", {}).get("ttc", 0) for c in children)
    return {
        "quote": {"doc_id": q["doc_id"], "number": q.get("number"), "ht": q_ht, "ttc": q_ttc,
                  "signed": bool(q.get("signed") or q.get("status") == "signed")},
        "invoices": [{"doc_id": c["doc_id"], "number": c.get("number"), "title": c.get("title"),
                      "source": c.get("source"), "status": c.get("status"),
                      "ht": c.get("totals", {}).get("ht", 0), "ttc": c.get("totals", {}).get("ttc", 0),
                      "created_at": c.get("created_at")} for c in children],
        "billed_ht": round(billed_ht, 2), "billed_ttc": round(billed_ttc, 2),
        "remaining_ht": round(q_ht - billed_ht, 2), "remaining_ttc": round(q_ttc - billed_ttc, 2),
        "progress_pct": round(billed_ht / q_ht * 100, 1) if q_ht else 0,
    }


class SituationIn(BaseModel):
    pct: float = Field(default=100, ge=0.1, le=100)
    deduct_deposit_pct: float = Field(default=0, ge=0, le=100)


async def _create_child_invoice(q: dict, user: dict, lines: list, title: str, note: str, source: str) -> dict:
    from datetime import timedelta
    number = await _next_number(user["user_id"], "invoice")
    now = _now()
    totals = _compute_totals(lines, 0)
    inv = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": user["user_id"],
        "doc_type": "invoice", "number": number, "title": title,
        "client_id": q.get("client_id"), "client": q.get("client"),
        "status": "draft", "lines": lines, "notes": note,
        "payment_terms": q.get("payment_terms") or "", "deposit_pct": 0, "totals": totals,
        "payments": [], "paid": 0.0, "remaining_due": totals["ttc"], "issue_date": now,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "source": source, "parent_doc_id": q["doc_id"],
        "source_quote_id": q["doc_id"], "source_quote_number": q.get("number") or q["doc_id"],
        "created_at": now, "updated_at": now,
    }
    await db.pro_documents.insert_one(dict(inv))
    inv.pop("_id", None)
    return inv


@router.post("/{doc_id}/situation-invoice")
async def create_situation_invoice(doc_id: str, body: SituationIn, user=Depends(current_user)) -> dict:
    """Facture de situation au prorata (pct d'avancement), avec déduction optionnelle des acomptes."""
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Devis introuvable")
    if not (q.get("signed") or q.get("status") == "signed"):
        raise HTTPException(status_code=400, detail="Le devis doit être signé")
    pct = float(body.pct)
    ded = float(body.deduct_deposit_pct or 0)
    num = q.get("number") or q["doc_id"]
    children = await _quote_children(user["user_id"], doc_id)
    sit_no = sum(1 for c in children if c.get("source") == "situation") + 1
    quote_ht_by_rate = _ht_by_rate(q.get("lines", []))
    # HT d'acompte déjà facturé par taux (pour la déduction)
    acompte_ht_by_rate: dict[float, float] = {}
    for c in children:
        if c.get("source") == "deposit":
            for r, ht in _ht_by_rate(c.get("lines", [])).items():
                acompte_ht_by_rate[r] = acompte_ht_by_rate.get(r, 0) + ht
    multi = len(quote_ht_by_rate) > 1
    lines = []
    for rate, ht in sorted(quote_ht_by_rate.items()):
        suffix = f" — TVA {rate:g}%" if multi else ""
        lines.append({"designation": f"Situation n°{sit_no} — avancement {pct:g}% — devis N°{num}{suffix}",
                      "description": (q.get("title") or "").strip()[:200], "unit": "forfait", "qty": 1,
                      "unit_price_ht": round(ht * pct / 100, 2), "vat_rate": rate, "category": "Situation"})
        if ded > 0 and acompte_ht_by_rate.get(rate):
            lines.append({"designation": f"Déduction acompte {ded:g}%{suffix}", "description": "",
                          "unit": "forfait", "qty": 1,
                          "unit_price_ht": -round(acompte_ht_by_rate[rate] * ded / 100, 2),
                          "vat_rate": rate, "category": "Déduction"})
    title = f"Situation n°{sit_no} ({pct:g}%) — devis N°{num}"
    note = f"Facture de situation n°{sit_no} au prorata ({pct:g}% d'avancement) du devis N°{num}." \
           + (f" Déduction de {ded:g}% des acomptes." if ded > 0 else "")
    inv = await _create_child_invoice(q, user, lines, title, note, "situation")
    return inv


@router.post("/{doc_id}/balance-invoice")
async def create_balance_invoice(doc_id: str, user=Depends(current_user)) -> dict:
    """Facture de solde : reste dû = total devis − déjà facturé (acomptes + situations), par taux de TVA."""
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Devis introuvable")
    if not (q.get("signed") or q.get("status") == "signed"):
        raise HTTPException(status_code=400, detail="Le devis doit être signé")
    num = q.get("number") or q["doc_id"]
    children = await _quote_children(user["user_id"], doc_id)
    quote_ht_by_rate = _ht_by_rate(q.get("lines", []))
    billed_ht_by_rate: dict[float, float] = {}
    for c in children:
        for r, ht in _ht_by_rate(c.get("lines", [])).items():
            billed_ht_by_rate[r] = billed_ht_by_rate.get(r, 0) + ht
    multi = len(quote_ht_by_rate) > 1
    lines = []
    for rate, ht in sorted(quote_ht_by_rate.items()):
        remaining = round(ht - billed_ht_by_rate.get(rate, 0), 2)
        if abs(remaining) < 0.01:
            continue
        suffix = f" — TVA {rate:g}%" if multi else ""
        lines.append({"designation": f"Solde — devis N°{num}{suffix}",
                      "description": (q.get("title") or "").strip()[:200], "unit": "forfait", "qty": 1,
                      "unit_price_ht": remaining, "vat_rate": rate, "category": "Solde"})
    if not lines:
        raise HTTPException(status_code=400, detail="Rien à facturer : le devis est déjà entièrement facturé")
    inv = await _create_child_invoice(q, user, lines, f"Facture de solde — devis N°{num}",
                                      f"Facture de solde du devis N°{num} (déduction des acomptes et situations déjà facturés).",
                                      "balance")
    return inv


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


# ---- Import de PDF externes (devis/factures d'autres logiciels) -------------

def _pdf_extract_text(data: bytes) -> str:
    """Texte des PDF natifs (texte sélectionnable)."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:15]).strip()
    except Exception:  # noqa: BLE001
        return ""


def _pdf_render_images(data: bytes, max_pages: int = 3) -> list[str]:
    """Rend les premières pages du PDF en PNG base64 (repli pour les scans)."""
    imgs: list[str] = []
    try:
        import pymupdf
        pdf = pymupdf.open(stream=data, filetype="pdf")
        for page in list(pdf)[:max_pages]:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            imgs.append(base64.b64encode(pix.tobytes("png")).decode())
        pdf.close()
    except Exception:  # noqa: BLE001
        pass
    return imgs


def _seq_from_number(number: str) -> int:
    import re
    m = re.findall(r"\d+", number or "")
    return int(m[-1]) if m else 0


async def _find_or_create_client(user_id: str, cl: dict) -> str | None:
    """Dédoublonne par e-mail, puis société, puis nom+prénom ; crée sinon."""
    import re
    email = (cl.get("email") or "").strip()
    company = (cl.get("company") or "").strip()
    last = (cl.get("last_name") or "").strip()
    first = (cl.get("first_name") or "").strip()
    if not any([email, company, last, first]):
        return None

    def _ci(val: str) -> dict:
        return {"$regex": f"^{re.escape(val)}$", "$options": "i"}

    existing = None
    if email:
        existing = await db.clients.find_one(
            {"user_id": user_id, "email": _ci(email)}, {"_id": 0, "client_id": 1})
    if not existing and company:
        existing = await db.clients.find_one(
            {"user_id": user_id, "company": _ci(company)}, {"_id": 0, "client_id": 1})
    if not existing and (last or first):
        existing = await db.clients.find_one(
            {"user_id": user_id, "last_name": _ci(last), "first_name": _ci(first)},
            {"_id": 0, "client_id": 1})
    if existing:
        return existing["client_id"]
    cid = "cli_" + secrets.token_hex(6)
    await db.clients.insert_one({
        "client_id": cid, "user_id": user_id,
        "first_name": first[:80], "last_name": last[:80], "company": company[:120],
        "email": email[:160], "phone": (cl.get("phone") or "").strip()[:40],
        "address": (cl.get("address") or "").strip()[:200],
        "postal_code": (cl.get("postal_code") or "").strip()[:16],
        "city": (cl.get("city") or "").strip()[:80],
        "siret": (cl.get("siret") or "").strip()[:20],
        "created_at": _now(), "updated_at": _now(),
    })
    return cid


async def _bump_counter(user_id: str, doc_type: str, seq: int) -> None:
    """Fait continuer le compteur ConstruPilot à partir du plus grand n° importé (année courante)."""
    if seq <= 0:
        return
    year = datetime.now(timezone.utc).year
    cur = await db.doc_counters.find_one(
        {"user_id": user_id, "doc_type": doc_type, "year": year}, {"_id": 0, "seq": 1})
    if (cur or {}).get("seq", 0) < seq:
        await db.doc_counters.update_one(
            {"user_id": user_id, "doc_type": doc_type, "year": year},
            {"$set": {"seq": seq}}, upsert=True)


@router.post("/import-pdf")
async def import_documents_pdf(files: list[UploadFile] = File(...),
                               status: str = Form("sent"),
                               user=Depends(current_user)) -> dict:
    """Importe un lot de devis/factures PDF d'autres logiciels.

    Extraction IA → crée/associe le client → crée le document au format ConstruPilot
    en conservant le NUMÉRO d'origine, puis fait continuer la numérotation.
    `status` (draft|sent|accepted|refused|paid) reconstitue l'historique.
    """
    from engines.ai import extract_document_from_pdf
    # Mapping du statut choisi vers le statut réel selon le type de document
    STATUS_MAP = {
        "draft": {"quote": "draft", "invoice": "draft", "credit_note": "draft"},
        "sent": {"quote": "sent", "invoice": "sent", "credit_note": "sent"},
        "accepted": {"quote": "signed", "invoice": "sent", "credit_note": "sent"},
        "refused": {"quote": "refused", "invoice": "refused", "credit_note": "refused"},
        "paid": {"quote": "signed", "invoice": "paid", "credit_note": "paid"},
    }
    chosen = status if status in STATUS_MAP else "sent"
    if not files:
        raise HTTPException(400, "Aucun fichier fourni")
    results: list[dict] = []
    max_seq: dict[str, int] = {}
    for f in files[:20]:
        name = f.filename or "document.pdf"
        try:
            data = await f.read()
            if not data or not name.lower().endswith(".pdf"):
                results.append({"file": name, "ok": False, "error": "Fichier non PDF"})
                continue
            text = _pdf_extract_text(data)
            images = [] if len(text) >= 120 else _pdf_render_images(data)
            if len(text) < 120 and not images:
                results.append({"file": name, "ok": False, "error": "PDF illisible"})
                continue
            ext = await extract_document_from_pdf(
                text=text if len(text) >= 120 else "", images=images or None)
            lines = ext.get("lines") or []
            if not lines:
                results.append({"file": name, "ok": False, "error": "Aucune ligne détectée"})
                continue
            dtype = ext.get("doc_type") or "quote"
            client_id = await _find_or_create_client(user["user_id"], ext.get("client") or {})
            number = (ext.get("number") or "").strip() or None
            label = "Facture" if dtype == "invoice" else ("Avoir" if dtype == "credit_note" else "Devis")
            totals = _compute_totals(lines, 0)
            doc_status = STATUS_MAP[chosen][dtype]
            doc = {
                "doc_id": "doc_" + secrets.token_hex(6),
                "user_id": user["user_id"],
                "doc_type": dtype,
                "number": number,
                "title": f"{label} importé — {name[:60]}",
                "client_id": client_id,
                "client": await _client_snapshot(client_id, user),
                "status": doc_status,
                "signed": doc_status == "signed",
                "lines": lines,
                "notes": ext.get("notes") or "",
                "payment_terms": "",
                "deposit_pct": 0,
                "totals": totals,
                "issue_date": ext.get("issue_date") or None,
                "due_date": None,
                "source": "import_pdf",
                "imported_filename": name[:160],
                "created_at": _now(),
                "updated_at": _now(),
            }
            if dtype == "invoice" and doc_status == "paid":
                doc["paid"] = totals["ttc"]
                doc["remaining_due"] = 0.0
                doc["payments"] = [{"amount": totals["ttc"], "date": _now(), "method": "import"}]
            await db.pro_documents.insert_one(dict(doc))
            doc.pop("_id", None)
            if number:
                max_seq[dtype] = max(max_seq.get(dtype, 0), _seq_from_number(number))
            results.append({"file": name, "ok": True, "doc_id": doc["doc_id"],
                            "doc_type": dtype, "number": number, "client_id": client_id,
                            "status": doc_status, "lines": len(lines), "ttc": totals["ttc"]})
        except Exception as e:  # noqa: BLE001
            logger.warning("import-pdf failed for %s: %s", name, e)
            results.append({"file": name, "ok": False, "error": str(e)[:200]})
    for dtype, seq in max_seq.items():
        await _bump_counter(user["user_id"], dtype, seq)
    return {"ok": True, "imported": sum(1 for r in results if r.get("ok")),
            "total": len(results), "results": results}


IMPORT_STATUS_MAP = {
    "draft": {"quote": "draft", "invoice": "draft", "credit_note": "draft"},
    "sent": {"quote": "sent", "invoice": "sent", "credit_note": "sent"},
    "accepted": {"quote": "signed", "invoice": "sent", "credit_note": "sent"},
    "refused": {"quote": "refused", "invoice": "refused", "credit_note": "refused"},
    "paid": {"quote": "signed", "invoice": "paid", "credit_note": "paid"},
}


async def _extract_pdf_item(f: UploadFile) -> dict:
    """Extrait (sans créer) les données d'un PDF pour l'aperçu éditable."""
    from engines.ai import extract_document_from_pdf
    name = f.filename or "document.pdf"
    data = await f.read()
    if not data or not name.lower().endswith(".pdf"):
        return {"file": name, "ok": False, "error": "Fichier non PDF"}
    text = _pdf_extract_text(data)
    images = [] if len(text) >= 120 else _pdf_render_images(data)
    if len(text) < 120 and not images:
        return {"file": name, "ok": False, "error": "PDF illisible"}
    ext = await extract_document_from_pdf(text=text if len(text) >= 120 else "", images=images or None)
    if not ext.get("lines"):
        return {"file": name, "ok": False, "error": "Aucune ligne détectée"}
    return {"file": name, "ok": True, **ext}


async def _persist_imported_doc(user: dict, item: dict, chosen: str) -> tuple[dict, str, int]:
    """Crée un document ConstruPilot depuis un item d'import (éventuellement édité)."""
    dtype = item.get("doc_type") if item.get("doc_type") in DOC_TYPES else "quote"
    lines = []
    for l in (item.get("lines") or []):
        lines.append({
            "designation": str(l.get("designation") or "").strip()[:200],
            "description": str(l.get("description") or "")[:400],
            "unit": l.get("unit") or "u",
            "qty": max(0.0, float(l.get("qty") or 0)),
            "unit_price_ht": max(0.0, float(l.get("unit_price_ht") or 0)),
            "vat_rate": float(l.get("vat_rate") if l.get("vat_rate") is not None else 20),
            "category": l.get("category") or "Importé",
        })
    client_id = await _find_or_create_client(user["user_id"], item.get("client") or {})
    number = (item.get("number") or "").strip() or None
    label = "Facture" if dtype == "invoice" else ("Avoir" if dtype == "credit_note" else "Devis")
    src = (item.get("file") or "").strip()
    totals = _compute_totals(lines, 0)
    doc_status = IMPORT_STATUS_MAP.get(chosen, IMPORT_STATUS_MAP["sent"])[dtype]
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": dtype,
        "number": number,
        "title": item.get("title") or f"{label} importé{(' — ' + src[:60]) if src else ''}",
        "client_id": client_id,
        "client": await _client_snapshot(client_id, user),
        "status": doc_status,
        "signed": doc_status == "signed",
        "lines": lines,
        "notes": item.get("notes") or "",
        "payment_terms": "",
        "deposit_pct": 0,
        "totals": totals,
        "issue_date": item.get("issue_date") or None,
        "due_date": None,
        "source": "import_pdf",
        "imported_filename": src[:160],
        "created_at": _now(),
        "updated_at": _now(),
    }
    if dtype == "invoice" and doc_status == "paid":
        doc["paid"] = totals["ttc"]
        doc["remaining_due"] = 0.0
        doc["payments"] = [{"amount": totals["ttc"], "date": _now(), "method": "import"}]
    await db.pro_documents.insert_one(dict(doc))
    result = {"ok": True, "file": src, "doc_id": doc["doc_id"], "doc_type": dtype,
              "number": number, "client_id": client_id, "status": doc_status,
              "lines": len(lines), "ttc": totals["ttc"]}
    return result, dtype, (_seq_from_number(number) if number else 0)


@router.post("/import-pdf/preview")
async def import_pdf_preview(files: list[UploadFile] = File(...),
                             user=Depends(current_user)) -> dict:
    """Étape 1 : extraction IA sans création — renvoie un aperçu éditable."""
    if not files:
        raise HTTPException(400, "Aucun fichier fourni")
    items: list[dict] = []
    for f in files[:20]:
        name = f.filename or "document.pdf"
        try:
            items.append(await _extract_pdf_item(f))
        except Exception as e:  # noqa: BLE001
            logger.warning("import preview failed for %s: %s", name, e)
            items.append({"file": name, "ok": False, "error": str(e)[:200]})
    return {"ok": True, "items": items}


class ImportConfirmIn(BaseModel):
    status: str = "sent"
    items: list[dict]


@router.post("/import-pdf/confirm")
async def import_pdf_confirm(body: ImportConfirmIn, user=Depends(current_user)) -> dict:
    """Étape 2 : crée les documents à partir de l'aperçu (éventuellement corrigé)."""
    chosen = body.status if body.status in IMPORT_STATUS_MAP else "sent"
    results: list[dict] = []
    max_seq: dict[str, int] = {}
    for it in (body.items or [])[:50]:
        if not (it.get("lines")):
            results.append({"file": it.get("file", ""), "ok": False, "error": "Aucune ligne"})
            continue
        try:
            res, dtype, seq = await _persist_imported_doc(user, it, chosen)
            results.append(res)
            if seq:
                max_seq[dtype] = max(max_seq.get(dtype, 0), seq)
        except Exception as e:  # noqa: BLE001
            logger.warning("import confirm failed: %s", e)
            results.append({"file": it.get("file", ""), "ok": False, "error": str(e)[:200]})
    for dtype, seq in max_seq.items():
        await _bump_counter(user["user_id"], dtype, seq)
    return {"ok": True, "imported": sum(1 for r in results if r.get("ok")),
            "total": len(results), "results": results}






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


# ============ Phase A — Devis multi-plans consolidé ============

ACIER_PRICE_KG = 1.85      # € HT / kg (fourniture + façonnage + pose) — éditable
TREILLIS_PRICE_PANEL = 48  # € HT / panneau — éditable
_DEFAULT_STRUCT_PARAMS = {
    "storey_height_m": 2.70, "n_levels": 1, "wall_thickness_m": None,
    "beam_w_m": None, "beam_h_m": None, "col_w_m": None, "col_h_m": None,
    "slab_thickness_m": None, "slab_area_m2": None, "margin_pct": 12.0,
    "partitions_as_concrete": True, "arase_inf_m": None, "arase_sup_m": None,
}


async def _ferraillage_lines(fid: str, user_id: str, prefix: str, vat: float) -> list[dict]:
    """Lignes de devis acier (fourniture/façonnage/pose) depuis l'analyse ferraillage d'un plan."""
    import engines.rebar as rebar
    d = await db.steel_analyses.find_one(
        {"plan_id": fid, "user_id": user_id}, {"_id": 0, "lines": 1, "treillis": 1, "filename": 1})
    if not d:
        return []
    rlines = d.get("lines") or []
    treillis = d.get("treillis") or []
    if not rlines and not treillis:
        return []
    summ = rebar.summary(rlines, treillis)
    loss = 0.05
    out = []
    for dia in summ.get("by_diameter", []):
        kg = round(float(dia.get("kg", 0)) * (1 + loss), 1)
        if kg <= 0:
            continue
        out.append({
            "designation": f"Acier {dia.get('diameter', '')} — fourniture, façonnage & pose",
            "description": f"{dia.get('ml', 0)} ml (pertes {int(loss*100)}%)",
            "unit": "kg", "qty": kg, "unit_price_ht": ACIER_PRICE_KG,
            "vat_rate": vat, "category": f"{prefix} · Ferraillage",
        })
    for t in treillis:
        panels = int(t.get("panels") or 0)
        if panels <= 0:
            continue
        out.append({
            "designation": f"Treillis soudé {t.get('ref', '')}".strip(),
            "description": f"{t.get('area_m2', '')} m²",
            "unit": "panneau", "qty": panels, "unit_price_ht": TREILLIS_PRICE_PANEL,
            "vat_rate": vat, "category": f"{prefix} · Ferraillage",
        })
    return out


async def _consolidated_lines_for_plan(plan_id: str, user_id: str, subcontract: bool,
                                       processed_ferr: set) -> tuple[list[dict], str]:
    """Renvoie (lignes, libellé) pour un plan selon son type : gros œuvre / maison / ferraillage.
    Inclut les aciers des plans de ferraillage rattachés (ferraillage_plan_ids)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "structural_metre": 1, "rooms": 1, "filename": 1,
         "calibrations": 1, "pages.dxf_ratio": 1, "ferraillage_plan_ids": 1})
    if not p:
        return [], plan_id
    fname = p.get("filename") or "plan"
    lines: list[dict] = []

    if p.get("structural_metre"):
        # GROS ŒUVRE (coffrage/DWG) — TVA 20 % (ou 0 % sous-traitance)
        vat = 0.0 if subcontract else 20.0
        prefix = f"Gros œuvre · {fname}"
        from routes.plans_crud import _rescale_metre_to_calibration
        from engines.dxf_takeoff import cost_structural
        metre, _ = _rescale_metre_to_calibration(p["structural_metre"], p)
        estimate = cost_structural(metre, dict(_DEFAULT_STRUCT_PARAMS))
        margin = float(estimate["params"].get("margin_pct", 0)) / 100.0
        for lot in estimate.get("lots", []):
            for ln in lot.get("lines", []):
                pu = round(float(ln.get("pu", 0)) * (1 + margin), 2)
                lines.append({
                    "designation": ln.get("designation", ""),
                    "description": ln.get("detail", ""),
                    "unit": ln.get("unit", "u"),
                    "qty": round(float(ln.get("qty", 0)), 2),
                    "unit_price_ht": pu, "vat_rate": vat,
                    "category": f"{prefix} · {lot.get('lot', '')}",
                })
        # Aciers des plans de ferraillage rattachés
        for fid in (p.get("ferraillage_plan_ids") or []):
            if fid in processed_ferr:
                continue
            processed_ferr.add(fid)
            lines += await _ferraillage_lines(fid, user_id, f"Gros œuvre · {fname}", vat)
        return lines, prefix

    if p.get("rooms"):
        # MAISON / rénovation (finitions depuis les pièces) — TVA 10 % (ou 0 %)
        vat = 0.0 if subcontract else 10.0
        prefix = f"Maison · {fname}"
        try:
            from routes.plans_common import _build_quote_and_pdf
            quote, _ = await _build_quote_and_pdf(
                plan_id, user_id, "std", "carrelage", True, True, True, True)
            for li in quote.get("line_items", []):
                qty = li.get("quantity") or 0
                pu = round((li.get("total") or 0) / qty, 2) if qty else (li.get("total") or 0)
                lines.append({
                    "designation": li.get("name") or "",
                    "unit": li.get("unit") or "u", "qty": round(qty, 2),
                    "unit_price_ht": pu, "vat_rate": vat,
                    "category": f"{prefix} · Depuis plan IA",
                })
        except HTTPException:
            pass
        return lines, prefix

    # FERRAILLAGE seul (sélectionné directement)
    if plan_id not in processed_ferr:
        processed_ferr.add(plan_id)
        vat = 0.0 if subcontract else 20.0
        ferr = await _ferraillage_lines(plan_id, user_id, f"Ferraillage · {fname}", vat)
        if ferr:
            return ferr, f"Ferraillage · {fname}"
    return [], fname


class FromPlansIn(BaseModel):
    plan_ids: list[str] = Field(min_length=1, max_length=30)
    project_name: str = Field(default="", max_length=160)
    client_id: str | None = None
    subcontract_plan_ids: list[str] = Field(default_factory=list)


@router.post("/from-plans")
async def document_from_plans(body: FromPlansIn, user=Depends(current_user)) -> dict:
    """Crée UN devis éditable consolidé à partir de plusieurs plans (gros œuvre + maison
    + ferraillage), chaque bloc préfixé par le nom/type du plan. TVA 20 % gros œuvre /
    10 % maison / 0 % sous-traitance appliquée par ligne."""
    uid = user["user_id"]
    sub = set(body.subcontract_plan_ids or [])
    processed_ferr: set = set()
    all_lines: list[dict] = []
    included: list[str] = []
    for pid in body.plan_ids:
        lns, label = await _consolidated_lines_for_plan(pid, uid, pid in sub, processed_ferr)
        if lns:
            all_lines.extend(lns)
            included.append(label)
    if not all_lines:
        raise HTTPException(400, "Aucun plan sélectionné ne contient de métré chiffrable "
                                 "(mesurez/analysez les plans d'abord).")
    title = (body.project_name.strip()
             or f"Devis projet — {len(included)} plan{'s' if len(included) > 1 else ''}")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": uid, "doc_type": "quote", "number": None,
        "title": title[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        "status": "draft", "lines": all_lines, "notes": "",
        "payment_terms": "", "deposit_pct": 0,
        "totals": _compute_totals(all_lines, 0),
        "issue_date": None, "due_date": None,
        "source": "multi_plan", "plan_id": body.plan_ids[0],
        "plan_ids": body.plan_ids,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"ok": True, "doc_id": doc["doc_id"], "totals": doc["totals"],
            "line_count": len(all_lines), "included": included}


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
    allowed = {"draft", "sent", "signed", "refused", "partial", "paid", "issued"}
    if body.status not in allowed:
        raise HTTPException(400, "Statut invalide")
    await _get_owned(doc_id, user)
    upd = {"status": body.status, "updated_at": _now()}
    if body.status == "signed":
        upd["signed"] = True
        upd["signed_at"] = _now()
    elif body.status in ("draft", "sent", "refused"):
        upd["signed"] = False
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": upd})
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


class DocAttachmentIn(BaseModel):
    filename: str
    content_b64: str
    content_type: str = "application/octet-stream"


class DocSendIn(BaseModel):
    client_email: str
    client_name: str = ""
    message: str = ""
    attach_3d: bool = True
    render_url: str = ""
    attachments: list[DocAttachmentIn] = []


@router.get("/{doc_id}/email-template")
async def get_email_template(doc_id: str, client_name: str | None = None,
                             user=Depends(current_user)) -> dict:
    """Message type pré-rempli pour l'envoi (selon type de document + TVA)."""
    from routes.plans_common import _resolve_branding
    doc = await _get_owned(doc_id, user)
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        doc["issue_date"] = doc.get("issue_date") or _now()
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc["issue_date"]}})
    branding = await _resolve_branding(user["user_id"]) or {}
    company = branding.get("company_name") or user.get("name") or "ConstruPilot"
    name = client_name or ((doc.get("client") or {}).get("first_name") or "")
    number = doc.get("number") or ""
    is_quote = doc["doc_type"] == "quote"
    subject = (f"Devis n° {number} · {company}" if is_quote
               else f"Facture n° {number} · {company}")
    return {"subject": subject,
            "message": _resolved_email_message(doc, company, name, branding),
            "attach_tva_attestation": is_quote and _reduced_vat_rate(doc) is not None}


class EmailPreviewIn(BaseModel):
    message: str | None = None
    client_name: str | None = None
    render_url: str | None = None


@router.post("/{doc_id}/email-preview")
async def email_preview(doc_id: str, body: EmailPreviewIn, user=Depends(current_user)) -> dict:
    """Rend l'e-mail exact (avec logo/branding) tel que le client le recevra."""
    from routes.plans_common import _resolve_branding
    from engines.emailer import wrap_company_html, logo_url_for
    doc = await _get_owned(doc_id, user)
    branding = await _resolve_branding(user["user_id"]) or {}
    company = branding.get("company_name") or user.get("name") or "ConstruPilot"
    company_email = branding.get("company_email")
    is_quote = doc["doc_type"] == "quote"
    number = doc.get("number") or ""
    name = body.client_name or ((doc.get("client") or {}).get("first_name") or "")
    body_text = (body.message or "").strip() or _resolved_email_message(doc, company, name, branding)
    inner = _text_to_html(body_text)
    subject = (f"Devis n° {number} · {company}" if is_quote
               else f"Facture n° {number} · {company}")
    if is_quote:
        inner += ('<p style="margin:22px 0"><a href="#" '
                  'style="background:#3F7D54;color:#fff;padding:12px 22px;border-radius:8px;'
                  'text-decoration:none;font-weight:bold;display:inline-block">'
                  '✍️ Consulter et signer le devis en ligne</a></p>')
    inner += _render_button_html((body.render_url or "").strip())
    if doc.get("doc_type") in ("invoice", "credit_note") and user.get("bank_details"):
        _bank = str(user["bank_details"]).replace(chr(10), "<br/>")
        inner += (f'<div style="margin:18px 0;padding:14px 16px;background:#f6f8fa;border-radius:8px">'
                  f'<p style="margin:0 0 6px 0;font-weight:bold">Coordonnées bancaires</p>'
                  f'<p style="margin:0;color:#333;font-size:13px">{_bank}</p></div>')
    html = wrap_company_html(
        subject, inner, company_name=company,
        logo_url=logo_url_for(user["user_id"], branding),
        logo_b64=branding.get("logo_b64"),
        contact_line=branding.get("contact_line"),
        siret=branding.get("siret"), vat=branding.get("vat"),
        nif=branding.get("nif"), alvara=branding.get("alvara"),
        company_email=company_email,
        verified=bool(branding.get("verified")),
        verify_url=(f"{os.getenv('FRONTEND_URL', '')}/pro-verifie/{user['user_id']}"
                    if branding.get("verified") else None))
    attachments = [f"{number or doc_id}.pdf"]
    if is_quote and _reduced_vat_rate(doc) is not None:
        attachments.append(f"attestation-tva-{number or doc_id}.pdf")
    return {"subject": subject, "html": html, "attachments": attachments}


@router.post("/{doc_id}/send")
async def send_document(doc_id: str, body: DocSendIn, background_tasks: BackgroundTasks,
                        user=Depends(current_user)):
    """Génère le PDF puis envoie l'email au client EN TÂCHE DE FOND (réponse immédiate)."""
    import re as _re
    import secrets as _secrets
    from engines.emailer import wrap_company_html
    from engines.pdf_docs import build_document_pdf
    from routes.plans_common import _resolve_branding, deliver_email
    from routes.reviews import get_reviews_for_user
    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", body.client_email or ""):
        raise HTTPException(400, "Email client invalide.")
    # E-mail du pro requis vérifié avant tout envoi (grand-fathering : comptes sans le champ = OK)
    if user.get("email_verified") is False:
        raise HTTPException(
            403, "Confirmez d'abord votre adresse e-mail (lien reçu à l'inscription) avant d'envoyer un devis.")
    doc = await _get_owned(doc_id, user)
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        doc["issue_date"] = doc.get("issue_date") or _now()
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc["issue_date"]}})
    branding = await _resolve_branding(user["user_id"]) or {}
    reviews = await get_reviews_for_user(user["user_id"]) if doc["doc_type"] == "quote" else None
    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=reviews,
                                   lang=(doc.get("lang") or user.get("lang")))
    company = branding.get("company_name") or user.get("name") or "ConstruPilot"
    company_email = branding.get("company_email")
    ttc = (doc.get("totals") or {}).get("ttc") or doc.get("total_ttc") or 0
    is_quote = doc["doc_type"] == "quote"
    number = doc.get("number") or ""
    body_text = (body.message or "").strip() or _resolved_email_message(
        doc, company, body.client_name or ((doc.get("client") or {}).get("first_name") or ""), branding)
    inner = _text_to_html(body_text)
    subject = (f"Devis n° {number} · {company}" if is_quote
               else f"Facture n° {number} · {company}")
    sender_u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "email": 1})
    cc = (sender_u or {}).get("email")
    log_id = "qs_" + _secrets.token_hex(6)
    sign_token = _secrets.token_urlsafe(24)
    sign_url = f"{os.getenv('FRONTEND_URL', '')}/sign/{sign_token}"
    if is_quote:
        inner += (f'<p style="margin:22px 0"><a href="{sign_url}" '
                  f'style="background:#3F7D54;color:#fff;padding:12px 22px;border-radius:8px;'
                  f'text-decoration:none;font-weight:bold;display:inline-block">'
                  f'✍️ Consulter et signer le devis en ligne</a></p>'
                  f'<p style="font-size:12px;color:#666">Ou copiez ce lien : {sign_url}</p>')
    inner += _render_button_html((body.render_url or "").strip())
    if doc.get("doc_type") in ("invoice", "credit_note") and user.get("bank_details"):
        _bank = str(user["bank_details"]).replace(chr(10), "<br/>")
        inner += (f'<div style="margin:18px 0;padding:14px 16px;background:#f6f8fa;border-radius:8px">'
                  f'<p style="margin:0 0 6px 0;font-weight:bold">Coordonnées bancaires</p>'
                  f'<p style="margin:0;color:#333;font-size:13px">{_bank}</p></div>')
    from engines.emailer import logo_url_for
    logo_url = logo_url_for(user["user_id"], branding)
    html = wrap_company_html(subject, inner, company_name=company,
                             logo_url=logo_url,
                             logo_b64=branding.get("logo_b64"),
                             contact_line=branding.get("contact_line"),
                             siret=branding.get("siret"), vat=branding.get("vat"),
                             nif=branding.get("nif"), alvara=branding.get("alvara"),
                             company_email=company_email,
                             verified=bool(branding.get("verified")),
                             verify_url=(f"{os.getenv('FRONTEND_URL', '')}/pro-verifie/{user['user_id']}"
                                         if branding.get("verified") else None))
    filename = f"{doc.get('number') or doc_id}.pdf"
    # Pièces jointes : attestation TVA (taux réduit) + rendu 3D éventuel
    extra_attachments: list[dict] = []
    has_3d = False
    reduced_rate = _reduced_vat_rate(doc) if is_quote else None
    if reduced_rate is not None:
        try:
            from engines.pdf_takeoff import build_tva_attestation_pdf
            cl = doc.get("client") or {}
            addr = ", ".join([p for p in [
                (cl.get("address") or "").strip(),
                " ".join([cl.get("postal_code", ""), cl.get("city", "")]).strip()]
                if p]) or ""
            work_desc = " ; ".join([ln.get("designation") or ln.get("description") or ""
                                    for ln in doc.get("lines", []) if
                                    (ln.get("designation") or ln.get("description"))]) \
                or "Travaux de rénovation"
            att_pdf = build_tva_attestation_pdf(
                client_name=body.client_name or "",
                client_address=addr, work_address=addr,
                work_description=work_desc, company_name=company,
                company_address=branding.get("contact_line") or "",
                branding=branding, tva_rate=reduced_rate / 100.0)
            extra_attachments.append({"filename": f"attestation-tva-{number or doc_id}.pdf",
                                      "content": att_pdf, "content_type": "application/pdf"})
        except Exception as e:  # noqa: BLE001
            logger.warning("Attestation TVA non générée pour %s: %s", doc_id, e)
    if body.attach_3d and doc.get("attachment_image_b64"):
        import base64 as _b64
        raw = doc["attachment_image_b64"]
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            extra_attachments.append({"filename": "rendu-3d.png",
                                      "content": _b64.b64decode(raw),
                                      "content_type": "image/png"})
            has_3d = True
        except Exception:  # noqa: BLE001
            pass
    # Pièces jointes libres ajoutées par le pro (max 5 fichiers, 15 Mo au total)
    if body.attachments:
        import base64 as _b64u
        total = 0
        for att in body.attachments[:5]:
            raw = att.content_b64 or ""
            if "," in raw and raw.strip().startswith("data:"):
                raw = raw.split(",", 1)[1]
            try:
                content = _b64u.b64decode(raw)
            except Exception:  # noqa: BLE001
                continue
            total += len(content)
            if total > 15 * 1024 * 1024:
                raise HTTPException(400, "Pièces jointes trop volumineuses (15 Mo maximum au total).")
            extra_attachments.append({
                "filename": (att.filename or "piece-jointe").strip()[:120],
                "content": content,
                "content_type": att.content_type or "application/octet-stream"})
    extra_attachments = extra_attachments or None
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
    if q.get("status") != "signed":
        raise HTTPException(400, "Le devis doit être signé avant d'être facturé")
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
    from engines.emailer import wrap_company_html
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
            branding = await _resolve_branding(inv["user_id"]) or {}
            pro = await db.users.find_one({"user_id": inv["user_id"]}, {"_id": 0, "lang": 1})
            lang = (pro or {}).get("lang")
            pdf = build_document_pdf(inv, branding=branding, lang=lang)
            remaining = inv.get("remaining_due", inv.get("totals", {}).get("ttc", 0)) or 0
            name = client.get("first_name") or client.get("company") or ""
            company_name = branding.get("company_name")
            company_email = branding.get("company_email")
            from engines.email_i18n import T
            number = inv.get("number")
            inner = (
                f"<p>{T(lang, 'invrem.greeting', name=name)}</p>"
                f"<p>{T(lang, 'invrem.body1', number=number, amount=f'{remaining:.2f} €')}</p>"
                f"<p>{T(lang, 'invrem.body2')}</p>")
            from engines.emailer import logo_url_for
            html = wrap_company_html(
                T(lang, "invrem.title", number=number), inner,
                company_name=company_name or "",
                logo_url=logo_url_for(inv["user_id"], branding),
                logo_b64=branding.get("logo_b64"),
                contact_line=branding.get("contact_line"), siret=branding.get("siret"),
                vat=branding.get("vat"), nif=branding.get("nif"),
                alvara=branding.get("alvara"), company_email=company_email)
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
