"""Plafond global d'exploitation : 500 €/mois, enveloppes par poste, blocage automatique.

Règles fixées par le propriétaire (21/09/2026) :
- plafond total 500 € toutes dépenses incluses ;
- alerte à 400 € consommés ou engagés ;
- suspension des nouveaux engagements non essentiels à 440 €, la réserve de 60 € restant
  disponible pour les dépenses obligatoires ou déjà autorisées ;
- si les coûts réels sont inconnus ou périmés, on l'affiche et on bloque les engagements
  dépendants plutôt que d'afficher un total rassurant mais faux.
"""
from datetime import datetime, timezone

from core.db import db
from engines.expenses.catalog import PROVIDERS
from engines.expenses.service import rows_for
from engines.expenses.accounting import totals

CAP_ID = "global"
DEFAULT_CAP = 500.0
WARNING_AT = 400.0
FREEZE_AT = 440.0
RESERVE = 60.0

# Postes de dépense et enveloppes par défaut (total planifié 440 € + 60 € de réserve).
ENVELOPES = {
    "infra": {"label": "Alojamento, base de dados, armazenamento, cópias de segurança", "amount": 150.0},
    "ai_api": {"label": "IA, Autodesk e APIs profissionais", "amount": 100.0},
    "tools": {"label": "Ferramentas, automatizações e e-mails", "amount": 30.0},
    "ads": {"label": "Publicidade", "amount": 120.0},
    "print": {"label": "Impressão e distribuição", "amount": 40.0},
    "reserve": {"label": "Reserva para imprevistos", "amount": 60.0},
}

# Rattachement des fournisseurs de l'inventaire vérifié aux postes ci-dessus.
CATEGORY_TO_ENVELOPE = {
    "storage": "infra", "local": "infra", "public_data": "infra", "documents": "infra",
    "ai": "ai_api", "cad": "ai_api", "search": "ai_api", "media": "ai_api", "audio": "ai_api",
    "email": "tools", "seo": "tools", "payments": "tools", "other": "tools",
    "postal": "print", "ads": "ads",
}
PROVIDER_ENVELOPE = {p: CATEGORY_TO_ENVELOPE.get(row[1], "tools") for p, row in PROVIDERS.items()}

STALE_AFTER_DAYS = 7  # au-delà, la source de coûts est considérée périmée


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def get_config() -> dict:
    doc = await db.budget_cap.find_one({"_id": CAP_ID}, {"_id": 0})
    if not doc:
        return {"cap_eur": DEFAULT_CAP, "warning_at": WARNING_AT, "freeze_at": FREEZE_AT,
                "envelopes": {k: v["amount"] for k, v in ENVELOPES.items()}, "updated_at": None}
    return doc


async def save_config(envelopes: dict[str, float], admin_id: str) -> dict:
    """Les enveloppes sont ajustables ; le plafond global de 500 € ne l'est pas ici."""
    clean = {k: round(float(envelopes.get(k, ENVELOPES[k]["amount"])), 2) for k in ENVELOPES}
    doc = {"cap_eur": DEFAULT_CAP, "warning_at": WARNING_AT, "freeze_at": FREEZE_AT,
           "envelopes": clean, "updated_at": _now(), "updated_by": admin_id}
    await db.budget_cap.update_one({"_id": CAP_ID}, {"$set": doc}, upsert=True)
    return doc


