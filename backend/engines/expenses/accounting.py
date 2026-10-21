from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from engines.expenses.store import micros, money


def month_of(value):
    return value.strftime("%Y-%m") if isinstance(value, datetime) else str(value)[:7]


def estimate(event, rates):
    if event.get("state") not in {"done", "success", "completed", "submitted", "observed", "recorded"}:
        return None
    candidates = [r for r in rates if r["provider"] == event["provider"]
                  and (not r.get("model") or r["model"] == event.get("model", ""))
                  and r["effective_from"] <= event["occurred_at"].date().isoformat()]
    candidates.sort(key=lambda r: (bool(r.get("model")), r["effective_from"]), reverse=True)
    units = event.get("units", {})
    for rate in candidates:
        if rate["mode"] == "tokens":
            if "input_tokens" not in units or "output_tokens" not in units:
                continue
            total = (Decimal(str(units["input_tokens"])) * Decimal(rate["input_price"])
                     + Decimal(str(units["output_tokens"])) * Decimal(rate["output_price"])) / Decimal(1000000)
        else:
            if rate["unit"] not in units:
                continue
            total = Decimal(str(units[rate["unit"]])) * Decimal(rate["price"]) / Decimal(rate["per_units"])
        return micros(total), rate["currency"], rate["rate_id"]
    return None


def covered_by(event, statements):
    if event.get("scope") == "monthly_total":
        return None
    for statement in statements:
        if (statement["provider"] == event["provider"]
                and month_of(statement["occurred_at"]) == month_of(event["occurred_at"])
                and statement.get("is_test", False) == event.get("is_test", False)
                and (not statement.get("user_id") or statement["user_id"] == event.get("user_id"))
                and (not statement.get("company_id") or statement["company_id"] == event.get("company_id"))):
            return statement["entry_id"]
    return None


def render_event(event, rates, statements):
    row = {key: event.get(key) for key in ("entry_id", "provider", "feature", "user_id", "company_id", "occurred_at", "state", "source_ref", "origin")}
    row.update(model=event.get("model", ""), units=event.get("units", {}), version=event.get("version", 0),
               is_test=event.get("is_test", False), scope=event.get("scope", "single"))
    confirmation = event.get("confirmation")
    evidence = "confirmed" if confirmation else event.get("evidence", "unavailable")
    amount = confirmation.get("amount_micros") if confirmation else event.get("amount_micros")
    currency = confirmation.get("currency") if confirmation else event.get("currency")
    eur = confirmation.get("settled_eur_micros") if confirmation else event.get("settled_eur_micros")
    if confirmation:
        row.update(source_ref=confirmation["source_ref"], source_kind="admin_confirmation")
    elif evidence == "confirmed":
        row["source_kind"] = "admin_confirmation" if event["origin"] == "manual" else "provider_report"
    reconciled = covered_by(event, statements)
    if reconciled:
        evidence, amount, eur = "reconciled", None, None
        row["reconciled_by"] = reconciled
    elif evidence == "unavailable":
        estimated = estimate(event, rates)
        if estimated:
            amount, currency, row["rate_ref"] = estimated
            evidence = "estimated"
    if currency == "EUR":
        eur = amount
    row.update(evidence=evidence, amount=money(amount), currency=currency, amount_eur=money(eur))
    return row


def totals(rows):
    result = {"confirmed_eur": None, "estimated_eur": None, "unavailable": 0, "reconciled": 0,
              "operations": 0, "unconverted": 0, "confirmed_native": {}, "estimated_native": {}}
    for row in rows:
        if row.get("scope") != "monthly_total":
            result["operations"] += 1
        evidence = row["evidence"]
        if evidence in {"unavailable", "reconciled"}:
            result[evidence] += 1
        if evidence not in {"confirmed", "estimated"} or row.get("amount") is None:
            continue
        native = result[f"{evidence}_native"]
        currency = row["currency"]
        native[currency] = native.get(currency, 0) + micros(row["amount"])
        if row.get("amount_eur") is not None:
            result[f"{evidence}_eur"] = (result[f"{evidence}_eur"] or 0) + micros(row["amount_eur"])
        else:
            result["unconverted"] += 1
    for kind in ("confirmed", "estimated"):
        result[f"{kind}_eur"] = money(result[f"{kind}_eur"])
        result[f"{kind}_native"] = {k: money(v) for k, v in result[f"{kind}_native"].items()}
    return result


def breakdown(rows, field):
    groups = defaultdict(list)
    for row in rows:
        key = month_of(row["occurred_at"]) if field == "month" else row.get(field) or "unattributed"
        groups[key].append(row)
    return [{"key": key, **totals(items)} for key, items in sorted(groups.items())]


def budget_status(budget, rows):
    relevant = [r for r in rows if month_of(r["occurred_at"]) == budget["month"]
                and (budget["provider"] == "all" or r["provider"] == budget["provider"])]
    summed = totals(relevant)
    amount = Decimal(budget["amount_eur"])
    spent = summed["confirmed_eur"]
    estimated = summed["estimated_eur"]
    pct = max(0, float(Decimal(spent) / amount * 100)) if spent is not None else None
    estimated_pct = max(0, float(Decimal(estimated) / amount * 100)) if estimated is not None else None
    state = "unavailable" if pct is None else "exceeded" if pct >= 100 else "warning" if pct >= budget["warning_percent"] else "below"
    estimated_state = "unavailable" if estimated_pct is None else "exceeded" if estimated_pct >= 100 else "warning" if estimated_pct >= budget["warning_percent"] else "below"
    return {**budget, "spent_eur": spent, "percent": pct, "state": state,
            "estimated_eur": estimated, "estimated_percent": estimated_pct, "estimated_state": estimated_state,
            "incomplete": bool(summed["unavailable"] or summed["unconverted"] or summed["estimated_native"]),
            "automatic_blocking": False}


def period(month):
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Mês inválido") from None
    return start, end