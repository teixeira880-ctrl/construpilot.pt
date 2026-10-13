"""Compact dossier health from persisted results, with source freshness."""
from engines.platform_supervisor import can_check_quotes, resource_fingerprint


async def build_workspace(db, chantier, user):
    uid, cid = user["user_id"], chantier["chantier_id"]
    scope = {"user_id": uid, "chantier_id": cid, "trashed_at": None}
    plans = await db.plans_takeoff.find(scope, {"_id": 0, "plan_id": 1, "filename": 1, "calibrations": 1,
        "measurements": 1, "rooms": 1, "chantier_id": 1, "trashed_at": 1}).sort("plan_id", 1).to_list(201)
    quotes = []
    if can_check_quotes(user):
        quotes = await db.pro_documents.find({**scope, "doc_type": "quote"}, {"_id": 0, "doc_id": 1, "title": 1,
            "lines": 1, "totals": 1, "deposit_pct": 1, "status": 1, "signed": 1, "chantier_id": 1, "trashed_at": 1}).sort("doc_id", 1).to_list(201)
    truncated = len(plans) > 200 or len(quotes) > 200
    resources, summary = [], {"unchecked": 0, "stale": 0, "needs_review": 0, "checked": 0}
    ids = [p["plan_id"] for p in plans[:200]] + [q["doc_id"] for q in quotes[:200]]
    checks = await db.agent_checks.find({"user_id": uid, "resource_id": {"$in": ids}}, {"_id": 0}).sort("checked_at", -1).to_list(2000)
    latest = {}
    for check in checks:
        latest.setdefault((check.get("kind"), check.get("resource_id")), check)
    for kind, docs, id_key, label in (("plan", plans[:200], "plan_id", "filename"), ("quote", quotes[:200], "doc_id", "title")):
        for doc in docs:
            check = latest.get((kind, doc[id_key]))
            state = "unchecked"
            if check and check.get("source_fingerprint"):
                state = "stale" if check["source_fingerprint"] != resource_fingerprint(doc, kind) else ("needs_review" if check.get("status") == "needs_review" else "checked")
            summary[state] += 1
            resources.append({"kind": kind, "id": doc[id_key], "label": doc.get(label) or doc[id_key], "state": state,
                              "issues": len(check.get("issues") or []) if check and state != "stale" else None,
                              "checked_at": check.get("checked_at") if check else None, "run_id": check.get("run_id") if check else None})
    runs = await db.agent_runs.find({"user_id": uid, "chantier_id": cid}, {"_id": 0, "run_id": 1, "agent": 1,
        "status": 1, "created_at": 1, "error": 1}).sort("created_at", -1).to_list(10)
    return {"chantier_id": cid, "summary": summary, "resources": resources, "runs": runs,
            "truncated": truncated, "source_measurements_verified": False,
            "note": "Contrôle des données enregistrées. Une modification du plan ou du devis impose un nouveau contrôle ; aucune précision de lecture n'est certifiée."}
