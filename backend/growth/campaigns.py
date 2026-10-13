"""Visibility campaigns: cost estimate, background execution with budget reservation and stop, transparent metrics."""
import asyncio
import logging

from core.db import db
from growth.brands import detect
from growth.common import budget_check, new_id, now_iso, record_cost
from growth.providers import estimate_test_cost, provider_status, run_test

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = "v1-2026-09"
RUNNING: dict[str, asyncio.Task] = {}


def plan_tests(campaign: dict) -> int:
    return len(campaign["question_ids"]) * len(campaign["providers"]) * int(campaign.get("repetitions") or 1)


def estimate(campaign: dict) -> float:
    per_q = sum(estimate_test_cost(p["provider"], p.get("model")) for p in campaign["providers"])
    return round(per_q * len(campaign["question_ids"]) * int(campaign.get("repetitions") or 1), 4)


async def run_campaign(campaign_id: str):
    c = await db.growth_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0})
    project = await db.growth_projects.find_one({"project_id": c["project_id"]}, {"_id": 0})
    lang = project["language"][:2]
    brands = await db.growth_brands.find({"project_id": c["project_id"]}, {"_id": 0}).to_list(100)
    questions = {q["question_id"]: q async for q in db.growth_questions.find({"question_id": {"$in": c["question_ids"]}}, {"_id": 0})}
    status = provider_status()
    await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "running", "started_at": now_iso(), "brands_scope": [b["name"] for b in brands]}})
    total = plan_tests(c)
    already = {(t["question_id"], t["provider"], t["repetition"]) async for t in db.growth_tests.find({"campaign_id": campaign_id}, {"_id": 0, "question_id": 1, "provider": 1, "repetition": 1})}
    done, errors = len(already), int(c.get("errors") or 0)
    try:
        for rep in range(1, int(c.get("repetitions") or 1) + 1):
            for qid in c["question_ids"]:
                q = questions.get(qid)
                for p in c["providers"]:
                    if (qid, p["provider"], rep) in already:
                        continue
                    cur = await db.growth_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0, "stop_requested": 1})
                    if cur and cur.get("stop_requested"):
                        raise asyncio.CancelledError()
                    test = {"test_id": new_id("t"), "campaign_id": campaign_id, "project_id": c["project_id"], "question_id": qid, "question_text": q["text"] if q else "?", "intent": q.get("intent") if q else None,
                            "branded": bool(q and q.get("branded")), "provider": p["provider"], "model_requested": p.get("model") or p.get("preset") or "défaut", "repetition": rep, "language": project["language"],
                            "country_requested": project["country"], "protocol_version": PROTOCOL_VERSION, "executed_at": now_iso()}
                    if not q:
                        test.update({"status": "excluded", "exclusion_reason": "question supprimée"})
                    elif not status.get(p["provider"], {}).get("configured"):
                        test.update({"status": "excluded", "exclusion_reason": f"connexion {p['provider']} non configurée"})
                    else:
                        est = estimate_test_cost(p["provider"], p.get("model"))
                        ok, why = await budget_check(project, est)
                        if not ok:
                            await db.growth_tests.insert_one({**test, "status": "excluded", "exclusion_reason": why})
                            await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "budget_reached", "finished_at": now_iso(), "note": why}})
                            return
                        await record_cost(c["project_id"], p["provider"], "visibility_test", est, test["test_id"], estimated=True)  # reservation
                        try:
                            res = await run_test(p["provider"], q["text"], lang, p)
                            await db.growth_costs.update_one({"ref": test["test_id"]}, {"$set": {"usd": res["cost_usd"], "estimated": res["cost_estimated"]}})
                            if not (res.get("text") or "").strip():
                                test.update({"status": "excluded", "exclusion_reason": "réponse vide", **{k: res[k] for k in ("model", "web_search", "cost_usd", "latency_ms")}})
                            else:
                                mentions = detect(res["text"], res["citations"], brands, lang)
                                test.update({"status": "completed", "response_text": res["text"], "citations": res["citations"], "model": res["model"], "web_search": res["web_search"],
                                             "citations_observable": bool(res["web_search"]), "cost_usd": res["cost_usd"], "cost_estimated": res["cost_estimated"], "latency_ms": res["latency_ms"],
                                             "geo_applied": res["geo_applied"], "usage": res.get("usage"), "mentions": mentions,
                                             "self_mentioned": any(m["is_self"] and m["mention"] for m in mentions), "self_cited": any(m["is_self"] and m["domain_citation"] for m in mentions)})
                        except Exception as e:
                            errors += 1
                            test.update({"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"})
                            await db.growth_costs.update_one({"ref": test["test_id"]}, {"$set": {"usd": 0.0}})
                    await db.growth_tests.insert_one(test)
                    done += 1
                    await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"done_tests": done, "progress": int(done * 100 / max(total, 1)), "errors": errors}})
        await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "completed", "finished_at": now_iso(), "progress": 100, "note": None}})
    except asyncio.CancelledError:
        await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "stopped", "finished_at": now_iso()}})
    except Exception as e:
        logger.exception("campaign failed")
        await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "failed", "error": str(e)[:300], "finished_at": now_iso()}})
    finally:
        actual = await db.growth_costs.aggregate([{"$match": {"project_id": c["project_id"], "ref": {"$in": [t["test_id"] async for t in db.growth_tests.find({"campaign_id": campaign_id}, {"test_id": 1})]}}},
                                                   {"$group": {"_id": None, "s": {"$sum": "$usd"}}}]).to_list(1)
        await db.growth_campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"actual_cost_usd": round(actual[0]["s"], 4) if actual else 0.0}})
        RUNNING.pop(campaign_id, None)


