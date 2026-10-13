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
from typing import Literal
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from core.db import db
from core.fiscal import policy_for, suggest_reduced_rate
from core.security import current_user, pro_required

logger = logging.getLogger(__name__)
from core.document_permissions import document_access, document_feature
from core.permissions import permissions_for, require_feature

router = APIRouter(tags=["documents"], prefix="/documents", dependencies=[Depends(document_access)])

DOC_TYPES = ("quote", "invoice", "credit_note")
PREFIX = {"quote": "DEV", "invoice": "FAC", "credit_note": "AV"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocLine(BaseModel):
    line_id: str | None = None
    kind: str = "line"  # line | section | subsection | text | pagebreak
    line_kind: str = ""  # fourniture | main_oeuvre | ouvrage (pour kind == line)
    title: str = ""  # pour section / subsection
    text: str = ""   # pour bloc texte libre
    components: list[dict] = []  # sous-éléments d'un ouvrage composé
    photos: list[dict] = []  # jusqu'à 3 photos {photo_id, storage_path} par ligne
    collapsed: bool = False
    designation: str = ""
    description: str = ""
    unit: str = "u"
    qty: float = Field(1, ge=-1e9, le=1e9, allow_inf_nan=False)
    unit_price_ht: float = Field(0, ge=-1e9, le=1e9, allow_inf_nan=False)
    discount_pct: float = Field(0, ge=0, le=100, allow_inf_nan=False)
    cost_price_ht: float = Field(0, ge=0, le=1e9, allow_inf_nan=False)
    cost_confirmed_zero: bool = False
    vat_rate: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)
    vat_suggestion: float | None = None
    vat_suggestion_reason: str = ""
    category: str = ""
    price_source: str = ""
    price_reference: str = ""
    price_reference_label: str = ""
    price_estimated: bool = False
    price_missing: bool = False
    quantity_missing: bool = False
    vat_assumed: bool = False
    vat_confirmed: bool = False


class PaymentStage(BaseModel):
    label: str = ""
    pct: float = Field(default=0, ge=0, le=100)


class DocIn(BaseModel):
    expected_updated_at: str | None = Field(default=None, min_length=1, max_length=60)
    doc_type: str = "quote"
    client_id: str | None = None
    title: str = ""
    lines: list[DocLine] = []
    notes: str = ""
    payment_terms: str = ""
    deposit_pct: float = Field(default=0, ge=0, le=100)
    status: str | None = None
    lead_id: str | None = None
    chantier_id: str | None = None
    # Échéancier, validité et infos chantier (modèles du kit CMRENOV)
    valid_until: str | None = None
    validity_days: int = Field(default=30, ge=0, le=365)
    project_address: str = ""
    project_duration: str = ""
    project_start: str = ""
    payment_schedule: list[PaymentStage] = []


def _quote_extras(body: "DocIn") -> dict:
    """Champs devis additionnels : validité, infos chantier, échéancier de règlement."""
    stages = []
    for s in (body.payment_schedule or [])[:8]:
        lab = (s.label or "").strip()[:60]
        if lab:
            stages.append({"label": lab, "pct": round(float(s.pct or 0), 2)})
    return {
        "validity_days": int(body.validity_days or 0),
        "valid_until": (body.valid_until or "").strip() or None,
        "project_address": (body.project_address or "").strip()[:200],
        "project_duration": (body.project_duration or "").strip()[:80],
        "project_start": (body.project_start or "").strip()[:80],
        "payment_schedule": stages,
    }


async def _chantier_link(chantier_id: str | None, user_id: str) -> dict:
    from routes.chantiers import owned_chantier_id
    return {"chantier_id": await owned_chantier_id(user_id, chantier_id)}


async def _lead_link(lead_id: str | None, user_id: str) -> dict:
    """Rattache un devis à la demande (lead) et au chantier du particulier."""
    if not lead_id:
        return {}
    lead = await db.leads.find_one({"lead_id": lead_id, "$or": [{"assigned_to": user_id}, {"candidates.user_id": user_id}, {"candidates": user_id}]}, {"_id": 0, "project_id": 1, "user_id": 1})
    if not lead:
        return {}
    return {"lead_id": lead_id, "project_id": lead.get("project_id"), "homeowner_user_id": lead.get("user_id")}


def _pdf_filename(doc: dict) -> str:
    """Nom de fichier du PDF : type + numéro + titre + client (si renseignés)."""
    import re as _re
    kind = {"quote": "Orçamento", "invoice": "Fatura"}.get(doc.get("doc_type"), "Documento")
    parts = [kind, (doc.get("number") or "").strip()]
    if (doc.get("title") or "").strip():
        parts.append(doc["title"].strip())
    c = doc.get("client") or {}
    who = " ".join(x for x in [(c.get("first_name") or "").strip(), (c.get("last_name") or "").strip()] if x).strip() or (c.get("company") or "").strip()
    if who:
        parts.append(who)
    raw = " - ".join(p for p in parts if p)
    safe = _re.sub(r"[^\w\-.() ]+", "", raw, flags=_re.UNICODE).strip() or (doc.get("doc_id") or "document")
    return f"{safe[:120]}.pdf"



