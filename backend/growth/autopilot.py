"""Auto-pilote Growth : après chaque audit → surcharges SEO proposées pour les défauts de balises, clôture des problèmes disparus,
idées d'articles depuis les questions où ConstruPilot est absent, pipeline complet (recherche → brief → rédaction → contrôles)
jusqu'à la relecture. Respecte le plafond budget mensuel et le quota d'articles/semaine. Rien n'est publié sans approbation
en mode « review »."""
import asyncio
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from core.db import db
from growth import content as ct
from growth.common import new_id, now_iso, spent
from growth.research import find_sources

logger = logging.getLogger(__name__)

META_KINDS = {"missing_title", "long_title", "missing_description", "long_description", "duplicate_title"}
AUTO_STATES = ("idea", "brief", "draft")


def _settings(project: dict) -> dict:
    from growth.seed import DEFAULT_SETTINGS
    return {**DEFAULT_SETTINGS, **(project.get("settings") or {})}


async def budget_state(project: dict) -> dict:
    st = _settings(project)
    cap = float((st.get("budgets") or {}).get("monthly_usd") or 0)
    used = await spent(project["project_id"], "month")
    return {"cap_usd": cap, "spent_usd": round(used, 4), "ok": not cap or used < cap}


def _clamp(text: str, n: int) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


async def propose_seo_overrides(project: dict, audit: dict, apply_mode: str) -> int:
    """Une proposition title/description par URL en défaut (LLM, contrainte 60/160), statut « proposed » ou « approved » selon le mode."""
    by_url: dict[str, list] = {}
    async for i in db.growth_issues.find({"audit_id": audit["audit_id"], "status": "open", "kind": {"$in": list(META_KINDS)}}, {"_id": 0}):
        by_url.setdefault(i["url"], []).append(i)
    created = 0
    for url, issues in list(by_url.items())[:40]:
        path = urlparse(url).path or "/"
        if await db.growth_seo_overrides.find_one({"project_id": project["project_id"], "path": path, "status": {"$in": ["proposed", "approved"]}, "kind": {"$ne": "canonical"}}):
            continue
        page = await db.growth_pages.find_one({"audit_id": audit["audit_id"], "url": url}, {"_id": 0, "title": 1, "meta_description": 1, "h1": 1, "h2": 1})
        if not page:
            continue
        lang = "français" if project["key"] == "fr" else "portugais du Portugal"
        prompt = (f"Page : {url}\nTitre actuel : {page.get('title') or '(vide)'}\nDescription actuelle : {page.get('meta_description') or '(vide)'}\n"
                  f"H1 : {page.get('h1')}\nH2 : {(page.get('h2') or [])[:8]}\nDéfauts : {sorted({i['kind'] for i in issues})}\n"
                  f"Écris en {lang} un <title> unique (max 58 caractères, sans « | », terminer par « · ConstruPilot » seulement si la place le permet) "
                  f"et une meta description (140 à 158 caractères, bénéfice concret, sans superlatif ni promesse de classement). "
                  'Réponds en JSON strict : {"title": str, "description": str}')
        try:
            data = ct._json(await ct._llm("Tu es un consultant SEO rigoureux. JSON strict uniquement.", prompt, project["project_id"], "seo_override"))
        except Exception as e:  # noqa: BLE001
            logger.warning("seo override llm failed %s: %s", url, e); continue
        if "error" in data or not data.get("title"):
            continue
        await db.growth_seo_overrides.insert_one({
            "override_id": new_id("seo"), "project_id": project["project_id"], "audit_id": audit["audit_id"], "url": url, "path": path,
            "title": _clamp(data["title"], 60), "description": _clamp(data.get("description") or "", 160),
            "current_title": page.get("title"), "current_description": page.get("meta_description"),
            "issue_kinds": sorted({i["kind"] for i in issues}), "issue_ids": [i["issue_id"] for i in issues],
            "status": "approved" if apply_mode == "auto" else "proposed", "created_at": now_iso(), "created_by": "autopilot"})
        created += 1
    return created


