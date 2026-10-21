"""Purge des données d'un compte (partagée entre l'admin et l'auto-suppression)."""
from core.db import db

PURGE_COLLECTIONS = [
    "projects", "leads", "quote_analyses", "quote_sends", "quote_templates",
    "clients", "entitlements", "payment_transactions", "plans_takeoff",
    "plans_takeoff_history", "material_orders", "notifications", "photo_analyses",
    "pro_documents", "doc_counters", "steel_analyses", "roofing_analyses",
    "waterproofing_analyses", "vrd_analyses", "dpgf_imports",
    "company_price_libraries", "library_items", "suppliers", "situations",
    "prorata", "site_reports", "site_reserves", "site_checklist", "hr_files",
    "hr_notes", "hr_photos", "hr_timesheets", "push_subscriptions",
    "price_alerts", "api_keys", "referrals", "einvoice_accounts",
    "einvoice_inbox", "shared_calcs", "tool_presets", "pc_settings",
    "pc_study_history", "chat_messages", "activity_log", "user_sessions",
    "two_fa_codes", "password_reset_tokens", "known_devices", "login_attempts",
    "evolution_runs", "evolution_compares", "pro_documents_files",
    "marketplace_pros", "chantiers", "chantier_messages", "chantier_issues",
    "chantier_participants", "chantier_milestones", "assistant_convs",
    "assistant_msgs", "assistant_docs", "assistant_doc_chunks", "assistant_prefs",
    "support_tickets", "journey_events",
]

OWNER_KEYS = ("user_id", "owner_user_id", "created_by", "pro_user_id",
              "owner_id", "author_id", "from_user_id", "assigned_to")


async def purge_user_data(user_id: str) -> dict[str, int]:
    """Supprime tous les documents appartenant à l'utilisateur. Ne touche pas `users`."""
    purged: dict[str, int] = {}
    owner_filter = {"$or": [{k: user_id} for k in OWNER_KEYS]}
    for coll in dict.fromkeys(PURGE_COLLECTIONS):
        try:
            res = await db[coll].delete_many(owner_filter)
            if res.deleted_count:
                purged[coll] = purged.get(coll, 0) + res.deleted_count
        except Exception:  # noqa: BLE001 — collection absente / robustesse
            continue
    try:
        org_res = await db.organizations.delete_many(
            {"$or": [{"owner_user_id": user_id}, {"owner_id": user_id}, {"user_id": user_id}]})
        if org_res.deleted_count:
            purged["organizations"] = org_res.deleted_count
        await db.organizations.update_many(
            {"members.user_id": user_id}, {"$pull": {"members": {"user_id": user_id}}})
        await db.org_members.delete_many({"user_id": user_id})
    except Exception:  # noqa: BLE001
        pass
    return purged