def _compute_totals(lines: list[dict], deposit_pct: float = 0.0) -> dict:
    """Totaux HT/TVA/TTC + couverture des coûts.

    Un coût n'est « connu » que s'il est > 0 ou explicitement confirmé nul (``cost_confirmed_zero``).
    La marge globale n'est publiée que si tous les coûts sont connus ; sinon on expose la
    couverture et une marge partielle clairement marquée comme telle.
    """
    ht = 0.0
    cost = 0.0
    covered_ht = 0.0
    known = 0
    total_lines = 0
    vat_unset = 0
    vat_assumed = 0
    tva_map: dict[float, float] = {}
    from decimal import Decimal, ROUND_HALF_UP
    tax_bases: dict[float, Decimal] = {}
    for ln in lines:
        if ln.get("kind") in ("section", "subsection", "text", "pagebreak"):
            continue
        qty = ln.get("qty") or 0
        disc = float(ln.get("discount_pct") or 0)
        line_ht = float((Decimal(str(qty)) * Decimal(str(ln.get("unit_price_ht") or 0))
                         * (1 - Decimal(str(disc)) / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        ht += line_ht
        total_lines += 1
        c = float(ln.get("cost_price_ht") or 0)
        if c > 0 or ln.get("cost_confirmed_zero"):
            known += 1
            covered_ht += line_ht
            cost += round(qty * c, 2)
        if ln.get("vat_rate") is None:
            vat_unset += 1
        if ln.get("vat_assumed"):
            vat_assumed += 1
        rate = float(ln.get("vat_rate") or 0)
        tax_bases[rate] = tax_bases.get(rate, Decimal(0)) + Decimal(str(line_ht))
    tva_map = {rate: float((base * Decimal(str(rate)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
               for rate, base in tax_bases.items()}
    ht = round(ht, 2)
    tva = round(sum(tva_map.values()), 2)
    ttc = round(ht + tva, 2)
    deposit = round(ttc * (deposit_pct or 0) / 100, 2)
    complete = total_lines > 0 and known == total_lines
    has_any = known > 0
    margin = round(ht - cost, 2) if complete else None
    partial_margin = round(covered_ht - cost, 2) if has_any and not complete else None
    return {
        "ht": ht,
        "cost_ht": round(cost, 2) if has_any else None,
        "margin_ht": margin,
        "margin_pct": (round(margin / ht * 100, 1) if complete and ht > 0 else None),
        "cost_coverage": {"known_lines": known, "total_lines": total_lines, "complete": complete,
                          "covered_ht": round(covered_ht, 2), "missing_lines": total_lines - known},
        "partial_margin_ht": partial_margin,
        "partial_margin_pct": (round(partial_margin / covered_ht * 100, 1) if partial_margin is not None and covered_ht > 0 else None),
        "vat_unset_lines": vat_unset,
        "vat_assumed_lines": vat_assumed,
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


async def _doc_lang(doc: dict, branding: dict | None) -> str:
    """Langue des PDF : celle du document, sinon PT si l'entreprise est au Portugal, sinon FR."""
    if doc.get("lang") in ("fr", "pt"):
        return doc["lang"]
    return "pt" if ((branding or {}).get("country") or "").upper() == "PT" else "pt"


async def apply_fiscal_policy(user: dict, lines: list, *text_hints: str) -> dict:
    """Applique la politique fiscale de l'ENTREPRISE (jamais la langue) aux lignes générées.

    Le taux par défaut est le taux normal du pays ; un taux réduit déduit du texte n'est
    qu'une suggestion (``vat_suggestion``) à confirmer par l'utilisateur.
    """
    branding = None
    if user:
        from routes.plans_common import _resolve_branding
        branding = await _resolve_branding(user["user_id"])
    country = ((branding or {}).get("country") or "").upper()
    policy = policy_for(country)
    suggestion = suggest_reduced_rate(country, *text_hints)
    for ln in lines:
        if ln.get("vat_rate") is None or not ln.get("vat_confirmed"):
            ln["vat_rate"] = policy["default_rate"]
            ln["vat_assumed"] = True
        if suggestion:
            ln["vat_suggestion"] = suggestion["rate"]
            ln["vat_suggestion_reason"] = suggestion["reason"]
    return policy


async def _apply_pt_vat(user: dict, lines: list, *text_hints: str) -> None:
    await apply_fiscal_policy(user, lines, *text_hints)


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
        return (f'Olá {name},\n\nSegue em anexo a sua fatura n.º {number}.\n\nAguardamos o seu pagamento.\n\nCom os melhores cumprimentos,\n{company}')
    if _reduced_vat_rate(doc) is not None:
        return (f'Olá {name},\n\nSegue em anexo o seu orçamento n.º {number} bem como a declaração correspondente, pré-preenchida, que permite beneficiar da taxa reduzida de IVA nas suas obras (verba 2.27 da Lista I do CIVA, quando aplicável).\n\nAgradecemos a sua confiança.\n\nCom os melhores cumprimentos,\n{company}')
    return (f'Olá {name},\n\nSegue em anexo o orçamento correspondente ao seu pedido de orçamento n.º {number}.\n\nContinuamos ao seu inteiro dispor para qualquer informação complementar ou para discutir alguns pontos, se necessário.\n\nAguardando o seu contacto, agradecemos a sua confiança.\n\nCom os melhores cumprimentos,\n{company}')


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
    return (f'<p style="margin:18px 0"><a href="{url}" style="background:#0A0D14;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">🏠 Ver a projeção antes / depois da obra</a></p>')



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
        raise HTTPException(404, "Documento não encontrado")
    require_feature(user, document_feature(doc.get("doc_type")))
    return doc


class DescribeIn(BaseModel):
    designation: str
    context: str = ""


@router.post("/ai/describe")
async def ai_describe_line(body: DescribeIn, user=Depends(current_user)) -> dict:
    """Suggestions IA : génère une description de prestations pour une ligne de devis."""
    designation = (body.designation or "").strip()
    if not designation:
        raise HTTPException(400, "Indique primeiro uma designação de linha")
    from engines.ai import suggest_line_description
    try:
        text = await suggest_line_description(designation, (body.context or "").strip()[:400])
    except Exception as e:
        logging.getLogger("documents").exception("ai describe failed")
        raise HTTPException(502, f'Sugestão IA indisponível: {type(e).__name__}')
    return {"description": (text or "").strip()}


class CheckIn(BaseModel):
    lines: list[DocLine] = []
    chantier_id: str | None = None
    title: str = ""
    use_ai: bool = True


@router.post("/check")
async def check_quote(body: CheckIn, user=Depends(current_user)) -> dict:
    """Contrôleur de devis avant envoi (Module 3) : alertes déterministes + règles + IA optionnelle."""
    lines = [l.model_dump() for l in body.lines]
    totals = _compute_totals(lines, 0)
    from routes.plans_common import _resolve_branding
    country = (((await _resolve_branding(user["user_id"])) or {}).get("country") or "").upper()
    policy = policy_for(country)
    metre = None
    cid = await owned_chantier_id_safe(body.chantier_id, user["user_id"])
    if cid:
        p = await db.plans_takeoff.find_one(
            {"chantier_id": cid, "user_id": user["user_id"], "structural_metre": {"$exists": True}},
            {"_id": 0, "structural_metre": 1}, sort=[("created_at", -1)])
        if p and p.get("structural_metre"):
            metre = p["structural_metre"]
    from engines.quote_check import run_quote_check
    result = await run_quote_check(lines, totals, policy, metre,
                                   use_ai=bool(body.use_ai), context=(body.title or "").strip())
    result["totals"] = {"ht": totals["ht"], "ttc": totals["ttc"],
                        "margin_ht": totals.get("margin_ht"), "margin_pct": totals.get("margin_pct")}
    return result


async def owned_chantier_id_safe(chantier_id: str | None, user_id: str) -> str | None:
    if not chantier_id:
        return None
    try:
        from routes.chantiers import owned_chantier_id
        return await owned_chantier_id(user_id, chantier_id)
    except Exception:
        return None


class DismissIn(BaseModel):
    key: str = Field(..., min_length=3, max_length=40)
    status: Literal["fixed", "elsewhere", "dismissed"] = "dismissed"
    reason: str = Field("", max_length=300)


@router.get("/{doc_id}/check/dismissals")
async def list_dismissals(doc_id: str, user=Depends(current_user)) -> dict:
    rows = await db.quote_check_dismissals.find(
        {"user_id": user["user_id"], "doc_id": doc_id}, {"_id": 0, "key": 1, "status": 1, "reason": 1}).to_list(500)
    return {"items": rows}


@router.post("/{doc_id}/check/dismissals")
async def save_dismissal(doc_id: str, body: DismissIn, user=Depends(current_user)) -> dict:
    await db.quote_check_dismissals.update_one(
        {"user_id": user["user_id"], "doc_id": doc_id, "key": body.key},
        {"$set": {"status": body.status, "reason": body.reason.strip()[:300], "updated_at": _now()}},
        upsert=True)
    return {"ok": True}


@router.delete("/{doc_id}/check/dismissals/{key}")
async def delete_dismissal(doc_id: str, key: str, user=Depends(current_user)) -> dict:
    await db.quote_check_dismissals.delete_one(
        {"user_id": user["user_id"], "doc_id": doc_id, "key": key})
    return {"ok": True}


class DepositIn(BaseModel):
    pct: float = Field(default=30, ge=1, le=100)


async def build_deposit_invoice(doc_id: str, user: dict, pct: float = 30) -> dict:
    """Crée une facture d'acompte à partir d'un devis SIGNÉ.
    Une ligne par taux de TVA, sans le détail du devis, référencée « Acompte …% sur devis N°… ».
    Réutilisée par l'endpoint manuel et par l'automatisme déclenché à la signature du client."""
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    if not (q.get("signed") or q.get("status") == "signed"):
        raise HTTPException(status_code=400, detail="O orçamento tem de estar assinado para faturar um adiantamento")
    if q.get("deposit_invoice_id"):
        raise HTTPException(status_code=400, detail="Já existe uma fatura de adiantamento para este orçamento")
    pct = max(1.0, min(100.0, float(pct or 30)))

    ht_by_rate: dict[float, float] = {}
    for ln in q.get("lines", []):
        if ln.get("kind") in ("section", "subsection", "text", "pagebreak"):
            continue
        rate = float(ln.get("vat_rate") or 0)
        line_ht = round((ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0)
                        * (1 - float(ln.get("discount_pct") or 0) / 100), 2)
        ht_by_rate[rate] = ht_by_rate.get(rate, 0) + line_ht
    if not ht_by_rate:
        raise HTTPException(status_code=400, detail="O orçamento não contém nenhuma linha com preço")

    num = q.get("number") or q["doc_id"]
    pct_txt = f"{pct:g}"
    multi = len(ht_by_rate) > 1
    lines = []
    for rate, ht in sorted(ht_by_rate.items()):
        desig = f'Adiantamento {pct_txt}% sobre o orçamento N.º{num}' + (f" — TVA {rate:g}%" if multi else "")
        lines.append({"designation": desig, "description": (q.get("title") or "").strip()[:200],
                      "unit": "forfait", "qty": 1, "unit_price_ht": round(ht * pct / 100, 2),
                      "vat_rate": rate, "category": "Adiantamento"})

    from datetime import timedelta
    number = await _next_number(user["user_id"], "invoice")
    now = _now()
    totals = _compute_totals(lines, 0)
    inv = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": user["user_id"],
        "doc_type": "invoice", "number": number,
        "title": f'Fatura de adiantamento {pct_txt}% — orçamento N.º{num}',
        "client_id": q.get("client_id"), "client": q.get("client"),
        "status": "draft", "lines": lines,
        "notes": f'Fatura de adiantamento de {pct_txt}% correspondente ao orçamento N.º{num}.',
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


@router.post("/{doc_id}/deposit-invoice")
async def create_deposit_invoice(doc_id: str, body: DepositIn, user=Depends(current_user)) -> dict:
    return await build_deposit_invoice(doc_id, user, body.pct or 30)


class AutoDepositIn(BaseModel):
    enabled: bool
    pct: Literal[10, 20, 30, 40, 50] | None = None


@router.get("/settings/auto-deposit")
async def get_auto_deposit(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                {"_id": 0, "auto_deposit_invoice": 1, "auto_deposit_pct": 1}) or {}
    return {"enabled": bool(u.get("auto_deposit_invoice")),
            "pct": int(u.get("auto_deposit_pct") or 30)}


@router.put("/settings/auto-deposit")
async def set_auto_deposit(body: AutoDepositIn, user=Depends(current_user)) -> dict:
    upd = {"auto_deposit_invoice": body.enabled}
    if body.pct:
        upd["auto_deposit_pct"] = int(body.pct)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return {"enabled": body.enabled, "pct": int(upd.get("auto_deposit_pct") or 30)}


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
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    children = await _quote_children(user["user_id"], doc_id)
    q_ht = q.get("totals", {}).get("ht", 0)
    q_ttc = q.get("totals", {}).get("ttc", 0)
    billed_ht = sum(c.get("totals", {}).get("ht", 0) for c in children)
    billed_ttc = sum(c.get("totals", {}).get("ttc", 0) for c in children)
    from engines.deposit_credit import deposit_state
    dep = await deposit_state(user["user_id"], doc_id)
    return {
        "quote": {"doc_id": q["doc_id"], "number": q.get("number"), "ht": q_ht, "ttc": q_ttc,
                  "signed": bool(q.get("signed") or q.get("status") == "signed")},
        "deposit": dep,
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
    deposit_mode: str = Field(default="prorata")  # none | prorata | full | manual
    deposit_amount_ht: float = Field(default=0, ge=0)


async def _create_child_invoice(q: dict, user: dict, lines: list, title: str, note: str,
                                source: str, extra: dict | None = None) -> dict:
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
    inv.update(extra or {})
    await db.pro_documents.insert_one(dict(inv))
    inv.pop("_id", None)
    return inv


@router.post("/{doc_id}/situation-invoice")
async def create_situation_invoice(doc_id: str, body: SituationIn, user=Depends(current_user)) -> dict:
    """Facture de situation au prorata (pct d'avancement), acompte encaissé déduit."""
    from engines.deposit_credit import deposit_state, imputation_amount, deduction_lines
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    if not (q.get("signed") or q.get("status") == "signed"):
        raise HTTPException(status_code=400, detail="O orçamento deve ser assinado")
    pct = float(body.pct)
    num = q.get("number") or q["doc_id"]
    children = await _quote_children(user["user_id"], doc_id)
    prev_sits = [c for c in children if c.get("source") == "situation"]
    sit_no = len(prev_sits) + 1
    quote_ht_by_rate = _ht_by_rate(q.get("lines", []))
    multi = len(quote_ht_by_rate) > 1
    lines = []
    for rate, ht in sorted(quote_ht_by_rate.items()):
        suffix = f" — TVA {rate:g}%" if multi else ""
        lines.append({"designation": f'Auto de medição n.º{sit_no} — avancement {pct:g}% — orçamento N.º{num}{suffix}',
                      "description": (q.get("title") or "").strip()[:200], "unit": "forfait", "qty": 1,
                      "unit_price_ht": round(ht * pct / 100, 2), "vat_rate": rate, "category": "Situação"})
    works_ht = round(sum(l["unit_price_ht"] for l in lines), 2)
    quote_ht = float((q.get("totals") or {}).get("ht") or 0)
    billed_before = round(sum(float(c.get("works_ht") or (c.get("totals") or {}).get("ht") or 0)
                              for c in prev_sits), 2)
    cumul_ratio = ((billed_before + works_ht) / quote_ht) if quote_ht else 0.0

    dep_state = await deposit_state(user["user_id"], doc_id)
    deposit_ht = imputation_amount(body.deposit_mode, dep_state, cumul_ratio,
                                   works_ht, body.deposit_amount_ht)
    lines += deduction_lines(deposit_ht, dep_state)

    title = f'Auto de medição n.º{sit_no} ({pct:g}%) — orçamento N.º{num}'
    note = f'Auto de medição n.º{sit_no} pro rata ({pct:g}% de execução) do orçamento N.º{num}.' \
           + (f' Adiantamento já pago deduzido: -{deposit_ht:.2f} € HT.' if deposit_ht else "")
    inv = await _create_child_invoice(q, user, lines, title, note, "situation",
                                      {"works_ht": works_ht, "deposit_imputed_ht": deposit_ht,
                                       "deposit_mode": body.deposit_mode})
    return inv


@router.post("/{doc_id}/balance-invoice")
async def create_balance_invoice(doc_id: str, user=Depends(current_user)) -> dict:
    """Facture de solde : reste dû = total devis − déjà facturé (acomptes + situations), par taux de TVA."""
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not q or q.get("doc_type") != "quote":
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    if not (q.get("signed") or q.get("status") == "signed"):
        raise HTTPException(status_code=400, detail="O orçamento deve ser assinado")
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
        lines.append({"designation": f'Saldo — orçamento N.º{num}{suffix}',
                      "description": (q.get("title") or "").strip()[:200], "unit": "forfait", "qty": 1,
                      "unit_price_ht": remaining, "vat_rate": rate, "category": "Saldo"})
    if not lines:
        raise HTTPException(status_code=400, detail="Nada a faturar: o orçamento já está totalmente faturado")
    inv = await _create_child_invoice(q, user, lines, f'Fatura de saldo — orçamento N.º{num}',
                                      f'Fatura de saldo do orçamento N.º{num} (dedução dos adiantamentos e autos de medição já faturados).',
                                      "balance")
    return inv


CONTENT_FIELDS = ("title", "client_id", "lines", "notes", "payment_terms", "deposit_pct")


def _content_hash(doc: dict) -> str:
    """Empreinte SHA-256 du contenu commercial (lignes, client, conditions)."""
    payload = {k: doc.get(k) for k in CONTENT_FIELDS}
    payload["lines"] = [{k: v for k, v in (ln or {}).items() if not str(k).startswith("_")} for ln in (doc.get("lines") or [])]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _is_frozen(doc: dict) -> bool:
    """Contenu figé : devis signé, ou facture/avoir déjà émis (tout statut hors brouillon)."""
    if doc.get("signed") or doc.get("status") == "signed":
        return True
    return doc.get("doc_type") in ("invoice", "credit_note") and doc.get("status") not in (None, "draft")


async def _freeze_document(doc_id: str, user: dict, reason: str) -> dict:
    """Snapshot immuable (contenu + empreinte + PDF) conservé à la signature / émission."""
    doc = await _get_owned(doc_id, user)
    h = _content_hash(doc)
    frozen = {"frozen_hash": h, "frozen_at": _now(), "frozen_reason": reason,
              "frozen_snapshot": {k: doc.get(k) for k in CONTENT_FIELDS + ("totals", "client", "number")}}
    try:
        from engines.pdf_docs import build_document_pdf
        from routes.plans_common import _resolve_branding
        from routes.company_page import pdf_customization
        branding = {**(await _resolve_branding(user["user_id"]) or {}), **await pdf_customization(user["user_id"])}
        pdf = build_document_pdf(doc, branding=branding, reviews=None, lang=await _doc_lang(doc, branding))
        frozen["frozen_pdf_b64"] = base64.b64encode(pdf).decode()
    except Exception as exc:  # noqa: BLE001 — le PDF figé est un plus, l'empreinte fait foi
        logging.getLogger(__name__).warning("frozen pdf failed for %s: %s", doc_id, exc)
    await db.pro_documents.update_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"$set": frozen})
    return frozen


async def _create_revision(previous: dict, candidate: dict, user: dict) -> dict:
    """Nouvelle révision brouillon liée au document figé ; l'original reste consultable."""
    rev_no = int(previous.get("revision") or 1) + 1
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": user["user_id"], "doc_type": previous.get("doc_type", "quote"),
        "number": None, "title": candidate["title"], "client_id": candidate["client_id"],
        "client": await _client_snapshot(candidate["client_id"], user) if candidate["client_id"] else previous.get("client"),
        "lead_id": previous.get("lead_id"), "project_id": previous.get("project_id"), "homeowner_user_id": previous.get("homeowner_user_id"),
        "chantier_id": previous.get("chantier_id"),
        "status": "draft", "signed": False, "lines": candidate["lines"], "notes": candidate["notes"], "payment_terms": candidate["payment_terms"],
        "deposit_pct": candidate["deposit_pct"], "totals": _compute_totals(candidate["lines"], candidate["deposit_pct"]),
        "issue_date": None, "due_date": None, "source": previous.get("source") or "manual",
        "revision": rev_no, "revision_of": previous["doc_id"], "root_doc_id": previous.get("root_doc_id") or previous["doc_id"],
        "created_at": _now(), "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    await db.pro_documents.update_one({"doc_id": previous["doc_id"], "user_id": user["user_id"]},
                                      {"$set": {"superseded_by": doc["doc_id"], "updated_at": _now()}})
    return doc


GENERATED_SOURCES_MANUAL = {"", "manual", "library", "company_library", "user"}


async def normalize_generated_vat(user: dict, lines: list[dict]) -> None:
    """Toute ligne produite par un générateur (plan, photo, dictée, CCTP, solveur…) prend le taux
    normal de la politique fiscale de l'entreprise, marqué « à confirmer », sauf si l'utilisateur l'a confirmé."""
    generated = [ln for ln in lines if (ln.get("price_source") or "") not in GENERATED_SOURCES_MANUAL and not ln.get("vat_confirmed")]
    if not generated:
        return
    from routes.plans_common import _resolve_branding
    policy = policy_for(((await _resolve_branding(user["user_id"])) or {}).get("country"))
    for ln in generated:
        ln["vat_rate"] = policy["default_rate"]
        ln["vat_assumed"] = True


@router.get("/fiscal-profile")
async def fiscal_profile(user=Depends(current_user)) -> dict:
    """Politique TVA de l'entreprise (pays du profil), indépendante de la langue d'affichage."""
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"])
    policy = policy_for((branding or {}).get("country"))
    return {**policy, "source": "company_profile" if policy["known"] else "unknown",
            "message": None if policy["known"] else "País da empresa não preenchido: escolha a taxa de IVA de cada linha, nenhuma predefinição é aplicada."}


@router.post("")
async def create_document(body: DocIn, user=Depends(current_user)) -> dict:
    dtype = body.doc_type if body.doc_type in DOC_TYPES else "quote"
    # Also enforce permissions when called by an agent, outside FastAPI dependencies.
    await pro_required(user)
    require_feature(user, document_feature(dtype))
    lines = [ln.model_dump() for ln in body.lines]
    await normalize_generated_vat(user, lines)
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": dtype,
        "number": None,
        "title": (body.title or "").strip()[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        **(await _lead_link(body.lead_id, user["user_id"])),
        **(await _chantier_link(body.chantier_id, user["user_id"])),
        "status": body.status or "draft",
        "lines": lines,
        "notes": (body.notes or "").strip()[:2000],
        "payment_terms": (body.payment_terms or "").strip()[:300],
        "deposit_pct": body.deposit_pct or 0,
        "totals": _compute_totals(lines, body.deposit_pct),
        **_quote_extras(body),
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
        raise HTTPException(400, "Nenhum ficheiro fornecido")
    results: list[dict] = []
    max_seq: dict[str, int] = {}
    for f in files[:20]:
        name = f.filename or "document.pdf"
        try:
            data = await f.read()
            if not data or not name.lower().endswith(".pdf"):
                results.append({"file": name, "ok": False, "error": "Ficheiro não PDF"})
                continue
            text = _pdf_extract_text(data)
            images = [] if len(text) >= 120 else _pdf_render_images(data)
            if len(text) < 120 and not images:
                results.append({"file": name, "ok": False, "error": "PDF ilegível"})
                continue
            ext = await extract_document_from_pdf(
                text=text if len(text) >= 120 else "", images=images or None)
            lines = ext.get("lines") or []
            if not lines:
                results.append({"file": name, "ok": False, "error": "Nenhuma linha detetada"})
                continue
            dtype = ext.get("doc_type") or "quote"
            client_id = await _find_or_create_client(user["user_id"], ext.get("client") or {})
            number = (ext.get("number") or "").strip() or None
            label = "Fatura" if dtype == "invoice" else ("Nota de crédito" if dtype == "credit_note" else "Orçamento")
            totals = _compute_totals(lines, 0)
            doc_status = STATUS_MAP[chosen][dtype]
            doc = {
                "doc_id": "doc_" + secrets.token_hex(6),
                "user_id": user["user_id"],
                "doc_type": dtype,
                "number": number,
                "title": f'{label} importado — {name[:60]}',
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
        return {"file": name, "ok": False, "error": "Ficheiro não PDF"}
    text = _pdf_extract_text(data)
    images = [] if len(text) >= 120 else _pdf_render_images(data)
    if len(text) < 120 and not images:
        return {"file": name, "ok": False, "error": "PDF ilegível"}
    ext = await extract_document_from_pdf(text=text if len(text) >= 120 else "", images=images or None)
    if not ext.get("lines"):
        return {"file": name, "ok": False, "error": "Nenhuma linha detetada"}
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
            "category": l.get("category") or "Importado",
        })
    client_id = await _find_or_create_client(user["user_id"], item.get("client") or {})
    number = (item.get("number") or "").strip() or None
    label = "Fatura" if dtype == "invoice" else ("Nota de crédito" if dtype == "credit_note" else "Orçamento")
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
        raise HTTPException(400, "Nenhum ficheiro fornecido")
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
            results.append({"file": it.get("file", ""), "ok": False, "error": "Sem linhas"})
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
            "vat_rate": 6,
            "category": "A partir de planta IA",
        })
    await _apply_pt_vat(user, lines, quote.get("filename") or "")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "quote",
        "number": None,
        "title": f"Orçamento — {quote.get('filename') or 'plan'}",
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


_CONCRETE_LABELS = {"slab": "Lajes", "beam": "Vigas", "column": "Pilares", "wall": "Paredes", "footing": "Sapatas"}


@router.post("/from-autopilot/{dossier_id}")
async def document_from_autopilot(dossier_id: str, client_id: str | None = None,
                                  margin_pct: float = 12.0, vat_rate: float = 23.0,
                                  user=Depends(current_user)) -> dict:
    """Crée un devis brouillon « Gros œuvre » depuis le métré de l'auto-pilote BET (lignes modifiables)."""
    d = await db.bet_dossiers.find_one(
        {"dossier_id": dossier_id, "user_id": user["user_id"]}, {"_id": 0, "autopilot": 1, "title": 1})
    if not d or not d.get("autopilot"):
        raise HTTPException(404, "Nenhum piloto automático gerado para este processo.")
    metre = ((d["autopilot"].get("summary") or {}).get("metre"))
    if not metre or not metre.get("concrete"):
        raise HTTPException(422, "Medição indisponível: relance a geração do piloto automático.")
    margin = max(0.0, min(float(margin_pct or 0), 100.0)) / 100.0
    vat = max(0.0, min(float(vat_rate or 0), 100.0))
    pc = float(metre["cost"].get("concrete_eur_m3") or 150)
    ps = float(metre["cost"].get("steel_eur_kg") or 2)
    lines: list[dict] = [{"kind": "section", "title": "Estrutura (piloto automático de projeto)"}]
    for k, v in (metre["concrete"].get("by_type_m3") or {}).items():
        if float(v or 0) <= 0:
            continue
        lines.append({"kind": "line", "line_kind": "ouvrage",
                      "designation": f'Betão {_CONCRETE_LABELS.get(k, k)} (fornecimento + aplicação)',
                      "description": "Volume resultante do pré-dimensionamento determinístico — indicativo, a verificar",
                      "unit": "m³", "qty": round(float(v), 2), "unit_price_ht": round(pc * (1 + margin), 2),
                      "vat_rate": vat, "vat_confirmed": True, "category": "Estrutura · Betão", "price_estimated": True})
    for r in (metre["steel"].get("schedule") or []):
        kg = round(float(r.get("weight_kg") or 0), 1)
        if kg <= 0:
            continue
        lines.append({"kind": "line", "line_kind": "fourniture",
                      "designation": f"Aço {r.get('mark', '')} — {r.get('type', '')} (fornecimento, moldagem e colocação)".strip(),
                      "description": f"{r.get('level', '')} · {r.get('bars', '')}".strip(" ·"),
                      "unit": "kg", "qty": kg, "unit_price_ht": round(ps * (1 + margin), 2),
                      "vat_rate": vat, "vat_confirmed": True, "category": "Estrutura · Aço", "price_estimated": True})
    if len(lines) <= 1:
        raise HTTPException(422, "Medição vazia: nenhuma quantidade a orçamentar.")
    await _apply_pt_vat(user, lines, "estrutura betao aco piloto automatico")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": user["user_id"], "doc_type": "quote",
        "number": None, "title": f"Orçamento de estrutura — {d.get('title') or 'Auto-pilote BET'}",
        "client_id": client_id, "client": await _client_snapshot(client_id, user),
        "status": "draft", "lines": lines, "notes": "Quantidades resultantes do pré-dimensionamento determinístico (piloto automático de projeto) — indicativas, a verificar e completar pelo engenheiro.",
        "payment_terms": "", "deposit_pct": 0, "totals": _compute_totals(lines, 0),
        "issue_date": None, "due_date": None, "source": "autopilot_bet",
        "autopilot_dossier_id": dossier_id, "created_at": _now(), "updated_at": _now(),
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
            "designation": f"Aço {dia.get('diameter', '')} — fornecimento, moldagem e colocação",
            "description": f"{dia.get('ml', 0)} ml (perdas {int(loss * 100)}%)",
            "unit": "kg", "qty": kg, "unit_price_ht": ACIER_PRICE_KG,
            "vat_rate": vat, "category": f"{prefix} · Ferraillage",
        })
    for t in treillis:
        panels = int(t.get("panels") or 0)
        if panels <= 0:
            continue
        out.append({
            "designation": f"Malha eletrossoldada {t.get('ref', '')}".strip(),
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
        prefix = f'Estrutura · {fname}'
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
            lines += await _ferraillage_lines(fid, user_id, f'Estrutura · {fname}', vat)
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
                    "category": f'{prefix} · A partir de planta IA',
                })
        except HTTPException:
            pass
        return lines, prefix

    # FERRAILLAGE seul (sélectionné directement)
    if plan_id not in processed_ferr:
        processed_ferr.add(plan_id)
        vat = 0.0 if subcontract else 20.0
        ferr = await _ferraillage_lines(plan_id, user_id, f'Armaduras · {fname}', vat)
        if ferr:
            return ferr, f'Armaduras · {fname}'
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
        raise HTTPException(400, "Nenhuma planta selecionada contém medição orçamentável (meça/analise primeiro as plantas).")
    title = (body.project_name.strip()
             or f"Orçamento de projeto — {len(included)} plan{('s' if len(included) > 1 else '')}")
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


_WHISPER_PROMPT_FR = ("Orçamento de obras de construção: remoção, demolição, pladur, divisória, forro, reboco, betonilha de regularização, cerâmico, azulejo, soalho, pintura, canalização, base de duche embutida, móvel de lavatório, sanita suspensa, eletricidade, quadro elétrico, tomadas, domótica KNX, ventilação mecânica, isolamento, caixilharia, cobertura, alvenaria, bloco de cimento, laje de betão, movimentos de terras, metros quadrados, metros lineares, valor global.")
_WHISPER_PROMPT_PT = ("Orçamento de obras : demolição, pladur, divisórias, reboco, azulejo, mosaico, pavimento, pintura, "
                      "canalização, base de duche, móvel de lavatório, eletricidade, quadro elétrico, tomadas, domótica, "
                      "isolamento, caixilharia, cobertura, alvenaria, betão, metros quadrados, metros lineares.")


async def _transcribe_video_bytes(raw: bytes, lang: str = "pt") -> str:
    """Extrait l'audio d'une vidéo (ffmpeg) et le transcrit (Whisper, vocabulaire BTP)."""
    import os
    import shutil
    import subprocess
    import tempfile
    if not raw:
        raise HTTPException(400, "Vídeo vazio")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(413, "Vídeo demasiado volumoso (>80 MB). Filme uma sequência mais curta.")
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
            raise HTTPException(422, "Impossível extrair o áudio do vídeo.")
        if os.path.getsize(audio) > 25 * 1024 * 1024:
            raise HTTPException(413, "Áudio demasiado longo (>25 MB). Filme uma sequência mais curta.")
        from emergentintegrations.llm.openai import OpenAISpeechToText
        stt = OpenAISpeechToText(api_key=os.environ["EMERGENT_LLM_KEY"])
        with open(audio, "rb") as af:
            resp = await stt.transcribe(file=af, model="whisper-1", response_format="text",
                                        language="pt" if lang == "pt" else "pt",
                                        prompt=_WHISPER_PROMPT_PT if lang == "pt" else _WHISPER_PROMPT_FR)
        transcript = resp if isinstance(resp, str) else (getattr(resp, "text", "") or "")
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger("documents").exception("video transcription failed")
        raise HTTPException(502, f'Transcrição indisponível: {type(e).__name__}')
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if not transcript.strip():
        raise HTTPException(422, "Nenhuma fala detetada no vídeo.")
    return transcript.strip()


async def _quote_doc_from_text(user: dict, text: str, client_id: str | None,
                               source: str = "video", images: list[str] | None = None) -> dict:
    """Génère un devis (lignes IA chiffrées via la bibliothèque) à partir d'un texte + photos."""
    from engines.ai import quote_lines_from_text
    from routes.plans_analysis import _apply_library_prices, library_hints_for_user
    if not (text or "").strip():
        raise HTTPException(400, "Description vide")
    hints = await library_hints_for_user(user["user_id"])
    lines, title = await quote_lines_from_text(text, images=images or None, library_hints=hints)
    if not lines:
        raise HTTPException(422, "A IA não conseguiu gerar linhas de orçamento a partir da descrição.")
    lines, priced = await _apply_library_prices(user["user_id"], lines)
    await _apply_pt_vat(user, lines, title or "", text or "")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"], "doc_type": "quote", "number": None,
        "title": title or "Orçamento (vídeo)",
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
    transcript = await _transcribe_video_bytes(raw, lang=user.get("lang") or "pt")
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
    transcript = await _transcribe_video_bytes(raw, lang=user.get("lang") or "pt")
    doc = await _quote_doc_from_text(user, transcript, client_id, source="video")
    doc["transcript"] = transcript
    return doc


@router.post("/cctp/extract")
async def cctp_extract(file: UploadFile = File(...), lot: str = "", user=Depends(current_user)) -> dict:
    """Lit un CCTP (PDF texte ou scanné) → ouvrages imposés + prescriptions, chiffrés via la bibliothèque.

    Ne crée pas de document : les lignes sont renvoyées pour être ajoutées au devis en cours.
    """
    from engines.ai import cctp_lines_from_text
    from routes.plans_analysis import _apply_library_prices
    raw = await file.read()
    if len(raw) > 40 * 1024 * 1024:
        raise HTTPException(413, "PDF demasiado volumoso (máx. 40 MB)")
    text = await asyncio.to_thread(_pdf_extract_text_long, raw)
    ocr_used = False
    if len(text) < 200:
        from engines.ai import ocr_pages_to_text
        images = await asyncio.to_thread(_pdf_render_images, raw, 16)
        if not images:
            raise HTTPException(422, "Caderno de encargos ilegível: impossível ler ou rasterizar este PDF.")
        text = await ocr_pages_to_text(images)
        ocr_used = True
        if len(text) < 200:
            raise HTTPException(422, "Caderno de encargos ilegível: o OCR não conseguiu extrair texto utilizável (digitalização demasiado desfocada ou clara). Tente novamente com uma digitalização mais nítida.")
    from routes.plans_analysis import library_hints_for_user
    lines, title, prescriptions = await cctp_lines_from_text(
        text, lot_filter=lot.strip(), library_hints=await library_hints_for_user(user["user_id"]))
    if not lines:
        raise HTTPException(422, "Nenhum trabalho identificado neste caderno de encargos.")
    lines, priced = await _apply_library_prices(user["user_id"], lines)
    return {"title": title, "lines": lines, "priced_lines": priced,
            "prescriptions": prescriptions, "chars": len(text), "ocr": ocr_used,
            "imposed_count": sum(1 for l in lines if l.get("imposed_materials"))}


def _pdf_extract_text_long(data: bytes, max_pages: int = 120) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages]).strip()
    except Exception:  # noqa: BLE001
        return ""



