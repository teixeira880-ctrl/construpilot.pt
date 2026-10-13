"""Authorize document operations before body processing or billable side effects."""
from fastapi import Depends, HTTPException, Request
from core.db import db
from core.security import pro_required
from core.permissions import permissions_for, require_feature


def document_feature(doc_type: str) -> str:
    return "devis" if doc_type == "quote" else "factures"


async def document_access(request: Request, user=Depends(pro_required)):
    perms = permissions_for(user)
    if not (perms["devis"] or perms["factures"]):
        raise HTTPException(403, "Votre rôle ne permet pas cet accès.")
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    # Imports and batches can contain mixed accounting documents.
    invoice_ops = ("deposit-invoice", "situation-invoice", "balance-invoice", "billing-recap",
                   "to-invoice", "to-credit-note", "payments", "factur-x", "client-summary",
                   "import-pdf", "issue-batch", "send-status")
    if any(op in path for op in invoice_ops):
        require_feature(user, "factures")
    doc_id = request.path_params.get("doc_id")
    if doc_id:
        doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0, "doc_type": 1})
        if doc:
            require_feature(user, document_feature(doc.get("doc_type")))
    if request.method == "GET" and request.query_params.get("doc_type"):
        require_feature(user, document_feature(request.query_params["doc_type"]))
    if request.method == "POST" and path.rstrip("/").endswith("/documents"):
        body = await request.json()
        if isinstance(body, dict):
            dtype = body.get("doc_type", "quote")
            require_feature(user, document_feature(dtype))
    if any(op in path for op in ("from-plan", "from-text", "from-video", "ai/describe", "cctp/extract")):
        require_feature(user, "devis")
    return user