def _rate(num: int, den: int) -> dict:
    return {"value": round(num * 100 / den, 1) if den else None, "numerator": num, "denominator": den, "display": f"{round(num * 100 / den, 1)} %" if den else "données indisponibles"}


async def metrics(campaign_id: str) -> dict:
    tests = await db.growth_tests.find({"campaign_id": campaign_id}, {"_id": 0, "response_text": 0, "citations": 0}).to_list(5000)
    c = await db.growth_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0})
    valid = [t for t in tests if t["status"] == "completed"]
    unbranded = [t for t in valid if not t.get("branded")]
    observable = [t for t in valid if t.get("citations_observable")]
    pairs_self = sum(1 for t in valid if any(m["is_self"] and (m["mention"] or m["domain_citation"]) and not m.get("false_positive") for m in t.get("mentions") or []))
    pairs_all = sum(len({m["brand_id"] for m in t.get("mentions") or [] if (m["mention"] or m["domain_citation"]) and not m.get("false_positive")}) for t in valid)
    by_brand = {}
    for t in valid:
        for m in t.get("mentions") or []:
            if m.get("false_positive"):
                continue
            e = by_brand.setdefault(m["name"], {"name": m["name"], "is_self": m["is_self"], "responses_mentioning": 0, "responses_citing": 0, "recommendations": 0, "ranks": []})
            e["responses_mentioning"] += 1 if m["mention"] else 0
            e["responses_citing"] += 1 if m["domain_citation"] else 0
            e["recommendations"] += 1 if m["recommendation"] else 0
            if m["rank"]:
                e["ranks"].append(m["rank"])
    for e in by_brand.values():
        e["avg_rank"] = round(sum(e["ranks"]) / len(e["ranks"]), 1) if e["ranks"] else None
        e["ranks"] = len(e["ranks"])
    excluded = [{"test_id": t["test_id"], "question": t["question_text"], "provider": t["provider"], "status": t["status"], "reason": t.get("exclusion_reason") or t.get("error")} for t in tests if t["status"] != "completed"]
    per_dim = {}
    for t in valid:
        for dim, key in (("provider", t["provider"]), ("intent", t.get("intent") or "?"), ("model", t.get("model") or "?")):
            d = per_dim.setdefault(dim, {}).setdefault(key, {"valid": 0, "self": 0})
            d["valid"] += 1
            d["self"] += 1 if t.get("self_mentioned") else 0
    for dim in per_dim.values():
        for k, d in dim.items():
            dim[k] = {**d, **_rate(d["self"], d["valid"])}
    return {
        "campaign": c, "planned": c.get("planned_tests", 0), "valid": len(valid), "errors": len([t for t in tests if t["status"] == "error"]), "excluded_count": len(excluded), "excluded": excluded[:100],
        "mention_rate": {**_rate(sum(1 for t in unbranded if t.get("self_mentioned")), len(unbranded)), "formula": "réponses valides SANS marque mentionnant ConstruPilot / réponses valides sans marque × 100"},
        "mention_rate_all": {**_rate(sum(1 for t in valid if t.get("self_mentioned")), len(valid)), "formula": "réponses valides (toutes questions) mentionnant ConstruPilot / réponses valides × 100"},
        "citation_rate": {**_rate(sum(1 for t in observable if t.get("self_cited")), len(observable)), "formula": "réponses citant un domaine ConstruPilot / réponses valides dont les citations sont observables × 100",
                          "note": "Seuls les fournisseurs avec recherche web renvoient des citations observables."},
        "share_of_mentions": {**_rate(pairs_self, pairs_all), "formula": "couples uniques réponse–ConstruPilot / couples uniques réponse–marque (marques suivies) × 100", "brands_scope": c.get("brands_scope") or []},
        "coverage": {**_rate(len(valid), c.get("planned_tests", 0)), "formula": "tests valides terminés / tests planifiés × 100"},
        "by_brand": sorted(by_brand.values(), key=lambda e: -e["responses_mentioning"]), "by_dimension": per_dim,
        "caveat": "Tests via API : ils ne reproduisent pas nécessairement les réponses des interfaces grand public. Une variation entre périodes n'est pas la preuve d'un effet d'une action marketing.",
    }