@router.get("")
async def list_documents(doc_type: str = "", client_id: str = "", status: str = "",
                         user=Depends(current_user)) -> dict:
    query: dict = {"user_id": user["user_id"]}
    if doc_type in DOC_TYPES:
        query["doc_type"] = doc_type
    else:
        perms = permissions_for(user)
        query["doc_type"] = {"$in": [dtype for dtype in DOC_TYPES if perms[document_feature(dtype)]]}
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
    previous = await _get_owned(doc_id, user)
    if body.expected_updated_at is not None and previous.get("updated_at") != body.expected_updated_at:
        raise HTTPException(409, "Este documento foi modificado noutro local. Releia a versão guardada antes de guardar.")
    lines = [ln.model_dump() for ln in body.lines]
    await normalize_generated_vat(user, lines)
    if _is_frozen(previous):
        candidate = {"title": (body.title or "").strip()[:160], "client_id": body.client_id, "lines": lines,
                     "notes": (body.notes or "").strip()[:2000], "payment_terms": (body.payment_terms or "").strip()[:300],
                     "deposit_pct": body.deposit_pct or 0}
        if _content_hash(candidate) != _content_hash(previous):
            if previous.get("doc_type") in ("invoice", "credit_note"):
                raise HTTPException(409, "Fatura emitida: o seu conteúdo está bloqueado. Corrija-a com uma nota de crédito («Criar uma nota de crédito»), nunca por modificação.")
            revision = await _create_revision(previous, candidate, user)
            return {**revision, "revision_created": True,
                    "message": "Orçamento assinado: o conteúdo bloqueado foi conservado e foi criada uma nova revisão em rascunho (não assinada)."}
        if body.status and body.status != previous.get("status"):
            raise HTTPException(409, "Utilize a mudança de estado dedicada para um documento assinado/emitido.")
        return previous
    upd = {
        "title": (body.title or "").strip()[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        **(await _lead_link(body.lead_id, user["user_id"])),
        **(await _chantier_link(body.chantier_id, user["user_id"])),
        "lines": lines,
        "notes": (body.notes or "").strip()[:2000],
        "payment_terms": (body.payment_terms or "").strip()[:300],
        "deposit_pct": body.deposit_pct or 0,
        "totals": _compute_totals(lines, body.deposit_pct),
        **_quote_extras(body),
        "updated_at": _now(),
        # Invalide le cache Factur-X : les lignes/totaux ont changé.
        "facturx_pdf_b64": None, "facturx_validation": None, "facturx_hash": None,
    }
    if body.status:
        upd["status"] = body.status
    if previous.get("source") == "assistant":
        if not body.client_id and not previous.get("client_id"):
            upd["client"] = previous.get("client")
        snapshot = upd.get("client") or {}
        upd["client_name"] = snapshot.get("company") or " ".join(filter(None, [snapshot.get("first_name"), snapshot.get("last_name")]))
    update_filter = {"doc_id": doc_id, "user_id": user["user_id"]}
    if body.expected_updated_at is not None:
        update_filter["updated_at"] = body.expected_updated_at
    result = await db.pro_documents.update_one(update_filter, {"$set": upd})
    if not result.matched_count:
        raise HTTPException(409, "Este documento foi modificado noutro local. Releia a sua versão atual.")
    try:
        from routes.library import auto_save_from_lines
        await auto_save_from_lines(user["user_id"], upd.get("lines"))
    except Exception:
        pass
    return await _get_owned(doc_id, user)


class StatusIn(BaseModel):
    status: str


ALLOWED_TRANSITIONS = {
    "quote": {"draft": {"sent", "signed", "refused"}, "sent": {"signed", "refused", "draft"}, "refused": {"draft", "sent"},
              "signed": set()},
    "invoice": {"draft": {"issued", "sent"}, "issued": {"sent", "partial", "paid"}, "sent": {"partial", "paid"},
                "partial": {"paid"}, "paid": set()},
    "credit_note": {"draft": {"issued", "sent"}, "issued": {"sent"}, "sent": set()},
}


@router.patch("/{doc_id}/status")
async def set_status(doc_id: str, body: StatusIn, user=Depends(current_user)) -> dict:
    allowed = {"draft", "sent", "signed", "refused", "partial", "paid", "issued"}
    if body.status not in allowed:
        raise HTTPException(400, "Estado inválido")
    doc = await _get_owned(doc_id, user)
    current = doc.get("status") or "draft"
    if body.status == current:
        return doc
    transitions = ALLOWED_TRANSITIONS.get(doc.get("doc_type"), ALLOWED_TRANSITIONS["quote"])
    if body.status not in transitions.get(current, set()):
        if current == "signed":
            raise HTTPException(409, "Orçamento assinado: a assinatura não pode ser retirada. Modifique o orçamento para criar uma nova revisão.")
        raise HTTPException(409, f'Transition {current} → {body.status} não autorizada para este documento.')
    upd = {"status": body.status, "updated_at": _now()}
    if body.status == "signed":
        upd["signed"] = True
        upd["signed_at"] = _now()
    await db.pro_documents.update_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"$set": upd})
    if body.status == "signed" or (doc.get("doc_type") in ("invoice", "credit_note") and current == "draft"):
        await _freeze_document(doc_id, user, reason=body.status)
    # Apprentissage auto : un devis SIGNÉ du compte propriétaire (admin) devient un exemple IA few-shot.
    if body.status == "signed" and doc.get("doc_type") == "quote" and user.get("role") == "admin":
        try:
            from engines.learning import create_from_document
            signed = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
            if signed:
                await create_from_document(signed, user["user_id"])
        except Exception:  # noqa: BLE001 — l'apprentissage ne doit jamais bloquer la signature
            pass
    return await _get_owned(doc_id, user)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, confirm_signed: bool = False, user=Depends(current_user)) -> dict:
    """Soft delete: the document goes to the bin (restorable 30 days). A signed document needs an explicit confirmation."""
    from routes.trash import trash_record
    doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Documento não encontrado")
    if doc.get("status") == "signed" and not confirm_signed:
        raise HTTPException(409, "Este documento está assinado: a sua eliminação requer uma confirmação explícita (confirm_signed=true).")
    res = await trash_record("document", doc, user["user_id"], {"doc_type": doc.get("doc_type"), "status": doc.get("status"), "signed_confirmed": doc.get("status") == "signed"})
    await db.pro_documents.delete_one({"doc_id": doc_id, "user_id": user["user_id"]})
    from engines import activity
    await activity.log(user, "document.delete", "document", doc.get("number") or doc.get("title") or doc_id)
    return res


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
            results.append({"doc_id": did, "ok": False, "error": "Não encontrado"})
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
    from routes.company_page import pdf_customization
    branding = {**(branding or {}), **await pdf_customization(user["user_id"])}
    reviews = await get_reviews_for_user(user["user_id"]) if doc["doc_type"] == "quote" else None
    sign_url = None
    if doc["doc_type"] == "quote" and not doc.get("signed"):
        from routes.project_quotes import _sign_token
        token = await _sign_token(doc, create=True)
        base = os.getenv("FRONTEND_URL", "").rstrip("/")
        sign_url = f"{base}/sign/{token}" if (token and base) else None
    # Page de garde + filigrane logo pour les devis projet consolidés
    cover = None
    watermark_logo = None
    cm = doc.get("cover_meta")
    if cm:
        from engines.pdf_takeoff import _styles as _cover_styles, build_cover_story, make_logo_watermark
        from routes.plans_common import _resolve_branding as _rb
        base_brand = await _rb(user["user_id"])
        cover = build_cover_story(
            base_brand,
            {"name": cm.get("project_name") or doc.get("title") or "Projeto",
             "levels_count": cm.get("levels_count", 0),
             "total_ttc": doc.get("total_ttc") or (doc.get("totals") or {}).get("ttc")},
            cm.get("client") or {}, cm.get("reference") or "", _cover_styles())
        watermark_logo = (base_brand or {}).get("logo_b64")
    # Annexe « Détail des cotes » pour les devis projet multi-niveaux
    appendix = None
    if cm and cm.get("group_id"):
        try:
            from routes.plans_analysis import _detail_cotes_flowables, _ensure_level_thumb
            from engines.pdf_takeoff import _styles as _ap_styles
            from reportlab.platypus import Paragraph, Spacer
            from reportlab.lib.units import mm
            g = await db.plan_groups.find_one(
                {"group_id": cm["group_id"], "user_id": user["user_id"]}, {"_id": 0})
            if g:
                aps = _ap_styles()
                ap = [Paragraph("ANEXO — DETALHE DAS COTAS", aps["kicker"]), Spacer(1, 4 * mm)]
                lvl_ids = [lv.get("plan_id") for lv in (g.get("levels") or [])]
                plan_docs = await db.plans_takeoff.find(
                    {"plan_id": {"$in": lvl_ids}, "user_id": user["user_id"]},
                    {"_id": 0, "plan_id": 1, "measurements": 1}).to_list(50)
                dby = {d["plan_id"]: d for d in plan_docs}
                for lv in (g.get("levels") or []):
                    pd = dby.get(lv.get("plan_id"))
                    if not pd:
                        continue
                    ap.append(Paragraph(f"DETALHE DAS COTAS — {lv.get('level_label') or 'Piso'}", aps["kicker"]))
                    thumb = await _ensure_level_thumb(lv.get("plan_id"), user["user_id"])
                    sub = _detail_cotes_flowables(pd.get("measurements") or [], aps, thumb_b64=thumb)
                    if sub:
                        ap += sub
                    ap.append(Spacer(1, 4 * mm))
                if len(ap) > 2:
                    appendix = ap
        except Exception:
            appendix = None
    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=reviews,
                                   lang=await _doc_lang(doc, branding), sign_url=sign_url,
                                   cover=cover, watermark_logo_b64=watermark_logo,
                                   appendix=appendix)
    fname = _pdf_filename(doc)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{doc_id}/sign-link")
