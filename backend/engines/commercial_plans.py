"""Catalogue commercial B2B ConstruPilot — source de vérité UNIQUE (2026-11).

Quatre offres : Solo · Professional · Business · Enterprise.

Règles absolues encodées ici (et vérifiées par tests) :
  * Enterprise n'a AUCUN montant (ni prix, ni minimum, ni estimation) — vente sur contact.
  * Les prix publics sont HT (FR) / + IVA (PT) : les Prices Stripe sont créés en
    ``tax_behavior="exclusive"``.
  * Annuel = 12 × mensuel × (1 − 15 %), arrondi au centime.
  * Les plans historiques (pro_*, pro_business_*, premium_*, project_pass) restent
    intacts : les clients existants conservent leur offre (grandfathering).

Le marché (fr | pt) est fixé par l'environnement ``CP_MARKET`` de chaque déploiement :
les lookup_keys Stripe sont préfixées par marché pour éviter toute collision si les deux
sites partagent un jour le même compte Stripe.
"""
from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal

ANNUAL_DISCOUNT_PCT = 15
UNLIMITED = -1

# Clés de fonctions. statut : "available" (vérifié dans le code), "beta", "roadmap".
# Le statut est AFFICHÉ sur la page tarifs : on ne vend pas comme disponible ce qui ne l'est pas.
FEATURES: dict[str, dict] = {
    "pdf_import":            {"status": "available"},
    "dwg_dxf_import":        {"status": "available"},
    "ai_plan_reading":       {"status": "available"},
    "takeoff":               {"status": "available"},
    "quotes":                {"status": "available"},
    "price_library":         {"status": "available"},
    "manual_edit":           {"status": "available"},
    "export_pdf_excel":      {"status": "available"},
    "project_history":       {"status": "available"},
    "support_email":         {"status": "available"},
    # Professional
    "advanced_takeoff":      {"status": "available"},
    "advanced_quotes":       {"status": "available"},
    "revision_compare":      {"status": "beta"},
    "clients_crm":           {"status": "available"},
    "proposals":             {"status": "available"},
    "quote_branding":        {"status": "available"},
    "collaboration":         {"status": "available"},
    "site_basic":            {"status": "available"},
    "cost_margin_reports":   {"status": "available"},
    "change_history":        {"status": "available"},
    "support_priority":      {"status": "available"},
    # Business
    "site_advanced":         {"status": "available"},
    "planned_vs_actual":     {"status": "available"},
    "team_management":       {"status": "available"},
    "role_permissions":      {"status": "available"},
    "business_dashboards":   {"status": "available"},
    "financial_tracking":    {"status": "available"},
    "budget_vs_execution":   {"status": "available"},
    "advanced_reports":      {"status": "available"},
    "multi_project":         {"status": "available"},
    "activity_audit":        {"status": "available"},
    "integrations":          {"status": "beta"},
    "assisted_onboarding":   {"status": "available"},
    # Enterprise
    "multi_company":         {"status": "roadmap"},
    "departments":           {"status": "roadmap"},
    "enterprise_permissions": {"status": "roadmap"},
    "enterprise_api":        {"status": "roadmap"},
    "erp_integrations":      {"status": "roadmap"},
    "custom_automations":    {"status": "roadmap"},
    "custom_config":         {"status": "available"},
    "dedicated_onboarding":  {"status": "available"},
    "account_manager":       {"status": "available"},
    "enterprise_support":    {"status": "available"},
    "contractual_sla":       {"status": "available"},
    "capacity_on_demand":    {"status": "available"},
}

_SOLO = ["pdf_import", "dwg_dxf_import", "ai_plan_reading", "takeoff", "quotes", "price_library",
         "manual_edit", "export_pdf_excel", "project_history", "support_email"]
_PRO = ["advanced_takeoff", "advanced_quotes", "revision_compare", "clients_crm", "proposals",
        "quote_branding", "collaboration", "site_basic", "cost_margin_reports", "change_history",
        "support_priority"]
_BUS = ["site_advanced", "planned_vs_actual", "team_management", "role_permissions",
        "business_dashboards", "financial_tracking", "budget_vs_execution", "advanced_reports",
        "multi_project", "activity_audit", "integrations", "assisted_onboarding"]