async def status(month: str | None = None) -> dict:
    """État du plafond : dépensé, engagé, reste, seuils, et par poste."""
    month = month or current_month()
    cfg = await get_config()
    rows = await rows_for(month)
    overall = totals(rows)
    confirmed = float(overall["confirmed_eur"] or 0)
    estimated = float(overall["estimated_eur"] or 0)

    # Engagements réservés par les actions autorisées mais pas encore facturées.
    holds = await db.budget_holds.find(
        {"month": month, "released": {"$ne": True}}, {"_id": 0}).to_list(500)
    held = round(sum(float(h.get("amount_eur") or 0) for h in holds), 2)

    used = round(confirmed + estimated + held, 2)
    remaining = round(cfg["cap_eur"] - used, 2)

    per_env: dict[str, dict] = {}
    for key, meta in ENVELOPES.items():
        env_rows = [r for r in rows if PROVIDER_ENVELOPE.get(r["provider"]) == key]
        t = totals(env_rows)
        env_held = round(sum(float(h["amount_eur"]) for h in holds if h.get("envelope") == key), 2)
        env_used = round(float(t["confirmed_eur"] or 0) + float(t["estimated_eur"] or 0) + env_held, 2)
        budget = float(cfg["envelopes"].get(key, meta["amount"]))
        per_env[key] = {
            "label": meta["label"], "budget_eur": budget, "used_eur": env_used,
            "confirmed_eur": t["confirmed_eur"], "estimated_eur": t["estimated_eur"],
            "held_eur": env_held, "remaining_eur": round(budget - env_used, 2),
            "percent": round(env_used / budget * 100, 1) if budget else None,
            "over": env_used > budget,
        }

    # Fraîcheur de la source de coûts : une source périmée bloque les engagements.
    sync = await db.api_expense_sync.find_one({"_id": "local"}, {"_id": 0}) or {}
    last = sync.get("last_synced_at") or sync.get("initialized_at")
    stale_days = None
    if last:
        dt = last if isinstance(last, datetime) else None
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            except ValueError:
                dt = None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            stale_days = (datetime.now(timezone.utc) - dt).days
    source_stale = stale_days is None or stale_days > STALE_AFTER_DAYS

    state = ("exceeded" if used >= cfg["cap_eur"]
             else "frozen" if used >= cfg["freeze_at"]
             else "warning" if used >= cfg["warning_at"] else "ok")

    return {
        "month": month, "currency": "EUR",
        "cap_eur": cfg["cap_eur"], "warning_at": cfg["warning_at"], "freeze_at": cfg["freeze_at"],
        "reserve_eur": RESERVE,
        "confirmed_eur": overall["confirmed_eur"], "estimated_eur": overall["estimated_eur"],
        "held_eur": held, "used_eur": used, "remaining_eur": remaining,
        "percent": round(used / cfg["cap_eur"] * 100, 1) if cfg["cap_eur"] else None,
        "state": state,
        "new_engagements_allowed": state in ("ok", "warning") and not source_stale,
        "blocking_reason": ("teto de 500 € atingido" if state == "exceeded"
                           else "limiar de congelamento de 440 € atingido: só os compromissos obrigatórios ou já autorizados continuam possíveis" if state == "frozen"
                           else "fonte de custos desatualizada ou ausente: reconcilie as faturas antes de qualquer novo compromisso" if source_stale
                           else None),
        "cost_source": {"last_sync": last.isoformat() if isinstance(last, datetime) else last, "stale": source_stale, "days_since": stale_days,
                        "note": "os montantes incluem as despesas confirmadas, as estimativas e os compromissos reservados"},
        "incomplete": bool(overall["unavailable"] or overall["unconverted"]),
        "envelopes": per_env,
        "holds": holds,
        "generated_at": _now(),
    }


async def check_engagement(amount_eur: float, envelope: str, essential: bool = False,
                           month: str | None = None) -> dict:
    """Vérifie si un engagement peut être pris. Ne réserve rien."""
    st = await status(month)
    env = st["envelopes"].get(envelope)
    if not env:
        return {"allowed": False, "reason": f'rubrica desconhecida: {envelope}', "status": st}
    after = round(st["used_eur"] + amount_eur, 2)
    if st["cost_source"]["stale"]:
        return {"allowed": False, "reason": st["blocking_reason"], "projected_used_eur": after, "status": st}
    if after > st["cap_eur"]:
        return {"allowed": False, "reason": "ultrapassaria o teto de 500 €",
                "projected_used_eur": after, "status": st}
    if after > st["freeze_at"] and not essential:
        return {"allowed": False,
                "reason": "ultrapassaria o limiar de congelamento de 440 € (reserva de 60 € preservada para as despesas obrigatórias)",
                "projected_used_eur": after, "status": st}
    if env["used_eur"] + amount_eur > env["budget_eur"] and not essential:
        return {"allowed": False, "reason": f"ultrapassaria o envelope «{env['label']} »",
                "projected_used_eur": after, "status": st}
    return {"allowed": True, "reason": None, "projected_used_eur": after, "status": st}


async def reserve(amount_eur: float, envelope: str, label: str, *, essential: bool = False,
                  ref: str | None = None) -> dict:
    """Réserve un montant avant une action coûteuse. Refuse si le garde-fou l'interdit."""
    month = current_month()
    verdict = await check_engagement(amount_eur, envelope, essential, month)
    if not verdict["allowed"]:
        return {"reserved": False, "reason": verdict["reason"]}
    hold = {"hold_id": f"hold_{datetime.now(timezone.utc).timestamp():.0f}", "month": month,
            "envelope": envelope, "amount_eur": round(float(amount_eur), 2), "label": label[:200],
            "ref": ref, "essential": essential, "created_at": _now(), "released": False}
    await db.budget_holds.insert_one(dict(hold))
    return {"reserved": True, "hold": hold}


async def release(hold_id: str, actual_eur: float | None = None) -> bool:
    """Libère une réservation après rapprochement avec le montant réellement facturé."""
    res = await db.budget_holds.update_one(
        {"hold_id": hold_id},
        {"$set": {"released": True, "released_at": _now(), "actual_eur": actual_eur}})
    return res.modified_count > 0