async def document_sign_link(doc_id: str, user=Depends(current_user)) -> dict:
    """Lien de signature du devis, pour faire signer le client sur place (tablette/téléphone)."""
    doc = await _get_owned(doc_id, user)
    if doc.get("doc_type") != "quote":
        raise HTTPException(400, "Apenas os orçamentos podem ser assinados")
    if doc.get("signed"):
        return {"already_signed": True, "sign_url": None}
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc.get("issue_date") or _now()}})
    from routes.project_quotes import _sign_token
    token = await _sign_token(doc, create=True)
    base = os.getenv("FRONTEND_URL", "").rstrip("/")
    return {"already_signed": False, "token": token,
            "sign_url": f"{base}/sign/{token}" if base else f"/sign/{token}",
            "path": f"/sign/{token}"}


@router.get("/{doc_id}/pdf-internal")
async def document_pdf_internal(doc_id: str, user=Depends(current_user)):
    """Version interne (coûts de revient + marges par lot) — réservée au pro, jamais envoyée au client."""
    from engines.pdf_internal import build_internal_quote_pdf
    from routes.plans_common import _resolve_branding
    doc = await _get_owned(doc_id, user)
    branding = await _resolve_branding(user["user_id"])
    pdf_bytes = build_internal_quote_pdf(doc, branding=branding)
    fname = f"{doc.get('number') or doc['doc_id']}-INTERNO.pdf"
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
    subject = (f'Orçamento n.º {number} · {company}' if is_quote
               else f'Fatura n.º {number} · {company}')
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
    subject = (f'Orçamento n.º {number} · {company}' if is_quote
               else f'Fatura n.º {number} · {company}')
    if is_quote:
        inner += ("<p style=\"margin:22px 0\"><a href=\"#\" style=\"background:#3F7D54;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block\">✍️ Consultar e assinar o orçamento online</a></p>")
    inner += _render_button_html((body.render_url or "").strip())
    if doc.get("doc_type") in ("invoice", "credit_note") and user.get("bank_details"):
        _bank = str(user["bank_details"]).replace(chr(10), "<br/>")
        inner += (f'<div style="margin:18px 0;padding:14px 16px;background:#f6f8fa;border-radius:8px"><p style="margin:0 0 6px 0;font-weight:bold">Dados bancários</p><p style="margin:0;color:#333;font-size:13px">{_bank}</p></div>')
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