async def close_resolved(project: dict, audit: dict) -> int:
    """Les problèmes d'audits précédents qui ne réapparaissent pas sur une URL re-crawlée sont clôturés (preuve : ré-audit)."""
    crawled = {p["url"] async for p in db.growth_pages.find({"audit_id": audit["audit_id"]}, {"_id": 0, "url": 1})}
    current = {(i["url"], i["kind"]) async for i in db.growth_issues.find({"audit_id": audit["audit_id"]}, {"_id": 0, "url": 1, "kind": 1})}
    closed = 0
    async for i in db.growth_issues.find({"project_id": project["project_id"], "status": {"$in": ["open", "fixing"]}, "audit_id": {"$ne": audit["audit_id"]}}, {"_id": 0, "issue_id": 1, "url": 1, "kind": 1}):
        if i["url"] in crawled and (i["url"], i["kind"]) not in current:
            await db.growth_issues.update_one({"issue_id": i["issue_id"]}, {"$set": {"status": "fixed", "fixed_at": now_iso(), "fixed_by": f"autopilot (ré-audit {audit['audit_id']})"}})
            closed += 1
    async for a in db.growth_actions.find({"project_id": project["project_id"], "status": {"$ne": "done"}, "issue_ids.0": {"$exists": True}}, {"_id": 0, "action_id": 1, "issue_ids": 1}):
        still = await db.growth_issues.count_documents({"issue_id": {"$in": a["issue_ids"]}, "status": {"$in": ["open", "fixing"]}})
        if still == 0:
            await db.growth_actions.update_one({"action_id": a["action_id"]}, {"$set": {"status": "done", "done_at": now_iso(), "done_by": "autopilot"}})
    return closed


async def _weekly_quota_left(project: dict) -> int:
    per_week = int(_settings(project).get("articles_per_week") or 3)
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    made = await db.growth_contents.count_documents({"project_id": project["project_id"], "created_by": "autopilot", "created_at": {"$gte": since}})
    return max(0, per_week - made)


async def ideas_from_signals(project: dict, limit: int) -> list[dict]:
    """Idées : questions sans mention de ConstruPilot dans la dernière campagne, puis questions du référentiel sans contenu."""
    if limit <= 0:
        return []
    pid = project["project_id"]
    covered = {c.get("question_id") async for c in db.growth_contents.find({"project_id": pid, "question_id": {"$ne": ""}, "status": {"$nin": ["archived", "failed"]}}, {"_id": 0, "question_id": 1})}
    ranked: list[tuple[int, str, str]] = []
    campaign = await db.growth_campaigns.find_one({"project_id": pid, "status": {"$in": ["completed", "stopped", "budget_reached"]}}, {"_id": 0}, sort=[("started_at", -1)])
    if campaign:
        agg: dict[str, dict] = {}
        async for t in db.growth_tests.find({"campaign_id": campaign["campaign_id"], "status": "completed", "branded": False}, {"_id": 0, "question_id": 1, "question_text": 1, "self_mentioned": 1}):
            d = agg.setdefault(t["question_id"], {"text": t["question_text"], "valid": 0, "self": 0})
            d["valid"] += 1; d["self"] += 1 if t.get("self_mentioned") else 0
        for qid, d in agg.items():
            if d["self"] == 0 and d["valid"] and qid not in covered:
                ranked.append((0, qid, d["text"]))
    async for q in db.growth_questions.find({"project_id": pid, "active": {"$ne": False}, "branded": {"$ne": True}}, {"_id": 0, "question_id": 1, "text": 1}).limit(60):
        if q["question_id"] not in covered and all(r[1] != q["question_id"] for r in ranked):
            ranked.append((1, q["question_id"], q.get("text") or ""))
    out = []
    for _, qid, text in ranked[:limit]:
        c = {"content_id": new_id("cnt"), "project_id": pid, "topic": text.strip(), "intent": "découverte", "audience": "professionnels du bâtiment et particuliers", "format": "guide pratique",
             "status": "idea", "version": 1, "question_id": qid, "created_by": "autopilot", "created_at": now_iso(), "updated_at": now_iso(), "autopilot_log": []}
        await db.growth_contents.insert_one(dict(c))
        out.append(c)
    return out


