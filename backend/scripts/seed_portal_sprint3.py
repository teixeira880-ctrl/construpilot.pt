"""Seed de test Sprint 3 : chantier + client + devis/facture + participant client actif.

Crée un jeu de données isolé (préfixe portaltest) pour valider les endpoints du portail.
Idempotent : supprime puis recrée. Affiche le token d'invitation et le ref.
"""
import asyncio
import secrets
from datetime import datetime, timezone

from core.db import db
from core.security import JWT_SECRET
import hmac
import hashlib


def _hash(v: str) -> str:
    return hmac.new(JWT_SECRET.encode(), v.encode(), hashlib.sha256).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    pro = await db.users.find_one({"email": "pro@construpilot.fr"}, {"_id": 0, "user_id": 1})
    uid = pro["user_id"]
    ref = "CP-PTST-0001"
    cid = "cht_portaltest01"
    client_id = "cl_portaltest01"
    # cleanup
    await db.chantiers.delete_many({"chantier_id": cid})
    await db.clients.delete_many({"client_id": client_id})
    await db.pro_documents.delete_many({"chantier_id": cid})
    await db.chantier_participants.delete_many({"chantier_id": cid})

    await db.clients.insert_one({"client_id": client_id, "user_id": uid, "company": "Famille Test",
                                 "first_name": "Sophie", "last_name": "Test", "email": "delivered@resend.dev",
                                 "address": "5 rue du Test", "postal_code": "75010", "city": "Paris", "created_at": now()})
    await db.chantiers.insert_one({"chantier_id": cid, "user_id": uid, "name": "Rénovation Test Portail",
                                   "ref": ref, "city": "Paris", "status": "en_cours", "client_id": client_id,
                                   "address": "5 rue du Test", "postal_code": "75010", "created_at": now(), "updated_at": now()})

    quote = {"doc_id": "doc_portaltest_q1", "user_id": uid, "doc_type": "quote", "number": "DEV-TEST-0001",
             "title": "Devis rénovation salle de bain", "chantier_id": cid, "client_id": client_id,
             "client": {"company": "Famille Test", "first_name": "Sophie", "last_name": "Test", "address": "5 rue du Test", "postal_code": "75010", "city": "Paris", "email": "delivered@resend.dev"},
             "status": "sent", "issue_date": now(), "lines": [
                 {"designation": "Dépose faïence", "qty": 20, "unit": "m2", "unit_price_ht": 25, "vat_rate": 10, "category": "Démolition"},
                 {"designation": "Pose carrelage", "qty": 20, "unit": "m2", "unit_price_ht": 60, "vat_rate": 10, "category": "Revêtement"}],
             "totals": {"ht": 1700, "tva_breakdown": {"10": 170}, "ttc": 1870}, "created_at": now(), "updated_at": now()}
    invoice = {"doc_id": "doc_portaltest_i1", "user_id": uid, "doc_type": "invoice", "number": "FAC-TEST-0001",
               "title": "Facture acompte", "chantier_id": cid, "client_id": client_id,
               "client": quote["client"], "status": "sent", "issue_date": now(),
               "lines": [{"designation": "Acompte 30%", "qty": 1, "unit": "forf", "unit_price_ht": 510, "vat_rate": 10, "category": ""}],
               "totals": {"ht": 510, "tva_breakdown": {"10": 51}, "ttc": 561}, "created_at": now(), "updated_at": now()}
    # un brouillon qui NE doit PAS apparaître dans le portail
    draft = {"doc_id": "doc_portaltest_draft", "user_id": uid, "doc_type": "quote", "number": None,
             "title": "Brouillon caché", "chantier_id": cid, "client_id": client_id, "status": "draft",
             "lines": [], "totals": {"ht": 0, "ttc": 0}, "created_at": now()}
    await db.pro_documents.insert_many([quote, invoice, draft])

    token = secrets.token_urlsafe(24)
    await db.chantier_participants.insert_one({
        "participant_id": "part_portaltest01", "chantier_id": cid, "chantier_ref": ref, "owner_user_id": uid,
        "role": "client", "email": "delivered@resend.dev", "name": "Sophie Test", "lot": "",
        "permissions": {"progress": True, "photos": True, "quotes": True, "invoices": True, "sign": True, "chat": True, "report_issue": True, "post_reports": False},
        "status": "invited", "invite_token_hash": _hash(token),
        "invite_expires_at": now().replace(now()[:4], str(int(now()[:4]) + 1)),  # +1 an ~ valide
        "accepted_at": None, "session_version": 0, "created_at": now(), "updated_at": now()})

    print("REF=" + ref)
    print("TOKEN=" + token)


if __name__ == "__main__":
    asyncio.run(main())