@router.get("/send-status/{log_id}")
async def send_status(log_id: str, user=Depends(current_user)) -> dict:
    """État réel de l'envoi (traité en arrière-plan) : queued / sent / failed + cause lisible."""
    log = await db.quote_sends.find_one({"log_id": log_id, "user_id": user["user_id"]},
                                        {"_id": 0, "email_status": 1, "error": 1, "email_via": 1, "client_email": 1, "email_id": 1})
    if not log:
        raise HTTPException(404, "Envio não encontrado")
    err = log.get("error") or ""
    if log.get("email_status") == "sent" and log.get("email_id"):
        from engines.emailer import email_last_event
        ev = await email_last_event(log["email_id"])
        if ev in ("bounced", "complained", "suppressed", "failed", "delivery_delayed"):
            causes = {"bounced": "endereço rejeitado pelo servidor do destinatário (devolução)",
                      "suppressed": "endereço na lista de supressão Resend (devolução anterior) — retirado automaticamente, reenvie o orçamento",
                      "complained": "o destinatário assinalou spam", "failed": "falha na entrega", "delivery_delayed": "entrega atrasada"}
            err = f"Resend : {causes.get(ev, ev)}"
            log["email_status"] = "failed" if ev != "delivery_delayed" else "queued"
            await db.quote_sends.update_one({"log_id": log_id}, {"$set": {"email_status": log["email_status"], "error": err, "last_event": ev}})
            if ev in ("suppressed", "bounced"):
                from engines.emailer import unsuppress
                await unsuppress(log.get("client_email") or "")
    if "only send testing emails" in err or "own email address" in err or "resend.dev" in err:
        err = ("Remetente não configurado no servidor (SENDER_EMAIL ausente ou domínio não verificado na Resend): a Resend só autoriza então o envio para o seu próprio endereço. Preencha SENDER_EMAIL com um endereço de um domínio verificado (ex. info@construpilot.pt).")
    elif "SENDER_EMAIL" in err:
        err = "SENDER_EMAIL ausente no servidor: configure um endereço de um domínio verificado na Resend (ex. info@construpilot.pt)."
    elif "RESEND_API_KEY" in err:
        err = "Chave RESEND_API_KEY ausente no servidor: nenhum e-mail pode ser enviado."
    return {"email_status": log.get("email_status"), "error": err or None, "via": log.get("email_via"), "to": log.get("client_email")}


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
    _emails = [e.strip() for e in _re.split(r"[,;\s]+", body.client_email or "") if e.strip()]
    _recipients = [e for e in _emails if _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e)]
    if not _recipients:
        raise HTTPException(400, "Email do cliente inválido.")
    _recipients = list(dict.fromkeys(_recipients))[:10]  # dédup, max 10 destinataires
    body.client_email = _recipients[0]
    # E-mail du pro requis vérifié avant tout envoi (grand-fathering : comptes sans le champ = OK)
    if user.get("email_verified") is False:
        raise HTTPException(
            403, "Confirme primeiro o seu endereço de e-mail (ligação recebida no registo) antes de enviar um orçamento.")
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
                                   lang=await _doc_lang(doc, branding))
    company = branding.get("company_name") or user.get("name") or "ConstruPilot"
    company_email = branding.get("company_email")
    ttc = (doc.get("totals") or {}).get("ttc") or doc.get("total_ttc") or 0
    is_quote = doc["doc_type"] == "quote"
    number = doc.get("number") or ""
    body_text = (body.message or "").strip() or _resolved_email_message(
        doc, company, body.client_name or ((doc.get("client") or {}).get("first_name") or ""), branding)
    inner = _text_to_html(body_text)
    subject = (f'Orçamento n.º {number} · {company}' if is_quote
               else f'Fatura n.º {number} · {company}')
    sender_u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "email": 1})
    cc = (sender_u or {}).get("email")
    log_id = "qs_" + _secrets.token_hex(6)
    sign_token = _secrets.token_urlsafe(24)
    sign_url = f"{os.getenv('FRONTEND_URL', '')}/sign/{sign_token}"
    if is_quote:
        inner += (f'<p style="margin:22px 0"><a href="{sign_url}" style="background:#3F7D54;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">✍️ Consultar e assinar o orçamento online</a></p><p style="font-size:12px;color:#666">Ou copie esta ligação: {sign_url}</p>')
    inner += _render_button_html((body.render_url or "").strip())
    if doc.get("doc_type") in ("invoice", "credit_note") and user.get("bank_details"):
        _bank = str(user["bank_details"]).replace(chr(10), "<br/>")
        inner += (f'<div style="margin:18px 0;padding:14px 16px;background:#f6f8fa;border-radius:8px"><p style="margin:0 0 6px 0;font-weight:bold">Dados bancários</p><p style="margin:0;color:#333;font-size:13px">{_bank}</p></div>')
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
                or "Obras de remodelação"
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
                raise HTTPException(400, "Anexos demasiado volumosos (máximo 15 MB no total).")
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
            res = {}
            for _i, _rcpt in enumerate(_recipients):
                res = await asyncio.wait_for(
                    deliver_email(user["user_id"], _rcpt, subject, html,
                                  pdf_bytes=pdf_bytes, filename=filename,
                                  cc=(cc if _i == 0 else None),
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
        raise HTTPException(status_code=400, detail="Fatura eletrónica (Factur-X) reservada às faturas")
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

    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=None,
                                   lang=await _doc_lang(doc, branding), facturx=True)
    try:
        fx, report = await convert_facturx(pdf_bytes, build_invoice_data(doc, branding))
        source = "convert"
    except FacturxConvertError as exc:
        logging.getLogger("documents").warning("Factur-X convert fallback: %s", exc)
        fx = to_facturx(pdf_bytes, doc, branding)
        report = {"valid": False, "profile": "BASIC", "error_count": None,
                  "warning_count": 0, "issues": getattr(exc, "issues", []),
                  "hint": getattr(exc, "hint", None),
                  "source": "local", "fallback_reason": str(exc)}
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
        raise HTTPException(400, "Apenas um orçamento pode ser transformado em fatura")
    if q.get("status") != "signed":
        raise HTTPException(400, "O orçamento deve ser assinado antes de ser faturado")
    scaled = body.mode in ("prorata", "acompte")
    factor = (max(0.0, min(body.pct, 100)) / 100) if scaled else 1.0
    note = q.get("notes") or ""
    if scaled and factor < 1:
        lines = [{**dict(ln), "qty": round((ln.get("qty") or 0) * factor, 4)}
                 for ln in q.get("lines", [])]
        if body.mode == "acompte":
            title = f"Fatura de adiantamento {int(round(body.pct))}% — {q.get('title') or 'devis'}"
            note = (f"Fatura de adiantamento de {int(round(body.pct))} % sobre o orçamento {q.get('number') or ''}. O saldo será faturado na conclusão das obras.").strip()
        else:
            title = f"Fatura de auto de medição {int(round(body.pct))}% — {q.get('title') or 'devis'}"
    else:
        lines = [dict(ln) for ln in q.get("lines", [])]
        title = f"Fatura — {q.get('title') or 'devis'}"
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
        "chantier_id": q.get("chantier_id"),
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
        raise HTTPException(400, "Apenas uma fatura pode dar origem a uma nota de crédito")
    lines = [dict(ln) for ln in inv.get("lines", [])]
    totals = _compute_totals(lines, 0)
    now = _now()
    number = await _next_number(user["user_id"], "credit_note")
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "credit_note",
        "number": number,
        "title": f"Nota de crédito — fatura {inv.get('number') or ''}".strip(),
        "client_id": inv.get("client_id"),
        "client": inv.get("client"),
        "status": "issued",
        "lines": lines,
        "notes": f"Nota de crédito emitida com referência à fatura {inv.get('number') or inv['doc_id']}.",
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
        raise HTTPException(400, "Os pagamentos só dizem respeito às faturas")
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
            lang = await _doc_lang(inv, branding)
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