async def _log(content_id: str, step: str, ok: bool, note: str = "") -> None:
    await db.growth_contents.update_one({"content_id": content_id}, {"$push": {"autopilot_log": {"step": step, "ok": ok, "note": note[:300], "at": now_iso()}}})


async def run_pipeline(project: dict, content: dict) -> dict:
    """Recherche → brief → rédaction → contrôles → « à relire » (ou publication si mode auto et contrôles réussis)."""
    cid = content["content_id"]
    try:
        research = await find_sources(project, content)
        await db.growth_contents.update_one({"content_id": cid}, {"$set": {"research": research, "updated_at": now_iso()}})
        await _log(cid, "research", True, f"{len(research['sources'])} sources vérifiées ({research['trusted_count']} officielles), {len(research['rejected'])} rejetées")
        content = await db.growth_contents.find_one({"content_id": cid}, {"_id": 0})
        b = await ct.generate_brief(project, content)
        await db.growth_contents.update_one({"content_id": cid}, {"$set": {**{k: b.get(k) for k in ("title", "slug", "description", "audience", "outline", "internal_links", "sources_to_check", "cta", "search_intent_note")}, "status": "brief", "updated_at": now_iso()}})
        await _log(cid, "brief", True, b.get("title") or "")
        content = await db.growth_contents.find_one({"content_id": cid}, {"_id": 0})
        d = await ct.generate_draft(project, content)
        await db.growth_contents.update_one({"content_id": cid}, {"$set": {"title": d.get("title") or content.get("title"), "body_markdown": d.get("body_markdown") or "", "claims_about_construpilot": d.get("claims_about_construpilot") or [],
                                                                            "sources": d.get("sources") or [], "faq": d.get("faq") or [], "status": "draft", "updated_at": now_iso()}})
        await _log(cid, "draft", True, f"{len((d.get('body_markdown') or '').split())} mots")
        content = await db.growth_contents.find_one({"content_id": cid}, {"_id": 0})
        checks = await ct.quality_checks(project, content)
        await db.growth_contents.update_one({"content_id": cid}, {"$set": {"checks": checks, "status": "review"}})
        await _log(cid, "check", checks["passed"], f"{len(checks['blocking'])} blocage(s), {len(checks['warnings'])} avertissement(s)")
        if checks["passed"] and _settings(project).get("publish_mode") == "auto":
            content = await db.growth_contents.find_one({"content_id": cid}, {"_id": 0})
            res = await ct.publish(project, content, "autopilot")
            await db.growth_contents.update_one({"content_id": cid}, {"$set": {"status": "published", **res}, "$push": {"publications": res}})
            await _log(cid, "publish", True, res.get("published_url") or "")
        return {"content_id": cid, "ok": True, "passed": checks["passed"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("autopilot pipeline %s failed: %s", cid, e)
        await db.growth_contents.update_one({"content_id": cid}, {"$set": {"status": "failed", "publish_error": f"{type(e).__name__}: {e}"[:300]}})
        await _log(cid, "pipeline", False, f"{type(e).__name__}: {e}")
        return {"content_id": cid, "ok": False, "error": str(e)[:200]}


async def notify_admins(message: str, url: str) -> None:
    async for a in db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}):
        await db.notifications.insert_one({"notif_id": "n_" + secrets.token_hex(5), "user_id": a["user_id"], "type": "growth_autopilot", "message": message, "url": url, "created_at": now_iso(), "read": False})


async def after_audit(project_id: str, audit_id: str) -> dict:
    project = await db.growth_projects.find_one({"project_id": project_id}, {"_id": 0})
    audit = await db.growth_audits.find_one({"audit_id": audit_id}, {"_id": 0})
    st = _settings(project)
    out = {"issues_closed": await close_resolved(project, audit), "overrides_proposed": 0}
    if st.get("auto_fix_enabled", True):
        from growth import autofix
        out["reappeared"] = await autofix.flag_reappeared(project["project_id"], audit["audit_id"])
        fix = await autofix.run(project, audit, trigger="audit")
        out["autofix"] = {"run_id": fix.get("run_id"), **(fix.get("counts") or {})}
    elif (await budget_state(project))["ok"]:
        out["overrides_proposed"] = await propose_seo_overrides(project, audit, st.get("seo_override_mode", "review"))
    return out