_ENT = ["multi_company", "departments", "enterprise_permissions", "enterprise_api",
        "erp_integrations", "custom_automations", "custom_config", "dedicated_onboarding",
        "account_manager", "enterprise_support", "contractual_sla", "capacity_on_demand"]

GB = 1024 ** 3

# tier : niveau d'accès historique auquel le plan donne droit (voir engines/access.py).
#  Solo → "pro" ; Professional et Business → "pro_business" (équipes, chantier, Gantt…).
PLANS: dict[str, dict] = {
    "solo": {
        "key": "solo", "tier": "pro", "sort": 10, "highlight": False, "checkout": True,
        "monthly_cents": 9900,
        "limits": {"seats": 1, "active_projects": 10, "pages_monthly": 100, "storage_bytes": 10 * GB},
        "features": _SOLO, "inherits": None,
    },
    "professional": {
        "key": "professional", "tier": "pro_business", "sort": 20, "highlight": True, "checkout": True,
        "monthly_cents": 24900,
        "limits": {"seats": 5, "active_projects": 50, "pages_monthly": 750, "storage_bytes": 100 * GB},
        "features": _SOLO + _PRO, "inherits": "solo",
    },
    "business": {
        "key": "business", "tier": "pro_business", "sort": 30, "highlight": False, "checkout": True,
        "monthly_cents": 59900,
        "limits": {"seats": 15, "active_projects": 200, "pages_monthly": 3000, "storage_bytes": 500 * GB},
        "features": _SOLO + _PRO + _BUS, "inherits": "professional",
    },
    "enterprise": {
        # AUCUN champ monétaire. Capacités = références commerciales, pas des garanties.
        "key": "enterprise", "tier": "pro_business", "sort": 40, "highlight": False, "checkout": False,
        "limits": {"seats": 50, "active_projects": 500, "pages_monthly": 10000, "storage_bytes": 2048 * GB},
        "limits_are_reference": True,
        "features": _SOLO + _PRO + _BUS + _ENT, "inherits": "business",
    },
}

INTERVALS = ("month", "year")


# Seule ligne qui diffère entre les dépôts construpilot.fr ("fr") et construpilot.pt ("pt").
DEFAULT_MARKET = "pt"


def market() -> str:
    m = (os.environ.get("CP_MARKET") or DEFAULT_MARKET).strip().lower()
    return m if m in ("fr", "pt") else "fr"


