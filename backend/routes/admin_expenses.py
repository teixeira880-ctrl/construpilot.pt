import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from core.db import db
from core.security import admin_user
from engines.expenses import service
from engines.expenses.catalog import PROVIDERS
from engines.expenses.models import (
    BudgetInput,
    ConfirmationInput,
    EventOut,
    ExpenseInput,
    LedgerOut,
    RateInput,
)
from engines.expenses.store import audit, identifier, now

router = APIRouter(prefix="/admin/expenses", tags=["admin-expenses"], dependencies=[Depends(admin_user)])
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
Admin = Annotated[dict, Depends(admin_user)]


class OverviewOut(BaseModel):
    month: str
    currency: str
    summary: dict
    providers: list[dict]
    breakdowns: dict
    daily: list[dict]
    budgets: list[dict]
    sync: dict
    generated_at: datetime
    include_test: bool


def selectors(provider, feature, user_id, company_id, evidence=None):
    if provider and provider not in PROVIDERS:
        raise HTTPException(422, "Fournisseur inconnu")
    return {"provider": provider, "feature": feature, "user_id": user_id, "company_id": company_id, "evidence": evidence}


@router.get("/overview", response_model=OverviewOut)
async def overview(month: str = Query(pattern=MONTH), provider: str | None = None, feature: str | None = None,
                   user_id: str | None = None, company_id: str | None = None, include_test: bool = False):
    return await service.overview(month, include_test, **selectors(provider, feature, user_id, company_id))


@router.get("/ledger", response_model=LedgerOut)
async def ledger(month: str = Query(pattern=MONTH), provider: str | None = None, feature: str | None = None,
                 user_id: str | None = None, company_id: str | None = None, evidence: str | None = None,
                 include_test: bool = False, page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100)):
    rows = service.filtered(await service.rows_for(month, include_test), **selectors(provider, feature, user_id, company_id, evidence))
    selected = await service.labels(rows[(page - 1) * page_size:page * page_size])
    return {"items": selected, "total": len(rows), "page": page, "page_size": page_size}


@router.get("/selectors")
async def selector_options():
    users = await db.users.find({"user_id": {"$type": "string", "$ne": ""}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).sort("name", 1).to_list(5000)
    companies = await db.organizations.find({"org_id": {"$type": "string", "$ne": ""}}, {"_id": 0, "org_id": 1, "name": 1}).sort("name", 1).to_list(5000)
    features = await db.api_expense_events.distinct("feature")
    return {"users": list({u["user_id"]: u for u in users}.values()),
            "companies": list({c["org_id"]: c for c in companies}.values()),
            "features": sorted(f for f in features if isinstance(f, str) and f)}


@router.post("/sync-local")
async def sync_local():
    from engines.expenses.ingest import refresh_local
    return await refresh_local()


@router.get("/trend")
async def trend(month: str = Query(pattern=MONTH), provider: str | None = None, feature: str | None = None,
                user_id: str | None = None, company_id: str | None = None, include_test: bool = False):
    from engines.expenses.accounting import period, totals
    start, _ = period(month)
    items = []
    for _ in range(6):
        key = start.strftime("%Y-%m")
        rows = service.filtered(await service.rows_for(key, include_test), **selectors(provider, feature, user_id, company_id))
        items.append({"month": key, **totals(rows)})
        if start.year == 1 and start.month == 1:
            break
        start = start.replace(year=start.year - 1, month=12) if start.month == 1 else start.replace(month=start.month - 1)
    return {"items": list(reversed(items))}


@router.post("/entries", response_model=EventOut)
async def manual_entry(body: ExpenseInput, admin: Admin):
    return await service.create_manual(body, admin["user_id"])


@router.put("/entries/{entry_id}/confirmation")
async def confirm(entry_id: str, body: ConfirmationInput, admin: Admin):
    return await service.confirm_entry(entry_id, body, admin["user_id"])


@router.delete("/entries/{entry_id}")
async def void(entry_id: str, admin: Admin, version: int = Query(ge=0)):
    return await service.void_entry(entry_id, version, admin["user_id"])


@router.get("/budgets")
async def budgets(month: str = Query(pattern=MONTH)):
    return {"items": await db.api_expense_budgets.find({"month": month}, {"_id": 0}).to_list(200)}


@router.put("/budgets")
async def save_budget(body: BudgetInput, admin: Admin):
    key = identifier(body.provider, body.month)
    value = {**body.model_dump(mode="json"), "budget_id": key, "updated_at": now(), "automatic_blocking": False}
    await db.api_expense_budgets.update_one({"_id": key}, {"$set": value}, upsert=True)
    await audit(admin["user_id"], "budget", key)
    return {"ok": True}


@router.delete("/budgets/{budget_id}")
async def delete_budget(budget_id: str, admin: Admin):
    await db.api_expense_budgets.delete_one({"_id": budget_id})
    await audit(admin["user_id"], "delete_budget", budget_id)
    return {"ok": True}


@router.get("/rates")
async def rates():
    return {"items": await db.api_expense_rates.find({"disabled": {"$ne": True}}, {"_id": 0}).sort("effective_from", -1).to_list(2000)}


@router.put("/rates")
async def save_rate(body: RateInput, admin: Admin):
    key = identifier(body.provider, body.model, body.effective_from)
    value = {**body.model_dump(mode="json"), "rate_id": key, "updated_at": now(), "source_kind": "admin_estimate", "disabled": False}
    previous = await db.api_expense_rates.find_one({"_id": key}, {"_id": 0})
    await db.api_expense_rates.update_one({"_id": key}, {"$set": value}, upsert=True)
    await audit(admin["user_id"], "rate", key, previous)
    return {"ok": True}


@router.delete("/rates/{rate_id}")
async def delete_rate(rate_id: str, admin: Admin):
    await db.api_expense_rates.update_one({"_id": rate_id}, {"$set": {"disabled": True}})
    await audit(admin["user_id"], "disable_rate", rate_id)
    return {"ok": True}


def csv_cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


@router.get("/export.csv")
async def export(month: str = Query(pattern=MONTH), provider: str | None = None, feature: str | None = None,
                 user_id: str | None = None, company_id: str | None = None, evidence: str | None = None, include_test: bool = False):
    rows = service.filtered(await service.rows_for(month, include_test), **selectors(provider, feature, user_id, company_id, evidence))
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["date_utc", "provider", "feature", "user_id", "company_id", "evidence", "amount_native", "currency", "amount_eur", "reference", "test"])
    for row in rows:
        writer.writerow([csv_cell(row[key].isoformat() if key == "occurred_at" else row.get(key)) for key in
                         ["occurred_at", "provider", "feature", "user_id", "company_id", "evidence", "amount", "currency", "amount_eur", "source_ref", "is_test"]])
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="api-expenses-{month}.csv"', "Cache-Control": "private, no-store"})