async def run(project_id: str, trigger: str = "manual", resume_only: bool = False) -> dict:
    """Cycle complet. `resume_only` : reprend seulement les contenus autopilot restés en idée/brief/brouillon."""
    project = await db.growth_projects.find_one({"project_id": project_id}, {"_id": 0})
    run_id = new_id("run")
    report = {"run_id": run_id, "project_id": project_id, "trigger": trigger, "started_at": now_iso(), "status": "running", "issues_closed": 0, "overrides_proposed": 0,
              "contents_created": 0, "contents_ready": 0, "contents_failed": 0, "skipped_budget": False, "notes": []}
    await db.growth_autopilot_runs.insert_one(dict(report))
    try:
        st = _settings(project)
        budget = await budget_state(project)
        report["budget"] = budget
        audit = await db.growth_audits.find_one({"project_id": project_id, "status": {"$in": ["completed", "stopped"]}}, {"_id": 0}, sort=[("finished_at", -1)])
        if audit and not resume_only:
            report["issues_closed"] = await close_resolved(project, audit)
            if st.get("auto_fix_enabled", True):
                from growth import autofix
                fix = await autofix.run(project, audit, trigger=trigger)
                report["autofix"] = {"run_id": fix.get("run_id"), **(fix.get("counts") or {})}
            elif budget["ok"]:
                report["overrides_proposed"] = await propose_seo_overrides(project, audit, st.get("seo_override_mode", "review"))
        if not budget["ok"]:
            report["skipped_budget"] = True
            report["notes"].append(f"Plafond mensuel atteint ({budget['spent_usd']:.2f} / {budget['cap_usd']:.2f} $) : aucune génération IA")
            await notify_admins(f"Growth auto-pilote : plafond budget mensuel atteint ({budget['spent_usd']:.2f} $ / {budget['cap_usd']:.2f} $). Générations suspendues.", "/admin/growth?tab=budget")
        else:
            pending = await db.growth_contents.find({"project_id": project_id, "created_by": "autopilot", "status": {"$in": list(AUTO_STATES)}}, {"_id": 0}).to_list(10)
            if not resume_only:
                new = await ideas_from_signals(project, await _weekly_quota_left(project))
                report["contents_created"] = len(new)
                pending += new
            for c in pending[: int(st.get("autopilot_batch") or 3)]:
                if not (await budget_state(project))["ok"]:
                    report["skipped_budget"] = True; break
                res = await run_pipeline(project, c)
                report["contents_ready" if res.get("ok") else "contents_failed"] += 1
        if budget["ok"] and (datetime.now(timezone.utc).weekday() == 0 or trigger == "manual"):
            from growth.marketing import weekly_newsletter, on_published
            async for c in db.growth_contents.find({"project_id": project_id, "status": "published", "published_url": {"$exists": True}}, {"_id": 0}).sort("published_at", -1).limit(5):
                await on_published(project, c)
            nl = await weekly_newsletter(project)
            report["newsletter_proposed"] = bool(nl)
        ready = await db.growth_contents.count_documents({"project_id": project_id, "status": "review", "created_by": "autopilot"})
        proposed = await db.growth_seo_overrides.count_documents({"project_id": project_id, "status": "proposed"})
        if trigger != "manual" and (ready or proposed):
            await notify_admins(f"Growth auto-pilote ({project['name']}) : {ready} article(s) à relire, {proposed} correction(s) SEO à approuver.", "/admin/growth?tab=autopilot")
        report.update({"status": "completed", "finished_at": now_iso(), "pending_review": ready, "pending_overrides": proposed})
    except Exception as e:  # noqa: BLE001
        logger.exception("autopilot run failed")
        report.update({"status": "failed", "error": f"{type(e).__name__}: {e}"[:300], "finished_at": now_iso()})
    await db.growth_autopilot_runs.update_one({"run_id": run_id}, {"$set": report})
    return report


async def run_all(trigger: str = "scheduler") -> list[dict]:
    out = []
    for p in await db.growth_projects.find({}, {"_id": 0}).to_list(20):
        if _settings(p).get("autopilot_enabled", True):
            out.append(await run(p["project_id"], trigger))
    return out
