"""Persist quote drafts in the real document collection. No outbound or billing operations."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from core.db import db
from core.permissions import require_feature
from engines.assistant_quote_pricing import build_lines
from engines.assistant_quote_schema import QuoteAppendInput, QuoteInput


def _coerce_quote_numbers(args):
    """Les modèles renvoient parfois les nombres en chaînes ('9.13'). On coerce
    quantity/unit_price/vat_rate pour éviter un échec de validation stricte opaque."""
    def num(v):
        if isinstance(v, str):
            s = v.strip().replace(",", ".")
            try:
                return float(s)
            except ValueError:
                return v
        return v
    if not isinstance(args, dict):
        return
    if "vat_rate" in args:
        args["vat_rate"] = num(args["vat_rate"])
    for line in args.get("lines") or []:
        if isinstance(line, dict):
            for k in ("quantity", "unit_price", "vat_rate"):
                if k in line:
                    line[k] = num(line[k])


def _validation_hint(exc: ValidationError) -> str:
    """Message clair et actionnable pour le modèle (pas de secret ni de texte de document)."""
    err = exc.errors()[0] if exc.errors() else {}
    loc = " → ".join(str(p) for p in err.get("loc", []))
    msg = err.get("msg", "argument invalide")
    return (f"Arguments du devis invalides ({loc}) : {msg}. "
            "Rappels : price_origin='user' (prix client fourni) ou 'estimate' (prix moyen marché/web) "
            "exigent un unit_price numérique ; 'library'/'unpriced' exigent unit_price=null. "
            "quantity, unit_price et vat_rate sont des nombres (jamais des chaînes). Corrige et rappelle l'outil.")


class QuoteResult(BaseModel):
    ok: bool = True
    saved: bool = True
    draft: dict
    doc_id: str
    edit_url: str
    tracking_url: str = "/devis"
    tool_input: dict
    note: str = "Brouillon enregistré dans Suivi devis ; aucun envoi au client. Prix et TVA à vérifier."


def present(doc):
    rows = doc.get("lines") or []
    tool_lines = [{"line_id": r.get("line_id") or f"legacy:{i}", "description": r.get("description", ""), "designation": r["designation"], "quantity": None if r.get("quantity_missing") else r["qty"],
                   "unit": r["unit"], "unit_price": r["unit_price_ht"] if r.get("price_source") in ("user_input", "assistant_estimate") else None,
                   "price_origin": "estimate" if r.get("price_source") == "assistant_estimate" else "library" if r.get("price_estimated") else "unpriced" if r.get("price_missing") else "user",
                   "lot": r.get("category", ""), "vat_rate": None if r.get("vat_assumed") else r["vat_rate"]} for i, r in enumerate(rows)]
    totals = doc.get("totals") or {}
    client = doc.get("client") or {}
    client_name = doc.get("client_name") or client.get("company") or " ".join(filter(None, [client.get("first_name"), client.get("last_name")]))
    draft = {"draft_id": doc["doc_id"], "doc_id": doc["doc_id"], "title": doc.get("title", ""),
             "status": doc.get("status"), "client_name": client_name, "lines": rows,
             "total_ht": totals.get("ht", 0), "total_tva": totals.get("tva", 0), "total_ttc": totals.get("ttc", 0),
             "estimated_lines": sum(bool(r.get("price_estimated")) for r in rows),
             "incomplete_lines": sum(bool(r.get("price_missing") or r.get("quantity_missing")) for r in rows),
             "vat_assumed": any(r.get("vat_assumed") for r in rows), "updated_at": doc.get("updated_at"),
             "conversation_id": doc.get("assistant_conversation_id")}
    data = QuoteResult(draft=draft, doc_id=doc["doc_id"], edit_url=f"/devis-editeur/{doc['doc_id']}",
                       tool_input={"title": doc.get("title", ""), "client_name": client_name, "vat_rate": None,
                                   "lines": tool_lines, "notes": doc.get("notes", "")})
    return data.model_dump(mode="json")


async def read_quote(doc_id, user):
    require_feature(user, "devis")
    doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"], "doc_type": "quote"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Devis introuvable pour ce compte.")
    return present(doc)


async def find_quotes(user, query: str = ""):
    """Liste les devis BROUILLON du compte (assistant OU éditeur) pour en reprendre un."""
    require_feature(user, "devis")
    q = {"user_id": user["user_id"], "doc_type": "quote", "status": "draft", "signed": {"$ne": True}}
    ql = (query or "").strip().lower()
    out = []
    cur = db.pro_documents.find(
        q, {"_id": 0, "doc_id": 1, "title": 1, "client": 1, "client_name": 1, "updated_at": 1, "totals": 1, "lines": 1}
    ).sort("updated_at", -1).limit(40)
    async for doc in cur:
        client = doc.get("client") or {}
        client_name = (doc.get("client_name") or client.get("company")
                       or " ".join(filter(None, [client.get("first_name"), client.get("last_name")])) or "")
        if ql and ql not in (doc.get("title", "") or "").lower() and ql not in client_name.lower():
            continue
        totals = doc.get("totals") or {}
        out.append({"doc_id": doc["doc_id"], "title": doc.get("title", ""), "client_name": client_name,
                    "updated_at": doc.get("updated_at"), "total_ht": totals.get("ht", 0),
                    "total_ttc": totals.get("ttc", 0), "lines": len(doc.get("lines") or [])})
        if len(out) >= 10:
            break
    return {"ok": True, "count": len(out), "quotes": out,
            "note": "Reprends-en un avec read_quote_draft (doc_id) puis update_quote_draft. N'en crée pas un nouveau."}


async def save_quote(args, user, conv, *, doc_id=None, expected_updated_at=None):
    from routes.documents import _compute_totals

    require_feature(user, "devis")
    if conv.get("user_id") != user["user_id"]:
        raise HTTPException(403, "Conversation inaccessible.")
    _coerce_quote_numbers(args)
    try:
        body = QuoteInput.model_validate(args)
    except ValidationError as exc:
        raise HTTPException(422, _validation_hint(exc))
    timestamp = datetime.now(timezone.utc).isoformat()
    # Stable across a retried HTTP request even if the model rephrases a title/description.
    # Distinct successful create actions within the same turn receive distinct slots.
    key = json.dumps([user["user_id"], conv["conversation_id"], conv.get("_quote_request_id") or uuid4().hex,
                      conv.get("_quote_create_slot", 0)], sort_keys=True, allow_nan=False)
    ident = doc_id or "doc_" + hashlib.sha256(key.encode()).hexdigest()[:24]
    query = {"doc_id": ident, "user_id": user["user_id"], "doc_type": "quote"}
    previous = await db.pro_documents.find_one(query, {"_id": 0})
    if previous and not doc_id:
        return present(previous)
    if doc_id and not previous:
        raise HTTPException(404, "Devis introuvable pour ce compte.")
    if doc_id and (previous.get("status") != "draft" or previous.get("signed")):
        raise HTTPException(409, "Seul un devis en brouillon peut être révisé par l'assistant.")
    if doc_id and previous.get("updated_at") != expected_updated_at:
        raise HTTPException(409, "Le devis a changé. Relisez sa version actuelle avant de le modifier.")
    chantier = conv.get("_chantier") or {}
    same_chantier = bool(previous and previous.get("chantier_id") and previous.get("chantier_id") == chantier.get("chantier_id"))
    if previous and previous.get("client_id") and not same_chantier and body.client_name != present(previous)["draft"]["client_name"]:
        raise HTTPException(409, "Ce devis est lié à un client CRM. Modifiez ce client dans l'éditeur.")
    lines = await build_lines(body, user, previous)
    totals = _compute_totals(lines, (previous or {}).get("deposit_pct", 0))
    if totals["ttc"] > 1_000_000_000_000:
        raise HTTPException(422, "Montant total trop élevé.")
    fields = {"title": body.title, "lines": lines, "totals": totals, "updated_at": timestamp,
              "client_name": body.client_name, "assistant_review_required": True,
              "facturx_pdf_b64": None, "facturx_validation": None, "facturx_hash": None}
    # Le champ "notes" n'est JAMAIS écrit par l'assistant : il reste vide (création) ou inchangé
    # (révision), à la disposition de l'entreprise pour une saisie manuelle dans l'éditeur.
    # A supplied name is a document snapshot only: no CRM mutation or guessed email.
    if same_chantier:
        fields.pop("client_name", None)
    if not (previous or {}).get("client_id"):
        fields["client"] = {"last_name": body.client_name} if body.client_name else None
        if not previous and chantier.get("client_id"):
            from routes.documents import _client_snapshot
            fields["client"] = await _client_snapshot(chantier["client_id"], user)
    if doc_id:
        result = await db.pro_documents.update_one({**query, "updated_at": expected_updated_at, "status": "draft", "signed": {"$ne": True}}, {"$set": fields})
        if not result.matched_count:
            raise HTTPException(409, "Le devis a changé. Relisez sa version actuelle.")
    else:
        # Mongo _id is an atomic idempotency key; $setOnInsert never overwrites an edited draft.
        await db.pro_documents.update_one({"_id": f"assistant_quote:{ident}"}, {"$setOnInsert": {
            **query, **fields, "number": None, "status": "draft", "signed": False,
            "client_id": chantier.get("client_id"), "chantier_id": chantier.get("chantier_id"), "payment_terms": "", "deposit_pct": 0, "issue_date": None, "due_date": None,
            "source": "assistant", "lang": conv.get("_quote_lang", "fr"), "assistant_conversation_id": conv["conversation_id"],
            "project_id": conv.get("project_id"), "created_at": timestamp}}, upsert=True)
    # Read back after persistence, never claim successful saving before this succeeds.
    out = await read_quote(ident, user)
    # Apprentissage auto : enrichit la bibliothèque entreprise + le pool global (prix estimés marqués).
    try:
        from routes.library import auto_save_from_lines
        await auto_save_from_lines(user["user_id"], lines, source="assistant_devis")
    except Exception:  # noqa: BLE001 — l'apprentissage ne doit jamais bloquer la création du devis
        pass
    return out


class _LineBatch:
    """Enveloppe minimale pour réutiliser build_lines avec un simple lot de lignes."""
    def __init__(self, lines, vat_rate):
        self.lines = lines
        self.vat_rate = vat_rate


async def append_quote_lines(args, user, conv, *, doc_id):
    """Ajoute des lignes à un devis brouillon existant sans resoumettre les lignes déjà présentes.
    Permet de construire un gros devis par étage/lot en plusieurs petits appels (jamais tronqués)."""
    from routes.documents import _compute_totals

    require_feature(user, "devis")
    if conv.get("user_id") != user["user_id"]:
        raise HTTPException(403, "Conversation inaccessible.")
    _coerce_quote_numbers(args)
    try:
        body = QuoteAppendInput.model_validate(args)
    except ValidationError as exc:
        raise HTTPException(422, _validation_hint(exc))
    query = {"doc_id": doc_id, "user_id": user["user_id"], "doc_type": "quote"}
    previous = await db.pro_documents.find_one(query, {"_id": 0})
    if not previous:
        raise HTTPException(404, "Devis introuvable pour ce compte.")
    if previous.get("status") != "draft" or previous.get("signed"):
        raise HTTPException(409, "Seul un devis en brouillon peut être complété par l'assistant.")
    append_key = None
    if conv.get("_quote_request_id"):
        append_key = hashlib.sha256(json.dumps(
            [user["user_id"], conv["conversation_id"], conv["_quote_request_id"], body.model_dump(mode="json")],
            sort_keys=True, allow_nan=False).encode()).hexdigest()
        if append_key in (previous.get("assistant_append_keys") or []):
            return present(previous)
    # Lignes ajoutées = toujours nouvelles ; on force line_id=null pour éviter toute collision.
    for line in body.lines:
        line.line_id = None
    new_lines = await build_lines(_LineBatch(body.lines, body.vat_rate), user, previous=None)
    merged = (previous.get("lines") or []) + new_lines
    if len(merged) > 400:
        raise HTTPException(422, "Trop de lignes au total pour ce devis ; finalisez-le dans l'éditeur.")
    totals = _compute_totals(merged, previous.get("deposit_pct", 0))
    if totals["ttc"] > 1_000_000_000_000:
        raise HTTPException(422, "Montant total trop élevé.")
    timestamp = datetime.now(timezone.utc).isoformat()
    update = {"$set": {"lines": merged, "totals": totals, "updated_at": timestamp, "assistant_review_required": True,
                       "facturx_pdf_b64": None, "facturx_validation": None, "facturx_hash": None}}
    if append_key:
        update["$push"] = {"assistant_append_keys": {"$each": [append_key], "$slice": -100}}
    result = await db.pro_documents.update_one(
        {**query, "status": "draft", "signed": {"$ne": True},
         "updated_at": previous.get("updated_at"), "lines": previous.get("lines") or []},
        update)
    if not result.matched_count:
        raise HTTPException(409, "Le devis a changé. Relisez sa version actuelle avant de le compléter.")
    out = await read_quote(doc_id, user)
    try:
        from routes.library import auto_save_from_lines
        await auto_save_from_lines(user["user_id"], new_lines, source="assistant_devis")
    except Exception:  # noqa: BLE001
        pass
    return out