def annual_cents(monthly_cents: int) -> int:
    """12 × mensuel × (1 − 15 %), arrondi half-up au centime (99 € → 1 009,80 €)."""
    v = Decimal(monthly_cents) * 12 * (Decimal(100 - ANNUAL_DISCOUNT_PCT) / 100)
    return int(v.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def price_cents(plan_key: str, interval: str) -> int:
    plan = PLANS[plan_key]
    if "monthly_cents" not in plan:
        raise ValueError("Plan sans prix public (vente sur contact)")
    if interval == "month":
        return plan["monthly_cents"]
    if interval == "year":
        return annual_cents(plan["monthly_cents"])
    raise ValueError(f"Intervalle invalide : {interval}")


def plan_id(plan_key: str, interval: str) -> str:
    """Identifiant DB/entitlement. Préfixe ``cp_`` : ne commence JAMAIS par 'pro' (les anciens
    tests de préfixe ``startswith('pro')`` ne doivent pas capter ces plans)."""
    return f"cp_{plan_key}_{'monthly' if interval == 'month' else 'yearly'}"


def lookup_key(plan_key: str, interval: str, mkt: str | None = None) -> str:
    return f"construpilot_{mkt or market()}_{plan_id(plan_key, interval)}"


def parse_plan_id(pid: str | None) -> tuple[str, str] | None:
    """'cp_business_yearly' → ('business', 'year') ; None si ce n'est pas un plan commercial."""
    if not pid or not pid.startswith("cp_"):
        return None
    try:
        _, key, per = pid.split("_", 2)
    except ValueError:
        return None
    if key not in PLANS or per not in ("monthly", "yearly"):
        return None
    return key, "month" if per == "monthly" else "year"


def tier_for_plan_id(pid: str | None) -> str | None:
    """Tier d'accès pour TOUT plan_id (nouveau ou historique). Remplace les tests de préfixe."""
    if not pid:
        return None
    parsed = parse_plan_id(pid)
    if parsed:
        return PLANS[parsed[0]]["tier"]
    if pid == "cp_enterprise":
        return "pro_business"
    if pid == "project_pass":
        return "project_pass"
    if pid.startswith("premium"):
        return "premium"
    if pid.startswith("pro_business"):
        return "pro_business"
    if pid.startswith("pro_"):
        return "pro"
    return None


def limits_for_plan_id(pid: str | None) -> dict | None:
    """Limites applicables. None = plan historique / aucun plan commercial → pas de nouvelle
    limite (les clients existants ne perdent rien)."""
    parsed = parse_plan_id(pid)
    if parsed:
        return dict(PLANS[parsed[0]]["limits"])
    if pid == "cp_enterprise":
        return dict(PLANS["enterprise"]["limits"])
    return None


def db_plan_docs(mkt: str | None = None) -> list[dict]:
    """Documents ``db.plans`` pour Solo/Professional/Business (mensuel + annuel).

    audience="b2b" : invisibles pour l'ancienne page (qui filtre particulier/pro).
    stripe_sync=False : ``ensure_stripe_catalog`` ne crée RIEN dans Stripe tant que le
    lancement commercial n'est pas autorisé (voir COMMERCIAL_STRIPE_SYNC).
    """
    mkt = mkt or market()
    docs = []
    for key, p in PLANS.items():
        if "monthly_cents" not in p:
            continue
        for interval in INTERVALS:
            docs.append({
                "plan_id": plan_id(key, interval),
                "code": plan_id(key, interval).upper(),
                "name": key.capitalize() + ("" if interval == "month" else " — annual"),
                "audience": "b2b", "kind": "subscription", "commercial_key": key,
                "amount_cents": price_cents(key, interval), "currency": "eur", "interval": interval,
                "tax_behavior": "exclusive",
                "lookup_key": lookup_key(key, interval, mkt),
                "quotas": {"seats": p["limits"]["seats"], "projects": p["limits"]["active_projects"],
                           "pages_monthly": p["limits"]["pages_monthly"],
                           "storage_bytes": p["limits"]["storage_bytes"]},
                "features": list(p["features"]),
                "sort_order": 100 + p["sort"] + (0 if interval == "month" else 1),
                "active": True, "highlight": p["highlight"], "stripe_sync": False,
            })
    return docs


def public_catalog() -> dict:
    """Vue publique (API /commercial/plans). Enterprise : aucune clé monétaire."""
    plans = []
    for key, p in sorted(PLANS.items(), key=lambda kv: kv[1]["sort"]):
        item = {"key": key, "highlight": p["highlight"], "checkout": p["checkout"],
                "limits": dict(p["limits"]), "limits_are_reference": bool(p.get("limits_are_reference")),
                "features": [{"key": f, "status": FEATURES[f]["status"]} for f in p["features"]],
                "inherits": p["inherits"]}
        if "monthly_cents" in p:
            item["price"] = {
                "currency": "EUR", "tax": "excl",
                "month_cents": p["monthly_cents"],
                "year_cents": annual_cents(p["monthly_cents"]),
                "year_monthly_equiv_cents": round(annual_cents(p["monthly_cents"]) / 12),
            }
        plans.append(item)
    return {"market": market(), "annual_discount_pct": ANNUAL_DISCOUNT_PCT, "plans": plans}


def checkout_open() -> bool:
    """Souscription en ligne des nouvelles offres : FERMÉE par défaut (autorisation requise)."""
    return os.environ.get("COMMERCIAL_CHECKOUT_ENABLED", "false").lower() == "true"


def live_charges_allowed() -> bool:
    """Garde-fou : refuse une clé Stripe live tant que STRIPE_LIVE_ALLOWED != true."""
    key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""
    if key.startswith("sk_live") or key.startswith("rk_live"):
        return os.environ.get("STRIPE_LIVE_ALLOWED", "false").lower() == "true"
    return True
