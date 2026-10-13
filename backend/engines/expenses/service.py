"""Admin queries and evidence edits, independent from invoicing/credits/quotas."""
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from core.db import db
from engines.expenses.accounting import (
    breakdown,
    budget_status,
    period,
    render_event,
    totals,
)
from engines.expenses.catalog import inventory
from engines.expenses.models import EventOut, ExpenseInput
from engines.expenses.store import audit, identifier, micros, now

MAX_ROWS = 50000


async def rows_for(month, include_test=False):
    start, end = period(month)
    query = {"occurred_at": {"$gte": start, "$lt": end}, "voided": {"$ne": True}}
    if not include_test:
        query["is_test"] = {"$ne": True}
    raw = await db.api_expense_events.find(query, {"_id": 0}).sort("occurred_at", -1).to_list(MAX_ROWS + 1)
    if len(raw) > MAX_ROWS:
        raise HTTPException(413, "Período demasiado volumoso para um relatório completo. Nenhum total parcial é apresentado.")
    rates = await db.api_expense_rates.find({"disabled": {"$ne": True}}, {"_id": 0}).to_list(2000)
    statements = [r for r in raw if r.get("scope") == "monthly_total"]
    return [EventOut(**render_event(r, rates, statements)).model_dump() for r in raw]


def filtered(rows, provider=None, feature=None, user_id=None, company_id=None, evidence=None):
    for field, value in (("provider", provider), ("feature", feature), ("user_id", user_id), ("company_id", company_id), ("evidence", evidence)):
        if value:
            rows = [r for r in rows if (r.get(field) or "unattributed") == value]
    return rows


async def labels(rows):
    user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
    company_ids = list({r["company_id"] for r in rows if r.get("company_id")})
    users = {u["user_id"]: u.get("name") or u.get("email") or u["user_id"] for u in await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(MAX_ROWS)}
    companies = {c["org_id"]: c.get("name") or c["org_id"] for c in await db.organizations.find({"org_id": {"$in": company_ids}}, {"_id": 0, "org_id": 1, "name": 1}).to_list(MAX_ROWS)}
    for row in rows:
        row.update(user_name=users.get(row.get("user_id")), company_name=companies.get(row.get("company_id")))
    return rows


async def overview(month, include_test=False, **filters):
    all_rows = await rows_for(month, include_test)
    rows = filtered(all_rows, **filters)
    budgets = await db.api_expense_budgets.find({"month": month}, {"_id": 0}).to_list(200)
    balances = {b["provider"]: b for b in await db.api_expense_balances.find({}, {"_id": 0}).to_list(100)}
    sync = await db.api_expense_sync.find_one({"_id": "local"}, {"_id": 0}) or {}
    providers = []
    for provider in inventory():
        provider_rows = [r for r in rows if r["provider"] == provider["provider"]]
        providers.append({**provider, **totals(provider_rows), "balance": balances.get(provider["provider"]),
                          "models": sorted({r["model"] for r in provider_rows if r.get("model")})})
    return {"month": month, "currency": "EUR", "summary": totals(rows), "providers": providers,
            "breakdowns": {key: breakdown(rows, key) for key in ("provider", "feature", "user_id", "company_id")},
            "daily": [{"day": day, **totals([r for r in rows if r["occurred_at"].date().isoformat() == day])}
                      for day in sorted({r["occurred_at"].date().isoformat() for r in rows})],
            "budgets": [budget_status(b, all_rows) for b in budgets],
            "sync": sync, "generated_at": now(), "include_test": include_test}


async def validate_attribution(body):
    if body.user_id and not await db.users.find_one({"user_id": body.user_id}, {"_id": 0, "user_id": 1}):
        raise HTTPException(422, "Utilizador não encontrado")
    if body.company_id and not await db.organizations.find_one({"org_id": body.company_id}, {"_id": 0, "org_id": 1}):
        raise HTTPException(422, "Empresa não encontrada")


async def create_manual(body: ExpenseInput, admin_id):
    await validate_attribution(body)
    ref = body.source_ref.strip()
    stamp = datetime.combine(body.occurred_on, datetime.min.time(), tzinfo=timezone.utc)
    if body.scope == "monthly_total":
        # One whole-period total per billing provider/scope; cannot silently stack invoices.
        entry_id = identifier("monthly_total", body.provider, body.occurred_on.strftime("%Y-%m"), body.is_test)
    else:
        entry_id = identifier("manual", body.provider, ref.casefold(), body.is_test)
    document = {"entry_id": entry_id, "provider": body.provider, "occurred_at": stamp, "feature": body.feature,
        "source_ref": ref, "origin": "manual", "scope": body.scope, "state": "recorded", "model": "", "units": {},
        "evidence": "confirmed", "amount_micros": micros(body.amount), "currency": body.currency,
        "settled_eur_micros": micros(body.settled_eur) if body.settled_eur is not None else None,
        "settlement_ref": body.settlement_ref, "user_id": body.user_id, "company_id": body.company_id,
        "is_test": body.is_test, "created_at": now(), "created_by": admin_id, "version": 0}
    try:
        await db.api_expense_events.insert_one({"_id": entry_id, **document})
    except DuplicateKeyError:
        raise HTTPException(409, "Esta referência ou este total mensal já existe. Corrija o registo existente.") from None
    await audit(admin_id, "create_manual", entry_id)
    return EventOut(**render_event(document, [], []))


async def confirm_entry(entry_id, body, admin_id):
    current = await db.api_expense_events.find_one({"_id": entry_id, "voided": {"$ne": True}}, {"_id": 0})
    if not current:
        raise HTTPException(404, "Registo não encontrado")
    checked = ExpenseInput(provider=current["provider"], source_ref=body.source_ref, amount=body.amount, currency=body.currency,
        occurred_on=current["occurred_at"].date(), settled_eur=body.settled_eur, settlement_ref=body.settlement_ref, confirmed_charge=True)
    confirmation = {"source_ref": checked.source_ref.strip(), "amount_micros": micros(checked.amount), "currency": checked.currency,
        "settled_eur_micros": micros(checked.settled_eur) if checked.settled_eur is not None else None,
        "settlement_ref": checked.settlement_ref, "confirmed_at": now(), "confirmed_by": admin_id}
    result = await db.api_expense_events.update_one({"_id": entry_id, "version": body.version, "voided": {"$ne": True}},
        {"$set": {"confirmation": confirmation}, "$inc": {"version": 1}})
    if not result.modified_count:
        raise HTTPException(409, "Registo alterado entretanto. Atualize antes de confirmar.")
    await audit(admin_id, "confirm", entry_id, current.get("confirmation"))
    return {"ok": True, "entry_id": entry_id}


async def void_entry(entry_id, version, admin_id):
    # Soft void and version check preserve financial history and auditability.
    result = await db.api_expense_events.update_one({"_id": entry_id, "version": version, "voided": {"$ne": True}},
        {"$set": {"voided": True, "voided_by": admin_id, "voided_at": now()}, "$inc": {"version": 1}})
    if not result.modified_count:
        raise HTTPException(409, "Registo ausente ou alterado entretanto.")
    await audit(admin_id, "void", entry_id)
    return {"ok": True}