# --- Plafond global d'exploitation (500 €/mois) : garde-fou et enveloppes par poste ---

class CapEnvelopesIn(BaseModel):
    envelopes: dict[str, float]


class EngagementCheckIn(BaseModel):
    amount_eur: float
    envelope: str
    essential: bool = False


@router.get("/cap")
async def cap_status(month: str | None = Query(default=None, pattern=MONTH)):
    from engines.expenses import cap
    return await cap.status(month)


@router.get("/cap/pilotage")
async def cap_pilotage(month: str | None = Query(default=None, pattern=MONTH)):
    """Pilotage IA : projection de fin de mois, score de santé et recommandations
    déterministes dérivées de l'état du plafond (aucune valeur inventée)."""
    from engines.expenses import pilotage
    return await pilotage.pilotage(month)


@router.put("/cap/envelopes")
async def cap_envelopes(body: CapEnvelopesIn, admin: Admin):
    from engines.expenses import cap
    total = round(sum(body.envelopes.values()), 2)
    if total > cap.DEFAULT_CAP:
        raise HTTPException(400, f"La somme des enveloppes ({total} €) dépasse le plafond de {cap.DEFAULT_CAP} €")
    saved = await cap.save_config(body.envelopes, admin["user_id"])
    await audit(admin["user_id"], "budget_cap_envelopes", "global")
    return saved


@router.post("/cap/check")
async def cap_check(body: EngagementCheckIn):
    """Simulation : un engagement de ce montant serait-il autorisé aujourd'hui ?"""
    from engines.expenses import cap
    verdict = await cap.check_engagement(body.amount_eur, body.envelope, body.essential)
    return {"allowed": verdict["allowed"], "reason": verdict["reason"],
            "projected_used_eur": verdict.get("projected_used_eur"),
            "cap_eur": verdict["status"]["cap_eur"], "used_eur": verdict["status"]["used_eur"]}


@router.post("/cap/holds/{hold_id}/release")
async def cap_release(hold_id: str, admin: Admin, actual_eur: float | None = None):
    from engines.expenses import cap
    if not await cap.release(hold_id, actual_eur):
        raise HTTPException(404, "Réservation introuvable")
    await audit(admin["user_id"], "budget_hold_release", hold_id)
    return {"ok": True}
